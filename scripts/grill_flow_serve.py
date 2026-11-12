import json
import os
import posixpath
import secrets
import signal
import socket
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from grill_flow_errors import die

SERVE_START_REQUIRES_EXCLUSIVE_LOCK = True
SERVE_STOP_REQUIRES_EXCLUSIVE_LOCK = False
SERVE_CHILD_READ_ONLY = True

REPO_MAX_LINES = 500
REPO_MAX_BYTES = 256 * 1024
REPO_SCAN_GUARD = 2_000_000

def normalize_repo_relpath(raw: str) -> str | None:
    if raw is None:
        return None
    s = unquote(str(raw))
    if "\x00" in s:
        return None
    if s.startswith("/") or (len(s) >= 2 and s[1] == ":"):
        return None
    n = posixpath.normpath(s)
    if n in ("", ".", "..") or n.startswith("../") or "/../" in f"/{n}/":
        return None
    if n.startswith("./"):
        n = n[2:]
    return n or None

def build_repo_allowlist(run_dir: Path) -> set[str]:
    out: set[str] = set()
    ob = run_dir / "obligations.json"
    if ob.is_file():
        data = json.loads(ob.read_text())
        if isinstance(data, list):
            for row in data:
                p = normalize_repo_relpath(str(row.get("path") or ""))
                if p:
                    out.add(p)
    for name in ("graph.json", "ledger.json"):
        fp = run_dir / name
        if not fp.is_file():
            continue
        doc = json.loads(fp.read_text())
        if name == "graph.json":
            for e in doc.get("edges") or []:
                er = e.get("evidenceRef") or {}
                p = normalize_repo_relpath(str(er.get("path") or ""))
                if p:
                    out.add(p)
        else:
            for entry in (doc or {}).values():
                disp = (entry or {}).get("disposition") or {}
                er = disp.get("evidenceRef") or {}
                p = normalize_repo_relpath(str(er.get("path") or ""))
                if p:
                    out.add(p)
    return out

def read_repo_slice(file_path: Path, start: int, end: int) -> tuple[str | None, str | None]:
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < 1 or start > end:
        return None, "range"
    if end - start + 1 > REPO_MAX_LINES:
        return None, "range"
    try:
        with file_path.open("rb") as f:
            head = f.read(8192)
            if b"\x00" in head:
                return None, "binary"
            f.seek(0)
            out = []
            scanned = 0
            for raw in f:
                scanned += 1
                if scanned > REPO_SCAN_GUARD and scanned < start:
                    return None, "scan"
                if scanned < start:
                    continue
                if scanned > end:
                    break
                try:
                    out.append(raw.decode("utf-8").rstrip("\n").rstrip("\r"))
                except UnicodeDecodeError:
                    return None, "binary"
            text = "\n".join(out)
            if len(text.encode("utf-8")) > REPO_MAX_BYTES:
                return None, "range"
            return text, None
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "io"

def _json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")

def server_info_path(run_dir: Path) -> Path:
    return run_dir / "server-info.json"

def read_server_info(run_dir: Path):
    p = server_info_path(run_dir)
    if not p.is_file():
        return None
    return json.loads(p.read_text())

def write_server_info(run_dir: Path, info: dict) -> None:
    server_info_path(run_dir).write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")

def clear_server_info(run_dir: Path) -> None:
    p = server_info_path(run_dir)
    if p.is_file():
        p.unlink()

def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])

def local_http_hosts() -> frozenset[str]:
    """Hosts allowed for /repo (loopback + this machine's IPv4 addrs — WSL/Windows)."""
    hosts = {"127.0.0.1", "localhost"}
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            hosts.add(res[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 80))
            hosts.add(s.getsockname()[0])
    except OSError:
        pass
    return frozenset(hosts)

SERVE_BIND = "0.0.0.0"

def build_serve_child_argv(
    helper: Path,
    *,
    repo_root: Path,
    run_dir: Path,
    instance_id: str,
    port: int,
) -> list:
    helper_s = str(helper)
    return [
        helper_s,
        helper_s,
        "--repo-root", str(repo_root),
        "--run-dir", str(run_dir),
        f"--grill-flow-instance={instance_id}",
        "--read-only",
        "serve-http",
        "--port", str(port),
    ]

def _pid_alive(pid: int) -> bool:
    status_path = Path(f"/proc/{pid}/status")
    if not status_path.is_file():
        return False
    try:
        for line in status_path.read_text().splitlines():
            if line.startswith("State:"):
                return not line.split()[1].startswith("Z")
    except OSError:
        return False
    return True

def _cmdline_args(pid: int) -> list:
    raw = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    return [x.decode(errors="ignore") for x in raw if x]

def _has_instance_flag(pid: int, instance_id: str) -> bool:
    needle = f"--grill-flow-instance={instance_id}"
    return needle in _cmdline_args(pid)

def serve_start(
    run_dir: Path,
    helper: Path,
    *,
    repo_root: Path,
    port: int | None = None,
    popen=subprocess.Popen,
) -> dict:
    instance_id = secrets.token_hex(8)
    if port is None or port == 0:
        port = pick_free_port()
    argv = build_serve_child_argv(
        helper,
        repo_root=repo_root,
        run_dir=run_dir,
        instance_id=instance_id,
        port=port,
    )
    proc = popen(
        argv,
        executable=sys.executable,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    info = {
        "pid": proc.pid,
        "instanceId": instance_id,
        "port": port,
        "readOnly": True,
    }
    write_server_info(run_dir, info)
    return info

def serve_stop(run_dir: Path) -> dict:
    info = read_server_info(run_dir)
    if info is None:
        die("serve_info_missing", "server-info.json missing")
    pid = int(info["pid"])
    instance_id = str(info["instanceId"])
    if not _pid_alive(pid):
        clear_server_info(run_dir)
        return {}
    if _has_instance_flag(pid, instance_id):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(50):
            if not _pid_alive(pid):
                break
            time.sleep(0.05)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for _ in range(20):
                if not _pid_alive(pid):
                    break
                time.sleep(0.05)
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        clear_server_info(run_dir)
        return {}
    die("serve_stop_mismatch", "live pid argv instance mismatch")

class _ReadOnlyHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        self.send_error(405, "Method Not Allowed")

    def do_PUT(self):
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        self.send_error(405, "Method Not Allowed")

    def do_PATCH(self):
        self.send_error(405, "Method Not Allowed")

    def log_message(self, format, *args):
        return

def make_handler(run_dir: Path, repo_root: Path, instance_id: str, allowlist: set[str]) -> type[_ReadOnlyHandler]:
    from urllib.parse import urlparse, parse_qs, unquote
    root = repo_root.resolve()

    class Handler(_ReadOnlyHandler):
        def _send_json(self, status: int, obj: dict, body: bool = True) -> None:
            raw = _json_bytes(obj)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if body:
                self.wfile.write(raw)

        def _unavail(self, status: int, reason: str, body: bool = True) -> None:
            self._send_json(status, {"unavailable": True, "reason": reason}, body=body)

        def _handle_repo(self, body: bool) -> bool:
            parsed = urlparse(self.path)
            p = parsed.path
            if p != "/repo" and not p.startswith("/repo/"):
                return False
            if p in ("/repo", "/repo/"):
                self._unavail(400, "path", body=body)
                return True
            if self.command not in ("GET", "HEAD"):
                self._unavail(405, "method", body=body)
                return True
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            if host not in local_http_hosts():
                self._unavail(403, "host", body=body)
                return True
            qs = parse_qs(parsed.query)
            tok = (qs.get("t") or [None])[0] or self.headers.get("X-Grill-Flow-Instance")
            if tok != instance_id:
                self._unavail(403, "token", body=body)
                return True
            rel_raw = unquote(p[len("/repo/"):])
            rel = normalize_repo_relpath(rel_raw)
            if not rel:
                self._unavail(400, "path", body=body)
                return True
            if rel not in allowlist:
                self._unavail(403, "allowlist", body=body)
                return True
            try:
                cand = (root / rel).resolve()
            except (OSError, RuntimeError):
                self._unavail(404, "missing", body=body)
                return True
            if not cand.is_relative_to(root):
                self._unavail(403, "escape", body=body)
                return True
            if not cand.is_file():
                self._unavail(404, "missing", body=body)
                return True
            try:
                start = int((qs.get("start") or [""])[0])
                end = int((qs.get("end") or [""])[0])
            except ValueError:
                self._unavail(400, "range", body=body)
                return True
            text, err = read_repo_slice(cand, start, end)
            if err:
                status = {"binary": 415, "range": 400, "scan": 400, "missing": 404, "io": 500}.get(err, 400)
                self._unavail(status, err, body=body)
                return True
            self._send_json(200, {"path": rel, "start": start, "end": end, "text": text}, body=body)
            return True

        def do_GET(self):
            if self._handle_repo(body=True):
                return
            super().do_GET()

        def do_HEAD(self):
            if self._handle_repo(body=False):
                return
            super().do_HEAD()

        def do_POST(self):
            if self._handle_repo(body=True):
                return
            super().do_POST()

        def do_PUT(self):
            if self._handle_repo(body=True):
                return
            super().do_PUT()

        def do_DELETE(self):
            if self._handle_repo(body=True):
                return
            super().do_DELETE()

        def do_PATCH(self):
            if self._handle_repo(body=True):
                return
            super().do_PATCH()

    return Handler

def run_serve_http(run_dir: Path, *, port: int, repo_root: Path, instance_id: str, read_only: bool = True) -> None:
    if not read_only:
        die("invalid_args", "serve-http requires --read-only")
    root = repo_root.resolve()
    allow = build_repo_allowlist(run_dir)
    os.chdir(run_dir)
    server = ThreadingHTTPServer((SERVE_BIND, port), make_handler(run_dir, root, instance_id, allow))
    try:
        server.serve_forever()
    finally:
        server.server_close()
