"use strict";
window.AgentVoice = (() => {
  let recorder = null,
    stream = null,
    timer = null,
    blob = null,
    localUrl = "",
    parts = [],
    bytes = 0,
    form = null,
    callbacks = null,
    generation = 0,
    starting = false,
    finishing = false,
    uploading = false;
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  function html(assets) {
    return `<section id="voice-fields" class="voice-compose" hidden><h3>O‘zingizning asl ovozingiz</h3><label>Saqlangan yozuv<select name="audio_id"><option value="">Ovoz tanlang yoki yangisini yozing</option>${assets.map((a) => `<option value="${esc(a.id)}">${esc(a.label)} · ${Math.round(a.duration)} s</option>`).join("")}</select></label><label>Yozuv nomi<input name="voice_label" maxlength="100" placeholder="Masalan: Uchrashuv haqida"></label><div class="voice-buttons"><button type="button" class="btn secondary" id="voice-record">🎙 Ovoz yozishni boshlash</button><label class="btn secondary">Audio fayl tanlash<input id="voice-file" type="file" accept="audio/*" hidden></label></div><p id="voice-status" class="form-note" role="status">Mikrofonni faqat siz bosganingizda yoqamiz. 3 daqiqagacha, 12 MB gacha.</p><audio id="voice-local" controls hidden></audio><button type="button" id="voice-save" class="btn secondary small" disabled>Kutubxonaga saqlash</button><label>Qanday yetkazilsin?<select name="delivery"><option value="call">Qo‘ng‘iroqda eshittirish</option><option value="message">Telegram chatga golos yuborish</option></select></label><label class="check-label"><input name="collect_reply" type="checkbox" checked> Xabardan keyin javobini ham yozib olib menga yuborsin</label><p class="form-note">Asl ovozingiz tarjima qilinmaydi, AI tanimaydi va o‘zgartirmaydi. Suhbat tili faqat agentning qisqa kirish gapiga tegishli. Saqlangan ovoz shu kompyuterda qoladi.</p></section>`;
  }
  function status(text) {
    const el = form?.querySelector("#voice-status");
    if (el) el.textContent = text;
  }
  function preview() {
    const audio = form?.querySelector("#voice-local"),
      save = form?.querySelector("#voice-save");
    if (!audio || !save) return;
    if (localUrl) URL.revokeObjectURL(localUrl);
    localUrl = "";
    if (blob) {
      localUrl = URL.createObjectURL(blob);
      audio.src = localUrl;
      audio.hidden = false;
      save.disabled = uploading;
    } else {
      audio.removeAttribute("src");
      audio.hidden = true;
      save.disabled = true;
    }
  }
  function stop() {
    clearTimeout(timer);
    timer = null;
    if (recorder && recorder.state !== "inactive") {
      finishing = true;
      recorder.stop();
    }
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    const b = form?.querySelector("#voice-record");
    if (b) b.textContent = "🎙 Ovoz yozishni boshlash";
  }
  function cleanup(clear = false) {
    stop();
    form = null;
    if (clear) {
      generation++;
      blob = null;
      parts = [];
      if (localUrl) URL.revokeObjectURL(localUrl);
      localUrl = "";
    }
  }
  async function record() {
    if (starting || finishing) return;
    if (recorder && recorder.state === "recording") {
      stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      status(
        "Bu brauzer mikrofonni qo‘llamayapti. Audio fayl tanlang yoki localhost/HTTPS orqali oching.",
      );
      return;
    }
    const originalForm = form,
      epoch = generation;
    starting = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (form !== originalForm || !form?.isConnected || epoch !== generation) {
        stop();
        return;
      }
      parts = [];
      bytes = 0;
      const mime = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((t) => MediaRecorder.isTypeSupported(t));
      recorder = new MediaRecorder(
        stream,
        mime ? { mimeType: mime } : undefined,
      );
      recorder.ondataavailable = (e) => {
        if (e.data.size) {
          parts.push(e.data);
          bytes += e.data.size;
          if (bytes > 12 * 1024 * 1024) stop();
        }
      };
      recorder.onstop = () => {
        finishing = false;
        if (epoch !== generation) return;
        blob =
          bytes > 12 * 1024 * 1024
            ? null
            : new Blob(parts, { type: recorder.mimeType || "audio/webm" });
        preview();
        status(
          blob
            ? "Yozuv tayyor. Eshiting, so‘ng kutubxonaga saqlang."
            : "Yozuv 12 MB dan oshdi. Qisqaroq yozing.",
        );
      };
      recorder.onerror = () => {
        stop();
        status("Yozishda xato. Qayta yozing yoki audio fayl tanlang.");
      };
      recorder.start(1000);
      form.querySelector("#voice-record").textContent = "■ Yozishni tugatish";
      status("Mikrofon yoqilgan — ovozingiz yozilyapti.");
      timer = setTimeout(stop, 179000);
    } catch {
      stop();
      status(
        "Mikrofon ochilmadi. Brauzer ruxsatini tekshiring yoki tayyor audio fayl tanlang.",
      );
    } finally {
      starting = false;
    }
  }
  function bind(target, options) {
    form = target;
    callbacks = options;
    preview();
    form.querySelector("#voice-record").onclick = record;
    form.querySelector("#voice-file").onchange = (e) => {
      generation++;
      stop();
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 12 * 1024 * 1024) {
        status("Fayl 12 MB dan katta.");
        return;
      }
      blob = file;
      preview();
      status("Fayl tanlandi. Eshiting va kutubxonaga saqlang.");
    };
    form.querySelector('[name="audio_id"]').onchange = (e) => {
      if (e.target.value) {
        const audio = form.querySelector("#voice-local");
        audio.src = "/api/voice-assets/" + e.target.value;
        audio.hidden = false;
      }
    };
    form.querySelector("#voice-save").onclick = async () => {
      if (!blob || uploading) return;
      const originalForm = form,
        originalCallbacks = callbacks,
        sourceBlob = blob;
      const button = originalForm.querySelector("#voice-save");
      const label =
        originalForm.querySelector('[name="voice_label"]').value.trim() ||
        "Mening ovozli xabarim";
      uploading = true;
      button.disabled = true;
      try {
        const response = await fetch(
          "/api/voice-upload?label=" + encodeURIComponent(label),
          {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": sourceBlob.type || "application/octet-stream",
              "X-CSRF-Token": originalCallbacks.csrf(),
            },
            body: sourceBlob,
          },
        );
        let data;
        try {
          data = await response.json();
        } catch {
          throw Error("Server audio javobini qaytarmadi.");
        }
        if (!response.ok) throw Error(data.error || "Audio saqlanmadi.");
        originalCallbacks.saved(data);
        if (
          form === originalForm &&
          originalForm.isConnected &&
          blob === sourceBlob
        ) {
          const select = originalForm.querySelector('[name="audio_id"]');
          select.add(
            new Option(
              data.label + " · " + Math.round(data.duration) + " s",
              data.id,
              true,
              true,
            ),
          );
          status("Saqlandi. Kontakt va yetkazish turini tanlang.");
        }
        if (blob === sourceBlob) blob = null;
      } catch (error) {
        if (form === originalForm) status(error.message);
      } finally {
        uploading = false;
        if (form?.isConnected) {
          const save = form.querySelector("#voice-save");
          if (save) save.disabled = !blob;
        }
      }
    };
  }
  return {
    html,
    bind,
    cleanup,
    stop,
    cancel: () => {
      generation++;
      stop();
    },
  };
})();
