import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestChrome(unittest.TestCase):
    def test_run_kinds(self):
        import grill_flow_chrome as c
        self.assertEqual(c.compute_chrome("empty", [], {}), "empty-run")
        self.assertEqual(c.compute_chrome("pathNotesOnly", [], {}), "pathNotes-only")
        self.assertEqual(c.compute_chrome("emptyLedger", [], {}), "empty-ledger")
    def test_only_delete(self):
        import grill_flow_chrome as c
        ob = [{"obligationId": "x", "change": "deleted"}]
        led = {"x": {"state": "covered", "kind": "semantic"}}
        self.assertEqual(c.compute_chrome("normal", ob, led), "only-delete")
    def test_all_structural(self):
        import grill_flow_chrome as c
        ob = [{"obligationId": "x", "change": "present"}]
        led = {"x": {"state": "covered", "kind": "structural"}}
        self.assertEqual(c.compute_chrome("normal", ob, led), "all-structural")
    def test_all_waived_normal(self):
        import grill_flow_chrome as c
        ob = [{"obligationId": "x", "change": "deleted"}]
        led = {"x": {"state": "waived", "kind": "semantic"}}
        self.assertEqual(c.compute_chrome("normal", ob, led), "normal")

if __name__ == "__main__":
    unittest.main()
