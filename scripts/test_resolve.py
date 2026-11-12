import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestResolve(unittest.TestCase):
    def _exec(self, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/usr/bin/env python3\n")
        p.chmod(0o755)
    def _nonexec(self, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/usr/bin/env python3\n")
        p.chmod(0o644)
    def test_empty_env(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                r.resolve_helper({"GRILL_FLOW_HELPER": ""}, Path(td), Path(td)/"share")
    def test_env_missing(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                r.resolve_helper({"GRILL_FLOW_HELPER": str(Path(td)/"missing.py")}, Path(td), Path(td)/"share")
    def test_env_not_exec(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"h.py"
            self._nonexec(p)
            with self.assertRaises(SystemExit):
                r.resolve_helper({"GRILL_FLOW_HELPER": str(p)}, Path(td), Path(td)/"share")
    def test_skill_hit(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            scripts = Path(td)/"scripts"
            self._exec(scripts/"grill-flow.py")
            self.assertEqual(r.resolve_helper({}, scripts, Path(td)/"share"), scripts/"grill-flow.py")
    def test_skill_not_exec_no_fallthrough(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            scripts = Path(td)/"scripts"
            self._nonexec(scripts/"grill-flow.py")
            self._exec(Path(td)/"share"/"grill-flow.py")
            with self.assertRaises(SystemExit):
                r.resolve_helper({}, scripts, Path(td)/"share")
    def test_share_fallback(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            self._exec(Path(td)/"share"/"grill-flow.py")
            self.assertEqual(r.resolve_helper({}, Path(td)/"scripts", Path(td)/"share"), Path(td)/"share"/"grill-flow.py")
    def test_share_not_exec(self):
        import json, grill_flow_resolve as r
        from io import StringIO
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            self._nonexec(Path(td)/"share"/"grill-flow.py")
            with patch("sys.stderr", new_callable=StringIO) as se:
                with self.assertRaises(SystemExit):
                    r.resolve_helper({}, Path(td)/"scripts", Path(td)/"share")
            self.assertEqual(json.loads(se.getvalue())["error"], "helper_not_executable")
    def test_both_missing(self):
        import json, grill_flow_resolve as r
        from io import StringIO
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            with patch("sys.stderr", new_callable=StringIO) as se:
                with self.assertRaises(SystemExit):
                    r.resolve_helper({}, Path(td)/"scripts", Path(td)/"share")
            self.assertEqual(json.loads(se.getvalue())["error"], "helper_not_found")
    def test_empty_env_code(self):
        import json, grill_flow_resolve as r
        from io import StringIO
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            with patch("sys.stderr", new_callable=StringIO) as se:
                with self.assertRaises(SystemExit):
                    r.resolve_helper({"GRILL_FLOW_HELPER": ""}, Path(td), Path(td)/"share")
            self.assertEqual(json.loads(se.getvalue())["error"], "invalid_args")
    def test_basename(self):
        import grill_flow_resolve as r
        self.assertEqual(r.helper_basename(Path("/x/custom-helper.py")), "custom-helper.py")

    def test_resolve_matrix(self):
        import grill_flow_resolve as r
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = root / "scripts"
            share = root / "share"
            env_ok = skill / "grill-flow.py"
            self._exec(env_ok)
            self.assertEqual(
                r.resolve_helper({"GRILL_FLOW_HELPER": str(env_ok)}, skill, share),
                env_ok,
            )
            self.assertEqual(r.resolve_helper({}, skill, share), env_ok)
            env_ok.unlink()
            share_h = share / "grill-flow.py"
            self._exec(share_h)
            self.assertEqual(r.resolve_helper({}, skill, share), share_h)
            with self.assertRaises(SystemExit):
                r.resolve_helper({"GRILL_FLOW_HELPER": ""}, skill, share)
            with self.assertRaises(SystemExit):
                r.resolve_helper({"GRILL_FLOW_HELPER": str(root / "missing.py")}, skill, share)
            bad = root / "bad.py"
            self._nonexec(bad)
            with self.assertRaises(SystemExit):
                r.resolve_helper({"GRILL_FLOW_HELPER": str(bad)}, skill, share)

if __name__ == "__main__":
    unittest.main()
