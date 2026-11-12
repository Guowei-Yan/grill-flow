import json, os, secrets, time
from pathlib import Path
from grill_flow_errors import die

def read_lock(run_dir: Path):
    p = run_dir / ".lock"
    if not p.exists():
        return None
    return json.loads(p.read_text())

def release_exclusive(run_dir: Path) -> None:
    p = run_dir / ".lock"
    if p.exists():
        p.unlink()

def acquire_exclusive(run_dir: Path, *, force_token=None, helper_basename="grill-flow.py", is_live=None):
    import sys
    if not sys.platform.startswith("linux"):
        die("unsupported_platform", "lock requires Linux")
    run_dir.mkdir(parents=True, exist_ok=True)
    if is_live is None:
        def is_live(pid, base):
            if not Path(f"/proc/{pid}").exists():
                return False
            try:
                cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            except OSError:
                return False
            return any(Path(x.decode(errors="ignore")).name == base for x in cmd if x)
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
