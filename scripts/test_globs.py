import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestGlobs(unittest.TestCase):
    def test_defaults(self):
        from grill_flow_globs import is_test_excluded, is_skipped
        self.assertTrue(is_test_excluded("tests/foo_test.py"))
        self.assertTrue(is_skipped("dist/app.js"))
        self.assertFalse(is_test_excluded("src/app.py"))

if __name__ == "__main__":
    unittest.main()
