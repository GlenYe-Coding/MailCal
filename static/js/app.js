const state = {
  events: [],
  config: {},
  sync: { status: "idle", message: "" },
  view: "month",
  cursor: new Date(),
  selectedEvent: null,
  editingEventId: null,
  meta: { email_providers: {}, model_providers: {} },
  usage: null,
  syncCursor: null,
  syncProgress: null,
};

const TYPE_LABELS = {
  interview: "面试",
  assessment: "测评",
  event: "活动",
  meeting: "会议",
  deadline: "截止",
  other: "其他",
};

const TYPE_FALLBACK = {
  interview: "#4f46e5",
  assessment: "#e11d48",
  event: "#d97706",
  meeting: "#0d9488",
  deadline: "#dc2626",
  other: "#64748b",
};

const STATUS_LABELS = {
  upcoming: "待开始",
  ongoing: "进行中",
  overdue: "已逾期",
  done: "已完成",
  cancelled: "已取消",
};

const DEBUG = new URLSearchParams(window.location.search).has("debug");

function debugLog(...args) {
  if (DEBUG) console.debug("[debug]", ...args);
}

const els = {
  todayDate: document.getElementById("today-date"),
  todayCount: document.getElementById("today-count"),
  upcomingList: document.getElementById("upcoming-list"),
  syncStatus: document.getElementById("sync-status"),
  syncProgress: document.getElementById("sync-progress"),
  syncStage: document.getElementById("sync-stage"),
  syncProgressBar: document.getElementById("sync-progress-bar"),
  lastSync: document.getElementById("last-sync"),
  syncCursor: document.getElementById("sync-cursor"),
  usageSummary: document.getElementById("usage-summary"),
  calendarWeekdays: document.getElementById("calendar-weekdays"),
  calendarGrid: document.getElementById("calendar-grid"),
  calendarTitle: document.getElementById("calendar-title"),
  detailModal: document.getElementById("detail-modal"),
  detailTitle: document.getElementById("detail-title"),
  detailBody: document.getElementById("detail-body"),
  eventModal: document.getElementById("event-modal"),
  settingsModal: document.getElementById("settings-modal"),
  settingsForm: document.getElementById("settings-form"),
  adminModal: document.getElementById("admin-modal"),
  adminBtn: document.getElementById("admin-btn"),
  adminStats: document.getElementById("admin-stats"),
  adminLogs: document.getElementById("admin-logs"),
  adminLogLevel: document.getElementById("admin-log-level"),
  adminUsage: document.getElementById("admin-usage"),
  adminMail: document.getElementById("admin-mail"),
  adminLogRefresh: document.getElementById("admin-log-refresh"),
  adminResetUsage: document.getElementById("admin-reset-usage"),
  adminResetCursor: document.getElementById("admin-reset-cursor"),
  adminRetentionInfo: document.getElementById("admin-retention-info"),
  emailAuthHint: document.getElementById("email-auth-hint"),
  modelAuthHint: document.getElementById("model-auth-hint"),
  eventForm: document.getElementById("event-form"),
  eventModalTitle: document.querySelector("#event-modal h2"),
  editEventBtn: document.getElementById("edit-event-btn"),
  toggleStatusBtn: document.getElementById("toggle-status-btn"),
  resetUsageBtn: document.getElementById("reset-usage-btn"),
  resetCursorBtn: document.getElementById("reset-cursor-btn"),
  refreshModelsBtn: document.getElementById("refresh-models-btn"),
  eventTooltip: document.getElementById("event-tooltip"),
  toast: document.getElementById("toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function localDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function startOfDay(date) {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function parseEventDate(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function eventColor(event) {
  return event.color || TYPE_FALLBACK[event.type] || TYPE_FALLBACK.other;
}

function eventTypeLabel(event) {
  return TYPE_LABELS[event.type] || "其他";
}

function eventState(event) {
  if (event.current_status) return event.current_status;
  if (event.status === "done" || event.status === "cancelled") return event.status;
  const now = Date.now();
  const start = parseEventDate(event.start);
  if (!start) return "upcoming";
  const end = parseEventDate(event.end) || new Date(start.getTime() + 60 * 60 * 1000);
  if (now < start.getTime()) return "upcoming";
  if (now <= end.getTime()) return "ongoing";
  return "overdue";
}

function statusLabel(event) {
  return STATUS_LABELS[eventState(event)] || "待开始";
}

function formatTime(date) {
  if (!date) return "--:--";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function formatDateCN(date) {
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function monthTitle(date) {
  return `${date.getFullYear()}年${date.getMonth() + 1}月`;
}

function weekTitle(date) {
  const monday = startOfDay(addDays(date, -((date.getDay() + 6) % 7)));
  const sunday = addDays(monday, 6);
  return `${monday.getMonth() + 1}/${monday.getDate()} - ${sunday.getMonth() + 1}/${sunday.getDate()}`;
}

function eventsByDay() {
  const map = {};
  for (const event of state.events) {
    const parsed = parseEventDate(event.start);
    if (!parsed) continue;
    const key = localDateKey(parsed);
    if (!map[key]) map[key] = [];
    map[key].push({ ...event, parsedStart: parsed });
  }
  for (const key of Object.keys(map)) {
    map[key].sort((a, b) => a.parsedStart - b.parsedStart);
  }
  return map;
}

function eventChip(event) {
  const color = eventColor(event);
  const time = formatTime(parseEventDate(event.start));
  const status = eventState(event);
  return `<button class="event-chip status-${status}" style="color:${color};background:${color}1c" data-event-id="${escapeHtml(event.id)}" title="${statusLabel(event)} · ${escapeHtml(event.title)}">
    <span>${time}</span><b>${escapeHtml(event.title)}</b>
  </button>`;
}

function renderMonth() {
  const year = state.cursor.getFullYear();
  const month = state.cursor.getMonth();
  const first = new Date(year, month, 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const gridStart = addDays(first, -mondayOffset);
  const byDay = eventsByDay();
  const todayKey = localDateKey(new Date());
  let html = "";

  els.calendarWeekdays.innerHTML = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    .map((label) => `<div class="weekday-head">${label}</div>`)
    .join("");
  els.calendarWeekdays.hidden = false;

  for (let i = 0; i < 42; i++) {
    const day = addDays(gridStart, i);
    const key = localDateKey(day);
    const outside = day.getMonth() !== month;
    const isToday = key === todayKey;
    const dayEvents = byDay[key] || [];
    const visible = dayEvents.slice(0, 4);
    const extra = dayEvents.length - visible.length;
    html += `<div class="day-cell ${outside ? "outside" : ""} ${isToday ? "today" : ""}">
      <span class="day-num">${day.getDate()}</span>
      <div class="day-events">
        ${visible.map(eventChip).join("")}
        ${extra > 0 ? `<div class="more-events">+${extra} 项</div>` : ""}
      </div>
    </div>`;
  }
  els.calendarGrid.className = "calendar-grid";
  els.calendarGrid.innerHTML = html;
  els.calendarTitle.textContent = monthTitle(state.cursor);
}

function renderWeek() {
  const monday = addDays(state.cursor, -((state.cursor.getDay() + 6) % 7));
  const byDay = eventsByDay();
  const todayKey = localDateKey(new Date());
  let html = "";

  els.calendarWeekdays.innerHTML = "";
  els.calendarWeekdays.hidden = true;

  for (let i = 0; i < 7; i++) {
    const day = addDays(monday, i);
    const key = localDateKey(day);
    const dayEvents = byDay[key] || [];
    html += `<div class="week-column ${key === todayKey ? "today" : ""}">
      <div class="week-head">
        ${key === todayKey ? '<span class="today-dot" aria-label="今天"></span>' : ""}
        <strong>${["周一", "周二", "周三", "周四", "周五", "周六", "周日"][i]}</strong>
        <span>${formatDateCN(day)}</span>
      </div>
      <div class="week-events">
        ${
          dayEvents.length
            ? dayEvents
                .map(
                  (event) => `<div class="week-event" style="color:${eventColor(event)}" data-event-id="${escapeHtml(event.id)}">
                    <time>${formatTime(event.parsedStart)}</time>
                    <strong>${escapeHtml(event.title)}</strong>
                  </div>`
                )
                .join("")
            : '<p class="muted small">无安排</p>'
        }
      </div>
    </div>`;
  }
  els.calendarGrid.className = "calendar-grid week-view";
  els.calendarGrid.innerHTML = html;
  els.calendarTitle.textContent = weekTitle(state.cursor);
}

function renderCalendar() {
  if (state.view === "week") renderWeek();
  else renderMonth();
}

function renderSidebar() {
  const now = new Date();
  const todayKey = localDateKey(now);
  const byDay = eventsByDay();
  const todayEvents = byDay[todayKey] || [];
  els.todayDate.textContent = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`;
  els.todayCount.textContent = todayEvents.length ? `今天有 ${todayEvents.length} 项安排` : "今天暂无安排";

  const upcoming = [...state.events]
    .map((event) => ({ ...event, parsedStart: parseEventDate(event.start) }))
    .filter((event) => event.parsedStart && event.parsedStart >= startOfDay(now))
    .sort((a, b) => a.parsedStart - b.parsedStart)
    .slice(0, 6);

  els.upcomingList.innerHTML = upcoming.length
    ? upcoming
        .map(
          (event) => `<div class="upcoming-item" data-event-id="${escapeHtml(event.id)}">
            <span class="upcoming-dot" style="background:${eventColor(event)}"></span>
            <div>
              <strong>${escapeHtml(event.title)}</strong>
              <span>${formatDateCN(event.parsedStart)} ${formatTime(event.parsedStart)} · ${eventTypeLabel(event)} · ${statusLabel(event)}</span>
            </div>
          </div>`
        )
        .join("")
    : '<p class="muted small">暂无即将到来的安排</p>';

  const status = state.sync?.status || "idle";
  els.syncStatus.innerHTML = `<span class="status-dot ${status === "ok" ? "ok" : status === "error" ? "error" : "idle"}"></span><span>${status === "ok" ? "同步正常" : status === "error" ? "同步失败" : "等待同步"}</span>`;
  const progress = state.syncProgress;
  if (progress && progress.status === "running") {
    els.syncProgress.hidden = false;
    els.syncProgressBar.style.width = `${progress.progress || 0}%`;
    els.syncStage.textContent = progress.message || progress.stage || "";
  } else {
    els.syncProgress.hidden = true;
  }
  els.lastSync.textContent = state.sync?.time ? `上次同步：${new Date(state.sync.time).toLocaleString("zh-CN")}` : state.sync?.message || "暂无同步记录";
  if (state.syncCursor) {
    els.syncCursor.textContent = `游标 UID #${state.syncCursor.last_uid || 0} · 已同步 ${state.syncCursor.synced_count || 0} 封`;
  }
}

function renderUsage(data) {
  const usage = data || state.usage;
  if (!usage) return;
  const models = usage.models || [];
  if (!models.length) {
    els.usageSummary.innerHTML = '<p class="muted small">暂无模型调用</p>';
    return;
  }
  els.usageSummary.innerHTML =
    models
      .map(
        (item) => `<div class="usage-row">
          <strong>${escapeHtml(item.model)}</strong>
          <span>${item.total_tokens.toLocaleString()} tokens · $${Number(item.cost).toFixed(4)}</span>
        </div>`
      )
      .join("") +
    `<div class="usage-total">总计 ${usage.total_tokens.toLocaleString()} tokens · $${Number(usage.total_cost).toFixed(4)}</div>`;
}

function renderAdminStats(data) {
  const mailbox = data.mailbox || {};
  const cursor = data.cursor || {};
  const usage = data.usage || {};
  const cache = data.cache || {};
  els.adminStats.innerHTML = `
    <div class="admin-stat"><span>邮箱邮件总数</span><strong>${mailbox.total ?? "-"}</strong></div>
    <div class="admin-stat"><span>已同步邮件</span><strong>${cursor.synced_count || 0}</strong></div>
    <div class="admin-stat"><span>日历事件</span><strong>${data.events || 0}</strong></div>
    <div class="admin-stat"><span>Token 总量</span><strong>${(usage.total_tokens || 0).toLocaleString()}</strong></div>
  `;

  els.adminMail.innerHTML = `
    <div class="admin-mail-item"><span>收件箱总数</span><strong>${mailbox.total ?? "-"}</strong></div>
    <div class="admin-mail-item"><span>未读邮件</span><strong>${mailbox.unread ?? "-"}</strong></div>
    <div class="admin-mail-item"><span>同步游标 UID</span><strong>${cursor.last_uid || 0}</strong></div>
    <div class="admin-mail-item"><span>已同步邮件</span><strong>${cursor.synced_count || 0}</strong></div>
    <div class="admin-mail-item"><span>日历事件</span><strong>${data.events || 0}</strong></div>
    <div class="admin-mail-item"><span>上次同步</span><strong>${new Date(data.sync?.time || Date.now()).toLocaleString("zh-CN")}</strong></div>
  `;

  const models = usage.models || [];
  els.adminUsage.innerHTML = models.length
    ? `<table class="admin-table">
        <thead><tr><th>模型</th><th>调用</th><th>Prompt Tokens</th><th>Completion Tokens</th><th>总 Tokens</th><th>费用 USD</th></tr></thead>
        <tbody>
          ${models
            .map(
              (item) => `<tr>
                <td>${escapeHtml(item.model)}</td>
                <td>${item.calls}</td>
                <td>${item.prompt_tokens.toLocaleString()}</td>
                <td>${item.completion_tokens.toLocaleString()}</td>
                <td>${item.total_tokens.toLocaleString()}</td>
                <td>${Number(item.cost).toFixed(4)}</td>
              </tr>`
            )
            .join("")}
          <tr>
            <td><strong>合计</strong></td>
            <td>${usage.total_calls}</td>
            <td colspan="3">${usage.total_tokens.toLocaleString()}</td>
            <td><strong>${Number(usage.total_cost).toFixed(4)}</strong></td>
          </tr>
        </tbody>
      </table>`
    : '<p class="muted">暂无模型调用记录</p>';

  if (els.adminRetentionInfo) {
    els.adminRetentionInfo.textContent =
      `模型缓存保留 ${cache.model_cache_ttl_hours ?? 24}h · 日志保留 ${cache.log_retention_days ?? 7} 天 · 事件保留 ${cache.event_retention_days ?? 30} 天`;
  }
}

async function loadAdminStats() {
  try {
    const data = await api("/api/admin/stats");
    renderAdminStats(data);
  } catch (error) {
    showToast(error.message);
  }
}

async function loadAdminLogs() {
  try {
    const level = els.adminLogLevel?.value || "";
    const data = await api(`/api/admin/logs?lines=500&level=${encodeURIComponent(level)}`);
    const rows = data.rows || [];
    els.adminLogs.innerHTML = rows.length
      ? `<table class="admin-table log-table">
          <thead>
            <tr><th>时间</th><th>级别</th><th>模块</th><th>内容</th></tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `<tr>
                  <td class="log-time">${escapeHtml(row.time)}</td>
                  <td><span class="log-level level-${escapeHtml(row.level.toLowerCase())}">${escapeHtml(row.level)}</span></td>
                  <td class="log-module">${escapeHtml(row.module)}</td>
                  <td class="log-message">${escapeHtml(row.message)}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>`
      : '<p class="muted">暂无日志</p>';
  } catch (error) {
    els.adminLogs.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

async function clearAdminTarget(target) {
  try {
    await api("/api/admin/clear", {
      method: "POST",
      body: JSON.stringify({ target }),
    });
    showToast("清理完成");
    await loadAdminStats();
    await loadAdminLogs();
    await loadState();
  } catch (error) {
    showToast(error.message);
  }
}

function openAdmin() {
  openModal(els.adminModal);
  loadAdminStats();
  loadAdminLogs();
}

function switchAdminTab(name) {
  document.querySelectorAll(".admin-nav-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.adminTab === name);
  });
  document.querySelectorAll(".admin-pane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === `admin-pane-${name}`);
  });
}

function render() {
  renderCalendar();
  renderSidebar();
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    els.toast.hidden = true;
  }, 2600);
}

function openModal(modal) {
  modal.hidden = false;
}

function closeModal(modal) {
  modal.hidden = true;
}

function openEventDetail(eventId) {
  const event = state.events.find((item) => item.id === eventId);
  if (!event) return;
  state.selectedEvent = event;
  const start = parseEventDate(event.start);
  const end = parseEventDate(event.end);
  const detailLinks = [];
  const mailboxUrl = event.email_web_url || event.email_url;
  if (mailboxUrl) {
    detailLinks.push({ label: "打开 QQ 邮箱", url: mailboxUrl });
  }
  if (event.email_uid) {
    detailLinks.push({
      label: "下载原始邮件",
      url: event.email_download_url || `/api/emails/${encodeURIComponent(event.email_uid)}/raw`,
    });
  }
  (event.links || []).forEach((link) => {
    detailLinks.push({ label: link.label || "邮件链接", url: link.url });
  });
  els.detailTitle.textContent = event.title || "事件详情";
  els.detailBody.innerHTML = `
    <div class="detail-row"><span>时间</span><strong>${formatDateCN(start)} ${formatTime(start)} - ${end ? `${formatDateCN(end)} ${formatTime(end)}` : "未设置"}</strong></div>
    <div class="detail-row"><span>类型</span><strong>${eventTypeLabel(event)}</strong></div>
    <div class="detail-row"><span>状态</span><strong class="status-text status-${eventState(event)}">${statusLabel(event)}</strong></div>
    <div class="detail-row"><span>来源</span><strong>${escapeHtml(event.source_subject || "手动添加")}</strong></div>
    ${event.source_from ? `<div class="detail-row"><span>发件人</span><strong>${escapeHtml(event.source_from)}</strong></div>` : ""}
    ${event.description ? `<div class="detail-row"><span>说明</span><strong>${escapeHtml(event.description)}</strong></div>` : ""}
    ${
      detailLinks.length
        ? `<div class="detail-row"><span>邮件链接分析</span><div class="link-list">
            ${detailLinks
              .map(
                (link) => `<a class="link-item" href="${escapeHtml(link.url)}" target="_blank" rel="noopener">
                  <strong>${escapeHtml(link.label)}</strong>
                  <span>${escapeHtml(link.url)}</span>
                </a>`
              )
              .join("")}
          </div></div>`
        : ""
    }
    ${
      event.source_html || event.source_body
        ? `<details class="source-body"><summary>查看邮件原文</summary>
            <div class="source-tabs">
              <button class="source-tab active" type="button" data-mode="html">HTML 渲染</button>
              <button class="source-tab" type="button" data-mode="text">纯文本</button>
            </div>
            <iframe class="email-frame" sandbox="" referrerpolicy="no-referrer" title="邮件原文" srcdoc="${escapeHtml(event.source_html || `<pre>${escapeHtml(event.source_body || "")}</pre>`)}"></iframe>
            <pre class="email-text" hidden>${escapeHtml(event.source_body || "")}</pre>
          </details>`
        : ""
    }
  `;
  els.toggleStatusBtn.textContent = eventState(event) === "done" ? "重新打开" : "标记完成";
  openModal(els.detailModal);
}

function showEventTooltip(event, anchor) {
  if (!event) return;
  const start = parseEventDate(event.start);
  const end = parseEventDate(event.end);
  const linkCount = (event.links || []).length;
  els.eventTooltip.innerHTML = `
    <strong>${escapeHtml(event.title)}</strong>
    <div class="tooltip-meta">
      <span class="tooltip-time">${formatDateCN(start)} ${formatTime(start)}${end ? ` - ${formatTime(end)}` : ""}</span>
      <span class="tooltip-status">${eventTypeLabel(event)} · ${statusLabel(event)}</span>
    </div>
    ${event.source_subject ? `<div class="tooltip-source">${escapeHtml(event.source_subject)}</div>` : ""}
    ${linkCount ? `<div class="tooltip-links">${linkCount} 个邮件链接</div>` : ""}
  `;
  els.eventTooltip.hidden = false;
  const rect = anchor.getBoundingClientRect();
  const tipRect = els.eventTooltip.getBoundingClientRect();
  let left = rect.left;
  let top = rect.bottom + 8;
  if (top + tipRect.height > window.innerHeight) top = rect.top - tipRect.height - 8;
  if (left + tipRect.width > window.innerWidth) left = window.innerWidth - tipRect.width - 10;
  els.eventTooltip.style.left = `${Math.max(8, left)}px`;
  els.eventTooltip.style.top = `${Math.max(8, top)}px`;
  debugLog("tooltip shown", event.id);
}

function hideEventTooltip() {
  els.eventTooltip.hidden = true;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "请求失败");
  return data;
}

async function loadState() {
  try {
    const data = await api("/api/state");
    state.events = data.events || [];
    state.config = data.config || {};
    state.sync = data.sync || {};
    state.meta = data.meta || { email_providers: {}, model_providers: {} };
    state.usage = data.usage || null;
    state.syncCursor = data.sync_cursor || null;
    state.syncProgress = data.sync_progress || null;
    render();
    renderUsage(state.usage);
    debugLog("state loaded", state.events.length);
  } catch (error) {
    showToast(error.message);
  }
}

async function runSync() {
  els.syncStatus.innerHTML = '<span class="status-dot idle"></span><span>同步中</span>';
  try {
    const result = await api("/api/sync", { method: "POST", body: "{}" });
    if (result.busy) {
      showToast("同步已在进行中");
      await loadState();
      return;
    }
    state.sync = { status: "ok", time: new Date().toISOString(), message: "同步完成" };
    await loadState();
    debugLog("sync finished");
    showToast("邮件同步完成");
  } catch (error) {
    state.sync = { status: "error", message: error.message };
    renderSidebar();
    showToast(error.message);
  }
}

function populateEmailProviders() {
  const select = els.settingsForm.email_provider;
  const providers = state.meta?.email_providers || {};
  select.innerHTML = Object.entries(providers)
    .map(([key, item]) => `<option value="${key}">${escapeHtml(item.label)}</option>`)
    .join("");
}

function updateEmailPreset() {
  const select = els.settingsForm.email_provider;
  const provider = state.meta?.email_providers?.[select.value] || {};
  if (provider.imap_host) els.settingsForm.imap_host.value = provider.imap_host;
  if (provider.imap_port) els.settingsForm.imap_port.value = provider.imap_port;
  els.emailAuthHint.textContent = provider.auth_hint || "";
}

function populateModelProviders() {
  const select = els.settingsForm.model_provider;
  const providers = state.meta?.model_providers || {};
  select.innerHTML = Object.entries(providers)
    .map(([key, item]) => `<option value="${key}">${escapeHtml(item.label)}</option>`)
    .join("");
}

function updateModelPreset() {
  const providerSelect = els.settingsForm.model_provider;
  const modelSelect = els.settingsForm.model_name;
  const provider = state.meta?.model_providers?.[providerSelect.value] || {};
  modelSelect.innerHTML = '<option value="">请获取模型列表</option>';
  if (provider.api_base !== undefined) els.settingsForm.api_base.value = provider.api_base;
  els.modelAuthHint.textContent = provider.needs_key
    ? "保存 API Key 后点击“获取可用模型”"
    : "本地或免费模型，可自动获取模型列表";
}

async function loadAvailableModels(useSaved = false) {
  const form = els.settingsForm;
  const modelSelect = form.model_name;
  const previous = modelSelect.value;
  let data;
  try {
    if (useSaved) {
      data = await api("/api/models");
    } else {
      data = await api("/api/models", {
        method: "POST",
        body: JSON.stringify({
          model: {
            provider: form.model_provider.value,
            api_base: form.api_base.value.trim(),
            api_key: form.api_key.value.trim(),
          },
        }),
      });
    }
  } catch (error) {
    debugLog("load models failed", error);
    els.modelAuthHint.textContent = error.message;
    return;
  }

  if (data.models && data.models.length) {
    modelSelect.innerHTML = data.models
      .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
      .join("");
    if (previous && data.models.includes(previous)) modelSelect.value = previous;
    els.modelAuthHint.textContent = `已从 ${data.source} 获取 ${data.models.length} 个模型`;
  } else {
    modelSelect.innerHTML = '<option value="">无可用模型</option>';
    els.modelAuthHint.textContent = data.message || "未获取到模型";
  }
}

function fillSettings() {
  const config = state.config || {};
  const cache = config.cache || {};
  const model = config.model || {};
  const form = els.settingsForm;
  populateEmailProviders();
  populateModelProviders();
  form.email.value = config.email || "";
  form.auth_code.value = "";
  form.email_provider.value = config.email_provider || "qq";
  form.imap_host.value = config.imap_host || "";
  form.imap_port.value = config.imap_port || 993;
  form.mailbox_web_url.value = config.mailbox_web_url || "";
  form.fetch_limit.value = config.fetch_limit || 50;
  form.auto_sync.checked = Boolean(config.auto_sync);
  form.sync_interval_minutes.value = config.sync_interval_minutes || 30;
  form.log_level.value = config.log_level || "INFO";
  form.cache_model_ttl.value = cache.model_cache_ttl_hours || 24;
  form.cache_log_retention.value = cache.log_retention_days || 7;
  form.cache_event_retention.value = cache.event_retention_days || 30;
  form.cache_cleanup_interval.value = cache.cleanup_interval_hours || 24;
  form.model_enabled.checked = Boolean(model.enabled);
  form.model_provider.value = model.provider || "";
  form.model_name.value = model.model_name || "";
  form.api_base.value = model.api_base || "";
  form.api_key.value = "";
  updateEmailPreset();
  updateModelPreset();
  if (model.model_name) form.model_name.value = model.model_name;
  if (model.api_key || model.provider === "ollama") loadAvailableModels(true);
}

async function saveSettings(event) {
  event.preventDefault();
  const form = els.settingsForm;
  const payload = {
    email_provider: form.email_provider.value,
    email: form.email.value.trim(),
    auth_code: form.auth_code.value.trim(),
    imap_host: form.imap_host.value.trim(),
    imap_port: Number(form.imap_port.value),
    mailbox_web_url: form.mailbox_web_url.value.trim(),
    fetch_limit: Number(form.fetch_limit.value),
    auto_sync: form.auto_sync.checked,
    sync_interval_minutes: Number(form.sync_interval_minutes.value),
    log_level: form.log_level.value,
    cache: {
      model_cache_ttl_hours: Number(form.cache_model_ttl.value),
      log_retention_days: Number(form.cache_log_retention.value),
      event_retention_days: Number(form.cache_event_retention.value),
      cleanup_interval_hours: Number(form.cache_cleanup_interval.value),
    },
    model: {
      enabled: form.model_enabled.checked,
      provider: form.model_provider.value,
      api_base: form.api_base.value.trim(),
      api_key: form.api_key.value.trim(),
      model_name: form.model_name.value,
    },
  };
  try {
    const result = await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
    state.config = result.config;
    showToast("设置已保存");
    closeModal(els.settingsModal);
  } catch (error) {
    showToast(error.message);
  }
}

async function saveEvent(event) {
  event.preventDefault();
  const form = els.eventForm;
  const payload = {
    title: form.title.value.trim(),
    start: new Date(form.start.value).toISOString().slice(0, 19),
    end: form.end.value ? new Date(form.end.value).toISOString().slice(0, 19) : "",
    type: form.type.value,
    description: form.description.value.trim(),
  };
  if (state.editingEventId) payload.id = state.editingEventId;
  if (!payload.title || !payload.start) {
    showToast("标题和开始时间必填");
    return;
  }
  try {
    const wasEditing = Boolean(state.editingEventId);
    await api("/api/events", {
      method: wasEditing ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    state.editingEventId = null;
    closeModal(els.eventModal);
    await loadState();
    showToast(wasEditing ? "事件已更新" : "事件已添加");
  } catch (error) {
    showToast(error.message);
  }
}

function openEditEvent(event) {
  state.editingEventId = event.id;
  const form = els.eventForm;
  const start = parseEventDate(event.start);
  const end = parseEventDate(event.end);
  form.title.value = event.title || "";
  form.start.value = start ? new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  form.end.value = end ? new Date(end.getTime() - end.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  form.type.value = event.type || "other";
  form.description.value = event.description || "";
  els.eventModalTitle.textContent = "编辑事件";
  closeModal(els.detailModal);
  openModal(els.eventModal);
}

async function toggleSelectedStatus() {
  if (!state.selectedEvent) return;
  const next = eventState(state.selectedEvent) === "done" ? "auto" : "done";
  try {
    await api("/api/events", {
      method: "PUT",
      body: JSON.stringify({ id: state.selectedEvent.id, status: next }),
    });
    closeModal(els.detailModal);
    await loadState();
    showToast(next === "done" ? "已标记完成" : "已重新打开");
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteSelectedEvent() {
  if (!state.selectedEvent) return;
  try {
    await api("/api/events", {
      method: "DELETE",
      body: JSON.stringify({ id: state.selectedEvent.id }),
    });
    closeModal(els.detailModal);
    await loadState();
    showToast("事件已删除");
  } catch (error) {
    showToast(error.message);
  }
}

function moveCursor(direction) {
  if (state.view === "month") {
    state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() + direction, 1);
  } else {
    state.cursor = addDays(state.cursor, direction * 7);
  }
  renderCalendar();
}

document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => {
    const modal = button.closest(".modal");
    if (modal) closeModal(modal);
  });
});

document.querySelectorAll(".view-btn").forEach((button) => {
  button.addEventListener("click", () => {
    state.view = button.dataset.view;
    document.querySelectorAll(".view-btn").forEach((item) => item.classList.toggle("active", item === button));
    renderCalendar();
  });
});

document.getElementById("prev-btn").addEventListener("click", () => moveCursor(-1));
document.getElementById("next-btn").addEventListener("click", () => moveCursor(1));
document.getElementById("today-btn").addEventListener("click", () => {
  state.cursor = new Date();
  renderCalendar();
});
document.getElementById("settings-btn").addEventListener("click", () => {
  fillSettings();
  openModal(els.settingsModal);
});
els.adminBtn.addEventListener("click", openAdmin);
els.adminLogRefresh.addEventListener("click", loadAdminLogs);
els.adminLogLevel.addEventListener("change", loadAdminLogs);
els.adminResetUsage.addEventListener("click", () => clearAdminTarget("usage"));
els.adminResetCursor.addEventListener("click", () => clearAdminTarget("cursor"));
document.getElementById("add-event-btn").addEventListener("click", () => {
  state.editingEventId = null;
  els.eventModalTitle.textContent = "添加事件";
  els.eventForm.reset();
  els.eventForm.start.value = new Date().toISOString().slice(0, 16);
  els.eventForm.end.value = new Date(Date.now() + 60 * 60 * 1000).toISOString().slice(0, 16);
  openModal(els.eventModal);
});
document.getElementById("sync-btn").addEventListener("click", runSync);
document.getElementById("test-connection-btn").addEventListener("click", runSync);
els.settingsForm.addEventListener("submit", saveSettings);
els.eventForm.addEventListener("submit", saveEvent);
els.settingsForm.email_provider.addEventListener("change", updateEmailPreset);
els.settingsForm.model_provider.addEventListener("change", () => {
  updateModelPreset();
  const provider = state.meta?.model_providers?.[els.settingsForm.model_provider.value];
  if (!provider?.needs_key) loadAvailableModels(false);
});
els.refreshModelsBtn.addEventListener("click", () => loadAvailableModels(false));
els.editEventBtn.addEventListener("click", () => {
  if (state.selectedEvent) openEditEvent(state.selectedEvent);
});
els.toggleStatusBtn.addEventListener("click", toggleSelectedStatus);
els.resetUsageBtn.addEventListener("click", async () => {
  try {
    await api("/api/usage", { method: "DELETE", body: "{}" });
    await loadState();
    showToast("模型用量已清零");
  } catch (error) {
    showToast(error.message);
  }
});
els.resetCursorBtn.addEventListener("click", async () => {
  try {
    await api("/api/sync-cursor", { method: "DELETE", body: "{}" });
    await loadState();
    showToast("同步游标已重置，下次同步会重新处理最近邮件");
  } catch (error) {
    showToast(error.message);
  }
});
document.querySelectorAll(".admin-nav-btn").forEach((button) => {
  button.addEventListener("click", () => switchAdminTab(button.dataset.adminTab));
});
document.querySelectorAll("[data-clear-target]").forEach((button) => {
  button.addEventListener("click", () => clearAdminTarget(button.dataset.clearTarget));
});
document.getElementById("delete-event-btn").addEventListener("click", deleteSelectedEvent);

document.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-event-id]");
  if (chip) openEventDetail(chip.dataset.eventId);
});

document.addEventListener("click", (event) => {
  const tab = event.target.closest(".source-tab");
  if (!tab) return;
  const details = tab.closest(".source-body");
  details.querySelectorAll(".source-tab").forEach((item) => item.classList.toggle("active", item === tab));
  const htmlMode = tab.dataset.mode === "html";
  const frame = details.querySelector(".email-frame");
  const text = details.querySelector(".email-text");
  if (frame) frame.hidden = !htmlMode;
  if (text) text.hidden = htmlMode;
});

document.addEventListener("mouseover", (event) => {
  const target = event.target.closest("[data-event-id]");
  if (!target) return;
  const eventItem = state.events.find((item) => item.id === target.dataset.eventId);
  if (eventItem) showEventTooltip(eventItem, target);
});

document.addEventListener("mouseout", (event) => {
  const target = event.target.closest("[data-event-id]");
  if (target && !target.contains(event.relatedTarget)) hideEventTooltip();
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    document.querySelectorAll(".modal").forEach((modal) => closeModal(modal));
  }
});

loadState();
setInterval(() => {
  if (!document.hidden) loadState();
}, 20000);
