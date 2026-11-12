import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestDriftLockAndShape(unittest.TestCase):
    def test_exclusive_lock_flag(self):
        from grill_flow_drift import CHECK_SURFACE_REQUIRES_EXCLUSIVE_LOCK
        self.assertTrue(CHECK_SURFACE_REQUIRES_EXCLUSIVE_LOCK)

    def test_c7_shape(self):
        from grill_flow_drift import build_c7_stdout
        out = build_c7_stdout(
            changed=True,
            surface_hash_before="aaa",
            surface_hash_after="bbb",
            dropped_edges=[{"from": "file:a.py", "to": "file:b.py", "edgeKind": "import", "reason": "endpoint_hop_gt_N"}],
            revoked_obligations=[{
                "obligationId": "file:src/a.py:10:abcd1234",
                "reason": "consumer_missing_from_graph",
                "componentId": "file:gone.py",
            }],
            run_status="in_progress",
            graph_phase="active",
            flows_phase="active",
        )
        for key in (
            "changed", "surfaceHashBefore", "surfaceHashAfter", "droppedEdges",
            "revokedObligations", "runStatus", "graphPhase", "flowsPhase",
        ):
            self.assertIn(key, out)
        self.assertTrue(out["changed"])

    def test_c11_inputs(self):
        from grill_flow_surface import build_c11_hash_object, build_file_set_surface
        surface = build_file_set_surface(targets=["a.py"])
        obj = build_c11_hash_object(surface, obligation_ids=["z", "a"], path_notes=[])
        self.assertEqual(
            set(obj.keys()),
            {
                "mode", "targets", "baseOid", "headOid", "dirty",
                "testExclude", "skip", "obligationIds", "pathNotesDigests",
            },
        )
        self.assertEqual(obj["obligationIds"], ["a", "z"])

    def test_embed_exceptions_list(self):
        from grill_flow_drift import EMBED_EXCEPTIONS
        self.assertEqual(EMBED_EXCEPTIONS, frozenset({"init-surface", "serve-start", "serve-stop"}))
        self.assertFalse(("init-run" in EMBED_EXCEPTIONS))

class TestDriftBehaviours(unittest.TestCase):
    def test_demote_complete_to_in_progress(self):
        from grill_flow_drift import demote_complete_on_drift
        doc = {"runStatus": "complete"}
        demote_complete_on_drift(doc)
        self.assertEqual(doc["runStatus"], "in_progress")
        doc2 = {"runStatus": "in_progress"}
        demote_complete_on_drift(doc2)
        self.assertEqual(doc2["runStatus"], "in_progress")

    def test_consumer_missing_revoke(self):
        from grill_flow_drift import revoke_missing_consumers
        ledger = {
            "oid:1": {
                "state": "covered",
                "kind": "semantic",
                "disposition": {
                    "obligationId": "oid:1",
                    "kind": "semantic",
                    "consumers": ["file:gone.py"],
                },
            },
            "oid:2": {
                "state": "covered",
                "kind": "semantic",
                "disposition": {
                    "obligationId": "oid:2",
                    "kind": "semantic",
                    "consumers": ["file:keep.py"],
                },
            },
        }
        revoked = revoke_missing_consumers(ledger, {"file:keep.py": {}})
        self.assertEqual(len(revoked), 1)
        self.assertEqual(revoked[0]["obligationId"], "oid:1")
        self.assertEqual(revoked[0]["reason"], "consumer_missing_from_graph")
        self.assertEqual(ledger["oid:1"]["state"], "uncovered")
        self.assertEqual(ledger["oid:2"]["state"], "covered")

    def test_graph_clean_to_active(self):
        from grill_flow_drift import apply_graph_phase_after_drift
        doc = {"graph": {"phase": "clean"}, "gate": {"N": 2}, "hardRejects": []}
        graph = {"nodes": {"file:a": {"expanded": False, "hop": 0}}, "edges": []}
        apply_graph_phase_after_drift(doc, graph)
        self.assertEqual(doc["graph"]["phase"], "active")

    def test_flows_clean_to_active(self):
        from grill_flow_drift import apply_flows_phase_after_drift
        doc = {"flows": {"phase": "clean"}}
        apply_flows_phase_after_drift(doc, revoked_count=1)
        self.assertEqual(doc["flows"]["phase"], "active")
        doc2 = {"flows": {"phase": "clean"}}
        apply_flows_phase_after_drift(doc2, revoked_count=0)
        self.assertEqual(doc2["flows"]["phase"], "clean")

    def test_hop_recompute(self):
        from grill_flow_drift import maintain_hops_after_drift
        nodes = {"file:a": {"hop": 0, "expanded": True}, "file:b": {"hop": None, "expanded": False}}
        edges = [{"from": "file:a", "to": "file:b", "edgeKind": "import"}]
        nodes2, edges2, dropped = maintain_hops_after_drift(nodes, edges, N=2, level0=["file:a"])
        self.assertEqual(nodes2["file:b"]["hop"], 1)
        self.assertEqual(dropped, [])

    def test_drop_hop_gt_n(self):
        from grill_flow_drift import maintain_hops_after_drift
        nodes = {
            "file:a": {"hop": 0, "expanded": True},
            "file:b": {"hop": 1, "expanded": True},
            "file:c": {"hop": 5, "expanded": True},
        }
        edges = [
            {"from": "file:a", "to": "file:b", "edgeKind": "import"},
            {"from": "file:b", "to": "file:c", "edgeKind": "import"},
        ]
        nodes2, edges2, dropped = maintain_hops_after_drift(
            nodes, edges, N=1, level0=["file:a"]
        )
        self.assertNotIn("file:c", nodes2)
        self.assertTrue(any(d.get("reason") == "endpoint_hop_gt_N" for d in dropped))

    def test_drop_unreachable_non_l0(self):
        from grill_flow_drift import maintain_hops_after_drift
        nodes = {
            "file:a": {"hop": 0, "expanded": True},
            "file:orphan": {"hop": None, "expanded": False},
        }
        edges = [{"from": "file:orphan", "to": "file:a", "edgeKind": "import"}]
        nodes2, edges2, dropped = maintain_hops_after_drift(
            nodes, edges, N=2, level0=["file:a"]
        )
        self.assertNotIn("file:orphan", nodes2)
        self.assertTrue(any(d.get("reason") == "unreachable_non_l0" for d in dropped))

class TestDriftCli(unittest.TestCase):
    def _load_cli(self):
        import importlib.util
        path = Path(__file__).resolve().parent / "grill-flow.py"
        spec = importlib.util.spec_from_file_location("grill_flow_cli_drift", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def _seed(self, run_dir: Path, repo: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (repo / "src").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "a.py").write_text("x = 1\n")
        from grill_flow_hash import content_hash8, surface_hash
        from grill_flow_surface import build_c11_hash_object, build_file_set_surface
        surface = build_file_set_surface(targets=["src/a.py"])
        (run_dir / "surface.json").write_text(json.dumps(surface, indent=2) + "\n")
        oid = f"file:src/a.py:1:{content_hash8('x = 1')}"
        obligations = [{
            "obligationId": oid,
            "kind": "semantic",
            "path": "src/a.py",
            "change": "present",
        }]
        path_notes = []
        hash_obj = build_c11_hash_object(
            surface,
            obligation_ids=[o["obligationId"] for o in obligations],
            path_notes=path_notes,
        )
        digest = surface_hash(hash_obj)
        (run_dir / "surface-hash.txt").write_text(digest + "\n")
        (run_dir / "obligations.json").write_text(json.dumps(obligations) + "\n")
        (run_dir / "pathNotes.json").write_text("[]\n")
        (run_dir / "ledger.json").write_text(json.dumps({
            oid: {
                "state": "covered",
                "kind": "semantic",
                "disposition": {
                    "obligationId": oid,
                    "kind": "semantic",
                    "consumers": ["file:gone.py"],
                },
            }
        }) + "\n")
        (run_dir / "graph.json").write_text(json.dumps({
            "nodes": {
                "file:src/a.py": {"hop": 0, "expanded": False, "path": "src/a.py"},
                "file:deep.py": {"hop": 9, "expanded": True},
                "file:orphan.py": {"hop": None, "expanded": False},
            },
            "edges": [
                {"from": "file:src/a.py", "to": "file:deep.py", "edgeKind": "import"},
                {"from": "file:orphan.py", "to": "file:src/a.py", "edgeKind": "import"},
            ],
        }) + "\n")
        (run_dir / "run.json").write_text(json.dumps({
            "runId": run_dir.name,
            "runKind": "normal",
            "runStatus": "complete",
            "gate": {
                "N": 0,
                "graphBudget": 0,
                "lineBudget": 0,
                "packetSizeObligations": 40,
                "packetSizeFiles": 8,
                "validatorSlots": 8,
                "models": "n/a",
            },
            "graph": {"phase": "clean"},
            "flows": {"phase": "clean"},
            "graphPartial": False,
            "hardRejects": [],
        }) + "\n")
        self._oid = oid
        self._real_digest = digest

    def test_check_surface_cli_applies_drift(self):
        import io
        cli = self._load_cli()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            run_dir = Path(td) / "rid"
            self._seed(run_dir, repo)
            (run_dir / "surface-hash.txt").write_text("0" * 64 + "\n")
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                rc = cli.main([
                    "--repo-root", str(repo),
                    "--run-dir", str(run_dir),
                    "check-surface",
                ])
            finally:
                sys.stdout = old
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertTrue(out["changed"])
            self.assertEqual(out["runStatus"], "in_progress")
            self.assertEqual(out["graphPhase"], "active")
            self.assertEqual(out["flowsPhase"], "active")
            self.assertTrue(any(
                r.get("reason") == "consumer_missing_from_graph"
                for r in out["revokedObligations"]
            ))
            doc = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(doc["runStatus"], "in_progress")
            graph = json.loads((run_dir / "graph.json").read_text())
            self.assertNotIn("file:deep.py", graph["nodes"])
            self.assertNotIn("file:orphan.py", graph["nodes"])

if __name__ == "__main__":
    unittest.main()
