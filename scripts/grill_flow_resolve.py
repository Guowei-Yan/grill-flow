import os
from pathlib import Path
from grill_flow_errors import die

def helper_basename(path: Path) -> str:
    return path.name

def _check(path: Path) -> Path:
    if not path.is_file():
        die("helper_not_found", f"helper not found: {path}")
    if not os.access(path, os.X_OK):
        die("helper_not_executable", f"helper not executable: {path}")
    return path

def resolve_helper(env, skill_scripts_dir: Path, local_share_dir: Path) -> Path:
    if "GRILL_FLOW_HELPER" in env:
        raw = env.get("GRILL_FLOW_HELPER")
        if not raw:
            die("invalid_args", "GRILL_FLOW_HELPER is empty")
        return _check(Path(raw))
    cand = skill_scripts_dir / "grill-flow.py"
    if cand.exists():
        return _check(cand)
    share = local_share_dir / "grill-flow.py"
    if share.exists():
        return _check(share)
    die("helper_not_found", "no helper in skill scripts or local share")
