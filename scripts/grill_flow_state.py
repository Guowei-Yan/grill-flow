import json
from pathlib import Path
from grill_flow_chrome import compute_chrome
from grill_flow_errors import die
from grill_flow_lock import read_lock

INIT_RUN_REQUIRES_EXCLUSIVE_LOCK = True
INIT_SURFACE_REQUIRES_EXCLUSIVE_LOCK = False
APPLY_GATE_REQUIRES_EXCLUSIVE_LOCK = True
ACCEPT_PARTIAL_REQUIRES_EXCLUSIVE_LOCK = True
BEGIN_FLOWS_REQUIRES_EXCLUSIVE_LOCK = True
UNWAIVE_REQUIRES_EXCLUSIVE_LOCK = True
RESUME_GRAPH_REQUIRES_EXCLUSIVE_LOCK = True
RAISE_BUDGET_REQUIRES_EXCLUSIVE_LOCK = True
ABORT_RUN_REQUIRES_EXCLUSIVE_LOCK = True
STATUS_REQUIRES_EXCLUSIVE_LOCK = False
RECOMMEND_GATE_REQUIRES_EXCLUSIVE_LOCK = False

DEFAULT_PACKET_SIZE_OBLIGATIONS = 40
DEFAULT_PACKET_SIZE_FILES = 8
DEFAULT_VALIDATOR_SLOTS = 8

DEFAULT_GATE_NORMAL = {
    "N": 2,
    "graphBudget": 6,
    "lineBudget": 8,
    "packetSizeObligations": DEFAULT_PACKET_SIZE_OBLIGATIONS,
    "packetSizeFiles": DEFAULT_PACKET_SIZE_FILES,
    "validatorSlots": DEFAULT_VALIDATOR_SLOTS,
    "models": "n/a",
}

_FROZEN_BLOCKED = frozenset({
    "pack-graph", "merge-graph", "pack-flows", "merge-flows", "inbox-put",
})
_FROZEN_ALLOWED = frozenset({"inbox-clear", "check-surface"})

def init_run_guard(*, surface_exists: bool) -> None:
    if not surface_exists:
        die("invalid_args", "init-run requires init-surface first")

def apply_init_run_kind(run_kind: str) -> dict:
    short_gate = {
        "N": 0, "graphBudget": 0, "lineBudget": 0,
        "packetSizeObligations": 40, "packetSizeFiles": 8,
        "validatorSlots": 1, "models": "n/a",
    }
    if run_kind == "empty":
        return {"runStatus": "complete", "runKind": "empty", "gate": None,
                "graph": {"phase": None}, "flows": {"phase": None}}
    if run_kind in ("pathNotesOnly", "emptyLedger"):
        return {"runStatus": "complete", "runKind": run_kind, "gate": dict(short_gate),
                "graph": {"phase": "clean"}, "flows": {"phase": "clean"}}
    return {"runStatus": "in_progress", "runKind": "normal", "gate": None,
            "graph": {"phase": "not_started"}, "flows": {"phase": "not_started"}}

def seed_level0_nodes(paths, *, expanded: bool) -> dict:
    return {f"file:{p}": {"hop": 0, "expanded": expanded, "kind": "file", "path": p} for p in paths}

def initial_surface_hash_written(surface_obj: dict) -> bool:
    from grill_flow_hash import surface_hash
    return bool(surface_hash(surface_obj))

def initial_ledger_state(obligation_id: str) -> str:
    return "uncovered"

def _run_path(run_dir: Path) -> Path:
    return run_dir / "run.json"

def load_run(run_dir: Path) -> dict:
    p = _run_path(run_dir)
    if not p.is_file():
        die("invalid_args", "run not initialised")
    return json.loads(p.read_text())

def save_run(run_dir: Path, doc: dict) -> None:
    _run_path(run_dir).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

def load_ledger(run_dir: Path) -> dict:
    p = run_dir / "ledger.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text())

def save_ledger(run_dir: Path, ledger: dict) -> None:
    (run_dir / "ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

def load_graph(run_dir: Path) -> dict:
    p = run_dir / "graph.json"
    if not p.is_file():
        return {"nodes": {}, "edges": []}
    return json.loads(p.read_text())

def load_obligations(run_dir: Path) -> list:
    p = run_dir / "obligations.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text())

def load_path_notes(run_dir: Path) -> list:
    p = run_dir / "pathNotes.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text())

def load_hard_rejects(run_doc: dict) -> list:
    return list(run_doc.get("hardRejects") or [])

def _budget_remaining(run_doc: dict, phase: str) -> int:
    gate = run_doc.get("gate") or {}
    if phase == "graph":
        return int(gate.get("graphBudget") or 0)
    return int(gate.get("lineBudget") or 0)

def graph_clean_predicate(run_doc: dict, graph: dict) -> bool:
    hard = [h for h in load_hard_rejects(run_doc) if h.get("phase") == "graph"]
    if hard:
        return False
    gate = run_doc.get("gate") or {}
    n = int(gate.get("N") or 0)
    nodes = graph.get("nodes") or {}
    for node in nodes.values():
        if (not node.get("expanded", False)) and int(node.get("hop", 0)) <= n:
            return False
    return True

def flows_clean_predicate(run_doc: dict, ledger: dict) -> bool:
    if (run_doc.get("flows") or {}).get("phase") == "accepted_partial":
        return False
    hard = [h for h in load_hard_rejects(run_doc) if h.get("phase") == "flows"]
    if hard:
        return False
    for entry in ledger.values():
        if entry.get("state") == "uncovered":
            return False
    return True

def apply_graph_clean_predicate(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    graph = load_graph(run_dir)
    if (doc.get("graph") or {}).get("phase") == "active" and graph_clean_predicate(doc, graph):
        doc["graph"] = dict(doc.get("graph") or {}, phase="clean")
        save_run(run_dir, doc)
    return doc

def evaluate_completion(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    ledger = load_ledger(run_dir)
    graph = load_graph(run_dir)
    if (doc.get("graph") or {}).get("phase") == "active" and graph_clean_predicate(doc, graph):
        doc["graph"] = dict(doc.get("graph") or {}, phase="clean")
    waived = [k for k, v in ledger.items() if v.get("state") == "waived"]
    flows_phase = (doc.get("flows") or {}).get("phase")
    graph_phase = (doc.get("graph") or {}).get("phase")
    if (
        flows_phase == "active"
        and flows_clean_predicate(doc, ledger)
        and graph_phase == "clean"
        and not doc.get("graphPartial")
        and not waived
    ):
        doc["flows"] = dict(doc.get("flows") or {}, phase="clean")
        doc["runStatus"] = "complete"
    save_run(run_dir, doc)
    return doc

def begin_flows(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    flows_phase = (doc.get("flows") or {}).get("phase")
    graph_phase = (doc.get("graph") or {}).get("phase")
    if flows_phase != "not_started" or graph_phase not in ("clean", "accepted_partial"):
        die("invalid_args", "begin-flows requires flows=not_started and graph clean|accepted_partial")
    doc["flows"] = dict(doc.get("flows") or {}, phase="active")
    if graph_phase == "accepted_partial":
        doc["graphPartial"] = True
    save_run(run_dir, doc)
    return doc

def accept_partial(run_dir: Path, *, phase: str) -> dict:
    doc = load_run(run_dir)
    if phase == "graph":
        if (doc.get("graph") or {}).get("phase") != "active":
            die("invalid_args", "accept-partial graph requires graph.phase=active")
        doc["graph"] = dict(doc.get("graph") or {}, phase="accepted_partial")
        doc["runStatus"] = "incomplete"
        save_run(run_dir, doc)
        return doc
    if phase == "flows":
        if (doc.get("flows") or {}).get("phase") != "active":
            die("invalid_args", "accept-partial flows requires flows.phase=active")
        ledger = load_ledger(run_dir)
        uncovered = [k for k, v in ledger.items() if v.get("state") == "uncovered"]
        if not uncovered:
            die("invalid_args", "accept-partial flows requires uncovered obligations")
        for oid in uncovered:
            ledger[oid] = dict(ledger[oid], state="waived")
        save_ledger(run_dir, ledger)
        doc["flows"] = dict(doc.get("flows") or {}, phase="accepted_partial")
        doc["runStatus"] = "incomplete"
        save_run(run_dir, doc)
        return doc
    die("invalid_args", "accept-partial phase must be graph|flows")
    return doc

def resume_graph(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    if (doc.get("graph") or {}).get("phase") != "accepted_partial":
        die("invalid_args", "resume-graph requires graph accepted_partial")
    if (doc.get("flows") or {}).get("phase") != "not_started":
        die("invalid_args", "resume-graph requires flows not_started")
    doc["graph"] = dict(doc.get("graph") or {}, phase="active")
    save_run(run_dir, doc)
    return doc

def unwaive(run_dir: Path, *, obligation_ids: list | None = None) -> dict:
    doc = load_run(run_dir)
    ledger = load_ledger(run_dir)
    if obligation_ids is None:
        targets = [k for k, v in ledger.items() if v.get("state") == "waived"]
    else:
        targets = list(obligation_ids)
    for oid in targets:
        if oid in ledger:
            ledger[oid] = dict(ledger[oid], state="uncovered")
    save_ledger(run_dir, ledger)
    doc["flows"] = dict(doc.get("flows") or {}, phase="active")
    graph_phase = (doc.get("graph") or {}).get("phase")
    if graph_phase != "accepted_partial" and not doc.get("graphPartial"):
        doc["runStatus"] = "in_progress"
    save_run(run_dir, doc)
    return doc

def raise_budget(run_dir: Path, *, phase: str) -> dict:
    doc = load_run(run_dir)
    gate = dict(doc.get("gate") or {})
    if phase == "graph":
        if (doc.get("graph") or {}).get("phase") != "active":
            die("invalid_args", "raise-budget graph requires graph.phase=active")
        gate["graphBudget"] = int(gate.get("graphBudget") or 0) + 1
    elif phase == "flows":
        if (doc.get("flows") or {}).get("phase") != "active":
            die("invalid_args", "raise-budget flows requires flows.phase=active")
        gate["lineBudget"] = int(gate.get("lineBudget") or 0) + 1
    else:
        die("invalid_args", "raise-budget phase must be graph|flows")
    doc["gate"] = gate
    save_run(run_dir, doc)
    return doc

def abort_run(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    status = doc.get("runStatus")
    if status in ("complete", "aborted"):
        die("abort_conflict", f"cannot abort when runStatus={status}")
    if status == "incomplete":
        return doc
    doc["runStatus"] = "aborted"
    save_run(run_dir, doc)
    return doc

def recommend_gate(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    if doc.get("runKind") != "normal":
        die("invalid_args", "recommend-gate only for normal runKind")
    recommended = dict(DEFAULT_GATE_NORMAL)
    return {
        "runKind": "normal",
        "recommended": recommended,
        "rationale": "defaults packetSizeObligations=40 packetSizeFiles=8; N from Gate B",
    }

def apply_gate(run_dir: Path, *, gate: dict) -> dict:
    if not _run_path(run_dir).is_file():
        die("invalid_args", "apply-gate before init-run")
    doc = load_run(run_dir)
    kind = doc.get("runKind")
    if kind == "empty":
        die("invalid_args", "apply-gate invalid for empty")
    if kind in ("pathNotesOnly", "emptyLedger"):
        return doc
    if kind != "normal":
        die("invalid_args", "apply-gate requires normal runKind")
    if (doc.get("graph") or {}).get("phase") != "not_started":
        die("apply_gate_too_late", "apply-gate only when graph.phase=not_started")
    merged = dict(DEFAULT_GATE_NORMAL)
    merged.update(gate or {})
    if "packetSizeObligations" not in (gate or {}):
        merged["packetSizeObligations"] = DEFAULT_PACKET_SIZE_OBLIGATIONS
    if "packetSizeFiles" not in (gate or {}):
        merged["packetSizeFiles"] = DEFAULT_PACKET_SIZE_FILES
    if "validatorSlots" not in (gate or {}):
        merged["validatorSlots"] = DEFAULT_VALIDATOR_SLOTS
    doc["gate"] = merged
    doc["graph"] = dict(doc.get("graph") or {}, phase="active")
    save_run(run_dir, doc)
    return doc

def assert_mutable_command_allowed(run_dir: Path, cmd: str) -> None:
    doc = load_run(run_dir)
    status = doc.get("runStatus")
    if status in ("complete", "aborted") and cmd in _FROZEN_BLOCKED:
        die("invalid_args", f"{cmd} blocked when runStatus={status}")
    if status in ("complete", "aborted") and cmd in _FROZEN_ALLOWED:
        return

def build_status(run_dir: Path) -> dict:
    doc = load_run(run_dir)
    ledger = load_ledger(run_dir)
    graph = load_graph(run_dir)
    obligations = load_obligations(run_dir)
    path_notes = load_path_notes(run_dir)
    chrome = compute_chrome(doc.get("runKind"), obligations, ledger)
    uncovered = sum(1 for v in ledger.values() if v.get("state") == "uncovered")
    waived = sum(1 for v in ledger.values() if v.get("state") == "waived")
    g_clean = graph_clean_predicate(doc, graph) if (doc.get("graph") or {}).get("phase") not in (None,) else False
    f_clean = flows_clean_predicate(doc, ledger) if (doc.get("flows") or {}).get("phase") not in (None, "not_started") else False
    gate = doc.get("gate")
    lock = read_lock(run_dir)
    return {
        "runId": doc.get("runId") or run_dir.name,
        "runKind": doc.get("runKind"),
        "runStatus": doc.get("runStatus"),
        "chrome": chrome,
        "graphPartial": bool(doc.get("graphPartial")),
        "graph": {
            "phase": (doc.get("graph") or {}).get("phase"),
            "budgetRemaining": _budget_remaining(doc, "graph") if gate else 0,
            "clean": bool(g_clean and (doc.get("graph") or {}).get("phase") == "clean"),
        },
        "flows": {
            "phase": (doc.get("flows") or {}).get("phase"),
            "budgetRemaining": _budget_remaining(doc, "flows") if gate else 0,
            "clean": bool(f_clean and (doc.get("flows") or {}).get("phase") == "clean"),
            "uncoveredCount": uncovered,
            "waivedCount": waived,
        },
        "gate": gate,
        "hardRejects": load_hard_rejects(doc),
        "pathNotesCount": len(path_notes),
        "lock": lock,
    }
