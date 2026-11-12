from grill_flow_errors import die

PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK = True
HAS_PACK_VALIDATE_COMMAND = False
flows_merge_sets_run_complete = False
FLOW_PATH_MIN_SEMANTIC = 8
FLOW_SINGLETON_RATE_MAX = 0.40
C10_FLOWS_WAVE_STEPS = (
    "pack-flows",
    "inbox-put",
    "pack-flows --validate",
    "inbox-put",
    "merge-flows",
)

def assert_flows_pack_allowed(*, phase: str) -> None:
    if phase != "active":
        die("invalid_args", f"pack/merge requires flows.phase=active, got {phase}")

def logic_fingerprint(logic) -> str:
    if not isinstance(logic, list):
        return ""
    parts = []
    for item in logic:
        s = str(item).strip()
        if s:
            parts.append(s)
    return "\n".join(parts)

def path_by_obligation(obligations: list, ledger: dict) -> dict:
    out = {}
    for ob in obligations or []:
        oid = ob.get("obligationId")
        if oid and ob.get("path") is not None:
            out[oid] = ob.get("path")
    for oid, entry in (ledger or {}).items():
        if oid in out and out[oid]:
            continue
        d = (entry or {}).get("disposition") or {}
        er = d.get("evidenceRef") or {}
        if er.get("path") is not None:
            out[oid] = er.get("path")
    return out

def semantic_flow_stats(ledger: dict, path_by_oid: dict) -> dict:
    """Covered-semantic flow groups by path; empty logic → per-id group."""
    by_path = {}
    for oid, entry in (ledger or {}).items():
        if not entry or entry.get("state") != "covered":
            continue
        d = entry.get("disposition") or {}
        if d.get("kind") != "semantic":
            continue
        path = path_by_oid.get(oid)
        if path is None:
            path = ""
        fp = logic_fingerprint(d.get("logic") or [])
        gkey = ("id", oid) if not fp else ("fp", fp)
        bucket = by_path.setdefault(path, {})
        bucket.setdefault(gkey, []).append(oid)

    path_stats = {}
    semantic_count = 0
    group_count = 0
    singleton_groups = 0
    violating_paths = []
    for path, groups in sorted(by_path.items()):
        sizes = [len(members) for members in groups.values()]
        sc = sum(sizes)
        gc = len(sizes)
        sg = sum(1 for n in sizes if n == 1)
        rate = (sg / gc) if gc else 0.0
        path_stats[path] = {
            "semanticCount": sc,
            "groupCount": gc,
            "singletonGroups": sg,
            "singletonRate": rate,
        }
        semantic_count += sc
        group_count += gc
        singleton_groups += sg
        if sc >= FLOW_PATH_MIN_SEMANTIC and rate > FLOW_SINGLETON_RATE_MAX:
            violating_paths.append(path)

    return {
        "semanticCount": semantic_count,
        "groupCount": group_count,
        "singletonGroups": singleton_groups,
        "singletonRate": (singleton_groups / group_count) if group_count else 0.0,
        "byPath": path_stats,
        "violatingPaths": violating_paths,
    }

def assert_flow_granularity(ledger: dict, path_by_oid: dict) -> None:
    stats = semantic_flow_stats(ledger, path_by_oid)
    bad = stats.get("violatingPaths") or []
    if not bad:
        return
    sample = ", ".join(bad[:5])
    more = "" if len(bad) <= 5 else f" (+{len(bad) - 5} more)"
    die(
        "quality_error",
        "line-scoped semantic flows "
        f"(singletonRate>{FLOW_SINGLETON_RATE_MAX} on path with "
        f">={FLOW_PATH_MIN_SEMANTIC} semantic): {sample}{more}",
    )

def partition_ledger(ledger: dict) -> dict:
    parts = {"uncovered": [], "covered": [], "waived": []}
    for oid, entry in sorted(ledger.items()):
        state = entry.get("state")
        if state in parts:
            parts[state].append(oid)
    return parts

def selectable_obligation_ids(ledger: dict) -> list:
    return sorted(
        oid for oid, entry in ledger.items() if entry.get("state") == "uncovered"
    )

def chunk_obligations(
    obligation_ids: list, *, packet_size_obligations: int, validator_slots: int
) -> list:
    chunks = []
    for i in range(0, len(obligation_ids), packet_size_obligations):
        chunks.append(obligation_ids[i:i + packet_size_obligations])
        if len(chunks) >= validator_slots:
            break
    return chunks

def pack_flows_budget_check(budget: int) -> int:
    return budget

def validate_c3_map_shape(obj: dict) -> dict:
    if obj.get("kind") != "flows-map" or "dispositions" not in obj:
        die("schema_error", "wrong top-level shape")
    return obj

def validate_c4_validate_shape(obj: dict) -> dict:
    if obj.get("kind") != "flows-validate" or "decisions" not in obj:
        die("schema_error", "wrong top-level shape")
    return obj

def consumer_component_ids(disposition: dict) -> list:
    ids = []
    for c in disposition.get("consumers") or []:
        if isinstance(c, str):
            ids.append(c)
    return ids

def collect_hard_rejects_from_dispositions(
    dispositions: list, graph_nodes: dict, *, packet_id: str
) -> list:
    hrs = []
    for d in dispositions:
        oid = d.get("obligationId")
        for cid in consumer_component_ids(d):
            if cid not in graph_nodes:
                hrs.append({
                    "phase": "flows",
                    "kind": "missing_component",
                    "obligationId": oid,
                    "componentId": cid,
                    "packetId": packet_id,
                })
    return hrs

def apply_map_dispositions(ledger: dict, dispositions: list) -> dict:
    for d in dispositions:
        oid = d.get("obligationId")
        if not oid:
            continue
        entry = dict(ledger.get(oid) or {})
        entry["state"] = "covered"
        entry["kind"] = d.get("kind", entry.get("kind"))
        entry["disposition"] = dict(d)
        ledger[oid] = entry
    return ledger

def apply_validate_flow_decisions(ledger: dict, decisions: list) -> dict:
    for d in decisions:
        oid = d.get("obligationId")
        if not oid:
            continue
        decision = d.get("decision")
        if decision == "reject":
            entry = dict(ledger.get(oid) or {})
            kind = entry.get("kind")
            ledger[oid] = {"state": "uncovered"}
            if kind is not None:
                ledger[oid]["kind"] = kind
        elif decision == "reclassifyTo":
            disp = dict(d.get("disposition") or {})
            entry = dict(ledger.get(oid) or {})
            entry["state"] = "covered"
            entry["kind"] = disp.get("kind", entry.get("kind"))
            entry["disposition"] = disp
            ledger[oid] = entry
        elif decision == "confirm":
            entry = dict(ledger.get(oid) or {})
            if entry.get("state") != "covered":
                entry["state"] = "covered"
            ledger[oid] = entry
    return ledger

def clear_flows_hard_rejects(hard_rejects: list, present_ids) -> list:
    return [h for h in hard_rejects if h.get("componentId") not in present_ids]

def flows_is_clean(ledger: dict, hard_rejects: list, flows_phase: str) -> bool:
    if flows_phase == "accepted_partial":
        return False
    if hard_rejects:
        return False
    for entry in ledger.values():
        if entry.get("state") == "uncovered":
            return False
    return True

def build_flows_pack_stdout(
    *, wave_id: str, mode: str, budget_remaining: int, packets: list
) -> dict:
    return {
        "waveId": wave_id,
        "phase": "flows",
        "mode": mode,
        "budgetRemaining": budget_remaining,
        "packets": packets,
    }

def build_flows_merge_stdout(
    *,
    wave_id: str,
    merged_packet_ids: list,
    budget_remaining: int,
    hard_rejects_added: list,
    dropped_edges: list,
    graph_clean: bool,
    flows_clean: bool,
) -> dict:
    return {
        "waveId": wave_id,
        "phase": "flows",
        "mergedPacketIds": merged_packet_ids,
        "budgetRemaining": budget_remaining,
        "hardRejectsAdded": hard_rejects_added,
        "droppedEdges": dropped_edges,
        "graphClean": graph_clean,
        "flowsClean": flows_clean,
    }

def build_flows_map_brief(
    *,
    packet_id: str,
    wave_id: str,
    assigned_obligation_ids: list,
    repo_root: str,
    run_dir: str,
) -> dict:
    return {
        "packetId": packet_id,
        "kind": "flows-map-brief",
        "waveId": wave_id,
        "assignedObligationIds": list(assigned_obligation_ids),
        "repoRoot": repo_root,
        "runDir": run_dir,
    }

def build_flows_validate_brief(
    *,
    packet_id: str,
    wave_id: str,
    assigned_obligation_ids: list,
    map_packet_id: str,
    repo_root: str,
    run_dir: str,
) -> dict:
    return {
        "packetId": packet_id,
        "kind": "flows-validate-brief",
        "waveId": wave_id,
        "assignedObligationIds": list(assigned_obligation_ids),
        "mapPacketId": map_packet_id,
        "mapReturnPath": f"packets/inbox/{map_packet_id}.json",
        "repoRoot": repo_root,
        "runDir": run_dir,
    }
