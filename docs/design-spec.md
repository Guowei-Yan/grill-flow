# grill-flow Design Specification

`grill-flow` maps a Git diff or explicit file-set into a deterministic component graph and line-to-flow coverage ledger, enforced by dual phase/wave budgets and rendered as an interactive single-host HTML/JS viewer.

## Architecture & Guarantees

1. **Surface & Inventory (`grill_flow_surface.py`, `grill_flow_inventory.py`)**:
   - Supports `git-diff` (including optional dirty working-tree union) and explicit `file-set` modes.
   - Classifies run kinds (`normal`, `empty`, `emptyLedger`, `pathNotesOnly`) and expands Level-0 directory inputs deterministically with named-file precedence (`named-wins`).
2. **State Machine, Locking & Drift Detection (`grill_flow_state.py`, `grill_flow_lock.py`, `grill_flow_drift.py`)**:
   - Exclusive run-directory lock with explicit force-token reclaim (`--force-lock`).
   - Non-blocking read-only `status` inspection while an exclusive writer lock is held.
   - Content-hash drift checks across phases (`graph` -> `flows` -> `complete`); detected workspace drift automatically demotes `complete` runs back to `in_progress`.
3. **Component Graph & Flow Coverage (`grill_flow_graph.py`, `grill_flow_flows.py`, `grill_flow_pack.py`)**:
   - Language-agnostic obligation packing without external AST/parser-generator dependencies.
   - Independent budgets per phase/wave (`graphBudget`, `lineBudget`) with controlled `raise-budget`, `accept-partial`, `begin-flows`, `resume-graph`, and `unwaive` transitions.
4. **Interactive Viewer & Local Server (`viewer/`, `grill_flow_render.py`, `grill_flow_serve.py`)**:
   - Renders `index.html` and serves repository line previews (`GET /repo`) with process-tree `serve-stop` lifecycle management.

## Tests (skill) — required
runKind; Level-0 expanded defaults; dirty union; named-wins; budgets per phase/wave; phase table incl. `begin-flows`/`resume-graph`; frozen complete; drift demotes complete; lock force success; status without exclusive block; serve-stop tree; stderr codes; chrome mapping; resolve matrix.
