import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HELPER = Path(__file__).resolve().parent / "grill-flow.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("grill_flow_cli_integration", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_cli(mod, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(argv)
    out = buf.getvalue().strip()
    return rc, json.loads(out) if out else None


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")


class TestCliIntegration(unittest.TestCase):
    def test_empty_run_kind_complete(self):
        mod = _load_cli()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "docs" / "grill-flow" / "empty-run"
            run_dir.mkdir(parents=True)
            rc, out = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-surface", "--mode", "file-set",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(out["mode"], "file-set")
            rc, out = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-run",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(out["runKind"], "empty")
            self.assertEqual(out["runStatus"], "complete")
            rc, st = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "status",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(st["runKind"], "empty")
            self.assertEqual(st["runStatus"], "complete")
            self.assertIsNone(st["gate"])
            self.assertEqual(st["chrome"], "empty-run")

    def test_empty_ledger_run_kind_complete(self):
        mod = _load_cli()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "blank.py").write_text("")
            run_dir = root / "docs" / "grill-flow" / "empty-ledger"
            run_dir.mkdir(parents=True)
            rc, out = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-surface", "--mode", "file-set", "--target", "blank.py",
            ])
            self.assertEqual(rc, 0)
            rc, out = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-run",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(out["runKind"], "emptyLedger")
            self.assertEqual(out["runStatus"], "complete")
            rc, st = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "status",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(st["runKind"], "emptyLedger")
            self.assertEqual(st["runStatus"], "complete")
            self.assertEqual(st["gate"]["N"], 0)
            self.assertEqual(st["gate"]["validatorSlots"], 1)
            self.assertEqual(st["chrome"], "empty-ledger")
            self.assertEqual(st["graph"]["phase"], "clean")
            self.assertEqual(st["flows"]["phase"], "clean")
            graph = json.loads((run_dir / "graph.json").read_text())
            node = graph["nodes"]["file:blank.py"]
            self.assertEqual(node["hop"], 0)
            self.assertTrue(node["expanded"])

    def test_path_notes_only_run_kind_complete(self):
        mod = _load_cli()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _init_repo(root)
            (root / "a.py").write_text("a\n")
            _git(root, "add", "a.py")
            _git(root, "commit", "-m", "c1")
            base = _git(root, "rev-parse", "HEAD")
            (root / "dist").mkdir()
            (root / "dist" / "app.js").write_text("console.log(1)\n")
            _git(root, "add", "dist/app.js")
            _git(root, "commit", "-m", "c2")
            head = _git(root, "rev-parse", "HEAD")
            run_dir = root / "docs" / "grill-flow" / "path-notes-only"
            run_dir.mkdir(parents=True)
            rc, out = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-surface", "--mode", "git-diff",
                "--base", base, "--head", head,
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(out["mode"], "git-diff")
            rc, out = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-run",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(out["runKind"], "pathNotesOnly")
            self.assertEqual(out["runStatus"], "complete")
            rc, st = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "status",
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(st["runKind"], "pathNotesOnly")
            self.assertEqual(st["runStatus"], "complete")
            self.assertEqual(st["gate"]["N"], 0)
            self.assertEqual(st["gate"]["validatorSlots"], 1)
            self.assertEqual(st["chrome"], "pathNotes-only")
            self.assertGreaterEqual(st["pathNotesCount"], 1)
            self.assertEqual(st["graph"]["phase"], "clean")
            self.assertEqual(st["flows"]["phase"], "clean")

    def test_status_ok_while_exclusive_lock_held_by_other_pid(self):
        mod = _load_cli()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "docs" / "grill-flow" / "lock-run"
            run_dir.mkdir(parents=True)
            rc, _ = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-surface", "--mode", "file-set",
            ])
            self.assertEqual(rc, 0)
            rc, _ = _run_cli(mod, [
                "--repo-root", str(root), "--run-dir", str(run_dir),
                "init-run",
            ])
            self.assertEqual(rc, 0)
            scripts = Path(__file__).resolve().parent
            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys, time; "
                        f"sys.path.insert(0, {str(scripts)!r}); "
                        "from pathlib import Path; "
                        "from grill_flow_lock import acquire_exclusive; "
                        f"acquire_exclusive(Path({str(run_dir)!r}), "
                        "force_token=None, helper_basename='grill-flow.py', "
                        "is_live=lambda p, b: True); "
                        "print('LOCKED', flush=True); "
                        "time.sleep(30)"
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                line = holder.stdout.readline().strip()
                self.assertEqual(line, "LOCKED")
                lock_path = run_dir / ".lock"
                self.assertTrue(lock_path.is_file())
                lock_doc = json.loads(lock_path.read_text())
                self.assertNotEqual(lock_doc["pid"], os.getpid())
                self.assertEqual(lock_doc["pid"], holder.pid)
                rc, st = _run_cli(mod, [
                    "--repo-root", str(root), "--run-dir", str(run_dir),
                    "status",
                ])
                self.assertEqual(rc, 0)
                self.assertEqual(st["runStatus"], "complete")
                self.assertIsNotNone(st["lock"])
                self.assertEqual(st["lock"]["pid"], holder.pid)
            finally:
                holder.terminate()
                holder.wait(timeout=5)
                if holder.stdout is not None:
                    holder.stdout.close()


if __name__ == "__main__":
    unittest.main()
