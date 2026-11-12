import json
from pathlib import Path
from grill_flow_errors import die

INBOX_PUT_REQUIRES_EXCLUSIVE_LOCK = True
INBOX_CLEAR_REQUIRES_EXCLUSIVE_LOCK = True

def inbox_file(run_dir: Path, packet_id: str) -> Path:
    return run_dir / "packets" / "inbox" / f"{packet_id}.json"

def inbox_put(run_dir: Path, packet_id: str, body: dict) -> dict:
    path = inbox_file(run_dir, packet_id)
    if path.exists():
        die("inbox_id_exists", f"inbox packet already exists: {packet_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return {}

def inbox_clear(run_dir: Path, packet_id: str) -> dict:
    path = inbox_file(run_dir, packet_id)
    if path.exists():
        path.unlink()
    return {}

def pack_graph_budget_check(budget: int) -> int:
    return budget

def check_packet_id_congruence(cli_id: str, body_id) -> None:
    if cli_id != body_id:
        die("schema_error", "packetId mismatch")

def load_inbox_packet(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        die("schema_error", "unparseable inbox")

def validate_graph_map_packet(obj: dict) -> dict:
    if obj.get("kind") != "graph-map" or "nodes" not in obj or "edges" not in obj:
        die("schema_error", "wrong top-level shape")
    return obj

def validate_graph_validate_packet(obj: dict) -> dict:
    if obj.get("kind") != "graph-validate" or "decisions" not in obj:
        die("schema_error", "wrong top-level shape")
    return obj

def validate_flows_map_packet(obj: dict) -> dict:
    if obj.get("kind") != "flows-map" or "dispositions" not in obj:
        die("schema_error", "wrong top-level shape")
    return obj

def validate_flows_validate_packet(obj: dict) -> dict:
    if obj.get("kind") != "flows-validate" or "decisions" not in obj:
        die("schema_error", "wrong top-level shape")
    return obj

def read_inbox_file(run_dir: Path, packet_id: str) -> dict:
    path = inbox_file(run_dir, packet_id)
    if not path.is_file():
        die("schema_error", f"missing inbox packet: {packet_id}")
    try:
        raw = path.read_text()
    except OSError:
        die("schema_error", f"unreadable inbox packet: {packet_id}")
    obj = load_inbox_packet(raw)
    if not isinstance(obj, dict):
        die("schema_error", "wrong top-level shape")
    check_packet_id_congruence(packet_id, obj.get("packetId"))
    return obj
