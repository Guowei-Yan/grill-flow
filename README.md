# grill-flow

[![CI](https://github.com/Guowei-Yan/grill-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/Guowei-Yan/grill-flow/actions/workflows/ci.yml)

Language-agnostic component-graph and line-to-flow coverage mapper for Git diffs and file sets, with a local vanilla-JS HTML explorer (`Python 3.10+`, MIT).

High-level architecture diagrams skip line-level control flow, while raw unified diffs hide component boundaries. `grill-flow` coordinates two budgeted mapping phases so every changed line is either attributed to an end-to-end execution flow, explicitly classified/waived, or left visibly uncovered.

## Pipeline

1. **Surface fingerprinting (`init-surface`, `check-surface`)**: snapshots a Git diff (optionally including dirty working-tree edits) or explicit file set using `SHA-256` digests and `git rev-parse` tree OIDs. If tracked files change after a run completes, the run automatically demotes back to `in_progress`.
2. **Phase 1 — Component graph (`pack-graph` / `merge-graph`)**: builds and validates a component topology under `graphBudget`.
3. **Phase 2 — Line-to-flow ledger (`pack-flows` / `merge-flows`)**: assigns line-range coverage obligations under `lineBudget`, enforcing a `0.40` singleton-rate ceiling on files with `>= 8` semantic lines.
4. **Interactive explorer (`render`, `serve-start`, `serve-stop`)**: renders a standalone viewer bundle (`viewer/model.js`, `viewer/app.js`, `viewer/style.css`) and serves live `GET /repo` line slices on loopback (`127.0.0.1`) by default with constant-time instance-token checks, canonical path containment, and `os.killpg` process-group shutdown.

### Concurrency & Locking

Mutating subcommands serialize lock acquisition with POSIX `fcntl.flock` on the run directory and atomically publish `.lock` via hard-link (`os.link`) from an `fsync`-ed temp file (with `--force-lock` recovery). Read-only `--read-only status` inspects run state directly without blocking writers.

## CLI Quickstart

```bash
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run \
  init-surface --mode git-diff --base HEAD~1 --head HEAD
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run init-run
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run recommend-gate
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run \
  apply-gate --N 2 --graph-budget 6 --line-budget 8

python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run --read-only status
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run render
python3 scripts/grill-flow.py --repo-root . --run-dir ./flow-run serve-start --port 8765
```

## Tests & Skill Install

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
./sync-grill-flow.sh
```

See [`SKILL.md`](SKILL.md) and [`docs/design-spec.md`](docs/design-spec.md) for the subcommand state machine, error codes, and viewer contracts.
