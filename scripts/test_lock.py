import json, subprocess, sys, tempfile, unittest
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
    def test_darwin_posix_fallback_live_and_stale(self):
        import os, grill_flow_lock as lock
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / ".lock").write_text(json.dumps({"pid": 99999999, "startedAt": "t", "token": "stale"}))
            with patch("sys.platform", "darwin"):
                rec = lock.acquire_exclusive(rd, force_token=None, helper_basename="grill-flow.py")
                self.assertNotEqual(rec["token"], "stale")
            fake_ps = subprocess.CompletedProcess(
                args=["ps"], returncode=0, stdout="S+ /usr/bin/python3 /tmp/grill-flow.py status\n", stderr=""
            )
            (rd / ".lock").write_text(json.dumps({"pid": os.getpid(), "startedAt": "t", "token": "live-tok"}))
            with patch("sys.platform", "darwin"), patch("subprocess.run", return_value=fake_ps):
                with self.assertRaises(SystemExit):
                    lock.acquire_exclusive(rd, force_token=None, helper_basename="grill-flow.py")
                rec2 = lock.acquire_exclusive(rd, force_token="live-tok", helper_basename="grill-flow.py")
                self.assertNotEqual(rec2["token"], "live-tok")
    def test_non_posix_unsupported(self):
        import grill_flow_lock as lock
        from io import StringIO
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            with patch("sys.platform", "win32"):
                with patch("sys.stderr", new_callable=StringIO) as se:
                    with self.assertRaises(SystemExit):
                        lock.acquire_exclusive(Path(td), force_token=None, helper_basename="grill-flow.py")
                self.assertEqual(json.loads(se.getvalue())["error"], "unsupported_platform")

    def test_concurrent_acquire_only_one_winner(self):
        import threading
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            barrier = threading.Barrier(4)
            winners = []
            failures = []
            mu = threading.Lock()

            def worker():
                barrier.wait()
                try:
                    rec = lock.acquire_exclusive(
                        rd, force_token=None, helper_basename="grill-flow.py", is_live=lambda p, b: True
                    )
                    with mu:
                        winners.append(rec)
                except SystemExit:
                    with mu:
                        failures.append(1)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(len(winners), 1)
            self.assertEqual(len(failures), 3)
            self.assertEqual(lock.read_lock(rd)["token"], winners[0]["token"])

    def test_concurrent_stale_lock_takeover_preserves_winner(self):
        import threading
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / ".lock").write_text(json.dumps({"pid": 999999, "startedAt": "t", "token": "stale"}))
            barrier = threading.Barrier(4)
            winners = []
            failures = []
            mu = threading.Lock()

            def is_live(pid, _base):
                return pid != 999999

            def worker():
                barrier.wait()
                try:
                    rec = lock.acquire_exclusive(
                        rd, force_token=None, helper_basename="grill-flow.py", is_live=is_live
                    )
                    with mu:
                        winners.append(rec)
                except SystemExit:
                    with mu:
                        failures.append(1)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(len(winners), 1)
            self.assertEqual(len(failures), 3)
            on_disk = lock.read_lock(rd)
            self.assertIsNotNone(on_disk)
            self.assertEqual(on_disk["token"], winners[0]["token"])

    def test_corrupt_non_dict_and_empty_force_token_edge_cases(self):
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            # Non-dict JSON and invalid JSON must not crash and should be reclaimed
            for raw in ("[]", '"hello"', "{bad json", ""):
                (rd / ".lock").write_text(raw)
                self.assertIsNone(lock.read_lock(rd))
                rec = lock.acquire_exclusive(
                    rd, force_token=None, helper_basename="grill-flow.py", is_live=lambda p, b: True
                )
                self.assertIn("token", rec)
                lock.release_exclusive(rd)

            # Empty force_token must never match a missing/empty token on a live lock
            (rd / ".lock").write_text(json.dumps({"pid": 1, "startedAt": "t"}))
            with self.assertRaises(SystemExit):
                lock.acquire_exclusive(
                    rd, force_token="", helper_basename="grill-flow.py", is_live=lambda p, b: True
                )

    def test_release_exclusive_respects_expected_token(self):
        import grill_flow_lock as lock
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            rec_a = lock.acquire_exclusive(
                rd, force_token=None, helper_basename="grill-flow.py", is_live=lambda p, b: False
            )
            # Process B force-reclaims the lock
            rec_b = lock.acquire_exclusive(
                rd, force_token=rec_a["token"], helper_basename="grill-flow.py", is_live=lambda p, b: True
            )
            # Process A exiting with its stale token must NOT delete Process B's live lock
            lock.release_exclusive(rd, expected_token=rec_a["token"])
            self.assertEqual(lock.read_lock(rd)["token"], rec_b["token"])
            # Process B releasing with its own token removes the lock
            lock.release_exclusive(rd, expected_token=rec_b["token"])
            self.assertIsNone(lock.read_lock(rd))

if __name__ == "__main__":
    unittest.main()
