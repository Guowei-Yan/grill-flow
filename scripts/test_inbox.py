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


class TestInbox(unittest.TestCase):
    def test_exclusive_lock_flags(self):
        from grill_flow_pack import (
            INBOX_CLEAR_REQUIRES_EXCLUSIVE_LOCK,
            INBOX_PUT_REQUIRES_EXCLUSIVE_LOCK,
        )

        self.assertTrue(INBOX_PUT_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(INBOX_CLEAR_REQUIRES_EXCLUSIVE_LOCK)

    def test_put_writes_inbox_file(self):
        from grill_flow_pack import inbox_put

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            body = {"packetId": "g1-p0", "kind": "graph-map", "nodes": [], "edges": []}
            out = inbox_put(run_dir, "g1-p0", body)
            self.assertEqual(out, {})
            path = run_dir / "packets" / "inbox" / "g1-p0.json"
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text()), body)

    def test_dup_inbox_id_exists(self):
        from grill_flow_pack import inbox_put

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            body = {"packetId": "g1-p0", "kind": "graph-map", "nodes": [], "edges": []}
            inbox_put(run_dir, "g1-p0", body)
            with mock.patch("sys.stderr", new_callable=StringIO) as se:
                with self.assertRaises(SystemExit):
                    inbox_put(run_dir, "g1-p0", body)
            self.assertEqual(json.loads(se.getvalue())["error"], "inbox_id_exists")

    def test_clear_missing_noop(self):
        from grill_flow_pack import inbox_clear

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self.assertEqual(inbox_clear(run_dir, "missing-id"), {})

    def test_clear_removes_existing(self):
        from grill_flow_pack import inbox_clear, inbox_put

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            inbox_put(run_dir, "g1-p0", {"packetId": "g1-p0"})
            path = run_dir / "packets" / "inbox" / "g1-p0.json"
            self.assertTrue(path.is_file())
            self.assertEqual(inbox_clear(run_dir, "g1-p0"), {})
            self.assertFalse(path.exists())

    def test_freeze_blocks_put_only(self):
        from grill_flow_state import assert_mutable_command_allowed
        from grill_flow_pack import inbox_clear

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            for status in ("complete", "aborted"):
                _write_run(run_dir, _normal_run(runStatus=status))
                with self.assertRaises(SystemExit):
                    assert_mutable_command_allowed(run_dir, "inbox-put")
                assert_mutable_command_allowed(run_dir, "inbox-clear")
                self.assertEqual(inbox_clear(run_dir, "any"), {})

    def test_put_allows_body_packet_id_mismatch_for_merge(self):
        from grill_flow_pack import inbox_put

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            body = {"packetId": "other", "kind": "graph-map", "nodes": [], "edges": []}
            inbox_put(run_dir, "g1-p0", body)
            stored = json.loads((run_dir / "packets" / "inbox" / "g1-p0.json").read_text())
            self.assertEqual(stored["packetId"], "other")
            self.assertNotEqual("g1-p0", stored["packetId"])


if __name__ == "__main__":
    unittest.main()
