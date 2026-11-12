import json
from pathlib import Path
from grill_flow_flows import consumer_component_ids
from grill_flow_graph import drop_out_of_scope, level0_ids_from_nodes, recompute_hops
from grill_flow_hash import surface_hash
from grill_flow_inventory import inventory_file_set, inventory_git_diff
from grill_flow_state import (
    flows_clean_predicate,
    graph_clean_predicate,
    load_graph,
    load_ledger,
    load_run,
    save_ledger,
    save_run,
)
from grill_flow_surface import (
    build_c11_hash_object,
    load_surface,
    write_surface_hash,
)

CHECK_SURFACE_REQUIRES_EXCLUSIVE_LOCK = True
EMBED_EXCEPTIONS = frozenset({"init-surface", "serve-start", "serve-stop"})

def should_embed_drift(cmd: str) -> bool:
    if cmd in EMBED_EXCEPTIONS or cmd in ("init-run", "check-surface", "status", "recommend-gate", "serve-stop"):
        return False
    return True

def build_c7_stdout(
    *,
    changed: bool,
    surface_hash_before: str,
    surface_hash_after: str,
    dropped_edges: list,
    revoked_obligations: list,
    run_status: str,
    graph_phase,
    flows_phase,
) -> dict:
    return {
        "changed": bool(changed),
        "surfaceHashBefore": surface_hash_before,
        "surfaceHashAfter": surface_hash_after,
        "droppedEdges": list(dropped_edges),
        "revokedObligations": list(revoked_obligations),
        "runStatus": run_status,
        "graphPhase": graph_phase,
        "flowsPhase": flows_phase,
    }

def demote_complete_on_drift(doc: dict) -> None:
    if doc.get("runStatus") == "complete":
        doc["runStatus"] = "in_progress"

def revoke_missing_consumers(ledger: dict, graph_nodes: dict) -> list:
    revoked = []
    for oid, entry in list(ledger.items()):
        if entry.get("state") != "covered":
            continue
        kind = entry.get("kind") or (entry.get("disposition") or {}).get("kind")
        if kind != "semantic":
            continue
        disp = entry.get("disposition") or {}
        for cid in consumer_component_ids(disp):
            if cid not in graph_nodes:
                new_entry = {"state": "uncovered"}
                if entry.get("kind") is not None:
                    new_entry["kind"] = entry.get("kind")
                ledger[oid] = new_entry
                revoked.append({
                    "obligationId": oid,
                    "reason": "consumer_missing_from_graph",
                    "componentId": cid,
                })
                break
    return revoked

def apply_graph_phase_after_drift(doc: dict, graph: dict) -> None:
    if (doc.get("graph") or {}).get("phase") != "clean":
        return
    if not graph_clean_predicate(doc, graph):
        doc["graph"] = dict(doc.get("graph") or {}, phase="active")

def apply_flows_phase_after_drift(doc: dict, *, revoked_count: int) -> None:
    if (doc.get("flows") or {}).get("phase") != "clean":
        return
    if revoked_count > 0:
        doc["flows"] = dict(doc.get("flows") or {}, phase="active")

def _edge_drop_record(e: dict, reason: str) -> dict:
    return {
        "from": e.get("from"),
        "to": e.get("to"),
        "edgeKind": e.get("edgeKind"),
        "reason": reason,
    }

def maintain_hops_after_drift(
    nodes: dict, edges: list, *, N: int, level0: list
) -> tuple:
    nodes = {k: dict(v) for k, v in nodes.items()}
    edges = [dict(e) for e in edges]
    recompute_hops(nodes, edges, level0)
    before_nodes = set(nodes.keys())
    before_edges = {(e.get("from"), e.get("to"), e.get("edgeKind")): dict(e) for e in edges}
    hop_gt = {
        nid for nid, n in nodes.items()
        if nid not in level0 and n.get("hop") is not None and n["hop"] > N
    }
    unreachable = {
        nid for nid, n in nodes.items()
        if nid not in level0 and n.get("hop") is None
    }
    nodes2, edges2 = drop_out_of_scope(nodes, edges, N=N, level0=level0)
    dropped = []
    for key, e in before_edges.items():
        if key not in {(x.get("from"), x.get("to"), x.get("edgeKind")) for x in edges2}:
            fr, to, _ = key
            reason = "endpoint_hop_gt_N"
            if fr in unreachable or to in unreachable:
                reason = "unreachable_non_l0"
            elif fr in hop_gt or to in hop_gt:
                reason = "endpoint_hop_gt_N"
            elif fr not in nodes2 or to not in nodes2:
                if fr in unreachable or to in unreachable or fr not in before_nodes:
                    reason = "unreachable_non_l0"
            dropped.append(_edge_drop_record(e, reason))
    return nodes2, edges2, dropped

def read_stored_surface_hash(run_dir: Path) -> str:
    p = run_dir / "surface-hash.txt"
    if not p.is_file():
        return ""
    return p.read_text().strip()

def _reinventory(repo_root: Path, surface: dict) -> dict:
    if surface.get("mode") == "file-set":
        return inventory_file_set(repo_root, surface.get("targets") or [])
    return inventory_git_diff(
        repo_root,
        base=surface["baseOid"],
        head=surface["headOid"],
        dirty=bool(surface.get("dirty")),
        test_exclude=surface.get("testExclude"),
        skip=surface.get("skip"),
    )

def sync_ledger_with_obligations(ledger: dict, obligations: list) -> dict:
    ids = {o["obligationId"] for o in obligations}
    synced = {oid: entry for oid, entry in ledger.items() if oid in ids}
    for o in obligations:
        oid = o["obligationId"]
        if oid not in synced:
            synced[oid] = {"state": "uncovered", "kind": o.get("kind", "semantic")}
    return synced

def apply_surface_drift(run_dir: Path, repo_root: Path) -> dict:
    surface = load_surface(run_dir)
    before = read_stored_surface_hash(run_dir)
    inv = _reinventory(repo_root, surface)
    obligations = inv["obligations"]
    path_notes = inv["pathNotes"]
    hash_obj = build_c11_hash_object(
        surface,
        obligation_ids=[o["obligationId"] for o in obligations],
        path_notes=path_notes,
    )
    after = surface_hash(hash_obj)
    doc = load_run(run_dir)
    graph = load_graph(run_dir)
    nodes = dict(graph.get("nodes") or {})
    edges = list(graph.get("edges") or [])
    ledger = load_ledger(run_dir)
    if before == after:
        return build_c7_stdout(
            changed=False,
            surface_hash_before=before,
            surface_hash_after=after,
            dropped_edges=[],
            revoked_obligations=[],
            run_status=doc.get("runStatus"),
            graph_phase=(doc.get("graph") or {}).get("phase"),
            flows_phase=(doc.get("flows") or {}).get("phase"),
        )
    (run_dir / "obligations.json").write_text(
        json.dumps(obligations, indent=2, sort_keys=True) + "\n"
    )
    (run_dir / "pathNotes.json").write_text(
        json.dumps(path_notes, indent=2, sort_keys=True) + "\n"
    )
    ledger = sync_ledger_with_obligations(ledger, obligations)
    gate = doc.get("gate") or {}
    n = int(gate.get("N") or 0)
    level0 = level0_ids_from_nodes(nodes)
    if not level0:
        level0 = [nid for nid, n in nodes.items() if n.get("hop") == 0]
    nodes, edges, dropped = maintain_hops_after_drift(nodes, edges, N=n, level0=level0)
    revoked = revoke_missing_consumers(ledger, nodes)
    graph = {"nodes": nodes, "edges": edges}
    (run_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n"
    )
    apply_graph_phase_after_drift(doc, graph)
    apply_flows_phase_after_drift(doc, revoked_count=len(revoked))
    if not flows_clean_predicate(doc, ledger) and (doc.get("flows") or {}).get("phase") == "clean":
        doc["flows"] = dict(doc.get("flows") or {}, phase="active")
    demote_complete_on_drift(doc)
    save_ledger(run_dir, ledger)
    save_run(run_dir, doc)
    write_surface_hash(run_dir, hash_obj)
    doc = load_run(run_dir)
    return build_c7_stdout(
        changed=True,
        surface_hash_before=before,
        surface_hash_after=after,
        dropped_edges=dropped,
        revoked_obligations=revoked,
        run_status=doc.get("runStatus"),
        graph_phase=(doc.get("graph") or {}).get("phase"),
        flows_phase=(doc.get("flows") or {}).get("phase"),
    )
