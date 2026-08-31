(function () {
  const $ = (id) => document.getElementById(id);
  const panels = {
    deps: $("panel-deps"),
    psn: $("panel-psn"),
    device: $("panel-device"),
    save: $("panel-save"),
  };

  let lastDevices = [];

  function showStep(step) {
    Object.entries(panels).forEach(([k, el]) => {
      if (!el) return;
      el.classList.toggle("hidden", k !== step && step !== "done");
    });
    if (step === "done") {
      Object.values(panels).forEach((el) => el && el.classList.remove("hidden"));
    }
    document.querySelectorAll("#step-rail li").forEach((li) => {
      const s = li.getAttribute("data-step");
      li.classList.toggle("active", s === step);
    });
  }

  function markDone(upto) {
    const order = ["deps", "psn", "device", "save"];
    const idx = order.indexOf(upto);
    document.querySelectorAll("#step-rail li").forEach((li) => {
      const s = li.getAttribute("data-step");
      const i = order.indexOf(s);
      li.classList.toggle("done", i >= 0 && i < idx);
    });
  }

  function fillProfileSelects(profiles, controlVal, spectatorVal) {
    const ids = ["role-control", "role-spectator", "ps5-user", "ps5-spectator-user"];
    ids.forEach((id) => {
      const el = $(id);
      if (!el) return;
      const keepEmpty = id.includes("spectator");
      const prev = el.value;
      el.innerHTML = keepEmpty ? '<option value="">— none —</option>' : "";
      (profiles || []).forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.name;
        opt.textContent = p.name;
        el.appendChild(opt);
      });
      if (id === "role-control" || id === "ps5-user") {
        el.value = controlVal || prev || (profiles[0] && profiles[0].name) || "";
      } else {
        el.value = spectatorVal || prev || "";
      }
    });
  }

  function fillDeviceSelect(devices) {
    lastDevices = devices || [];
    const sel = $("ps5-device-select");
    sel.innerHTML = '<option value="">— scan or pick manual IP below —</option>';
    lastDevices.forEach((d, i) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      const name = d.name || d.type || "PlayStation";
      const on = d.is_on ? "ON" : "standby/?";
      opt.textContent = `${name} — ${d.host} (${on})`;
      sel.appendChild(opt);
    });
    if (lastDevices.length === 1) {
      sel.value = "0";
      applySelectedDevice();
    }
  }

  function applySelectedDevice() {
    const sel = $("ps5-device-select");
    const idx = sel.value;
    if (idx === "" || !lastDevices[idx]) return;
    const d = lastDevices[idx];
    $("ps5-host").value = d.host || "";
  }

  function syncRolesToDevicePanel() {
    const control = $("role-control").value;
    const spectator = $("role-spectator").value;
    if ($("ps5-user") && control) $("ps5-user").value = control;
    if ($("ps5-spectator-user")) $("ps5-spectator-user").value = spectator || "";
  }

  function updateSaveSummary() {
    const host = $("ps5-host").value.trim();
    const control = $("role-control").value || $("ps5-user").value;
    const spectator = $("role-spectator").value || $("ps5-spectator-user").value;
    $("save-summary").textContent =
      `Host: ${host || "?"} · Control: ${control || "?"} · Spectator: ${spectator || "none"}`;
  }

  async function refresh() {
    const res = await fetch("/api/setup/status");
    const data = await res.json();
    $("deps-msg").textContent = data.deps_message || "";

    const list = $("profile-list");
    list.innerHTML = "";
    (data.profiles || []).forEach((p) => {
      const li = document.createElement("li");
      li.textContent = p.name;
      list.appendChild(li);
    });

    fillProfileSelects(data.profiles || [], data.ps5_user, data.ps5_spectator_user);
    if (data.ps5_host) $("ps5-host").value = data.ps5_host;

    // Already onboarded → go straight to studio (don't trap on /setup)
    if (data.complete || data.skipped) {
      location.replace("/");
      return data;
    }

    const next = data.next || "deps";
    markDone(next);
    showStep(next === "done" ? "save" : next);
    updateSaveSummary();
    return data;
  }

  $("btn-install").onclick = async () => {
    $("deps-log").textContent = "Installing… (may take a minute)";
    const res = await fetch("/api/setup/install-deps", { method: "POST" });
    const data = await res.json();
    $("deps-log").textContent = (data.log_tail || "") + "\n\n" + (data.message || "");
    await refresh();
  };

  $("btn-oauth-url").onclick = async () => {
    const res = await fetch("/api/setup/oauth/url");
    const data = await res.json();
    if (!res.ok) {
      $("psn-status").textContent = data.detail || "failed";
      return;
    }
    $("oauth-link").href = data.url;
    $("oauth-link").textContent = "Open Sony login";
    window.open(data.url, "_blank", "noopener");
  };

  $("btn-oauth-save").onclick = async () => {
    const redirect_url = $("redirect-url").value.trim();
    $("psn-status").textContent = "Saving…";
    const res = await fetch("/api/setup/oauth/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ redirect_url }),
    });
    const data = await res.json();
    $("psn-status").textContent = res.ok
      ? `Added profile: ${data.user}. Add another for spectator if you want.`
      : data.detail || "failed";
    if (res.ok) $("redirect-url").value = "";
    await refresh();
  };

  $("btn-psn-next").onclick = () => {
    const control = $("role-control").value;
    if (!control) {
      $("psn-status").textContent = "Select a Control account (add a profile first).";
      return;
    }
    if ($("role-spectator").value && $("role-spectator").value === control) {
      $("psn-status").textContent = "Spectator must be a different account.";
      return;
    }
    syncRolesToDevicePanel();
    markDone("device");
    showStep("device");
  };

  $("ps5-device-select").onchange = applySelectedDevice;

  $("btn-discover").onclick = async () => {
    $("probe-out").textContent = "Scanning LAN (≈3s)…";
    const res = await fetch("/api/setup/discover", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      $("probe-out").textContent = data.detail || "scan failed";
      return;
    }
    fillDeviceSelect(data.devices || []);
    $("probe-out").textContent =
      (data.devices || []).length
        ? `Found ${data.devices.length} device(s). Pick one from the dropdown.`
        : data.hint || "No devices found. Enter IP manually and Probe.";
  };

  $("btn-probe").onclick = async () => {
    const host = $("ps5-host").value.trim();
    $("probe-out").textContent = "Probing…";
    const res = await fetch("/api/setup/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host }),
    });
    const data = await res.json();
    $("probe-out").textContent = JSON.stringify(data, null, 2);
    if (res.ok && data.ok && host) {
      // ensure dropdown has this host
      const exists = lastDevices.some((d) => d.host === host);
      if (!exists) {
        fillDeviceSelect([
          ...lastDevices,
          {
            host,
            name: (data.status && data.status["host-name"]) || "Probed",
            type: data.type,
            is_on: data.is_on,
            status: data.status || {},
          },
        ]);
        $("ps5-device-select").value = String(lastDevices.length - 1);
      }
    }
  };

  async function registerUser(user, pin, statusEl) {
    statusEl.textContent = "Registering…";
    const res = await fetch("/api/setup/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        host: $("ps5-host").value.trim(),
        user,
        pin,
      }),
    });
    const data = await res.json();
    statusEl.textContent = res.ok
      ? `Registered ${user}. Device users: ${(data.registered_users || []).join(", ")}`
      : data.detail || "failed";
    return res.ok;
  }

  $("btn-register").onclick = async () => {
    const user = $("ps5-user").value;
    const pin = $("ps5-pin").value.trim();
    if (!user || !pin) {
      $("reg-status").textContent = "Need Control user + PIN";
      return;
    }
    await registerUser(user, pin, $("reg-status"));
  };

  $("btn-register-spectator").onclick = async () => {
    const user = $("ps5-spectator-user").value;
    const pin = $("ps5-spectator-pin").value.trim();
    if (!user) {
      $("reg-spec-status").textContent = "Pick a spectator profile (or skip).";
      return;
    }
    if (!pin) {
      $("reg-spec-status").textContent = "Need a fresh PIN from the PS5 link screen.";
      return;
    }
    await registerUser(user, pin, $("reg-spec-status"));
  };

  $("btn-device-next").onclick = () => {
    if (!$("ps5-host").value.trim()) {
      $("reg-status").textContent = "Set a console IP (scan or type it).";
      return;
    }
    // keep role selects in sync from device panel
    if ($("ps5-user").value) $("role-control").value = $("ps5-user").value;
    $("role-spectator").value = $("ps5-spectator-user").value || "";
    updateSaveSummary();
    markDone("save");
    showStep("save");
  };

  $("btn-save").onclick = async () => {
    $("save-status").textContent = "Saving…";
    const control = $("role-control").value || $("ps5-user").value;
    const spectator = $("role-spectator").value || $("ps5-spectator-user").value || "";
    const res = await fetch("/api/setup/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        host: $("ps5-host").value.trim(),
        user: control,
        spectator_user: spectator,
        bridge: "pyremoteplay",
        auto_connect: true,
        apply_now: true,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("save-status").textContent = data.detail || "save failed";
      return;
    }
    $("save-status").textContent = data.connect_error
      ? `Saved. Connect warning: ${data.connect_error}`
      : "Saved. Control session connected (spectator is stored, not used for input).";
    $("enter-studio").classList.remove("hidden");
  };

  $("btn-skip").onclick = async () => {
    await fetch("/api/setup/skip-fake", { method: "POST" });
    location.href = "/";
  };

  ["role-control", "role-spectator", "ps5-user", "ps5-spectator-user", "ps5-host"].forEach(
    (id) => {
      const el = $(id);
      if (el) el.addEventListener("change", updateSaveSummary);
    }
  );

  refresh().catch((err) => {
    $("deps-msg").textContent = String(err);
  });
})();
