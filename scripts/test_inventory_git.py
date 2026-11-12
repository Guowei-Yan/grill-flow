import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _init_repo() -> Path:
    td = Path(tempfile.mkdtemp())
    _git(td, "init")
    _git(td, "config", "user.email", "t@example.com")
    _git(td, "config", "user.name", "t")
    return td


class TestGitDiffInventory(unittest.TestCase):
    def test_dirty_false_committed_only(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("one\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "a.py").write_text("one\ntwo\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        (root / "a.py").write_text("one\ntwo\nDIRTY\n")
        (root / "untracked.py").write_text("u\n")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        texts = [o.get("lineText") or o.get("text") for o in inv["obligations"]]
        ids = [o["obligationId"] for o in inv["obligations"]]
        self.assertTrue(any("diff:new:" in i for i in ids))
        self.assertFalse(any("DIRTY" in (t or "") for t in texts))
        self.assertFalse(any(o.get("path") == "untracked.py" for o in inv["obligations"]))
        self.assertFalse(any(n.get("path") == "untracked.py" for n in inv["pathNotes"]))

    def test_dirty_union_oid_prefer(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("base\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "a.py").write_text("base\ncommitted\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv_clean = inventory_git_diff(root, base=base, head=head, dirty=False)
        oid_row = next(o for o in inv_clean["obligations"] if "committed" in o["obligationId"] or o.get("change") == "added")
        self.assertEqual(oid_row["evidenceRef"]["source"], "oid")
        self.assertIsNotNone(oid_row["evidenceRef"]["oid"])
        (root / "a.py").write_text("base\ncommitted\nextra\n")
        inv = inventory_git_diff(root, base=base, head=head, dirty=True)
        by_id = {}
        for o in inv["obligations"]:
            by_id[o["obligationId"]] = o
        self.assertEqual(by_id[oid_row["obligationId"]]["evidenceRef"]["source"], "oid")
        extra = [o for o in inv["obligations"] if o["evidenceRef"]["source"] == "worktree"]
        self.assertTrue(len(extra) >= 1)
        self.assertTrue(all(e["evidenceRef"]["oid"] is None for e in extra))

    def test_modify_pair_id_diff_old_new(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "m.py").write_text("alpha\n")
        _git(root, "add", "m.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "m.py").write_text("beta\n")
        _git(root, "add", "m.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        olds = [o for o in inv["obligations"] if o["obligationId"].startswith("diff:old:")]
        news = [o for o in inv["obligations"] if o["obligationId"].startswith("diff:new:")]
        self.assertEqual(len(olds), 1)
        self.assertEqual(len(news), 1)
        self.assertIn("pairId", olds[0])
        self.assertEqual(olds[0]["pairId"], news[0]["pairId"])
        self.assertTrue(olds[0]["obligationId"].startswith("diff:old:m.py:"))
        self.assertTrue(news[0]["obligationId"].startswith("diff:new:m.py:"))

    def test_untracked_adds(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("x\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = head = _git(root, "rev-parse", "HEAD")
        (root / "new.py").write_text("hello\n")
        inv = inventory_git_diff(root, base=base, head=head, dirty=True)
        paths = {o["path"] for o in inv["obligations"]}
        self.assertIn("new.py", paths)
        row = next(o for o in inv["obligations"] if o["path"] == "new.py")
        self.assertTrue(row["obligationId"].startswith("diff:new:new.py:"))
        self.assertEqual(row["evidenceRef"]["source"], "worktree")

    def test_worktree_evidence_when_dirty(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("x\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = head = _git(root, "rev-parse", "HEAD")
        (root / "a.py").write_text("x\ny\n")
        inv = inventory_git_diff(root, base=base, head=head, dirty=True)
        self.assertTrue(any(o["evidenceRef"]["source"] == "worktree" for o in inv["obligations"]))
        self.assertTrue(all(
            o["evidenceRef"]["oid"] is None
            for o in inv["obligations"]
            if o["evidenceRef"]["source"] == "worktree"
        ))

    def test_path_notes_binary(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "t.txt").write_text("t\n")
        _git(root, "add", "t.txt")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "blob.bin").write_bytes(b"\x00\x01\xff")
        _git(root, "add", "blob.bin")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "binary" and n.get("path") == "blob.bin" for n in inv["pathNotes"]))
        self.assertFalse(any(o.get("path") == "blob.bin" for o in inv["obligations"]))

    def test_path_notes_rename(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "old.py").write_text("same\n")
        _git(root, "add", "old.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        _git(root, "mv", "old.py", "new.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "rename" for n in inv["pathNotes"]))

    def test_path_notes_copy(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "src.py").write_text("payload_line_for_copy_detection_aaaaaaaa\n")
        _git(root, "add", "src.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "dst.py").write_text("payload_line_for_copy_detection_aaaaaaaa\n")
        _git(root, "add", "dst.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(
            root, base=base, head=head, dirty=False, find_copies=True
        )
        self.assertTrue(any(n.get("kind") == "copy" for n in inv["pathNotes"]))

    def test_path_notes_mode(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "x.sh").write_text("echo hi\n")
        _git(root, "add", "x.sh")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "x.sh").chmod(0o755)
        _git(root, "add", "x.sh")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "mode" and n.get("path") == "x.sh" for n in inv["pathNotes"]))

    def test_path_notes_submodule(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("x\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        sub = Path(tempfile.mkdtemp())
        _git(sub, "init")
        _git(sub, "config", "user.email", "t@example.com")
        _git(sub, "config", "user.name", "t")
        (sub / "s.txt").write_text("s\n")
        _git(sub, "add", "s.txt")
        _git(sub, "commit", "-m", "s1")
        sub_oid = _git(sub, "rev-parse", "HEAD")
        subprocess.run(
            ["git", "update-index", "--add", "--cacheinfo", f"160000,{sub_oid},vendor"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "submodule" for n in inv["pathNotes"]))

    def test_path_notes_empty_hunk(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("a\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "empty_new.py").write_text("")
        _git(root, "add", "empty_new.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "empty-hunk" for n in inv["pathNotes"]))

    def test_residual_hunks_after_rename(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "old.py").write_text("line1\nline2\nline3\nline4\nline5\nchange_me\n")
        _git(root, "add", "old.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        _git(root, "mv", "old.py", "new.py")
        (root / "new.py").write_text("line1\nline2\nline3\nline4\nline5\nchanged\n")
        _git(root, "add", "new.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "rename" for n in inv["pathNotes"]))
        self.assertTrue(len(inv["obligations"]) >= 1)
        self.assertTrue(any(o["obligationId"].startswith("diff:") for o in inv["obligations"]))

    def test_test_exclude_omit(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("a\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "tests").mkdir()
        (root / "tests" / "t_test.py").write_text("assert 1\n")
        _git(root, "add", "tests/t_test.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertFalse(any(o.get("path", "").startswith("tests/") for o in inv["obligations"]))
        self.assertFalse(any(n.get("path", "").startswith("tests/") for n in inv["pathNotes"]))
        self.assertNotIn("tests/t_test.py", inv["level0"])

    def test_skip_to_path_notes(self):
        from grill_flow_inventory import inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("a\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "dist").mkdir()
        (root / "dist" / "app.js").write_text("console.log(1)\n")
        _git(root, "add", "dist/app.js")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(any(n.get("kind") == "skip" and n.get("path") == "dist/app.js" for n in inv["pathNotes"]))
        self.assertFalse(any(o.get("path") == "dist/app.js" for o in inv["obligations"]))

    def test_skip_only_path_notes_only(self):
        from grill_flow_inventory import classify_run_kind, inventory_git_diff

        root = _init_repo()
        (root / "a.py").write_text("a\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "dist").mkdir()
        (root / "dist" / "app.js").write_text("console.log(1)\n")
        _git(root, "add", "dist/app.js")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        kind = classify_run_kind(inv["obligations"], inv["pathNotes"], inv["level0"])
        self.assertEqual(kind, "pathNotesOnly")
        self.assertEqual(inv["level0"], [])
        self.assertEqual(inv["obligations"], [])
        self.assertTrue(len(inv["pathNotes"]) >= 1)

    def test_find_renames_flag(self):
        from grill_flow_inventory import inventory_git_diff, GIT_DIFF_FIND_RENAMES

        self.assertTrue(GIT_DIFF_FIND_RENAMES)
        root = _init_repo()
        (root / "a.py").write_text("x\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = head = _git(root, "rev-parse", "HEAD")
        calls = []
        real_run = subprocess.run

        def spy(*a, **k):
            if a and a[0] and a[0][0] == "git":
                calls.append(list(a[0]))
            return real_run(*a, **k)

        with mock.patch("subprocess.run", side_effect=spy):
            inventory_git_diff(root, base=base, head=head, dirty=False)
        joined = [" ".join(c) for c in calls]
        self.assertTrue(any("--find-renames" in j for j in joined))

    def test_pinned_base_head_oids(self):
        from grill_flow_inventory import inventory_git_diff
        from grill_flow_surface import build_git_diff_surface

        root = _init_repo()
        (root / "a.py").write_text("x\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base_ref = _git(root, "rev-parse", "HEAD")
        (root / "a.py").write_text("x\ny\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c2")
        head_ref = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base_ref, head=head_ref, dirty=False)
        self.assertEqual(inv["baseOid"], base_ref)
        self.assertEqual(inv["headOid"], head_ref)
        surface = build_git_diff_surface(
            base_oid=inv["baseOid"], head_oid=inv["headOid"], dirty=False
        )
        self.assertEqual(surface["baseOid"], base_ref)
        self.assertEqual(surface["headOid"], head_ref)
        self.assertEqual(surface["mode"], "git-diff")

    def test_new_obligations_uncovered(self):
        from grill_flow_inventory import inventory_git_diff
        from grill_flow_state import initial_ledger_state

        root = _init_repo()
        (root / "a.py").write_text("x\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c1")
        base = _git(root, "rev-parse", "HEAD")
        (root / "a.py").write_text("x\ny\n")
        _git(root, "add", "a.py")
        _git(root, "commit", "-m", "c2")
        head = _git(root, "rev-parse", "HEAD")
        inv = inventory_git_diff(root, base=base, head=head, dirty=False)
        self.assertTrue(len(inv["obligations"]) >= 1)
        for o in inv["obligations"]:
            self.assertEqual(initial_ledger_state(o["obligationId"]), "uncovered")


if __name__ == "__main__":
    unittest.main()
