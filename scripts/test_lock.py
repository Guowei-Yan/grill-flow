import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestLock(unittest.TestCase):
    def test_stale_reclaim(self):
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / ".lock").write_text(json.dumps({"pid": 999999, "startedAt": "t", "token": "abc"}))
            rec = lock.acquire_exclusive(rd, force_token=None, helper_basename="grill-flow.py", is_live=lambda p, b: False)
            self.assertIn("token", rec)
    def test_live_without_force(self):
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / ".lock").write_text(json.dumps({"pid": 1, "startedAt": "t", "token": "tok"}))
            with self.assertRaises(SystemExit):
                lock.acquire_exclusive(rd, force_token=None, helper_basename="grill-flow.py", is_live=lambda p, b: True)
    def test_force_ok(self):
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / ".lock").write_text(json.dumps({"pid": 1, "startedAt": "t", "token": "tok"}))
            rec = lock.acquire_exclusive(rd, force_token="tok", helper_basename="grill-flow.py", is_live=lambda p, b: True)
            self.assertNotEqual(rec["token"], "tok")
    def test_force_mismatch(self):
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / ".lock").write_text(json.dumps({"pid": 1, "startedAt": "t", "token": "tok"}))
            with self.assertRaises(SystemExit):
                lock.acquire_exclusive(rd, force_token="wrong", helper_basename="grill-flow.py", is_live=lambda p, b: True)
            with self.assertRaises(SystemExit):
                lock.acquire_exclusive(rd, force_token=None, helper_basename="grill-flow.py", is_live=lambda p, b: True)
    def test_non_linux_unsupported(self):
        import json, grill_flow_lock as lock
        from io import StringIO
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            with patch("sys.platform", "darwin"):
                with patch("sys.stderr", new_callable=StringIO) as se:
                    with self.assertRaises(SystemExit):
                        lock.acquire_exclusive(Path(td), force_token=None, helper_basename="grill-flow.py")
                self.assertEqual(json.loads(se.getvalue())["error"], "unsupported_platform")

if __name__ == "__main__":
    unittest.main()
