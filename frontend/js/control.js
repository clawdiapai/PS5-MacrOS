/**
 * Front-facing console — preview + Wake / Rest (extensible action grid).
 */
(function () {
  const preview = document.getElementById("preview");
  const previewEmpty = document.getElementById("preview-empty");
  const badgeBridge = document.getElementById("badge-bridge");
  const badgeRun = document.getElementById("badge-run");
  const statusLine = document.getElementById("status-line");
  const btnWake = document.getElementById("btn-wake");
  const btnOpenFortnite = document.getElementById("btn-open-fortnite");
  const btnRest = document.getElementById("btn-rest");
  const btnStop = document.getElementById("btn-stop");
  const actionBtns = [btnWake, btnOpenFortnite, btnRest].filter(Boolean);

  let busy = false;
  let lastStatus = null;

  function setStatus(text, kind) {
    statusLine.textContent = text;
    statusLine.classList.remove("busy", "ok", "err");
    if (kind) statusLine.classList.add(kind);
  }

  function setBusy(on) {
    busy = !!on;
    actionBtns.forEach((b) => {
      if (b) b.disabled = busy;
    });
  }

  function refreshPreview() {
    if (!preview) return;
    preview.onload = function () {
      previewEmpty.classList.add("hidden");
    };
    preview.onerror = function () {
      previewEmpty.classList.remove("hidden");
    };
    preview.src = "/api/preview/mjpeg?t=" + Date.now();
  }

  function paintStatus(data) {
    lastStatus = data;
    const b = (data && data.bridge) || {};
    const r = (data && data.run) || {};

    if (b.connecting) {
      badgeBridge.textContent = "connecting…";
      badgeBridge.className = "pill warn";
    } else if (b.connected) {
      badgeBridge.textContent = "connected";
      badgeBridge.className = "pill ok";
      previewEmpty.classList.add("hidden");
    } else {
      badgeBridge.textContent = b.connect_error
        ? "offline"
        : "disconnected";
      badgeBridge.className = "pill err";
      if (!preview.complete || !preview.naturalWidth) {
        previewEmpty.classList.remove("hidden");
      }
    }

    const rs = r.status || "idle";
    badgeRun.textContent = "run: " + rs + (r.graph ? " (" + r.graph + ")" : "");
    badgeRun.className =
      "pill" +
      (rs === "running" || rs === "stopping"
        ? " warn"
        : rs === "error"
          ? " err"
          : "");

    const running = rs === "running" || rs === "stopping";
    btnStop.hidden = !running;
    if (!busy) {
      actionBtns.forEach((b) => {
        if (b && b !== btnWake) b.disabled = running;
      });
    }

    if (r.error && rs === "error") {
      setStatus("Run error: " + r.error, "err");
    }
  }

  async function fetchStatus() {
    try {
      const res = await fetch("/api/console/status");
      const data = await res.json();
      if (res.ok) paintStatus(data);
    } catch (_) {
      /* ignore poll errors */
    }
  }

  async function postJson(url) {
    const res = await fetch(url, { method: "POST" });
    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      data = {};
    }
    if (!res.ok) {
      const detail = data.detail || data.error || res.statusText || "request failed";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  async function onWake() {
    setBusy(true);
    setStatus("Waking / reconnecting Remote Play…", "busy");
    try {
      await postJson("/api/console/wake");
      setStatus("Wake requested — waiting for video…", "ok");
      refreshPreview();
      await fetchStatus();
    } catch (err) {
      setStatus(String(err.message || err), "err");
    } finally {
      setBusy(false);
      await fetchStatus();
    }
  }

  async function runConsoleAction(opts) {
    const {
      confirmMsg,
      startMsg,
      url,
      label,
      timeoutMs,
    } = opts;
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(true);
    setStatus(startMsg, "busy");
    try {
      const data = await postJson(url);
      setStatus(
        label +
          " running" +
          (data.run && data.run.run_id ? " (" + data.run.run_id + ")" : "") +
          "…",
        "busy"
      );
      await fetchStatus();
      const started = Date.now();
      const limit = timeoutMs != null ? timeoutMs : 180000;
      while (Date.now() - started < limit) {
        await new Promise((r) => setTimeout(r, 800));
        await fetchStatus();
        const rs =
          (lastStatus && lastStatus.run && lastStatus.run.status) || "idle";
        if (rs === "idle") {
          setStatus(label + " finished.", "ok");
          break;
        }
        if (rs === "error") {
          setStatus(
            label +
              " error: " +
              ((lastStatus.run && lastStatus.run.error) || "unknown"),
            "err"
          );
          break;
        }
      }
    } catch (err) {
      setStatus(String(err.message || err), "err");
    } finally {
      setBusy(false);
      await fetchStatus();
    }
  }

  async function onRest() {
    await runConsoleAction({
      confirmMsg:
        "Send the PS5 to Rest Mode?\n\nThis runs REST-PS5 (Control Center → power → Rest).",
      startMsg: "Starting REST-PS5…",
      url: "/api/console/rest",
      label: "REST-PS5",
    });
  }

  async function onOpenFortnite() {
    await runConsoleAction({
      confirmMsg:
        "Open Fortnite?\n\nLong-press PS, seek the row, OCR for Fortnite, then CROSS.",
      startMsg: "Starting OPEN FORTNITE…",
      url: "/api/console/open-fortnite",
      label: "Open Fortnite",
      timeoutMs: 300000,
    });
  }

  async function onStop() {
    setBusy(true);
    setStatus("Stopping run…", "busy");
    try {
      await postJson("/api/console/stop");
      setStatus("Run stopped.", "ok");
    } catch (err) {
      setStatus(String(err.message || err), "err");
    } finally {
      setBusy(false);
      await fetchStatus();
    }
  }

  btnWake.addEventListener("click", () => {
    onWake().catch(() => {});
  });
  if (btnOpenFortnite) {
    btnOpenFortnite.addEventListener("click", () => {
      onOpenFortnite().catch(() => {});
    });
  }
  btnRest.addEventListener("click", () => {
    onRest().catch(() => {});
  });
  btnStop.addEventListener("click", () => {
    onStop().catch(() => {});
  });

  // First-run wizard
  fetch("/api/setup/status")
    .then((r) => r.json())
    .then((data) => {
      if (data.needs_wizard) location.replace("/setup");
    })
    .catch(() => {});

  refreshPreview();
  fetchStatus();
  setInterval(fetchStatus, 2500);
})();
