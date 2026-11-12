import json, sys, unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestErrors(unittest.TestCase):
    def test_die_stderr_shape(self):
        import grill_flow_errors as err
        with patch("sys.stderr", new_callable=StringIO) as se:
            with self.assertRaises(SystemExit) as cm:
                err.die("invalid_args", "nope")
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(json.loads(se.getvalue()), {"error": "invalid_args", "message": "nope"})

    def test_codes_include_spec_set(self):
        import grill_flow_errors as err
        required = {
            "run_in_progress", "force_lock_required", "helper_not_found",
            "helper_not_executable", "invalid_args", "inbox_id_exists",
            "budget_exhausted", "serve_stop_mismatch", "serve_info_missing",
            "apply_gate_too_late", "unsupported_platform", "schema_error",
            "abort_conflict", "quality_error",
        }
        self.assertTrue(required <= err.CODES)

if __name__ == "__main__":
    unittest.main()
