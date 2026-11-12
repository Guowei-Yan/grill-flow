(function () {
  "use strict";

  const M = globalThis.GrillFlowModel;
  const EDGE_KINDS = ["import", "call", "type", "shared_state", "event"];
  const FIT_PAD = 24;
  const NODE_W = 176;
  const NODE_H = 52;
  const LABEL_CHARS = 18;
  const LABEL_LINES = 2;
  const ROW_PX = 44;
  const SNIP_MAX = 72;
  const ELLIPSIS = "\u2026";
  const EN_DASH = "\u2013";
  const WHY_NO_DISP = "no disposition";
  const SYMBOL_EMPTY = "No obligations cite this symbol as consumer.";

  let payload = {};
  let graph = null;
  let ledger = null;
  let obligations = null;
  let run = null;
  let surface = null;
  let serverInfo = null;
  let userHop = 2;
  let edgeKindOn = {
    import: true,
    call: true,
    type: true,
    shared_state: true,
    event: true,
  };
  let selectedKey = null;
  let consumerKeys = Object.create(null);
  let panX = 0;
  let panY = 0;
  let scale = 1;
  let layout = Object.create(null);
  let svg = null;
  let viewport = null;
  let drag = null;
  let changeMode = "all";
  let activeTab = "Flows";
  let openFlowFp = null;
  let expandedUncovered = null;
  let snippetCache = Object.create(null);
  let inspectorGen = 0;
  let obById = Object.create(null);

  function svgEl(name) {
    return document.createElementNS("http://www.w3.org/2000/svg", name);
  }

  function clampScale(s) {
    return Math.min(4, Math.max(0.25, s));
  }

  function setTransform(x, y, s) {
    panX = x;
    panY = y;
    scale = clampScale(s);
    if (viewport) {
      viewport.setAttribute(
        "transform",
        "translate(" + panX + "," + panY + ") scale(" + scale + ")"
      );
    }
  }

  function centerOnNode(key, lay, s) {
    const n = lay[key];
    if (!n || !svg) return;
    const cx = svg.clientWidth / 2;
    const cy = svg.clientHeight / 2;
    setTransform(cx - n.x * s, cy - n.y * s, s);
  }

  function fitToGraph(lay) {
    const keys = Object.keys(lay);
    if (!keys.length || !svg) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (let i = 0; i < keys.length; i++) {
      const p = lay[keys[i]];
      minX = Math.min(minX, p.x - NODE_W / 2);
      minY = Math.min(minY, p.y - NODE_H / 2);
      maxX = Math.max(maxX, p.x + NODE_W / 2);
      maxY = Math.max(maxY, p.y + NODE_H / 2);
    }
    const w = maxX - minX + FIT_PAD * 2;
    const h = maxY - minY + FIT_PAD * 2;
    const vw = Math.max(1, svg.clientWidth);
    const vh = Math.max(1, svg.clientHeight);
    const s = clampScale(Math.min(vw / w, vh / h, 1));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    setTransform(vw / 2 - cx * s, vh / 2 - cy * s, s);
  }

  function initialView(lay) {
    const keys = Object.keys(lay);
    if (!keys.length || !svg) return;
    let minHop = Infinity;
    for (let i = 0; i < keys.length; i++) {
      const n = lay[keys[i]].node || {};
      const hop = n.hop == null ? 0 : n.hop;
      if (hop < minHop) minHop = hop;
    }
    let minY = Infinity;
    let maxY = -Infinity;
    let minX = Infinity;
    let maxX = -Infinity;
    let count = 0;
    for (let i = 0; i < keys.length; i++) {
      const p = lay[keys[i]];
      const hop = (p.node && p.node.hop != null) ? p.node.hop : 0;
      if (hop > minHop) continue;
      count += 1;
      minX = Math.min(minX, p.x - NODE_W / 2);
      maxX = Math.max(maxX, p.x + NODE_W / 2);
      minY = Math.min(minY, p.y - NODE_H / 2);
      maxY = Math.max(maxY, p.y + NODE_H / 2);
    }
    if (!count) {
      fitToGraph(lay);
      return;
    }
    const vw = Math.max(1, svg.clientWidth);
    const vh = Math.max(1, svg.clientHeight);
    const w = Math.max(NODE_W + FIT_PAD * 2, maxX - minX + FIT_PAD * 2);
    const h = Math.max(NODE_H + FIT_PAD * 2, maxY - minY + FIT_PAD * 2);
    const s = clampScale(Math.min(vw / w, vh / h, 1.25));
    setTransform(
      FIT_PAD - minX * s,
      vh / 2 - ((minY + maxY) / 2) * s,
      s
    );
  }

  function selectedHop() {
    if (!selectedKey || !graph || !graph.nodes) return null;
    const node = graph.nodes[selectedKey];
    if (!node) return null;
    return node.hop == null ? null : node.hop;
  }

  function effectiveN() {
    return M.effectiveHop(userHop, selectedHop());
  }

  function chromeMode() {
    return (payload && payload.chrome) || (run && run.chrome) || "";
  }

  function invMode() {
    return M.inventoryMode(surface);
  }

  function rebuildObById() {
    obById = Object.create(null);
    const list = obligations || [];
    for (let i = 0; i < list.length; i++) {
      const ob = list[i];
      if (ob && ob.obligationId != null) obById[ob.obligationId] = ob;
    }
  }

  function trunc72(s) {
    const str = s == null ? "" : String(s);
    if (str.length <= SNIP_MAX) return str;
    return str.slice(0, SNIP_MAX);
  }

  function repoUrl(path, startLine, endLine) {
    const segs = String(path)
      .split("/")
      .map(function (p) {
        return encodeURIComponent(p);
      })
      .join("/");
    const t =
      serverInfo && serverInfo.instanceId != null
        ? String(serverInfo.instanceId)
        : "";
    const start = startLine;
    const end = endLine == null ? startLine : endLine;
    return (
      "/repo/" +
      segs +
      "?start=" +
      encodeURIComponent(String(start)) +
      "&end=" +
      encodeURIComponent(String(end)) +
      "&t=" +
      encodeURIComponent(t)
    );
  }

  function cacheKey(path, line, endLine) {
    if (endLine != null && endLine !== line) {
      return String(path) + ":" + String(line) + "-" + String(endLine);
    }
    return String(path) + ":" + String(line);
  }

  function snippetTextSync(ob) {
    const sync = M.snippetSync(ob);
    if (sync.unavailable) return ELLIPSIS;
    if (!sync.needRepo) return sync.text || ELLIPSIS;
    const k = cacheKey(sync.path, sync.line);
    if (Object.prototype.hasOwnProperty.call(snippetCache, k)) {
      return snippetCache[k] || ELLIPSIS;
    }
    return ELLIPSIS;
  }

  function ensureSnippet(ob, gen, onDone) {
    const sync = M.snippetSync(ob);
    if (!sync.needRepo || sync.unavailable) {
      if (onDone) onDone(snippetTextSync(ob));
      return;
    }
    const k = cacheKey(sync.path, sync.line);
    if (Object.prototype.hasOwnProperty.call(snippetCache, k)) {
      if (onDone) onDone(snippetCache[k] || ELLIPSIS);
      return;
    }
    fetch(repoUrl(sync.path, sync.line, sync.line))
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (j) {
        const text =
          j && j.text != null && String(j.text) !== ""
            ? String(j.text)
            : ELLIPSIS;
        snippetCache[k] = text;
        if (gen === inspectorGen && onDone) onDone(text);
      })
      .catch(function () {
        snippetCache[k] = ELLIPSIS;
        if (gen === inspectorGen && onDone) onDone(ELLIPSIS);
      });
  }

  function ensureRangeSnippet(path, startLine, endLine, change, obs, gen, onDone) {
    if (change === "deleted") {
      if (onDone) onDone(ELLIPSIS);
      return;
    }
    if (path == null || startLine == null) {
      if (onDone) onDone(ELLIPSIS);
      return;
    }
    const end = endLine == null ? startLine : endLine;
    if (startLine === end && obs && obs.length === 1) {
      ensureSnippet(obs[0], gen, onDone);
      return;
    }
    const k = cacheKey(path, startLine, end);
    if (Object.prototype.hasOwnProperty.call(snippetCache, k)) {
      if (onDone) onDone(snippetCache[k] || ELLIPSIS);
      return;
    }
    // Prefer concatenated lineText when every row has it
    let allSync = true;
    const parts = [];
    if (obs && obs.length) {
      for (let i = 0; i < obs.length; i++) {
        const sync = M.snippetSync(obs[i]);
        if (sync.unavailable || sync.needRepo || !sync.text) {
          allSync = false;
          break;
        }
        parts.push(sync.text);
      }
    } else {
      allSync = false;
    }
    if (allSync) {
      const joined = parts.join("\n");
      snippetCache[k] = joined;
      if (onDone) onDone(joined);
      return;
    }
    fetch(repoUrl(path, startLine, end))
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (j) {
        const text =
          j && j.text != null && String(j.text) !== ""
            ? String(j.text)
            : ELLIPSIS;
        snippetCache[k] = text;
        if (gen === inspectorGen && onDone) onDone(text);
      })
      .catch(function () {
        snippetCache[k] = ELLIPSIS;
        if (gen === inspectorGen && onDone) onDone(ELLIPSIS);
      });
  }

  function renderFlowProse(parent, disposition) {
    const wrap = document.createElement("div");
    wrap.id = "flow-prose";
    wrap.className = "flow-prose";
    const sec = M.flowProseSections(disposition);
    function addSection(label, values, asList) {
      if (!values || (Array.isArray(values) && values.length === 0)) return;
      const block = document.createElement("div");
      block.className = "flow-prose-section";
      const lab = document.createElement("div");
      lab.className = "flow-prose-label";
      lab.textContent = label;
      block.appendChild(lab);
      const body = document.createElement("div");
      body.className = "flow-prose-body";
      if (asList && Array.isArray(values)) {
        const ul = document.createElement("ul");
        for (let i = 0; i < values.length; i++) {
          const li = document.createElement("li");
          let t = values[i];
          if (label === "Consumers" && t.indexOf("file:") === 0) {
            t = M.shortPathLabel(t.slice(5)) || t;
          } else if (label === "Consumers" && t.indexOf("symbol:") === 0) {
            t = t.slice(7);
          }
          li.textContent = t;
          ul.appendChild(li);
        }
        body.appendChild(ul);
      } else if (Array.isArray(values)) {
        body.textContent = values.join(", ");
      } else {
        body.textContent = String(values);
      }
      block.appendChild(body);
      wrap.appendChild(block);
    }
    addSection("Logic", sec.logic, true);
    addSection("In", sec.inputs, false);
    addSection("Out", sec.outputs, false);
    addSection("Consumers", sec.consumers, true);
    if (sec.pre != null) addSection("Pre", sec.pre, false);
    if (sec.impact != null) addSection("Impact", sec.impact, false);
    parent.appendChild(wrap);
  }

  function fillPathNotes(panel, notes) {
    while (panel.firstChild) panel.removeChild(panel.firstChild);
    const h2 = document.createElement("h2");
    h2.textContent = "PathNotes";
    panel.appendChild(h2);
    const ul = document.createElement("ul");
    for (let i = 0; i < notes.length; i++) {
      const n = notes[i] || {};
      const li = document.createElement("li");
      let t =
        (n.path != null ? String(n.path) : "") +
        " · " +
        (n.kind != null ? String(n.kind) : "");
      if (n.from != null || n.to != null) {
        t +=
          " (" +
          (n.from != null ? String(n.from) : "") +
          " → " +
          (n.to != null ? String(n.to) : "") +
          ")";
      }
      li.textContent = t;
      ul.appendChild(li);
    }
    panel.appendChild(ul);
    panel.hidden = notes.length === 0;
    panel.setAttribute("data-ready", "1");
  }

  async function mountPathNotes() {
    const existing = document.getElementById("path-notes-panel");
    if (existing) {
      let notes = [];
      try {
        notes = JSON.parse(existing.getAttribute("data-path-notes") || "[]");
      } catch (e) {
        notes = [];
      }
      if (!Array.isArray(notes)) notes = [];
      fillPathNotes(existing, notes);
      return;
    }
    let notes = [];
    try {
      const r = await fetch("pathNotes.json");
      if (r.ok) {
        notes = await r.json();
      } else {
        notes = [];
      }
    } catch (e) {
      notes = [];
    }
    if (!Array.isArray(notes) || notes.length === 0) return;
    const panel = document.createElement("section");
    panel.id = "path-notes-panel";
    const banner = document.getElementById("hard-reject-strip");
    if (banner && banner.parentNode) {
      banner.parentNode.insertBefore(panel, banner.nextSibling);
    } else {
      document.body.insertBefore(panel, document.body.firstChild);
    }
    fillPathNotes(panel, notes);
  }

  function updateStatusBanner() {
    const el = document.getElementById("run-status-banner");
    if (!el) return;
    if (el.textContent === "invalid artefact JSON") return;
    const runStatus =
      (run && run.runStatus != null ? run.runStatus : null) ||
      payload.runStatus ||
      null;
    const graphPartial =
      (run && run.graphPartial != null ? run.graphPartial : null) != null
        ? run.graphPartial
        : payload.graphPartial;
    const parts = [];
    if (runStatus != null && runStatus !== "complete") {
      parts.push("runStatus: " + runStatus);
    }
    if (graphPartial === true) {
      parts.push("graphPartial");
    }
    el.textContent = parts.join(" · ");
  }

  function updateFragmentationBanner() {
    let el = document.getElementById("flow-fragmentation-banner");
    if (!el) {
      el = document.createElement("div");
      el.id = "flow-fragmentation-banner";
      const status = document.getElementById("run-status-banner");
      if (status && status.parentNode) {
        status.parentNode.insertBefore(el, status.nextSibling);
      } else {
        document.body.insertBefore(el, document.body.firstChild);
      }
    }
    if (!ledger || !obligations) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    const stats = M.semanticFlowStats(ledger, obligations);
    const bad = stats.violatingPaths || [];
    if (!bad.length) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    const sample = bad.slice(0, 3).join(", ");
    const more = bad.length > 3 ? " (+" + (bad.length - 3) + " more)" : "";
    el.textContent =
      "Flow map is line-fragmented (singleton rate too high on: " +
      sample +
      more +
      "). Re-run flows with shared logic per behaviour.";
  }

  function updateHardRejectStrip() {
    const el = document.getElementById("hard-reject-strip");
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    const hrs = M.runLevelHardRejects((run && run.hardRejects) || []);
    if (!hrs.length) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    for (let i = 0; i < hrs.length; i++) {
      const h = hrs[i] || {};
      const span = document.createElement("span");
      span.textContent =
        (h.kind != null ? String(h.kind) : "?") +
        (h.phase != null ? " [" + h.phase + "]" : "");
      el.appendChild(span);
      if (i < hrs.length - 1) el.appendChild(document.createTextNode(" · "));
    }
  }

  function clearConsumers() {
    consumerKeys = Object.create(null);
  }

  function setConsumersFromFlow(group) {
    clearConsumers();
    if (!group || !ledger) return;
    const members = group.memberIds || [];
    for (let i = 0; i < members.length; i++) {
      const entry = ledger[members[i]];
      const d = entry && entry.disposition;
      if (!d || !Array.isArray(d.consumers)) continue;
      for (let j = 0; j < d.consumers.length; j++) {
        const c = d.consumers[j];
        if (typeof c === "string" && graph && graph.nodes && graph.nodes[c]) {
          consumerKeys[c] = true;
        }
      }
    }
  }

  function matchesChange(ob) {
    return M.changeFilterMatch(ob && ob.change, changeMode, invMode());
  }

  function filteredFlowGroups(ids) {
    const groups = M.flowGroups(ids, obById, ledger);
    const out = [];
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i];
      const kept = [];
      for (let j = 0; j < g.memberIds.length; j++) {
        const id = g.memberIds[j];
        if (matchesChange(obById[id])) kept.push(id);
      }
      if (kept.length) {
        out.push({
          fingerprint: g.fingerprint,
          title: g.title,
          memberIds: kept,
        });
      }
    }
    return out;
  }

  function uncoveredRows(ids) {
    const chrome = chromeMode();
    const hideObs = chrome === "only-delete" || chrome === "all-structural";
    const obsRows = [];
    if (!hideObs) {
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        const entry = ledger && ledger[id];
        if (!entry || entry.state !== "uncovered") continue;
        const ob = obById[id];
        if (!ob || !matchesChange(ob)) continue;
        obsRows.push({ type: "ob", id: id, ob: ob, entry: entry });
      }
      obsRows.sort(function (a, b) {
        const pa = a.ob.path != null ? String(a.ob.path) : "";
        const pb = b.ob.path != null ? String(b.ob.path) : "";
        if (pa < pb) return -1;
        if (pa > pb) return 1;
        const la = a.ob.line != null ? a.ob.line : 0;
        const lb = b.ob.line != null ? b.ob.line : 0;
        if (la < lb) return -1;
        if (la > lb) return 1;
        if (a.id < b.id) return -1;
        if (a.id > b.id) return 1;
        return 0;
      });
    }
    const hrs = M.hardRejectsForSelection(
      (run && run.hardRejects) || [],
      ids
    );
    hrs.sort(function (a, b) {
      const ka = a.kind != null ? String(a.kind) : "";
      const kb = b.kind != null ? String(b.kind) : "";
      if (ka < kb) return -1;
      if (ka > kb) return 1;
      const oa = a.obligationId != null ? String(a.obligationId) : "";
      const ob = b.obligationId != null ? String(b.obligationId) : "";
      if (oa < ob) return -1;
      if (oa > ob) return 1;
      const ca = a.componentId != null ? String(a.componentId) : "";
      const cb = b.componentId != null ? String(b.componentId) : "";
      if (ca < cb) return -1;
      if (ca > cb) return 1;
      return 0;
    });
    const hrRows = [];
    for (let i = 0; i < hrs.length; i++) {
      hrRows.push({ type: "hr", hr: hrs[i], idx: i });
    }
    return obsRows.concat(hrRows);
  }

  function structuralRows(ids) {
    const out = [];
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const entry = ledger && ledger[id];
      if (!entry || entry.state !== "covered") continue;
      const d = entry.disposition;
      if (!d || d.kind !== "structural") continue;
      const ob = obById[id];
      if (!ob || !matchesChange(ob)) continue;
      out.push({ id: id, ob: ob, entry: entry, disposition: d });
    }
    return out;
  }

  function mountChangeToolbar(parent) {
    const wrap = document.createElement("div");
    wrap.id = "change-toolbar";
    const inv = invMode();
    const modes =
      inv === "file-set"
        ? [
            { mode: "all", label: "All" },
            { mode: "present", label: "Present" },
          ]
        : [
            { mode: "all", label: "All" },
            { mode: "added", label: "Added" },
            { mode: "deleted", label: "Removed" },
          ];
    for (let i = 0; i < modes.length; i++) {
      const m = modes[i];
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = m.label;
      if (changeMode === m.mode) btn.setAttribute("aria-pressed", "true");
      btn.addEventListener(
        "click",
        (function (mode) {
          return function () {
            changeMode = mode;
            updateInspector();
          };
        })(m.mode)
      );
      wrap.appendChild(btn);
    }
    const legend = document.createElement("span");
    legend.className = "legend";
    legend.textContent = "+ / \u2212 / \u00b7 / ?";
    wrap.appendChild(legend);
    parent.appendChild(wrap);
  }

  function mountTabs(parent) {
    const wrap = document.createElement("div");
    wrap.id = "inspector-tabs";
    const tabs = ["Flows", "Uncovered", "Structural"];
    for (let i = 0; i < tabs.length; i++) {
      const name = tabs[i];
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = name;
      if (activeTab === name) btn.setAttribute("aria-pressed", "true");
      btn.addEventListener(
        "click",
        (function (tab) {
          return function () {
            activeTab = tab;
            if (tab !== "Flows") {
              openFlowFp = null;
              clearConsumers();
              redraw(false);
            }
            if (tab !== "Uncovered") expandedUncovered = null;
            updateInspector();
          };
        })(name)
      );
      wrap.appendChild(btn);
    }
    parent.appendChild(wrap);
  }

  function virtualList(parent, items, renderRow, gen) {
    const meta = document.createElement("div");
    meta.id = "virtual-window-label";
    const scroller = document.createElement("div");
    scroller.className = "virtual-scroller";
    scroller.style.height = "280px";
    scroller.style.position = "relative";
    const spacer = document.createElement("div");
    spacer.style.position = "relative";
    spacer.style.height = items.length * ROW_PX + "px";
    scroller.appendChild(spacer);

    function paint() {
      while (spacer.firstChild) spacer.removeChild(spacer.firstChild);
      const vw = M.virtualWindow(
        scroller.scrollTop,
        scroller.clientHeight,
        items.length,
        ROW_PX,
        5
      );
      const start = vw.start;
      const end = vw.end;
      if (items.length === 0) {
        meta.textContent = "0" + EN_DASH + "0 of 0";
      } else {
        meta.textContent =
          start + 1 + EN_DASH + end + " of " + items.length;
      }
      for (let i = start; i < end; i++) {
        const row = document.createElement("div");
        row.className = "row";
        row.style.position = "absolute";
        row.style.left = "0";
        row.style.right = "0";
        row.style.top = i * ROW_PX + "px";
        row.style.height = ROW_PX + "px";
        row.style.boxSizing = "border-box";
        renderRow(row, items[i], i, gen);
        spacer.appendChild(row);
      }
    }

    scroller.addEventListener("scroll", paint);
    parent.appendChild(meta);
    parent.appendChild(scroller);
    paint();
    return { paint: paint, scroller: scroller };
  }

  function renderFlowsTab(parent, ids, gen) {
    const groups = filteredFlowGroups(ids);
    const detail = document.createElement("div");
    detail.id = "flow-detail";
    virtualList(
      parent,
      groups,
      function (row, g) {
        row.style.cursor = "pointer";
        const n = g.memberIds ? g.memberIds.length : 0;
        row.textContent = g.title + " \u00b7 " + n + " lines";
        if (openFlowFp === g.fingerprint) {
          row.setAttribute("data-open", "1");
        }
        row.addEventListener("click", function () {
          if (openFlowFp === g.fingerprint) {
            openFlowFp = null;
            clearConsumers();
          } else {
            openFlowFp = g.fingerprint;
            setConsumersFromFlow(g);
          }
          redraw(false);
          updateInspector();
        });
      },
      gen
    );
    parent.appendChild(detail);
    if (openFlowFp == null) return;
    let open = null;
    for (let i = 0; i < groups.length; i++) {
      if (groups[i].fingerprint === openFlowFp) {
        open = groups[i];
        break;
      }
    }
    if (!open) return;
    const first = open.memberIds[0];
    const entry = ledger && ledger[first];
    const d = entry && entry.disposition;
    renderFlowProse(detail, d);
    const members = document.createElement("div");
    members.id = "flow-members";
    const runs = M.coalesceMemberRuns(open.memberIds, obById);
    for (let j = 0; j < runs.length; j++) {
      const run = runs[j];
      const block = document.createElement("div");
      block.className = "flow-member-run";
      const head = document.createElement("div");
      head.className = "flow-member-head";
      const marker = M.changeMarker(run.change);
      let lineLabel = "";
      if (run.startLine == null) lineLabel = "?";
      else if (run.endLine == null || run.endLine === run.startLine) {
        lineLabel = String(run.startLine);
      } else {
        lineLabel = String(run.startLine) + EN_DASH + String(run.endLine);
      }
      const count =
        run.memberIds.length > 1 ? " · " + run.memberIds.length + " lines" : "";
      head.textContent = marker + " " + lineLabel + count;
      block.appendChild(head);
      const snipEl = document.createElement("pre");
      snipEl.className = "flow-member-snip";
      snipEl.textContent = ELLIPSIS;
      block.appendChild(snipEl);
      members.appendChild(block);
      ensureRangeSnippet(
        run.path,
        run.startLine,
        run.endLine,
        run.change,
        run.obs,
        gen,
        function (text) {
          snipEl.textContent = text;
        }
      );
    }
    detail.appendChild(members);
  }

  function uncoveredKey(row) {
    if (row.type === "ob") return "ob:" + row.id;
    return (
      "hr:" +
      (row.hr.kind != null ? String(row.hr.kind) : "") +
      ":" +
      (row.hr.obligationId != null ? String(row.hr.obligationId) : "") +
      ":" +
      (row.hr.componentId != null ? String(row.hr.componentId) : "") +
      ":" +
      String(row.idx)
    );
  }

  function renderUncoveredTab(parent, ids, gen) {
    const rows = uncoveredRows(ids);
    const sticky = document.createElement("div");
    sticky.id = "uncovered-sticky";
    virtualList(
      parent,
      rows,
      function (rowEl, row) {
        rowEl.style.cursor = "pointer";
        const key = uncoveredKey(row);
        if (expandedUncovered === key) rowEl.setAttribute("data-open", "1");
        if (row.type === "ob") {
          const ob = row.ob;
          const marker = M.changeMarker(ob.change);
          const lineNo = ob.line != null ? String(ob.line) : "";
          const snipEl = document.createElement("span");
          snipEl.textContent = trunc72(snippetTextSync(ob));
          const why = document.createElement("span");
          why.textContent = " " + WHY_NO_DISP;
          rowEl.appendChild(
            document.createTextNode(marker + " " + lineNo + " ")
          );
          rowEl.appendChild(snipEl);
          rowEl.appendChild(why);
          ensureSnippet(ob, gen, function (text) {
            snipEl.textContent = trunc72(text);
          });
        } else {
          const h = row.hr || {};
          const shortId =
            h.obligationId != null
              ? String(h.obligationId)
              : h.componentId != null
                ? String(h.componentId)
                : "";
          rowEl.textContent =
            (h.kind != null ? String(h.kind) : "?") +
            " " +
            shortId +
            (h.phase != null ? " [" + h.phase + "]" : "");
        }
        rowEl.addEventListener("click", function () {
          expandedUncovered = expandedUncovered === key ? null : key;
          updateInspector();
        });
      },
      gen
    );
    parent.appendChild(sticky);
    if (expandedUncovered == null) return;
    let open = null;
    for (let i = 0; i < rows.length; i++) {
      if (uncoveredKey(rows[i]) === expandedUncovered) {
        open = rows[i];
        break;
      }
    }
    if (!open) return;
    if (open.type === "ob") {
      const ob = open.ob;
      const full = document.createElement("div");
      const snip = document.createElement("div");
      snip.textContent = snippetTextSync(ob);
      full.appendChild(snip);
      ensureSnippet(ob, gen, function (text) {
        snip.textContent = text;
      });
      const meta = document.createElement("div");
      meta.textContent =
        "path: " +
        (ob.path != null ? String(ob.path) : "") +
        " · obligationId: " +
        open.id +
        " · state: " +
        (open.entry && open.entry.state != null
          ? String(open.entry.state)
          : "") +
        " · why: " +
        WHY_NO_DISP;
      full.appendChild(meta);
      sticky.appendChild(full);
    } else {
      const h = open.hr || {};
      const full = document.createElement("div");
      full.textContent =
        "phase: " +
        (h.phase != null ? String(h.phase) : "") +
        " · kind: " +
        (h.kind != null ? String(h.kind) : "") +
        " · componentId: " +
        (h.componentId != null ? String(h.componentId) : "") +
        " · obligationId: " +
        (h.obligationId != null ? String(h.obligationId) : "") +
        " · packetId: " +
        (h.packetId != null ? String(h.packetId) : "");
      sticky.appendChild(full);
    }
  }

  function renderStructuralTab(parent, ids, gen) {
    const rows = structuralRows(ids);
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      const wrap = document.createElement("div");
      wrap.className = "row structural-row";
      const cls =
        r.disposition.structuralClass != null
          ? String(r.disposition.structuralClass)
          : "";
      const head = document.createElement("div");
      const snipEl = document.createElement("span");
      snipEl.textContent = trunc72(snippetTextSync(r.ob));
      head.appendChild(document.createTextNode(cls + " "));
      head.appendChild(snipEl);
      wrap.appendChild(head);
      ensureSnippet(r.ob, gen, function (text) {
        snipEl.textContent = trunc72(text);
      });
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "full";
      details.appendChild(summary);
      const full = document.createElement("div");
      full.textContent = snippetTextSync(r.ob);
      details.appendChild(full);
      ensureSnippet(r.ob, gen, function (text) {
        full.textContent = text;
      });
      wrap.appendChild(details);
      const deleted =
        r.ob.change === "deleted" || r.disposition.change === "deleted";
      if (deleted && r.disposition.removalNote != null) {
        const note = document.createElement("div");
        note.textContent = String(r.disposition.removalNote);
        wrap.appendChild(note);
      }
      parent.appendChild(wrap);
    }
  }

  function updateInspector() {
    const empty = document.getElementById("inspector-empty");
    const body = document.getElementById("inspector-body");
    if (!empty || !body) return;
    inspectorGen++;
    const gen = inspectorGen;
    if (!selectedKey || !graph || !graph.nodes || !graph.nodes[selectedKey]) {
      empty.hidden = false;
      empty.textContent = "click a node";
      body.hidden = true;
      while (body.firstChild) body.removeChild(body.firstChild);
      return;
    }
    empty.hidden = true;
    body.hidden = false;
    while (body.firstChild) body.removeChild(body.firstChild);
    const node = graph.nodes[selectedKey];
    const fields = M.stickyHeaderFields(selectedKey, node);
    const header = document.createElement("div");
    header.id = "sticky-header";
    header.className = "inspector-header";
    function addField(label, value) {
      const row = document.createElement("div");
      row.className = "inspector-field";
      const lab = document.createElement("div");
      lab.className = "inspector-label";
      lab.textContent = label;
      const val = document.createElement("div");
      val.className = "inspector-value";
      val.textContent = value == null ? "" : String(value);
      row.appendChild(lab);
      row.appendChild(val);
      header.appendChild(row);
    }
    addField("key", fields.key);
    addField("path", fields.path != null ? fields.path : "—");
    addField("hop", fields.hopLabel);
    if (node.kind === "symbol" || fields.qualname != null) {
      addField("qualname", fields.qualname != null ? fields.qualname : "—");
    }
    body.appendChild(header);
    const ids = M.selectionObligationIds(
      selectedKey,
      node,
      obligations,
      ledger
    );
    if (node.kind === "symbol" && ids.length === 0) {
      const msg = document.createElement("div");
      msg.id = "symbol-empty";
      msg.textContent = SYMBOL_EMPTY;
      body.appendChild(msg);
      return;
    }
    const agg = M.headerAggregates(ids, obById, ledger);
    const aggEl = document.createElement("div");
    aggEl.id = "header-aggregates";
    function addChip(text) {
      const chip = document.createElement("span");
      chip.className = "agg-chip";
      chip.textContent = text;
      aggEl.appendChild(chip);
    }
    addChip("+" + agg.added);
    addChip("\u2212" + agg.deleted);
    addChip("Flows " + agg.flows);
    addChip("Structural " + agg.structural);
    addChip("Uncovered " + agg.uncovered);
    body.appendChild(aggEl);
    mountChangeToolbar(body);
    mountTabs(body);
    const panel = document.createElement("div");
    panel.id = "inspector-tab-panel";
    body.appendChild(panel);
    if (activeTab === "Flows") renderFlowsTab(panel, ids, gen);
    else if (activeTab === "Uncovered") renderUncoveredTab(panel, ids, gen);
    else renderStructuralTab(panel, ids, gen);
  }

  function selectNode(key, opts) {
    selectedKey = key;
    clearConsumers();
    openFlowFp = null;
    expandedUncovered = null;
    changeMode = "all";
    const node =
      graph && graph.nodes && graph.nodes[key] ? graph.nodes[key] : null;
    const ids = M.selectionObligationIds(key, node, obligations, ledger);
    const groups = M.flowGroups(ids, obById, ledger);
    activeTab = M.defaultTab(chromeMode(), groups.length);
    updateInspector();
    redraw(opts && opts.center);
  }

  function clearSelection() {
    selectedKey = null;
    clearConsumers();
    openFlowFp = null;
    expandedUncovered = null;
    updateInspector();
    redraw(false);
  }

  function nodeStroke(key) {
    if (key === selectedKey) return "#3db8a8";
    if (consumerKeys[key]) return "#ff6b6b";
    return "#8b949e";
  }

  function edgeStroke(e) {
    if (selectedKey && (e.from === selectedKey || e.to === selectedKey)) {
      return "#3db8a8";
    }
    if (consumerKeys[e.from] || consumerKeys[e.to]) return "#ff6b6b";
    return M.edgeColor(e.edgeKind);
  }

  function drawNode(g, key, pos) {
    const node = pos.node || {};
    const fullLabel = M.nodeLabel(key, node);
    const lines = M.wrapNodeLabel(fullLabel, LABEL_CHARS, LABEL_LINES);
    const stroke = nodeStroke(key);
    const group = svgEl("g");
    group.setAttribute("data-node-key", key);
    group.style.cursor = "pointer";
    const title = svgEl("title");
    title.textContent = fullLabel + "\n" + key;
    group.appendChild(title);
    const hit = svgEl("rect");
    hit.setAttribute("x", String(pos.x - NODE_W / 2 - 4));
    hit.setAttribute("y", String(pos.y - NODE_H / 2 - 4));
    hit.setAttribute("width", String(NODE_W + 8));
    hit.setAttribute("height", String(NODE_H + 8));
    hit.setAttribute("fill", "transparent");
    hit.setAttribute("stroke", "none");
    group.appendChild(hit);
    const padX = 8;
    if (node.kind === "symbol") {
      const poly = svgEl("polygon");
      const hw = NODE_W / 2;
      const hh = NODE_H / 2;
      const pts =
        pos.x +
        "," +
        (pos.y - hh) +
        " " +
        (pos.x + hw) +
        "," +
        pos.y +
        " " +
        pos.x +
        "," +
        (pos.y + hh) +
        " " +
        (pos.x - hw) +
        "," +
        pos.y;
      poly.setAttribute("points", pts);
      poly.setAttribute("fill", "#1a2330");
      poly.setAttribute("stroke", stroke);
      poly.setAttribute(
        "stroke-width",
        key === selectedKey || consumerKeys[key] ? "2.5" : "1.5"
      );
      poly.setAttribute("pointer-events", "none");
      group.appendChild(poly);
    } else {
      const rect = svgEl("rect");
      rect.setAttribute("x", String(pos.x - NODE_W / 2));
      rect.setAttribute("y", String(pos.y - NODE_H / 2));
      rect.setAttribute("width", String(NODE_W));
      rect.setAttribute("height", String(NODE_H));
      rect.setAttribute("rx", "8");
      rect.setAttribute("ry", "8");
      rect.setAttribute("fill", "#1a2330");
      rect.setAttribute("stroke", stroke);
      rect.setAttribute(
        "stroke-width",
        key === selectedKey || consumerKeys[key] ? "2.5" : "1.5"
      );
      rect.setAttribute("pointer-events", "none");
      group.appendChild(rect);
    }
    const clip = svgEl("clipPath");
    const clipId =
      "nclip-" +
      String(key)
        .replace(/[^a-zA-Z0-9_-]/g, "_")
        .slice(0, 96);
    clip.setAttribute("id", clipId);
    const clipRect = svgEl("rect");
    clipRect.setAttribute("x", String(pos.x - NODE_W / 2 + padX));
    clipRect.setAttribute("y", String(pos.y - NODE_H / 2 + 4));
    clipRect.setAttribute("width", String(NODE_W - padX * 2));
    clipRect.setAttribute("height", String(NODE_H - 8));
    clip.appendChild(clipRect);
    group.appendChild(clip);
    const text = svgEl("text");
    text.setAttribute("x", String(pos.x));
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#e6edf3");
    text.setAttribute("font-size", "10");
    text.setAttribute("font-family", "ui-monospace, SFMono-Regular, Menlo, monospace");
    text.setAttribute("pointer-events", "none");
    text.setAttribute("clip-path", "url(#" + clipId + ")");
    const lineH = 12;
    const startY = pos.y - ((lines.length - 1) * lineH) / 2 + 3;
    for (let i = 0; i < lines.length; i++) {
      const tspan = svgEl("tspan");
      tspan.setAttribute("x", String(pos.x));
      tspan.setAttribute("y", String(startY + i * lineH));
      tspan.textContent = lines[i];
      text.appendChild(tspan);
    }
    group.appendChild(text);
    group.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.stopPropagation();
      drag = {
        x: e.clientX,
        y: e.clientY,
        panX: panX,
        panY: panY,
        moved: false,
        nodeKey: key,
      };
      try {
        group.setPointerCapture(e.pointerId);
      } catch (err) {}
    });
    group.addEventListener("pointermove", function (e) {
      if (!drag || drag.nodeKey !== key) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) > 5) drag.moved = true;
      if (drag.moved) setTransform(drag.panX + dx, drag.panY + dy, scale);
    });
    group.addEventListener("pointerup", function (e) {
      if (!drag || drag.nodeKey !== key) return;
      const wasDrag = drag;
      drag = null;
      e.stopPropagation();
      if (wasDrag.moved) return;
      selectNode(key);
    });
    group.addEventListener("pointercancel", function () {
      if (drag && drag.nodeKey === key) drag = null;
    });
    g.appendChild(group);
  }

  function redraw(doFit) {
    if (!viewport || !graph) return;
    const entries = M.entriesNodes(graph);
    const eff = effectiveN();
    const visible = M.filterVisible(
      entries,
      graph.edges || [],
      eff,
      edgeKindOn
    );
    layout = M.layoutNodes(visible.entries, eff);
    while (viewport.firstChild) viewport.removeChild(viewport.firstChild);
    const edges = visible.edges || [];
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i];
      const a = layout[e.from];
      const b = layout[e.to];
      if (!a || !b) continue;
      const line = svgEl("line");
      line.setAttribute("x1", String(a.x));
      line.setAttribute("y1", String(a.y));
      line.setAttribute("x2", String(b.x));
      line.setAttribute("y2", String(b.y));
      line.setAttribute("stroke", edgeStroke(e));
      line.setAttribute("stroke-width", "1.5");
      line.setAttribute("pointer-events", "none");
      viewport.appendChild(line);
    }
    const keys = Object.keys(layout);
    for (let i = 0; i < keys.length; i++) {
      drawNode(viewport, keys[i], layout[keys[i]]);
    }
    if (doFit === true) initialView(layout);
    else if (doFit === "center" && selectedKey)
      centerOnNode(selectedKey, layout, scale);
    else if (doFit === "fit") fitToGraph(layout);
    setTransform(panX, panY, scale);
  }

  function mountToolbar(toolbar) {
    if (!toolbar) return;
    while (toolbar.firstChild) toolbar.removeChild(toolbar.firstChild);
    for (let i = 0; i < EDGE_KINDS.length; i++) {
      const kind = EDGE_KINDS[i];
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = edgeKindOn[kind] !== false;
      cb.addEventListener("change", function () {
        edgeKindOn[kind] = cb.checked;
        redraw(false);
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + kind));
      toolbar.appendChild(lab);
    }
    const hopLab = document.createElement("label");
    hopLab.appendChild(document.createTextNode("hop ≤ "));
    const hopInput = document.createElement("input");
    hopInput.type = "number";
    hopInput.min = "0";
    hopInput.step = "1";
    hopInput.value = String(userHop);
    hopInput.addEventListener("change", function () {
      const v = Number(hopInput.value);
      userHop = isFinite(v) && v >= 0 ? Math.floor(v) : userHop;
      hopInput.value = String(userHop);
      redraw(false);
    });
    hopLab.appendChild(hopInput);
    toolbar.appendChild(hopLab);
    const searchWrap = document.createElement("div");
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = "Find node";
    const searchStatus = document.createElement("div");
    searchStatus.id = "search-status";
    const searchResults = document.createElement("div");
    searchResults.id = "search-results";
    function runSearch() {
      while (searchResults.firstChild)
        searchResults.removeChild(searchResults.firstChild);
      const q = searchInput.value.trim();
      if (!q) {
        searchStatus.textContent = "";
        return;
      }
      const hits = M.searchNodes(M.entriesNodes(graph), q);
      if (!hits.length) {
        searchStatus.textContent = "No nodes match.";
        return;
      }
      searchStatus.textContent = "";
      for (let i = 0; i < hits.length; i++) {
        const key = hits[i][0];
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = key;
        btn.addEventListener("click", function () {
          selectNode(key, { center: "center" });
        });
        searchResults.appendChild(btn);
      }
    }
    searchInput.addEventListener("input", runSearch);
    searchWrap.appendChild(searchInput);
    searchWrap.appendChild(searchStatus);
    searchWrap.appendChild(searchResults);
    toolbar.appendChild(searchWrap);
    const findBtn = document.createElement("button");
    findBtn.type = "button";
    findBtn.textContent = "Re-center";
    findBtn.addEventListener("click", function () {
      if (selectedKey) centerOnNode(selectedKey, layout, scale);
    });
    toolbar.appendChild(findBtn);
    const fitBtn = document.createElement("button");
    fitBtn.type = "button";
    fitBtn.textContent = "Fit";
    fitBtn.addEventListener("click", function () {
      fitToGraph(layout);
    });
    toolbar.appendChild(fitBtn);
  }

  function bindPanZoom() {
    if (!svg) return;
    svg.addEventListener(
      "wheel",
      function (e) {
        e.preventDefault();
        const rect = svg.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const worldX = (mx - panX) / scale;
        const worldY = (my - panY) / scale;
        const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
        const newScale = clampScale(scale * factor);
        setTransform(mx - worldX * newScale, my - worldY * newScale, newScale);
      },
      { passive: false }
    );
    svg.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      drag = {
        x: e.clientX,
        y: e.clientY,
        panX: panX,
        panY: panY,
        moved: false,
      };
      try {
        svg.setPointerCapture(e.pointerId);
      } catch (err) {}
    });
    svg.addEventListener("pointermove", function (e) {
      if (!drag) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) > 5) drag.moved = true;
      if (drag.moved) setTransform(drag.panX + dx, drag.panY + dy, scale);
    });
    svg.addEventListener("pointerup", function (e) {
      if (!drag) return;
      const wasDrag = drag;
      drag = null;
      if (wasDrag.moved) return;
      let el = document.elementFromPoint(e.clientX, e.clientY);
      while (el && el !== svg) {
        if (el.getAttribute && el.getAttribute("data-node-key")) {
          selectNode(el.getAttribute("data-node-key"));
          return;
        }
        el = el.parentNode || el.parentElement;
      }
      clearSelection();
    });
    svg.addEventListener("pointercancel", function () {
      drag = null;
    });
    window.addEventListener("keydown", function (e) {
      if (e.key === "Escape") clearSelection();
    });
  }

  async function boot() {
    const payloadEl = document.getElementById("run-payload");
    try {
      payload = JSON.parse((payloadEl && payloadEl.textContent) || "{}");
    } catch (e) {
      payload = {};
    }
    const chromeBanner = document.getElementById("chrome-banner");
    if (chromeBanner && !chromeBanner.textContent) {
      chromeBanner.textContent = payload.chrome || "";
    }
    const drill = document.getElementById("delete-drill-in");
    if (drill) drill.setAttribute("data-ready", "1");

    let jsonError = false;
    try {
      const parts = await Promise.all([
        fetch("graph.json").then(function (r) {
          return r.ok ? r.json() : null;
        }),
        fetch("ledger.json").then(function (r) {
          return r.ok ? r.json() : null;
        }),
        fetch("obligations.json").then(function (r) {
          return r.ok ? r.json() : null;
        }),
        fetch("run.json").then(function (r) {
          return r.ok ? r.json() : null;
        }),
        fetch("surface.json").then(function (r) {
          return r.ok ? r.json() : null;
        }),
        fetch("server-info.json").then(function (r) {
          return r.ok ? r.json() : null;
        }),
      ]);
      graph = parts[0];
      ledger = parts[1];
      obligations = parts[2];
      run = parts[3];
      surface = parts[4];
      serverInfo = parts[5];
    } catch (e) {
      jsonError = true;
      const banner = document.getElementById("run-status-banner");
      if (banner) banner.textContent = "invalid artefact JSON";
    }

    svg = document.getElementById("graph-canvas");
    if (svg) {
      viewport = svgEl("g");
      viewport.setAttribute("id", "viewport");
      svg.appendChild(viewport);
      bindPanZoom();
    }
    await mountPathNotes();

    if (jsonError || !graph || !ledger || !obligations) {
      const empty = document.getElementById("inspector-empty");
      if (empty) empty.textContent = "missing map artefacts";
      return;
    }

    rebuildObById();
    updateStatusBanner();
    updateFragmentationBanner();
    updateHardRejectStrip();
    userHop = M.initialUserHop(run || {});
    mountToolbar(document.getElementById("graph-toolbar"));
    redraw(true);
  }

  boot();
})();
