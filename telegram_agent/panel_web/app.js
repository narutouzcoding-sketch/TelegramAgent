"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  home: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
  chat: "M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z",
  calls:
    "M22 16.9v3a2 2 0 0 1-2.2 2A19.8 19.8 0 0 1 11.2 19a19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.5 2.1L8 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.7 2Z",
  plans: "M9 5h11M9 12h11M9 19h11M3 5l1 1 2-2M3 12l1 1 2-2M3 19l1 1 2-2",
  reminders: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
  contacts:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.9M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  arrow: "M7 17 17 7M7 7h10v10",
  plus: "M12 5v14M5 12h14",
  play: "m9 5 11 7-11 7Z",
  pause: "M9 5v14M15 5v14",
  check: "m5 12 4 4L19 6",
  recordings: "M12 3v18M8 7v10M16 7v10M4 10v4M20 10v4",
  clock: "M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
};
paths.library = paths.plans;
paths.menu = "M4 6h16M4 12h16M4 18h16";
const icon = (name, cls = "") =>
  `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.home}"/></svg>`;
const navigation = [
  ["home", "Bosh sahifa"],
  ["chat", "Suhbat"],
  ["calls", "Qo‘ng‘iroqlar"],
  ["plans", "Rejalar"],
  ["reminders", "Eslatmalar"],
  ["contacts", "Kontaktlar"],
  ["recordings", "Yozuvlar"],
  ["library", "Hujjatlar"],
];
let callHistoryQuery = "",
  callHistoryStatus = "all";
const formDrafts = {};
let editorVersion = 0;
let sessionEpoch = 0,
  refreshFlight = null;
const activeOperations = new Map(),
  busyMarkup = new WeakMap(),
  writeTickets = new Map();
class SessionChanged extends Error {}
const token = () =>
  Array.from(crypto.getRandomValues(new Uint32Array(4)))
    .map((n) => n.toString(16).padStart(8, "0"))
    .join("");
function operationKey(button) {
  if (button?.dataset.action)
    return (
      "action:" +
      button.dataset.action +
      ":" +
      (button.dataset.id || button.dataset.recordingId || "")
    );
  if (button?.type === "submit" && button.form) return "form:" + button.form.id;
  return button?.id ? "button:" + button.id : button;
}
function syncBusyButtons() {
  document
    .querySelectorAll("button[type=submit],button[data-action],button[id]")
    .forEach((button) => {
      const pending = activeOperations.has(operationKey(button));
      if (pending && !busyMarkup.has(button)) {
        busyMarkup.set(button, {
          html: button.innerHTML,
          disabled: button.disabled,
        });
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        button.textContent = "Bajarilmoqda…";
      } else if (!pending && busyMarkup.has(button)) {
        const saved = busyMarkup.get(button);
        button.innerHTML = saved.html;
        button.disabled = saved.disabled;
        button.removeAttribute("aria-busy");
        busyMarkup.delete(button);
      }
    });
}
let csrf = "",
  state = null,
  current = navigation.some(([id]) => id === location.hash.slice(1))
    ? location.hash.slice(1)
    : "home",
  chatPending = false,
  editorKind = "",
  chatStamp = "",
  contactQuery = "",
  recordingStamp = "",
  chatDraft = "",
  callDraft = null;
const callStates = {
  text_sent: ["Telegram xabari yuborildi", "success"],
  text_replied: ["Yozma javob keldi", "success"],
  text_failed: ["Telegram xabari yuborilmadi", "danger"],
  rate_limited: ["Mahalliy limit band", "waiting"],
  connection_failed: ["Qabul qilindi — ovoz ulanmagan", "danger"],
  unanswered: ["Qo‘ng‘iroq ulanishi tasdiqlanmadi", "waiting"],
  busy: ["Kontakt band", "waiting"],
  rejected: ["Qo‘ng‘iroq rad etildi", "muted"],
  privacy_blocked: ["Qo‘ng‘iroqqa ruxsat yo‘q", "muted"],
  completed: ["Savolga javob aniqlandi", "success"],
  recorded_unverified: ["Faqat ovoz yozildi — javob tekshirilmagan", "waiting"],
  answer_unverified: ["Javob tasdiqlanmagan", "waiting"],
  partial_answer: ["Qisman javob olindi", "waiting"],
  declined: ["Javob berishni rad etdi", "muted"],
  no_answer: ["Javob olinmadi", "waiting"],
  queued: ["Kutilmoqda", "waiting"],
  running: ["Qo‘ng‘iroq ketmoqda", "purple"],
  sent: ["Audio uzatildi", "success"],
  failed: ["Bajarilmadi", "danger"],
  cancelled: ["Bekor qilindi", "muted"],
  interrupted: ["To‘xtatilgan", "muted"],
  simulated: ["Sinov", "muted"],
};
const months = [
  "yan",
  "fev",
  "mar",
  "apr",
  "may",
  "iyn",
  "iyl",
  "avg",
  "sen",
  "okt",
  "noy",
  "dek",
];
function dateParts(value) {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: state?.agent.timezone || "Asia/Tashkent",
      day: "numeric",
      month: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(value))
      .map((p) => [p.type, p.value]),
  );
}
const dateTime = (value) => {
  if (!value) return "Hozir";
  if (Number.isNaN(Date.parse(value))) return "Vaqt noma’lum";
  const p = dateParts(value),
    year = p.year === dateParts(Date.now()).year ? "" : " " + p.year;
  return `${p.day} ${months[Number(p.month) - 1]}${year}, ${p.hour}:${p.minute}`;
};
function toast(message, bad = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("bad", bad);
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 5000);
}
async function api(action, data) {
  const epoch = sessionEpoch,
    controller = new AbortController();
  const idempotent = new Set([
    "chat",
    "plan",
    "reminder",
    "library-note",
    "call",
    "snooze-reminder",
  ]);
  let ticketKey = "";
  if (data !== undefined && idempotent.has(action) && !data.request_id) {
    ticketKey = action + ":" + JSON.stringify(data);
    if (!writeTickets.has(ticketKey)) writeTickets.set(ticketKey, token());
    data = { ...data, request_id: writeTickets.get(ticketKey) };
  }
  const timer = setTimeout(
    () => controller.abort(),
    data === undefined ? 15000 : 180000,
  );
  try {
    const response = await fetch("/api/" + action, {
      method: data === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers:
        data === undefined
          ? {}
          : { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: controller.signal,
    });
    if (epoch !== sessionEpoch) throw new SessionChanged();
    let result;
    try {
      result = await response.json();
    } catch {
      throw Error("Server javobini o‘qib bo‘lmadi.");
    }
    if (epoch !== sessionEpoch) throw new SessionChanged();
    if (!response.ok) {
      if (response.status === 401 && action !== "login") showLogin();
      throw Error(result.error || "Amal bajarilmadi.");
    }
    if (ticketKey) writeTickets.delete(ticketKey);
    return result;
  } catch (error) {
    if (epoch !== sessionEpoch) throw new SessionChanged();
    if (error.name === "AbortError" || error instanceof TypeError)
      throw Error(
        data === undefined
          ? "Server bilan aloqa yo‘q."
          : ticketKey
            ? "Server javobi olinmadi. Natijani tekshiring; ayni so‘rov qayta bosilganda takrorlanishdan himoyalangan."
            : "Server javobi olinmadi. Amal holatini tekshiring.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
function showLogin() {
  sessionEpoch++;
  refreshFlight = null;
  activeOperations.clear();
  writeTickets.clear();
  chatPending = false;
  $("#login-form").reset();
  $("#login-form [name=password]").type = "password";
  $("#toggle-password").textContent = "Ko‘rsatish";
  syncBusyButtons();
  AgentWorkspace.reset();
  for (const key of Object.keys(formDrafts)) delete formDrafts[key];
  callHistoryQuery = "";
  callHistoryStatus = "all";
  document.getElementById("document-body").textContent = "";
  document.getElementById("document-title").textContent = "Hujjat matni";
  AgentVoice.cleanup(true);
  document.querySelectorAll("dialog[open]").forEach((d) => d.close());
  chatDraft = "";
  callDraft = null;
  contactQuery = "";
  organizerQuery = "";
  organizerResults = null;
  organizerRequest++;
  $("#workspace").hidden = true;
  $("#login").hidden = false;
  csrf = "";
  state = null;
  chatStamp = "";
  $("#main").replaceChildren();
}
function nav() {
  const item = ([
    id,
    label,
  ]) => `<button data-page="${id}" class="nav-item ${current === id ? "active" : ""}" ${current === id ? 'aria-current="page"' : ""}>
    ${icon(id)}<span>${esc(label)}</span>${id === "reminders" && state?.reminders.length ? `<b>${state.reminders.length}</b>` : ""}</button>`;
  const markup = navigation.map(item).join("");
  $("#navigation").innerHTML = markup;
  $("#all-navigation").innerHTML = markup;
  $("#mobile-navigation").innerHTML =
    navigation
      .filter(([id]) => ["home", "chat", "calls", "contacts"].includes(id))
      .map(item)
      .join("") +
    `<button class="nav-item ${["plans", "reminders", "recordings", "library"].includes(current) ? "active" : ""}" data-action="open-navigation">${icon("menu")}<span>Ko‘proq</span></button>`;
  $("#page-name").textContent =
    navigation.find((n) => n[0] === current)?.[1] || "";
}
function syncAvailability() {
  if (!state) return;
  const a = state.agent,
    blocked = !a.running || a.telegram_restricted || a.telegram_paused;
  document
    .querySelectorAll(
      '#call-form button[type=submit],[data-action="call-owner"],[data-action="preview"],[data-action="sync-contacts"],[data-action="verify-contact"]',
    )
    .forEach((button) => {
      button.disabled = blocked || activeOperations.has(operationKey(button));
      if (blocked)
        button.setAttribute(
          "title",
          a.telegram_restricted
            ? "Telegram akkauntini tekshiring"
            : a.telegram_paused
              ? "Telegram kutish muddati tugashini kuting"
              : "Avval agentni ishga tushiring",
        );
      else button.removeAttribute("title");
    });
}
function header() {
  if (!state) return;
  const a = state.agent,
    blocked = a.telegram_restricted || a.telegram_paused;
  const label = a.telegram_restricted
    ? "Telegram cheklovi"
    : a.telegram_paused
      ? "Telegram kutish holatida"
      : {
          running: "Agent ishlayapti",
          connecting: "Ulanmoqda…",
          reconnecting: "Qayta ulanmoqda…",
          stopped: "Agent o‘chirilgan",
          error: "Ulanishni tekshiring",
        }[a.phase] || a.phase;
  const badge = $("#connection");
  badge.className =
    "status-badge " +
    (blocked || a.phase === "error" ? "error" : a.running ? "online" : "");
  badge.innerHTML = "<i></i><span>" + esc(label) + "</span>";
  const alert = $("#agent-alert");
  alert.hidden = !blocked;
  alert.textContent = a.telegram_restricted
    ? "Telegram akkauntga cheklov qaytargan. Xabar va qo‘ng‘iroqlar to‘xtatilgan. Akkaunt holatini Telegramda tekshiring; avtomatik qayta yuborish bajarilmaydi."
    : a.telegram_paused
      ? "Telegram " +
        dateTime(a.telegram_pause_until) +
        " gacha kutishni talab qilgan. Shu vaqtgacha xabar va qo‘ng‘iroqlar yuborilmaydi."
      : "";
  $("#zone").textContent = a.timezone;
  syncAvailability();
}
const empty = (title, description, ico = "plans") =>
  `<div class="empty-state"><span>${icon(ico)}</span><h3>${title}</h3><p>${description}</p></div>`;
const sectionHead = (title, sub, extra = "") =>
  `<div class="page-heading"><div><span class="eyebrow">SHAXSIY YORDAMCHINGIZ</span><h1>${title}</h1><p>${sub}</p></div>${extra}</div>`;
function planRows(rows) {
  return rows
    .map(
      (row) =>
        `<div class="task-row"><button class="task-check" data-action="complete-plan" data-id="${row.id}" aria-label="${esc(row.title)} — bajarildi">${icon("check")}</button><div><strong>${esc(row.title)}</strong>${row.details ? `<p>${esc(row.details)}</p>` : ""}</div><button class="row-more" data-action="edit-plan" data-id="${row.id}" aria-label="Rejani tahrirlash">⋯</button></div>`,
    )
    .join("");
}
function reminderRows(rows) {
  return rows
    .map(
      (row) =>
        `<div class="reminder-row"><span class="soft-icon">${icon(row.mode === "call" ? "calls" : "reminders")}</span><div><strong>${esc(row.title)}</strong><p>${esc(dateTime(row.due))} <span>· ${row.recovery_message_only ? "Xabar bilan tiklash" : row.mode === "call" ? "Qo‘ng‘iroq" : "Xabar"}</span></p></div>${row.state !== "delivering" ? `<button class="btn secondary small" data-action="snooze-reminder" data-id="${row.id}">15 daqiqa keyin</button>` : ""}${row.state === "failed" ? `<span class="pill danger">Yetkazilmadi</span><button class="btn secondary small" data-action="retry-reminder" data-id="${row.id}">Xabar bilan qayta eslatish</button>` : ""}${row.last_error ? `<span class="form-note">${row.delivery_status === "previous_occurrence_failed" ? "Oldingi eslatish yetkazilmadi; keyingisi saqlangan." : "Yetkazish xatosi: " + esc(row.last_error)}</span>` : ""}<span class="repeat-label">${{ none: "Bir marta", daily: "Har kuni", weekly: "Har hafta" }[row.repeat]}</span><button class="row-more" data-action="edit-reminder" data-id="${row.id}" aria-label="Eslatmani tahrirlash">⋯</button></div>`,
    )
    .join("");
}
function callReason(row) {
  const r = row.result || "";
  if (r.includes("UserPrivacyRestricted"))
    return "Kontaktning maxfiylik sozlamalari qo‘ng‘iroqni ruxsat bermadi.";
  if (r.includes("TimedOutAnswer"))
    return "Telegram qo‘ng‘iroq qabul qilingani yoki ulanishini tasdiqlamadi; savol eshittirilgani tasdiqlanmagan.";
  return r;
}
function jsonArray(value) {
  try {
    const rows = JSON.parse(value || "[]");
    return Array.isArray(rows)
      ? rows.filter((row) => row && typeof row === "object")
      : [];
  } catch {
    return [];
  }
}
function jsonObject(value) {
  try {
    const row = JSON.parse(value || "{}");
    return row && typeof row === "object" ? row : {};
  } catch {
    return {};
  }
}
function filteredCalls() {
  return state.calls.filter(
    (row) =>
      AgentContacts.matches(
        {
          name:
            state.contacts.find(
              (c) =>
                (row.recipient_user_id &&
                  c.telegram_id === row.recipient_user_id) ||
                c.reference === row.target,
            )?.name || row.target,
          reference: row.target + " " + row.message,
        },
        callHistoryQuery,
      ) &&
      (callHistoryStatus === "all" ||
        (callHistoryStatus === "pending"
          ? ["queued", "running"].includes(row.state)
          : callHistoryStatus === "done"
            ? ["completed", "text_sent", "text_replied", "sent"].includes(
                row.state,
              )
            : ![
                "queued",
                "running",
                "completed",
                "text_sent",
                "text_replied",
                "sent",
                "cancelled",
                "simulated",
              ].includes(row.state))),
  );
}
function callHistory() {
  const rows = filteredCalls();
  return rows.length
    ? callRows(rows)
    : empty(
        "Bu filtrda vazifa topilmadi",
        "Yangi topshiriq yoki boshqa filtrni tanlang.",
        "calls",
      );
}
function callRows(rows) {
  return rows
    .map((row) => {
      const shownState =
        row.state === "completed" && !row.answer_verified
          ? row.mode === "record"
            ? "recorded_unverified"
            : "answer_unverified"
          : row.state;
      const [label, color] = callStates[shownState] || [shownState, "muted"];
      return `<div class="call-row"><span class="call-history-icon">${icon("calls")}</span><div class="call-content"><strong>${esc(state.contacts.find((c) => (row.recipient_user_id && c.telegram_id === row.recipient_user_id) || c.reference === row.target)?.name || row.target)}</strong><span class="form-note"> · ${esc(row.target)}</span><p>${esc(row.message)}</p><small>${esc(dateTime(row.due || row.created))}${row.result ? " · " + esc(callReason(row)) : ""}</small>${row.mode === "relay" && row.state !== "text_sent" && row.state !== "text_replied" ? '<p class="form-note">Bir tomonlama xabar: javob tinglanmagan.</p>' : ""}${row.summary ? `<p class="call-summary"><b>Natija:</b> ${esc(row.summary)}</p>` : ""}${
        row.transcript && row.transcript !== "[]"
          ? `<details><summary>${!row.question_delivered && !jsonObject(row.diagnostics).playback_frames ? "Tayyorlangan matn — aytilgani tasdiqlanmagan" : "Suhbat matni"}</summary><div class="call-transcript">${jsonArray(
              row.transcript,
            )
              .map(
                (t) =>
                  `<p><b>${t.role === "user" ? "Kontakt" : "Agent"}:</b> ${esc(t.content)}</p>`,
              )
              .join("")}</div></details>`
          : ""
      }</div><span class="pill ${color}">${esc(label)}</span>${row.state === "queued" ? `<button class="row-more" data-action="cancel-call" data-id="${row.id}" aria-label="Qo‘ng‘iroqni bekor qilish">✕</button>` : ""}</div>`;
    })
    .join("");
}
function callDiagnostic(event) {
  if (!event) return "";
  const names = {
    incoming_received: "Kiruvchi qo‘ng‘iroq olindi",
    connecting: "Ulanish boshlandi",
    connected: "Qo‘ng‘iroq ulandi",
    ended: "Qo‘ng‘iroq tugadi",
    busy: "Agent band edi",
    other_account_rejected: "Boshqa akkauntdan qo‘ng‘iroq rad etildi",
  };
  return `<p class="form-note">Oxirgi qo‘ng‘iroq: ${esc(names[event.status] || event.status)} · ${esc(dateTime(event.at))}</p>`;
}
function home() {
  const a = state.agent;
  const dt = dateParts(Date.now());
  const today = dt.day + " " + months[Number(dt.month) - 1];
  return `${sectionHead("Bugun nimalar qilamiz?", "Rejalaringiz, suhbatlaringiz va muhim ishlaringiz — bir joyda.", `<span class="today">${icon("clock")}${esc(today)}</span>`)}<section class="hero"><div><span class="hero-kicker"><i></i> SIZNING AI YORDAMCHINGIZ</span><h2>Vaqtingiz muhim.<br>Qolganini birga qilamiz.</h2><p>Biror narsani eslataymi yoki rejalaringizni tartiblaymizmi?</p><button class="btn hero-button" data-page="chat">Suhbatni boshlash ${icon("arrow")}</button></div><div class="hero-shape" aria-hidden="true"><div class="shape-ring ring-one"></div><div class="shape-ring ring-two"></div><div class="shape-core">✦</div><span class="float-card float-one">${icon("check")} Hammasi nazoratda</span><span class="float-card float-two">${icon("reminders")} O‘z vaqtida eslatamiz</span></div></section><div class="stats">${[
    ["plans", state.plans.length, "Ochiq rejalar", "purple"],
    ["reminders", state.reminders.length, "Yaqin eslatmalar", "amber"],
    [
      "calls",
      state.calls.filter((r) => r.state === "queued").length,
      "Navbatdagi qo‘ng‘iroqlar",
      "green",
    ],
    ["contacts", state.contacts.length, "Saqlangan kontaktlar", "blue"],
  ]
    .map(
      ([name, value, label, color]) =>
        `<button class="stat-card" data-page="${name}"><span class="stat-icon ${color}">${icon(name)}</span><div><strong>${value}</strong><span>${esc(label)}</span></div>${icon("arrow", "stat-arrow")}</button>`,
    )
    .join(
      "",
    )}</div>${organizerPanel()}<div class="dashboard-grid"><section class="card"><div class="card-heading"><div><span class="eyebrow">BIR QADAMDAN BOSHLANG</span><h2>Rejalaringiz</h2></div><button class="text-button" data-action="new-plan">${icon("plus")} Reja qo‘shish</button></div>${state.plans.length ? planRows(state.plans.slice(0, 4)) : empty("Yangi rejalarga joy bor", "Bugun qilmoqchi bo‘lgan birinchi ishingizni qo‘shing.")}<button class="card-bottom-link" data-page="plans">Barcha rejalar ${icon("arrow")}</button></section><section class="card"><div class="card-heading"><div><span class="eyebrow">YODINGIZDAN KO‘TARILMASIN</span><h2>Yaqin eslatmalar</h2></div><span class="count-bubble">${state.reminders.length}</span></div>${state.reminders.length ? reminderRows(state.reminders.slice(0, 3)) : empty("Hozircha eslatma yo‘q", "Muhim vaqtni ayting, yordamchingiz eslatadi.", "reminders")}<button class="card-bottom-link" data-action="new-reminder">Eslatma yaratish ${icon("plus")}</button></section></div><div class="dashboard-grid bottom-grid"><section class="card quick-card"><div><span class="eyebrow">TEZKOR AMALLAR</span><h2>Nimadan boshlaymiz?</h2></div><div class="quick-actions"><button data-page="calls">${icon("calls")}<strong>Xabarni ayttirish</strong><span>Kontaktga qo‘ng‘iroq</span></button><button data-action="new-reminder">${icon("reminders")}<strong>Vaqtni belgilash</strong><span>Yangi eslatma</span></button><button data-action="new-contact">${icon("contacts")}<strong>Kontakt saqlash</strong><span>Ism orqali boshqaring</span></button></div></section><section class="card agent-card"><div class="agent-card-top"><span class="agent-symbol">✦</span><div><h2>Agent holati</h2><p>${a.running ? "Telegramga ulangan va tayyor." : a.phase === "reconnecting" ? "Telegram bilan aloqa uzilgan. Qayta ulanish kutilmoqda." : a.phase === "connecting" ? "Telegramga ulanish tayyorlanyapti." : "Telegram amallari uchun ishga tushiring."}</p></div></div>${callDiagnostic(a.last_call_event)}${callBudget()}${a.error ? `<p class="inline-error">${esc(a.error)}</p>` : ""}<div class="service-tags"><span>Matn <b>${esc(a.text_provider)}</b></span><span>Ovoz <b>${a.voice_enabled ? esc(a.voice_provider) : "O‘chiq"}</b></span></div><button class="btn ${a.worker_running ? "secondary" : "dark"} wide" data-action="${a.worker_running ? "stop" : "start"}">${icon(a.worker_running ? "pause" : "play")}${a.worker_running ? "Agentni to‘xtatish" : a.phase === "connecting" ? "Ulanmoqda…" : "Agentni ishga tushirish"}</button></section></div>`;
}
function callBudget() {
  return state.agent.call_budget
    ? '<p id="call-budget" class="form-note" role="status">' +
        esc(state.agent.call_budget.text) +
        "</p>"
    : "";
}
function calls() {
  return `${sectionHead("Xabaringizni yetkazamiz.", "Kontaktni tanlang, aytiladigan gapni yozing va vaqtini belgilang.")}<div class="call-header-stats"><div><small>Oxirgi topshiriqlar</small><strong>${state.calls.length}</strong></div><div><small>Navbatda</small><strong>${state.calls.filter((c) => ["queued", "running"].includes(c.state)).length}</strong></div><div><small>Matn yuborilgan</small><strong>${state.calls.filter((c) => ["text_sent", "text_replied"].includes(c.state)).length}</strong></div></div><div class="call-layout"><section class="card form-card"><div class="card-heading"><h2>Yangi vazifa</h2><span class="pill purple">Telegram orqali</span></div><form id="call-form">${callBudget()}<label>Kimga qo‘ng‘iroq qilamiz?<input name="target" required maxlength="200" placeholder="Ism, @username yoki +998…"><input name="contact_id" type="hidden"><span id="selected-recipient" class="form-note"></span></label><div class="form-columns"><label>Vazifa turi<select name="mode"><option value="text">Telegram orqali matn yuborish</option><option value="voice">Mening asl ovozimni yetkazish</option><option value="record">Faqat ovoz yozish — javob tekshirilmaydi</option><option value="ask" selected>Savol berib, javobni aniqlasin</option><option value="conversation">Vazifa bo‘yicha suhbatlashsin</option><option value="relay">Faqat xabar — javob kutilmaydi</option></select></label><label>Suhbat tili<select name="language"><option value="uz">O‘zbekcha</option><option value="en">English</option><option value="ru">Русский</option></select></label></div><button class="text-button contact-link" type="button" data-page="contacts">${icon("plus")} Kontaktni tekshirish yoki qo‘shish</button><label>Savol yoki yetkaziladigan xabar<textarea name="message" required maxlength="1500" rows="5" placeholder="Masalan: Hozir qayerdaligini so‘ra."></textarea></label><p id="call-intent-note" class="form-note" role="status">Savol bo‘lsa, agent javobni kutadi. Faqat yetkazish kerak bo‘lsa matnda “javob kutma” deb yozing.</p>${AgentVoice.html(state.voice_assets || [])}<details class="call-advanced"><summary>Suhbat chegaralari va davomiyligi</summary><div class="form-columns"><label>Javoblar chegarasi<select name="max_turns"><option value="4">4 ta javob</option><option value="2">2 ta javob</option><option value="6">6 ta javob</option><option value="10">10 ta javob</option></select></label><label>Maksimal davomiylik<select name="duration_seconds"><option value="180">3 daqiqa</option><option value="60">1 daqiqa</option><option value="300">5 daqiqa</option><option value="600">10 daqiqa</option></select></label></div></details><label>Qachon?<select name="timing"><option value="now">Hozir qo‘ng‘iroq qilish</option><option value="later">Vaqtini belgilash</option></select></label><label id="call-date-label" hidden>Toshkent vaqti<input name="due_at" type="datetime-local"></label><label id="message-fallback-label" class="check-label"><input name="fallback_to_message" type="checkbox" checked> Qo‘ng‘iroq ulanmasa Telegram xabari yuborsin</label><div class="voice-preview"><span class="soft-icon">${icon("play")}</span><div><strong>Avval ovozini eshiting</strong><p>AI ekanini, ovoz yozilib sizga yuborilishini aytadi.</p></div><button type="button" class="btn secondary small" data-action="preview">Eshitish</button></div><audio id="preview-player" controls hidden></audio><button type="submit" class="btn primary wide">${icon("calls")} Vazifani topshirish</button><details class="call-advanced"><summary>Vazifa qanday bajariladi?</summary><p class="form-note">Savolga javob kerak bo‘lsa “Savol berib, javobni aniqlasin” rejimini tanlang. “Faqat ovoz yozish” mazmunni tekshirmaydi va uni “javob olindi” deb belgilamaydi. ${state.agent.voice_provider === "free" ? (state.agent.gemini_audio_asr ? "Nutq Gemini orqali taniladi. U ishlamasa, mahalliy tanish sinab ko‘riladi." : "Nutq mahalliy Whisper modeli orqali taniladi.") : "Nutqni tanish sozlangan ovoz provayderi orqali bajariladi."} Har bir qo‘ng‘iroqning asl ovozi “Yozuvlar”da qoladi va Telegram chattingizga golos yuboriladi. Javob bo‘lmasa, avtomatik qayta terilmaydi. Belgilangan vaqtdan 5 daqiqa o‘tsa, topshiriq bekor qilinadi. Qo‘ng‘iroq limiti band yoki ulanish muvaffaqiyatsiz bo‘lsa, belgilangan zaxira xabar ishlatiladi. Yozma javob olish uchun kontakt shu xabarga Reply qilishi kerak. Kontaktning Telegram sozlamalari yetkazishga ruxsat berishi kerak.</p></details></form></section><aside><section class="card owner-call"><span class="stat-icon green">${icon("calls")}</span><h2>Yordamchingiz bilan gaplashing.</h2><p>Agent asosiy Telegram akkauntingizga qo‘ng‘iroq qiladi.</p><button class="btn dark wide" data-action="call-owner">Menga qo‘ng‘iroq qil</button><button class="text-button danger-text" data-action="hangup">Faol qo‘ng‘iroqni tugatish</button></section><div class="info-note">${icon("clock")}<p>Belgilangan qo‘ng‘iroq agent ishlayotgan paytda bajariladi. Kompyuter o‘chiq bo‘lsa, serverga ko‘chirmagunimizcha ishlamaydi.</p></div></aside></div><section class="card history-card"><div class="card-heading"><h2>Vazifalar tarixi</h2><span class="subtle">Oxirgi 20 ta va barcha faol topshiriqlar</span></div><div class="history-filters"><input id="call-history-search" type="search" value="${esc(callHistoryQuery)}" placeholder="Kontakt yoki topshiriqdan qidirish"><select id="call-history-status" aria-label="Vazifa holati">${[
    ["all", "Barchasi"],
    ["pending", "Navbatdagi"],
    ["done", "Bajarilgan"],
    ["attention", "E’tibor kerak"],
  ]
    .map(
      ([v, l]) =>
        `<option value="${v}" ${callHistoryStatus === v ? "selected" : ""}>${l}</option>`,
    )
    .join(
      "",
    )}</select></div><div id="call-history">${callHistory()}</div><p class="history-note">“Audio uzatildi” holati qabul qiluvchi xabarni eshitganini alohida tasdiqlamaydi.</p></section>`;
}
function library() {
  return AgentWorkspace.library();
}
function plans() {
  return AgentWorkspace.plans();
}
function reminders() {
  return AgentWorkspace.reminders();
}
function contacts() {
  return AgentWorkspace.contacts();
}
function aiUsage() {
  const {
    ai_status: ai,
    ai_backups: backups = {},
    asr_provider: asr,
    text_provider: primary,
  } = state.agent;
  const daily = ai?.daily;
  const names = new Set([
    primary,
    ...Object.keys(backups),
    ...Object.keys(daily?.providers || {}),
  ]);
  const rows = [...names]
    .map((name) => {
      const used = daily?.providers?.[name] || {};
      const status = name === primary ? ai : backups[name];
      const wait = status?.cooldown_seconds;
      const availability =
        status?.configured === false
          ? "API kaliti kiritilmagan."
          : wait
            ? `Kutish vaqti ${wait} soniya.`
            : "";
      return `<li><b>${esc(name)}</b> · ${used.requests || 0} so‘rov, ${used.input_tokens || 0} kirish va ${used.output_tokens || 0} chiqish tokeni.
      ${used.unknown_usage ? `Sarfi noma’lum: ${used.unknown_usage} so‘rov.` : ""} ${availability}
      ${status?.last_error ? esc(status.last_error) : ""}</li>`;
    })
    .join("");
  return `<section id="ai-usage" class="card form-card"><h2>AI va token sarfi</h2>
    <p>Nutq tanish: <b>${esc(asr || "Kutilyapti")}</b>.</p>
    ${
      daily
        ? `<p>Bugun <b>${esc(daily.day)}</b> · ${esc(daily.timezone)}</p><ul>${rows}</ul>
      <p class="form-note">Har bir xizmat uchun kunlik chegara: ${daily.max_requests || "cheklanmagan"} so‘rov, ${daily.max_tokens || "cheklanmagan"} token.</p>`
        : "<p>Kunlik sarf hali qayd etilmagan.</p>"
    }
    <p class="form-note">Hisoblagich faqat agentdagi so‘rovlarni ko‘rsatadi. “Faqat ovoz yozish” AI va matn tanishni chaqirmaydi.</p></section>`;
}
let organizerQuery = "",
  organizerResults = null,
  organizerRequest = 0;

function organizerSearchResults() {
  if (organizerResults === null) return "";
  if (!organizerResults.length)
    return '<p class="form-note">Mos yozuv topilmadi. Boshqa so‘z bilan qidiring.</p>';
  const labels = {
    plan: "Reja",
    reminder: "Eslatma",
    contact: "Kontakt",
    task: "Vazifa",
  };
  const states = {
    open: "Ochiq",
    done: "Bajarilgan",
    saved: "Saqlangan",
    pending: "Kutilmoqda",
    delivered: "Yetkazilgan",
    delivering: "Yetkazilmoqda",
  };
  return organizerResults
    .map(
      (row) => `<article class="organizer-result">
    <small>${labels[row.kind] || esc(row.kind)} #${row.id} · ${esc(states[row.state] || callStates[row.state]?.[0] || row.state)}</small>
    <strong>${esc(row.title)}</strong><p>${esc(row.snippet)}</p>
  </article>`,
    )
    .join("");
}

function organizerPanel() {
  const today = state.today;
  if (!today) return "";
  const counts = today.reminder_counts;
  return `<section class="card organizer-card">
    <div class="card-heading"><div><span class="eyebrow">${esc(today.date)} · ${esc(today.timezone)}</span><h2>Bugun</h2></div>
      <button class="text-button" data-page="reminders">Eslatmalarni boshqarish ${icon("arrow")}</button></div>
    <div class="organizer-content">
      <p>${today.open_plans} ta ochiq reja · bugungacha ${counts.total} ta eslatma · ${counts.overdue} ta kechikkan · ${counts.failed} ta xatoli.</p>
      <div class="organizer-events">${
        today.reminders
          .slice(0, 4)
          .map(
            (row) => `<div>
        <span>${esc(dateTime(row.due))}</span><strong>#${row.id} ${esc(row.title)}</strong>
        ${row.state !== "delivering" ? `<button class="btn secondary small" data-action="snooze-reminder" data-id="${row.id}">15 daqiqa keyin</button>` : "<span>Yetkazilmoqda</span>"}
      </div>`,
          )
          .join("") ||
        '<p class="form-note">Bugun uchun kutilayotgan eslatma yo‘q.</p>'
      }</div>
      ${
        today.tasks.length
          ? `<details><summary>Vazifalar va yozma javoblar · ${today.tasks.length}</summary>
        ${today.tasks.map((row) => `<p>#${row.id} ${esc(row.target)} · ${esc(callStates[row.state]?.[0] || row.state)}</p>`).join("")}</details>`
          : ""
      }
      <form id="organizer-search-form" class="organizer-search">
        <label>Saqlangan ma’lumotlardan qidirish<input name="query" required maxlength="200" value="${esc(organizerQuery)}" placeholder="Kontakt, reja, eslatma yoki vazifa matni"></label>
        <button class="btn secondary" type="submit">Qidirish</button>
      </form>
      <div id="organizer-search-results" aria-live="polite">${organizerSearchResults()}</div>
      <p class="form-note">Telegram buyruqlari · /bugun · /qidir MATN · /keyin ID 15 daqiqa · /bajarildi ID</p>
    </div></section>`;
}

function bindOrganizerForm() {
  const form = $("#organizer-search-form");
  if (!form) return;
  form.elements.namedItem("query").oninput = (event) => {
    organizerQuery = event.target.value;
    organizerResults = null;
    organizerRequest++;
    $("#organizer-search-results").replaceChildren();
  };
  form.onsubmit = (event) => {
    event.preventDefault();
    const query = form.elements.namedItem("query").value.trim();
    if (!query) return;
    const request = ++organizerRequest;
    busy($('[type="submit"]', form), async () => {
      const result = await api("search", { query });
      if (request !== organizerRequest || !state) return;
      organizerResults = result.results;
      const output = $("#organizer-search-results");
      if (output) output.innerHTML = organizerSearchResults();
    });
  };
}

function recordings() {
  return AgentWorkspace.recordings();
}
function chat() {
  return `${sectionHead("Yordamchingizga ayting.", "Savol bering, reja tuzing yoki aniq vaqtga eslatma so‘rang.")}<section class="card chat-card"><div class="chat-top"><span class="agent-symbol small-symbol">✦</span><div><strong>Shaxsiy AI yordamchi</strong><small>${esc(state.agent.text_provider)} · O‘zbekcha suhbat</small></div><div class="chat-toolbar"><a class="icon-button" href="/api/chat-export" download aria-label="Suhbat matnini yuklab olish" title="Oxirgi 40 ta xabarni yuklab olish">↓</a></div><span class="pill muted">Faqat siz uchun</span></div><div id="chat-thread" class="chat-thread"></div><div class="chat-suggestions"><button data-prompt="/bugun">Bugungi kun tartibi</button><button data-prompt="/usage">AI sarfi</button><button data-page="contacts">Kontaktga xabar</button><button data-prompt="Ertaga soat 09:00 da kitob o‘qishimni xabar bilan eslat.">Eslatma yaratish</button><button data-prompt="/reja Ingliz tilini o‘rganish">Reja qo‘shish</button></div><form id="chat-form" class="chat-input"><textarea name="text" rows="1" maxlength="12000" placeholder="Yordamchingizga yozing…" required aria-label="Xabar"></textarea><button class="btn primary send-button" type="submit" aria-label="Xabar yuborish">↑</button></form><p class="chat-disclaimer">AI javobida ism, sana va vaqtlarni tekshiring. Matn tanlangan AI xizmatiga yuboriladi.</p></section>`;
}
function updateThread() {
  const el = $("#chat-thread");
  if (!el) return;
  const stamp = JSON.stringify(state.messages);
  if (stamp === chatStamp && el.children.length) return;
  chatStamp = stamp;
  el.innerHTML = state.messages.length
    ? state.messages
        .map(
          (m) =>
            `<article class="chat-message ${m.role === "user" ? "user" : "assistant"}"><span class="bubble-avatar">${m.role === "user" ? "Q" : "✦"}</span><div><span class="speaker">${m.role === "user" ? "Siz" : "Agent"}</span><div class="bubble">${esc(m.content)}</div></div></article>`,
        )
        .join("")
    : `<div class="chat-welcome"><span class="welcome-symbol">✦</span><h2>Nima yordam beray?</h2><p>Oddiy tilda yozing. Reja va eslatmalarni shu suhbatdan ham boshqarishingiz mumkin.</p></div>`;
  el.scrollTop = el.scrollHeight;
}
function composeContact(id, mode) {
  const contact = state.contacts.find((row) => row.id === id);
  if (!contact) return;
  callDraft = {
    target: contact.reference,
    contact_id: String(id),
    mode,
    language: "uz",
    message: "",
    max_turns: "4",
    duration_seconds: "180",
    timing: "now",
    fallback_to_message: "on",
  };
  go("calls");
  if ($("#selected-recipient"))
    $("#selected-recipient").textContent = contact.name;
  document
    .querySelector('#call-form [name="message"]')
    ?.focus({ preventScroll: true });
}
function saveDrafts() {
  for (const id of [
    "quick-plan-form",
    "quick-reminder-form",
    "library-folder-form",
    "library-search-form",
    "library-note-form",
  ]) {
    const form = document.getElementById(id);
    if (form) formDrafts[id] = Object.fromEntries(new FormData(form));
  }
  const chat = $('#chat-form [name="text"]');
  if (chat) chatDraft = chat.value;
  const form = $("#call-form");
  if (form) callDraft = Object.fromEntries(new FormData(form));
}
function restoreDrafts() {
  for (const [id, draft] of Object.entries(formDrafts)) {
    const form = document.getElementById(id);
    if (form)
      for (const [name, value] of Object.entries(draft)) {
        const field = form.elements.namedItem(name);
        if (field) field.value = value;
      }
  }
  const chat = $('#chat-form [name="text"]');
  if (chat) chat.value = chatDraft;
  const form = $("#call-form");
  if (form && callDraft) {
    form
      .querySelectorAll("input[type=checkbox]")
      .forEach((f) => (f.checked = Object.hasOwn(callDraft, f.name)));
    for (const [key, value] of Object.entries(callDraft)) {
      const field = form.elements.namedItem(key);
      if (field) field.value = value;
    }
    const later = form.elements.namedItem("timing").value === "later";
    $("#call-date-label").hidden = !later;
    form.elements.namedItem("due_at").required = later;
    form.elements.namedItem("mode").onchange?.();
    const selected = state.contacts.find(
      (c) => String(c.id) === callDraft.contact_id,
    );
    if (selected && $("#selected-recipient"))
      $("#selected-recipient").textContent = selected.name;
  }
}
function configureWorkspace() {
  AgentWorkspace.configure(state, {
    esc,
    icon,
    dateTime,
    api,
    refresh,
    render,
    go,
    busy,
    composeContact,
    jsonArray,
    aiUsage,
    finishForm,
  });
}
function render() {
  if (!state) return;
  saveDrafts();
  AgentVoice.cleanup(false);
  configureWorkspace();
  nav();
  header();
  $("#main").classList.toggle(
    "reference-workspace",
    ["contacts", "plans", "reminders", "recordings", "library"].includes(
      current,
    ),
  );
  $("#main").dataset.view = current;
  $("#main")
    .closest(".content")
    .classList.toggle("chat-page", current === "chat");
  $("#main").innerHTML = (
    { home, calls, plans, reminders, contacts, recordings, chat, library }[
      current
    ] || home
  )();
  if (current === "chat") {
    chatStamp = "";
    updateThread();
  }
  if (current === "recordings")
    recordingStamp = JSON.stringify(state.recordings || []);
  bindForms();
  restoreDrafts();
  syncBusyButtons();
  syncChatPending();
  syncAvailability();
}
function networkStatus(message = "") {
  const banner = $("#network-status");
  banner.textContent = message;
  banner.hidden = !message;
}
async function refresh(force = false) {
  if (!csrf) return false;
  if (refreshFlight) {
    if (force) refreshFlight.again = true;
    return refreshFlight.promise;
  }
  const flight = { epoch: sessionEpoch, again: false, promise: null };
  refreshFlight = flight;
  flight.promise = (async () => {
    let requestedForce = force;
    do {
      flight.again = false;
      try {
        const next = await api("state");
        if (flight.epoch !== sessionEpoch) return false;
        const changed = JSON.stringify(state) !== JSON.stringify(next);
        state = next;
        configureWorkspace();
        networkStatus();
        header();
        if ($("#call-budget") && state.agent.call_budget)
          $("#call-budget").textContent = state.agent.call_budget.text;
        if (requestedForce) render();
        else if (current === "calls" && $("#call-history"))
          $("#call-history").innerHTML = callHistory();
        else if (current === "chat") {
          if (!chatPending) updateThread();
          syncChatPending();
        } else if (
          current === "recordings" &&
          !activeOperations.size &&
          !document.activeElement?.matches("input,textarea,select")
        )
          refreshRecordings();
        else if (
          changed &&
          current !== "library" &&
          !activeOperations.size &&
          !document.querySelector("dialog[open],#main details[open]") &&
          !document.activeElement?.matches("input,textarea,select")
        )
          render();
      } catch (error) {
        if (flight.epoch === sessionEpoch && csrf)
          networkStatus(
            "Aloqa uzildi. Tarmoq tiklanganda avtomatik qayta ulanadi.",
          );
        return false;
      }
      requestedForce = flight.again;
    } while (flight.again && flight.epoch === sessionEpoch && csrf);
    return true;
  })();
  try {
    return await flight.promise;
  } finally {
    if (refreshFlight === flight) refreshFlight = null;
  }
}
function refreshRecordings() {
  const stamp = JSON.stringify(state.recordings || []);
  const playing = Array.from(document.querySelectorAll("audio")).some(
    (a) => !a.paused,
  );
  if (stamp !== recordingStamp && !playing) {
    const opened = new Set(
      Array.from(
        document.querySelectorAll(".recording-card details[open]"),
      ).map((d) => d.closest("article").dataset.recordingId),
    );
    const positions = new Map(
      Array.from(document.querySelectorAll(".recording-card audio")).map(
        (a) => [a.getAttribute("src"), a.currentTime],
      ),
    );
    render();
    document.querySelectorAll(".recording-card details").forEach((d) => {
      d.open = opened.has(d.closest("article").dataset.recordingId);
    });
    document.querySelectorAll(".recording-card audio").forEach((a) => {
      const time = positions.get(a.getAttribute("src"));
      if (time > 0) {
        a.preload = "metadata";
        a.addEventListener(
          "loadedmetadata",
          () => {
            a.currentTime = Math.min(time, a.duration || time);
          },
          { once: true },
        );
        a.load();
      }
    });
  }
  const usage = $("#ai-usage");
  if (usage) {
    const holder = document.createElement("template");
    holder.innerHTML = aiUsage();
    usage.replaceWith(holder.content.firstElementChild);
  }
}
function go(page) {
  if (!navigation.some((n) => n[0] === page)) return;
  const menu = $("#navigation-dialog");
  if (menu.open) menu.close();
  current = page;
  if (location.hash !== "#" + page) history.pushState({ page }, "", "#" + page);
  render();
  window.scrollTo(0, 0);
}
function openEditor(kind, id) {
  editorVersion++;
  editorKind = kind;
  let row = {};
  if (id)
    row =
      (kind === "plan" ? state.plans : state.reminders).find(
        (r) => r.id === Number(id),
      ) || {};
  $("#edit-title").textContent =
    kind === "contact"
      ? "Kontakt qo‘shish"
      : id
        ? "Tahrirlash"
        : kind === "plan"
          ? "Yangi reja"
          : "Yangi eslatma";
  let fields = `<input type="hidden" name="id" value="${row.id || ""}">`;
  if (kind === "contact")
    fields += `<label>Kontakt ismi<input name="name" required maxlength="100" placeholder="Masalan: Kursdosh"></label><label>Telegram @username yoki to‘liq raqam<input name="reference" required maxlength="200" placeholder="@username yoki +998…"></label><p class="form-note">Saqlagach, “Tekshirish va ruxsat berish” tugmasini bosing.</p>`;
  else {
    fields += `<label>${kind === "plan" ? "Reja" : "Eslatma"} nomi<input name="title" required maxlength="500" value="${esc(row.title || "")}" placeholder="Masalan: Kitob o‘qish"></label>`;
    if (kind === "plan")
      fields += `<label>Tafsilotlar<textarea name="details" rows="3" maxlength="4000" placeholder="Qisqacha izoh…">${esc(row.details || "")}</textarea></label>`;
    else {
      const local = row.due_local?.slice(0, 16) || "";
      fields += `<label>Qachon? · Toshkent vaqti<input name="due_at" type="datetime-local" required value="${esc(local)}"></label><div class="form-columns"><label>Takrorlanishi<select name="repeat">${[
        ["none", "Bir marta"],
        ["daily", "Har kuni"],
        ["weekly", "Har hafta"],
      ]
        .map(
          ([v, t]) =>
            `<option value="${v}" ${row.repeat === v ? "selected" : ""}>${t}</option>`,
        )
        .join(
          "",
        )}</select></label><label>Qanday eslatilsin?<select name="mode"><option value="message" ${row.mode === "message" ? "selected" : ""}>Telegram xabari</option><option value="call" ${row.mode === "call" ? "selected" : ""}>Menga qo‘ng‘iroq</option></select></label></div>`;
      if (id)
        fields += `<button type="button" class="text-button danger-text" data-action="cancel-reminder" data-id="${row.id}">Eslatmani bekor qilish</button>`;
    }
  }
  $("#edit-fields").innerHTML = fields;
  $("#editor").showModal();
}
async function busy(button, operation) {
  const key = operationKey(button),
    epoch = sessionEpoch;
  if (button?.disabled || activeOperations.has(key)) return;
  const marker = {};
  activeOperations.set(key, marker);
  syncBusyButtons();
  try {
    await operation();
  } catch (error) {
    if (epoch === sessionEpoch && !(error instanceof SessionChanged))
      toast(error.message, true);
  } finally {
    if (activeOperations.get(key) === marker) activeOperations.delete(key);
    syncBusyButtons();
    syncAvailability();
  }
}
function finishForm(form, submitted) {
  const live = document.getElementById(form.id);
  const saved = live
    ? Object.fromEntries(new FormData(live))
    : formDrafts[form.id];
  if (JSON.stringify(saved) === JSON.stringify(submitted)) {
    if (live) live.reset();
    delete formDrafts[form.id];
    return true;
  }
  return false;
}
function syncChatPending() {
  const form = $("#chat-form");
  if (!form) return;
  const button = form.querySelector("[type=submit]");
  button.disabled = chatPending || activeOperations.has("form:chat-form");
  button.setAttribute("aria-busy", String(chatPending));
  const input = form.elements.namedItem("text");
  input.placeholder = chatPending
    ? "Agent javob tayyorlayapti…"
    : "Yordamchingizga yozing…";
}
function bindForms() {
  const callSearch = $("#call-history-search"),
    callFilter = $("#call-history-status");
  if (callSearch)
    callSearch.oninput = () => {
      callHistoryQuery = callSearch.value;
      $("#call-history").innerHTML = callHistory();
    };
  if (callFilter)
    callFilter.onchange = () => {
      callHistoryStatus = callFilter.value;
      $("#call-history").innerHTML = callHistory();
    };
  bindOrganizerForm();
  bindLibraryForms();
  AgentWorkspace.bind();
  const file = $("#contact-file");
  if (file)
    file.onchange = async () => {
      try {
        const selected = file.files[0];
        if (!selected) return;
        if (selected.size > 4 * 1024 * 1024)
          throw Error("JSON 4 MB dan kichik bo‘lsin.");
        const data = JSON.parse(await selected.text());
        const r = await api("import-contacts", { contacts: data });
        toast(`${r.imported} ta kontakt olindi. Jami ${r.total}.`);
        await refresh(true);
      } catch (e) {
        toast(e.message, true);
      }
    };
  const callForm = $("#call-form");
  if (callForm) {
    bindVoiceForm(callForm);
    AgentContacts.bind(callForm.elements.namedItem("target"), state.contacts);
    callForm.elements.namedItem("message").onblur = () =>
      AgentCallIntent.normalize(callForm);
    $('[name="timing"]', callForm).onchange = (e) => {
      const later = e.target.value === "later";
      $("#call-date-label").hidden = !later;
      $('[name="due_at"]', callForm).required = later;
    };
    callForm.onsubmit = (e) => {
      e.preventDefault();
      busy($('[type="submit"]', callForm), async () => {
        AgentCallIntent.normalize(callForm);
        const d = Object.fromEntries(new FormData(callForm));
        const result = await api("call", {
          contact_id: d.contact_id ? Number(d.contact_id) : null,
          target: d.target,
          message: d.message,
          mode: d.mode,
          language: d.language,
          max_turns: Number(d.max_turns),
          duration_seconds: Number(d.duration_seconds),
          audio_id: d.mode === "voice" ? d.audio_id : null,
          delivery:
            d.mode === "voice"
              ? d.delivery
              : d.mode === "text"
                ? "message"
                : "call",
          fallback_to_message:
            d.mode !== "text" && d.fallback_to_message === "on",
          collect_reply:
            d.mode === "voice" &&
            d.delivery === "call" &&
            d.collect_reply === "on",
          due_at: d.timing === "later" ? d.due_at : null,
        });
        toast(
          d.timing === "later"
            ? "Qo‘ng‘iroq belgilangan vaqtga saqlandi."
            : "Vazifa navbatga qo‘yildi.",
        );
        const activeForm = $("#call-form");
        const draft = activeForm
          ? Object.fromEntries(new FormData(activeForm))
          : callDraft;
        if (JSON.stringify(draft) === JSON.stringify(d)) {
          callDraft = null;
          if (activeForm) {
            activeForm.reset();
            activeForm.elements.namedItem("mode").onchange?.();
            $("#call-date-label", activeForm).hidden = true;
            activeForm.elements.namedItem("due_at").required = false;
            $("#selected-recipient", activeForm).textContent = "";
          }
        }
        await refresh();
        if (result.id)
          $("#call-history")?.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
      });
    };
  }
  const chatForm = $("#chat-form");
  if (chatForm) {
    chatForm.onsubmit = (e) => {
      e.preventDefault();
      const text = $('[name="text"]', chatForm).value.trim();
      if (!text || chatPending) return;
      busy($('[type="submit"]', chatForm), async () => {
        const epoch = sessionEpoch;
        chatPending = true;
        syncChatPending();
        try {
          const pending = document.createElement("article");
          pending.className = "chat-message user";
          pending.innerHTML = `<span class="bubble-avatar">Q</span><div><span class="speaker">Siz</span><div class="bubble">${esc(text)}</div></div>`;
          $("#chat-thread").append(pending);
          $("#chat-thread").scrollTop = $("#chat-thread").scrollHeight;
          $('[name="text"]', chatForm).value = "";
          chatDraft = "";
          $('[name="text"]', chatForm).placeholder =
            "Agent javob tayyorlayapti…";
          await api("chat", { text });
        } catch (error) {
          if (epoch === sessionEpoch) {
            const input = $("#chat-form [name=text]");
            if (input && !input.value.trim()) input.value = text;
            else if (!input && !chatDraft.trim()) chatDraft = text;
          }
          throw error;
        } finally {
          if (epoch === sessionEpoch) {
            chatPending = false;
            syncChatPending();
            await refresh();
            updateThread();
          }
        }
      });
    };
    $('[name="text"]', chatForm).onkeydown = (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        chatForm.requestSubmit();
      }
    };
  }
}
document.addEventListener("click", (event) => {
  const page = event.target.closest("[data-page]");
  if (page) {
    go(page.dataset.page);
    return;
  }
  const suggestion = event.target.closest("[data-prompt]");
  if (suggestion) {
    $('[name="text"]', $("#chat-form")).value = suggestion.dataset.prompt;
    $('[name="text"]', $("#chat-form")).focus();
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action,
    id = Number(button.dataset.id);
  if (action === "open-navigation") {
    $("#navigation-dialog").showModal();
    return;
  }
  if (action.startsWith("new-")) {
    openEditor(action.slice(4));
    return;
  }
  if (action.startsWith("edit-")) {
    openEditor(action.slice(5), id);
    return;
  }
  busy(button, async () => {
    if (action === "library-disconnect") {
      await api(action, {});
      toast("Papka uzildi; asl fayllar saqlandi.");
      await refresh(true);
      return;
    }
    if (action === "backup") {
      const r = await api("backup", {});
      const box = $("#backup-result");
      if (box) {
        const link = document.createElement("a");
        link.href = r.url;
        link.download = r.filename;
        link.textContent = "Zaxirani yuklab olish";
        box.replaceChildren(link);
      }
      return;
    }
    if (action === "snooze-reminder") {
      await api(action, { id, minutes: 15 });
      toast("15 daqiqadan keyin xabar bilan eslatiladi.");
      await refresh(true);
      return;
    }
    if (action === "retry-recording") {
      await api("retry-recording", { id: button.dataset.recordingId });
      toast("Ovoz yuborish navbatiga qo‘yildi.");
      await refresh(true);
      return;
    }
    if (action === "sync-contacts") {
      const r = await api("sync-contacts", {});
      toast(`${r.imported} ta yangi kontakt olindi. Jami ${r.total}.`);
      await refresh(true);
      return;
    }
    if (action === "preview") {
      const previewForm = $("#call-form");
      AgentCallIntent.normalize(previewForm);
      const message = $('[name="message"]', previewForm).value;
      const result = await api("preview", {
        message,
        language: $('[name="language"]', $("#call-form")).value,
        mode: $('[name="mode"]', $("#call-form")).value,
      });
      if (!previewForm.isConnected) return;
      $("#preview-player", previewForm).src = result.url;
      $("#preview-player", previewForm).hidden = false;
      return;
    }
    if (action === "verify-contact" || action === "revoke-contact") {
      await api("verify-contact", { id, allow: action === "verify-contact" });
      toast(
        action === "verify-contact"
          ? "Kontakt tekshirildi va ruxsat berildi."
          : "Qo‘ng‘iroq ruxsati olib tashlandi.",
      );
    } else {
      await api(action, id ? { id } : {});
      toast(
        {
          start: "Agent ishga tushyapti.",
          stop: "Agent to‘xtatildi.",
          "call-owner": "Sizga qo‘ng‘iroq boshlanyapti.",
          hangup: "Qo‘ng‘iroq to‘xtatildi.",
          "complete-plan": "Reja bajarildi deb belgilandi.",
          "cancel-reminder": "Eslatma bekor qilindi.",
          "cancel-call": "Qo‘ng‘iroq bekor qilindi.",
          "delete-contact": "Kontakt o‘chirildi.",
        }[action] || "Saqlandi.",
      );
    }
    if (action === "cancel-reminder" && $("#editor").open) $("#editor").close();
    await refresh(true);
  });
});
$("#edit-form").onsubmit = (event) => {
  event.preventDefault();
  busy($('[type="submit"]', $("#edit-form")), async () => {
    const version = editorVersion,
      kind = editorKind;
    const data = Object.fromEntries(new FormData($("#edit-form")));
    await api(kind, data);
    if (version === editorVersion) $("#editor").close();
    toast("Saqlandi.");
    await refresh(true);
  });
};
document
  .querySelectorAll(".close-dialog")
  .forEach((b) =>
    b.addEventListener("click", () => b.closest("dialog").close()),
  );
$("#login-form").onsubmit = async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  await busy($('[type="submit"]', $("#login-form")), async () => {
    try {
      const r = await api("login", {
        password: $('[name="password"]', $("#login-form")).value,
        remember: $('[name="remember"]', $("#login-form")).checked,
      });
      csrf = r.csrf;
      if (!(await refresh(true)))
        throw Error("Panel ma’lumotlari olinmadi. Qayta urinib ko‘ring.");
      $("#login-form").reset();
      $("#login").hidden = true;
      $("#workspace").hidden = false;
      window.scrollTo(0, 0);
    } catch (e) {
      $("#login-error").textContent = e.message;
    }
  });
};
$("#logout").onclick = async () => {
  try {
    await api("logout", {});
  } finally {
    showLogin();
  }
};
let connectingSession = false;
async function connectSession() {
  if (connectingSession || document.hidden) return;
  connectingSession = true;
  try {
    const session = await api("session");
    networkStatus();
    if (session.authenticated) {
      csrf = session.csrf;
      if (await refresh(true)) {
        $("#login").hidden = true;
        $("#workspace").hidden = false;
      }
    } else if (csrf) showLogin();
  } catch {
    networkStatus(
      "Server bilan aloqa yo‘q. Avtomatik qayta ulanish kutilmoqda.",
    );
  } finally {
    connectingSession = false;
  }
}
function reconnectPanel() {
  if (document.hidden) return;
  if (csrf && state) refresh();
  else connectSession();
}
$("#toggle-password").onclick = () => {
  const input = $('#login-form [name="password"]');
  input.type = input.type === "password" ? "text" : "password";
  $("#toggle-password").textContent =
    input.type === "password" ? "Ko‘rsatish" : "Yashirish";
};
window.addEventListener("online", reconnectPanel);
window.addEventListener("popstate", () => {
  const page = location.hash.slice(1) || "home";
  if (navigation.some(([id]) => id === page)) {
    current = page;
    if (state) render();
  }
});
document.addEventListener("visibilitychange", reconnectPanel);
setInterval(reconnectPanel, 5000);
connectSession();
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});

$("#account-button").onclick = () => $("#account-dialog").showModal();
$("#close-account").onclick = () => $("#account-dialog").close();
$("#account-logout").onclick = async () => {
  $("#account-dialog").close();
  try {
    await api("logout", {});
  } finally {
    showLogin();
  }
};
$("#account-shutdown").onclick = async () => {
  try {
    await api("shutdown", {});
    $("#account-dialog").close();
    showLogin();
    $("#login-error").textContent =
      "Panel yopildi. Qayta ochish uchun open-panel.cmd ni bosing.";
  } catch (e) {
    toast(e.message, true);
  }
};

function bindVoiceForm(form) {
  const epoch = sessionEpoch;
  AgentVoice.bind(form, {
    csrf: () => csrf,
    saved: (asset) => {
      if (epoch === sessionEpoch && state)
        state.voice_assets = [asset, ...(state.voice_assets || [])];
    },
  });
  const toggle = () => {
    const voice = form.elements.namedItem("mode").value === "voice";
    const written = form.elements.namedItem("mode").value === "text";
    $("#message-fallback-label", form).hidden =
      written ||
      (voice && form.elements.namedItem("delivery").value === "message");
    const note = $("#call-intent-note", form);
    if (note)
      note.textContent = written
        ? "Matn siz yozgan tilda yetkaziladi. Kontakt shu xabarga Reply qilsa, yozma javobini olasiz."
        : "Savol bo‘lsa, agent javobni kutadi. Faqat yetkazish kerak bo‘lsa matnda “javob kutma” deb yozing.";
    form.elements.namedItem("duration_seconds").closest("label").hidden =
      written;
    const recipient = form.elements.namedItem("target").closest("label");
    recipient.firstChild.textContent = written
      ? "Kimga xabar yuboramiz?"
      : "Kimga qo‘ng‘iroq qilamiz?";
    form.elements.namedItem("timing").options[0].textContent = written
      ? "Hozir xabar yuborish"
      : "Hozir qo‘ng‘iroq qilish";
    form.querySelector(".call-advanced").hidden = written;
    if (!voice) AgentVoice.cancel();
    $("#voice-fields", form).hidden = !voice;
    form.elements.namedItem("audio_id").required = voice;
    form.elements.namedItem("message").required = !voice;
    form.elements.namedItem("message").closest("label").hidden = voice;
    form.elements.namedItem("max_turns").closest("label").hidden =
      voice || written;
    $(".voice-preview", form).hidden = voice || written;
    if (voice || written) {
      $("#preview-player", form).pause();
      $("#preview-player", form).hidden = true;
    }
    form.elements.namedItem("collect_reply").disabled =
      !voice || form.elements.namedItem("delivery").value !== "call";
  };
  form.elements.namedItem("mode").onchange = toggle;
  form.elements.namedItem("delivery").onchange = toggle;
  toggle();
}
function bindLibraryForms() {
  const folder = $("#library-folder-form");
  if (folder)
    folder.onsubmit = (e) => {
      e.preventDefault();
      busy($('[type="submit"]', folder), async () => {
        const r = await api("library-index", {
          folder: folder.elements.namedItem("folder").value,
        });
        toast(`${r.files} hujjat tayyor. ${r.skipped} fayl o‘tkazildi.`);
        await refresh(true);
      });
    };
  const search = $("#library-search-form");
  if (search)
    search.onsubmit = (e) => {
      e.preventDefault();
      busy($('[type="submit"]', search), async () => {
        const r = await api("library-search", {
          query: search.elements.namedItem("query").value,
        });
        const out = $("#library-results");
        if (out)
          out.innerHTML = r.results.length
            ? r.results
                .map(
                  (row) =>
                    `<article class="document-result"><strong>${esc(row.title)}</strong><small>${esc(row.source)}</small><p>${esc(row.snippet)}</p></article>`,
                )
                .join("")
            : "<p>Mos parcha topilmadi. Boshqa kalit so‘z kiriting.</p>";
      });
    };
  const note = $("#library-note-form");
  if (note)
    note.onsubmit = (e) => {
      e.preventDefault();
      busy($('[type="submit"]', note), async () => {
        const submitted = Object.fromEntries(new FormData(note));
        await api("library-note", submitted);
        finishForm(note, submitted);
        toast("Shaxsiy qayd saqlandi.");
        await refresh(true);
      });
    };
}
