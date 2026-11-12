#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grill_flow_errors import die
from grill_flow_inventory import (
    classify_run_kind,
    inventory_file_set,
    inventory_git_diff,
    level0_expanded_for,
)
from grill_flow_lock import acquire_exclusive, release_exclusive
from grill_flow_state import (
    ACCEPT_PARTIAL_REQUIRES_EXCLUSIVE_LOCK,
    ABORT_RUN_REQUIRES_EXCLUSIVE_LOCK,
    APPLY_GATE_REQUIRES_EXCLUSIVE_LOCK,
    BEGIN_FLOWS_REQUIRES_EXCLUSIVE_LOCK,
    INIT_RUN_REQUIRES_EXCLUSIVE_LOCK,
    RAISE_BUDGET_REQUIRES_EXCLUSIVE_LOCK,
    RESUME_GRAPH_REQUIRES_EXCLUSIVE_LOCK,
    UNWAIVE_REQUIRES_EXCLUSIVE_LOCK,
    abort_run,
    accept_partial,
    apply_gate,
    apply_graph_clean_predicate,
    apply_init_run_kind,
    assert_mutable_command_allowed,
    begin_flows,
    build_status,
    evaluate_completion,
    init_run_guard,
    initial_ledger_state,
    load_graph,
    load_ledger,
    load_obligations,
    load_run,
    raise_budget,
    recommend_gate,
    resume_graph,
    save_ledger,
    save_run,
    seed_level0_nodes,
    unwaive,
)
from grill_flow_pack import (
    INBOX_CLEAR_REQUIRES_EXCLUSIVE_LOCK,
    INBOX_PUT_REQUIRES_EXCLUSIVE_LOCK,
    inbox_clear,
    inbox_put,
    pack_graph_budget_check,
    read_inbox_file,
    validate_flows_map_packet,
    validate_flows_validate_packet,
    validate_graph_map_packet,
    validate_graph_validate_packet,
)
from grill_flow_graph import (
    PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK,
    apply_merge_expanded,
    apply_validate_decisions,
    assert_pack_allowed,
    chunk_nodes,
    clear_hard_rejects_for_components,
    collect_hard_rejects_from_edges,
    drop_out_of_scope,
    graph_is_clean,
    level0_ids_from_nodes,
    merge_budget_after,
    merge_map_nodes_edges,
    recompute_hops,
    selectable_node_ids,
)
from grill_flow_flows import (
    PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK as FLOWS_PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK,
    apply_map_dispositions,
    apply_validate_flow_decisions,
    assert_flow_granularity,
    assert_flows_pack_allowed,
    build_flows_map_brief,
    build_flows_merge_stdout,
    build_flows_pack_stdout,
    build_flows_validate_brief,
    chunk_obligations,
    clear_flows_hard_rejects,
    collect_hard_rejects_from_dispositions,
    flows_is_clean,
    pack_flows_budget_check,
    path_by_obligation,
    selectable_obligation_ids,
)
from grill_flow_surface import (
    build_c11_hash_object,
    build_file_set_surface,
    build_git_diff_surface,
    load_surface,
    surface_exists,
    write_surface,
    write_surface_hash,
)
from grill_flow_drift import (
    CHECK_SURFACE_REQUIRES_EXCLUSIVE_LOCK,
    apply_surface_drift,
    should_embed_drift,
)
from grill_flow_render import RENDER_REQUIRES_EXCLUSIVE_LOCK, render_run
from grill_flow_serve import (
    SERVE_START_REQUIRES_EXCLUSIVE_LOCK,
    run_serve_http,
    serve_start,
    serve_stop,
)

def build_parser():
    p = argparse.ArgumentParser(prog="grill-flow")
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--run-dir", type=Path, default=None)
    p.add_argument("--force-lock", default=None)
    p.add_argument("--grill-flow-instance", default=None)
    p.add_argument("--read-only", action="store_true", default=False)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p_is = sub.add_parser("init-surface")
    p_is.add_argument("--mode", required=True, choices=["file-set", "git-diff"])
    p_is.add_argument("--target", action="append", default=[])
    p_is.add_argument("--base", default=None)
    p_is.add_argument("--head", default=None)
    p_is.add_argument("--dirty", action="store_true", default=False)
    sub.add_parser("init-run")
    sub.add_parser("recommend-gate")
    p_ag = sub.add_parser("apply-gate")
    p_ag.add_argument("--N", type=int, dest="N", default=None)
    p_ag.add_argument("--graph-budget", type=int, default=None)
    p_ag.add_argument("--line-budget", type=int, default=None)
    p_ag.add_argument("--packet-size-obligations", type=int, default=None)
    p_ag.add_argument("--packet-size-files", type=int, default=None)
    p_ag.add_argument("--validator-slots", type=int, default=None)
    p_ag.add_argument("--models", default=None)
    p_ap = sub.add_parser("accept-partial")
    p_ap.add_argument("--phase", required=True, choices=["graph", "flows"])
    sub.add_parser("begin-flows")
    p_uw = sub.add_parser("unwaive")
    p_uw.add_argument("--obligation-id", action="append", default=None)
    sub.add_parser("resume-graph")
    p_rb = sub.add_parser("raise-budget")
    p_rb.add_argument("--phase", required=True, choices=["graph", "flows"])
    sub.add_parser("abort-run")
    sub.add_parser("check-surface")
    p_ip = sub.add_parser("inbox-put")
    p_ip.add_argument("--packet-id", required=True)
    p_ic = sub.add_parser("inbox-clear")
    p_ic.add_argument("--packet-id", required=True)
    p_pg = sub.add_parser("pack-graph")
    p_pg.add_argument("--wave-id", required=True)
    p_pg.add_argument("--validate", action="store_true", default=False)
    p_mg = sub.add_parser("merge-graph")
    p_mg.add_argument("--wave-id", required=True)
    p_pf = sub.add_parser("pack-flows")
    p_pf.add_argument("--wave-id", required=True)
    p_pf.add_argument("--validate", action="store_true", default=False)
    p_mf = sub.add_parser("merge-flows")
    p_mf.add_argument("--wave-id", required=True)
    sub.add_parser("render")
    p_ss = sub.add_parser("serve-start")
    p_ss.add_argument("--port", type=int, default=0)
    p_ss.add_argument("--bind", default="127.0.0.1")
    sub.add_parser("serve-stop")
    p_sh = sub.add_parser("serve-http")
    p_sh.add_argument("--port", type=int, required=True)
    p_sh.add_argument("--bind", default="127.0.0.1")
    return p

def _require_run_dir(args) -> Path:
    if args.run_dir is None:
        die("invalid_args", f"--run-dir required for {args.cmd}")
    return args.run_dir

def _with_exclusive(args, run_dir: Path, fn):
    acquire_exclusive(run_dir, force_token=args.force_lock)
    try:
        return fn()
    finally:
        release_exclusive(run_dir)

def _embed_drift(args, run_dir: Path) -> None:
    if should_embed_drift(args.cmd):
        apply_surface_drift(run_dir, Path(args.repo_root))

def _cmd_init_surface(args) -> int:
    run_dir = _require_run_dir(args)
    if args.mode == "file-set":
        surface = build_file_set_surface(targets=args.target)
    else:
        if not args.base or not args.head:
            die("invalid_args", "git-diff init-surface requires --base and --head")
        inv = inventory_git_diff(
            args.repo_root, base=args.base, head=args.head, dirty=bool(args.dirty)
        )
        surface = build_git_diff_surface(
            base_oid=inv["baseOid"], head_oid=inv["headOid"], dirty=bool(args.dirty)
        )
    write_surface(run_dir, surface)
    print(json.dumps({"ok": True, "mode": surface["mode"]}))
    return 0

def _seed_graph_nodes(level0: list, obligations: list) -> dict:
    obligation_paths = {o["path"] for o in obligations}
    nodes = {}
    for p in level0:
        if p in obligation_paths:
            expanded = level0_expanded_for(kind="obligation")
        else:
            expanded = level0_expanded_for(kind="empty_or_binary_seed")
        nodes.update(seed_level0_nodes([p], expanded=expanded))
    return nodes

def _cmd_init_run(args) -> int:
    run_dir = _require_run_dir(args)
    init_run_guard(surface_exists=surface_exists(run_dir))
    def body():
        surface = load_surface(run_dir)
        if surface["mode"] == "file-set":
            inv = inventory_file_set(args.repo_root, surface.get("targets") or [])
        else:
            inv = inventory_git_diff(
                args.repo_root,
                base=surface["baseOid"],
                head=surface["headOid"],
                dirty=bool(surface.get("dirty")),
                test_exclude=surface.get("testExclude"),
                skip=surface.get("skip"),
            )
            surface = build_git_diff_surface(
                base_oid=inv["baseOid"],
                head_oid=inv["headOid"],
                dirty=bool(surface.get("dirty")),
                test_exclude=surface.get("testExclude"),
                skip=surface.get("skip"),
            )
            write_surface(run_dir, surface)
        obligations = inv["obligations"]
        path_notes = inv["pathNotes"]
        level0 = inv["level0"]
        run_kind = classify_run_kind(obligations, path_notes, level0)
        outcome = apply_init_run_kind(run_kind)
        nodes = _seed_graph_nodes(level0, obligations)
        ledger = {
            o["obligationId"]: {
                "state": initial_ledger_state(o["obligationId"]),
                "kind": o.get("kind", "semantic"),
            }
            for o in obligations
        }
        hash_obj = build_c11_hash_object(
            surface,
            obligation_ids=[o["obligationId"] for o in obligations],
            path_notes=path_notes,
        )
        write_surface_hash(run_dir, hash_obj)
        (run_dir / "graph.json").write_text(
            json.dumps({"nodes": nodes, "edges": []}, indent=2, sort_keys=True) + "\n"
        )
        (run_dir / "ledger.json").write_text(
            json.dumps(ledger, indent=2, sort_keys=True) + "\n"
        )
        (run_dir / "pathNotes.json").write_text(
            json.dumps(path_notes, indent=2, sort_keys=True) + "\n"
        )
        (run_dir / "obligations.json").write_text(
            json.dumps(obligations, indent=2, sort_keys=True) + "\n"
        )
        run_doc = {
            "runId": run_dir.name,
            "runKind": outcome["runKind"],
            "runStatus": outcome["runStatus"],
            "gate": outcome["gate"],
            "graph": outcome["graph"],
            "flows": outcome["flows"],
            "graphPartial": False,
            "hardRejects": [],
        }
        (run_dir / "run.json").write_text(
            json.dumps(run_doc, indent=2, sort_keys=True) + "\n"
        )
        print(json.dumps({
            "ok": True,
            "runKind": outcome["runKind"],
            "runStatus": outcome["runStatus"],
        }))
        return 0
    if INIT_RUN_REQUIRES_EXCLUSIVE_LOCK:
        return _with_exclusive(args, run_dir, body)
    return body()

def _gate_from_args(args) -> dict:
    gate = {}
    if args.N is not None:
        gate["N"] = args.N
    if args.graph_budget is not None:
        gate["graphBudget"] = args.graph_budget
    if args.line_budget is not None:
        gate["lineBudget"] = args.line_budget
    if args.packet_size_obligations is not None:
        gate["packetSizeObligations"] = args.packet_size_obligations
    if args.packet_size_files is not None:
        gate["packetSizeFiles"] = args.packet_size_files
    if args.validator_slots is not None:
        gate["validatorSlots"] = args.validator_slots
    if args.models is not None:
        gate["models"] = args.models
    return gate

def _manifest_path(run_dir: Path, wave_id: str) -> Path:
    return run_dir / "packets" / "out" / f"{wave_id}-manifest.json"

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def _rel_out(packet_id: str) -> str:
    return f"packets/out/{packet_id}.json"

def _cmd_pack_graph(args, run_dir: Path) -> int:
    doc = load_run(run_dir)
    phase = (doc.get("graph") or {}).get("phase")
    assert_pack_allowed(phase=phase)
    gate = doc.get("gate") or {}
    budget = int(gate.get("graphBudget") or 0)
    if budget == 0:
        die("budget_exhausted", "graphBudget is 0")
    budget_remaining = pack_graph_budget_check(budget)
    n = int(gate.get("N") or 0)
    packet_size_files = int(gate.get("packetSizeFiles") or 8)
    validator_slots = int(gate.get("validatorSlots") or 8)
    wave_id = args.wave_id
    out_dir = run_dir / "packets" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.validate:
        man_path = _manifest_path(run_dir, wave_id)
        if not man_path.is_file():
            die("invalid_args", f"missing manifest for wave {wave_id}")
        manifest = json.loads(man_path.read_text())
        map_ids = list(manifest.get("mapPacketIds") or [])
        validate_ids = []
        packets_out = []
        for mid in map_ids:
            brief_path = out_dir / f"{mid}.json"
            if not brief_path.is_file():
                die("invalid_args", f"missing map brief {mid}")
            brief = json.loads(brief_path.read_text())
            assigned = list(brief.get("assignedNodeIds") or [])
            map_obj = read_inbox_file(run_dir, mid)
            validate_graph_map_packet(map_obj)
            vid = f"{mid}-val"
            vbrief = {
                "packetId": vid,
                "kind": "graph-validate-brief",
                "waveId": wave_id,
                "assignedNodeIds": assigned,
                "mapPacketId": mid,
                "mapReturnPath": f"packets/inbox/{mid}.json",
                "N": n,
                "repoRoot": str(args.repo_root.resolve()),
                "runDir": str(run_dir.resolve()),
            }
            _write_json(out_dir / f"{vid}.json", vbrief)
            validate_ids.append(vid)
            packets_out.append({
                "packetId": vid,
                "assignedNodeIds": assigned,
                "outPath": _rel_out(vid),
            })
        manifest["validatePacketIds"] = validate_ids
        _write_json(man_path, manifest)
        print(json.dumps({
            "waveId": wave_id,
            "phase": "graph",
            "mode": "validate",
            "budgetRemaining": budget_remaining,
            "packets": packets_out,
        }))
        return 0
    graph = load_graph(run_dir)
    nodes = graph.get("nodes") or {}
    selected = selectable_node_ids(nodes, N=n)
    chunks = chunk_nodes(selected, packet_size_files=packet_size_files, validator_slots=validator_slots)
    map_ids = []
    packets_out = []
    for i, chunk in enumerate(chunks):
        pid = f"{wave_id}-p{i}"
        brief = {
            "packetId": pid,
            "kind": "graph-map-brief",
            "waveId": wave_id,
            "assignedNodeIds": list(chunk),
            "N": n,
            "repoRoot": str(args.repo_root.resolve()),
            "runDir": str(run_dir.resolve()),
        }
        _write_json(out_dir / f"{pid}.json", brief)
        map_ids.append(pid)
        packets_out.append({
            "packetId": pid,
            "assignedNodeIds": list(chunk),
            "outPath": _rel_out(pid),
        })
    manifest = {
        "waveId": wave_id,
        "mapPacketIds": map_ids,
        "validatePacketIds": [],
    }
    _write_json(_manifest_path(run_dir, wave_id), manifest)
    print(json.dumps({
        "waveId": wave_id,
        "phase": "graph",
        "mode": "map",
        "budgetRemaining": budget_remaining,
        "packets": packets_out,
    }))
    return 0

def _cmd_merge_graph(args, run_dir: Path) -> int:
    doc = load_run(run_dir)
    phase = (doc.get("graph") or {}).get("phase")
    assert_pack_allowed(phase=phase)
    gate = doc.get("gate") or {}
    n = int(gate.get("N") or 0)
    wave_id = args.wave_id
    man_path = _manifest_path(run_dir, wave_id)
    if not man_path.is_file():
        die("invalid_args", f"missing manifest for wave {wave_id}")
    manifest = json.loads(man_path.read_text())
    map_ids = list(manifest.get("mapPacketIds") or [])
    validate_ids = list(manifest.get("validatePacketIds") or [])
    merged_ids = map_ids + validate_ids
    assigned_all = []
    for mid in map_ids:
        brief_path = run_dir / "packets" / "out" / f"{mid}.json"
        if brief_path.is_file():
            brief = json.loads(brief_path.read_text())
            assigned_all.extend(brief.get("assignedNodeIds") or [])
    graph = load_graph(run_dir)
    nodes = dict(graph.get("nodes") or {})
    edges = list(graph.get("edges") or [])
    level0 = level0_ids_from_nodes(nodes)
    hard_added = []
    for mid in map_ids:
        obj = read_inbox_file(run_dir, mid)
        validate_graph_map_packet(obj)
        nodes, edges = merge_map_nodes_edges(nodes, edges, obj)
        hrs = collect_hard_rejects_from_edges(nodes, edges, packet_id=mid)
        hard_added.extend(hrs)
    for vid in validate_ids:
        obj = read_inbox_file(run_dir, vid)
        validate_graph_validate_packet(obj)
        edges = apply_validate_decisions(edges, obj.get("decisions") or [])
    apply_merge_expanded(nodes, assigned_all)
    recompute_hops(nodes, edges, level0)
    nodes, edges = drop_out_of_scope(nodes, edges, N=n, level0=level0)
    dropped_edges = []
    present = set(nodes.keys())
    existing_hrs = list(doc.get("hardRejects") or [])
    existing_hrs = clear_hard_rejects_for_components(existing_hrs, present)
    non_graph = [h for h in existing_hrs if h.get("phase") != "graph"]
    graph_hrs = [h for h in existing_hrs if h.get("phase") == "graph"]
    graph_hrs = clear_hard_rejects_for_components(graph_hrs, present)
    for h in hard_added:
        if h.get("componentId") not in present:
            graph_hrs.append(h)
    seen = set()
    deduped = []
    for h in graph_hrs:
        key = (h.get("phase"), h.get("kind"), h.get("componentId"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)
    doc["hardRejects"] = non_graph + deduped
    budget_before = int(gate.get("graphBudget") or 0)
    budget_after = merge_budget_after(
        budget_before, hard_rejects=len(hard_added), schema_error=False, failed_wave=False
    )
    gate = dict(gate)
    gate["graphBudget"] = budget_after
    doc["gate"] = gate
    (run_dir / "graph.json").write_text(
        json.dumps({"nodes": nodes, "edges": edges}, indent=2, sort_keys=True) + "\n"
    )
    save_run(run_dir, doc)
    apply_graph_clean_predicate(run_dir)
    doc = load_run(run_dir)
    for pid in merged_ids:
        inbox_clear(run_dir, pid)
    g_clean = graph_is_clean(nodes, [h for h in doc.get("hardRejects") or [] if h.get("phase") == "graph"], n)
    print(json.dumps({
        "waveId": wave_id,
        "phase": "graph",
        "mergedPacketIds": merged_ids,
        "budgetRemaining": budget_after,
        "hardRejectsAdded": hard_added,
        "droppedEdges": dropped_edges,
        "graphClean": g_clean or (doc.get("graph") or {}).get("phase") == "clean",
        "flowsClean": False,
    }))
    return 0

def _cmd_pack_flows(args, run_dir: Path) -> int:
    doc = load_run(run_dir)
    phase = (doc.get("flows") or {}).get("phase")
    assert_flows_pack_allowed(phase=phase)
    gate = doc.get("gate") or {}
    budget = int(gate.get("lineBudget") or 0)
    if budget == 0:
        die("budget_exhausted", "lineBudget is 0")
    budget_remaining = pack_flows_budget_check(budget)
    packet_size_obligations = int(gate.get("packetSizeObligations") or 40)
    validator_slots = int(gate.get("validatorSlots") or 8)
    wave_id = args.wave_id
    out_dir = run_dir / "packets" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.validate:
        man_path = _manifest_path(run_dir, wave_id)
        if not man_path.is_file():
            die("invalid_args", f"missing manifest for wave {wave_id}")
        manifest = json.loads(man_path.read_text())
        map_ids = list(manifest.get("mapPacketIds") or [])
        validate_ids = []
        packets_out = []
        for mid in map_ids:
            brief_path = out_dir / f"{mid}.json"
            if not brief_path.is_file():
                die("invalid_args", f"missing map brief {mid}")
            brief = json.loads(brief_path.read_text())
            assigned = list(brief.get("assignedObligationIds") or [])
            map_obj = read_inbox_file(run_dir, mid)
            validate_flows_map_packet(map_obj)
            vid = f"{mid}-val"
            vbrief = build_flows_validate_brief(
                packet_id=vid,
                wave_id=wave_id,
                assigned_obligation_ids=assigned,
                map_packet_id=mid,
                repo_root=str(args.repo_root.resolve()),
                run_dir=str(run_dir.resolve()),
            )
            _write_json(out_dir / f"{vid}.json", vbrief)
            validate_ids.append(vid)
            packets_out.append({
                "packetId": vid,
                "assignedObligationIds": assigned,
                "outPath": _rel_out(vid),
            })
        manifest["validatePacketIds"] = validate_ids
        _write_json(man_path, manifest)
        print(json.dumps(build_flows_pack_stdout(
            wave_id=wave_id,
            mode="validate",
            budget_remaining=budget_remaining,
            packets=packets_out,
        )))
        return 0
    ledger = load_ledger(run_dir)
    selected = selectable_obligation_ids(ledger)
    chunks = chunk_obligations(
        selected,
        packet_size_obligations=packet_size_obligations,
        validator_slots=validator_slots,
    )
    map_ids = []
    packets_out = []
    for i, chunk in enumerate(chunks):
        pid = f"{wave_id}-p{i}"
        brief = build_flows_map_brief(
            packet_id=pid,
            wave_id=wave_id,
            assigned_obligation_ids=chunk,
            repo_root=str(args.repo_root.resolve()),
            run_dir=str(run_dir.resolve()),
        )
        _write_json(out_dir / f"{pid}.json", brief)
        map_ids.append(pid)
        packets_out.append({
            "packetId": pid,
            "assignedObligationIds": list(chunk),
            "outPath": _rel_out(pid),
        })
    manifest = {
        "waveId": wave_id,
        "mapPacketIds": map_ids,
        "validatePacketIds": [],
    }
    _write_json(_manifest_path(run_dir, wave_id), manifest)
    print(json.dumps(build_flows_pack_stdout(
        wave_id=wave_id,
        mode="map",
        budget_remaining=budget_remaining,
        packets=packets_out,
    )))
    return 0

def _cmd_merge_flows(args, run_dir: Path) -> int:
    doc = load_run(run_dir)
    phase = (doc.get("flows") or {}).get("phase")
    assert_flows_pack_allowed(phase=phase)
    gate = doc.get("gate") or {}
    wave_id = args.wave_id
    man_path = _manifest_path(run_dir, wave_id)
    if not man_path.is_file():
        die("invalid_args", f"missing manifest for wave {wave_id}")
    manifest = json.loads(man_path.read_text())
    map_ids = list(manifest.get("mapPacketIds") or [])
    validate_ids = list(manifest.get("validatePacketIds") or [])
    merged_ids = map_ids + validate_ids
    ledger = load_ledger(run_dir)
    graph = load_graph(run_dir)
    nodes = dict(graph.get("nodes") or {})
    hard_added = []
    for mid in map_ids:
        obj = read_inbox_file(run_dir, mid)
        validate_flows_map_packet(obj)
        dispositions = list(obj.get("dispositions") or [])
        apply_map_dispositions(ledger, dispositions)
        hard_added.extend(collect_hard_rejects_from_dispositions(
            dispositions, nodes, packet_id=mid
        ))
    for vid in validate_ids:
        obj = read_inbox_file(run_dir, vid)
        validate_flows_validate_packet(obj)
        apply_validate_flow_decisions(ledger, obj.get("decisions") or [])
        for d in obj.get("decisions") or []:
            if d.get("decision") == "reclassifyTo":
                disp = d.get("disposition") or {}
                hard_added.extend(collect_hard_rejects_from_dispositions(
                    [disp], nodes, packet_id=vid
                ))
    present = set(nodes.keys())
    existing_hrs = list(doc.get("hardRejects") or [])
    non_flows = [h for h in existing_hrs if h.get("phase") != "flows"]
    flows_hrs = [h for h in existing_hrs if h.get("phase") == "flows"]
    flows_hrs = clear_flows_hard_rejects(flows_hrs, present)
    for h in hard_added:
        if h.get("componentId") not in present:
            flows_hrs.append(h)
    seen = set()
    deduped = []
    for h in flows_hrs:
        key = (h.get("phase"), h.get("kind"), h.get("obligationId"), h.get("componentId"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)
    doc["hardRejects"] = non_flows + deduped
    obligations = load_obligations(run_dir)
    assert_flow_granularity(ledger, path_by_obligation(obligations, ledger))
    budget_before = int(gate.get("lineBudget") or 0)
    budget_after = merge_budget_after(
        budget_before, hard_rejects=len(hard_added), schema_error=False, failed_wave=False
    )
    gate = dict(gate)
    gate["lineBudget"] = budget_after
    doc["gate"] = gate
    save_ledger(run_dir, ledger)
    save_run(run_dir, doc)
    evaluate_completion(run_dir)
    doc = load_run(run_dir)
    for pid in merged_ids:
        inbox_clear(run_dir, pid)
    g_clean = (doc.get("graph") or {}).get("phase") == "clean"
    f_clean = flows_is_clean(
        load_ledger(run_dir),
        [h for h in doc.get("hardRejects") or [] if h.get("phase") == "flows"],
        (doc.get("flows") or {}).get("phase") or "",
    )
    print(json.dumps(build_flows_merge_stdout(
        wave_id=wave_id,
        merged_packet_ids=merged_ids,
        budget_remaining=budget_after,
        hard_rejects_added=hard_added,
        dropped_edges=[],
        graph_clean=g_clean,
        flows_clean=f_clean,
    )))
    return 0

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "status":
        run_dir = _require_run_dir(args)
        print(json.dumps(build_status(run_dir)))
        return 0
    if args.cmd == "recommend-gate":
        run_dir = _require_run_dir(args)
        print(json.dumps(recommend_gate(run_dir)))
        return 0
    if args.cmd == "init-surface":
        return _cmd_init_surface(args)
    if args.cmd == "init-run":
        return _cmd_init_run(args)
    if args.cmd == "apply-gate":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = apply_gate(run_dir, gate=_gate_from_args(args))
            print(json.dumps({"ok": True, "graph": out["graph"], "gate": out["gate"]}))
            return 0
        if APPLY_GATE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "begin-flows":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = begin_flows(run_dir)
            print(json.dumps({"ok": True, "flows": out["flows"], "graphPartial": out.get("graphPartial", False)}))
            return 0
        if BEGIN_FLOWS_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "accept-partial":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = accept_partial(run_dir, phase=args.phase)
            print(json.dumps({"ok": True, "runStatus": out["runStatus"], "graph": out["graph"], "flows": out["flows"]}))
            return 0
        if ACCEPT_PARTIAL_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "resume-graph":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = resume_graph(run_dir)
            print(json.dumps({"ok": True, "graph": out["graph"]}))
            return 0
        if RESUME_GRAPH_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "unwaive":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = unwaive(run_dir, obligation_ids=args.obligation_id)
            print(json.dumps({"ok": True, "runStatus": out["runStatus"], "flows": out["flows"]}))
            return 0
        if UNWAIVE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "raise-budget":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = raise_budget(run_dir, phase=args.phase)
            print(json.dumps({"ok": True, "gate": out["gate"]}))
            return 0
        if RAISE_BUDGET_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "abort-run":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            out = abort_run(run_dir)
            print(json.dumps({"ok": True, "runStatus": out["runStatus"]}))
            return 0
        if ABORT_RUN_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "inbox-put":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            assert_mutable_command_allowed(run_dir, "inbox-put")
            try:
                payload = json.loads(sys.stdin.read())
            except json.JSONDecodeError:
                die("schema_error", "unparseable inbox body")
            if not isinstance(payload, dict):
                die("schema_error", "inbox body must be a JSON object")
            out = inbox_put(run_dir, args.packet_id, payload)
            print(json.dumps(out))
            return 0
        if INBOX_PUT_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "inbox-clear":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            assert_mutable_command_allowed(run_dir, "inbox-clear")
            out = inbox_clear(run_dir, args.packet_id)
            print(json.dumps(out))
            return 0
        if INBOX_CLEAR_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "pack-graph":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            assert_mutable_command_allowed(run_dir, "pack-graph")
            return _cmd_pack_graph(args, run_dir)
        if PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "merge-graph":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            assert_mutable_command_allowed(run_dir, "merge-graph")
            return _cmd_merge_graph(args, run_dir)
        if PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "pack-flows":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            assert_mutable_command_allowed(run_dir, "pack-flows")
            return _cmd_pack_flows(args, run_dir)
        if FLOWS_PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "merge-flows":
        run_dir = _require_run_dir(args)
        def body():
            _embed_drift(args, run_dir)
            assert_mutable_command_allowed(run_dir, "merge-flows")
            return _cmd_merge_flows(args, run_dir)
        if FLOWS_PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "check-surface":
        run_dir = _require_run_dir(args)
        def body():
            assert_mutable_command_allowed(run_dir, "check-surface")
            out = apply_surface_drift(run_dir, Path(args.repo_root))
            print(json.dumps(out))
            return 0
        if CHECK_SURFACE_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "render":
        run_dir = _require_run_dir(args)
        helper = Path(__file__).resolve()
        def body():
            _embed_drift(args, run_dir)
            out = render_run(
                run_dir, helper, repo_root=Path(args.repo_root).resolve()
            )
            print(json.dumps(out))
            return 0
        if RENDER_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "serve-start":
        run_dir = _require_run_dir(args)
        helper = Path(__file__).resolve()
        def body():
            out = serve_start(
                run_dir,
                helper,
                repo_root=Path(args.repo_root),
                port=args.port if args.port else None,
                bind=str(args.bind),
            )
            print(json.dumps(out))
            return 0
        if SERVE_START_REQUIRES_EXCLUSIVE_LOCK:
            return _with_exclusive(args, run_dir, body)
        return body()
    if args.cmd == "serve-stop":
        run_dir = _require_run_dir(args)
        out = serve_stop(run_dir)
        print(json.dumps(out))
        return 0
    if args.cmd == "serve-http":
        run_dir = _require_run_dir(args)
        if not args.grill_flow_instance:
            die("invalid_args", "serve-http requires --grill-flow-instance")
        run_serve_http(
            run_dir,
            port=int(args.port),
            repo_root=Path(args.repo_root).resolve(),
            instance_id=str(args.grill_flow_instance),
            read_only=bool(args.read_only),
            bind=str(args.bind),
        )
        return 0
    die("invalid_args", f"unsupported cmd {args.cmd}")

if __name__ == "__main__":
    raise SystemExit(main())
