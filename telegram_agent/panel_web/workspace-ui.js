"use strict";
window.AgentWorkspace = (() => {
  let state, ui;
  const filters = {
    contacts: { query: "", tab: "all", page: 1, sort: "name" },
    plans: { query: "", tab: "open" },
    reminders: { query: "", tab: "active" },
    recordings: { query: "", tab: "all" },
    library: { query: "", tab: "all" },
  };
  let selectedRecording = "",
    documentRequest = 0;
  const box =
    "rounded-xl bg-surface-container-lowest shadow-sm border border-outline-variant/15";
  const small = "font-label-sm text-label-sm text-outline";
  const heading =
    "font-headline-xl text-headline-xl font-semibold tracking-tight text-on-surface";
  function escape(value) {
    return ui.esc(value);
  }
  function day(value) {
    if (!value) return "";
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: state.agent.timezone || "Asia/Tashkent",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date(value));
  }
  function icon(name) {
    return ui.icon(name);
  }
  function header(eyebrow, title, subtitle, action = "") {
    return `<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-space-base mb-space-xl"><div class="flex flex-col gap-space-xxs max-w-2xl"><span class="font-label-sm text-label-sm uppercase tracking-wider text-primary-container font-semibold">${escape(eyebrow)}</span><h1 class="${heading}">${escape(title)}</h1><p class="font-body-md text-body-md text-on-surface-variant">${escape(subtitle)}</p></div><div class="flex items-center gap-space-sm flex-wrap">${action}</div></div>`;
  }
  function metrics(items) {
    return `<div class="reference-metrics grid grid-cols-2 xl:grid-cols-4 gap-space-md mb-space-xl">${items.map(([label, value, note, name]) => `<div class="${box} p-space-base"><div class="flex items-center justify-between mb-space-sm"><span class="font-label-sm text-label-sm text-on-surface-variant">${escape(label)}</span><span class="text-primary-container">${icon(name)}</span></div><strong class="text-[28px] leading-tight font-semibold text-on-surface">${escape(value)}</strong><p class="${small} mt-space-xs">${escape(note)}</p></div>`).join("")}</div>`;
  }
  function tabs(page, items) {
    const selected = filters[page].tab;
    return `<div class="flex flex-wrap items-center gap-space-xxs" role="tablist">${items.map(([value, label, count]) => `<button type="button" role="tab" aria-selected="${selected === value}" data-ref-tab="${page}" data-value="${value}" class="px-space-md py-space-sm rounded-lg font-label-md text-label-md ${selected === value ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant hover:bg-surface-container"}">${escape(label)}${count !== undefined ? ` <span class="ml-space-xxs">${count}</span>` : ""}</button>`).join("")}</div>`;
  }
  function empty(text) {
    return `<div class="p-10 text-center text-outline font-body-md text-body-md">${escape(text)}</div>`;
  }
  function contactStats() {
    const activity = state.workspace?.contact_activity || {};
    const week = Date.now() - 7 * 86400000;
    const allowed = state.contacts.filter(
      (contact) => contact.call_allowed,
    ).length;
    const recent = state.contacts.filter(
      (contact) =>
        Date.parse(activity[contact.telegram_id]?.last || "") >= week,
    ).length;
    return {
      total: state.contacts.length,
      allowed,
      pending: state.contacts.length - allowed,
      recent,
    };
  }
  function contactList() {
    const filter = filters.contacts,
      activity = state.workspace?.contact_activity || {};
    let rows = state.contacts.filter((contact) =>
      AgentContacts.matches(contact, filter.query),
    );
    if (filter.tab === "allowed")
      rows = rows.filter((contact) => contact.call_allowed);
    if (filter.tab === "pending")
      rows = rows.filter((contact) => !contact.call_allowed);
    if (filter.tab === "recent")
      rows = rows.filter(
        (contact) =>
          Date.parse(activity[contact.telegram_id]?.last || "") >=
          Date.now() - 7 * 86400000,
      );
    rows.sort((a, b) =>
      filter.sort === "activity"
        ? (activity[b.telegram_id]?.count || 0) -
          (activity[a.telegram_id]?.count || 0)
        : AgentContacts.normalize(a.name).localeCompare(
            AgentContacts.normalize(b.name),
            "uz",
          ),
    );
    const pages = Math.max(1, Math.ceil(rows.length / 9));
    filter.page = Math.min(filter.page, pages);
    const selected = rows.slice((filter.page - 1) * 9, filter.page * 9);
    return `<p class="${small} my-space-base" id="contact-match-count">Jami ${state.contacts.length} ta kontakt · qidiruvda ${rows.length} ta</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-space-base">${
        selected
          .map((contact) => {
            const last = activity[contact.telegram_id];
            const initials = contact.name
              .normalize("NFKC")
              .split(/\s+/)
              .filter(Boolean)
              .slice(0, 2)
              .map((part) => Array.from(part)[0])
              .join("")
              .toUpperCase();
            return `<article class="${box} p-space-base flex flex-col gap-space-sm"><div class="flex justify-between items-center"><span class="w-11 h-11 rounded-xl bg-surface-container-low text-primary flex items-center justify-center font-semibold">${escape(initials)}</span><button type="button" class="row-more" data-action="delete-contact" data-id="${contact.id}" aria-label="Kontaktni o‘chirish">×</button></div><h2 class="font-headline-sm text-headline-sm text-on-surface break-words">${escape(contact.name)}</h2><p class="text-primary font-body-sm text-body-sm break-all">${escape(contact.reference)}</p><span class="font-label-sm text-label-sm ${contact.call_allowed ? "text-secondary" : "text-tertiary"}">${contact.call_allowed ? "✓ Vazifa yuborishga ruxsat berilgan" : "Tekshirish kerak"}</span>${contact.telegram_id ? `<span class="${small}">TG ID #${contact.telegram_id}</span>` : ""}<p class="${small} min-h-[18px]">${last ? `Oxirgi vazifa · ${escape(ui.dateTime(last.last))}` : "Hali vazifa topshirilmagan"}</p><div class="flex gap-space-sm mt-auto"><button type="button" class="btn primary flex-1" data-contact-compose="${contact.id}" data-mode="ask">${icon("calls")} Qo‘ng‘iroq</button><button type="button" class="btn secondary" data-contact-compose="${contact.id}" data-mode="text" aria-label="Telegram xabari yuborish">${icon("chat")}</button></div>${!contact.call_allowed ? `<button class="text-button" data-action="verify-contact" data-id="${contact.id}">Tekshirish va ruxsat berish →</button>` : `<button class="text-button danger-text" data-action="revoke-contact" data-id="${contact.id}">Ruxsatni olib tashlash</button>`}</article>`;
          })
          .join("") ||
        empty(
          filter.query
            ? "Mos kontakt topilmadi. Ism, username yoki raqamni qisqartirib yozing."
            : "Bu filtrda kontaktlar yo‘q.",
        )
      }</div>
      <div class="flex items-center justify-between mt-space-lg gap-space-sm"><span class="${small}">${rows.length ? (filter.page - 1) * 9 + 1 : 0}–${Math.min(filter.page * 9, rows.length)} / ${rows.length}</span><div class="flex items-center gap-space-sm"><button class="btn secondary small" data-ref-page="${filter.page - 1}" ${filter.page === 1 ? "disabled" : ""}>←</button><span class="${small}">${filter.page} / ${pages}</span><button class="btn secondary small" data-ref-page="${filter.page + 1}" ${filter.page === pages ? "disabled" : ""}>→</button></div></div>`;
  }
  function contacts() {
    const counts = contactStats();
    return (
      header(
        "TELEGRAM SINXRONIZATSIYA · TELEGRAM MTPROTO",
        "Kerakli insonlar, bir joyda.",
        "Telegram kontaktlaringiz, vazifa yuborish va ruxsat sozlamalari.",
        `<button class="btn secondary" data-action="sync-contacts">${icon("contacts")} Kontaktlarni yangilash</button><button class="btn primary" data-action="new-contact">${icon("plus")} Kontakt qo‘shish</button>`,
      ) +
      metrics([
        [
          "Jami kontaktlar",
          counts.total,
          "Saqlangan Telegram kontaktlari",
          "contacts",
        ],
        [
          "Ruxsat berilgan",
          counts.allowed,
          "Vazifa topshirish uchun tayyor",
          "check",
        ],
        [
          "Tekshirish kerak",
          counts.pending,
          "Kontaktni tasdiqlashingiz mumkin",
          "clock",
        ],
        [
          "Faol muloqotda",
          counts.recent,
          "Oxirgi 7 kun ichida vazifa bo‘lgan",
          "calls",
        ],
      ]) +
      `<section class="${box} p-space-base mb-space-base"><div class="flex flex-col lg:flex-row lg:items-center gap-space-base justify-between"><label class="m-0 flex-1 relative"><input id="contact-search" data-ref-search="contacts" type="search" value="${escape(filters.contacts.query)}" placeholder="Ism, username yoki telefon raqami" autocomplete="off" class="m-0"></label><select data-ref-sort="contacts" aria-label="Kontaktlarni saralash" class="m-0 lg:w-[210px]"><option value="name" ${filters.contacts.sort === "name" ? "selected" : ""}>Ism bo‘yicha</option><option value="activity" ${filters.contacts.sort === "activity" ? "selected" : ""}>Eng faol kontaktlar</option></select></div><div class="mt-space-base">${tabs(
        "contacts",
        [
          ["all", "Barchasi", counts.total],
          ["allowed", "Ruxsat berilgan", counts.allowed],
          ["pending", "Tekshirish kerak", counts.pending],
          ["recent", "Yaqinda", counts.recent],
        ],
      )}</div></section><div id="ref-contact-results">${contactList()}</div><label class="btn secondary mt-space-lg">Kontakt JSON import<input id="contact-file" type="file" accept=".json,application/json" hidden></label>`
    );
  }
  function planRows() {
    const filter = filters.plans;
    let rows =
      filter.tab === "done"
        ? state.workspace?.completed_plans || []
        : state.plans;
    if (filter.tab === "today")
      rows = rows.filter((row) => day(row.created) === day(Date.now()));
    rows = rows.filter((row) =>
      AgentContacts.matches(
        { name: row.title, reference: row.details },
        filter.query,
      ),
    );
    return (
      rows
        .map(
          (row) =>
            `<article class="p-space-base border-b border-outline-variant/15 flex items-start gap-space-md"><button class="task-check mt-1" ${row.status === "done" ? "disabled" : 'data-action="complete-plan" data-id="' + row.id + '"'} aria-label="Bajarildi"><span class="${row.status === "done" ? "text-secondary" : ""}">${icon("check")}</span></button><div class="flex-1 min-w-0"><h3 class="font-headline-sm text-headline-sm text-on-surface ${row.status === "done" ? "line-through opacity-60" : ""}">${escape(row.title)}</h3>${row.details ? `<p class="font-body-sm text-body-sm text-on-surface-variant mt-space-xs whitespace-pre-wrap break-words">${escape(row.details)}</p>` : ""}<span class="${small} mt-space-sm block">${escape(ui.dateTime(row.created))}</span></div>${row.status !== "done" ? `<button class="row-more" data-action="edit-plan" data-id="${row.id}" aria-label="Tahrirlash">⋯</button>` : ""}</article>`,
        )
        .join("") || empty("Bu ro‘yxatda reja topilmadi.")
    );
  }
  function plans() {
    const counts = state.workspace?.plan_counts || {},
      open = counts.open || state.plans.length,
      done = counts.done || 0,
      total = open + done;
    return (
      header(
        "REJALAR VA KUNLIK TARTIB",
        "Kichik qadamlar. Katta rejalar.",
        "Vazifalaringizni saqlang, bajaring va natijalarni kuzating.",
        `<button class="btn primary" data-action="new-plan">${icon("plus")} Yangi reja</button>`,
      ) +
      metrics([
        ["Jami rejalar", total, "Ochiq va bajarilgan rejalar", "plans"],
        ["Ochiq rejalar", open, "Bajarilishi kutilmoqda", "clock"],
        ["Yakunlangan", done, "Bajarilgan deb belgilangan", "check"],
        [
          "Faol eslatmalar",
          state.reminders.length,
          "Vaqti belgilangan eslatmalar",
          "reminders",
        ],
      ]) +
      `<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-space-lg"><section class="${box}"><div class="p-space-base flex flex-col sm:flex-row gap-space-base justify-between border-b border-outline-variant/15">${tabs(
        "plans",
        [
          ["open", "Ochiq", open],
          ["today", "Bugun qo‘shilgan"],
          ["done", "Yakunlangan", done],
        ],
      )}<input type="search" data-ref-search="plans" class="m-0 sm:w-[210px]" value="${escape(filters.plans.query)}" placeholder="Rejadan qidirish"></div><div id="ref-plan-results">${planRows()}</div></section><aside class="flex flex-col gap-space-base"><section class="${box} p-space-base"><h2 class="font-headline-md text-headline-md mb-space-base">Tezkor reja qo‘shish</h2><form id="quick-plan-form"><label>Reja nomi<input name="title" required maxlength="500" placeholder="Nima qilmoqchisiz?"></label><label>Izoh<textarea name="details" rows="3" maxlength="4000" placeholder="Kerakli tafsilotlar"></textarea></label><button class="btn primary wide" type="submit">${icon("plus")} Rejani qo‘shish</button></form></section><section class="${box} p-space-base"><h2 class="font-headline-sm text-headline-sm">Bajarilish holati</h2><strong class="text-[32px] text-primary block my-space-sm">${total ? Math.round((done / total) * 100) : 0}%</strong><div class="h-2 rounded-full bg-surface-container overflow-hidden"><div class="plan-progress h-full bg-primary-container" data-progress="${total ? Math.round((done / total) * 100) : 0}"></div></div><p class="${small} mt-space-base">${total} ta rejadan ${done} tasi bajarilgan.</p><button class="text-button mt-space-sm" data-page="chat" data-ref-prompt="/bugun">Kun tartibini ko‘rish →</button></section></aside></div>`
    );
  }
  function reminderRows() {
    const filter = filters.reminders;
    let rows =
      filter.tab === "history"
        ? state.workspace?.reminder_history || []
        : state.reminders;
    if (filter.tab === "today")
      rows = rows.filter((row) => day(row.due) === day(Date.now()));
    if (filter.tab === "call") rows = rows.filter((row) => row.mode === "call");
    if (filter.tab === "repeat")
      rows = rows.filter((row) => row.repeat !== "none");
    rows = rows.filter((row) =>
      AgentContacts.matches({ name: row.title, reference: "" }, filter.query),
    );
    const repeats = {
      none: "Bir martalik",
      daily: "Har kuni",
      weekly: "Har hafta",
    };
    return (
      rows
        .map(
          (row) =>
            `<article class="p-space-base border-b border-outline-variant/15"><div class="flex items-start gap-space-md"><span class="w-10 h-10 rounded-xl bg-surface-container-low text-primary flex items-center justify-center shrink-0">${icon(row.mode === "call" ? "calls" : "reminders")}</span><div class="flex-1 min-w-0"><div class="flex flex-wrap gap-space-sm items-center"><h3 class="font-headline-sm text-headline-sm text-on-surface">${escape(row.title)}</h3><span class="pill ${row.state === "failed" ? "danger" : row.state === "delivered" ? "success" : "purple"}">${{ pending: "Faol", delivering: "Yetkazilmoqda", failed: "Yetkazilmadi", delivered: "Yetkazildi", cancelled: "Bekor qilingan" }[row.state] || escape(row.state)}</span></div><p class="text-primary font-body-sm text-body-sm mt-space-xs">${escape(ui.dateTime(row.due))}</p><div class="flex flex-wrap gap-space-sm mt-space-sm"><span class="${small}">${repeats[row.repeat]}</span><span class="${small}">· ${row.mode === "call" ? "Xabar va qo‘ng‘iroq" : "Telegram xabari"}</span></div>${row.last_error ? `<p class="text-error font-body-sm text-body-sm mt-space-sm">${escape(row.last_error)}</p>` : ""}</div></div><div class="flex flex-wrap gap-space-sm mt-space-base sm:ml-[52px]">${["pending", "failed"].includes(row.state) ? `<button class="btn secondary small" data-action="snooze-reminder" data-id="${row.id}">15 daqiqa keyin</button>` : ""}${["pending", "failed"].includes(row.state) ? `<button class="btn secondary small" data-action="edit-reminder" data-id="${row.id}">Tahrirlash</button><button class="text-button danger-text" data-action="cancel-reminder" data-id="${row.id}">Bekor qilish</button>` : ""}${row.state === "failed" ? `<button class="btn secondary small" data-action="retry-reminder" data-id="${row.id}">Xabar bilan qayta eslatish</button>` : ""}</div></article>`,
        )
        .join("") || empty("Bu filtrda eslatma topilmadi.")
    );
  }
  function reminders() {
    const count = state.workspace?.reminder_counts || {},
      active = state.reminders.length,
      history = (count.delivered || 0) + (count.cancelled || 0);
    return (
      header(
        "YODINGIZDAN KO‘TARILMASIN · VAQT BOSHQARUVI",
        "Muhim ishlar yodingizda.",
        "Bir martalik, kunlik va haftalik Telegram eslatmalari.",
        `<span class="text-label-sm text-outline">${escape(state.agent.timezone)}</span><button class="btn primary" data-action="new-reminder">${icon("plus")} Yangi eslatma</button>`,
      ) +
      metrics([
        [
          "Jami eslatmalar",
          Object.values(count).reduce((a, b) => a + b, 0),
          "Barcha saqlangan eslatmalar",
          "reminders",
        ],
        ["Faol", active, "Navbatdagi yoki e’tibor talab qiladigan", "clock"],
        [
          "Ovozli qo‘ng‘iroq",
          state.reminders.filter((row) => row.mode === "call").length,
          "Qo‘ng‘iroq bilan eslatish",
          "calls",
        ],
        [
          "Takroriy",
          state.reminders.filter((row) => row.repeat !== "none").length,
          "Kunlik va haftalik jadval",
          "plans",
        ],
      ]) +
      `<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-space-lg"><section class="${box}"><div class="p-space-base border-b border-outline-variant/15">${tabs(
        "reminders",
        [
          ["active", "Faol", active],
          ["today", "Bugun"],
          ["call", "Qo‘ng‘iroq"],
          ["repeat", "Takroriy"],
          ["history", "Tarix", history],
        ],
      )}<input class="mt-space-base" type="search" data-ref-search="reminders" value="${escape(filters.reminders.query)}" placeholder="Eslatmadan qidirish"></div><div id="ref-reminder-results">${reminderRows()}</div></section><aside class="${box} p-space-base self-start"><h2 class="font-headline-md text-headline-md mb-space-base">Tezkor eslatma yaratish</h2><form id="quick-reminder-form"><label>Eslatma matni<input name="title" required maxlength="500" placeholder="Nimani eslatay?"></label><label>Sana va vaqt<input name="due_at" type="datetime-local" required></label><label>Ogohlantirish usuli<select name="mode"><option value="message">Telegram xabari</option><option value="call">Xabar va qo‘ng‘iroq</option></select></label><label>Takrorlanish<select name="repeat"><option value="none">Bir martalik</option><option value="daily">Har kuni</option><option value="weekly">Har hafta</option></select></label><button class="btn primary wide" type="submit">${icon("check")} Eslatmani saqlash</button></form></aside></div>`
    );
  }
  function recordingList() {
    const f = filters.recordings;
    const rows = (state.recordings || []).filter(
      (row) =>
        AgentContacts.matches(
          { name: row.label, reference: row.question || "" },
          f.query,
        ) &&
        (f.tab === "all" ||
          (f.tab === "failed" ? row.state === "failed" : row.state === "sent")),
    );
    return (
      rows
        .map(
          (row) =>
            `<article class="${box} p-space-base mb-space-base recording-card" data-recording-id="${escape(row.id)}"><div class="flex items-start justify-between gap-space-sm"><div class="flex gap-space-md min-w-0"><span class="soft-icon">${icon("recordings")}</span><div class="min-w-0"><h2 class="font-headline-sm text-headline-sm break-words">${escape(row.label)}</h2><p class="${small} mt-space-xs">${escape(ui.dateTime(row.created))} · ${Math.round(row.duration || 0)} soniya</p></div></div><span class="pill ${row.state === "sent" ? "success" : row.state === "failed" ? "danger" : "waiting"}">${escape({ capturing: "Yozilyapti", captured: "Tayyorlanyapti", ready: "Navbatda", sending: "Yuborilyapti", sent: "Yuborilgan", failed: "Xato" }[row.state] || row.state)}</span></div>${row.incoming_filename ? `<label class="mt-space-base mb-space-sm">Kontaktning asl ovozi<audio controls preload="none" src="/api/recordings/${escape(row.id)}/incoming"></audio></label>` : ""}${row.filename ? `<details><summary class="text-primary cursor-pointer font-label-sm text-label-sm">To‘liq suhbat audiosi</summary><audio controls preload="none" src="/api/recordings/${escape(row.id)}/audio"></audio></details>` : ""}${row.last_error ? `<p class="text-error text-body-sm mt-space-sm">${escape(row.last_error)}</p>` : ""}<div class="flex flex-wrap gap-space-base mt-space-base"><button class="text-button" data-recording-select="${escape(row.id)}">Xulosa va transkript →</button>${!["capturing", "captured", "sending"].includes(row.state) ? `<button class="text-button" data-action="retry-recording" data-recording-id="${escape(row.id)}">Chatga qayta yuborish</button>` : ""}</div></article>`,
        )
        .join("") || empty("Bu filtrda ovoz yozuvi topilmadi.")
    );
  }
  function recordingDetail() {
    const row =
      (state.recordings || []).find((row) => row.id === selectedRecording) ||
      (state.recordings || [])[0];
    if (!row)
      return empty("Qo‘ng‘iroq yozilgach, tafsilotlar shu yerda ko‘rinadi.");
    selectedRecording = row.id;
    const transcript = ui.jsonArray(row.transcript);
    return `<div class="p-space-base border-b border-outline-variant/15"><span class="text-primary">${icon("recordings")}</span><h2 class="font-headline-md text-headline-md mt-space-sm">Yozuv tafsilotlari</h2><p class="${small} break-all">ID: ${escape(row.id)}</p></div><div class="p-space-base"><h3 class="font-headline-sm text-headline-sm mb-space-sm">${escape(row.label)}</h3>${row.question ? `<p class="text-body-sm text-on-surface-variant whitespace-pre-wrap">Topshiriq: ${escape(row.question)}</p>` : ""}<h3 class="font-headline-sm text-headline-sm mt-space-xl mb-space-sm">Vazifa xulosasi</h3><p class="text-body-md whitespace-pre-wrap">${escape(row.summary || "Tasdiqlangan matnli xulosa mavjud emas. Asl ovozni tinglashingiz mumkin.")}</p><h3 class="font-headline-sm text-headline-sm mt-space-xl mb-space-base">Suhbat transkripti</h3>${transcript.length ? transcript.map((part) => `<div class="mb-space-base"><b class="text-label-sm text-primary">${part.role === "user" ? "Kontakt" : "Agent"}</b><p class="text-body-md whitespace-pre-wrap mt-space-xs">${escape(part.content)}</p></div>`).join("") : `<p class="${small}">Bu yozuv uchun transkript yaratilmagan. Ovoz yozilgani javob mazmuni tasdiqlanganini bildirmaydi.</p>`}</div>`;
  }
  function recordings() {
    const counts = state.workspace?.recording_counts || {},
      total = Object.values(counts).reduce((a, b) => a + b, 0);
    return (
      header(
        "OVOZLI QO‘NG‘IROQLAR ARXIVI",
        "Barcha ovozli yozuvlar va transkriptlar.",
        "Asl audio, topshiriq xulosasi va saqlangan suhbat matni.",
        `<button class="btn primary" data-page="calls">${icon("plus")} Yangi ovozli vazifa</button>`,
      ) +
      metrics([
        ["Jami yozuvlar", total, "Barcha saqlangan yozuvlar", "recordings"],
        [
          "Davomiylik",
          Math.round((state.workspace?.recording_seconds || 0) / 60) + " daq",
          "Barcha yozuvlarning umumiy vaqti",
          "clock",
        ],
        [
          "Telegramga yuborilgan",
          counts.sent || 0,
          "Yetkazish tasdiqlangan",
          "check",
        ],
        [
          "E’tibor kerak",
          counts.failed || 0,
          "Qayta yuborish mumkin",
          "reminders",
        ],
      ]) +
      `<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-space-lg"><section><div class="${box} p-space-base mb-space-base">${tabs(
        "recordings",
        [
          ["all", "Barchasi"],
          ["sent", "Yuborilgan"],
          ["failed", "Xatoli"],
        ],
      )}<input data-ref-search="recordings" type="search" value="${escape(filters.recordings.query)}" placeholder="Kontakt yoki vazifadan qidirish"><p class="${small} mt-space-sm">Oxirgi 30 ta yozuv orasidan qidiriladi.</p></div><div id="ref-recording-results">${recordingList()}</div></section><aside id="recording-detail" class="${box} self-start">${recordingDetail()}</aside></div><details class="mt-space-xl"><summary class="text-primary text-label-md cursor-pointer">AI sarfi va xizmatlar holati</summary>${ui.aiUsage()}</details>`
    );
  }
  function documentList() {
    const f = filters.library;
    const rows = (state.library?.items || []).filter(
      (row) =>
        AgentContacts.matches(
          { name: row.title, reference: row.source },
          f.query,
        ) &&
        (f.tab === "all" || row.kind === f.tab),
    );
    return (
      rows
        .map(
          (row) =>
            `<article class="${box} p-space-base mb-space-base"><div class="flex gap-space-base items-start"><span class="w-12 h-12 bg-surface-container-low text-primary rounded-xl flex items-center justify-center font-label-sm text-label-sm shrink-0">${escape(row.kind === "note" ? "QAYD" : row.title.split(".").pop().slice(0, 5).toUpperCase())}</span><div class="min-w-0 flex-1"><h2 class="font-headline-sm text-headline-sm break-words">${escape(row.title)}</h2><p class="${small} break-all mt-space-xs">${escape(row.source)} · ${row.characters.toLocaleString()} belgi</p><p class="${small} mt-space-xs">${escape(ui.dateTime(row.created))}</p><span class="pill success mt-space-sm">Mahalliy qidiruvga tayyor</span></div></div><div class="mt-space-base flex gap-space-base"><button class="text-button" data-document-open="${row.id}">Matnni ko‘rish →</button><button class="text-button" data-document-search="${escape(row.title)}">Shu mavzuda qidirish</button></div></article>`,
        )
        .join("") ||
      empty("Hujjat topilmadi. Papka ulang yoki shaxsiy qayd qo‘shing.")
    );
  }
  function library() {
    const s = state.library || {};
    return (
      header(
        "SHAXSIY HUJJATLAR VA MAHALLIY QIDIRUV",
        "Barcha hujjatlar va bilimlar bazasi.",
        "Tanlangan papka va shaxsiy qaydlaringiz. Hujjat matni bulutdagi AI xizmatiga yuborilmaydi.",
        `<button class="btn primary" data-local-focus="library-note-form">${icon("plus")} Yangi qayd</button>`,
      ) +
      metrics([
        [
          "Jami hujjatlar",
          (s.files || 0) + (s.notes || 0),
          "Mahalliy qidiruvga tayyor",
          "library",
        ],
        ["Papka fayllari", s.files || 0, "TXT, MD, PDF, DOCX", "plans"],
        [
          "Shaxsiy qaydlar",
          s.notes || 0,
          "O‘zingiz saqlagan ma’lumotlar",
          "chat",
        ],
        [
          "O‘tkazilgan fayllar",
          s.skipped || 0,
          "Format, hajm yoki maxfiy nom sababli",
          "clock",
        ],
      ]) +
      `<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-space-lg"><section><div class="${box} p-space-base mb-space-base">${tabs(
        "library",
        [
          ["all", "Barchasi"],
          ["file", "Hujjatlar"],
          ["note", "Qaydlar"],
        ],
      )}<input data-ref-search="library" type="search" value="${escape(filters.library.query)}" placeholder="Hujjat nomi yoki manbadan qidirish"></div><div id="ref-document-results">${documentList()}</div><details class="${box} p-space-base mt-space-xl" ${s.folder ? "" : "open"}><summary class="font-headline-sm text-headline-sm cursor-pointer">Papka ulash va yangilash</summary><form id="library-folder-form" class="mt-space-base"><label>Kompyuterdagi papkaning to‘liq yo‘li<input name="folder" value="${escape(s.folder || "")}" required maxlength="1000" placeholder="D:\\Hujjatlar"></label><button class="btn primary" type="submit">Papka ulash / yangilash</button></form><p class="${small} mt-space-base">5 MB/fayl, 50 sahifa/PDF, 200 fayl. Skanerlangan PDF uchun OCR yo‘q. Kalit, parol va sessiya nomli fayllar olinmaydi.</p>${s.folder ? '<button class="text-button danger-text mt-space-base" data-action="library-disconnect">Papkani uzish</button>' : ""}</details><section class="${box} p-space-base mt-space-base"><h2 class="font-headline-sm text-headline-sm">Zaxira va yetkazish navbati</h2><p class="text-body-sm text-on-surface-variant my-space-base">Ma’lumotlar va ovozlarni zaxiralash. Telegram sessiyasi va .env fayli kiritilmaydi.</p><button class="btn secondary" data-action="backup">Zaxira tayyorlash</button><div id="backup-result" class="mt-space-sm"></div><p class="${small} mt-space-base">Natijalar navbati: ${state.notifications?.pending || 0} · Xatoli: ${state.notifications?.failed || 0}</p>${state.notifications?.failed ? '<button class="text-button" data-action="retry-notifications">Natijalarni qayta yuborish</button>' : ""}</section></section><aside class="flex flex-col gap-space-base"><section class="${box} p-space-base"><h2 class="font-headline-md text-headline-md mb-space-base">Hujjatdan javob qidiring</h2><form id="library-search-form"><label>Mavzu yoki kalit so‘z<input name="query" required maxlength="500" placeholder="Masalan: dars jadvali"></label><button class="btn primary wide" type="submit">Mahalliy qidirish</button></form><div id="library-results" aria-live="polite"></div></section><section class="${box} p-space-base"><h2 class="font-headline-md text-headline-md mb-space-base">Shaxsiy qayd qo‘shish</h2><form id="library-note-form"><label>Sarlavha<input name="title" required maxlength="500"></label><label>Qayd matni<textarea name="body" rows="5" required maxlength="10000"></textarea></label><button class="btn primary wide" type="submit">Qaydni saqlash</button></form></section></aside></div>`
    );
  }
  function redraw(page) {
    const targets = {
      contacts: ["ref-contact-results", contactList],
      plans: ["ref-plan-results", planRows],
      reminders: ["ref-reminder-results", reminderRows],
      recordings: ["ref-recording-results", recordingList],
      library: ["ref-document-results", documentList],
    };
    const target = targets[page];
    const node = document.getElementById(target[0]);
    if (node) node.innerHTML = target[1]();
  }
  function bind() {
    document.querySelectorAll("[data-ref-search]").forEach(
      (input) =>
        (input.oninput = () => {
          const page = input.dataset.refSearch;
          filters[page].query = input.value;
          if (page === "contacts") filters.contacts.page = 1;
          redraw(page);
        }),
    );
    document.querySelectorAll("[data-ref-sort]").forEach(
      (select) =>
        (select.onchange = () => {
          filters.contacts.sort = select.value;
          filters.contacts.page = 1;
          redraw("contacts");
        }),
    );
    document
      .querySelectorAll("[data-progress]")
      .forEach((node) => (node.style.width = node.dataset.progress + "%"));
    const plan = document.getElementById("quick-plan-form");
    if (plan)
      plan.onsubmit = async (event) => {
        event.preventDefault();
        await ui.busy(plan.querySelector('[type="submit"]'), async () => {
          const submitted = Object.fromEntries(new FormData(plan));
          await ui.api("plan", submitted);
          ui.finishForm(plan, submitted);
          await ui.refresh(true);
        });
      };
    const reminder = document.getElementById("quick-reminder-form");
    if (reminder)
      reminder.onsubmit = async (event) => {
        event.preventDefault();
        await ui.busy(reminder.querySelector('[type="submit"]'), async () => {
          const submitted = Object.fromEntries(new FormData(reminder));
          await ui.api("reminder", submitted);
          ui.finishForm(reminder, submitted);
          await ui.refresh(true);
        });
      };
  }
  document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-ref-tab]");
    if (tab) {
      filters[tab.dataset.refTab].tab = tab.dataset.value;
      if (tab.dataset.refTab === "contacts") filters.contacts.page = 1;
      ui.render();
      return;
    }
    const page = event.target.closest("[data-ref-page]");
    if (page && !page.disabled) {
      filters.contacts.page = Number(page.dataset.refPage);
      redraw("contacts");
      return;
    }
    const compose = event.target.closest("[data-contact-compose]");
    if (compose) {
      ui.composeContact(
        Number(compose.dataset.contactCompose),
        compose.dataset.mode,
      );
      return;
    }
    const recording = event.target.closest("[data-recording-select]");
    if (recording) {
      selectedRecording = recording.dataset.recordingSelect;
      const detail = document.getElementById("recording-detail");
      detail.innerHTML = recordingDetail();
      detail.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const focus = event.target.closest("[data-local-focus]");
    if (focus) {
      const form = document.getElementById(focus.dataset.localFocus);
      form?.scrollIntoView({ behavior: "smooth", block: "center" });
      form?.querySelector("input")?.focus({ preventScroll: true });
      return;
    }
    const search = event.target.closest("[data-document-search]");
    if (search) {
      const input = document.querySelector("#library-search-form [name=query]");
      if (input) {
        input.value = search.dataset.documentSearch;
        input.form.requestSubmit();
        input.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }
    const documentButton = event.target.closest("[data-document-open]");
    if (documentButton) {
      const request = ++documentRequest;
      ui.busy(documentButton, async () => {
        const result = await ui.api("library-document", {
          id: documentButton.dataset.documentOpen,
        });
        if (request !== documentRequest || !state) return;
        document.getElementById("document-title").textContent = result.title;
        document.getElementById("document-body").textContent = result.body;
        document.getElementById("document-viewer").showModal();
      });
      return;
    }
    const prompt = event.target.closest("[data-ref-prompt]");
    if (prompt) {
      ui.go("chat");
      const input = document.querySelector("#chat-form [name=text]");
      if (input) {
        input.value = prompt.dataset.refPrompt;
        input.focus();
      }
    }
  });
  return {
    configure(value, helpers) {
      state = value;
      ui = helpers;
    },
    contacts,
    plans,
    reminders,
    recordings,
    library,
    bind,
    reset() {
      state = null;
      documentRequest++;
      selectedRecording = "";
      for (const filter of Object.values(filters)) {
        filter.query = "";
        filter.page = 1;
        filter.tab =
          filter === filters.plans
            ? "open"
            : filter === filters.reminders
              ? "active"
              : "all";
      }
    },
  };
})();
