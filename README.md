# grill-flow

[![CI](https://github.com/Guowei-Yan/grill-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/Guowei-Yan/grill-flow/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](#)

Deterministic codebase component-graph and line-to-flow coverage mapper for Git diffs and file sets, featuring dual phase budgets, content-hash drift guards, validator return barriers, and an interactive hosted HTML/JS viewer (**zero third-party runtime dependencies**).

---

## What It Solves

Understanding an unfamiliar pull request or multi-module subsystem fails in two ways: high-level architecture diagrams omit line-level control flow, while raw unified diffs obscure cross-component boundaries. `grill-flow` coordinates fresh-context mapping waves against deterministic file/line ledgers so every in-scope line is either attributed to an explicit end-to-end execution flow, explicitly waived with rationale, or surfaced as uncovered.

```text
Git Diff / File-Set Surface
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. Surface & Inventory (init-surface ─► recommend-gate)      │
│    • Git-diff (+ optional dirty working tree) or file-set    │
│    • SHA-256 / blob-OID surface fingerprinting               │
├──────────────────────────────────────────────────────────────┤
│ 2. Phase 1: Component Graph (pack-graph ─► merge-graph)      │
│    • Bounded graph packets + independent validator pass      │
│    • Controlled graphBudget waves                            │
├──────────────────────────────────────────────────────────────┤
│ 3. Phase 2: Line-to-Flow Ledger (pack-flows ─► merge-flows)  │
│    • Line-range coverage obligations per file                │
│    • Controlled lineBudget waves + explicit waive/unwaive    │
├──────────────────────────────────────────────────────────────┤
│ 4. Interactive Viewer (render ─► serve-start / serve-stop)   │
│    • Coalesced member runs, flow prose sections, inspector   │
│    • Local HTTP preview server with GET /repo source slices  │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Engineering Properties

- **Language-Agnostic & Zero External Dependencies**: Built strictly on the Python standard library and vanilla ES modules (`viewer/model.js`, `viewer/app.js`, `viewer/style.css`) — no fragile AST or `tree-sitter` native compilation required.
- **Exclusive Run-Dir Locking & Non-Blocking `status`**: Mutating subcommands acquire an exclusive lock with force-token recovery (`--force-lock`), while `status` inspects live state safely without blocking active runs.
- **Automatic Drift Demotion**: `check-surface` and phase transitions verify file fingerprints; if tracked files change after a run reaches `complete`, the run automatically demotes to `in_progress` instead of serving stale flow maps.
- **Hosted Web Explorer**: `render` emits a self-contained viewer bundle and `serve-start` launches a managed local HTTP server (`GET /repo` live line previews) with clean process-tree shutdown via `serve-stop`.

---

## Quickstart

### CLI Workflow

```bash
# 1. Initialize surface from a Git diff (or --mode file-set)
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run \
  init-surface --mode git-diff --base HEAD~1

# 2. Initialize run, inspect recommended gate, and apply dual-phase budgets
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run init-run
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run recommend-gate
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run \
  apply-gate --N 2 --graph-budget 6 --line-budget 8

# 3. Inspect run state or render & serve the interactive HTML viewer
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run --read-only status
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run render
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run serve-start --port 8765
```

### Install as a Local Coding-Agent Skill

```bash
./sync-grill-flow.sh
```

### Run the Test Suite (170 Tests)

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

See [`SKILL.md`](SKILL.md) and [`docs/design-spec.md`](docs/design-spec.md) for the full subcommand state table, error codes, and viewer layout contracts.

---

## License

[MIT](LICENSE)
