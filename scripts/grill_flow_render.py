import json
import shutil
from pathlib import Path
from grill_flow_chrome import compute_chrome
from grill_flow_state import load_ledger, load_obligations, load_path_notes, load_run

RENDER_REQUIRES_EXCLUSIVE_LOCK = True

def viewer_dir_for_helper(helper: Path) -> Path:
    if helper.parent.name == "scripts":
        return helper.parent.parent / "viewer"
    return helper.parent / "viewer"

def _copy_assets(viewer_dir: Path, run_dir: Path) -> None:
    for name in ("app.js", "style.css", "model.js"):
        src = viewer_dir / name
        if not src.is_file():
            continue
        shutil.copy2(src, run_dir / name)

def _build_html(
    *,
    chrome: str,
    path_notes: list,
    run_doc: dict,
    obligations: list,
    ledger: dict,
    repo_root: Path | None = None,
) -> str:
    path_notes_panel = ""
    if path_notes:
        notes_json = json.dumps(path_notes, separators=(",", ":"))
        path_notes_panel = (
            f'<section id="path-notes-panel" data-path-notes="{_escape_attr(notes_json)}">'
            f"<h2>PathNotes</h2></section>"
        )
    delete_drill = ""
    if chrome == "only-delete":
        delete_drill = '<section id="delete-drill-in"><h2>Delete drill-in</h2></section>'
    payload = {
        "chrome": chrome,
        "runKind": run_doc.get("runKind"),
        "runStatus": run_doc.get("runStatus"),
        "graphPartial": run_doc.get("graphPartial"),
        "pathNotesCount": len(path_notes),
        "obligationCount": len(obligations),
    }
    if repo_root is not None:
        payload["repoRoot"] = str(repo_root)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<meta name=\"grill-flow-chrome\" content=\"{chrome}\">\n"
        "<title>grill-flow</title>\n"
        "<link rel=\"stylesheet\" href=\"style.css\">\n"
        "</head>\n"
        f"<body data-chrome=\"{chrome}\">\n"
        f"<header id=\"chrome-banner\">{chrome}</header>\n"
        "<div id=\"run-status-banner\"></div>\n"
        "<div id=\"flow-fragmentation-banner\" hidden></div>\n"
        "<div id=\"hard-reject-strip\"></div>\n"
        f"{path_notes_panel}\n"
        f"{delete_drill}\n"
        "<div id=\"shell\">\n"
        "  <section id=\"graph-pane\">\n"
        "    <div id=\"graph-toolbar\"></div>\n"
        "    <svg id=\"graph-canvas\" xmlns=\"http://www.w3.org/2000/svg\"></svg>\n"
        "  </section>\n"
        "  <aside id=\"inspector-panel\">\n"
        "    <div id=\"inspector-empty\">click a node</div>\n"
        "    <div id=\"inspector-body\" hidden></div>\n"
        "  </aside>\n"
        "</div>\n"
        f"<script type=\"application/json\" id=\"run-payload\">{json.dumps(payload)}</script>\n"
        "<script src=\"model.js\"></script>\n"
        "<script src=\"app.js\"></script>\n"
        "</body>\n</html>\n"
    )

def _escape_attr(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def render_run(run_dir: Path, helper: Path, *, repo_root: Path | None = None) -> dict:
    run_doc = load_run(run_dir)
    obligations = load_obligations(run_dir)
    path_notes = load_path_notes(run_dir)
    ledger = load_ledger(run_dir)
    chrome = compute_chrome(run_doc.get("runKind"), obligations, ledger)
    viewer_dir = viewer_dir_for_helper(helper)
    _copy_assets(viewer_dir, run_dir)
    html = _build_html(
        chrome=chrome,
        path_notes=path_notes,
        run_doc=run_doc,
        obligations=obligations,
        ledger=ledger,
        repo_root=repo_root,
    )
    (run_dir / "index.html").write_text(html)
    return {"ok": True, "chrome": chrome, "index": str(run_dir / "index.html")}
