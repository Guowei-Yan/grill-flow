(function () {
  "use strict";

  function entriesNodes(graph) {
    if (!graph || !graph.nodes) return [];
    return Object.entries(graph.nodes);
  }

  function selectionObligationIds(key, node, obligations, ledger) {
    const out = [];
    const list = obligations || [];
    const led = ledger || {};
    for (let i = 0; i < list.length; i++) {
      const ob = list[i];
      const id = ob.obligationId;
      const entry = led[id];
      if (entry && entry.state === "waived") continue;
      if (node && node.kind === "file") {
        if (ob.path === node.path) out.push(id);
        continue;
      }
      if (node && node.kind === "symbol") {
        const d = entry && entry.disposition;
        const consumers = d && d.consumers;
        if (Array.isArray(consumers) && consumers.indexOf(key) !== -1) out.push(id);
      }
    }
    return out;
  }

  function fingerprint(logic) {
    if (!Array.isArray(logic)) return "";
    return logic
      .map(function (s) {
        return String(s).trim();
      })
      .filter(Boolean)
      .join("\n");
  }

  function flowGroups(ids, obById, ledger) {
    const led = ledger || {};
    const groups = Object.create(null);
    const order = [];
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const entry = led[id];
      if (!entry || entry.state !== "covered") continue;
      const d = entry.disposition;
      if (!d || d.kind !== "semantic") continue;
      const logic = d.logic || [];
      const fp = fingerprint(logic);
      let gkey;
      if (!fp) {
        gkey = "id:" + id;
      } else {
        gkey = "fp:" + fp;
      }
      let g = groups[gkey];
      if (!g) {
        let title = "(untitled flow)";
        for (let j = 0; j < logic.length; j++) {
          const t = String(logic[j]).trim();
          if (t) {
            title = t;
            break;
          }
        }
        g = { fingerprint: fp || id, title: title, memberIds: [] };
        groups[gkey] = g;
        order.push(g);
      }
      g.memberIds.push(id);
    }
    order.sort(function (a, b) {
      if (a.title < b.title) return -1;
      if (a.title > b.title) return 1;
      if (a.fingerprint < b.fingerprint) return -1;
      if (a.fingerprint > b.fingerprint) return 1;
      return 0;
    });
    return order;
  }

  function consumerLabel(c) {
    if (typeof c === "string") return c;
    if (c && typeof c === "object" && c.label != null) return "unknown:" + c.label;
    return "unknown:";
  }

  function flowProseSections(disposition) {
    if (!disposition) {
      return {
        logic: [],
        inputs: [],
        outputs: [],
        consumers: [],
        pre: null,
        impact: null,
      };
    }
    const logic = Array.isArray(disposition.logic)
      ? disposition.logic.map(function (x) {
          return String(x);
        }).filter(function (s) {
          return s.trim() !== "";
        })
      : [];
    const inputs = Array.isArray(disposition.inputs)
      ? disposition.inputs.map(function (x) {
          return String(x);
        })
      : [];
    const outputs = Array.isArray(disposition.outputs)
      ? disposition.outputs.map(function (x) {
          return String(x);
        })
      : [];
    const consumers = Array.isArray(disposition.consumers)
      ? disposition.consumers.map(consumerLabel)
      : [];
    let pre = null;
    let impact = null;
    if (disposition.change === "deleted") {
      if (disposition.preChangeRole != null) pre = String(disposition.preChangeRole);
      if (disposition.removalImpact != null) impact = String(disposition.removalImpact);
    }
    return {
      logic: logic,
      inputs: inputs,
      outputs: outputs,
      consumers: consumers,
      pre: pre,
      impact: impact,
    };
  }

  function flowProse(disposition) {
    const sec = flowProseSections(disposition);
    if (!disposition) return "";
    let s =
      "Logic: " +
      sec.logic.join("; ") +
      "; In: " +
      sec.inputs.join(", ") +
      "; Out: " +
      sec.outputs.join(", ") +
      "; Consumers: " +
      sec.consumers.join(", ");
    if (sec.pre != null) s += "; Pre: " + sec.pre;
    if (sec.impact != null) s += "; Impact: " + sec.impact;
    return s;
  }

  function coalesceMemberRuns(memberIds, obById) {
    const by = obById || {};
    const items = [];
    const ids = memberIds || [];
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const ob = by[id] || {};
      const line = ob.line != null ? Number(ob.line) : null;
      items.push({
        id: id,
        ob: ob,
        path: ob.path != null ? String(ob.path) : "",
        change: ob.change != null ? String(ob.change) : "",
        line: line,
      });
    }
    items.sort(function (a, b) {
      if (a.path < b.path) return -1;
      if (a.path > b.path) return 1;
      if (a.change < b.change) return -1;
      if (a.change > b.change) return 1;
      const al = a.line == null ? Infinity : a.line;
      const bl = b.line == null ? Infinity : b.line;
      if (al < bl) return -1;
      if (al > bl) return 1;
      if (a.id < b.id) return -1;
      if (a.id > b.id) return 1;
      return 0;
    });
    const runs = [];
    for (let i = 0; i < items.length; i++) {
      const cur = items[i];
      const prev = runs.length ? runs[runs.length - 1] : null;
      const canMerge =
        prev &&
        prev.path === cur.path &&
        prev.change === cur.change &&
        prev.endLine != null &&
        cur.line != null &&
        cur.line === prev.endLine + 1;
      if (canMerge) {
        prev.endLine = cur.line;
        prev.memberIds.push(cur.id);
        prev.obs.push(cur.ob);
      } else {
        runs.push({
          path: cur.path,
          change: cur.change,
          startLine: cur.line,
          endLine: cur.line,
          memberIds: [cur.id],
          obs: [cur.ob],
        });
      }
    }
    return runs;
  }

  function headerAggregates(ids, obById, ledger) {
    const led = ledger || {};
    const by = obById || {};
    let added = 0;
    let deleted = 0;
    let uncovered = 0;
    let structural = 0;
    const flowIds = [];
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const entry = led[id];
      if (!entry || entry.state === "waived") continue;
      const ob = by[id] || {};
      if (ob.change === "added") added++;
      if (ob.change === "deleted") deleted++;
      if (entry.state === "uncovered") uncovered++;
      if (entry.state === "covered") {
        const d = entry.disposition;
        if (d && d.kind === "structural") structural++;
        flowIds.push(id);
      }
    }
    const flows = flowGroups(flowIds, by, led).length;
    return {
      added: added,
      deleted: deleted,
      flows: flows,
      structural: structural,
      uncovered: uncovered,
    };
  }

  const FLOW_PATH_MIN_SEMANTIC = 8;
  const FLOW_SINGLETON_RATE_MAX = 0.4;

  function semanticFlowStats(ledger, obligations) {
    const led = ledger || {};
    const list = obligations || [];
    const pathByOid = Object.create(null);
    for (let i = 0; i < list.length; i++) {
      const ob = list[i];
      if (ob && ob.obligationId != null && ob.path != null) {
        pathByOid[ob.obligationId] = ob.path;
      }
    }
    const byPath = Object.create(null);
    const oids = Object.keys(led);
    for (let i = 0; i < oids.length; i++) {
      const oid = oids[i];
      const entry = led[oid];
      if (!entry || entry.state !== "covered") continue;
      const d = entry.disposition || {};
      if (d.kind !== "semantic") continue;
      let path = pathByOid[oid];
      if (path == null) {
        const er = d.evidenceRef || {};
        path = er.path != null ? er.path : "";
      }
      const fp = fingerprint(d.logic || []);
      const gkey = fp ? "fp:" + fp : "id:" + oid;
      if (!byPath[path]) byPath[path] = Object.create(null);
      if (!byPath[path][gkey]) byPath[path][gkey] = [];
      byPath[path][gkey].push(oid);
    }
    const violatingPaths = [];
    const pathKeys = Object.keys(byPath).sort();
    let semanticCount = 0;
    let groupCount = 0;
    let singletonGroups = 0;
    for (let p = 0; p < pathKeys.length; p++) {
      const path = pathKeys[p];
      const groups = byPath[path];
      const gkeys = Object.keys(groups);
      let sc = 0;
      let sg = 0;
      for (let g = 0; g < gkeys.length; g++) {
        const n = groups[gkeys[g]].length;
        sc += n;
        if (n === 1) sg++;
      }
      const gc = gkeys.length;
      const rate = gc ? sg / gc : 0;
      semanticCount += sc;
      groupCount += gc;
      singletonGroups += sg;
      if (sc >= FLOW_PATH_MIN_SEMANTIC && rate > FLOW_SINGLETON_RATE_MAX) {
        violatingPaths.push(path);
      }
    }
    return {
      semanticCount: semanticCount,
      groupCount: groupCount,
      singletonGroups: singletonGroups,
      singletonRate: groupCount ? singletonGroups / groupCount : 0,
      violatingPaths: violatingPaths,
    };
  }

  function changeMarker(change) {
    if (change === "added") return "+";
    if (change === "deleted") return "\u2212";
    if (change === "present") return "\u00b7";
    return "?";
  }

  function changeFilterMatch(change, mode, inventory) {
    if (mode === "all") return true;
    return change === mode;
  }

  function inventoryMode(surface) {
    if (surface && (surface.mode === "git-diff" || surface.mode === "file-set")) {
      return surface.mode;
    }
    return "git-diff";
  }

  function virtualWindow(scrollTop, viewportH, M, ROW_PX, overscan) {
    const row = ROW_PX == null ? 44 : ROW_PX;
    const over = overscan == null ? 5 : overscan;
    const start = Math.max(0, Math.floor(scrollTop / row) - over);
    const end = Math.min(M, start + Math.ceil(viewportH / row) + 2 * over);
    return { start: start, end: end };
  }

  function searchNodes(entries, query) {
    if (!query) return [];
    const q = String(query).toLowerCase();
    const scored = [];
    for (let i = 0; i < entries.length; i++) {
      const key = entries[i][0];
      const node = entries[i][1] || {};
      const keyL = String(key).toLowerCase();
      const pathL = node.path != null ? String(node.path).toLowerCase() : "";
      const qualL = node.qualname != null ? String(node.qualname).toLowerCase() : "";
      let tier = -1;
      if (keyL === q) tier = 0;
      else if (keyL.indexOf(q) === 0) tier = 1;
      else if (pathL.indexOf(q) !== -1) tier = 2;
      else if (qualL.indexOf(q) !== -1) tier = 3;
      else if (keyL.indexOf(q) !== -1) tier = 4;
      if (tier >= 0) scored.push({ tier: tier, key: key, entry: entries[i] });
    }
    scored.sort(function (a, b) {
      if (a.tier !== b.tier) return a.tier - b.tier;
      if (a.key < b.key) return -1;
      if (a.key > b.key) return 1;
      return 0;
    });
    return scored.map(function (s) {
      return s.entry;
    });
  }

  function runLevelHardRejects(hrs) {
    const list = hrs || [];
    const out = [];
    for (let i = 0; i < list.length; i++) {
      const h = list[i];
      if (h.phase === "graph" || h.obligationId == null) out.push(h);
    }
    return out;
  }

  function hardRejectsForSelection(hrs, selectionIds) {
    const set = Object.create(null);
    const ids = selectionIds || [];
    for (let i = 0; i < ids.length; i++) set[ids[i]] = true;
    const list = hrs || [];
    const out = [];
    for (let i = 0; i < list.length; i++) {
      const h = list[i];
      if (h.obligationId != null && set[h.obligationId]) out.push(h);
    }
    return out;
  }

  function defaultTab(chrome, flowGroupCount) {
    if (chrome === "all-structural") return "Structural";
    if (chrome === "only-delete") {
      return flowGroupCount === 0 ? "Structural" : "Flows";
    }
    return "Flows";
  }

  function truncateLabel(s, n) {
    const max = n == null ? 28 : n;
    const str = s == null ? "" : String(s);
    if (str.length <= max) return str;
    return str.slice(0, max);
  }

  function wrapNodeLabel(s, maxPerLine, maxLines) {
    const str = s == null ? "" : String(s);
    const per = maxPerLine == null ? 20 : maxPerLine;
    const linesMax = maxLines == null ? 2 : maxLines;
    const lines = [];
    let rest = str;
    while (rest.length && lines.length < linesMax) {
      if (rest.length <= per) {
        lines.push(rest);
        break;
      }
      if (lines.length === linesMax - 1) {
        lines.push(rest.slice(0, Math.max(1, per - 1)) + "\u2026");
        break;
      }
      let breakAt = -1;
      const lo = Math.floor(per * 0.45);
      for (let i = Math.min(per - 1, rest.length - 1); i >= lo; i--) {
        const ch = rest.charAt(i);
        if (ch === "/" || ch === "." || ch === "_" || ch === "-" || ch === ":") {
          breakAt = i + 1;
          break;
        }
      }
      if (breakAt <= 0) breakAt = per;
      lines.push(rest.slice(0, breakAt));
      rest = rest.slice(breakAt);
    }
    return lines;
  }

  function basename(path) {
    if (path == null) return "";
    const s = String(path);
    const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
    return i === -1 ? s : s.slice(i + 1);
  }

  function shortPathLabel(path) {
    if (path == null) return "";
    const s = String(path).replace(/\\/g, "/");
    const parts = s.split("/").filter(Boolean);
    if (!parts.length) return s;
    const nm = parts.indexOf("node_modules");
    if (nm >= 0 && nm + 1 < parts.length) {
      let i = nm + 1;
      let pkg = parts[i];
      if (pkg.charAt(0) === "@" && i + 1 < parts.length) {
        pkg = parts[i] + "/" + parts[i + 1];
        i += 2;
      } else {
        i += 1;
      }
      const rest = parts.slice(i).join("/");
      return rest ? pkg + "/" + rest : pkg;
    }
    if (parts.length >= 3) return parts.slice(-3).join("/");
    return parts.join("/");
  }

  function nodeLabel(key, node) {
    const n = node || {};
    if (n.kind === "symbol" || (n.qualname != null && n.kind !== "file")) {
      if (n.qualname) return String(n.qualname);
      return shortPathLabel(n.path) || basename(n.path) || String(key);
    }
    return shortPathLabel(n.path) || basename(n.path) || String(key);
  }

  function edgeColor(edgeKind) {
    if (edgeKind === "import") return "#6c8cff";
    if (edgeKind === "call") return "#c4a35a";
    if (edgeKind === "type") return "#9b7bdb";
    if (edgeKind === "shared_state") return "#5a9e8f";
    if (edgeKind === "event") return "#d4789c";
    return "#8b949e";
  }

  function stickyHeaderFields(key, node) {
    const n = node || {};
    const hop = n.hop;
    return {
      key: key,
      path: n.path != null ? n.path : null,
      qualname: n.qualname != null ? n.qualname : null,
      hopLabel: hop == null ? "\u2014" : hop,
    };
  }

  function snippetSync(ob) {
    const o = ob || {};
    const path = o.path != null ? o.path : null;
    const line = o.line != null ? o.line : null;
    if (typeof o.lineText === "string" && o.lineText !== "") {
      return { text: o.lineText, needRepo: false, path: path, line: line, unavailable: false };
    }
    if (o.change === "deleted") {
      return { text: "", needRepo: false, path: path, line: line, unavailable: true };
    }
    if (path != null && line != null) {
      return { text: "", needRepo: true, path: path, line: line, unavailable: false };
    }
    return { text: "", needRepo: false, path: path, line: line, unavailable: true };
  }

  function initialUserHop(runDoc) {
    const gate = runDoc && runDoc.gate;
    if (gate && typeof gate.N === "number" && isFinite(gate.N)) return gate.N;
    return 2;
  }

  function effectiveHop(userHop, selectedHop) {
    if (selectedHop == null) return userHop;
    return Math.max(userHop, selectedHop);
  }

  function layoutNodes(entries, effectiveN) {
    const COL_W = 280;
    const ROW_H = 72;
    const byHop = Object.create(null);
    for (let i = 0; i < entries.length; i++) {
      const key = entries[i][0];
      const node = entries[i][1] || {};
      const hop = node.hop == null ? 0 : node.hop;
      if (hop > effectiveN) continue;
      if (!byHop[hop]) byHop[hop] = [];
      byHop[hop].push({ key: key, node: node });
    }
    const out = Object.create(null);
    const hops = Object.keys(byHop)
      .map(Number)
      .sort(function (a, b) {
        return a - b;
      });
    for (let h = 0; h < hops.length; h++) {
      const hop = hops[h];
      const col = byHop[hop];
      col.sort(function (a, b) {
        if (a.key < b.key) return -1;
        if (a.key > b.key) return 1;
        return 0;
      });
      for (let i = 0; i < col.length; i++) {
        out[col[i].key] = {
          x: hop * COL_W,
          y: i * ROW_H,
          node: col[i].node,
        };
      }
    }
    return out;
  }

  function filterVisible(entries, edges, effectiveN, edgeKindOn) {
    const visibleKeys = Object.create(null);
    const nodes = [];
    for (let i = 0; i < entries.length; i++) {
      const key = entries[i][0];
      const node = entries[i][1] || {};
      const hop = node.hop == null ? 0 : node.hop;
      if (hop > effectiveN) continue;
      visibleKeys[key] = true;
      nodes.push(entries[i]);
    }
    const outEdges = [];
    const list = edges || [];
    for (let i = 0; i < list.length; i++) {
      const e = list[i];
      if (!visibleKeys[e.from] || !visibleKeys[e.to]) continue;
      if (edgeKindOn && e.edgeKind != null && edgeKindOn[e.edgeKind] === false) continue;
      outEdges.push(e);
    }
    return { entries: nodes, edges: outEdges };
  }

  globalThis.GrillFlowModel = {
    entriesNodes: entriesNodes,
    selectionObligationIds: selectionObligationIds,
    flowGroups: flowGroups,
    flowProse: flowProse,
    flowProseSections: flowProseSections,
    coalesceMemberRuns: coalesceMemberRuns,
    headerAggregates: headerAggregates,
    semanticFlowStats: semanticFlowStats,
    FLOW_PATH_MIN_SEMANTIC: FLOW_PATH_MIN_SEMANTIC,
    FLOW_SINGLETON_RATE_MAX: FLOW_SINGLETON_RATE_MAX,
    fingerprint: fingerprint,
    changeMarker: changeMarker,
    changeFilterMatch: changeFilterMatch,
    inventoryMode: inventoryMode,
    virtualWindow: virtualWindow,
    searchNodes: searchNodes,
    runLevelHardRejects: runLevelHardRejects,
    hardRejectsForSelection: hardRejectsForSelection,
    defaultTab: defaultTab,
    truncateLabel: truncateLabel,
    wrapNodeLabel: wrapNodeLabel,
    shortPathLabel: shortPathLabel,
    nodeLabel: nodeLabel,
    edgeColor: edgeColor,
    stickyHeaderFields: stickyHeaderFields,
    snippetSync: snippetSync,
    initialUserHop: initialUserHop,
    effectiveHop: effectiveHop,
    layoutNodes: layoutNodes,
    filterVisible: filterVisible,
  };
})();
