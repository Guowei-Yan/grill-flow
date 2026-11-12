import json, sys
CODES = frozenset({
    "run_in_progress", "force_lock_required", "helper_not_found",
    "helper_not_executable", "invalid_args", "inbox_id_exists",
    "budget_exhausted", "serve_stop_mismatch", "serve_info_missing",
    "apply_gate_too_late", "unsupported_platform", "schema_error",
    "abort_conflict", "quality_error",
})
def die(code: str, message: str) -> None:
    if code not in CODES:
        code = "invalid_args"
    print(json.dumps({"error": code, "message": message}), file=sys.stderr)
    raise SystemExit(1)
