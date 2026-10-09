const $ = (id) => document.getElementById(id);

let currentView = "dashboard";
let promptSeeded = false;

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function money(value, currency) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  const prefix = num > 0 ? "+" : "";
  return prefix + num.toFixed(2) + (currency ? " " + currency : "");
}

function setConn(connected) {
  const wrap = $("conn-wrap");
  wrap.className = "conn-wrap " + (connected ? "online" : "offline");
  $("conn-text").textContent = connected ? "CONNECTED" : "NOT CONNECTED";
}

function tickNyClock() {
  const now = new Date();
  const text = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }).format(now);
  $("ny-clock").textContent = text.replace(/^0/, "");
}

function showView(name) {
  currentView = name;
  $("view-dashboard").classList.toggle("hidden", name !== "dashboard");
  $("view-chat").classList.toggle("hidden", name !== "chat");
  $("view-settings").classList.toggle("hidden", name !== "settings");
  ["tab-dashboard", "tab-chat", "tab-settings"].forEach((id) => {
    $(id).classList.remove("active", "gold");
    $(id).classList.add("white");
    $(id).setAttribute("aria-selected", "false");
  });
  const active = name === "dashboard" ? "tab-dashboard" : name === "chat" ? "tab-chat" : "tab-settings";
  $(active).classList.add("active");
  $(active).classList.remove("white");
  $(active).classList.add("gold");
  $(active).setAttribute("aria-selected", "true");
  if (name === "chat") {
    $("page-title").textContent = "IFVG_AI_CHATROOM";
  } else if (name === "settings") {
    $("page-title").textContent = "SETTINGS AND PARAMETERS";
  } else {
    $("page-title").textContent = "IFVG_AI_EA: METATRADER 5";
  }
}

function renderLive(live) {
  live = live || {};
  setConn(!!live.connected);
  const currency = live.currency || "";
  const pnl = live.profit;
  const pnlEl = $("live-pnl");
  pnlEl.textContent = money(pnl, currency);
  pnlEl.parentElement.className = "stat " + (Number(pnl) >= 0 ? "up" : "down");
  $("live-price").textContent = live.price != null ? Number(live.price).toFixed(5) : "--";
  $("live-session").textContent = (live.session && live.session.label) || "--";
  $("live-won").textContent = live.trades_won ?? 0;
  $("live-lost").textContent = live.trades_lost ?? 0;
  $("live-equity").textContent = money(live.equity, currency);
  const bits = [
    live.symbol || "",
    live.timeframe || "",
    live.open_positions != null ? live.open_positions + " open" : "",
    live.age_sec != null ? "hb " + live.age_sec + "s" : "",
  ].filter(Boolean);
  $("live-meta").textContent = bits.join(" · ") || "Waiting for EA heartbeat from MetaTrader 5.";
}

function renderChat(history, model) {
  $("chat-model").textContent = "Model: " + (model || "--");
  $("model-line").textContent = model ? "Ollama model: " + model : "";
  $("chat-log").innerHTML = (history || []).map((item) => `
    <div class="chat-line ${item.role}">
      <strong>${item.role === "user" ? "YOU" : "IFVG AI"}</strong>
      <p>${escapeHtml(item.content || "")}</p>
    </div>
  `).join("") || '<p class="muted">No chat yet. Ask about the EA, a document, EURUSD, or a live signal.</p>';
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

function renderState(state) {
  const settings = state.settings || {};
  const health = state.health || {};
  const last = (state.decisions || [])[0];
  const model = (state.models && state.models.text) || settings.text_model || "";
  renderLive(state.live || health.live || {});
  renderChat(state.chat || [], model);

  $("min-conf").value = settings.min_accept_confidence || 0.62;
  $("min-conf-val").textContent = Number($("min-conf").value).toFixed(2);
  $("symbol").value = settings.default_symbol || "";
  $("timeframe").value = settings.default_timeframe || "";
  $("lots").value = settings.default_lots || "0.10";
  $("direction").value = settings.default_direction || "buy";
  $("lan-url").textContent = "Phone URL: " + (health.lan_url || window.location.origin);

  if (!promptSeeded && state.prompts) {
    $("ea-prompt").value = state.prompts.ea_prompt || "";
    $("ea-instructions").value = state.prompts.ea_instructions || "";
    $("chat-prompt").value = state.prompts.chat_prompt || "";
    $("chat-instructions").value = state.prompts.chat_instructions || "";
    promptSeeded = true;
  }

  if (last) {
    $("last-action").textContent = last.action;
    $("last-action").style.color = last.action === "ACCEPT" ? "#2fe37a" : "#ff5a68";
    $("last-reason").textContent = last.reason || last.payload?.reason || "";
    $("last-conf").textContent = Number(last.confidence).toFixed(2);
    $("last-symbol").textContent = `${last.symbol || ""} ${last.timeframe || ""}`;
    $("last-source").textContent = last.payload?.source || "--";
  }

  $("memories").innerHTML = (state.memories || []).map((m) => `
    <div class="item" data-id="${m.id}">
      <strong>${escapeHtml(m.title)}</strong>
      <p class="muted">${escapeHtml(m.kind)} · used ${m.use_count} times</p>
      <p>${escapeHtml((m.content || "").slice(0, 220))}</p>
      <div class="item-actions">
        <button class="btn-3d gold" data-analyze="${m.id}" type="button">ANALYZE / MEMORIZE</button>
        <button class="btn-3d red" data-forget="${m.id}" type="button" aria-label="Delete ${escapeHtml(m.title)}">&#128465;</button>
      </div>
    </div>
  `).join("") || '<p class="muted">Library empty.</p>';

  $("decisions").innerHTML = (state.decisions || []).map((d) => `
    <div class="item ${d.action === "ACCEPT" ? "accept" : "deny"}">
      <strong>${d.action}</strong> ${d.symbol} ${d.timeframe} · ${Number(d.confidence).toFixed(2)}
      <p>${escapeHtml(d.reason || "")}</p>
    </div>
  `).join("") || '<p class="muted">No trade history yet.</p>';
}

async function refresh() {
  const state = await api("/api/state");
  renderState(state);
}

function setBusy(ids, busy) {
  ids.forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.disabled = busy;
    el.setAttribute("aria-busy", busy ? "true" : "false");
  });
}

async function sendCommand(action, extra) {
  const body = Object.assign({ action }, extra || {});
  setBusy(["btn-ping", "btn-open", "btn-close", "btn-close-all", "btn-pause", "btn-resume"], true);
  let result;
  try {
    result = await api("/api/commands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } finally {
    setBusy(["btn-ping", "btn-open", "btn-close", "btn-close-all", "btn-pause", "btn-resume"], false);
  }
  const connected = result.ea_connected;
  $("cmd-msg").textContent = connected
    ? "Queued " + action.replace("_", " ").toUpperCase() + " for the EA."
    : "Command queued. EA is NOT CONNECTED — attach the Expert Advisor in MT5.";
  if (action === "ping") {
    $("ping-msg").textContent = connected
      ? "Startup ping sent. Waiting for the EA heartbeat to answer CONNECTED."
      : "Ping queued, but the EA is NOT CONNECTED. Start Ollama, run the PowerShell launcher, and attach VisionBrainEA in MT5.";
  }
  refresh();
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

function uploadWithProgress(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onProgress(Math.round((ev.loaded / ev.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch (err) { resolve({ ok: true }); }
      } else reject(new Error(xhr.responseText || "Upload failed"));
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    const body = new FormData();
    body.append("file", file);
    xhr.send(body);
  });
}

async function savePrompt(target, value) {
  const payload = {};
  payload[target] = value;
  const result = await api("/api/prompts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const ping = $("ping-" + target.replace("_", "-"));
  if (ping) ping.textContent = "PING RECEIVED · " + target.replaceAll("_", " ").toUpperCase();
  return result;
}

async function uploadPromptFile(target, file) {
  const ping = $("ping-" + target.replace("_", "-"));
  const result = await uploadWithProgress("/api/prompts/upload?target=" + encodeURIComponent(target), file, () => {});
  if (ping) ping.textContent = "PING RECEIVED · uploaded " + file.name + " · " + (result.chars || 0) + " chars";
  promptSeeded = false;
  refresh();
}

$("tab-dashboard").onclick = () => showView("dashboard");
$("tab-chat").onclick = () => showView("chat");
$("tab-settings").onclick = () => showView("settings");

$("min-conf").addEventListener("input", () => {
  $("min-conf-val").textContent = Number($("min-conf").value).toFixed(2);
});

$("btn-ping").onclick = () => sendCommand("ping");
$("btn-open").onclick = () => sendCommand("open_trade", {
  direction: $("direction").value,
  lots: Number($("lots").value || 0.1),
  symbol: $("symbol").value,
});
$("btn-close").onclick = () => {
  if (window.confirm("Close the newest open trade?")) sendCommand("close_trade");
};
$("btn-close-all").onclick = () => {
  if (window.confirm("Close ALL open trades from this EA?")) sendCommand("close_all");
};
$("btn-pause").onclick = async () => { await sendCommand("pause"); };
$("btn-resume").onclick = async () => { await sendCommand("resume"); };
$("btn-rescan").onclick = async () => { await api("/api/control/rescan", { method: "POST" }); refresh(); };
$("btn-demo").onclick = async () => { await api("/api/demo/analyze", { method: "POST" }); refresh(); };
$("btn-save").onclick = async () => {
  await api("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      min_accept_confidence: Number($("min-conf").value),
      default_symbol: $("symbol").value,
      default_timeframe: $("timeframe").value,
      default_lots: Number($("lots").value || 0.1),
      default_direction: $("direction").value,
    }),
  });
  $("cmd-msg").textContent = "Settings saved.";
  refresh();
};
$("btn-note").onclick = async () => {
  await api("/api/memories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: $("note-title").value,
      content: $("note-body").value,
      tags: ["note", "manual"],
    }),
  });
  $("note-title").value = "";
  $("note-body").value = "";
  refresh();
};

$("file").onchange = async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  $("upload-preview").classList.remove("hidden");
  $("upload-name").textContent = file.name;
  $("upload-size").textContent = formatBytes(file.size);
  $("upload-status").textContent = "Uploading...";
  $("upload-bar").style.width = "0%";
  if (file.type.startsWith("image/")) {
    $("upload-thumb").src = URL.createObjectURL(file);
  } else {
    $("upload-thumb").removeAttribute("src");
    $("upload-thumb").alt = file.name;
  }
  try {
    await uploadWithProgress("/api/memories/upload", file, (pct) => {
      $("upload-bar").style.width = pct + "%";
      $("upload-status").textContent = "Uploading " + pct + "%";
    });
    $("upload-bar").style.width = "100%";
    $("upload-status").textContent = "PING RECEIVED · memorized " + file.name;
    refresh();
  } catch (err) {
    $("upload-status").textContent = "Upload failed";
  }
};

$("memories").addEventListener("click", async (ev) => {
  const analyze = ev.target.closest("[data-analyze]");
  const forget = ev.target.closest("[data-forget]");
  if (analyze) {
    analyze.disabled = true;
    try {
      const result = await api("/api/memories/" + analyze.getAttribute("data-analyze") + "/analyze", { method: "POST" });
      $("cmd-msg").textContent = (result.ping || "RECEIVED") + " · analyzed into memory";
      showView("chat");
      refresh();
    } finally {
      analyze.disabled = false;
    }
  }
  if (forget) {
    if (!window.confirm("Delete this document from the database library?")) return;
    await api("/api/memories/" + forget.getAttribute("data-forget") + "/forget", { method: "POST" });
    refresh();
  }
});

$("btn-chat").onclick = async () => {
  const message = $("chat-input").value.trim();
  if (!message) return;
  $("btn-chat").disabled = true;
  try {
    await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    $("chat-input").value = "";
    $("chat-msg").textContent = "PING RECEIVED";
    refresh();
  } finally {
    $("btn-chat").disabled = false;
  }
};

$("btn-signal").onclick = async () => {
  $("btn-signal").disabled = true;
  try {
    await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Give me a live EURUSD signal using current price, session, P&L, and FVG / Inverse FVG memory." }),
    });
    $("chat-msg").textContent = "PING RECEIVED · live EURUSD signal requested";
    refresh();
  } finally {
    $("btn-signal").disabled = false;
  }
};

$("btn-save-ea-prompt").onclick = () => savePrompt("ea_prompt", $("ea-prompt").value);
$("btn-save-ea-instructions").onclick = () => savePrompt("ea_instructions", $("ea-instructions").value);
$("btn-save-chat-prompt").onclick = () => savePrompt("chat_prompt", $("chat-prompt").value);
$("btn-save-chat-instructions").onclick = () => savePrompt("chat_instructions", $("chat-instructions").value);

$("file-ea-prompt").onchange = (ev) => ev.target.files[0] && uploadPromptFile("ea_prompt", ev.target.files[0]);
$("file-ea-instructions").onchange = (ev) => ev.target.files[0] && uploadPromptFile("ea_instructions", ev.target.files[0]);
$("file-chat-prompt").onchange = (ev) => ev.target.files[0] && uploadPromptFile("chat_prompt", ev.target.files[0]);
$("file-chat-instructions").onchange = (ev) => ev.target.files[0] && uploadPromptFile("chat_instructions", ev.target.files[0]);

try {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onmessage = () => refresh();
} catch (err) {
  console.warn(err);
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}

tickNyClock();
setInterval(tickNyClock, 1000);
showView("dashboard");
refresh();
setInterval(refresh, 4000);
