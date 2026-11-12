import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestClassify(unittest.TestCase):
    def test_kinds(self):
        from grill_flow_inventory import classify_run_kind
        self.assertEqual(classify_run_kind([], [], []), "empty")
        self.assertEqual(classify_run_kind([], [{"kind": "skip"}], []), "pathNotesOnly")
        self.assertEqual(classify_run_kind([], [], ["a.py"]), "emptyLedger")
        self.assertEqual(classify_run_kind([{"obligationId": "x"}], [], ["a.py"]), "normal")

    def test_named_wins_inventory(self):
        from grill_flow_inventory import inventory_file_set
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir()
            (root / "tests" / "foo_test.py").write_text("x = 1\n")
            (root / "dist").mkdir()
            (root / "dist" / "app.js").write_text("console.log(1)\n")
            inv = inventory_file_set(root, ["tests/foo_test.py", "dist/app.js"])
            ids = {o["path"] for o in inv["obligations"]}
            self.assertIn("tests/foo_test.py", ids)
            self.assertIn("dist/app.js", ids)

    def test_level0_expanded_defaults(self):
        from grill_flow_inventory import level0_expanded_for
        self.assertEqual(level0_expanded_for(kind="obligation"), False)
        self.assertEqual(level0_expanded_for(kind="empty_or_binary_seed"), True)

    def test_init_run_before_surface_invalid(self):
        from grill_flow_state import init_run_guard
        with self.assertRaises(SystemExit):
            init_run_guard(surface_exists=False)

    def test_named_binary_path_notes(self):
        from grill_flow_inventory import inventory_file_set
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "blob.bin").write_bytes(b"\x00\x01\xff")
            inv = inventory_file_set(root, ["blob.bin"])
            self.assertEqual(inv["obligations"], [])
            self.assertTrue(any(n.get("kind") == "binary" for n in inv["pathNotes"]))

class TestInitRunShort(unittest.TestCase):
    def test_empty_complete_no_gate(self):
        from grill_flow_state import apply_init_run_kind
        st = apply_init_run_kind("empty")
        self.assertEqual(st["runStatus"], "complete")
        self.assertIsNone(st.get("gate"))
    def test_path_notes_only_auto_gate(self):
        from grill_flow_state import apply_init_run_kind
        st = apply_init_run_kind("pathNotesOnly")
        self.assertEqual(st["runStatus"], "complete")
        self.assertEqual(st["gate"]["N"], 0)
        self.assertEqual(st["gate"]["graphBudget"], 0)
        self.assertEqual(st["gate"]["lineBudget"], 0)
        self.assertEqual(st["gate"]["validatorSlots"], 1)
    def test_empty_ledger_auto_gate(self):
        from grill_flow_state import apply_init_run_kind
        st = apply_init_run_kind("emptyLedger")
        self.assertEqual(st["runStatus"], "complete")
        self.assertEqual(st["gate"]["N"], 0)
        self.assertEqual(st["gate"]["graphBudget"], 0)
        self.assertEqual(st["gate"]["lineBudget"], 0)
        self.assertEqual(st["gate"]["validatorSlots"], 1)
        self.assertEqual(st["gate"]["packetSizeObligations"], 40)
        self.assertEqual(st["gate"]["packetSizeFiles"], 8)
    def test_init_run_exclusive_lock_flag(self):
        from grill_flow_state import INIT_RUN_REQUIRES_EXCLUSIVE_LOCK, INIT_SURFACE_REQUIRES_EXCLUSIVE_LOCK
        self.assertTrue(INIT_RUN_REQUIRES_EXCLUSIVE_LOCK)
        self.assertFalse(INIT_SURFACE_REQUIRES_EXCLUSIVE_LOCK)
    def test_level0_hop0_seed(self):
        from grill_flow_state import seed_level0_nodes
        nodes = seed_level0_nodes(["src/a.py"], expanded=False)
        self.assertEqual(nodes["file:src/a.py"]["hop"], 0)
        self.assertFalse(nodes["file:src/a.py"]["expanded"])
    def test_init_writes_surface_hash(self):
        from grill_flow_state import initial_surface_hash_written
        self.assertTrue(initial_surface_hash_written({"mode": "file-set"}))
    def test_new_obligation_uncovered(self):
        from grill_flow_state import initial_ledger_state
        self.assertEqual(initial_ledger_state("file:a.py:1:abcd1234"), "uncovered")

if __name__ == "__main__":
    unittest.main()
