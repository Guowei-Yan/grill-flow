from collections import deque
from grill_flow_errors import die

PACK_MERGE_REQUIRES_EXCLUSIVE_LOCK = True
HARD_REJECT_KEEPS_PROCESS_ZERO = True
HAS_PACK_VALIDATE_COMMAND = False

def recompute_hops(nodes: dict, edges: list, level0_ids: list) -> dict:
    adj = {}
    for e in edges:
        adj.setdefault(e["from"], []).append(e["to"])
    hop = {nid: None for nid in nodes}
    q = deque()
    for lid in level0_ids:
        if lid in hop:
            hop[lid] = 0
            q.append(lid)
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            if hop.get(v) is None or hop[v] > hop[u] + 1:
                hop[v] = hop[u] + 1
                q.append(v)
    for nid, h in hop.items():
        if nid in nodes:
            nodes[nid]["hop"] = h if h is not None else None
    return nodes

def selectable_node_ids(nodes: dict, N: int) -> list:
    return [nid for nid, n in nodes.items() if (not n.get("expanded")) and n.get("hop") is not None and n["hop"] <= N]

def merge_budget_after(budget: int, *, hard_rejects: int, schema_error: bool, failed_wave: bool = False) -> int:
    if schema_error or failed_wave:
        return budget
    return budget - 1

def graph_is_clean(nodes: dict, hard_rejects: list, N: int) -> bool:
    if hard_rejects:
        return False
    for n in nodes.values():
        if (not n.get("expanded")) and n.get("hop") is not None and n["hop"] <= N:
            return False
    return True

def assert_pack_allowed(*, phase: str) -> None:
    if phase != "active":
        die("invalid_args", f"pack/merge requires phase=active, got {phase}")

def chunk_nodes(node_ids: list, *, packet_size_files: int, validator_slots: int) -> list:
    chunks = []
    for i in range(0, len(node_ids), packet_size_files):
        chunks.append(node_ids[i:i + packet_size_files])
        if len(chunks) >= validator_slots:
            break
    return chunks

def apply_merge_expanded(nodes: dict, assigned_ids: list) -> None:
    for nid in assigned_ids:
        if nid in nodes:
            nodes[nid]["expanded"] = True

def drop_out_of_scope(nodes: dict, edges: list, *, N: int, level0: list) -> tuple:
    keep = {nid for nid, n in nodes.items() if n.get("hop") is not None and n["hop"] <= N}
    keep |= set(level0)
    nodes2 = {nid: n for nid, n in nodes.items() if nid in keep}
    edges2 = [e for e in edges if e["from"] in nodes2 and e["to"] in nodes2]
    return nodes2, edges2

def collect_hard_rejects_from_edges(nodes: dict, edges: list, *, packet_id: str) -> list:
    hrs = []
    for e in edges:
        if e["to"] not in nodes:
            hrs.append({"phase": "graph", "kind": "missing_component", "componentId": e["to"], "packetId": packet_id})
    return hrs

def clear_hard_rejects_for_components(hard_rejects: list, present_ids) -> list:
    return [h for h in hard_rejects if h.get("componentId") not in present_ids]

def _edge_key(e: dict) -> tuple:
    return (e.get("from"), e.get("to"), e.get("edgeKind"))

def apply_validate_decisions(edges: list, decisions: list) -> list:
    reject_keys = set()
    for d in decisions:
        if d.get("decision") == "reject":
            ek = d.get("edgeKey") or {}
            reject_keys.add((ek.get("from"), ek.get("to"), ek.get("edgeKind")))
    if not reject_keys:
        return edges
    return [e for e in edges if _edge_key(e) not in reject_keys]

def merge_map_nodes_edges(nodes: dict, edges: list, map_packet: dict) -> tuple:
    for n in map_packet.get("nodes") or []:
        nid = n.get("id")
        if not nid:
            continue
        if nid not in nodes:
            entry = dict(n)
            entry.setdefault("expanded", False)
            entry.setdefault("hop", None)
            nodes[nid] = entry
        else:
            for k, v in n.items():
                if k != "id":
                    nodes[nid][k] = v
    existing = {_edge_key(e) for e in edges}
    for e in map_packet.get("edges") or []:
        key = _edge_key(e)
        if key not in existing:
            edges.append(dict(e))
            existing.add(key)
    return nodes, edges

def level0_ids_from_nodes(nodes: dict) -> list:
    return [nid for nid, n in nodes.items() if n.get("hop") == 0]
