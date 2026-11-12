import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _write_run(run_dir: Path, doc: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def _normal_run(**overrides) -> dict:
    doc = {
        "runId": "rid",
        "runKind": "normal",
        "runStatus": "in_progress",
        "graphPartial": False,
        "gate": {
            "N": 2,
            "graphBudget": 6,
            "lineBudget": 8,
            "packetSizeObligations": 40,
            "packetSizeFiles": 8,
            "validatorSlots": 8,
            "models": "n/a",
        },
        "graph": {"phase": "active"},
        "flows": {"phase": "not_started"},
        "hardRejects": [],
    }
    doc.update(overrides)
    return doc


def _seed_run(
    run_dir: Path,
    *,
    run_kind: str = "normal",
    obligations: list | None = None,
    path_notes: list | None = None,
    ledger: dict | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    obligations = obligations if obligations is not None else []
    path_notes = path_notes if path_notes is not None else []
    ledger = ledger if ledger is not None else {}
    _write_run(run_dir, _normal_run(runKind=run_kind, runStatus="complete",
                                    graph={"phase": "clean"}, flows={"phase": "clean"}))
    (run_dir / "obligations.json").write_text(json.dumps(obligations) + "\n")
    (run_dir / "pathNotes.json").write_text(json.dumps(path_notes) + "\n")
    (run_dir / "ledger.json").write_text(json.dumps(ledger) + "\n")
    (run_dir / "graph.json").write_text(json.dumps({"nodes": {}, "edges": []}) + "\n")
    (run_dir / "surface.json").write_text(json.dumps({
        "mode": "file-set", "targets": [], "baseOid": None, "headOid": None, "dirty": False,
    }) + "\n")
    (run_dir / "surface-hash.txt").write_text("a" * 64 + "\n")


def _install_viewer(root: Path) -> Path:
    viewer = root / "viewer"
    viewer.mkdir(parents=True, exist_ok=True)
    (viewer / "app.js").write_text("window.GRILL_FLOW_VIEWER = true;\n")
    (viewer / "style.css").write_text("body { margin: 0; }\n")
    (viewer / "model.js").write_text("globalThis.GrillFlowModel = {};\n")
    return viewer


class TestRender(unittest.TestCase):
    def test_exclusive_lock_flag(self):
        from grill_flow_render import RENDER_REQUIRES_EXCLUSIVE_LOCK
        self.assertTrue(RENDER_REQUIRES_EXCLUSIVE_LOCK)

    def test_viewer_dir_both_layouts(self):
        from grill_flow_render import viewer_dir_for_helper
        skill_helper = Path("/tmp/skill/grill-flow/scripts/grill-flow.py")
        self.assertEqual(
            viewer_dir_for_helper(skill_helper),
            Path("/tmp/skill/grill-flow/viewer"),
        )
        share_helper = Path("/home/u/.local/share/grill-flow/grill-flow.py")
        self.assertEqual(
            viewer_dir_for_helper(share_helper),
            Path("/home/u/.local/share/grill-flow/viewer"),
        )

    def test_asset_copy_and_chrome_in_html(self):
        from grill_flow_render import render_run
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "scripts" / "grill-flow.py"
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/usr/bin/env python3\n")
            _install_viewer(root)
            run_dir = root / "run"
            _seed_run(run_dir, run_kind="empty")
            out = render_run(run_dir, helper, repo_root=root.resolve())
            self.assertTrue((run_dir / "app.js").is_file())
            self.assertTrue((run_dir / "style.css").is_file())
            self.assertTrue((run_dir / "model.js").is_file())
            self.assertTrue((run_dir / "index.html").is_file())
            html = (run_dir / "index.html").read_text()
            self.assertIn("empty-run", html)
            self.assertIn(out["chrome"], html)
            self.assertIn('id="graph-canvas"', html)
            self.assertIn('id="inspector-panel"', html)
            self.assertIn('id="flow-fragmentation-banner"', html)
            self.assertIn('src="model.js"', html)
            payload = json.loads(
                html.split('id="run-payload">', 1)[1].split("</script>", 1)[0]
            )
            self.assertEqual(payload.get("repoRoot"), str(root.resolve()))

    def test_path_notes_panel_when_present(self):
        from grill_flow_render import render_run
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "scripts" / "grill-flow.py"
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/usr/bin/env python3\n")
            _install_viewer(root)
            run_dir = root / "run"
            _seed_run(
                run_dir,
                run_kind="pathNotesOnly",
                path_notes=[{"kind": "binary", "path": "blob.bin"}],
            )
            render_run(run_dir, helper)
            html = (run_dir / "index.html").read_text()
            self.assertIn('id="path-notes-panel"', html)
            empty_dir = root / "run-empty"
            _seed_run(empty_dir, run_kind="empty", path_notes=[])
            render_run(empty_dir, helper)
            html2 = (empty_dir / "index.html").read_text()
            self.assertNotIn('id="path-notes-panel"', html2)

    def test_delete_drill_in_kind_gated(self):
        from grill_flow_render import render_run
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "scripts" / "grill-flow.py"
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/usr/bin/env python3\n")
            _install_viewer(root)
            run_dir = root / "run-del"
            oid = "diff:old:a.py:1:deadbeef"
            _seed_run(
                run_dir,
                run_kind="normal",
                obligations=[{
                    "obligationId": oid,
                    "kind": "semantic",
                    "path": "a.py",
                    "change": "deleted",
                }],
                ledger={oid: {"state": "covered", "kind": "semantic"}},
            )
            render_run(run_dir, helper)
            html = (run_dir / "index.html").read_text()
            self.assertIn("only-delete", html)
            self.assertIn('id="delete-drill-in"', html)
            run_normal = root / "run-normal"
            oid2 = "file:a.py:1:cafe"
            _seed_run(
                run_normal,
                run_kind="normal",
                obligations=[{
                    "obligationId": oid2,
                    "kind": "semantic",
                    "path": "a.py",
                    "change": "present",
                }],
                ledger={oid2: {"state": "uncovered"}},
            )
            render_run(run_normal, helper)
            html2 = (run_normal / "index.html").read_text()
            self.assertNotIn('id="delete-drill-in"', html2)

    def test_render_cli_exclusive_lock(self):
        import importlib.util
        path = Path(__file__).resolve().parent / "grill-flow.py"
        spec = importlib.util.spec_from_file_location("grill_flow_cli_render", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        acq = []
        rel = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper_scripts = Path(__file__).resolve().parent
            viewer_src = helper_scripts.parent / "viewer"
            viewer_src.mkdir(parents=True, exist_ok=True)
            if not (viewer_src / "app.js").is_file():
                (viewer_src / "app.js").write_text("window.GRILL_FLOW_VIEWER = true;\n")
            if not (viewer_src / "style.css").is_file():
                (viewer_src / "style.css").write_text("body { margin: 0; }\n")
            run_dir = root / "run"
            _seed_run(run_dir, run_kind="empty")
            real_acq = mod.acquire_exclusive
            real_rel = mod.release_exclusive
            def fake_acq(rd, force_token=None):
                acq.append(rd)
                return real_acq(rd, force_token=force_token)
            def fake_rel(rd):
                rel.append(rd)
                return real_rel(rd)
            with mock.patch.object(mod, "acquire_exclusive", side_effect=fake_acq):
                with mock.patch.object(mod, "release_exclusive", side_effect=fake_rel):
                    with mock.patch.object(mod, "apply_surface_drift", return_value={"changed": False}):
                        rc = mod.main([
                            "--repo-root", str(root),
                            "--run-dir", str(run_dir),
                            "render",
                        ])
            self.assertEqual(rc, 0)
            self.assertEqual(len(acq), 1)
            self.assertEqual(len(rel), 1)
            self.assertTrue((run_dir / "index.html").is_file())


def _load_cli(name: str):
    import importlib.util
    path = Path(__file__).resolve().parent / "grill-flow.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestServe(unittest.TestCase):
    def test_exclusive_lock_flags(self):
        from grill_flow_serve import (
            SERVE_CHILD_READ_ONLY,
            SERVE_START_REQUIRES_EXCLUSIVE_LOCK,
            SERVE_STOP_REQUIRES_EXCLUSIVE_LOCK,
        )
        self.assertTrue(SERVE_START_REQUIRES_EXCLUSIVE_LOCK)
        self.assertFalse(SERVE_STOP_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(SERVE_CHILD_READ_ONLY)

    def test_serve_start_info_argv_and_lock_release(self):
        import time
        from grill_flow_lock import read_lock
        from grill_flow_serve import _pid_alive, serve_start, serve_stop
        helper = Path(__file__).resolve().parent / "grill-flow.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            _seed_run(run_dir, run_kind="empty")
            (run_dir / "index.html").write_text("<html></html>\n")
            info = serve_start(run_dir, helper, repo_root=root)
            try:
                self.assertIn("pid", info)
                self.assertIn("instanceId", info)
                stored = json.loads((run_dir / "server-info.json").read_text())
                self.assertEqual(stored["pid"], info["pid"])
                self.assertEqual(stored["instanceId"], info["instanceId"])
                self.assertIsNone(read_lock(run_dir))
                deadline = time.time() + 2.0
                cmdline = []
                while time.time() < deadline:
                    try:
                        raw = Path(f"/proc/{info['pid']}/cmdline").read_bytes().split(b"\0")
                        cmdline = [x.decode(errors="ignore") for x in raw if x]
                        if cmdline:
                            break
                    except OSError:
                        time.sleep(0.05)
                self.assertTrue(cmdline)
                self.assertEqual(cmdline[0], str(helper))
                self.assertIn(f"--grill-flow-instance={info['instanceId']}", cmdline)
                self.assertIn("--read-only", cmdline)
            finally:
                serve_stop(run_dir)
                self.assertFalse(_pid_alive(info["pid"]))

    def test_serve_stop_missing(self):
        from grill_flow_serve import serve_stop
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            with mock.patch("sys.stderr", new_callable=StringIO) as se:
                with self.assertRaises(SystemExit):
                    serve_stop(run_dir)
            self.assertEqual(json.loads(se.getvalue())["error"], "serve_info_missing")

    def test_serve_stop_dead_pid_clears(self):
        from grill_flow_serve import serve_stop, write_server_info
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            write_server_info(run_dir, {"pid": 99999999, "instanceId": "deadbeef"})
            self.assertEqual(serve_stop(run_dir), {})
            self.assertFalse((run_dir / "server-info.json").exists())

    def test_serve_stop_live_match_and_mismatch(self):
        import time
        from grill_flow_serve import _pid_alive, serve_start, serve_stop, write_server_info
        helper = Path(__file__).resolve().parent / "grill-flow.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            _seed_run(run_dir, run_kind="empty")
            (run_dir / "index.html").write_text("<html></html>\n")
            info = serve_start(run_dir, helper, repo_root=root)
            pid = info["pid"]
            try:
                deadline = time.time() + 2.0
                while time.time() < deadline and not _pid_alive(pid):
                    time.sleep(0.05)
                self.assertTrue(_pid_alive(pid))
                write_server_info(run_dir, {"pid": pid, "instanceId": "wrong-instance-id"})
                with mock.patch("sys.stderr", new_callable=StringIO) as se:
                    with self.assertRaises(SystemExit):
                        serve_stop(run_dir)
                self.assertEqual(json.loads(se.getvalue())["error"], "serve_stop_mismatch")
                self.assertTrue(_pid_alive(pid))
                write_server_info(run_dir, info)
                self.assertEqual(serve_stop(run_dir), {})
                deadline = time.time() + 3.0
                while time.time() < deadline and _pid_alive(pid):
                    time.sleep(0.05)
                self.assertFalse(_pid_alive(pid))
                self.assertFalse((run_dir / "server-info.json").exists())
            finally:
                if _pid_alive(pid):
                    write_server_info(run_dir, info)
                    try:
                        serve_stop(run_dir)
                    except SystemExit:
                        pass

    def test_serve_cli_lock_matrix(self):
        from grill_flow_lock import read_lock
        mod = _load_cli("grill_flow_cli_serve")
        acq = []
        rel = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            _seed_run(run_dir, run_kind="empty")
            (run_dir / "index.html").write_text("<html></html>\n")
            real_acq = mod.acquire_exclusive
            real_rel = mod.release_exclusive
            def fake_acq(rd, force_token=None):
                acq.append(("start", rd))
                return real_acq(rd, force_token=force_token)
            def fake_rel(rd):
                rel.append(("start", rd))
                return real_rel(rd)
            with mock.patch.object(mod, "acquire_exclusive", side_effect=fake_acq):
                with mock.patch.object(mod, "release_exclusive", side_effect=fake_rel):
                    out_buf = StringIO()
                    old = sys.stdout
                    sys.stdout = out_buf
                    try:
                        rc = mod.main([
                            "--repo-root", str(root),
                            "--run-dir", str(run_dir),
                            "serve-start",
                        ])
                    finally:
                        sys.stdout = old
            self.assertEqual(rc, 0)
            self.assertEqual(len(acq), 1)
            self.assertEqual(len(rel), 1)
            self.assertIsNone(read_lock(run_dir))
            info = json.loads(out_buf.getvalue())
            self.assertIn("pid", info)
            self.assertIn("instanceId", info)
            stop_acq = []
            def stop_fake_acq(rd, force_token=None):
                stop_acq.append(rd)
                return real_acq(rd, force_token=force_token)
            with mock.patch.object(mod, "acquire_exclusive", side_effect=stop_fake_acq):
                rc2 = mod.main([
                    "--repo-root", str(root),
                    "--run-dir", str(run_dir),
                    "serve-stop",
                ])
            self.assertEqual(rc2, 0)
            self.assertEqual(stop_acq, [])


if __name__ == "__main__":
    unittest.main()
