import importlib
import re
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent / "SKILL.md"
SPEC = SCRIPTS.parent / "docs" / "design-spec.md"

SPEC_TEST_POINTERS = {
    "runKind": "test_inventory.py::TestClassify.test_kinds",
    "Level-0 expanded defaults": "test_inventory.py::TestClassify.test_level0_expanded_defaults",
    "dirty union": "test_inventory_git.py::TestGitDiffInventory.test_dirty_union_oid_prefer",
    "named-wins": "test_inventory.py::TestClassify.test_named_wins_inventory",
    "budgets per phase/wave": "test_phases.py::TestPhases.test_raise_budget_plus_one",
    "phase table incl. `begin-flows`/`resume-graph`": (
        "test_phases.py::TestPhases.test_phase_table_begin_flows_resume_graph"
    ),
    "frozen complete": "test_phases.py::TestPhases.test_freeze_pack_merge_inbox_put",
    "drift demotes complete": "test_drift.py::TestDriftBehaviours.test_demote_complete_to_in_progress",
    "lock force success": "test_lock.py::TestLock.test_force_ok",
    "status without exclusive block": (
        "test_cli_integration.py::TestCliIntegration"
        ".test_status_ok_while_exclusive_lock_held_by_other_pid"
    ),
    "serve-stop tree": "test_render_serve.py::TestServe.test_serve_stop_live_match_and_mismatch",
    "stderr codes": "test_errors.py::TestErrors.test_codes_include_spec_set",
    "chrome mapping": "test_chrome.py::TestChrome.test_run_kinds",
    "resolve matrix": "test_resolve.py::TestResolve.test_resolve_matrix",
}

SPEC_COMMANDS = (
    "init-surface",
    "init-run",
    "recommend-gate",
    "apply-gate",
    "check-surface",
    "inbox-put",
    "inbox-clear",
    "pack-graph",
    "merge-graph",
    "pack-flows",
    "merge-flows",
    "status",
    "accept-partial",
    "begin-flows",
    "unwaive",
    "resume-graph",
    "raise-budget",
    "abort-run",
    "render",
    "serve-start",
    "serve-stop",
)

BANNED_IMPORT_RE = re.compile(
    r"\b(?:import|from)\s+(?:grill_review|grill_diff|grill_yagni|grill_repo)\b"
    r"|\bimport\s+ast\b|\bfrom\s+ast\s+import\b"
)
BANNED_DEP_RE = re.compile(r"tree-sitter|libcst|parser-generator", re.I)


def _spec_test_bullets() -> list:
    text = SPEC.read_text()
    marker = "## Tests (skill) — required"
    start = text.index(marker) + len(marker)
    rest = text[start:].lstrip("\n")
    line = rest.splitlines()[0].strip()
    return [b.strip().rstrip(".") for b in line.split(";") if b.strip()]


def _load_pointer(pointer: str):
    file_part, qual = pointer.split("::", 1)
    class_name, meth_name = qual.split(".", 1)
    mod_name = file_part[:-3] if file_part.endswith(".py") else file_part
    mod = importlib.import_module(mod_name)
    cls = getattr(mod, class_name)
    meth = getattr(cls, meth_name)
    return cls, meth


class TestSkillContracts(unittest.TestCase):
    def test_spec_tests_map_to_existing_methods(self) -> None:
        bullets = _spec_test_bullets()
        self.assertEqual(set(bullets), set(SPEC_TEST_POINTERS))
        self.assertEqual(bullets, list(SPEC_TEST_POINTERS.keys()))
        for bullet, pointer in SPEC_TEST_POINTERS.items():
            with self.subTest(bullet=bullet):
                cls, meth = _load_pointer(pointer)
                self.assertTrue(callable(meth), pointer)
                self.assertTrue(issubclass(cls, unittest.TestCase), pointer)

    def test_skill_contains_c10_and_commands(self) -> None:
        skill = SKILL.read_text()
        self.assertIn("C10", skill)
        self.assertNotIn("grill-review", skill)
        for cmd in SPEC_COMMANDS:
            with self.subTest(cmd=cmd):
                self.assertIn(cmd, skill)

    def test_helper_sources_ban_imports_and_parsers(self) -> None:
        helpers = sorted(SCRIPTS.glob("grill_flow_*.py")) + [SCRIPTS / "grill-flow.py"]
        self.assertGreaterEqual(len(helpers), 2)
        for path in helpers:
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertIsNone(BANNED_IMPORT_RE.search(text), path.name)
                self.assertIsNone(BANNED_DEP_RE.search(text), path.name)


if __name__ == "__main__":
    unittest.main()
