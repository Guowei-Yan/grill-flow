import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestHops(unittest.TestCase):
    def test_level0_and_neighbour(self):
        from grill_flow_graph import recompute_hops
        nodes = {"file:a": {}, "file:b": {}}
        edges = [{"from": "file:a", "to": "file:b"}]
        recompute_hops(nodes, edges, ["file:a"])
        self.assertEqual(nodes["file:a"]["hop"], 0)
        self.assertEqual(nodes["file:b"]["hop"], 1)

class TestPackMerge(unittest.TestCase):
    def test_pack_selects_unexpanded_within_N(self):
        from grill_flow_graph import selectable_node_ids
        nodes = {
            "file:a": {"expanded": False, "hop": 0},
            "file:b": {"expanded": False, "hop": 1},
            "file:c": {"expanded": True, "hop": 0},
            "file:d": {"expanded": False, "hop": 3},
        }
        self.assertEqual(set(selectable_node_ids(nodes, N=2)), {"file:a", "file:b"})

    def test_pack_does_not_decrement_budget(self):
        from grill_flow_pack import pack_graph_budget_check
        before, after = 6, None
        after = pack_graph_budget_check(budget=before)
        self.assertEqual(after, before)

    def test_merge_decrements_even_with_hard_reject(self):
        from grill_flow_graph import merge_budget_after
        self.assertEqual(merge_budget_after(6, hard_rejects=1, schema_error=False), 5)
        self.assertEqual(merge_budget_after(6, hard_rejects=0, schema_error=True), 6)

    def test_graph_clean_predicate(self):
        from grill_flow_graph import graph_is_clean
        nodes = {"file:a": {"expanded": True, "hop": 0}}
        self.assertTrue(graph_is_clean(nodes, hard_rejects=[], N=2))
        nodes["file:b"] = {"expanded": False, "hop": 1}
        self.assertFalse(graph_is_clean(nodes, hard_rejects=[], N=2))

class TestGraphCliRules(unittest.TestCase):
    def test_pack_requires_active_phase(self):
        from grill_flow_graph import assert_pack_allowed
        with self.assertRaises(SystemExit):
            assert_pack_allowed(phase="not_started")
        with self.assertRaises(SystemExit):
            assert_pack_allowed(phase="clean")
        assert_pack_allowed(phase="active")

    def test_pack_caps(self):
        from grill_flow_graph import chunk_nodes
        ids = [f"file:{i}" for i in range(20)]
        packets = chunk_nodes(ids, packet_size_files=8, validator_slots=2)
        self.assertEqual(len(packets), 2)
        self.assertTrue(all(len(p) <= 8 for p in packets))

    def test_packet_id_congruence_schema_error(self):
        from grill_flow_pack import check_packet_id_congruence
        with self.assertRaises(SystemExit):
            check_packet_id_congruence(cli_id="g1-p0", body_id="other")

    def test_exclusive_lock_flag(self):
        from grill_flow_graph import PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK
        self.assertTrue(PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK)

    def test_failed_wave_no_decrement(self):
        from grill_flow_graph import merge_budget_after
        self.assertEqual(merge_budget_after(6, hard_rejects=0, schema_error=False, failed_wave=True), 6)

class TestGraphMergeRules(unittest.TestCase):
    def test_unparseable_inbox_schema_error(self):
        from grill_flow_pack import load_inbox_packet
        with self.assertRaises(SystemExit) as cm:
            load_inbox_packet("{not json")

    def test_wrong_shape_schema_error(self):
        from grill_flow_pack import validate_graph_map_packet
        with self.assertRaises(SystemExit):
            validate_graph_map_packet({"packetId": "g1", "kind": "wrong"})

    def test_merge_marks_expanded(self):
        from grill_flow_graph import apply_merge_expanded
        nodes = {"file:a": {"expanded": False, "hop": 0}}
        apply_merge_expanded(nodes, ["file:a"])
        self.assertTrue(nodes["file:a"]["expanded"])

    def test_drop_hop_gt_n_and_unreachable(self):
        from grill_flow_graph import drop_out_of_scope
        nodes = {"file:a": {"hop": 0}, "file:b": {"hop": 3}, "file:c": {"hop": None}}
        edges = [{"from": "file:a", "to": "file:b"}, {"from": "file:a", "to": "file:c"}]
        nodes2, edges2 = drop_out_of_scope(nodes, edges, N=2, level0=["file:a"])
        self.assertNotIn("file:b", nodes2)
        self.assertNotIn("file:c", nodes2)

    def test_hard_reject_exit_zero_flag(self):
        from grill_flow_graph import HARD_REJECT_KEEPS_PROCESS_ZERO
        self.assertTrue(HARD_REJECT_KEEPS_PROCESS_ZERO)

    def test_no_pack_validate_command(self):
        from grill_flow_graph import HAS_PACK_VALIDATE_COMMAND
        self.assertFalse(HAS_PACK_VALIDATE_COMMAND)

    def test_missing_component_hard_reject(self):
        from grill_flow_graph import collect_hard_rejects_from_edges
        nodes = {"file:a": {"hop": 0}}
        edges = [{"from": "file:a", "to": "file:missing", "edgeKind": "import"}]
        hrs = collect_hard_rejects_from_edges(nodes, edges, packet_id="g1-p0")
        self.assertEqual(hrs[0]["componentId"], "file:missing")
        self.assertEqual(hrs[0]["phase"], "graph")

    def test_hard_rejects_clear_on_success(self):
        from grill_flow_graph import clear_hard_rejects_for_components
        hrs = [{"phase": "graph", "componentId": "file:missing", "kind": "missing_component"}]
        left = clear_hard_rejects_for_components(hrs, {"file:missing"})
        self.assertEqual(left, [])

if __name__ == "__main__":
    unittest.main()
