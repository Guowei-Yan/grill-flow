import hmac
import json
import os
import secrets
import shlex
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from grill_flow_errors import die

SUPPORTED_PLATFORMS = ("linux", "darwin", "freebsd", "openbsd", "netbsd")


def read_lock(run_dir: Path):
    p = run_dir / ".lock"
    if not p.exists():
        return None
    try:
        raw = p.read_text()
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


@contextmanager
def _dir_mutex(run_dir: Path):
    import fcntl

    fd = os.open(str(run_dir), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def release_exclusive(run_dir: Path, *, expected_token: str | None = None) -> None:
    p = run_dir / ".lock"
    if not run_dir.is_dir():
        return

    def _unlink_if_owned() -> None:
        if expected_token is not None:
            current = read_lock(run_dir)
            if current is None:
                return
            cur_tok = current.get("token")
            if not (isinstance(cur_tok, str) and cur_tok and hmac.compare_digest(cur_tok, expected_token)):
                return
        p.unlink(missing_ok=True)

    if sys.platform.startswith(SUPPORTED_PLATFORMS):
        with _dir_mutex(run_dir):
            _unlink_if_owned()
    else:
        _unlink_if_owned()


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


def _atomic_publish_lock(run_dir: Path, lock_path: Path, payload: bytes) -> None:
    tmp_path = run_dir / f".lock.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    fd = os.open(str(tmp_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        try:
            view = memoryview(payload)
            written = 0
            while written < len(view):
                written += os.write(fd, view[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(str(tmp_path), str(lock_path))
    finally:
        try:
            os.unlink(str(tmp_path))
        except FileNotFoundError:
            pass


def acquire_exclusive(run_dir: Path, *, force_token=None, helper_basename="grill-flow.py", is_live=None):
    if not sys.platform.startswith(SUPPORTED_PLATFORMS):
        die("unsupported_platform", "lock requires POSIX (Linux or macOS/BSD)")
    run_dir.mkdir(parents=True, exist_ok=True)
    if is_live is None:
        is_live = _default_is_live
    lock_path = run_dir / ".lock"
    rec = {"pid": os.getpid(), "startedAt": str(time.time()), "token": secrets.token_hex(16)}
    payload = json.dumps(rec).encode("utf-8")

    with _dir_mutex(run_dir):
        existing = read_lock(run_dir)
        if existing is not None:
            live = is_live(existing.get("pid"), helper_basename)
            if live and force_token is None:
                die("run_in_progress", "exclusive lock held")
            expected_tok = existing.get("token")
            valid_force = (
                isinstance(expected_tok, str)
                and bool(expected_tok)
                and isinstance(force_token, str)
                and bool(force_token)
                and hmac.compare_digest(force_token, expected_tok)
            )
            if live and not valid_force:
                die("force_lock_required", "force token mismatch")
            lock_path.unlink(missing_ok=True)
        elif lock_path.exists():
            # Reclaim corrupt/empty/non-dict lock file safely under directory flock.
            lock_path.unlink(missing_ok=True)
        try:
            _atomic_publish_lock(run_dir, lock_path, payload)
        except FileExistsError:
            die("run_in_progress", "exclusive lock contention")
        return rec
