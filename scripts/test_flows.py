import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestFlowsLockAndPhase(unittest.TestCase):
    def test_exclusive_lock_flag(self):
        from grill_flow_flows import PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK
        self.assertTrue(PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK)

    def test_phase_active_gate(self):
        from grill_flow_flows import assert_flows_pack_allowed
        with self.assertRaises(SystemExit):
            assert_flows_pack_allowed(phase="not_started")
        with self.assertRaises(SystemExit):
            assert_flows_pack_allowed(phase="clean")
        assert_flows_pack_allowed(phase="active")

class TestFlowsLedger(unittest.TestCase):
    def test_coverage_ledger_partition(self):
        from grill_flow_flows import partition_ledger
        ledger = {
            "a": {"state": "uncovered"},
            "b": {"state": "covered"},
            "c": {"state": "waived"},
        }
        parts = partition_ledger(ledger)
        self.assertEqual(parts["uncovered"], ["a"])
        self.assertEqual(parts["covered"], ["b"])
        self.assertEqual(parts["waived"], ["c"])

class TestFlowsContracts(unittest.TestCase):
    def test_c3_map_return_shape(self):
        from grill_flow_flows import validate_c3_map_shape
        body = {
            "packetId": "f1-p0",
            "kind": "flows-map",
            "dispositions": [
                {
                    "obligationId": "file:src/a.py:10:abcd1234",
                    "kind": "semantic",
                    "change": "present",
                    "inputs": ["x"],
                    "logic": ["add 1"],
                    "outputs": ["y"],
                    "consumers": ["file:src/b.py"],
                    "evidenceRef": {
                        "path": "src/a.py", "oid": None, "source": "worktree",
                        "startLine": 10, "endLine": 10, "note": "",
                    },
                }
            ],
        }
        self.assertEqual(validate_c3_map_shape(body)["kind"], "flows-map")
        self.assertIn("dispositions", body)

    def test_c4_validate_return_shape(self):
        from grill_flow_flows import validate_c4_validate_shape
        body = {
            "packetId": "f1-p0-val",
            "kind": "flows-validate",
            "decisions": [
                {"obligationId": "file:src/a.py:10:abcd1234", "decision": "confirm"},
                {"obligationId": "file:src/a.py:11:ffffffff", "decision": "reject", "reason": "hollow"},
                {
                    "obligationId": "file:src/a.py:1:deadbeef",
                    "decision": "reclassifyTo",
                    "disposition": {
                        "obligationId": "file:src/a.py:1:deadbeef",
                        "kind": "semantic",
                        "change": "present",
                        "inputs": [],
                        "logic": ["side-effect import"],
                        "outputs": [],
                        "consumers": [],
                        "evidenceRef": {
                            "path": "src/a.py", "oid": None, "source": "worktree",
                            "startLine": 1, "endLine": 1, "note": "",
                        },
                    },
                },
            ],
        }
        self.assertEqual(validate_c4_validate_shape(body)["kind"], "flows-validate")
        self.assertEqual(body["decisions"][2]["decision"], "reclassifyTo")

class TestFlowsPackCaps(unittest.TestCase):
    def test_line_budget_wave_caps(self):
        from grill_flow_flows import chunk_obligations, selectable_obligation_ids
        ledger = {f"oid:{i}": {"state": "uncovered"} for i in range(100)}
        ids = selectable_obligation_ids(ledger)
        packets = chunk_obligations(ids, packet_size_obligations=40, validator_slots=2)
        self.assertEqual(len(packets), 2)
        self.assertTrue(all(len(p) <= 40 for p in packets))

    def test_pack_does_not_change_line_budget(self):
        from grill_flow_flows import pack_flows_budget_check
        self.assertEqual(pack_flows_budget_check(8), 8)

class TestFlowsMergeRules(unittest.TestCase):
    def test_merge_decrements_even_with_hard_rejects(self):
        from grill_flow_graph import merge_budget_after
        self.assertEqual(merge_budget_after(8, hard_rejects=1, schema_error=False), 7)

    def test_no_decrement_on_schema_error_or_failed_wave(self):
        from grill_flow_graph import merge_budget_after
        self.assertEqual(merge_budget_after(8, hard_rejects=0, schema_error=True), 8)
        self.assertEqual(merge_budget_after(8, hard_rejects=0, schema_error=False, failed_wave=True), 8)

    def test_packet_id_congruence_schema_error(self):
        from grill_flow_pack import check_packet_id_congruence
        with self.assertRaises(SystemExit):
            check_packet_id_congruence(cli_id="f1-p0", body_id="other")

    def test_unparseable_wrong_shape_schema_error(self):
        from grill_flow_pack import load_inbox_packet, validate_flows_map_packet
        with self.assertRaises(SystemExit):
            load_inbox_packet("{not json")
        with self.assertRaises(SystemExit):
            validate_flows_map_packet({"packetId": "f1", "kind": "wrong"})

    def test_reject_to_uncovered(self):
        from grill_flow_flows import apply_validate_flow_decisions
        ledger = {
            "oid:1": {
                "state": "covered",
                "kind": "semantic",
                "disposition": {"obligationId": "oid:1", "kind": "semantic", "consumers": []},
            }
        }
        apply_validate_flow_decisions(
            ledger,
            [{"obligationId": "oid:1", "decision": "reject", "reason": "hollow"}],
        )
        self.assertEqual(ledger["oid:1"]["state"], "uncovered")
        self.assertNotIn("disposition", ledger["oid:1"])

    def test_reclassify_to(self):
        from grill_flow_flows import apply_validate_flow_decisions
        ledger = {
            "oid:1": {
                "state": "covered",
                "kind": "structural",
                "disposition": {"obligationId": "oid:1", "kind": "structural"},
            }
        }
        new_disp = {
            "obligationId": "oid:1",
            "kind": "semantic",
            "change": "present",
            "inputs": [],
            "logic": ["x"],
            "outputs": [],
            "consumers": [],
            "evidenceRef": {"path": "a.py", "oid": None, "source": "worktree", "note": ""},
        }
        apply_validate_flow_decisions(
            ledger,
            [{"obligationId": "oid:1", "decision": "reclassifyTo", "disposition": new_disp}],
        )
        self.assertEqual(ledger["oid:1"]["state"], "covered")
        self.assertEqual(ledger["oid:1"]["kind"], "semantic")
        self.assertEqual(ledger["oid:1"]["disposition"]["logic"], ["x"])

    def test_hard_reject_c5_missing_consumer(self):
        from grill_flow_flows import collect_hard_rejects_from_dispositions
        dispositions = [{
            "obligationId": "file:src/a.py:10:abcd1234",
            "kind": "semantic",
            "consumers": ["file:missing.py"],
        }]
        hrs = collect_hard_rejects_from_dispositions(
            dispositions, graph_nodes={"file:src/a.py": {}}, packet_id="f1-p0"
        )
        self.assertEqual(hrs[0]["phase"], "flows")
        self.assertEqual(hrs[0]["kind"], "missing_component")
        self.assertEqual(hrs[0]["obligationId"], "file:src/a.py:10:abcd1234")
        self.assertEqual(hrs[0]["componentId"], "file:missing.py")

    def test_hard_rejects_clear_on_later_flows_success(self):
        from grill_flow_flows import clear_flows_hard_rejects
        hrs = [{
            "phase": "flows",
            "kind": "missing_component",
            "obligationId": "oid:1",
            "componentId": "file:missing.py",
        }]
        left = clear_flows_hard_rejects(hrs, {"file:missing.py"})
        self.assertEqual(left, [])

    def test_flows_clean_predicate(self):
        from grill_flow_flows import flows_is_clean
        ledger = {"a": {"state": "covered"}}
        self.assertTrue(flows_is_clean(ledger, hard_rejects=[], flows_phase="active"))
        ledger["b"] = {"state": "uncovered"}
        self.assertFalse(flows_is_clean(ledger, hard_rejects=[], flows_phase="active"))
        self.assertFalse(flows_is_clean({"a": {"state": "covered"}}, hard_rejects=[{"phase": "flows"}], flows_phase="active"))
        self.assertFalse(flows_is_clean({"a": {"state": "covered"}}, hard_rejects=[], flows_phase="accepted_partial"))

    def test_semantic_flow_stats_and_granularity_gate(self):
        from grill_flow_errors import die
        from grill_flow_flows import (
            FLOW_PATH_MIN_SEMANTIC,
            assert_flow_granularity,
            logic_fingerprint,
            path_by_obligation,
            semantic_flow_stats,
        )
        self.assertEqual(logic_fingerprint([" a ", "", "b"]), "a\nb")
        self.assertEqual(logic_fingerprint(None), "")

        # Tiny path of 3 singletons — exempt (< FLOW_PATH_MIN_SEMANTIC)
        tiny_led = {}
        tiny_obs = []
        for i in range(3):
            oid = f"file:tiny.py:{i}:aaaaaaa{i}"
            tiny_obs.append({"obligationId": oid, "path": "tiny.py", "line": i})
            tiny_led[oid] = {
                "state": "covered",
                "disposition": {
                    "kind": "semantic",
                    "logic": [f"unique-{i}"],
                    "obligationId": oid,
                },
            }
        tiny_stats = semantic_flow_stats(tiny_led, path_by_obligation(tiny_obs, tiny_led))
        self.assertEqual(tiny_stats["byPath"]["tiny.py"]["semanticCount"], 3)
        self.assertEqual(tiny_stats["violatingPaths"], [])
        assert_flow_granularity(tiny_led, path_by_obligation(tiny_obs, tiny_led))

        # 10 unique logics on one path — fail
        bad_led = {}
        bad_obs = []
        for i in range(10):
            oid = f"file:big.py:{i}:bbbbbbb{i}"
            bad_obs.append({"obligationId": oid, "path": "big.py", "line": i})
            bad_led[oid] = {
                "state": "covered",
                "disposition": {
                    "kind": "semantic",
                    "logic": [f"line-only-{i}"],
                    "obligationId": oid,
                },
            }
        bad_stats = semantic_flow_stats(bad_led, path_by_obligation(bad_obs, bad_led))
        self.assertGreaterEqual(
            bad_stats["byPath"]["big.py"]["semanticCount"], FLOW_PATH_MIN_SEMANTIC
        )
        self.assertIn("big.py", bad_stats["violatingPaths"])
        with self.assertRaises(SystemExit):
            assert_flow_granularity(bad_led, path_by_obligation(bad_obs, bad_led))

        # Shared logic across 10 lines — pass
        good_led = {}
        good_obs = []
        for i in range(10):
            oid = f"file:ok.py:{i}:cccccccc{i}"
            good_obs.append({"obligationId": oid, "path": "ok.py", "line": i})
            good_led[oid] = {
                "state": "covered",
                "disposition": {
                    "kind": "semantic",
                    "logic": ["shared flow behaviour"],
                    "obligationId": oid,
                },
            }
        good_stats = semantic_flow_stats(good_led, path_by_obligation(good_obs, good_led))
        self.assertEqual(good_stats["byPath"]["ok.py"]["groupCount"], 1)
        self.assertEqual(good_stats["violatingPaths"], [])
        assert_flow_granularity(good_led, path_by_obligation(good_obs, good_led))

    def test_run_status_complete_only_via_task8_conjunct(self):
        from grill_flow_flows import flows_merge_sets_run_complete
        self.assertFalse(flows_merge_sets_run_complete)


class TestFlowsC8C9C10(unittest.TestCase):
    def _seed_run(self, run_dir: Path, *, line_budget: int = 8) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "packets" / "inbox").mkdir(parents=True, exist_ok=True)
        (run_dir / "packets" / "out").mkdir(parents=True, exist_ok=True)
        ledger = {
            "file:src/a.py:10:abcd1234": {"state": "uncovered", "kind": "semantic"},
        }
        (run_dir / "ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
        (run_dir / "graph.json").write_text(json.dumps({
            "nodes": {
                "file:src/a.py": {"hop": 0, "expanded": True},
                "file:src/b.py": {"hop": 1, "expanded": True},
            },
            "edges": [],
        }, indent=2) + "\n")
        (run_dir / "run.json").write_text(json.dumps({
            "runId": run_dir.name,
            "runKind": "normal",
            "runStatus": "in_progress",
            "gate": {
                "N": 2,
                "graphBudget": 0,
                "lineBudget": line_budget,
                "packetSizeObligations": 40,
                "packetSizeFiles": 8,
                "validatorSlots": 8,
                "models": "n/a",
            },
            "graph": {"phase": "clean"},
            "flows": {"phase": "active"},
            "graphPartial": False,
            "hardRejects": [],
        }, indent=2) + "\n")
        (run_dir / "obligations.json").write_text("[]\n")
        (run_dir / "pathNotes.json").write_text("[]\n")
        (run_dir / "surface.json").write_text(json.dumps({
            "mode": "file-set",
            "targets": ["src/a.py"],
            "baseOid": None,
            "headOid": None,
            "dirty": False,
            "testExclude": [],
            "skip": [],
        }) + "\n")
        (run_dir / "surface-hash.txt").write_text("deadbeef\n")

    def test_c8_flows_pack_stdout_map_and_validate(self):
        import grill_flow_flows as flows_mod
        from grill_flow_flows import build_flows_pack_stdout
        out_map = build_flows_pack_stdout(
            wave_id="f1",
            mode="map",
            budget_remaining=8,
            packets=[{
                "packetId": "f1-p0",
                "assignedObligationIds": ["file:src/a.py:10:abcd1234"],
                "outPath": "packets/out/f1-p0.json",
            }],
        )
        self.assertEqual(out_map["phase"], "flows")
        self.assertEqual(out_map["mode"], "map")
        self.assertEqual(out_map["budgetRemaining"], 8)
        self.assertIn("assignedObligationIds", out_map["packets"][0])
        out_val = build_flows_pack_stdout(
            wave_id="f1",
            mode="validate",
            budget_remaining=8,
            packets=[{
                "packetId": "f1-p0-val",
                "assignedObligationIds": ["file:src/a.py:10:abcd1234"],
                "outPath": "packets/out/f1-p0-val.json",
            }],
        )
        self.assertEqual(out_val["mode"], "validate")
        self.assertEqual(out_val["phase"], "flows")
        self.assertTrue(hasattr(flows_mod, "HAS_PACK_VALIDATE_COMMAND"))
        self.assertFalse(flows_mod.HAS_PACK_VALIDATE_COMMAND)

    def test_c9_flows_merge_stdout(self):
        from grill_flow_flows import build_flows_merge_stdout
        out = build_flows_merge_stdout(
            wave_id="f1",
            merged_packet_ids=["f1-p0", "f1-p0-val"],
            budget_remaining=7,
            hard_rejects_added=[],
            dropped_edges=[],
            graph_clean=True,
            flows_clean=False,
        )
        self.assertEqual(out["phase"], "flows")
        self.assertEqual(out["waveId"], "f1")
        for key in (
            "mergedPacketIds", "budgetRemaining", "hardRejectsAdded",
            "droppedEdges", "graphClean", "flowsClean",
        ):
            self.assertIn(key, out)

    def test_c10_wave_steps(self):
        from grill_flow_flows import C10_FLOWS_WAVE_STEPS, HAS_PACK_VALIDATE_COMMAND
        self.assertFalse(HAS_PACK_VALIDATE_COMMAND)
        self.assertEqual(
            C10_FLOWS_WAVE_STEPS,
            (
                "pack-flows",
                "inbox-put",
                "pack-flows --validate",
                "inbox-put",
                "merge-flows",
            ),
        )

    def _load_cli(self):
        import importlib.util
        path = Path(__file__).resolve().parent / "grill-flow.py"
        spec = importlib.util.spec_from_file_location("grill_flow_cli_flows", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_cli_pack_merge_wave_smoke(self):
        import io
        cli = self._load_cli()
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "rid"
            self._seed_run(run_dir, line_budget=8)
            repo = Path(td) / "repo"
            repo.mkdir()
            (repo / "src").mkdir(parents=True, exist_ok=True)
            (repo / "src" / "a.py").write_text("x = 1\n")
            from grill_flow_hash import content_hash8, surface_hash
            from grill_flow_surface import build_c11_hash_object, load_surface
            surface = load_surface(run_dir)
            oid = f"file:src/a.py:1:{content_hash8('x = 1')}"
            ledger = {oid: {"state": "uncovered", "kind": "semantic"}}
            (run_dir / "ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
            hash_obj = build_c11_hash_object(surface, obligation_ids=[oid], path_notes=[])
            (run_dir / "surface-hash.txt").write_text(surface_hash(hash_obj) + "\n")
            argv_pack = [
                "--repo-root", str(repo),
                "--run-dir", str(run_dir),
                "pack-flows", "--wave-id", "f1",
            ]
            old_out = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                rc = cli.main(argv_pack)
            finally:
                sys.stdout = old_out
            self.assertEqual(rc, 0)
            pack_out = json.loads(buf.getvalue())
            self.assertEqual(pack_out["phase"], "flows")
            self.assertEqual(pack_out["mode"], "map")
            self.assertEqual(pack_out["budgetRemaining"], 8)
            pid = pack_out["packets"][0]["packetId"]
            map_body = {
                "packetId": pid,
                "kind": "flows-map",
                "dispositions": [{
                    "obligationId": oid,
                    "kind": "semantic",
                    "change": "present",
                    "inputs": ["x"],
                    "logic": ["add 1"],
                    "outputs": ["y"],
                    "consumers": ["file:src/b.py"],
                    "evidenceRef": {
                        "path": "src/a.py", "oid": None, "source": "worktree",
                        "startLine": 10, "endLine": 10, "note": "",
                    },
                }],
            }
            (run_dir / "packets" / "inbox" / f"{pid}.json").write_text(
                json.dumps(map_body) + "\n"
            )
            buf = io.StringIO()
            sys.stdout = buf
            try:
                rc = cli.main([
                    "--repo-root", str(repo),
                    "--run-dir", str(run_dir),
                    "pack-flows", "--wave-id", "f1", "--validate",
                ])
            finally:
                sys.stdout = old_out
            self.assertEqual(rc, 0)
            val_out = json.loads(buf.getvalue())
            self.assertEqual(val_out["mode"], "validate")
            vid = val_out["packets"][0]["packetId"]
            val_body = {
                "packetId": vid,
                "kind": "flows-validate",
                "decisions": [{
                    "obligationId": oid,
                    "decision": "confirm",
                }],
            }
            (run_dir / "packets" / "inbox" / f"{vid}.json").write_text(
                json.dumps(val_body) + "\n"
            )
            before = json.loads((run_dir / "run.json").read_text())["gate"]["lineBudget"]
            buf = io.StringIO()
            sys.stdout = buf
            try:
                rc = cli.main([
                    "--repo-root", str(repo),
                    "--run-dir", str(run_dir),
                    "merge-flows", "--wave-id", "f1",
                ])
            finally:
                sys.stdout = old_out
            self.assertEqual(rc, 0)
            merge_out = json.loads(buf.getvalue())
            self.assertEqual(merge_out["phase"], "flows")
            self.assertEqual(merge_out["budgetRemaining"], before - 1)
            ledger = json.loads((run_dir / "ledger.json").read_text())
            self.assertEqual(ledger[oid]["state"], "covered")

if __name__ == "__main__":
    unittest.main()
