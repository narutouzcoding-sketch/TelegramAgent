"use strict";
window.AgentContacts = (() => {
  function normalize(value) {
    return String(value || "")
      .normalize("NFKD")
      .toLowerCase()
      .replace(/\p{M}/gu, "")
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim();
  }
  function matches(contact, query) {
    const terms = normalize(query).split(/\s+/).filter(Boolean);
    if (!terms.length) return true;
    const text = normalize(contact.name + " " + contact.reference);
    if (
      /^[\d\s+().-]+$/.test(query) &&
      String(contact.reference || "")
        .replace(/\D/g, "")
        .includes(query.replace(/\D/g, ""))
    )
      return true;
    return terms.every((word) =>
      /^\d+$/.test(word)
        ? text.split(" ").some((part) => part.startsWith(word))
        : text.includes(word) ||
          (word.length > 5 &&
            text.includes(word.replace(/(?:ning|dagi|dan|ga|ni)$/u, ""))),
    );
  }
  const escape = (value) =>
    String(value ?? "").replace(
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
  function bind(input, contacts) {
    if (!input) return;
    input.removeAttribute("list");
    input.parentElement.classList.add("recipient-field");
    const selectedId = input.form?.elements.namedItem("contact_id");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "recipient-options");
    input.setAttribute("aria-expanded", "false");
    const box = document.createElement("div");
    box.id = "recipient-options";
    box.className = "recipient-options";
    box.setAttribute("role", "listbox");
    box.hidden = true;
    input.insertAdjacentElement("afterend", box);
    let results = [],
      active = -1;
    function close() {
      box.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }
    function choose(index) {
      const selected = results[index];
      if (!selected) return;
      input.value = selected.reference;
      input.dataset.contactId = String(selected.id);
      if (selectedId) selectedId.value = String(selected.id);
      const label = document.getElementById("selected-recipient");
      if (label) label.textContent = selected.name;
      close();
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    function show() {
      results = contacts
        .filter((contact) => matches(contact, input.value))
        .slice(0, 12);
      active = -1;
      box.innerHTML = results.length
        ? results
            .map(
              (contact, index) =>
                `<button type="button" role="option" aria-selected="false" id="recipient-${index}" data-choice="${index}"><strong>${escape(contact.name)}</strong><small>${escape(contact.reference)}</small></button>`,
            )
            .join("")
        : "<p>Kontakt topilmadi. Aniq @username yozishingiz ham mumkin.</p>";
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    input.addEventListener("input", () => {
      delete input.dataset.contactId;
      if (selectedId) selectedId.value = "";
      const label = document.getElementById("selected-recipient");
      if (label) label.textContent = "";
      show();
    });
    input.addEventListener("focus", show);
    input.addEventListener("blur", () =>
      setTimeout(() => {
        if (
          document.activeElement !== input &&
          !box.contains(document.activeElement)
        )
          close();
      }, 180),
    );
    box.addEventListener("focusout", () =>
      setTimeout(() => {
        if (
          document.activeElement !== input &&
          !box.contains(document.activeElement)
        )
          close();
      }, 0),
    );
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        close();
        return;
      }
      if (box.hidden) return;
      if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        choose(active);
        return;
      }
      if (!["ArrowDown", "ArrowUp"].includes(event.key) || !results.length)
        return;
      event.preventDefault();
      active =
        active < 0
          ? event.key === "ArrowDown"
            ? 0
            : results.length - 1
          : (active + (event.key === "ArrowDown" ? 1 : -1) + results.length) %
            results.length;
      box
        .querySelectorAll('[role="option"]')
        .forEach((option, index) =>
          option.setAttribute("aria-selected", String(index === active)),
        );
      input.setAttribute("aria-activedescendant", "recipient-" + active);
      box
        .querySelector("#recipient-" + active)
        ?.scrollIntoView({ block: "nearest" });
    });
    box.addEventListener("click", (event) => {
      const option = event.target.closest("[data-choice]");
      if (option) choose(Number(option.dataset.choice));
    });
  }
  return { matches, normalize, bind };
})();
