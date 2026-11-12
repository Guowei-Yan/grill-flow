import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestHash(unittest.TestCase):
    def test_content_hash8_stable(self):
        from grill_flow_hash import content_hash8
        self.assertEqual(len(content_hash8("hello\n")), 8)
        self.assertEqual(content_hash8("hello\r\n"), content_hash8("hello\n"))
    def test_surface_hash_key_order(self):
        from grill_flow_hash import surface_hash
        a = {"mode": "file-set", "targets": ["a.py"], "baseOid": None, "headOid": None,
             "dirty": False, "testExclude": [], "skip": [], "obligationIds": ["b", "a"], "pathNotesDigests": ["z", "y"]}
        a_sorted = dict(a); a_sorted["obligationIds"] = sorted(a["obligationIds"]); a_sorted["pathNotesDigests"] = sorted(a["pathNotesDigests"])
        b = dict(reversed(list(a_sorted.items())))
        self.assertEqual(surface_hash(a_sorted), surface_hash(b))

if __name__ == "__main__":
    unittest.main()
