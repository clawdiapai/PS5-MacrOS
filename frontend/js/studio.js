/**
 * LiteGraph studio canvas + save/load/run wiring for Web2PS5.
 */
(function () {
  const canvasEl = document.getElementById("graph-canvas");
  if (!canvasEl || typeof LiteGraph === "undefined") {
    console.error("studio.js: canvas or LiteGraph missing");
    return;
  }

  const graph = new LGraph();
  const canvas = new LGraphCanvas(canvasEl, graph);
  canvas.background_image = null;
  canvas.render_canvas_border = false;
  canvas.always_render_background = true;

  const healthBadge = document.getElementById("health-badge");
  const wsBadge = document.getElementById("ws-badge");
  const runBadge = document.getElementById("run-badge");
  const graphSelect = document.getElementById("graph-select");

  const teleLines = [];
  let lastHealth = null;
  const glowBackup = new Map();
  let suppressGraphChange = false;

  function currentGraphName() {
    const v = (graphSelect && graphSelect.value) || "open_fortnite";
    return String(v).trim() || "open_fortnite";
  }

  function setGraphSelectValue(name) {
    if (!graphSelect) return;
    const n = String(name || "open_fortnite").trim() || "open_fortnite";
    suppressGraphChange = true;
    graphSelect.value = n;
    if (graphSelect.value !== n) {
      // Name not in list yet — add it
      const opt = document.createElement("option");
      opt.value = n;
      opt.textContent = n;
      graphSelect.appendChild(opt);
      graphSelect.value = n;
    }
    suppressGraphChange = false;
  }

  async function refreshGraphList(preferName) {
    if (!graphSelect) return;
    const keep = preferName || currentGraphName();
    try {
      const res = await fetch("/api/graphs");
      const data = await res.json();
      const names = Array.isArray(data.graphs) ? data.graphs.slice() : [];
      if (!names.includes(keep) && keep) names.push(keep);
      names.sort();
      suppressGraphChange = true;
      graphSelect.innerHTML = "";
      names.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        graphSelect.appendChild(opt);
      });
      if (names.includes(keep)) graphSelect.value = keep;
      else if (names.length) graphSelect.value = names[0];
      suppressGraphChange = false;
    } catch (err) {
      suppressGraphChange = false;
      pushTelemetry(String(err));
    }
  }

  function dirtyUiNodes() {
    graph.setDirtyCanvas(true, false);
    if (window.Web2PS5UI && window.Web2PS5UI.syncToggles) {
      window.Web2PS5UI.syncToggles();
    }
  }

  function pushTelemetry(obj) {
    teleLines.push(typeof obj === "string" ? obj : JSON.stringify(obj));
    while (teleLines.length > 80) teleLines.shift();
    dirtyUiNodes();
  }

  function resizeCanvas() {
    const parent = canvasEl.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    const w = Math.max(320, Math.floor(rect.width));
    const h = Math.max(240, Math.floor(rect.height));
    canvasEl.width = w;
    canvasEl.height = h;
    canvas.resize();
  }

  function seedDemoGraph() {
    graph.clear();
    const start = LiteGraph.createNode("logic/start");
    start.pos = [40, 160];
    graph.add(start);

    const wait = LiteGraph.createNode("vis/wait_anchor");
    wait.pos = [240, 120];
    wait.properties.anchor_id = "demo_bar";
    wait.properties.threshold = 0.6;
    wait.properties.timeout_ms = 5000;
    graph.add(wait);

    const logOk = LiteGraph.createNode("sys/log");
    logOk.pos = [520, 80];
    logOk.properties.message = "anchor FOUND";
    graph.add(logOk);

    const logTo = LiteGraph.createNode("sys/log");
    logTo.pos = [520, 220];
    logTo.properties.message = "anchor TIMEOUT";
    graph.add(logTo);

    const press = LiteGraph.createNode("ds/press");
    press.pos = [760, 80];
    press.properties.button = "cross";
    graph.add(press);

    start.connect(0, wait, 0);
    wait.connect(0, logOk, 0); // found
    wait.connect(1, logTo, 0); // timeout
    logOk.connect(0, press, 0);
    graph.setDirtyCanvas(true, true);
  }

  async function refreshHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      lastHealth = data;
      if (healthBadge) {
        healthBadge.textContent = data.status === "ok" ? "api ok" : data.status;
        healthBadge.className = "badge " + (data.status === "ok" ? "ok" : "err");
      }
      const run = data.run || {};
      if (runBadge) {
        runBadge.textContent = "run: " + (run.status || "unknown");
        runBadge.className = "badge " + (run.status === "running" ? "warn" : "ok");
      }
      dirtyUiNodes();
    } catch (err) {
      lastHealth = { status: "down", error: String(err) };
      if (healthBadge) {
        healthBadge.textContent = "api down";
        healthBadge.className = "badge err";
      }
      dirtyUiNodes();
    }
  }

  function connectTelemetry() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);
    ws.onopen = () => {
      if (wsBadge) {
        wsBadge.textContent = "ws ok";
        wsBadge.className = "badge ok";
      }
    };
    ws.onclose = () => {
      if (wsBadge) {
        wsBadge.textContent = "ws down";
        wsBadge.className = "badge err";
      }
      setTimeout(connectTelemetry, 1500);
    };
    ws.onerror = () => {
      if (wsBadge) {
        wsBadge.textContent = "ws err";
        wsBadge.className = "badge err";
      }
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        pushTelemetry(ev.data);
        return;
      }
      pushTelemetry(msg);
      handleGlow(msg);
      if (
        (msg.type === "wait_progress" ||
          msg.type === "match_score" ||
          msg.type === "ocr_check" ||
          msg.type === "ocr_wait_progress") &&
        window.Web2PS5UI &&
        window.Web2PS5UI.setDetections
      ) {
        window.Web2PS5UI.setDetections(msg);
      }
      if (msg.type === "run_finished" || msg.type === "run_stopped" || msg.type === "run_error") {
        // keep last boxes briefly; poll continues if detections toggle on
      }
      refreshHealth();
    };
  }

  function findNode(nodeId) {
    if (nodeId == null) return null;
    // Backend sends litegraph numeric id as string/number
    const id = Number(nodeId);
    if (Number.isFinite(id) && graph._nodes_by_id[id]) {
      return graph._nodes_by_id[id];
    }
    // stub ids like "stub:waiting"
    return null;
  }

  function handleGlow(msg) {
    if (msg.type === "node_enter") {
      const node = findNode(msg.node_id);
      if (!node) return;
      if (!glowBackup.has(node.id)) {
        glowBackup.set(node.id, {
          boxcolor: node.boxcolor,
          bgcolor: node.bgcolor,
        });
      }
      node.boxcolor = "#3dd68c";
      node.bgcolor = "#143528";
      graph.setDirtyCanvas(true, true);
    } else if (msg.type === "node_exit") {
      const node = findNode(msg.node_id);
      if (!node) return;
      const bak = glowBackup.get(node.id);
      if (bak) {
        node.boxcolor = bak.boxcolor;
        node.bgcolor = bak.bgcolor;
        glowBackup.delete(node.id);
      }
      graph.setDirtyCanvas(true, true);
    } else if (msg.type === "run_stopped" || msg.type === "run_error") {
      for (const [id, bak] of glowBackup.entries()) {
        const node = graph._nodes_by_id[id];
        if (node) {
          node.boxcolor = bak.boxcolor;
          node.bgcolor = bak.bgcolor;
        }
      }
      glowBackup.clear();
      graph.setDirtyCanvas(true, true);
    }
  }

  async function saveGraph(nameOverride) {
    const name = String(nameOverride || currentGraphName()).trim() || "demo";
    const body = {
      name,
      version: 1,
      graph: graph.serialize(),
    };
    const res = await fetch(`/api/graphs/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "save failed");
    await refreshGraphList(name);
    setGraphSelectValue(name);
    pushTelemetry({ type: "ui_save_graph", ...data });
    await refreshHealth();
  }

  async function saveGraphAs() {
    const cur = currentGraphName();
    const raw = window.prompt("Save graph as (new name):", cur + "_copy");
    if (raw == null) return;
    const name = String(raw).trim();
    if (!name) throw new Error("empty graph name");
    if (!/^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$/.test(name)) {
      throw new Error("name must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}");
    }
    await saveGraph(name);
  }

  async function loadGraph(nameOverride) {
    const name = String(nameOverride || currentGraphName()).trim() || "demo";
    const res = await fetch(`/api/graphs/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "load failed");
    graph.configure(data.document.graph);
    graph.setDirtyCanvas(true, true);
    setGraphSelectValue(name);
    // Re-attach live preview streams after deserialize
    (graph.findNodesByType("ui/preview") || []).forEach((n) => {
      if (n.properties && n.properties.live !== false && window.Web2PS5UI) {
        window.Web2PS5UI.preview.acquire(n);
      }
    });
    if (window.Web2PS5UI && window.Web2PS5UI.syncToggles) {
      window.Web2PS5UI.syncToggles();
    }
    pushTelemetry({ type: "ui_load_graph", name, nodes: graph._nodes.length });
  }

  async function startRun() {
    const name = currentGraphName();
    // Always save current canvas before run so backend sees latest wires
    await saveGraph(name);
    const res = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ graph: name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    pushTelemetry({ type: "ui_start_run", ...data });
    await refreshHealth();
  }

  async function stopRun() {
    const res = await fetch("/api/runs/stop", { method: "POST" });
    const data = await res.json();
    pushTelemetry({ type: "ui_stop_run", ...data });
    await refreshHealth();
  }

  document.getElementById("btn-save")?.addEventListener("click", () => {
    saveGraph().catch((err) => pushTelemetry(String(err)));
  });
  document.getElementById("btn-save-as")?.addEventListener("click", () => {
    saveGraphAs().catch((err) => pushTelemetry(String(err)));
  });
  document.getElementById("btn-load")?.addEventListener("click", () => {
    loadGraph().catch((err) => pushTelemetry(String(err)));
  });
  document.getElementById("btn-start")?.addEventListener("click", () => {
    startRun().catch((err) => pushTelemetry(String(err)));
  });
  document.getElementById("btn-stop")?.addEventListener("click", () => {
    stopRun().catch((err) => pushTelemetry(String(err)));
  });
  document.getElementById("btn-seed")?.addEventListener("click", () => {
    seedDemoGraph();
    pushTelemetry({ type: "ui_seed_demo" });
  });

  graphSelect?.addEventListener("change", () => {
    if (suppressGraphChange) return;
    loadGraph(currentGraphName()).catch((err) => pushTelemetry(String(err)));
  });

  const ptBtn = document.getElementById("btn-passthrough");

  function paintPassthrough(active, detail) {
    if (!ptBtn) return;
    ptBtn.textContent = active ? "Pass-through ON" : "Pass-through OFF";
    ptBtn.classList.toggle("warn", !!active);
    if (detail) pushTelemetry({ type: "passthrough", ...detail });
  }

  async function refreshPassthrough() {
    try {
      const res = await fetch("/api/passthrough");
      const data = await res.json();
      paintPassthrough(!!data.active, data);
    } catch (err) {
      pushTelemetry(String(err));
    }
  }

  async function togglePassthrough() {
    try {
      const cur = await (await fetch("/api/passthrough")).json();
      const res = await fetch(
        cur.active ? "/api/passthrough/stop" : "/api/passthrough/start",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: cur.active ? undefined : JSON.stringify({ pad_index: 0 }),
        }
      );
      const data = await res.json();
      if (!res.ok) {
        pushTelemetry({ type: "passthrough_error", detail: data.detail || data });
        return;
      }
      paintPassthrough(!!data.active, data);
      await refreshHealth();
    } catch (err) {
      pushTelemetry(String(err));
    }
  }

  ptBtn?.addEventListener("click", () => {
    togglePassthrough();
  });
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "F9") {
      ev.preventDefault();
      togglePassthrough();
    }
  });

  async function rpAction(path, label) {
    pushTelemetry({ type: "ui_session", action: label, state: "pending" });
    try {
      const res = await fetch(path, { method: "POST" });
      const data = await res.json();
      pushTelemetry({
        type: "ui_session",
        action: label,
        ok: res.ok,
        detail: data.detail || data.bridge || data,
      });
      await refreshHealth();
      await refreshPassthrough();
    } catch (err) {
      pushTelemetry({ type: "ui_session", action: label, error: String(err) });
    }
  }

  document.getElementById("btn-rp-disconnect")?.addEventListener("click", () => {
    rpAction("/api/session/disconnect", "disconnect");
  });
  document.getElementById("btn-rp-reconnect")?.addEventListener("click", () => {
    rpAction("/api/session/reconnect", "reconnect");
  });

  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();
  seedDemoGraph();
  graph.start();
  refreshHealth();
  refreshPassthrough();
  setInterval(refreshHealth, 4000);
  connectTelemetry();

  // Populate graph dropdown, then load the selected graph if present
  refreshGraphList("open_fortnite")
    .then(() => loadGraph())
    .catch(() => {
      /* first run — keep seeded canvas if load fails */
    });

  // First-run: send to setup wizard unless already complete/skipped
  fetch("/api/setup/status")
    .then((r) => r.json())
    .then((data) => {
      if (data.needs_wizard) {
        location.replace("/setup");
      }
    })
    .catch(() => {});

  async function setMacroRecording(node, wantOn) {
    if (!node || !node.properties) return;
    const name = String(node.properties.name || `seq_${node.id}`).replace(
      /[^A-Za-z0-9_-]/g,
      "_"
    );
    node.properties.name = name;
    const evWidget = (node.widgets || []).find((w) => w.name === "events");
    const tog = (node.widgets || []).find((w) => w.name === "record");

    if (wantOn) {
      pushTelemetry({ type: "macro_record_start", name, node_id: node.id });
      const res = await fetch("/api/macros/record/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, ensure_passthrough: true, pad_index: 0 }),
      });
      const data = await res.json();
      if (!res.ok) {
        pushTelemetry({ type: "macro_record_error", detail: data.detail || data });
        node.properties.recording = false;
        if (tog) tog.value = false;
        graph.setDirtyCanvas(true, true);
        return;
      }
      node.properties.recording = true;
      paintPassthrough(true, data.passthrough);
      pushTelemetry({
        type: "macro_recording",
        hint: "Play DualSense now, then flip record OFF",
        name,
      });
      graph.setDirtyCanvas(true, true);
      return;
    }

    // wantOn === false → stop. Normalize ALWAYS unless toggle explicitly unticked.
    const doNorm = node.properties.normalize !== false;
    const gapMs = Number(node.properties.gap_ms != null ? node.properties.gap_ms : 700);
    const pressMs = Number(node.properties.press_ms != null ? node.properties.press_ms : 100);
    const res = await fetch("/api/macros/record/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        normalize: doNorm,
        gap_ms: gapMs,
        press_ms: pressMs,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      pushTelemetry({ type: "macro_record_error", detail: data.detail || data });
      node.properties.recording = false;
      if (tog) tog.value = false;
      graph.setDirtyCanvas(true, true);
      return;
    }
    node.properties.events = data.events || [];
    node.properties.event_count = data.count || 0;
    node.properties.recording = false;
    node.properties.macro = name;
    if (evWidget) evWidget.value = String(data.count || 0);
    if (tog) tog.value = false;
    pushTelemetry({
      type: "macro_recorded",
      name,
      count: data.count,
      raw_count: data.raw_count,
      normalized: data.normalized !== false && doNorm,
      gap_ms: gapMs,
      node_id: node.id,
    });
    graph.setDirtyCanvas(true, true);
    try {
      await saveGraph();
    } catch (err) {
      pushTelemetry(String(err));
    }
  }

  async function renormalizeMacroNode(node) {
    const events = node.properties.events || [];
    if (!events.length) return;
    const gapMs = Number(node.properties.gap_ms != null ? node.properties.gap_ms : 700);
    const pressMs = Number(node.properties.press_ms != null ? node.properties.press_ms : 100);
    try {
      const res = await fetch("/api/macros/normalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: node.properties.name || "demo",
          events,
          gap_ms: gapMs,
          press_ms: pressMs,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        pushTelemetry({ type: "macro_normalize_error", detail: data.detail || data });
        return;
      }
      node.properties.events = data.events || [];
      node.properties.event_count = data.count || 0;
      const evWidget = node.widgets && node.widgets.find((w) => w.name === "events");
      if (evWidget) evWidget.value = String(data.count || 0);
      pushTelemetry({
        type: "macro_renormalized",
        count: data.count,
        node_id: node.id,
      });
      graph.setDirtyCanvas(true, true);
      await saveGraph();
    } catch (err) {
      pushTelemetry({ type: "macro_normalize_error", detail: String(err) });
    }
  }

  window.Web2PS5Studio = {
    graph,
    canvas,
    seedDemoGraph,
    saveGraph,
    saveGraphAs,
    loadGraph,
    refreshGraphList,
    currentGraphName,
    setMacroRecording,
    renormalizeMacroNode,
    pushTelemetry,
    getTelemetryLines: () => teleLines.slice(),
    getLastHealth: () => lastHealth,
  };

  // Re-bind UI toggles once studio is ready (ui_nodes may have loaded first)
  if (window.Web2PS5UI && window.Web2PS5UI.syncToggles) {
    window.Web2PS5UI.syncToggles();
  }
})();
