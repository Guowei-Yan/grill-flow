from pathlib import Path
from grill_flow_hash import content_hash8
from grill_flow_globs import DEFAULT_SKIP, DEFAULT_TEST_EXCLUDE, is_skipped, is_test_excluded
import re
import subprocess

GIT_DIFF_FIND_RENAMES = True

def classify_run_kind(obligations, path_notes, level0_paths) -> str:
    if not obligations and not path_notes and not level0_paths:
        return "empty"
    if not obligations and path_notes and not level0_paths:
        return "pathNotesOnly"
    if not obligations and level0_paths:
        return "emptyLedger"
    return "normal"

def level0_expanded_for(*, kind: str) -> bool:
    if kind == "obligation":
        return False
    if kind == "empty_or_binary_seed":
        return True
    raise ValueError(kind)

def inventory_file_set(repo_root: Path, named_paths) -> dict:
    obligations, path_notes, level0 = [], [], []
    for rel in named_paths:
        raw = (repo_root / rel).read_bytes()
        if b"\x00" in raw:
            path_notes.append({"kind": "binary", "path": rel})
            level0.append(rel)
            continue
        text = raw.decode("utf-8", errors="replace")
        level0.append(rel)
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip() == "":
                continue
            obligations.append({
                "obligationId": f"file:{rel}:{i}:{content_hash8(line)}",
                "path": rel, "line": i, "kind": "semantic", "change": "present",
            })
    return {"obligations": obligations, "pathNotes": path_notes, "level0": level0}

def _run_git(repo_root: Path, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

def _git_out(repo_root: Path, args: list) -> str:
    r = _run_git(repo_root, args)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "git failed")
    return r.stdout

def _rev_parse(repo_root: Path, ref: str) -> str:
    return _git_out(repo_root, ["rev-parse", ref]).strip()

def _blob_oid(repo_root: Path, treeish: str, path: str):
    r = _run_git(repo_root, ["rev-parse", f"{treeish}:{path}"])
    if r.returncode != 0:
        return None
    return r.stdout.strip()

def _parse_name_status(text: str) -> list:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        code = status[0]
        if code in ("R", "C") and len(parts) >= 3:
            rows.append({"code": code, "score": status[1:], "old": parts[1], "new": parts[2]})
        elif len(parts) >= 2:
            rows.append({"code": code, "path": parts[1], "old": parts[1], "new": parts[1]})
    return rows

def _parse_numstat(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        if " => " in path:
            path = path.split(" => ", 1)[-1].strip("{}")
        out[path] = {"added": a, "deleted": d, "binary": a == "-" and d == "-"}
    return out

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

def _parse_unified_file_diffs(diff_text: str) -> dict:
    files = {}
    current = None
    old_ln = new_ln = 0
    pending_old = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                files.setdefault(current, {"hunks": [], "is_binary": False, "is_submodule": False})
            current = None
            pending_old = []
            continue
        if line.startswith("rename from "):
            continue
        if line.startswith("rename to "):
            current = line[len("rename to "):]
            files.setdefault(current, {"hunks": [], "is_binary": False, "is_submodule": False})
            continue
        if line.startswith("copy from "):
            continue
        if line.startswith("copy to "):
            current = line[len("copy to "):]
            files.setdefault(current, {"hunks": [], "is_binary": False, "is_submodule": False})
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            if path != "/dev/null":
                current = path
                files.setdefault(current, {"hunks": [], "is_binary": False, "is_submodule": False})
            continue
        if line.startswith("Binary files "):
            m = re.search(r" and ([^\s]+) differ$", line)
            if m:
                path = m.group(1)
                if path.startswith("b/"):
                    path = path[2:]
                current = path
                files.setdefault(current, {"hunks": [], "is_binary": True, "is_submodule": False})
                files[current]["is_binary"] = True
            continue
        if "Subproject commit" in line:
            if current is not None:
                files.setdefault(current, {"hunks": [], "is_binary": False, "is_submodule": True})
                files[current]["is_submodule"] = True
            continue
        m = _HUNK_RE.match(line)
        if m and current is not None:
            old_ln = int(m.group(1))
            new_ln = int(m.group(3))
            pending_old = []
            files[current]["hunks"].append({
                "old_start": old_ln,
                "new_start": new_ln,
                "old": [],
                "new": [],
            })
            continue
        if current is None or not files.get(current, {}).get("hunks"):
            continue
        hunk = files[current]["hunks"][-1]
        if line.startswith("+") and not line.startswith("+++"):
            text = line[1:]
            hunk["new"].append({"line": new_ln, "text": text})
            new_ln += 1
        elif line.startswith("-") and not line.startswith("---"):
            text = line[1:]
            hunk["old"].append({"line": old_ln, "text": text})
            old_ln += 1
        elif line.startswith("\\"):
            continue
        else:
            old_ln += 1
            new_ln += 1
    return files

def _summary_mode_paths(repo_root: Path, range_args: list) -> set:
    text = _git_out(repo_root, ["diff", "--find-renames", "--summary", *range_args])
    paths = set()
    for line in text.splitlines():
        line = line.strip()
        if "mode change" in line or line.startswith("mode change"):
            parts = line.split()
            if parts:
                paths.add(parts[-1])
        if line.startswith("change mode"):
            parts = line.split()
            if parts:
                paths.add(parts[-1])
    return paths

def _obligation(
    *,
    side: str,
    path: str,
    lineno: int,
    text: str,
    change: str,
    evidence_ref: dict,
    pair_id: str | None = None,
) -> dict:
    oid = f"diff:{side}:{path}:{lineno}:{content_hash8(text)}"
    row = {
        "obligationId": oid,
        "path": path,
        "line": lineno,
        "kind": "semantic",
        "change": change,
        "evidenceRef": evidence_ref,
        "lineText": text,
    }
    if pair_id is not None:
        row["pairId"] = pair_id
    return row

def _evidence(path: str, *, oid, source: str) -> dict:
    return {"path": path, "oid": oid, "source": source, "note": ""}

def _collect_from_range(
    repo_root: Path,
    *,
    range_args: list,
    old_tree: str | None,
    new_tree: str | None,
    source: str,
    test_exclude,
    skip,
    find_copies: bool,
) -> tuple:
    obligations = []
    path_notes = []
    level0 = set()
    ns_flags = ["diff", "--find-renames", "--name-status"]
    if find_copies:
        ns_flags = ["diff", "--find-renames", "--find-copies", "--find-copies-harder", "--name-status"]
    name_status = _parse_name_status(_git_out(repo_root, ns_flags + range_args))
    num_flags = ["diff", "--find-renames", "--numstat"]
    if find_copies:
        num_flags = ["diff", "--find-renames", "--find-copies", "--find-copies-harder", "--numstat"]
    numstat = _parse_numstat(_git_out(repo_root, num_flags + range_args))
    diff_flags = ["diff", "--find-renames", "-U0"]
    if find_copies:
        diff_flags = ["diff", "--find-renames", "--find-copies", "--find-copies-harder", "-U0"]
    file_diffs = _parse_unified_file_diffs(_git_out(repo_root, diff_flags + range_args))
    mode_paths = _summary_mode_paths(repo_root, range_args)

    handled = set()
    for row in name_status:
        code = row["code"]
        if code in ("R", "C"):
            path = row["new"]
            old_path = row["old"]
            if is_test_excluded(path, test_exclude) or is_test_excluded(old_path, test_exclude):
                handled.add(path)
                handled.add(old_path)
                continue
            if is_skipped(path, skip) or is_skipped(old_path, skip):
                path_notes.append({"kind": "skip", "path": path})
                handled.add(path)
                handled.add(old_path)
                continue
            kind = "rename" if code == "R" else "copy"
            path_notes.append({
                "kind": kind,
                "path": path,
                "from": old_path,
                "to": path,
            })
            handled.add(path)
            handled.add(old_path)
            fd = file_diffs.get(path) or {}
            hunks = fd.get("hunks") or []
            for h in hunks:
                pair_id = f"pair:{path}:{h['old_start']}:{h['new_start']}"
                for item in h["old"]:
                    if item["text"].strip() == "":
                        continue
                    oid = _blob_oid(repo_root, old_tree, old_path) if old_tree and source == "oid" else None
                    ev = _evidence(old_path, oid=oid, source=source if oid else ("worktree" if source == "worktree" else "oid"))
                    if source == "oid" and oid is None:
                        ev = _evidence(old_path, oid=None, source="worktree")
                    elif source == "oid":
                        ev = _evidence(old_path, oid=oid, source="oid")
                    else:
                        ev = _evidence(old_path, oid=None, source="worktree")
                    obligations.append(_obligation(
                        side="old", path=path, lineno=item["line"], text=item["text"],
                        change="deleted", evidence_ref=ev, pair_id=pair_id,
                    ))
                    level0.add(path)
                for item in h["new"]:
                    if item["text"].strip() == "":
                        continue
                    oid = _blob_oid(repo_root, new_tree, path) if new_tree and source == "oid" else None
                    if source == "oid" and oid is not None:
                        ev = _evidence(path, oid=oid, source="oid")
                    else:
                        ev = _evidence(path, oid=None, source="worktree")
                    obligations.append(_obligation(
                        side="new", path=path, lineno=item["line"], text=item["text"],
                        change="added", evidence_ref=ev, pair_id=pair_id,
                    ))
                    level0.add(path)
            continue

        path = row["path"]
        if is_test_excluded(path, test_exclude):
            handled.add(path)
            continue
        if is_skipped(path, skip):
            path_notes.append({"kind": "skip", "path": path})
            handled.add(path)
            continue

        ns = numstat.get(path, {})
        fd = file_diffs.get(path) or {"hunks": [], "is_binary": False, "is_submodule": False}
        tree_probe = new_tree or "HEAD"
        mode_r = _run_git(repo_root, ["ls-tree", tree_probe, path])
        is_gitlink = mode_r.returncode == 0 and mode_r.stdout.startswith("160000")
        if not is_gitlink and old_tree:
            old_mode = _run_git(repo_root, ["ls-tree", old_tree, path])
            is_gitlink = old_mode.returncode == 0 and old_mode.stdout.startswith("160000")
        if is_gitlink or fd.get("is_submodule"):
            path_notes.append({"kind": "submodule", "path": path})
            handled.add(path)
            continue
        if ns.get("binary") or fd.get("is_binary"):
            path_notes.append({"kind": "binary", "path": path})
            handled.add(path)
            continue

        if path in mode_paths and not (fd.get("hunks")):
            path_notes.append({"kind": "mode", "path": path})
            handled.add(path)
            continue
        if path in mode_paths and not any(
            (h.get("old") or h.get("new")) for h in (fd.get("hunks") or [])
        ):
            path_notes.append({"kind": "mode", "path": path})
            handled.add(path)
            continue

        hunks = fd.get("hunks") or []
        if code in ("A", "M", "D") and not hunks:
            path_notes.append({"kind": "empty-hunk", "path": path})
            handled.add(path)
            continue

        if path in mode_paths:
            path_notes.append({"kind": "mode", "path": path})

        for h in hunks:
            pair_id = None
            if h["old"] and h["new"]:
                pair_id = f"pair:{path}:{h['old_start']}:{h['new_start']}"
            for item in h["old"]:
                if item["text"].strip() == "":
                    continue
                oid = _blob_oid(repo_root, old_tree, path) if old_tree and source == "oid" else None
                if source == "oid" and oid is not None:
                    ev = _evidence(path, oid=oid, source="oid")
                else:
                    ev = _evidence(path, oid=None, source="worktree")
                obligations.append(_obligation(
                    side="old", path=path, lineno=item["line"], text=item["text"],
                    change="deleted", evidence_ref=ev, pair_id=pair_id,
                ))
                level0.add(path)
            for item in h["new"]:
                if item["text"].strip() == "":
                    continue
                oid = _blob_oid(repo_root, new_tree, path) if new_tree and source == "oid" else None
                if source == "oid" and oid is not None:
                    ev = _evidence(path, oid=oid, source="oid")
                else:
                    ev = _evidence(path, oid=None, source="worktree")
                obligations.append(_obligation(
                    side="new", path=path, lineno=item["line"], text=item["text"],
                    change="added", evidence_ref=ev, pair_id=pair_id,
                ))
                level0.add(path)
        handled.add(path)

    for path, fd in file_diffs.items():
        if path in handled:
            continue
        if is_test_excluded(path, test_exclude):
            continue
        if is_skipped(path, skip):
            path_notes.append({"kind": "skip", "path": path})
            continue
        if fd.get("is_submodule"):
            path_notes.append({"kind": "submodule", "path": path})
        elif fd.get("is_binary"):
            path_notes.append({"kind": "binary", "path": path})

    return obligations, path_notes, level0

def _untracked_adds(repo_root: Path, test_exclude, skip) -> tuple:
    obligations = []
    path_notes = []
    level0 = set()
    text = _git_out(repo_root, ["ls-files", "--others", "--exclude-standard"])
    for path in text.splitlines():
        path = path.strip()
        if not path:
            continue
        if is_test_excluded(path, test_exclude):
            continue
        if is_skipped(path, skip):
            path_notes.append({"kind": "skip", "path": path})
            continue
        raw = (repo_root / path).read_bytes()
        if b"\x00" in raw:
            path_notes.append({"kind": "binary", "path": path})
            continue
        body = raw.decode("utf-8", errors="replace")
        lines = body.splitlines()
        if not lines and raw == b"":
            path_notes.append({"kind": "empty-hunk", "path": path})
            continue
        for i, line in enumerate(lines, 1):
            if line.strip() == "":
                continue
            obligations.append(_obligation(
                side="new", path=path, lineno=i, text=line, change="added",
                evidence_ref=_evidence(path, oid=None, source="worktree"),
            ))
            level0.add(path)
    return obligations, path_notes, level0

def _merge_oid_prefer(primary: list, secondary: list) -> list:
    by_id = {}
    for o in secondary:
        by_id[o["obligationId"]] = o
    for o in primary:
        existing = by_id.get(o["obligationId"])
        if existing is None:
            by_id[o["obligationId"]] = o
            continue
        if existing["evidenceRef"].get("source") == "oid":
            continue
        if o["evidenceRef"].get("source") == "oid":
            by_id[o["obligationId"]] = o
    return list(by_id.values())

def inventory_git_diff(
    repo_root: Path,
    *,
    base: str,
    head: str,
    dirty: bool = False,
    test_exclude=None,
    skip=None,
    find_copies: bool = False,
) -> dict:
    test_exclude = list(test_exclude if test_exclude is not None else DEFAULT_TEST_EXCLUDE)
    skip = list(skip if skip is not None else DEFAULT_SKIP)
    base_oid = _rev_parse(repo_root, base)
    head_oid = _rev_parse(repo_root, head)
    range_args = [f"{base_oid}...{head_oid}"]
    obligations, path_notes, level0 = _collect_from_range(
        repo_root,
        range_args=range_args,
        old_tree=base_oid,
        new_tree=head_oid,
        source="oid",
        test_exclude=test_exclude,
        skip=skip,
        find_copies=find_copies,
    )
    if dirty:
        dirty_obs, dirty_notes, dirty_l0 = _collect_from_range(
            repo_root,
            range_args=["HEAD"],
            old_tree=head_oid,
            new_tree=None,
            source="worktree",
            test_exclude=test_exclude,
            skip=skip,
            find_copies=False,
        )
        u_obs, u_notes, u_l0 = _untracked_adds(repo_root, test_exclude, skip)
        obligations = _merge_oid_prefer(obligations, dirty_obs + u_obs)
        path_notes = path_notes + dirty_notes + u_notes
        level0 = set(level0) | set(dirty_l0) | set(u_l0)
    seen_notes = []
    note_keys = set()
    for n in path_notes:
        key = (n.get("kind"), n.get("path"), n.get("from"), n.get("to"))
        if key in note_keys:
            continue
        note_keys.add(key)
        seen_notes.append(n)
    return {
        "obligations": obligations,
        "pathNotes": seen_notes,
        "level0": sorted(level0),
        "baseOid": base_oid,
        "headOid": head_oid,
    }
