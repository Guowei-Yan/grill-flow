def compute_chrome(run_kind, obligations, ledger):
    if run_kind == "empty":
        return "empty-run"
    if run_kind == "pathNotesOnly":
        return "pathNotes-only"
    if run_kind == "emptyLedger":
        return "empty-ledger"
    non = [o for o in obligations if ledger.get(o["obligationId"], {}).get("state") != "waived"]
    if not non:
        return "normal"
    def covered(oid):
        return ledger.get(oid, {}).get("state") == "covered"
    if all(o.get("change") == "deleted" for o in non) and all(covered(o["obligationId"]) for o in non):
        return "only-delete"
    if all(covered(o["obligationId"]) for o in non) and all(ledger.get(o["obligationId"], {}).get("kind") == "structural" for o in non):
        return "all-structural"
    return "normal"
