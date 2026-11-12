---
name: grill-flow
description: >-
  Use when mapping a file-set or git diff into a component graph and line-to-flow coverage with dual
  budgets, validators, and a hosted HTML viewer. Maps only — never grades, reviews, or commits.
  Triggers: "grill-flow", "map this flow", "map the component graph", "run grill-flow on this diff".
---

# grill-flow

Map-only skill. Spec: docs/design-spec.md

## Gate A / Gate B
Gate A: surface mode git-diff|file-set (+ dirty ask for git-diff). Gate B: N, graphBudget, lineBudget (normal only; empty/emptyLedger/pathNotesOnly auto-complete at init-run).

## Resolve
GRILL_FLOW_HELPER → skill scripts → ~/.local/share/grill-flow/

## Contracts

### C1 graph-map return

```json
{
  "packetId": "g1-p0",
  "kind": "graph-map",
  "nodes": [
    {"id": "file:src/a.py", "kind": "file", "path": "src/a.py"},
    {"id": "symbol:src/a.py:foo", "kind": "symbol", "path": "src/a.py", "qualname": "foo"}
  ],
  "edges": [
    {
      "from": "file:src/a.py",
      "to": "file:src/b.py",
      "edgeKind": "import",
      "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "startLine": 1, "endLine": 1, "note": "import b"}
    }
  ]
}
```

`edgeKind` ∈ `call|import|type|shared_state|event`.

### C2 graph-validate return

```json
{
  "packetId": "g1-p0-val",
  "kind": "graph-validate",
  "decisions": [
    {"edgeKey": {"from": "file:src/a.py", "to": "file:src/b.py", "edgeKind": "import"}, "decision": "confirm"},
    {"edgeKey": {"from": "file:x", "to": "file:y", "edgeKind": "call"}, "decision": "reject", "reason": "no evidence"}
  ],
  "advisoryNotes": [
    {"message": "possible missing neighbour", "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "note": "…"}}
  ]
}
```

### C3 flows-map return

**Granularity:** A semantic flow is a shared behaviour (function / multi-line unit). Obligations in the same behaviour **must** share the exact same non-empty `logic[]`. Non-behaviour lines use `kind: structural`. Do **not** invent unique one-line `logic` per obligation. Empty `logic` yields a per-id group and counts toward fragmentation. `merge-flows` exits `quality_error` (no persist, no budget −1) if any path with ≥8 covered-semantic obligations has singleton flow-group rate > 0.40.

```json
{
  "packetId": "f1-p0",
  "kind": "flows-map",
  "dispositions": [
    {
      "obligationId": "file:src/a.py:10:abcd1234",
      "kind": "semantic",
      "change": "present",
      "inputs": ["x"],
      "logic": ["add 1"],
      "outputs": ["y"],
      "consumers": ["file:src/b.py"],
      "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "startLine": 10, "endLine": 10, "note": ""}
    },
    {
      "obligationId": "file:src/a.py:11:ffffffff",
      "kind": "semantic",
      "change": "present",
      "inputs": ["x"],
      "logic": ["add 1"],
      "outputs": ["y"],
      "consumers": ["file:src/b.py"],
      "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "startLine": 11, "endLine": 11, "note": ""}
    },
    {
      "obligationId": "file:src/a.py:1:deadbeef",
      "kind": "structural",
      "change": "present",
      "structuralClass": "import-or-include",
      "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "startLine": 1, "endLine": 1, "note": ""}
    },
    {
      "obligationId": "diff:old:src/a.py:3:eeeeeeee",
      "kind": "semantic",
      "change": "deleted",
      "inputs": ["a"],
      "logic": ["was used"],
      "outputs": [],
      "consumers": [{"unknown": true, "label": "old caller", "evidenceRef": {"path": "src/a.py", "oid": "abc", "source": "oid", "note": ""}}],
      "preChangeRole": "computed a",
      "removalImpact": "callers must stop",
      "evidenceRef": {"path": "src/a.py", "oid": "abc", "source": "oid", "startLine": 3, "endLine": 3, "note": ""}
    },
    {
      "obligationId": "diff:old:src/a.py:1:bbbbbbbb",
      "kind": "structural",
      "change": "deleted",
      "structuralClass": "import-or-include",
      "removalNote": "import removed; callers no longer resolve this module edge",
      "evidenceRef": {"path": "src/a.py", "oid": "abc", "source": "oid", "startLine": 1, "endLine": 1, "note": ""}
    }
  ]
}
```

### C4 flows-validate return

Reject reasons include `hollow` and **`line_scoped`** (unique logic that only restates a single line instead of joining a shared flow).

```json
{
  "packetId": "f1-p0-val",
  "kind": "flows-validate",
  "decisions": [
    {"obligationId": "file:src/a.py:10:abcd1234", "decision": "confirm"},
    {"obligationId": "file:src/a.py:11:ffffffff", "decision": "confirm"},
    {"obligationId": "file:src/a.py:12:eeeeeeee", "decision": "reject", "reason": "line_scoped"},
    {"obligationId": "file:src/a.py:13:dddddddd", "decision": "reject", "reason": "hollow"},
    {
      "obligationId": "file:src/a.py:1:deadbeef",
      "decision": "reclassifyTo",
      "disposition": {
        "obligationId": "file:src/a.py:1:deadbeef",
        "kind": "semantic",
        "change": "present",
        "inputs": [],
        "logic": ["side-effect import"],
        "outputs": [],
        "consumers": [],
        "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "startLine": 1, "endLine": 1, "note": ""}
      }
    }
  ]
}
```

**Rule:** `inbox-put --packet-id` MUST equal body `packetId` or merge → `schema_error`.

### C5 `status` stdout

```json
{
  "runId": "rid",
  "runKind": "normal",
  "runStatus": "in_progress",
  "chrome": "normal",
  "graphPartial": false,
  "graph": {"phase": "active", "budgetRemaining": 6, "clean": false},
  "flows": {"phase": "not_started", "budgetRemaining": 8, "clean": false, "uncoveredCount": 3, "waivedCount": 0},
  "gate": {"N": 2, "graphBudget": 6, "lineBudget": 8, "packetSizeObligations": 40, "packetSizeFiles": 8, "validatorSlots": 8, "models": "n/a"},
  "hardRejects": [
    {
      "phase": "graph",
      "kind": "missing_component",
      "componentId": "file:missing.py",
      "packetId": "g1-p0",
      "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "note": "edge target absent"}
    },
    {
      "phase": "flows",
      "kind": "missing_component",
      "obligationId": "file:src/a.py:10:abcd1234",
      "componentId": "file:missing.py",
      "packetId": "f1-p0",
      "evidenceRef": {"path": "src/a.py", "oid": null, "source": "worktree", "note": "consumer absent from graph"}
    }
  ],
  "pathNotesCount": 0,
  "lock": null
}
```

`hardReject` element (also used in C9 `hardRejectsAdded`): `phase` ∈ `graph|flows`; `kind` at least `missing_component`; graph items require `componentId`; flows items require `obligationId` + `componentId` when the reject is a missing consumer/component; optional `packetId`, `evidenceRef`.

### C6 `recommend-gate` stdout

```json
{
  "runKind": "normal",
  "recommended": {
    "N": 2,
    "graphBudget": 6,
    "lineBudget": 8,
    "packetSizeObligations": 40,
    "packetSizeFiles": 8,
    "validatorSlots": 8,
    "models": "n/a"
  },
  "rationale": "defaults packetSizeObligations=40 packetSizeFiles=8; N from Gate B"
}
```

Non-`normal` → stderr `invalid_args` (no exclusive lock). Defaults: `packetSizeObligations=40`, `packetSizeFiles=8`, `validatorSlots=8`.

### C7 `check-surface` stdout

```json
{
  "changed": true,
  "surfaceHashBefore": "abc…",
  "surfaceHashAfter": "def…",
  "droppedEdges": [
    {"from": "file:a.py", "to": "file:b.py", "edgeKind": "import", "reason": "endpoint_hop_gt_N"}
  ],
  "revokedObligations": [
    {"obligationId": "file:src/a.py:10:abcd1234", "reason": "consumer_missing_from_graph", "componentId": "file:gone.py"}
  ],
  "runStatus": "in_progress",
  "graphPhase": "active",
  "flowsPhase": "active"
}
```

When hash unchanged: `{"changed":false,"surfaceHashBefore":"…","surfaceHashAfter":"…","droppedEdges":[],"revokedObligations":[],"runStatus":"…","graphPhase":"…","flowsPhase":"…"}`. Covered semantic whose consumer id is missing from graph → revoke → uncovered (listed in `revokedObligations`, not hardReject).

### C8 Pack stdout (budget is **not** mutated by pack)

```json
{
  "waveId": "g1",
  "phase": "graph",
  "mode": "map",
  "budgetRemaining": 6,
  "packets": [
    {"packetId": "g1-p0", "assignedNodeIds": ["file:src/a.py"], "outPath": "packets/out/g1-p0.json"}
  ]
}
```

`budgetRemaining` = current `graphBudget` or `lineBudget` for the phase, **unchanged** by pack (informational). Pack fails `budget_exhausted` only if that budget is already 0.

Map brief file `packets/out/g1-p0.json`:
```json
{"packetId":"g1-p0","kind":"graph-map-brief","waveId":"g1","assignedNodeIds":["file:src/a.py"],"N":2,"repoRoot":"/repo","runDir":"/repo/docs/grill-flow/rid"}
```

Validate pack stdout:
```json
{
  "waveId": "g1",
  "phase": "graph",
  "mode": "validate",
  "budgetRemaining": 6,
  "packets": [
    {"packetId": "g1-p0-val", "assignedNodeIds": ["file:src/a.py"], "outPath": "packets/out/g1-p0-val.json"}
  ]
}
```

Validate brief:
```json
{
  "packetId": "g1-p0-val",
  "kind": "graph-validate-brief",
  "waveId": "g1",
  "assignedNodeIds": ["file:src/a.py"],
  "mapPacketId": "g1-p0",
  "mapReturnPath": "packets/inbox/g1-p0.json",
  "N": 2,
  "repoRoot": "/repo",
  "runDir": "/repo/docs/grill-flow/rid"
}
```

Flows pack stdout (map):
```json
{
  "waveId": "f1",
  "phase": "flows",
  "mode": "map",
  "budgetRemaining": 8,
  "packets": [
    {"packetId": "f1-p0", "assignedObligationIds": ["file:src/a.py:10:abcd1234"], "outPath": "packets/out/f1-p0.json"}
  ]
}
```

Flows map brief:
```json
{"packetId":"f1-p0","kind":"flows-map-brief","waveId":"f1","assignedObligationIds":["file:src/a.py:10:abcd1234"],"repoRoot":"/repo","runDir":"/repo/docs/grill-flow/rid"}
```

Flows pack stdout (validate):
```json
{
  "waveId": "f1",
  "phase": "flows",
  "mode": "validate",
  "budgetRemaining": 8,
  "packets": [
    {"packetId": "f1-p0-val", "assignedObligationIds": ["file:src/a.py:10:abcd1234"], "outPath": "packets/out/f1-p0-val.json"}
  ]
}
```

Flows validate brief:
```json
{
  "packetId": "f1-p0-val",
  "kind": "flows-validate-brief",
  "waveId": "f1",
  "assignedObligationIds": ["file:src/a.py:10:abcd1234"],
  "mapPacketId": "f1-p0",
  "mapReturnPath": "packets/inbox/f1-p0.json",
  "repoRoot": "/repo",
  "runDir": "/repo/docs/grill-flow/rid"
}
```

CLI: `pack-flows` / `merge-flows`. Pack caps: ≤`validatorSlots` packets per wave; each graph map packet ≤`packetSizeFiles` assigned nodes; each flows map packet ≤`packetSizeObligations` assigned obligations.

### C9 Merge stdout

```json
{
  "waveId": "g1",
  "phase": "graph",
  "mergedPacketIds": ["g1-p0", "g1-p0-val"],
  "budgetRemaining": 5,
  "hardRejectsAdded": [],
  "droppedEdges": [],
  "graphClean": false,
  "flowsClean": false
}
```

Flows merge: **same shape** with `"phase": "flows"` and `waveId` like `"f1"`.

**Budget fields (Spec-aligned):** `graphBudget` / `lineBudget` on gate **are** the mutable phase budgets (not frozen ceilings). C8/C9 `budgetRemaining` is that phase’s current budget value (informational on pack; post-decrement on successful merge). Pack never changes it; successful merge −1; hardRejects still −1; `schema_error` / failed wave / `quality_error` → no −1; pack when already 0 → `budget_exhausted`.

### C10 Wave procedure (normative CLI)

Manifest path **only**: `packets/out/<waveId>-manifest.json` (example `packets/out/g1-manifest.json`).

1. `pack-graph --wave-id g1` → mode map; writes briefs + manifest `{"waveId":"g1","mapPacketIds":["g1-p0"],"validatePacketIds":[]}`; budget unchanged  
2. Subagents → `inbox-put --packet-id g1-p0` with C1  
3. `pack-graph --wave-id g1 --validate` → reads map inbox + manifest; writes validate briefs; sets `validatePacketIds` e.g. `["g1-p0-val"]`; budget unchanged  
4. Subagents → `inbox-put --packet-id g1-p0-val` with C2  
5. `merge-graph --wave-id g1` → merges **only** packetIds listed in that manifest (map+validate); **no** prefix matching; clears those inbox ids; **decrements graphBudget by 1**; returns C9  
6. Repeat until clean / `accept-partial --phase graph` / `budget_exhausted` (or `raise-budget --phase graph` then continue)  
7. `begin-flows` then the same with `pack-flows` / `merge-flows` / `lineBudget`

There is **no** `pack-validate` command and **no** `--validate-wave` flag — only `--validate` boolean on `pack-graph`/`pack-flows`.

### C11 Surface hash object

```json
{
  "mode": "file-set",
  "targets": ["a.py"],
  "baseOid": null,
  "headOid": null,
  "dirty": false,
  "testExclude": ["**/tests/**"],
  "skip": ["*.min.js"],
  "obligationIds": [],
  "pathNotesDigests": []
}
```

`obligationIds` and `pathNotesDigests` MUST be sorted ascending before hashing (Spec).

## C10 Wave procedure
Manifest path **only**: `packets/out/<waveId>-manifest.json` (example `packets/out/g1-manifest.json`).

1. `pack-graph --wave-id g1` → mode map; writes briefs + manifest `{"waveId":"g1","mapPacketIds":["g1-p0"],"validatePacketIds":[]}`; budget unchanged  
2. Subagents → `inbox-put --packet-id g1-p0` with C1  
3. `pack-graph --wave-id g1 --validate` → reads map inbox + manifest; writes validate briefs; sets `validatePacketIds` e.g. `["g1-p0-val"]`; budget unchanged  
4. Subagents → `inbox-put --packet-id g1-p0-val` with C2  
5. `merge-graph --wave-id g1` → merges **only** packetIds listed in that manifest (map+validate); **no** prefix matching; clears those inbox ids; **decrements graphBudget by 1**; returns C9  
6. Repeat until clean / `accept-partial --phase graph` / `budget_exhausted` (or `raise-budget --phase graph` then continue)  
7. `begin-flows` then the same with `pack-flows` / `merge-flows` / `lineBudget`

There is **no** `pack-validate` command and **no** `--validate-wave` flag — only `--validate` boolean on `pack-graph`/`pack-flows`.

## Commands
init-surface, init-run, recommend-gate, apply-gate, check-surface, inbox-put, inbox-clear,
pack-graph, merge-graph, pack-flows, merge-flows, status, accept-partial, begin-flows,
unwaive, resume-graph, raise-budget, abort-run, render, serve-start, serve-stop

## begin-flows / freeze / graphPartial
begin-flows always required; graph clean does not auto-start flows; graphPartial sticky ⇒ never complete; freeze complete|aborted blocks pack/merge/inbox-put; inbox-clear and check-surface still allowed.

## Viewer
`render` emits a read-only graph-first map browser by **copying** skill `viewer/{model.js,app.js,style.css}` into the run dir (never hand-author those files inside a run). `serve-http` hosts the run dir statically on loopback (`127.0.0.1` by default; optional `--bind`), blocks internal lock/token files, and adds read-only `GET /repo/<relpath>?start&end` (instance token + Host allowlist) for line snippets; `/repo` is additive and never writes.
Viewer path: `viewer_dir_for_helper`: if helper.parent.name == "scripts" → helper.parent.parent/viewer; else helper.parent/viewer

### Flow detail (inspector) — required behaviour
When a flow is open:
- **Prose** is structured sections (not one `Logic: …; In: …` string): **Logic** (one list item per `logic[]` entry), **In**, **Out**, **Consumers** (shorten `file:`/`symbol:` paths for display), plus **Pre** / **Impact** when semantic deleted.
- **Mapped lines** coalesce adjacent same-path / same-change obligations into runs (`173–185 · N lines`); one `/repo?start&end` fetch per run; show as a `<pre>` block. Do **not** emit one truncated row per adjacent line.
- Aggregates chips include **Structural** count; flow index rows show `· N lines`; run-level fragmentation banner when singleton-rate gate would fail.

### Layout / style locks (do not regress)
Agents editing `viewer/style.css` or inspector DOM **must** keep:
- Dark workspace tokens in `:root` (`--bg`, `--bg-elev`, `--fg`, `--muted`, `--border`, `--teal`, …); **no** network fonts.
- Shell: `html,body` column flex, `overflow: hidden`; `#shell` fills remaining height with `min-height: 0`.
- Inspector: fixed width, `overflow-x: hidden`, vertical scroll **only** on `#inspector-body` / empty state — **never** bidirectional panel scroll.
- Sticky header = labeled key/path/hop fields (grid), not one joined ` · ` line.
- Node labels wrap/clip inside node bounds (`wrapNodeLabel` + clipPath); never basename-only overflow.
- List rows: ellipsis; detail panes / prose / member snips: `overflow-wrap: anywhere`.
- Flow prose sections and member runs use bordered cards with clear label/body separation (see `#flow-prose`, `.flow-member-run` in `style.css`).
- Do not replace vanilla CSS with a framework, cards-in-hero clutter, or flat unsectioned inspector dumps.

`style.css` opens with a short lock comment repeating these constraints — keep that comment when editing.

## Artefacts
docs/grill-flow/<run-id>/ (warn if not gitignored)
