import json
from pathlib import Path
from grill_flow_globs import DEFAULT_SKIP, DEFAULT_TEST_EXCLUDE
from grill_flow_hash import content_hash8, surface_hash

def surface_path(run_dir: Path) -> Path:
    return run_dir / "surface.json"

def surface_exists(run_dir: Path) -> bool:
    return surface_path(run_dir).is_file()

def load_surface(run_dir: Path) -> dict:
    return json.loads(surface_path(run_dir).read_text())

def write_surface(run_dir: Path, surface: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    surface_path(run_dir).write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")

def build_file_set_surface(*, targets: list, test_exclude=None, skip=None) -> dict:
    return {
        "mode": "file-set",
        "targets": list(targets),
        "baseOid": None,
        "headOid": None,
        "dirty": False,
        "testExclude": list(test_exclude if test_exclude is not None else DEFAULT_TEST_EXCLUDE),
        "skip": list(skip if skip is not None else DEFAULT_SKIP),
    }

def build_git_diff_surface(*, base_oid: str, head_oid: str, dirty: bool = False, test_exclude=None, skip=None) -> dict:
    return {
        "mode": "git-diff",
        "targets": [],
        "baseOid": base_oid,
        "headOid": head_oid,
        "dirty": bool(dirty),
        "testExclude": list(test_exclude if test_exclude is not None else DEFAULT_TEST_EXCLUDE),
        "skip": list(skip if skip is not None else DEFAULT_SKIP),
    }

def path_note_digest(note: dict) -> str:
    blob = json.dumps(note, sort_keys=True, separators=(",", ":"))
    return content_hash8(blob)

def build_c11_hash_object(surface: dict, *, obligation_ids: list, path_notes: list) -> dict:
    digests = sorted(path_note_digest(n) for n in path_notes)
    return {
        "mode": surface["mode"],
        "targets": list(surface.get("targets") or []),
        "baseOid": surface.get("baseOid"),
        "headOid": surface.get("headOid"),
        "dirty": bool(surface.get("dirty", False)),
        "testExclude": list(surface.get("testExclude") or []),
        "skip": list(surface.get("skip") or []),
        "obligationIds": sorted(obligation_ids),
        "pathNotesDigests": digests,
    }

def write_surface_hash(run_dir: Path, hash_obj: dict) -> str:
    digest = surface_hash(hash_obj)
    (run_dir / "surface-hash.txt").write_text(digest + "\n")
    return digest
