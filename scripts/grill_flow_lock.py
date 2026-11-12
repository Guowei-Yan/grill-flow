import json
import os
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path
from grill_flow_errors import die

SUPPORTED_PLATFORMS = ("linux", "darwin", "freebsd", "openbsd", "netbsd")


def read_lock(run_dir: Path):
    p = run_dir / ".lock"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def release_exclusive(run_dir: Path) -> None:
    p = run_dir / ".lock"
    if p.exists():
        p.unlink()


def _default_is_live(pid: int, base: str) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    proc_dir = Path(f"/proc/{pid}")
    if sys.platform.startswith("linux") and Path("/proc").is_dir():
        if not proc_dir.exists():
            return False
        try:
            status_path = proc_dir / "status"
            if status_path.is_file():
                for line in status_path.read_text().splitlines():
                    if line.startswith("State:") and line.split()[1].startswith("Z"):
                        return False
            cmd = (proc_dir / "cmdline").read_bytes().split(b"\0")
        except OSError:
            return False
        return any(Path(x.decode(errors="ignore")).name == base for x in cmd if x)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    except OSError:
        return False
    try:
        res = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat=,args="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    line = (res.stdout or "").strip()
    if res.returncode != 0 or not line:
        return False
    parts = line.split(None, 1)
    if not parts or parts[0].startswith("Z"):
        return False
    args_str = parts[1] if len(parts) > 1 else ""
    try:
        tokens = shlex.split(args_str)
    except ValueError:
        tokens = args_str.split()
    return any(Path(tok).name == base for tok in tokens if tok)


def acquire_exclusive(run_dir: Path, *, force_token=None, helper_basename="grill-flow.py", is_live=None):
    if not sys.platform.startswith(SUPPORTED_PLATFORMS):
        die("unsupported_platform", "lock requires POSIX (Linux or macOS/BSD)")
    run_dir.mkdir(parents=True, exist_ok=True)
    if is_live is None:
        is_live = _default_is_live
    existing = read_lock(run_dir)
    if existing:
        live = is_live(existing["pid"], helper_basename)
        if live and force_token is None:
            die("run_in_progress", "exclusive lock held")
        if live and force_token != existing.get("token"):
            die("force_lock_required", "force token mismatch")
    rec = {"pid": os.getpid(), "startedAt": str(time.time()), "token": secrets.token_hex(16)}
    (run_dir / ".lock").write_text(json.dumps(rec))
    return rec
