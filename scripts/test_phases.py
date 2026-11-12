import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _write_run(run_dir: Path, doc: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def _write_ledger(run_dir: Path, ledger: dict) -> None:
    (run_dir / "ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def _write_graph(run_dir: Path, nodes: dict, edges=None) -> None:
    (run_dir / "graph.json").write_text(
        json.dumps({"nodes": nodes, "edges": edges or []}, indent=2, sort_keys=True) + "\n"
    )


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
        "graph": {"phase": "not_started"},
        "flows": {"phase": "not_started"},
        "hardRejects": [],
    }
    doc.update(overrides)
    return doc


class TestPhases(unittest.TestCase):
    def test_begin_flows_requires_graph_clean_or_accepted(self):
        from grill_flow_state import begin_flows

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(graph={"phase": "active"}, flows={"phase": "not_started"}))
            with self.assertRaises(SystemExit):
                begin_flows(run_dir)
            _write_run(run_dir, _normal_run(graph={"phase": "clean"}, flows={"phase": "not_started"}))
            out = begin_flows(run_dir)
            self.assertEqual(out["flows"]["phase"], "active")
            self.assertFalse(out.get("graphPartial", False))

    def test_begin_flows_accepted_partial_sets_graph_partial(self):
        from grill_flow_state import begin_flows

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                _normal_run(
                    graph={"phase": "accepted_partial"},
                    flows={"phase": "not_started"},
                    runStatus="incomplete",
                ),
            )
            out = begin_flows(run_dir)
            self.assertEqual(out["flows"]["phase"], "active")
            self.assertTrue(out["graphPartial"])

    def test_graph_clean_does_not_auto_start_flows(self):
        from grill_flow_state import apply_graph_clean_predicate

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            gate = _normal_run()["gate"]
            _write_run(run_dir, _normal_run(graph={"phase": "active"}, gate=gate))
            _write_graph(run_dir, {"file:a.py": {"hop": 0, "expanded": True, "kind": "file", "path": "a.py"}})
            _write_ledger(run_dir, {})
            out = apply_graph_clean_predicate(run_dir)
            self.assertEqual(out["graph"]["phase"], "clean")
            self.assertEqual(out["flows"]["phase"], "not_started")

    def test_accept_partial_graph(self):
        from grill_flow_state import accept_partial

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(graph={"phase": "not_started"}))
            with self.assertRaises(SystemExit):
                accept_partial(run_dir, phase="graph")
            _write_run(run_dir, _normal_run(graph={"phase": "active"}))
            out = accept_partial(run_dir, phase="graph")
            self.assertEqual(out["graph"]["phase"], "accepted_partial")
            self.assertEqual(out["flows"]["phase"], "not_started")
            self.assertEqual(out["runStatus"], "incomplete")

    def test_accept_partial_flows(self):
        from grill_flow_state import accept_partial

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(graph={"phase": "clean"}, flows={"phase": "active"}))
            _write_ledger(run_dir, {})
            with self.assertRaises(SystemExit):
                accept_partial(run_dir, phase="flows")
            _write_ledger(run_dir, {"o1": {"state": "uncovered", "kind": "semantic"}})
            out = accept_partial(run_dir, phase="flows")
            self.assertEqual(out["flows"]["phase"], "accepted_partial")
            self.assertEqual(out["runStatus"], "incomplete")
            ledger = json.loads((run_dir / "ledger.json").read_text())
            self.assertEqual(ledger["o1"]["state"], "waived")

    def test_resume_graph(self):
        from grill_flow_state import resume_graph

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(graph={"phase": "clean"}, flows={"phase": "not_started"}))
            with self.assertRaises(SystemExit):
                resume_graph(run_dir)
            _write_run(
                run_dir,
                _normal_run(
                    graph={"phase": "accepted_partial"},
                    flows={"phase": "not_started"},
                    runStatus="incomplete",
                ),
            )
            out = resume_graph(run_dir)
            self.assertEqual(out["graph"]["phase"], "active")

    def test_phase_table_begin_flows_resume_graph(self):
        from grill_flow_state import begin_flows, resume_graph

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(graph={"phase": "clean"}, flows={"phase": "not_started"}))
            begun = begin_flows(run_dir)
            self.assertEqual(begun["flows"]["phase"], "active")
            _write_run(
                run_dir,
                _normal_run(
                    graph={"phase": "accepted_partial"},
                    flows={"phase": "not_started"},
                    runStatus="incomplete",
                ),
            )
            resumed = resume_graph(run_dir)
            self.assertEqual(resumed["graph"]["phase"], "active")

    def test_unwaive(self):
        from grill_flow_state import unwaive

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                _normal_run(
                    graph={"phase": "clean"},
                    flows={"phase": "accepted_partial"},
                    runStatus="incomplete",
                    graphPartial=False,
                ),
            )
            _write_ledger(run_dir, {"o1": {"state": "waived", "kind": "semantic"}})
            out = unwaive(run_dir, obligation_ids=["o1"])
            ledger = json.loads((run_dir / "ledger.json").read_text())
            self.assertEqual(ledger["o1"]["state"], "uncovered")
            self.assertEqual(out["flows"]["phase"], "active")
            self.assertEqual(out["runStatus"], "in_progress")

    def test_raise_budget_plus_one(self):
        from grill_flow_state import raise_budget

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            doc = _normal_run(graph={"phase": "active"}, flows={"phase": "not_started"})
            _write_run(run_dir, doc)
            out = raise_budget(run_dir, phase="graph")
            self.assertEqual(out["gate"]["graphBudget"], 7)
            _write_run(
                run_dir,
                _normal_run(
                    graph={"phase": "clean"},
                    flows={"phase": "active"},
                    gate=dict(doc["gate"], graphBudget=7),
                ),
            )
            out2 = raise_budget(run_dir, phase="flows")
            self.assertEqual(out2["gate"]["lineBudget"], 9)
            _write_run(run_dir, _normal_run(graph={"phase": "not_started"}))
            with self.assertRaises(SystemExit):
                raise_budget(run_dir, phase="graph")

    def test_abort_run(self):
        from grill_flow_state import abort_run

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(runStatus="complete"))
            with self.assertRaises(SystemExit) as ctx:
                abort_run(run_dir)
            self.assertEqual(ctx.exception.code, 1)
            _write_run(run_dir, _normal_run(runStatus="aborted"))
            with self.assertRaises(SystemExit):
                abort_run(run_dir)
            _write_run(run_dir, _normal_run(runStatus="incomplete", graph={"phase": "accepted_partial"}))
            out = abort_run(run_dir)
            self.assertEqual(out["runStatus"], "incomplete")
            _write_run(run_dir, _normal_run(runStatus="in_progress"))
            out2 = abort_run(run_dir)
            self.assertEqual(out2["runStatus"], "aborted")

    def test_recommend_gate_normal_only_no_lock(self):
        from grill_flow_state import RECOMMEND_GATE_REQUIRES_EXCLUSIVE_LOCK, recommend_gate

        self.assertFalse(RECOMMEND_GATE_REQUIRES_EXCLUSIVE_LOCK)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(runKind="empty", gate=None))
            with self.assertRaises(SystemExit):
                recommend_gate(run_dir)
            _write_run(run_dir, _normal_run())
            out = recommend_gate(run_dir)
            self.assertEqual(out["runKind"], "normal")
            self.assertEqual(out["recommended"]["packetSizeObligations"], 40)
            self.assertEqual(out["recommended"]["packetSizeFiles"], 8)
            self.assertEqual(out["recommended"]["validatorSlots"], 8)
            self.assertEqual(out["recommended"]["N"], 2)
            self.assertEqual(out["recommended"]["graphBudget"], 6)
            self.assertEqual(out["recommended"]["lineBudget"], 8)
            self.assertIn("rationale", out)

    def test_status_c5_no_lock(self):
        from grill_flow_state import STATUS_REQUIRES_EXCLUSIVE_LOCK, build_status

        self.assertFalse(STATUS_REQUIRES_EXCLUSIVE_LOCK)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run(graph={"phase": "active"}, flows={"phase": "not_started"}))
            _write_ledger(run_dir, {"o1": {"state": "uncovered", "kind": "semantic"}})
            _write_graph(run_dir, {"file:a.py": {"hop": 0, "expanded": False, "kind": "file", "path": "a.py"}})
            (run_dir / "pathNotes.json").write_text("[]\n")
            (run_dir / "obligations.json").write_text(json.dumps([
                {"obligationId": "o1", "path": "a.py", "kind": "semantic", "change": "present"}
            ]) + "\n")
            st = build_status(run_dir)
            for key in (
                "runId", "runKind", "runStatus", "chrome", "graphPartial",
                "graph", "flows", "gate", "hardRejects", "pathNotesCount", "lock",
            ):
                self.assertIn(key, st)
            self.assertEqual(st["graph"]["phase"], "active")
            self.assertEqual(st["graph"]["budgetRemaining"], 6)
            self.assertIn("clean", st["graph"])
            self.assertEqual(st["flows"]["uncoveredCount"], 1)
            self.assertEqual(st["flows"]["waivedCount"], 0)

    def test_freeze_pack_merge_inbox_put(self):
        from grill_flow_state import assert_mutable_command_allowed

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            for status in ("complete", "aborted"):
                _write_run(run_dir, _normal_run(runStatus=status))
                for cmd in ("pack-graph", "merge-graph", "pack-flows", "merge-flows", "inbox-put"):
                    with self.assertRaises(SystemExit):
                        assert_mutable_command_allowed(run_dir, cmd)
            _write_run(run_dir, _normal_run(runStatus="complete"))
            assert_mutable_command_allowed(run_dir, "inbox-clear")
            assert_mutable_command_allowed(run_dir, "check-surface")

    def test_apply_gate_rules(self):
        from grill_flow_state import apply_gate

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            with self.assertRaises(SystemExit):
                apply_gate(run_dir, gate={"N": 1, "graphBudget": 1, "lineBudget": 1,
                                          "packetSizeObligations": 40, "packetSizeFiles": 8,
                                          "validatorSlots": 8, "models": "n/a"})
            _write_run(run_dir, _normal_run(runKind="empty", gate=None, graph={"phase": None}, flows={"phase": None}, runStatus="complete"))
            with self.assertRaises(SystemExit):
                apply_gate(run_dir, gate={"N": 0, "graphBudget": 0, "lineBudget": 0,
                                          "packetSizeObligations": 40, "packetSizeFiles": 8,
                                          "validatorSlots": 1, "models": "n/a"})
            short = {
                "N": 0, "graphBudget": 0, "lineBudget": 0,
                "packetSizeObligations": 40, "packetSizeFiles": 8,
                "validatorSlots": 1, "models": "n/a",
            }
            _write_run(run_dir, _normal_run(runKind="pathNotesOnly", gate=short, graph={"phase": "clean"}, flows={"phase": "clean"}, runStatus="complete"))
            out = apply_gate(run_dir, gate=short)
            self.assertEqual(out["gate"], short)
            _write_run(run_dir, _normal_run(graph={"phase": "not_started"}))
            gate = {
                "N": 2, "graphBudget": 6, "lineBudget": 8,
                "packetSizeObligations": 40, "packetSizeFiles": 8,
                "validatorSlots": 8, "models": "n/a",
            }
            out2 = apply_gate(run_dir, gate=gate)
            self.assertEqual(out2["graph"]["phase"], "active")
            self.assertEqual(out2["gate"]["packetSizeObligations"], 40)
            self.assertEqual(out2["gate"]["packetSizeFiles"], 8)
            self.assertEqual(out2["gate"]["validatorSlots"], 8)
            _write_run(run_dir, _normal_run(graph={"phase": "active"}, gate=gate))
            with self.assertRaises(SystemExit):
                apply_gate(run_dir, gate=gate)

    def test_defaults_packet_sizes(self):
        from grill_flow_state import DEFAULT_GATE_NORMAL, DEFAULT_PACKET_SIZE_FILES, DEFAULT_PACKET_SIZE_OBLIGATIONS, DEFAULT_VALIDATOR_SLOTS

        self.assertEqual(DEFAULT_PACKET_SIZE_OBLIGATIONS, 40)
        self.assertEqual(DEFAULT_PACKET_SIZE_FILES, 8)
        self.assertEqual(DEFAULT_VALIDATOR_SLOTS, 8)
        self.assertEqual(DEFAULT_GATE_NORMAL["packetSizeObligations"], 40)
        self.assertEqual(DEFAULT_GATE_NORMAL["packetSizeFiles"], 8)
        self.assertEqual(DEFAULT_GATE_NORMAL["validatorSlots"], 8)

    def test_happy_path_complete(self):
        from grill_flow_state import begin_flows, evaluate_completion

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            gate = {
                "N": 2, "graphBudget": 6, "lineBudget": 8,
                "packetSizeObligations": 40, "packetSizeFiles": 8,
                "validatorSlots": 8, "models": "n/a",
            }
            _write_run(run_dir, _normal_run(graph={"phase": "clean"}, flows={"phase": "not_started"}, gate=gate))
            _write_graph(run_dir, {"file:a.py": {"hop": 0, "expanded": True, "kind": "file", "path": "a.py"}})
            _write_ledger(run_dir, {"o1": {"state": "covered", "kind": "semantic"}})
            begin_flows(run_dir)
            _write_ledger(run_dir, {"o1": {"state": "covered", "kind": "semantic"}})
            out = evaluate_completion(run_dir)
            self.assertEqual(out["flows"]["phase"], "clean")
            self.assertEqual(out["runStatus"], "complete")
            self.assertFalse(out["graphPartial"])

    def test_mutators_require_exclusive_lock_flags(self):
        from grill_flow_state import (
            ACCEPT_PARTIAL_REQUIRES_EXCLUSIVE_LOCK,
            ABORT_RUN_REQUIRES_EXCLUSIVE_LOCK,
            APPLY_GATE_REQUIRES_EXCLUSIVE_LOCK,
            BEGIN_FLOWS_REQUIRES_EXCLUSIVE_LOCK,
            RAISE_BUDGET_REQUIRES_EXCLUSIVE_LOCK,
            RESUME_GRAPH_REQUIRES_EXCLUSIVE_LOCK,
            UNWAIVE_REQUIRES_EXCLUSIVE_LOCK,
        )

        self.assertTrue(APPLY_GATE_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(ACCEPT_PARTIAL_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(BEGIN_FLOWS_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(UNWAIVE_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(RESUME_GRAPH_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(RAISE_BUDGET_REQUIRES_EXCLUSIVE_LOCK)
        self.assertTrue(ABORT_RUN_REQUIRES_EXCLUSIVE_LOCK)

    def test_cli_status_and_recommend_gate(self):
        import importlib.util
        import grill_flow_lock

        spec = importlib.util.spec_from_file_location(
            "grill_flow_cli",
            Path(__file__).resolve().parent / "grill-flow.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            _write_run(run_dir, _normal_run())
            _write_ledger(run_dir, {})
            _write_graph(run_dir, {})
            (run_dir / "pathNotes.json").write_text("[]\n")
            (run_dir / "obligations.json").write_text("[]\n")
            with mock.patch.object(grill_flow_lock, "acquire_exclusive") as acq:
                rc = mod.main([
                    "--repo-root", td, "--run-dir", str(run_dir), "recommend-gate",
                ])
                self.assertEqual(rc, 0)
                acq.assert_not_called()
            with mock.patch.object(grill_flow_lock, "acquire_exclusive") as acq2:
                rc2 = mod.main([
                    "--repo-root", td, "--run-dir", str(run_dir), "status",
                ])
                self.assertEqual(rc2, 0)
                acq2.assert_not_called()


if __name__ == "__main__":
    unittest.main()
