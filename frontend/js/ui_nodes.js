/**
 * Canvas UI tools as real LiteGraph nodes — zoom/pan/resize with the graph.
 * Types: ui/preview, ui/anchors, ui/macros, ui/telemetry, ui/note
 */
(function (global) {
  const LiteGraph = global.LiteGraph;
  if (!LiteGraph) {
    console.error("ui_nodes.js: LiteGraph missing");
    return;
  }

  const PREVIEW_URL = "/api/preview/mjpeg";

  // Live detection overlays (from run telemetry + optional /detect poll)
  const detectionState = {
    boxes: [],
    frameW: 1280,
    frameH: 720,
    anchorId: null,
    matched: false,
    hits: 0,
    targetCount: 0,
    ts: 0,
    pollTimer: 0,
    pollBusy: false,
    setFromDetect(payload) {
      if (!payload) return;
      this.boxes = Array.isArray(payload.boxes) ? payload.boxes : [];
      const fs = payload.frame_size || {};
      this.frameW = fs.width || this.frameW || 1280;
      this.frameH = fs.height || this.frameH || 720;
      this.anchorId = payload.anchor_id || this.anchorId;
      this.matched = !!payload.matched;
      this.hits = payload.hits != null ? payload.hits : this.hits;
      this.targetCount =
        payload.target_count != null ? payload.target_count : this.targetCount;
      this.ts = Date.now();
      previewState.kickRedraw();
    },
    clear() {
      this.boxes = [];
      this.matched = false;
      this.hits = 0;
      this.ts = Date.now();
      previewState.kickRedraw();
    },
  };

  // --- shared MJPEG (one hidden <img>, refcounted) ---
  const previewState = {
    img: null,
    refs: new Set(),
    raf: 0,
    ensureImg() {
      if (this.img) return this.img;
      let el = document.getElementById("preview-stream");
      if (!el) {
        el = document.createElement("img");
        el.id = "preview-stream";
        el.alt = "";
        el.style.cssText =
          "position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;pointer-events:none";
        document.body.appendChild(el);
      }
      this.img = el;
      return el;
    },
    acquire(node) {
      this.refs.add(node);
      const el = this.ensureImg();
      if (!el.getAttribute("src")) {
        el.src = PREVIEW_URL + "?t=" + Date.now();
      }
      this.kickRedraw();
      detectionPoll.sync();
    },
    release(node) {
      this.refs.delete(node);
      if (this.refs.size === 0 && this.img) {
        this.img.removeAttribute("src");
        try {
          this.img.src = "";
        } catch (_) {
          /* ignore */
        }
      }
      detectionPoll.sync();
    },
    kickRedraw() {
      if (this.raf) return;
      const tick = () => {
        this.raf = 0;
        if (!this.refs.size) return;
        const studio = global.Web2PS5Studio;
        if (studio && studio.graph) {
          studio.graph.setDirtyCanvas(true, false);
        }
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    },
  };

  const detectionPoll = {
    sync() {
      const anyOn = [...previewState.refs].some(
        (n) => n.properties && n.properties.detections !== false
      );
      if (anyOn && previewState.refs.size) this.start();
      else this.stop();
    },
    start() {
      if (detectionState.pollTimer) return;
      detectionState.pollTimer = setInterval(() => this.tick(), 400);
      this.tick();
    },
    stop() {
      if (detectionState.pollTimer) {
        clearInterval(detectionState.pollTimer);
        detectionState.pollTimer = 0;
      }
    },
    watchIds() {
      const ids = new Set();
      for (const n of previewState.refs) {
        const w = n.properties && n.properties.watch;
        if (w && String(w).trim()) ids.add(String(w).trim());
      }
      const studio = global.Web2PS5Studio;
      if (studio && studio.graph) {
        ["ui/preview", "vis/wait_anchor", "vis/check_state"].forEach((t) => {
          (studio.graph.findNodesByType(t) || []).forEach((n) => {
            if (t === "ui/preview") {
              const w = n.properties && n.properties.watch;
              if (w && String(w).trim()) ids.add(String(w).trim());
            } else {
              const id = n.properties && n.properties.anchor_id;
              if (id && String(id).trim() && id !== "demo_bar") {
                ids.add(String(id).trim());
              }
            }
          });
        });
      }
      return [...ids];
    },
    watchOcrIds() {
      const ids = new Set();
      const studio = global.Web2PS5Studio;
      if (!(studio && studio.graph)) return [];
      ["vis/wait_ocr", "vis/ocr_check"].forEach((t) => {
        (studio.graph.findNodesByType(t) || []).forEach((n) => {
          const id = n.properties && n.properties.ocr_id;
          if (id && String(id).trim()) ids.add(String(id).trim());
        });
      });
      return [...ids];
    },
    async tick() {
      if (detectionState.pollBusy) return;
      const ids = this.watchIds();
      const ocrIds = this.watchOcrIds();
      if (!ids.length && !ocrIds.length) return;
      detectionState.pollBusy = true;
      try {
        const allBoxes = [];
        let frameW = 1280;
        let frameH = 720;
        let hits = 0;
        let matchedAny = false;
        let label = ids[0] || ocrIds[0] || "detect";

        for (const id of ids.slice(0, 3)) {
          const res = await fetch("/api/anchors/detect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id }),
          });
          if (!res.ok) continue;
          const data = await res.json();
          const fs = data.frame_size || {};
          frameW = fs.width || frameW;
          frameH = fs.height || frameH;
          (data.boxes || []).forEach((b) => {
            allBoxes.push({ ...b, anchor_id: id, kind: b.kind || "anchor" });
          });
          hits += data.hits || 0;
          if (data.matched) matchedAny = true;
        }

        for (const id of ocrIds.slice(0, 2)) {
          const res = await fetch("/api/vision/ocr", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ocr_id: id }),
          });
          if (!res.ok) continue;
          const data = await res.json();
          const fs = data.frame_size || {};
          frameW = fs.width || frameW;
          frameH = fs.height || frameH;
          (data.boxes || []).forEach((b) => {
            allBoxes.push({
              ...b,
              anchor_id: id,
              kind: "ocr",
              found: true,
            });
          });
          hits += data.hits || 0;
          if (data.matched) matchedAny = true;
          if (!ids.length) label = "ocr:" + id;
        }

        detectionState.setFromDetect({
          boxes: allBoxes,
          frame_size: { width: frameW, height: frameH },
          anchor_id: label,
          matched: matchedAny,
          hits,
          target_count: allBoxes.length,
        });
      } catch (_) {
        /* ignore poll errors */
      } finally {
        detectionState.pollBusy = false;
      }
    },
  };

  function styleUi(node, color) {
    node.color = color || "#2a3548";
    node.bgcolor = "#141a24";
    node.boxcolor = "#7c9cff";
    node.resizable = true;
  }

  function letterbox(ctx, img, x, y, w, h) {
    if (!img || !img.naturalWidth) return false;
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

  // ---------- ui/preview ----------
  function UiPreview() {
    this.title = "ui.preview";
    this.size = [520, 340];
    this.properties = {
      live: true,
      detections: true,
      watch: "", // optional anchor id; empty → auto from wait_anchor nodes
    };
    const node = this;
    this.addWidget("toggle", "live", true, function (v) {
      node.properties.live = !!v;
      if (v) previewState.acquire(node);
      else previewState.release(node);
    });
    this.addWidget("toggle", "detections", true, function (v) {
      node.properties.detections = !!v;
      if (!v) detectionState.clear();
      detectionPoll.sync();
      node.setDirtyCanvas(true, false);
    });
    this.addWidget("text", "watch", "", function (v) {
      node.properties.watch = v;
      detectionPoll.sync();
    });
    styleUi(this, "#1a3048");
  }
  UiPreview.prototype.onAdded = function () {
    if (this.properties.live !== false) previewState.acquire(this);
    detectionPoll.sync();
  };
  UiPreview.prototype.onConfigure = function () {
    if (this.properties.detections == null) this.properties.detections = true;
    if (this.properties.live !== false) previewState.acquire(this);
    const names = (this.widgets || []).map((w) => w.name);
    const node = this;
    if (names.indexOf("detections") < 0) {
      this.addWidget(
        "toggle",
        "detections",
        this.properties.detections !== false,
        function (v) {
          node.properties.detections = !!v;
          if (!v) detectionState.clear();
          detectionPoll.sync();
        }
      );
    }
    if (names.indexOf("watch") < 0) {
      this.addWidget("text", "watch", this.properties.watch || "", function (v) {
        node.properties.watch = v;
        detectionPoll.sync();
      });
    }
    detectionPoll.sync();
  };
  UiPreview.prototype.onRemoved = function () {
    previewState.release(this);
  };
  UiPreview.prototype.onDrawForeground = function (ctx) {
    if (this.flags.collapsed) return;
    const pad = 8;
    const top = 58;
    const w = this.size[0] - pad * 2;
    const h = this.size[1] - top - pad;
    if (w < 8 || h < 8) return;
    const img = previewState.img;
    const drawn =
      this.properties.live !== false && letterbox(ctx, img, pad, top, w, h);
    if (!drawn) {
      ctx.fillStyle = "#0a0c10";
      ctx.fillRect(pad, top, w, h);
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "12px sans-serif";
      ctx.fillText(
        this.properties.live === false ? "live OFF" : "waiting for stream…",
        pad + 10,
        top + 22
      );
      return;
    }
    if (this.properties.detections === false) return;

    const boxes = detectionState.boxes || [];
    const fw = detectionState.frameW || 1280;
    const fh = detectionState.frameH || 720;
    const sx = drawn.w / fw;
    const sy = drawn.h / fh;
    for (let i = 0; i < boxes.length; i++) {
      const b = boxes[i];
      if (!b) continue;
      const isOcr = b.kind === "ocr";
      if (!isOcr && !b.found && b.score < 0.15) continue;
      const x = drawn.x + b.x * sx;
      const y = drawn.y + b.y * sy;
      const bw = b.w * sx;
      const bh = b.h * sy;
      const hit = !!b.hit;
      ctx.strokeStyle = hit ? "#3dd68c" : isOcr ? "#7c9cff" : "#ffc450";
      ctx.lineWidth = hit ? 2.5 : 1.5;
      ctx.fillStyle = hit
        ? "rgba(61,214,140,0.18)"
        : isOcr
          ? "rgba(124,156,255,0.12)"
          : "rgba(255,196,80,0.10)";
      ctx.strokeRect(x, y, bw, bh);
      ctx.fillRect(x, y, bw, bh);
      let label;
      if (isOcr) {
        label =
          "OCR " +
          (hit ? "MATCH" : "…") +
          (b.expect ? ' "' + String(b.expect).slice(0, 18) + '"' : "");
        if (b.label) label += " → " + String(b.label).slice(0, 24);
      } else {
        label =
          "#" +
          (b.index != null ? b.index + 1 : i + 1) +
          " " +
          (b.score != null ? Number(b.score).toFixed(2) : "");
      }
      ctx.font = "11px sans-serif";
      ctx.fillStyle = hit ? "#3dd68c" : isOcr ? "#7c9cff" : "#ffc450";
      ctx.fillText(label, x + 3, y + 12);
    }
    if (boxes.length) {
      ctx.font = "11px sans-serif";
      ctx.fillStyle = detectionState.matched ? "#3dd68c" : "#9aa0a6";
      const summary =
        (detectionState.anchorId || "detect") +
        "  hits " +
        detectionState.hits +
        "/" +
        (detectionState.targetCount || boxes.length) +
        (detectionState.matched ? "  MATCH" : "");
      ctx.fillText(summary, drawn.x + 4, drawn.y + drawn.h - 6);
    }
  };
  LiteGraph.registerNodeType("ui/preview", UiPreview);

  // ---------- ui/anchors (library: multi-freeze create + list + edit) ----------
  const LIST_W = 150;

  function UiAnchors() {
    this.title = "ui.anchors";
    this.size = [640, 480];
    this.properties = {
      anchor_id: "my_anchor",
      match_mode: "all",
      match_count: 1,
      threshold: 0.7,
      hint: "Freeze new OR click a name to edit",
      mode: "create", // create | edit
    };
    this._list = [];
    this._snap = null;
    this._frameB64 = null;
    this._natural = { w: 1280, h: 720 };
    this._targets = []; // frame-space boxes
    this._draft = null;
    this._drag = null;
    this._selected = -1;
    this._imgRect = { x: LIST_W + 16, y: 150, w: 400, h: 260 };
    this._listRects = [];
    const node = this;
    this.addWidget("text", "id", this.properties.anchor_id, function (v) {
      node.properties.anchor_id = v;
    });
    this.addWidget(
      "combo",
      "match",
      "all",
      function (v) {
        node.properties.match_mode = v;
      },
      { values: ["all", "any", "at_least"] }
    );
    this.addWidget(
      "number",
      "at_least",
      1,
      function (v) {
        node.properties.match_count = Math.max(1, v | 0);
      },
      { min: 1, max: 32, step: 1 }
    );
    this.addWidget(
      "number",
      "threshold",
      0.7,
      function (v) {
        node.properties.threshold = v;
      },
      { min: 0.1, max: 1.0, step: 0.05 }
    );
    this.addWidget("button", "Refresh list", "", function () {
      node._refreshList();
    });
    this.addWidget("button", "Freeze new", "", function () {
      node._doFreezeNew();
    });
    this.addWidget("button", "Save", "", function () {
      node._doSave().catch((e) => {
        node.properties.hint = String(e);
        node.setDirtyCanvas(true, false);
      });
    });
    this.addWidget("button", "Clear boxes", "", function () {
      node._targets = [];
      node._draft = null;
      node._selected = -1;
      node.properties.hint = "Boxes cleared — drag new targets";
      node.setDirtyCanvas(true, false);
    });
    this.addWidget("button", "Del selected", "", function () {
      if (node._selected >= 0 && node._selected < node._targets.length) {
        node._targets.splice(node._selected, 1);
        node._selected = -1;
        node.properties.hint = "Deleted target — Save to apply";
        node.setDirtyCanvas(true, false);
      }
    });
    this.addWidget("button", "Delete anchor", "", function () {
      node._doDeleteAnchor().catch((e) => {
        node.properties.hint = String(e);
        node.setDirtyCanvas(true, false);
      });
    });
    styleUi(this, "#2a4030");
    setTimeout(function () {
      node._refreshList();
    }, 0);
  }

  UiAnchors.prototype.onAdded = function () {
    this._refreshList();
  };
  UiAnchors.prototype.onConfigure = function () {
    if (!Array.isArray(this._targets)) this._targets = [];
    if (!Array.isArray(this._list)) this._list = [];
    this._refreshList();
  };

  UiAnchors.prototype._refreshList = async function () {
    try {
      const res = await fetch("/api/anchors");
      const data = await res.json();
      const rows = (data.anchors || []).filter(
        (a) => a && a.id && a.id !== "demo_bar"
      );
      this._list = rows.map((a) => a.id);
      this._metaById = {};
      rows.forEach((a) => {
        this._metaById[a.id] = {
          legacy: !!a.legacy,
          has_full: !!a.has_full,
        };
      });
      const legacyCount = rows.filter((a) => a.legacy && !a.has_full).length;
      this.properties.hint =
        this._list.length +
        " anchors" +
        (legacyCount ? " (" + legacyCount + " LEGACY)" : "") +
        " — click a name to edit, or Freeze new";
      this.setDirtyCanvas(true, false);
    } catch (err) {
      this.properties.hint = String(err);
      this.setDirtyCanvas(true, false);
    }
  };

  UiAnchors.prototype._blobToDataUrl = function (blob) {
    return new Promise(function (resolve, reject) {
      const r = new FileReader();
      r.onload = function () {
        resolve(r.result);
      };
      r.onerror = reject;
      r.readAsDataURL(blob);
    });
  };

  UiAnchors.prototype._doFreezeNew = async function () {
    try {
      const res = await fetch("/api/anchors/snapshot.jpg?" + Date.now());
      if (!res.ok) throw new Error("freeze failed: " + res.status);
      const blob = await res.blob();
      this._frameB64 = await this._blobToDataUrl(blob);
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
      this._targets = [];
      this._draft = null;
      this._selected = -1;
      this.properties.mode = "create";
      this.properties.hint =
        "NEW freeze — set id, drag target(s), Save (creates another anchor)";
      if (this.size[0] < 640) this.size[0] = 640;
      if (this.size[1] < 480) this.size[1] = 480;
      this.setDirtyCanvas(true, true);
    } catch (err) {
      this.properties.hint = String(err);
      this.setDirtyCanvas(true, false);
    }
  };

  UiAnchors.prototype._loadImageUrl = async function (url) {
    const imgRes = await fetch(url);
    if (!imgRes.ok) throw new Error("image load failed: " + imgRes.status);
    const blob = await imgRes.blob();
    const dataUrl = await this._blobToDataUrl(blob);
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = dataUrl;
    });
    return { img: img, dataUrl: dataUrl };
  };

  UiAnchors.prototype._showCropPreview = async function (id, meta) {
    const cropUrl =
      (meta && meta.crop_url) ||
      "/api/anchors/" + encodeURIComponent(id) + "/image";
    const loaded = await this._loadImageUrl(cropUrl + "?" + Date.now());
    this._snap = loaded.img;
    this._frameB64 = null;
    this._cropPreviewOnly = true;
    this._natural = {
      w: loaded.img.naturalWidth || 64,
      h: loaded.img.naturalHeight || 64,
    };
    this._targets = [];
    this._selected = -1;
    this._draft = null;
    const legacy = !!(meta && meta.legacy);
    this.properties.hint = legacy
      ? 'LEGACY crop "' + id + '" — Freeze new to retake full frame'
      : 'Crop "' + id + '" (no full.jpg) — Freeze new to attach reference';
    if (this.size[0] < 640) this.size[0] = 640;
    if (this.size[1] < 480) this.size[1] = 480;
    this.setDirtyCanvas(true, true);
  };

  UiAnchors.prototype._loadAnchorForEdit = async function (id) {
    try {
      const res = await fetch("/api/anchors/" + encodeURIComponent(id));
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "load failed");
      const meta = data.anchor || {};
      this.properties.anchor_id = id;
      const idW = (this.widgets || []).find((w) => w.name === "id");
      if (idW) idW.value = id;
      this.properties.match_mode = meta.match_mode || "all";
      this.properties.match_count = meta.match_count || 1;
      this.properties.threshold =
        meta.threshold != null ? meta.threshold : 0.7;
      const matchW = (this.widgets || []).find((w) => w.name === "match");
      if (matchW) matchW.value = this.properties.match_mode;
      const atW = (this.widgets || []).find((w) => w.name === "at_least");
      if (atW) atW.value = this.properties.match_count;
      const thW = (this.widgets || []).find((w) => w.name === "threshold");
      if (thW) thW.value = this.properties.threshold;

      this._targets = Array.isArray(meta.crops)
        ? meta.crops.map((c) => ({
            x: c.x | 0,
            y: c.y | 0,
            w: c.w | 0,
            h: c.h | 0,
          }))
        : [];
      this._draft = null;
      this._selected = this._targets.length ? 0 : -1;
      this.properties.mode = "edit";

      if (!meta.has_full) {
        await this._showCropPreview(id, meta);
        if (meta.legacy) {
          const retake = window.confirm(
            'LEGACY — no full reference frame\n\n"' +
              id +
              '" shows its crop template only.\nRetake a full freeze to edit boxes on-screen?\n\nOK = Retake (Freeze)\nCancel = Keep viewing crop'
          );
          if (retake) {
            await this._doFreezeNew();
            this.properties.mode = "edit";
            this.properties.anchor_id = id;
            const idW2 = (this.widgets || []).find((w) => w.name === "id");
            if (idW2) idW2.value = id;
            this.properties.hint =
              'RETAKE "' + id + '" — drag target(s), Save (clears LEGACY)';
            this.setDirtyCanvas(true, true);
          }
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
      this.properties.hint =
        "EDIT \"" +
        id +
        "\" — " +
        this._targets.length +
        " box(es). Drag to add, click box to select, Save";
      this.setDirtyCanvas(true, true);
    } catch (err) {
      this.properties.hint = String(err);
      this.setDirtyCanvas(true, false);
    }
  };

  UiAnchors.prototype._displayToFrame = function (rect) {
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

  UiAnchors.prototype._frameToDisplay = function (box) {
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

  UiAnchors.prototype._finalizeDraft = function () {
    if (!this._draft || this._draft.w < 4 || this._draft.h < 4) {
      this._draft = null;
      return;
    }
    this._targets.push(this._displayToFrame(this._draft));
    this._selected = this._targets.length - 1;
    this._draft = null;
    this.properties.hint =
      this._targets.length + " target(s) — Save, or drag another";
  };

  UiAnchors.prototype._doSave = async function () {
    if (this._cropPreviewOnly || !this._frameB64) {
      throw new Error(
        "crop preview only — Freeze new, draw boxes, then Save"
      );
    }
    if (this._draft && this._draft.w >= 4) this._finalizeDraft();
    if (!this._targets.length) throw new Error("draw at least one target box");
    const id = String(this.properties.anchor_id || "anchor").trim() || "anchor";
    this.properties.anchor_id = id;
    const mode = this.properties.match_mode || "all";
    const need = Math.max(1, Number(this.properties.match_count) || 1);
    const thr = Number(this.properties.threshold != null ? this.properties.threshold : 0.7);

    let res;
    if (this.properties.mode === "edit" && !this._frameB64) {
      throw new Error("no full frame to edit — Freeze new or pick another");
    }
    if (this.properties.mode === "edit") {
      // Prefer PUT from stored full (omit frame if we loaded from disk and didn't re-freeze)
      // Always send frame_b64 when we have it so crops cut from what's on screen
      res = await fetch("/api/anchors/" + encodeURIComponent(id), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          crops: this._targets,
          threshold: thr,
          match_mode: mode,
          match_count: need,
          frame_b64: this._frameB64 || undefined,
          note: "edited in ui/anchors",
        }),
      });
    } else {
      if (!this._frameB64) throw new Error("Freeze new first");
      res = await fetch("/api/anchors/crop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          crops: this._targets,
          threshold: thr,
          match_mode: mode,
          match_count: need,
          frame_b64: this._frameB64,
          note: "from ui/anchors",
        }),
      });
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "save failed");
    this.properties.mode = "edit";
    this.properties.hint =
      "Saved \"" +
      id +
      "\" ×" +
      this._targets.length +
      " (" +
      mode +
      ")" +
      (data.has_full ? " + full.jpg" : "");
    await this._refreshList();
    if (global.Web2PS5Studio && global.Web2PS5Studio.pushTelemetry) {
      global.Web2PS5Studio.pushTelemetry({
        type: "anchor_saved",
        id,
        target_count: this._targets.length,
        match_mode: mode,
        has_full: data.has_full,
      });
    }
    if (global.Web2PS5UI && global.Web2PS5UI.onAnchorsChanged) {
      global.Web2PS5UI.onAnchorsChanged();
    }
    this.setDirtyCanvas(true, false);
  };

  UiAnchors.prototype._doDeleteAnchor = async function () {
    const id = String(this.properties.anchor_id || "").trim();
    if (!id) throw new Error("no anchor id");
    if (id === "demo_bar") throw new Error("cannot delete demo_bar");
    const res = await fetch("/api/anchors/" + encodeURIComponent(id), {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "delete failed");
    this._snap = null;
    this._frameB64 = null;
    this._targets = [];
    this.properties.hint = "Deleted \"" + id + "\"";
    await this._refreshList();
    this.setDirtyCanvas(true, true);
  };

  UiAnchors.prototype._layoutCaptureBand = function () {
    const slotH =
      (typeof LiteGraph !== "undefined" && LiteGraph.NODE_SLOT_HEIGHT) || 20;
    const wh =
      (typeof LiteGraph !== "undefined" && LiteGraph.NODE_WIDGET_HEIGHT) || 20;
    const rows = Math.max(
      (this.inputs && this.inputs.length) || 0,
      (this.outputs && this.outputs.length) || 0,
      1
    );
    const slotBottom = rows * slotH + 6;
    let widgetStack = 8;
    (this.widgets || []).forEach((w) => {
      const h =
        w.computeSize && typeof w.computeSize === "function"
          ? w.computeSize(this.size[0])[1]
          : wh;
      widgetStack += h + 4;
    });
    const minCapture = 220;
    const need = slotBottom + minCapture + widgetStack + 24;
    if (this.size[1] < need) this.size[1] = need;
    const bottom = Math.max(
      slotBottom + minCapture,
      this.size[1] - widgetStack - 16
    );
    this.widgets_start_y = bottom + 4;
    return { top: slotBottom, bottom: bottom, height: bottom - slotBottom };
  };

  UiAnchors.prototype.onDrawForeground = function (ctx) {
    if (this.flags.collapsed) return;
    const pad = 8;
    const band = this._layoutCaptureBand();
    const top = band.top;
    const listX = pad;
    const listY = top;
    const listH = Math.max(80, band.height - 8);
    const imgX = LIST_W + pad * 2;
    const imgW = Math.max(16, this.size[0] - imgX - pad);
    const imgH = listH;

    // --- name list ---
    ctx.fillStyle = "#0a0c10";
    ctx.fillRect(listX, listY, LIST_W, listH);
    ctx.strokeStyle = "#2a2f3a";
    ctx.strokeRect(listX, listY, LIST_W, listH);
    ctx.fillStyle = "#9aa0a6";
    ctx.font = "11px sans-serif";
    ctx.fillText("Anchors", listX + 6, listY + 14);
    this._listRects = [];
    const rowH = 18;
    const cur = this.properties.anchor_id;
    for (let i = 0; i < this._list.length; i++) {
      const name = this._list[i];
      const y = listY + 22 + i * rowH;
      if (y + rowH > listY + listH) break;
      const selected = name === cur;
      const meta = (this._metaById && this._metaById[name]) || {};
      const legacy = !!meta.legacy && !meta.has_full;
      if (selected) {
        ctx.fillStyle = legacy
          ? "rgba(255,171,64,0.28)"
          : "rgba(124,156,255,0.25)";
        ctx.fillRect(listX + 2, y - 12, LIST_W - 4, rowH);
      }
      ctx.fillStyle = legacy ? "#ffab40" : selected ? "#7c9cff" : "#e8eaed";
      ctx.font = "11px Consolas, monospace";
      const label = legacy
        ? "L:" + name.slice(0, 16)
        : name.slice(0, 18);
      ctx.fillText(label, listX + 6, y);
      this._listRects.push({
        id: name,
        x: listX,
        y: y - 12,
        w: LIST_W,
        h: rowH,
      });
    }
    if (!this._list.length) {
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "11px sans-serif";
      ctx.fillText("none yet", listX + 6, listY + 36);
    }

    // --- image / boxes ---
    this._imgRect = { x: imgX, y: listY, w: imgW, h: imgH };
    const drawn = letterbox(ctx, this._snap, imgX, listY, imgW, imgH);
    if (!drawn) {
      ctx.fillStyle = "#0a0c10";
      ctx.fillRect(imgX, listY, imgW, imgH);
      ctx.fillStyle = "#9aa0a6";
      ctx.font = "12px sans-serif";
      ctx.fillText(
        "Freeze new  OR  click a name to edit",
        imgX + 10,
        listY + 24
      );
    } else {
      this._imgRect = drawn;
      if (this._cropPreviewOnly) {
        ctx.fillStyle = "rgba(255,171,64,0.85)";
        ctx.font = "11px sans-serif";
        ctx.fillText("crop template (preview)", drawn.x + 6, drawn.y + 14);
      }
      const targets = this._cropPreviewOnly ? [] : this._targets;
      for (let i = 0; i < targets.length; i++) {
        const d = this._frameToDisplay(targets[i]);
        const sel = i === this._selected;
        ctx.strokeStyle = sel ? "#7c9cff" : "#3dd68c";
        ctx.lineWidth = sel ? 3 : 2;
        ctx.fillStyle = sel
          ? "rgba(124,156,255,0.2)"
          : "rgba(61,214,140,0.15)";
        ctx.strokeRect(drawn.x + d.x, drawn.y + d.y, d.w, d.h);
        ctx.fillRect(drawn.x + d.x, drawn.y + d.y, d.w, d.h);
        ctx.fillStyle = sel ? "#7c9cff" : "#3dd68c";
        ctx.font = "10px sans-serif";
        ctx.fillText(String(i + 1), drawn.x + d.x + 3, drawn.y + d.y + 11);
      }
      if (this._draft && this._draft.w > 0) {
        ctx.strokeStyle = "#ffc450";
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
      String(this.properties.hint || "").slice(0, 90),
      pad,
      Math.min(top + listH - 6, (this.widgets_start_y || this.size[1]) - 8)
    );
  };

  UiAnchors.prototype.onMouseDown = function (e, local) {
    // Click list item → edit that anchor
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
    if (this._cropPreviewOnly) return false;
    if (
      !this._snap ||
      local[1] < ir.y ||
      local[0] < ir.x ||
      local[0] > ir.x + ir.w ||
      local[1] > ir.y + ir.h
    ) {
      return false;
    }
    const lx = local[0] - ir.x;
    const ly = local[1] - ir.y;

    // Click existing box → select (and optionally start move)
    for (let i = this._targets.length - 1; i >= 0; i--) {
      const d = this._frameToDisplay(this._targets[i]);
      if (
        lx >= d.x &&
        lx <= d.x + d.w &&
        ly >= d.y &&
        ly <= d.y + d.h
      ) {
        this._selected = i;
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

    // Empty area → new box
    this._drag = { mode: "draw", x0: lx, y0: ly };
    this._draft = { x: lx, y: ly, w: 0, h: 0 };
    this._selected = -1;
    if (this.captureInput) this.captureInput(true);
    return true;
  };

  UiAnchors.prototype.onMouseMove = function (e, local) {
    if (!this._drag) return false;
    const ir = this._imgRect;
    const lx = Math.max(0, Math.min(ir.w, local[0] - ir.x));
    const ly = Math.max(0, Math.min(ir.h, local[1] - ir.y));
    if (this._drag.mode === "draw") {
      this._draft = {
        x: Math.min(this._drag.x0, lx),
        y: Math.min(this._drag.y0, ly),
        w: Math.abs(lx - this._drag.x0),
        h: Math.abs(ly - this._drag.y0),
      };
    } else if (this._drag.mode === "move") {
      const i = this._drag.index;
      const d = this._frameToDisplay(this._targets[i]);
      const nx = Math.max(0, Math.min(ir.w - d.w, lx - this._drag.ox));
      const ny = Math.max(0, Math.min(ir.h - d.h, ly - this._drag.oy));
      this._targets[i] = this._displayToFrame({
        x: nx,
        y: ny,
        w: d.w,
        h: d.h,
      });
    }
    this.setDirtyCanvas(true, false);
    return true;
  };

  UiAnchors.prototype.onMouseUp = function () {
    if (this._drag && this._drag.mode === "draw") this._finalizeDraft();
    this._drag = null;
    if (this.captureInput) this.captureInput(false);
    this.setDirtyCanvas(true, false);
    return false;
  };

  LiteGraph.registerNodeType("ui/anchors", UiAnchors);

  // ---------- ui/macros ----------
  function UiMacros() {
    this.title = "ui.macros";
    this.size = [300, 140];
    this.properties = { name: "demo", status: "idle" };
    const node = this;
    this.addWidget("text", "name", this.properties.name, function (v) {
      node.properties.name = v;
    });
    this.addWidget("button", "Rec", "", function () {
      node._rec(true);
    });
    this.addWidget("button", "Stop Rec", "", function () {
      node._rec(false);
    });
    styleUi(this, "#402848");
  }
  UiMacros.prototype.onDrawForeground = function (ctx) {
    if (this.flags.collapsed) return;
    ctx.fillStyle = "#9aa0a6";
    ctx.font = "11px sans-serif";
    ctx.fillText(
      "Prefer ds/macro_block on the graph for normalize.",
      8,
      this.size[1] - 28
    );
    ctx.fillText("status: " + (this.properties.status || "idle"), 8, this.size[1] - 12);
  };
  UiMacros.prototype._rec = async function (start) {
    const name = String(this.properties.name || "demo").trim() || "demo";
    this.properties.name = name;
    try {
      if (start) {
        const res = await fetch("/api/macros/record/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, ensure_passthrough: true }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "rec start failed");
        this.properties.status = "recording " + name;
      } else {
        const res = await fetch("/api/macros/record/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            normalize: true,
            gap_ms: 700,
            press_ms: 100,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "rec stop failed");
        this.properties.status =
          "saved " + name + " (" + (data.count || 0) + " ev, normalized)";
        if (global.Web2PS5Studio && global.Web2PS5Studio.pushTelemetry) {
          global.Web2PS5Studio.pushTelemetry({
            type: "macro_recorded",
            name,
            count: data.count,
            normalized: data.normalized,
          });
        }
      }
    } catch (err) {
      this.properties.status = String(err);
    }
    this.setDirtyCanvas(true, false);
  };
  LiteGraph.registerNodeType("ui/macros", UiMacros);

  // ---------- ui/telemetry ----------
  function UiTelemetry() {
    this.title = "ui.telemetry";
    this.size = [420, 280];
    this.properties = {};
    styleUi(this, "#2a2a3a");
  }
  UiTelemetry.prototype.onDrawForeground = function (ctx) {
    if (this.flags.collapsed) return;
    const pad = 8;
    const top = 8;
    const studio = global.Web2PS5Studio;
    const lines = (studio && studio.getTelemetryLines && studio.getTelemetryLines()) || [];
    const health = (studio && studio.getLastHealth && studio.getLastHealth()) || null;

    ctx.fillStyle = "#0a0c10";
    ctx.fillRect(pad, top, this.size[0] - pad * 2, this.size[1] - top - pad);
    ctx.fillStyle = "#7c9cff";
    ctx.font = "11px Consolas, monospace";
    let y = top + 14;
    const maxW = this.size[0] - pad * 2 - 8;
    const show = lines.slice(-Math.floor((this.size[1] - 80) / 14));
    for (let i = 0; i < show.length; i++) {
      const t = String(show[i]);
      ctx.fillText(t.length > 80 ? t.slice(0, 77) + "…" : t, pad + 4, y, maxW);
      y += 14;
      if (y > this.size[1] - 60) break;
    }
    if (health) {
      ctx.fillStyle = "#9aa0a6";
      ctx.fillText("— health —", pad + 4, this.size[1] - 40);
      const brief =
        "bridge=" +
        ((health.bridge && health.bridge.connected) || health.status) +
        "  age_ms=" +
        (((health.bridge || {}).video || {}).age_ms != null
          ? (health.bridge || {}).video.age_ms
          : "?");
      ctx.fillStyle = "#3dd68c";
      ctx.fillText(brief, pad + 4, this.size[1] - 22, maxW);
    }
  };
  LiteGraph.registerNodeType("ui/telemetry", UiTelemetry);

  // ---------- ui/note (display-only annotation; not executed by GraphRunner) ----------
  function wrapNoteLines(ctx, text, maxWidth) {
    const raw = String(text || "").replace(/\r/g, "").split("\n");
    const out = [];
    for (let r = 0; r < raw.length; r++) {
      const line = raw[r];
      if (!line) {
        out.push("");
        continue;
      }
      const words = line.split(/\s+/);
      let cur = "";
      for (let i = 0; i < words.length; i++) {
        const trial = cur ? cur + " " + words[i] : words[i];
        if (ctx.measureText(trial).width <= maxWidth || !cur) {
          cur = trial;
        } else {
          out.push(cur);
          cur = words[i];
        }
      }
      if (cur) out.push(cur);
    }
    return out;
  }

  function UiNote() {
    this.title = "ui.note";
    this.size = [320, 140];
    this.properties = {
      heading: "Note",
      text: "Describe this section…",
    };
    const node = this;
    this.addWidget("text", "heading", this.properties.heading, function (v) {
      node.properties.heading = v;
    });
    this.addWidget("text", "text", this.properties.text, function (v) {
      node.properties.text = v;
    });
    styleUi(this, "#3a3420");
    this.boxcolor = "#ffc450";
  }
  UiNote.prototype.onDrawForeground = function (ctx) {
    if (this.flags.collapsed) return;
    const pad = 10;
    const top = 28;
    const w = Math.max(40, this.size[0] - pad * 2);
    const h = Math.max(40, this.size[1] - top - pad);
    ctx.fillStyle = "#12160c";
    ctx.fillRect(pad, top, w, h);
    ctx.strokeStyle = "#5a5030";
    ctx.strokeRect(pad, top, w, h);

    const heading = String(this.properties.heading || "Note");
    ctx.fillStyle = "#ffc450";
    ctx.font = "bold 12px sans-serif";
    ctx.fillText(heading.slice(0, 48), pad + 8, top + 16);

    ctx.fillStyle = "#d8dcc8";
    ctx.font = "11px sans-serif";
    const lines = wrapNoteLines(ctx, this.properties.text, w - 16);
    let y = top + 34;
    const maxY = top + h - 8;
    for (let i = 0; i < lines.length; i++) {
      if (y > maxY) {
        ctx.fillStyle = "#9aa0a6";
        ctx.fillText("…", pad + 8, maxY);
        break;
      }
      ctx.fillText(lines[i], pad + 8, y);
      y += 14;
    }
  };
  UiNote.title = "ui.note";
  UiNote.desc = "Display-only sticky note. Not executed by the runner.";
  LiteGraph.registerNodeType("ui/note", UiNote);

  // ---------- topbar: spawn / focus ----------
  const TYPE_MAP = {
    preview: "ui/preview",
    anchors: "ui/anchors",
    macros: "ui/macros",
    telemetry: "ui/telemetry",
    note: "ui/note",
  };

  function spawnOrFocus(kind) {
    const type = TYPE_MAP[kind];
    const studio = global.Web2PS5Studio;
    if (!type || !studio || !studio.graph || !studio.canvas) return null;
    const graph = studio.graph;
    const canvas = studio.canvas;
    let node = graph.findNodesByType(type)[0];
    if (!node) {
      node = LiteGraph.createNode(type);
      if (!node) return null;
      // Place near view center
      const area = canvas.visible_area || [0, 0, 800, 600];
      node.pos = [
        area[0] + Math.max(40, area[2] * 0.2),
        area[1] + Math.max(40, area[3] * 0.2),
      ];
      graph.add(node);
    }
    canvas.selectNode(node);
    if (canvas.centerOnNode) canvas.centerOnNode(node);
    else if (canvas.ds) {
      canvas.ds.offset[0] =
        -node.pos[0] + canvas.canvas.width / (2 * canvas.ds.scale) - node.size[0] / 2;
      canvas.ds.offset[1] =
        -node.pos[1] + canvas.canvas.height / (2 * canvas.ds.scale) - node.size[1] / 2;
    }
    graph.setDirtyCanvas(true, true);
    document.querySelectorAll(".panel-tog").forEach((btn) => {
      const on = btn.getAttribute("data-panel") === kind;
      btn.classList.toggle("on", on && !!graph.findNodesByType(type).length);
    });
    return node;
  }

  function syncToggles() {
    const studio = global.Web2PS5Studio;
    if (!studio || !studio.graph) return;
    Object.keys(TYPE_MAP).forEach((kind) => {
      const type = TYPE_MAP[kind];
      const has = studio.graph.findNodesByType(type).length > 0;
      document
        .querySelectorAll('.panel-tog[data-panel="' + kind + '"]')
        .forEach((btn) => btn.classList.toggle("on", has));
    });
  }

  function bindTopbar() {
    document.querySelectorAll(".panel-tog[data-panel]").forEach((btn) => {
      btn.addEventListener("click", () => {
        spawnOrFocus(btn.getAttribute("data-panel"));
      });
    });
    // Reflect existing graph nodes after load
    setTimeout(syncToggles, 0);
    setInterval(syncToggles, 2000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindTopbar);
  } else {
    bindTopbar();
  }

  global.Web2PS5UI = {
    spawn: spawnOrFocus,
    preview: previewState,
    detections: detectionState,
    detectionPoll,
    syncToggles,
    setDetections(payload) {
      if (!payload) return;
      // Normalize OCR run telemetry into the same overlay shape as detect polls
      if (
        (payload.type === "ocr_check" || payload.type === "ocr_wait_progress") &&
        !(payload.boxes && payload.boxes.length) &&
        payload.roi
      ) {
        const r = payload.roi;
        payload = Object.assign({}, payload, {
          boxes: [
            {
              index: 0,
              x: r[0] | 0,
              y: r[1] | 0,
              w: r[2] | 0,
              h: r[3] | 0,
              hit: !!payload.matched,
              found: true,
              kind: "ocr",
              label: String(payload.text || "").slice(0, 48),
              expect: payload.expect,
              score: payload.matched ? 1 : 0,
            },
          ],
        });
      }
      if (payload.ocr_id && !payload.anchor_id) {
        payload = Object.assign({}, payload, {
          anchor_id: "ocr:" + payload.ocr_id,
        });
      }
      detectionState.setFromDetect(payload);
    },
    onAnchorsChanged() {
      const studio = global.Web2PS5Studio;
      if (!studio || !studio.graph) return;
      (studio.graph.findNodesByType("ui/anchors") || []).forEach((n) => {
        if (n._refreshList) n._refreshList();
      });
      ["vis/wait_anchor", "vis/check_state"].forEach((t) => {
        (studio.graph.findNodesByType(t) || []).forEach((n) => {
          if (n._refreshAnchorList) n._refreshAnchorList();
        });
      });
      detectionPoll.sync();
    },
  };
})(window);
