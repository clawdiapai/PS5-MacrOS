/**
 * Web2PS5 node catalog — hybrid EXEC + data (authoring only).
 */
(function (global) {
  const LiteGraph = global.LiteGraph;
  if (!LiteGraph) {
    console.error("LiteGraph not loaded before nodes.js");
    return;
  }

  const EXEC = "EXEC";
  const BOOL = "BOOL";
  const FLOAT = "FLOAT";
  const STRING = "STRING";
  const VEC4 = "VEC4";

  function styleExecNode(node, color) {
    node.color = color || "#335";
    node.bgcolor = "#1b2030";
    node.boxcolor = "#7c9cff";
  }

  function reg(type, title, ctor) {
    ctor.title = title;
    LiteGraph.registerNodeType(type, ctor);
  }

  function LogicStart() {
    this.addOutput("EXEC", EXEC);
    this.properties = {};
    styleExecNode(this, "#2a4a2a");
  }
  reg("logic/start", "logic.start", LogicStart);

  function LogicBranch() {
    this.addInput("EXEC", EXEC);
    this.addInput("cond", BOOL);
    this.addOutput("true", EXEC);
    this.addOutput("false", EXEC);
    this.properties = {};
    styleExecNode(this, "#4a3a20");
  }
  reg("logic/branch", "logic.branch", LogicBranch);

  function LogicMerge() {
    this.addInput("a", EXEC);
    this.addInput("b", EXEC);
    this.addOutput("EXEC", EXEC);
    this.properties = {};
    styleExecNode(this, "#3a3048");
  }
  LogicMerge.title = "logic.merge";
  LogicMerge.desc = "Join two EXEC branches into one (pass-through).";
  reg("logic/merge", "logic.merge", LogicMerge);

  function LogicWhile() {
    this.addInput("EXEC", EXEC);
    this.addInput("cond", BOOL);
    this.addOutput("body", EXEC);
    this.addOutput("done", EXEC);
    this.properties = {};
    styleExecNode(this, "#4a4020");
  }
  reg("logic/while", "logic.while", LogicWhile);

  function LogicRepeat() {
    this.addInput("EXEC", EXEC);
    this.addOutput("body", EXEC);
    this.addOutput("done", EXEC);
    this.addOutput("index", FLOAT);
    this.addWidget("number", "times", 3, (v) => (this.properties.times = v), {
      min: 1,
      max: 10000,
      step: 1,
    });
    this.properties = { times: 3 };
    styleExecNode(this, "#3a4028");
  }
  reg("logic/repeat", "logic.repeat", LogicRepeat);

  function LogicRetry() {
    this.addInput("EXEC", EXEC);
    this.addInput("ok", BOOL);
    this.addOutput("body", EXEC);
    this.addOutput("success", EXEC);
    this.addOutput("fail", EXEC);
    this.addOutput("attempt", FLOAT);
    this.addWidget(
      "number",
      "max_attempts",
      3,
      (v) => (this.properties.max_attempts = v),
      { min: 1, max: 100, step: 1 }
    );
    this.properties = { max_attempts: 3 };
    styleExecNode(this, "#4a3020");
  }
  reg("logic/retry", "logic.retry", LogicRetry);

  function gate(type, title, dual) {
    function Ctor() {
      this.addInput("EXEC", EXEC);
      this.addInput("a", BOOL);
      if (dual) this.addInput("b", BOOL);
      this.addOutput("EXEC", EXEC);
      this.addOutput("out", BOOL);
      this.properties = {};
      styleExecNode(this, "#304040");
    }
    reg(type, title, Ctor);
  }
  gate("logic/and", "logic.and", true);
  gate("logic/or", "logic.or", true);
  gate("logic/not", "logic.not", false);

  function LogicSetVar() {
    this.addInput("EXEC", EXEC);
    this.addInput("value", "*");
    this.addOutput("EXEC", EXEC);
    this.addWidget("text", "name", "x", (v) => (this.properties.name = v));
    this.addWidget("text", "value", "", (v) => (this.properties.value = v));
    this.properties = { name: "x", value: "" };
    styleExecNode(this, "#2a3550");
  }
  reg("logic/set_var", "logic.set_var", LogicSetVar);

  function LogicGetVar() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addOutput("value", "*");
    this.addWidget("text", "name", "x", (v) => (this.properties.name = v));
    this.properties = { name: "x", default: null };
    styleExecNode(this, "#2a3550");
  }
  reg("logic/get_var", "logic.get_var", LogicGetVar);

  function LogicCounter() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addOutput("value", FLOAT);
    this.addWidget("text", "name", "count", (v) => (this.properties.name = v));
    this.addWidget(
      "combo",
      "op",
      "inc",
      (v) => (this.properties.op = v),
      { values: ["inc", "dec", "set", "reset"] }
    );
    this.properties = { name: "count", op: "inc", by: 1, value: 0 };
    styleExecNode(this, "#2a4050");
  }
  reg("logic/counter", "logic.counter", LogicCounter);

  function LogicSubgraph() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget("text", "graph", "sub", (v) => (this.properties.graph = v));
    this.properties = { graph: "sub" };
    styleExecNode(this, "#403050");
  }
  reg("logic/subgraph", "logic.subgraph", LogicSubgraph);

  function DsDelay() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget("number", "ms", 500, (v) => (this.properties.ms = v), {
      min: 0,
      max: 60000,
      step: 50,
    });
    this.properties = { ms: 500 };
    styleExecNode(this, "#203a4a");
  }
  reg("ds/delay", "ds.delay", DsDelay);

  function DsPress() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget(
      "combo",
      "button",
      "cross",
      (v) => (this.properties.button = v),
      {
        values: [
          "cross",
          "circle",
          "square",
          "triangle",
          "l1",
          "r1",
          "l2",
          "r2",
          "up",
          "down",
          "left",
          "right",
          "options",
          "share",
          "ps",
          "touchpad",
        ],
      }
    );
    this.addWidget(
      "number",
      "duration_ms",
      80,
      (v) => (this.properties.duration_ms = v),
      { min: 80, max: 5000, step: 10 }
    );
    this.properties = { button: "cross", duration_ms: 80 };
    styleExecNode(this, "#3a204a");
  }
  reg("ds/press", "ds.press", DsPress);

  function DsStick() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget(
      "combo",
      "stick",
      "left",
      (v) => (this.properties.stick = v),
      { values: ["left", "right"] }
    );
    this.addWidget("number", "x", 0, (v) => (this.properties.x = v), {
      min: -1,
      max: 1,
      step: 0.05,
    });
    this.addWidget("number", "y", 0, (v) => (this.properties.y = v), {
      min: -1,
      max: 1,
      step: 0.05,
    });
    this.addWidget(
      "number",
      "hold_ms",
      0,
      (v) => (this.properties.hold_ms = v),
      { min: 0, max: 10000, step: 50 }
    );
    this.properties = { stick: "left", x: 0, y: 0, hold_ms: 0 };
    styleExecNode(this, "#3a2848");
  }
  reg("ds/stick", "ds.stick", DsStick);

  function DsMacro() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget("text", "macro", "demo", (v) => (this.properties.macro = v));
    this.properties = { macro: "demo", events: [] };
    styleExecNode(this, "#402848");
  }
  reg("ds/macro", "ds.macro", DsMacro);

  // Record DualSense sequence on the node, play on EXEC
  function DsMacroBlock() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.properties = {
      name: "seq_" + Math.floor(Math.random() * 1e6),
      events: [],
      recording: false,
      event_count: 0,
      // Default ON — untick only if you want raw timings
      normalize: true,
      gap_ms: 700,
      press_ms: 100,
    };
    const node = this;
    this.addWidget("text", "name", this.properties.name, function (v) {
      node.properties.name = v;
    });
    this.addWidget(
      "toggle",
      "normalize",
      true,
      function (v) {
        const was = !!node.properties.normalize;
        node.properties.normalize = !!v;
        // Turning normalize ON on an existing raw recording → re-normalize in place
        if (!was && v && Array.isArray(node.properties.events) && node.properties.events.length) {
          if (window.Web2PS5Studio && window.Web2PS5Studio.renormalizeMacroNode) {
            window.Web2PS5Studio.renormalizeMacroNode(node);
          }
        }
      },
      { on: "ON", off: "off" }
    );
    this.addWidget(
      "toggle",
      "record",
      false,
      function (v) {
        node.properties.recording = !!v;
        if (window.Web2PS5Studio && window.Web2PS5Studio.setMacroRecording) {
          window.Web2PS5Studio.setMacroRecording(node, !!v);
        }
      },
      { on: "REC", off: "off" }
    );
    this.addWidget("text", "events", "0", null);
    this.widgets[this.widgets.length - 1].disabled = true;
    this.addWidget("button", "Clear", "", function () {
      node.properties.events = [];
      node.properties.event_count = 0;
      node.properties.recording = false;
      const tog = node.widgets.find((w) => w.name === "record");
      if (tog) tog.value = false;
      const ev = node.widgets.find((w) => w.name === "events");
      if (ev) ev.value = "0";
      if (window.Web2PS5Studio && window.Web2PS5Studio.pushTelemetry) {
        window.Web2PS5Studio.pushTelemetry({
          type: "macro_cleared",
          node_id: node.id,
        });
      }
    });
    this.size = this.computeSize();
    styleExecNode(this, "#502848");
  }
  DsMacroBlock.prototype.onConfigure = function () {
    // Old graphs / missing props → normalize stays ON unless explicitly false
    if (this.properties.normalize === undefined || this.properties.normalize === null) {
      this.properties.normalize = true;
    }
    if (this.properties.gap_ms == null) this.properties.gap_ms = 700;
    if (this.properties.press_ms == null) this.properties.press_ms = 100;
    const nW = this.widgets && this.widgets.find((w) => w.name === "normalize");
    if (nW) nW.value = this.properties.normalize !== false;
    const eW = this.widgets && this.widgets.find((w) => w.name === "events");
    if (eW) {
      eW.value = String(
        this.properties.event_count != null
          ? this.properties.event_count
          : (this.properties.events || []).length
      );
    }
  };
  DsMacroBlock.title = "ds.macro_block";
  DsMacroBlock.desc =
    "Record DualSense. normalize=ON (default): buttons=uniform taps+700ms gaps; sticks=hold segments (real duration). Untick for raw.";
  LiteGraph.registerNodeType("ds/macro_block", DsMacroBlock);

  function SysLog() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget("text", "message", "hello", (v) => (this.properties.message = v));
    this.properties = { message: "hello" };
    styleExecNode(this, "#2a2a3a");
  }
  reg("sys/log", "sys.log", SysLog);

  function SysAssert() {
    this.addInput("EXEC", EXEC);
    this.addInput("cond", BOOL);
    this.addOutput("EXEC", EXEC);
    this.addWidget(
      "text",
      "message",
      "assert failed",
      (v) => (this.properties.message = v)
    );
    this.properties = { message: "assert failed", value: true };
    styleExecNode(this, "#4a2020");
  }
  reg("sys/assert", "sys.assert", SysAssert);

  function SysWebhook() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget("text", "url", "", (v) => (this.properties.url = v));
    this.addWidget(
      "text",
      "message",
      "Web2PS5 event",
      (v) => (this.properties.message = v)
    );
    this.addWidget(
      "toggle",
      "screenshot",
      false,
      (v) => (this.properties.screenshot = v)
    );
    this.properties = { url: "", message: "Web2PS5 event", screenshot: false };
    styleExecNode(this, "#203040");
  }
  reg("sys/webhook", "sys.webhook", SysWebhook);

  function SysScreenshot() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addOutput("path", STRING);
    this.addWidget("text", "name", "shot", (v) => (this.properties.name = v));
    this.properties = { name: "shot" };
    styleExecNode(this, "#203838");
  }
  reg("sys/screenshot", "sys.screenshot", SysScreenshot);

  function PwrSession() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget(
      "combo",
      "action",
      "connect",
      (v) => (this.properties.action = v),
      { values: ["connect", "disconnect", "standby"] }
    );
    this.properties = { action: "connect" };
    styleExecNode(this, "#403020");
  }
  reg("pwr/session", "pwr.session", PwrSession);

  function _letterbox(ctx, img, x, y, w, h) {
    if (!img || !img.naturalWidth) return null;
    const ir = img.naturalWidth / img.naturalHeight;
    const ar = w / h;
    let dw = w;
    let dh = h;
    let dx = x;
    let dy = y;
    if (ir > ar) {
      dh = w / ir;
      dy = y + (h - dh) / 2;
    } else {
      dw = h * ir;
      dx = x + (w - dw) / 2;
    }
    ctx.fillStyle = "#000";
    ctx.fillRect(x, y, w, h);
    ctx.drawImage(img, dx, dy, dw, dh);
    return { x: dx, y: dy, w: dw, h: dh };
  }

  async function _blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = reject;
      r.readAsDataURL(blob);
    });
  }

  const CAPTURE_LIST_W = 140;

  /**
   * LiteGraph draws:
   *   slots at y ≈ 0..slotRows*SLOT_H
   *   widgets starting at widgets_start_y (or after last slot)
   * So we reserve a band BETWEEN slots and widgets for Saved/list + freeze image,
   * and force widgets_start_y to the bottom of that band.
   */
  function _captureLayout(node) {
    const slotH =
      (typeof LiteGraph !== "undefined" && LiteGraph.NODE_SLOT_HEIGHT) || 20;
    const wh =
      (typeof LiteGraph !== "undefined" && LiteGraph.NODE_WIDGET_HEIGHT) || 20;
    const inputs = (node.inputs && node.inputs.length) || 0;
    const outputs = (node.outputs && node.outputs.length) || 0;
    const slotRows = Math.max(inputs, outputs, 1);
    // Match drawNode: last slot ~ (n-1+0.7)*slotH, then +0.5*slotH → ≈ n*slotH
    const slotBottom = slotRows * slotH + 6;

    let widgetStack = 8;
    const widgets = node.widgets || [];
    for (let i = 0; i < widgets.length; i++) {
      const w = widgets[i];
      const h =
        w.computeSize && typeof w.computeSize === "function"
          ? w.computeSize(node.size[0])[1]
          : wh;
      widgetStack += h + 4;
    }

    const minCapture = 200;
    const need = slotBottom + minCapture + widgetStack + 24;
    if (!node.size) node.size = [560, need];
    if (node.size[1] < need) node.size[1] = need;

    // Capture fills everything between slots and the widget stack at the bottom
    const captureBottom = node.size[1] - widgetStack - 16;
    const top = slotBottom;
    const bottom = Math.max(top + minCapture, captureBottom);
    node.widgets_start_y = bottom + 4;
    return { top: top, bottom: bottom, height: bottom - top };
  }

  function _captureContentTop(node) {
    return _captureLayout(node).top;
  }

  /** Shared freeze / list / edit for wait_anchor + check_state. */
  function _bindAnchorCapture(node, opts) {
    opts = opts || {};
    const padTop = opts.padTop != null ? opts.padTop : 180;
    node._capturePadTop = padTop;
    node._snap = node._snap || null;
    node._frameB64 = node._frameB64 || null;
    node._natural = node._natural || { w: 1280, h: 720 };
    node._drag = null;
    node._draft = null;
    node._selectedTarget = node._selectedTarget != null ? node._selectedTarget : -1;
    node._anchorList = Array.isArray(node._anchorList) ? node._anchorList : [];
    node._listRects = [];
    node._imgRect = node._imgRect || {
      x: CAPTURE_LIST_W + 16,
      y: padTop,
      w: 400,
      h: 200,
    };
    if (!Array.isArray(node.properties.targets)) node.properties.targets = [];
    if (!node.properties.match_mode) node.properties.match_mode = "all";
    if (node.properties.match_count == null) node.properties.match_count = 1;
    if (!node.properties.edit_mode) node.properties.edit_mode = "create";
    node.properties.capture_hint =
      node.properties.capture_hint ||
      "Freeze new OR click a saved name to edit";

    node._targets = function () {
      return Array.isArray(this.properties.targets) ? this.properties.targets : [];
    };

    node._displayToFrame = function (rect) {
      const ir = this._imgRect;
      const sx = this._natural.w / Math.max(1, ir.w);
      const sy = this._natural.h / Math.max(1, ir.h);
      return {
        x: Math.round(rect.x * sx),
        y: Math.round(rect.y * sy),
        w: Math.max(1, Math.round(rect.w * sx)),
        h: Math.max(1, Math.round(rect.h * sy)),
      };
    };

    node._frameToDisplay = function (box) {
      const ir = this._imgRect;
      const sx = ir.w / Math.max(1, this._natural.w);
      const sy = ir.h / Math.max(1, this._natural.h);
      return {
        x: box.x * sx,
        y: box.y * sy,
        w: box.w * sx,
        h: box.h * sy,
      };
    };

    node._finalizeDraft = function () {
      if (!this._draft || this._draft.w < 4 || this._draft.h < 4) {
        this._draft = null;
        return false;
      }
      if (!Array.isArray(this.properties.targets)) this.properties.targets = [];
      this.properties.targets.push(this._displayToFrame(this._draft));
      this._selectedTarget = this.properties.targets.length - 1;
      this._draft = null;
      const n = this.properties.targets.length;
      this.properties.capture_hint =
        n + " target(s) — click box to select, Confirm to save";
      return true;
    };

    node._refreshAnchorList = async function () {
      try {
        const res = await fetch("/api/anchors");
        const data = await res.json();
        const rows = (data.anchors || []).filter(
          (a) => a && a.id && a.id !== "demo_bar"
        );
        this._anchorList = rows.map((a) => a.id);
        this._anchorMetaById = {};
        rows.forEach((a) => {
          this._anchorMetaById[a.id] = {
            legacy: !!a.legacy,
            has_full: !!a.has_full,
          };
        });
        this.setDirtyCanvas(true, false);
      } catch (_) {
        /* ignore */
      }
    };

    node._promptLegacyRetake = function (id) {
      const msg =
        'LEGACY — no full reference frame\n\n"' +
        id +
        '" shows its crop template only.\nRetake a full freeze to edit boxes on-screen?\n\nOK = Retake (Freeze)\nCancel = Keep viewing crop';
      return window.confirm(msg);
    };

    node._loadImageUrl = async function (url) {
      const imgRes = await fetch(url);
      if (!imgRes.ok) throw new Error("image load failed: " + imgRes.status);
      const blob = await imgRes.blob();
      const dataUrl = await _blobToDataUrl(blob);
      const img = new Image();
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = reject;
        img.src = dataUrl;
      });
      return { img: img, dataUrl: dataUrl };
    };

    node._showCropPreview = async function (id, meta) {
      const cropUrl =
        (meta && meta.crop_url) ||
        "/api/anchors/" + encodeURIComponent(id) + "/image";
      const loaded = await this._loadImageUrl(cropUrl + "?" + Date.now());
      this._snap = loaded.img;
      this._frameB64 = null; // crop-only — not a full freeze to re-cut from
      this._cropPreviewOnly = true;
      this._natural = {
        w: loaded.img.naturalWidth || 64,
        h: loaded.img.naturalHeight || 64,
      };
      // Search-ROI boxes are full-frame coords — don't overlay them on the crop
      this.properties.targets = [];
      this._selectedTarget = -1;
      this._draft = null;
      this._drag = null;
      const legacy = !!(meta && meta.legacy);
      this.properties.capture_hint = legacy
        ? 'LEGACY crop "' + id + '" — Freeze to retake full frame'
        : 'Crop "' + id + '" (no full.jpg) — Freeze to attach reference';
      if (this.size[0] < 560) this.size[0] = 560;
      if (this.size[1] < 420) this.size[1] = 420;
      this.setDirtyCanvas(true, true);
    };

    node._loadAnchorForEdit = async function (id) {
      try {
        const res = await fetch("/api/anchors/" + encodeURIComponent(id));
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "load failed");
        const meta = data.anchor || {};
        this.properties.anchor_id = id;
        const aw = (this.widgets || []).find((x) => x.name === "anchor");
        if (aw) aw.value = id;
        this.properties.match_mode = meta.match_mode || "all";
        this.properties.match_count = meta.match_count || 1;
        if (meta.threshold != null) this.properties.threshold = meta.threshold;
        const mw = (this.widgets || []).find((x) => x.name === "match");
        if (mw) mw.value = this.properties.match_mode;
        const atw = (this.widgets || []).find((x) => x.name === "at_least");
        if (atw) atw.value = this.properties.match_count;
        const thw = (this.widgets || []).find((x) => x.name === "threshold");
        if (thw && meta.threshold != null) thw.value = meta.threshold;

        this.properties.targets = Array.isArray(meta.crops)
          ? meta.crops.map((c) => ({
              x: c.x | 0,
              y: c.y | 0,
              w: c.w | 0,
              h: c.h | 0,
            }))
          : [];
        this._draft = null;
        this._drag = null;
        this._selectedTarget = this.properties.targets.length ? 0 : -1;
        this.properties.edit_mode = "edit";

        if (!meta.has_full) {
          await this._showCropPreview(id, meta);
          if (meta.legacy && this._promptLegacyRetake(id)) {
            await this._doFreeze();
            this.properties.edit_mode = "edit";
            this.properties.capture_hint =
              'RETAKE "' + id + '" — drag target(s), Confirm (clears LEGACY)';
            this.setDirtyCanvas(true, true);
          }
          return;
        }
        const loaded = await this._loadImageUrl(
          "/api/anchors/" + encodeURIComponent(id) + "/full.jpg?" + Date.now()
        );
        this._frameB64 = loaded.dataUrl;
        this._snap = loaded.img;
        this._cropPreviewOnly = false;
        this._natural = {
          w: loaded.img.naturalWidth || 1280,
          h: loaded.img.naturalHeight || 720,
        };
        this.properties.capture_hint =
          "EDIT \"" +
          id +
          "\" — " +
          this.properties.targets.length +
          " box(es). Move/add, then Confirm";
        if (this.size[0] < 560) this.size[0] = 560;
        if (this.size[1] < 420) this.size[1] = 420;
        this.setDirtyCanvas(true, true);
      } catch (err) {
        this.properties.capture_hint = String(err);
        this.setDirtyCanvas(true, false);
      }
    };

    node._doFreeze = async function () {
      try {
        const res = await fetch("/api/anchors/snapshot.jpg?" + Date.now());
        if (!res.ok) throw new Error("freeze failed: " + res.status);
        const blob = await res.blob();
        this._frameB64 = await _blobToDataUrl(blob);
        const img = new Image();
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
          img.src = this._frameB64;
        });
        this._snap = img;
        this._cropPreviewOnly = false;
        this._natural = {
          w: img.naturalWidth || 1280,
          h: img.naturalHeight || 720,
        };
        this._draft = null;
        this._drag = null;
        this._selectedTarget = -1;
        this.properties.targets = [];
        this.properties.edit_mode = "create";
        this.properties.capture_hint =
          "NEW freeze — set name, drag target(s), Confirm (adds to list)";
        if (this.size[1] < 420) this.size[1] = 420;
        if (this.size[0] < 560) this.size[0] = 560;
        this.setDirtyCanvas(true, true);
      } catch (err) {
        this.properties.capture_hint = String(err);
        this.setDirtyCanvas(true, false);
      }
    };

    node._doClearTargets = function () {
      this.properties.targets = [];
      this._draft = null;
      this._drag = null;
      this._selectedTarget = -1;
      this.properties.capture_hint = this._frameB64
        ? "Targets cleared — drag new boxes"
        : "Freeze or click a saved name";
      this.setDirtyCanvas(true, false);
    };

    node._doDelSelected = function () {
      const t = this._targets();
      if (this._selectedTarget < 0 || this._selectedTarget >= t.length) return;
      t.splice(this._selectedTarget, 1);
      this.properties.targets = t;
      this._selectedTarget = -1;
      this.properties.capture_hint = "Deleted box — Confirm to save";
      this.setDirtyCanvas(true, false);
    };

    node._doConfirm = async function () {
      if (this._cropPreviewOnly || !this._frameB64) {
        throw new Error(
          "crop preview only — Freeze a full frame, then draw boxes and Confirm"
        );
      }
      if (this._draft && this._draft.w >= 4 && this._draft.h >= 4) {
        this._finalizeDraft();
      }
      const targets = this._targets();
      if (!targets.length) {
        throw new Error("draw at least one target box, then Confirm");
      }
      if (!this._frameB64) throw new Error("freeze a frame or open a saved anchor");

      const id = String(this.properties.anchor_id || "anchor").trim() || "anchor";
      this.properties.anchor_id = id;
      const mode = String(this.properties.match_mode || "all");
      const need = Math.max(1, Number(this.properties.match_count) || 1);
      const thr = Number(
        this.properties.threshold != null ? this.properties.threshold : 0.7
      );
      const editing = this.properties.edit_mode === "edit";

      const res = await fetch(
        editing
          ? "/api/anchors/" + encodeURIComponent(id)
          : "/api/anchors/crop",
        {
          method: editing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            editing
              ? {
                  crops: targets,
                  threshold: thr,
                  match_mode: mode,
                  match_count: need,
                  frame_b64: this._frameB64,
                  note: "edited in " + (this.type || "node"),
                }
              : {
                  id,
                  crops: targets,
                  threshold: thr,
                  match_mode: mode,
                  match_count: need,
                  frame_b64: this._frameB64,
                  note: "from " + (this.type || "node"),
                }
          ),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "confirm failed");
      this.properties.edit_mode = "edit";
      this.properties.capture_hint =
        "Saved \"" +
        id +
        "\" ×" +
        targets.length +
        " (" +
        mode +
        (mode === "at_least" ? "≥" + need : "") +
        ")" +
        (data.has_full ? " + full.jpg" : "");
      const w = (this.widgets || []).find((x) => x.name === "anchor");
      if (w) w.value = id;
      await this._refreshAnchorList();
      this.setDirtyCanvas(true, false);
      if (global.Web2PS5Studio && global.Web2PS5Studio.pushTelemetry) {
        global.Web2PS5Studio.pushTelemetry({
          type: "anchor_saved",
          id,
          target_count: targets.length,
          match_mode: mode,
          match_count: need,
          has_full: data.has_full,
        });
      }
      if (global.Web2PS5UI && global.Web2PS5UI.onAnchorsChanged) {
        global.Web2PS5UI.onAnchorsChanged();
      }
      return data;
    };

    node._drawCapture = function (ctx, padTopY) {
      if (this.flags.collapsed) return;
      const pad = 8;
      // Band between EXEC slots (top) and widget buttons (bottom)
      const band = _captureLayout(this);
      const top = band.top;
      const listH = Math.max(80, band.height - 8);
      const imgX = CAPTURE_LIST_W + pad * 2;
      const imgW = Math.max(16, this.size[0] - imgX - pad);

      // --- saved anchors list ---
      ctx.fillStyle = "#0a0c10";
      ctx.fillRect(pad, top, CAPTURE_LIST_W, listH);
      ctx.strokeStyle = "#2a2f3a";
      ctx.strokeRect(pad, top, CAPTURE_LIST_W, listH);
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "10px sans-serif";
      ctx.fillText("Saved", pad + 6, top + 12);
      this._listRects = [];
      const rowH = 17;
      const cur = this.properties.anchor_id;
      for (let i = 0; i < (this._anchorList || []).length; i++) {
        const name = this._anchorList[i];
        const y = top + 20 + i * rowH;
        if (y + rowH > top + listH) break;
        const sel = name === cur;
        const meta =
          (this._anchorMetaById && this._anchorMetaById[name]) || {};
        const legacy = !!meta.legacy && !meta.has_full;
        if (sel) {
          ctx.fillStyle = legacy
            ? "rgba(255,171,64,0.28)"
            : "rgba(124,156,255,0.25)";
          ctx.fillRect(pad + 2, y - 11, CAPTURE_LIST_W - 4, rowH);
        }
        ctx.fillStyle = legacy ? "#ffab40" : sel ? "#7c9cff" : "#e8eaed";
        ctx.font = "10px Consolas, monospace";
        const label = legacy
          ? "L:" + String(name).slice(0, 14)
          : String(name).slice(0, 16);
        ctx.fillText(label, pad + 6, y);
        this._listRects.push({
          id: name,
          x: pad,
          y: y - 11,
          w: CAPTURE_LIST_W,
          h: rowH,
        });
      }
      if (!(this._anchorList || []).length) {
        ctx.fillStyle = "#9aa0a6";
        ctx.font = "10px sans-serif";
        ctx.fillText("none yet", pad + 6, top + 32);
      }

      // --- freeze image + boxes ---
      this._imgRect = { x: imgX, y: top, w: imgW, h: listH };
      const drawn = _letterbox(ctx, this._snap, imgX, top, imgW, listH);
      if (!drawn) {
        ctx.fillStyle = "#0a0c10";
        ctx.fillRect(imgX, top, imgW, listH);
        ctx.fillStyle = "#9aa0a6";
        ctx.font = "12px sans-serif";
        ctx.fillText("Freeze OR click a saved name", imgX + 10, top + 22);
      } else {
        this._imgRect = drawn;
        if (this._cropPreviewOnly) {
          ctx.fillStyle = "rgba(255,171,64,0.85)";
          ctx.font = "11px sans-serif";
          ctx.fillText("crop template (preview)", drawn.x + 6, drawn.y + 14);
        }
        const targets = this._cropPreviewOnly ? [] : this._targets();
        for (let i = 0; i < targets.length; i++) {
          const d = this._frameToDisplay(targets[i]);
          const sel = i === this._selectedTarget;
          ctx.strokeStyle = sel ? "#7c9cff" : "#3dd68c";
          ctx.lineWidth = sel ? 3 : 2;
          ctx.fillStyle = sel
            ? "rgba(124,156,255,0.2)"
            : "rgba(61,214,140,0.18)";
          ctx.strokeRect(drawn.x + d.x, drawn.y + d.y, d.w, d.h);
          ctx.fillRect(drawn.x + d.x, drawn.y + d.y, d.w, d.h);
          ctx.fillStyle = sel ? "#7c9cff" : "#3dd68c";
          ctx.font = "10px sans-serif";
          ctx.fillText(String(i + 1), drawn.x + d.x + 3, drawn.y + d.y + 11);
        }
        if (this._draft && this._draft.w > 0 && this._draft.h > 0) {
          ctx.strokeStyle = "#ffc450";
          ctx.lineWidth = 2;
          ctx.fillStyle = "rgba(255,196,80,0.12)";
          ctx.strokeRect(
            drawn.x + this._draft.x,
            drawn.y + this._draft.y,
            this._draft.w,
            this._draft.h
          );
          ctx.fillRect(
            drawn.x + this._draft.x,
            drawn.y + this._draft.y,
            this._draft.w,
            this._draft.h
          );
        }
      }
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "11px sans-serif";
      ctx.fillText(
        String(this.properties.capture_hint || "").slice(0, 86),
        pad,
        Math.min(top + listH - 6, (this.widgets_start_y || this.size[1]) - 8)
      );
    };

    node.onMouseDown = function (e, local) {
      // Click saved-anchor list → load freeze + boxes for edit
      for (let i = 0; i < (this._listRects || []).length; i++) {
        const r = this._listRects[i];
        if (
          local[0] >= r.x &&
          local[0] <= r.x + r.w &&
          local[1] >= r.y &&
          local[1] <= r.y + r.h
        ) {
          this._loadAnchorForEdit(r.id);
          return true;
        }
      }

      const ir = this._imgRect;
      if (!this._snap || !ir) return false;
      // Crop-only preview is view-only until Freeze attaches a full frame
      if (this._cropPreviewOnly) return true;
      if (local[1] < ir.y - 2) return false;
      if (
        local[0] < ir.x ||
        local[1] < ir.y ||
        local[0] > ir.x + ir.w ||
        local[1] > ir.y + ir.h
      ) {
        return false;
      }
      const lx = local[0] - ir.x;
      const ly = local[1] - ir.y;

      // Click existing target → select + move
      const targets = this._targets();
      for (let i = targets.length - 1; i >= 0; i--) {
        const d = this._frameToDisplay(targets[i]);
        if (lx >= d.x && lx <= d.x + d.w && ly >= d.y && ly <= d.y + d.h) {
          this._selectedTarget = i;
          this._drag = {
            mode: "move",
            index: i,
            ox: lx - d.x,
            oy: ly - d.y,
          };
          if (this.captureInput) this.captureInput(true);
          this.setDirtyCanvas(true, false);
          return true;
        }
      }

      // Empty → draw new box
      this._drag = { mode: "draw", x0: lx, y0: ly };
      this._draft = { x: lx, y: ly, w: 0, h: 0 };
      this._selectedTarget = -1;
      if (this.captureInput) this.captureInput(true);
      return true;
    };
    node.onMouseMove = function (e, local) {
      if (!this._drag) return false;
      const ir = this._imgRect;
      const lx = Math.max(0, Math.min(ir.w, local[0] - ir.x));
      const ly = Math.max(0, Math.min(ir.h, local[1] - ir.y));
      if (this._drag.mode === "move") {
        const i = this._drag.index;
        const d = this._frameToDisplay(this._targets()[i]);
        const nx = Math.max(0, Math.min(ir.w - d.w, lx - this._drag.ox));
        const ny = Math.max(0, Math.min(ir.h - d.h, ly - this._drag.oy));
        this.properties.targets[i] = this._displayToFrame({
          x: nx,
          y: ny,
          w: d.w,
          h: d.h,
        });
      } else {
        this._draft = {
          x: Math.min(this._drag.x0, lx),
          y: Math.min(this._drag.y0, ly),
          w: Math.abs(lx - this._drag.x0),
          h: Math.abs(ly - this._drag.y0),
        };
      }
      this.setDirtyCanvas(true, false);
      return true;
    };
    node.onMouseUp = function () {
      if (this._drag && this._drag.mode === "draw") this._finalizeDraft();
      this._drag = null;
      if (this.captureInput) this.captureInput(false);
      this.setDirtyCanvas(true, false);
      return false;
    };

    // Initial list load
    setTimeout(function () {
      if (node._refreshAnchorList) node._refreshAnchorList();
    }, 0);
  }

  function _addCaptureWidgets(node) {
    node.addWidget("button", "Freeze", "", function () {
      node._doFreeze();
    });
    node.addWidget("button", "Confirm", "", function () {
      node._doConfirm().catch((e) => {
        node.properties.capture_hint = String(e);
        node.setDirtyCanvas(true, false);
      });
    });
    node.addWidget("button", "Clear targets", "", function () {
      node._doClearTargets();
    });
    node.addWidget("button", "Del box", "", function () {
      if (node._doDelSelected) node._doDelSelected();
    });
    node.addWidget("button", "Refresh list", "", function () {
      if (node._refreshAnchorList) node._refreshAnchorList();
    });
    node.addWidget(
      "combo",
      "match",
      node.properties.match_mode || "all",
      function (v) {
        node.properties.match_mode = v;
      },
      { values: ["all", "any", "at_least"] }
    );
    node.addWidget(
      "number",
      "at_least",
      node.properties.match_count != null ? node.properties.match_count : 1,
      function (v) {
        node.properties.match_count = Math.max(1, v | 0);
      },
      { min: 1, max: 32, step: 1 }
    );
  }

  function _ensureCaptureWidgets(node, padTop) {
    if (typeof node._doFreeze !== "function") {
      _bindAnchorCapture(node, { padTop: padTop });
    }
    const names = (node.widgets || []).map((w) => w.name);
    if (names.indexOf("Freeze") < 0) {
      _addCaptureWidgets(node);
    } else {
      if (names.indexOf("Clear targets") < 0) {
        node.addWidget("button", "Clear targets", "", function () {
          node._doClearTargets();
        });
      }
      if (names.indexOf("Del box") < 0) {
        node.addWidget("button", "Del box", "", function () {
          if (node._doDelSelected) node._doDelSelected();
        });
      }
      if (names.indexOf("Refresh list") < 0) {
        node.addWidget("button", "Refresh list", "", function () {
          if (node._refreshAnchorList) node._refreshAnchorList();
        });
      }
      if (names.indexOf("match") < 0) {
        node.addWidget(
          "combo",
          "match",
          node.properties.match_mode || "all",
          function (v) {
            node.properties.match_mode = v;
          },
          { values: ["all", "any", "at_least"] }
        );
      }
      if (names.indexOf("at_least") < 0) {
        node.addWidget(
          "number",
          "at_least",
          node.properties.match_count != null ? node.properties.match_count : 1,
          function (v) {
            node.properties.match_count = Math.max(1, v | 0);
          },
          { min: 1, max: 32, step: 1 }
        );
      }
    }
    if (!Array.isArray(node.properties.targets)) node.properties.targets = [];
    if (!node.properties.match_mode) node.properties.match_mode = "all";
    if (node.properties.match_count == null) node.properties.match_count = 1;
    if (!node.properties.edit_mode) node.properties.edit_mode = "create";
    if (node.size[0] < 560) node.size[0] = 560;
    _captureLayout(node); // sets widgets_start_y + min height
    if (node._refreshAnchorList) node._refreshAnchorList();
  }

  function VisCheckState() {
    this.addInput("EXEC", EXEC);
    this.addInput("anchor", STRING);
    this.addInput("roi", VEC4);
    this.addOutput("EXEC", EXEC);
    this.addOutput("matched", BOOL);
    this.addOutput("score", FLOAT);
    this.size = [580, 520];
    this.addWidget(
      "text",
      "anchor",
      "my_anchor",
      (v) => (this.properties.anchor_id = v)
    );
    this.addWidget(
      "number",
      "threshold",
      0.7,
      (v) => (this.properties.threshold = v),
      { min: 0.1, max: 1.0, step: 0.05 }
    );
    this.properties = {
      anchor_id: "my_anchor",
      threshold: 0.7,
      roi: null,
      targets: [],
      match_mode: "all",
      match_count: 1,
      edit_mode: "create",
      capture_hint: "Freeze new OR click a saved name to edit",
    };
    _bindAnchorCapture(this, { padTop: 0 });
    _addCaptureWidgets(this);
    _captureLayout(this);
    styleExecNode(this, "#1a3a3a");
  }
  VisCheckState.prototype.onDrawForeground = function (ctx) {
    this._drawCapture(ctx);
  };
  VisCheckState.prototype.onConfigure = function () {
    _ensureCaptureWidgets(this, 0);
  };
  reg("vis/check_state", "vis.check_state", VisCheckState);

  function VisWaitAnchor() {
    this.addInput("EXEC", EXEC);
    this.addInput("anchor", STRING);
    this.addInput("roi", VEC4);
    this.addOutput("found", EXEC);
    this.addOutput("timeout", EXEC);
    this.addOutput("matched", BOOL);
    this.addOutput("score", FLOAT);
    this.size = [600, 540];
    this.addWidget(
      "text",
      "anchor",
      "my_anchor",
      (v) => (this.properties.anchor_id = v)
    );
    this.addWidget(
      "number",
      "threshold",
      0.7,
      (v) => (this.properties.threshold = v),
      { min: 0.1, max: 1.0, step: 0.05 }
    );
    this.addWidget(
      "number",
      "timeout_ms",
      10000,
      (v) => (this.properties.timeout_ms = v),
      { min: 100, max: 300000, step: 100 }
    );
    this.properties = {
      anchor_id: "my_anchor",
      threshold: 0.7,
      timeout_ms: 10000,
      poll_ms: 100,
      roi: null,
      targets: [],
      match_mode: "all",
      match_count: 1,
      edit_mode: "create",
      capture_hint: "Freeze new OR click a saved name to edit",
    };
    _bindAnchorCapture(this, { padTop: 0 });
    _addCaptureWidgets(this);
    _captureLayout(this);
    styleExecNode(this, "#1a4040");
  }
  VisWaitAnchor.prototype.onDrawForeground = function (ctx) {
    this._drawCapture(ctx);
  };
  VisWaitAnchor.prototype.onConfigure = function () {
    _ensureCaptureWidgets(this, 0);
  };
  VisWaitAnchor.title = "vis.wait_anchor";
  VisWaitAnchor.desc =
    "Wait for anchor. Left list = saved freezes (click to edit). Freeze→drag→Confirm.";
  reg("vis/wait_anchor", "vis.wait_anchor", VisWaitAnchor);

  /** Freeze → box ROI → Confirm for named OCR targets (like anchors). */
  function _bindOcrCapture(node) {
    node.size = node.size || [600, 520];
    if (node.size[0] < 560) node.size[0] = 560;
    if (node.size[1] < 420) node.size[1] = 420;
    node._snap = null;
    node._frameB64 = null;
    node._natural = { w: 1280, h: 720 };
    node._drag = null;
    node._draft = null;
    node._ocrList = [];
    node._ocrMetaById = {};
    node._listRects = [];
    node._imgRect = null;
    if (!Array.isArray(node.properties.targets)) node.properties.targets = [];
    if (!node.properties.ocr_id) node.properties.ocr_id = "ocr_region";
    if (!node.properties.expect) node.properties.expect = "Rest";
    if (!node.properties.mode) node.properties.mode = "contains";
    if (!node.properties.lang) node.properties.lang = "eng";
    if (node.properties.invert == null) node.properties.invert = false;
    if (!node.properties.capture_hint) {
      node.properties.capture_hint =
        "Freeze → draw ONE box (OCR ROI) → set expect → Confirm";
    }

    node._targets = function () {
      return Array.isArray(this.properties.targets) ? this.properties.targets : [];
    };
    node._displayToFrame = function (rect) {
      const ir = this._imgRect;
      const sx = this._natural.w / Math.max(1, ir.w);
      const sy = this._natural.h / Math.max(1, ir.h);
      return {
        x: Math.round(rect.x * sx),
        y: Math.round(rect.y * sy),
        w: Math.max(1, Math.round(rect.w * sx)),
        h: Math.max(1, Math.round(rect.h * sy)),
      };
    };
    node._frameToDisplay = function (box) {
      const ir = this._imgRect;
      const sx = ir.w / Math.max(1, this._natural.w);
      const sy = ir.h / Math.max(1, this._natural.h);
      return {
        x: box.x * sx,
        y: box.y * sy,
        w: box.w * sx,
        h: box.h * sy,
      };
    };
    node._finalizeDraft = function () {
      if (!this._draft || this._draft.w < 4 || this._draft.h < 4) {
        this._draft = null;
        return;
      }
      // OCR uses a single ROI box
      this.properties.targets = [this._displayToFrame(this._draft)];
      this._draft = null;
      const t = this.properties.targets[0];
      this.properties.roi = [t.x, t.y, t.w, t.h];
      this.properties.capture_hint =
        "ROI " + t.x + "," + t.y + " " + t.w + "×" + t.h + " — set expect, Confirm";
    };

    node._refreshOcrList = async function () {
      try {
        const res = await fetch("/api/ocr-targets");
        const data = await res.json();
        const rows = data.targets || [];
        this._ocrList = rows.map((t) => t.id).filter(Boolean);
        this._ocrMetaById = {};
        rows.forEach((t) => {
          this._ocrMetaById[t.id] = t;
        });
        this.setDirtyCanvas(true, false);
      } catch (_) {
        /* ignore */
      }
    };

    node._loadOcrForEdit = async function (id) {
      try {
        const res = await fetch("/api/ocr-targets/" + encodeURIComponent(id));
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "load failed");
        const meta = data.target || {};
        this.properties.ocr_id = id;
        const idW = (this.widgets || []).find((w) => w.name === "id");
        if (idW) idW.value = id;
        if (meta.expect != null) this.properties.expect = meta.expect;
        if (meta.mode) this.properties.mode = meta.mode;
        if (meta.lang) this.properties.lang = meta.lang;
        this.properties.invert = !!meta.invert;
        const exW = (this.widgets || []).find((w) => w.name === "expect");
        if (exW) exW.value = this.properties.expect;
        const moW = (this.widgets || []).find((w) => w.name === "mode");
        if (moW) moW.value = this.properties.mode;
        const invW = (this.widgets || []).find((w) => w.name === "invert");
        if (invW) invW.value = this.properties.invert;

        const roi = meta.roi || meta.crop;
        this.properties.targets = roi
          ? [{ x: roi.x | 0, y: roi.y | 0, w: roi.w | 0, h: roi.h | 0 }]
          : [];
        if (roi) this.properties.roi = [roi.x, roi.y, roi.w, roi.h];
        this.properties.edit_mode = "edit";

        if (!meta.has_full) {
          this._snap = null;
          this._frameB64 = null;
          // Still show crop preview if available
          try {
            const imgRes = await fetch(
              "/api/ocr-targets/" + encodeURIComponent(id) + "/image?" + Date.now()
            );
            if (imgRes.ok) {
              const blob = await imgRes.blob();
              const url = await _blobToDataUrl(blob);
              const img = new Image();
              await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = reject;
                img.src = url;
              });
              this._snap = img;
              this._natural = {
                w: img.naturalWidth || 64,
                h: img.naturalHeight || 64,
              };
              this.properties.targets = [];
              this.properties.capture_hint =
                'OCR "' + id + '" crop preview — Freeze full frame to edit ROI';
            } else {
              this.properties.capture_hint =
                'OCR "' + id + '" — no full.jpg; Freeze to capture ROI';
            }
          } catch (_) {
            this.properties.capture_hint =
              'OCR "' + id + '" — Freeze to capture ROI';
          }
          this.setDirtyCanvas(true, true);
          return;
        }

        const imgRes = await fetch(
          "/api/ocr-targets/" + encodeURIComponent(id) + "/full.jpg?" + Date.now()
        );
        if (!imgRes.ok) throw new Error("full frame missing");
        const blob = await imgRes.blob();
        this._frameB64 = await _blobToDataUrl(blob);
        const img = new Image();
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
          img.src = this._frameB64;
        });
        this._snap = img;
        this._natural = {
          w: img.naturalWidth || 1280,
          h: img.naturalHeight || 720,
        };
        this.properties.capture_hint =
          'EDIT OCR "' + id + '" — drag box, Confirm saves ROI + expect';
        this.setDirtyCanvas(true, true);
      } catch (err) {
        this.properties.capture_hint = String(err);
        this.setDirtyCanvas(true, false);
      }
    };

    node._doFreeze = async function () {
      try {
        const res = await fetch("/api/anchors/snapshot.jpg?" + Date.now());
        if (!res.ok) throw new Error("freeze failed: " + res.status);
        const blob = await res.blob();
        this._frameB64 = await _blobToDataUrl(blob);
        const img = new Image();
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
          img.src = this._frameB64;
        });
        this._snap = img;
        this._natural = {
          w: img.naturalWidth || 1280,
          h: img.naturalHeight || 720,
        };
        this.properties.targets = [];
        this._draft = null;
        this.properties.edit_mode = "create";
        this.properties.capture_hint =
          "NEW freeze — set id + expect, draw ONE box, Confirm";
        this.setDirtyCanvas(true, true);
      } catch (err) {
        this.properties.capture_hint = String(err);
        this.setDirtyCanvas(true, false);
      }
    };

    node._doConfirm = async function () {
      if (this._draft && this._draft.w >= 4) this._finalizeDraft();
      const targets = this._targets();
      if (!targets.length) throw new Error("draw one ROI box, then Confirm");
      if (!this._frameB64) throw new Error("Freeze a frame first");
      const id =
        String(this.properties.ocr_id || "ocr_region").trim() || "ocr_region";
      this.properties.ocr_id = id;
      const box = targets[0];
      this.properties.roi = [box.x, box.y, box.w, box.h];
      const editing = this.properties.edit_mode === "edit";
      const payload = {
        x: box.x,
        y: box.y,
        w: box.w,
        h: box.h,
        expect: String(this.properties.expect || ""),
        mode: String(this.properties.mode || "contains"),
        lang: String(this.properties.lang || "eng"),
        invert: !!this.properties.invert,
        case_sensitive: !!this.properties.case_sensitive,
        psm: Number(this.properties.psm) || 6,
        frame_b64: this._frameB64,
        note: "from " + (this.type || "ocr node"),
      };
      const res = await fetch(
        editing
          ? "/api/ocr-targets/" + encodeURIComponent(id)
          : "/api/ocr-targets",
        {
          method: editing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            editing ? payload : Object.assign({ id: id }, payload)
          ),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "save failed");
      this.properties.edit_mode = "edit";
      this.properties.capture_hint =
        'Saved OCR "' + id + '" ROI + expect="' + this.properties.expect + '"';
      await this._refreshOcrList();
      this.setDirtyCanvas(true, false);
      return data;
    };

    node._drawCapture = function (ctx) {
      if (this.flags.collapsed) return;
      const pad = 8;
      const band = _captureLayout(this);
      const top = band.top;
      const listH = Math.max(80, band.height - 8);
      const imgX = CAPTURE_LIST_W + pad * 2;
      const imgW = Math.max(16, this.size[0] - imgX - pad);

      ctx.fillStyle = "#0a0c10";
      ctx.fillRect(pad, top, CAPTURE_LIST_W, listH);
      ctx.strokeStyle = "#2a2f3a";
      ctx.strokeRect(pad, top, CAPTURE_LIST_W, listH);
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "10px sans-serif";
      ctx.fillText("OCR targets", pad + 6, top + 12);
      this._listRects = [];
      const rowH = 17;
      const cur = this.properties.ocr_id;
      for (let i = 0; i < (this._ocrList || []).length; i++) {
        const name = this._ocrList[i];
        const y = top + 20 + i * rowH;
        if (y + rowH > top + listH) break;
        const sel = name === cur;
        if (sel) {
          ctx.fillStyle = "rgba(124,156,255,0.25)";
          ctx.fillRect(pad + 2, y - 11, CAPTURE_LIST_W - 4, rowH);
        }
        ctx.fillStyle = sel ? "#7c9cff" : "#e8eaed";
        ctx.font = "10px Consolas, monospace";
        ctx.fillText(String(name).slice(0, 16), pad + 6, y);
        this._listRects.push({
          id: name,
          x: pad,
          y: y - 11,
          w: CAPTURE_LIST_W,
          h: rowH,
        });
      }

      this._imgRect = { x: imgX, y: top, w: imgW, h: listH };
      const drawn = _letterbox(ctx, this._snap, imgX, top, imgW, listH);
      if (!drawn) {
        ctx.fillStyle = "#0a0c10";
        ctx.fillRect(imgX, top, imgW, listH);
        ctx.fillStyle = "#9aa0a6";
        ctx.font = "12px sans-serif";
        ctx.fillText("Freeze OR click a saved OCR name", imgX + 10, top + 22);
      } else {
        this._imgRect = drawn;
        const targets = this._targets();
        for (let i = 0; i < targets.length; i++) {
          const d = this._frameToDisplay(targets[i]);
          ctx.strokeStyle = "#ffc450";
          ctx.lineWidth = 3;
          ctx.fillStyle = "rgba(255,196,80,0.15)";
          ctx.strokeRect(drawn.x + d.x, drawn.y + d.y, d.w, d.h);
          ctx.fillRect(drawn.x + d.x, drawn.y + d.y, d.w, d.h);
          ctx.fillStyle = "#ffc450";
          ctx.font = "10px sans-serif";
          ctx.fillText("OCR", drawn.x + d.x + 3, drawn.y + d.y + 11);
        }
        if (this._draft && this._draft.w > 0) {
          ctx.strokeStyle = "#7c9cff";
          ctx.lineWidth = 2;
          ctx.strokeRect(
            drawn.x + this._draft.x,
            drawn.y + this._draft.y,
            this._draft.w,
            this._draft.h
          );
        }
      }
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "11px sans-serif";
      ctx.fillText(
        String(this.properties.capture_hint || "").slice(0, 86),
        pad,
        Math.min(top + listH - 6, (this.widgets_start_y || this.size[1]) - 8)
      );
    };

    node.onMouseDown = function (e, local) {
      for (let i = 0; i < (this._listRects || []).length; i++) {
        const r = this._listRects[i];
        if (
          local[0] >= r.x &&
          local[0] <= r.x + r.w &&
          local[1] >= r.y &&
          local[1] <= r.y + r.h
        ) {
          this._loadOcrForEdit(r.id);
          return true;
        }
      }
      const ir = this._imgRect;
      if (!this._snap || !ir || !this._frameB64) return false;
      if (
        local[0] < ir.x ||
        local[1] < ir.y ||
        local[0] > ir.x + ir.w ||
        local[1] > ir.y + ir.h
      ) {
        return false;
      }
      const lx = local[0] - ir.x;
      const ly = local[1] - ir.y;
      this._drag = { mode: "draw", x0: lx, y0: ly };
      this._draft = { x: lx, y: ly, w: 0, h: 0 };
      if (this.captureInput) this.captureInput(true);
      return true;
    };
    node.onMouseMove = function (e, local) {
      if (!this._drag || this._drag.mode !== "draw" || !this._imgRect) return false;
      const ir = this._imgRect;
      let lx = local[0] - ir.x;
      let ly = local[1] - ir.y;
      lx = Math.max(0, Math.min(ir.w, lx));
      ly = Math.max(0, Math.min(ir.h, ly));
      const x0 = this._drag.x0;
      const y0 = this._drag.y0;
      this._draft = {
        x: Math.min(x0, lx),
        y: Math.min(y0, ly),
        w: Math.abs(lx - x0),
        h: Math.abs(ly - y0),
      };
      this.setDirtyCanvas(true, false);
      return true;
    };
    node.onMouseUp = function () {
      if (this._drag && this._drag.mode === "draw") this._finalizeDraft();
      this._drag = null;
      if (this.captureInput) this.captureInput(false);
      this.setDirtyCanvas(true, false);
      return false;
    };

    // Widgets
    node.addWidget("text", "id", node.properties.ocr_id, function (v) {
      node.properties.ocr_id = v;
    });
    node.addWidget("text", "expect", node.properties.expect, function (v) {
      node.properties.expect = v;
    });
    node.addWidget(
      "combo",
      "mode",
      node.properties.mode,
      function (v) {
        node.properties.mode = v;
      },
      { values: ["contains", "equals", "regex"] }
    );
    node.addWidget(
      "toggle",
      "invert",
      !!node.properties.invert,
      function (v) {
        node.properties.invert = !!v;
      },
      { on: "ON", off: "off" }
    );
    node.addWidget("button", "Freeze", "", function () {
      node._doFreeze().catch(function (e) {
        node.properties.capture_hint = String(e);
        node.setDirtyCanvas(true, false);
      });
    });
    node.addWidget("button", "Confirm", "", function () {
      node._doConfirm().catch(function (e) {
        node.properties.capture_hint = String(e);
        node.setDirtyCanvas(true, false);
      });
    });
    _captureLayout(node);
    setTimeout(function () {
      node._refreshOcrList();
    }, 0);
  }

  function VisOcrCheck() {
    this.addInput("EXEC", EXEC);
    this.addInput("ocr_id", STRING);
    this.addInput("expect", STRING);
    this.addInput("roi", VEC4);
    this.addOutput("EXEC", EXEC);
    this.addOutput("matched", BOOL);
    this.addOutput("text", STRING);
    this.properties = {
      ocr_id: "ocr_region",
      expect: "Rest",
      mode: "contains",
      lang: "eng",
      invert: false,
      case_sensitive: false,
      psm: 6,
      roi: null,
      targets: [],
      edit_mode: "create",
      capture_hint: "Freeze → box OCR area → set expect → Confirm",
    };
    _bindOcrCapture(this);
    styleExecNode(this, "#2a3a48");
  }
  VisOcrCheck.prototype.onDrawForeground = function (ctx) {
    this._drawCapture(ctx);
  };
  VisOcrCheck.prototype.onConfigure = function () {
    if (this._refreshOcrList) this._refreshOcrList();
  };
  VisOcrCheck.title = "vis.ocr_check";
  VisOcrCheck.desc =
    "OCR check with Freeze/box capture (named targets in data/ocr/). Needs Tesseract.";
  reg("vis/ocr_check", "vis.ocr_check", VisOcrCheck);

  function VisWaitOcr() {
    this.addInput("EXEC", EXEC);
    this.addInput("ocr_id", STRING);
    this.addInput("expect", STRING);
    this.addInput("roi", VEC4);
    this.addOutput("found", EXEC);
    this.addOutput("timeout", EXEC);
    this.addOutput("matched", BOOL);
    this.addOutput("text", STRING);
    this.properties = {
      ocr_id: "ocr_region",
      expect: "Rest",
      mode: "contains",
      lang: "eng",
      invert: false,
      case_sensitive: false,
      psm: 6,
      timeout_ms: 10000,
      poll_ms: 200,
      roi: null,
      targets: [],
      edit_mode: "create",
      capture_hint: "Freeze → box OCR area → set expect → Confirm",
    };
    _bindOcrCapture(this);
    this.addWidget(
      "number",
      "timeout_ms",
      this.properties.timeout_ms,
      function (v) {
        this.properties.timeout_ms = v;
      }.bind(this),
      { min: 100, max: 300000, step: 100 }
    );
    styleExecNode(this, "#243848");
  }
  VisWaitOcr.prototype.onDrawForeground = function (ctx) {
    this._drawCapture(ctx);
  };
  VisWaitOcr.prototype.onConfigure = function () {
    if (this._refreshOcrList) this._refreshOcrList();
  };
  VisWaitOcr.title = "vis.wait_ocr";
  VisWaitOcr.desc =
    "Wait until OCR matches expect in the captured ROI. Needs Tesseract.";
  reg("vis/wait_ocr", "vis.wait_ocr", VisWaitOcr);

  function VisFrameSnapshot() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addWidget("text", "name", "nav", (v) => (this.properties.name = v));
    this.properties = { name: "nav" };
    styleExecNode(this, "#2a4048");
  }
  VisFrameSnapshot.title = "vis.frame_snapshot";
  VisFrameSnapshot.desc = "Store a tiny fingerprint of the current frame (for change checks).";
  reg("vis/frame_snapshot", "vis.frame_snapshot", VisFrameSnapshot);

  function VisFrameChanged() {
    this.addInput("EXEC", EXEC);
    this.addOutput("EXEC", EXEC);
    this.addOutput("changed", BOOL);
    this.addOutput("score", FLOAT);
    this.addWidget("text", "name", "nav", (v) => (this.properties.name = v));
    this.addWidget(
      "number",
      "threshold",
      0.02,
      (v) => (this.properties.threshold = v),
      { min: 0.001, max: 0.5, step: 0.001 }
    );
    this.addWidget(
      "toggle",
      "update",
      true,
      (v) => (this.properties.update = !!v),
      { on: "ON", off: "off" }
    );
    this.properties = { name: "nav", threshold: 0.02, update: true };
    styleExecNode(this, "#2a4840");
  }
  VisFrameChanged.title = "vis.frame_changed";
  VisFrameChanged.desc =
    "Compare live frame to last snapshot (same name). changed=false ⇒ screen did not move.";
  reg("vis/frame_changed", "vis.frame_changed", VisFrameChanged);

  global.Web2PS5Nodes = {
    EXEC,
    BOOL,
    FLOAT,
    STRING,
    VEC4,
  };
})(window);
