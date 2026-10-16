"use strict";

(function (root) {
  const fold = text => String(text ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  function matching(options, query) {
    const terms = fold(query).trim().split(/\s+/).filter(Boolean);
    return options.filter(o => !o.disabled && terms.every(t => fold(`${o.label} ${o.value}`).includes(t)));
  }
  const api = {matching};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;
  const controls = new Map();
  let current = null, serial = 0, scheduled = false;
  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function close(focus = false) {
    if (!current) return;
    const item = current;
    current = null;
    item.popup.hidden = true;
    item.button.setAttribute("aria-expanded", "false");
    item.abort?.abort();
    clearTimeout(item.timer);
    if (focus && item.select.isConnected) item.button.focus();
  }
  function options(select) {
    return [...select.options].map(o => ({value: o.value, label: o.textContent, disabled: o.disabled}));
  }
  function sync(item) {
    const choice = item.select.selectedOptions[0];
    item.value.textContent = choice?.textContent || "Escolha uma opção";
    item.button.disabled = item.select.disabled || !item.select.options.length;
    item.button.setAttribute("aria-label", `${item.label}: ${item.value.textContent}`);
  }
  function choose(item, choice) {
    if (![...item.select.options].some(o => o.value === choice.value)) {
      const o = node("option", "", choice.label); o.value = choice.value; item.select.append(o);
    }
    const changed = item.select.value !== choice.value;
    item.select.value = choice.value;
    sync(item);
    close(true);
    if (changed) item.select.dispatchEvent(new Event("change", {bubbles: true}));
  }
  function highlight(item, index) {
    const buttons = [...item.list.children];
    if (!buttons.length) { item.input.removeAttribute("aria-activedescendant"); return; }
    item.index = (index + buttons.length) % buttons.length;
    buttons.forEach((b, i) => b.classList.toggle("highlighted", i === item.index));
    item.input.setAttribute("aria-activedescendant", buttons[item.index].id);
    const active = buttons[item.index].getBoundingClientRect(), bounds = item.list.getBoundingClientRect();
    if (active.top < bounds.top) item.list.scrollTop -= bounds.top - active.top;
    if (active.bottom > bounds.bottom) item.list.scrollTop += active.bottom - bounds.bottom;
  }
  function render(item, choices, more = false) {
    item.choices = choices.slice(0, 200);
    item.list.replaceChildren(...item.choices.map((choice, index) => {
      const b = node("button", "filter-select-option", choice.label);
      b.type = "button"; b.id = `${item.select.id}-choice-${index}`; b.tabIndex = -1;
      b.setAttribute("role", "option"); b.setAttribute("aria-selected", String(choice.value === item.select.value));
      b.addEventListener("click", () => choose(item, choice));
      return b;
    }));
    item.note.textContent = !choices.length ? "Nenhuma opção encontrada." : more || choices.length > 200 ? "Refine a busca para encontrar outras opções." : `${choices.length} opção(ões). Use ↑ ↓ e Enter.`;
    const selected = item.choices.findIndex(o => o.value === item.select.value);
    item.index = !item.input.value.trim() && selected >= 0 ? selected : 0;
    if (choices.length) highlight(item, item.index);
    else item.input.removeAttribute("aria-activedescendant");
  }
  async function search(item) {
    if (current !== item) return;
    const request = ++item.request;
    item.abort?.abort();
    if (!item.provider) { render(item, matching(options(item.select), item.input.value)); return; }
    const controller = new AbortController(); item.abort = controller;
    item.note.textContent = "Buscando opções…";
    item.list.replaceChildren();
    try {
      const result = await item.provider(item.input.value, controller.signal);
      if (current !== item || request !== item.request) return;
      const values = Array.isArray(result) ? result : result.options;
      const choices = values.map(v => typeof v === "string" ? {value: v, label: v} : v);
      const empty = options(item.select).find(o => o.value === "");
      if (empty && !item.input.value.trim() && !choices.some(o => o.value === "")) choices.unshift(empty);
      render(item, choices, !!result.more);
    } catch (error) {
      if (error.name !== "AbortError" && current === item) {
        render(item, matching(options(item.select), item.input.value));
        item.note.textContent = "Busca na base indisponível. Mostrando opções já carregadas.";
      }
    }
  }
  function open(item) {
    if (item.button.disabled) return;
    if (current === item) { close(true); return; }
    close(); current = item;
    const rect = item.button.getBoundingClientRect();
    item.wrapper.classList.toggle("open-above", rect.bottom + 325 > innerHeight && rect.top > innerHeight - rect.bottom);
    item.wrapper.classList.toggle("align-right", rect.left + Math.max(240, rect.width) > innerWidth - 16);
    item.popup.hidden = false; item.button.setAttribute("aria-expanded", "true");
    item.input.value = ""; item.input.focus(); search(item);
  }
  function enhance(select) {
    if (controls.has(select) || select.dataset.native === "true") return;
    if (!select.id) select.id = `filter-field-${++serial}`;
    const label = select.getAttribute("aria-label") || [...(select.closest("label")?.childNodes || [])].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(" ") || "Filtro";
    const wrapper = node("span", "filter-select"), button = node("button", "filter-select-trigger"), value = node("span"), arrow = node("span", "filter-select-arrow", "⌄");
    const popup = node("span", "filter-select-popup"), input = node("input", "filter-select-search"), list = node("span", "filter-select-list"), note = node("span", "filter-select-note");
    button.type = "button"; button.setAttribute("role", "combobox"); button.setAttribute("aria-haspopup", "listbox"); button.setAttribute("aria-expanded", "false");
    list.id = `${select.id}-choices`; list.setAttribute("role", "listbox"); list.setAttribute("aria-label", label);
    button.setAttribute("aria-controls", list.id);
    input.type = "search"; input.placeholder = "Pesquisar opção…"; input.autocomplete = "off"; input.maxLength = 300;
    input.setAttribute("aria-label", `Pesquisar opções de ${label}`); input.setAttribute("aria-controls", list.id);
    note.setAttribute("role", "status"); note.setAttribute("aria-live", "polite");
    popup.hidden = true; button.append(value, arrow); popup.append(input, list, note); wrapper.append(button, popup);
    select.after(wrapper); select.hidden = true; select.tabIndex = -1; select.setAttribute("aria-hidden", "true");
    const item = {select, wrapper, button, value, popup, input, list, note, label, request: 0, index: 0};
    controls.set(select, item); sync(item);
    button.addEventListener("click", () => open(item));
    button.addEventListener("keydown", e => { if (["ArrowDown", "ArrowUp"].includes(e.key)) { e.preventDefault(); open(item); } });
    input.addEventListener("input", () => {
      clearTimeout(item.timer); item.abort?.abort(); ++item.request;
      item.choices = []; item.list.replaceChildren(); item.note.textContent = "Buscando opções…";
      item.timer = setTimeout(() => search(item), item.provider ? 180 : 0);
    });
    input.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); highlight(item, item.index + (e.key === "ArrowDown" ? 1 : -1)); }
      if (e.key === "Enter") { e.preventDefault(); if (item.choices?.[item.index]) choose(item, item.choices[item.index]); }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
      if (e.key === "Tab") { close(); item.button.focus(); }
    });
    select.addEventListener("change", () => sync(item));
    item.observer = new MutationObserver(() => { sync(item); if (current === item && !item.provider) search(item); });
    item.observer.observe(select, {childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "selected", "label"]});
  }
  function refresh() {
    document.querySelectorAll("select").forEach(enhance);
    for (const [select, item] of controls) {
      if (!select.isConnected) { if (current === item) close(); item.observer.disconnect(); controls.delete(select); }
      else sync(item);
    }
  }
  api.refresh = refresh;
  api.close = close;
  api.setProvider = (select, provider) => { enhance(select); const item = controls.get(select); if (item) item.provider = provider; };
  root.FilterMenus = api;
  document.addEventListener("click", e => { if (current && !current.wrapper.contains(e.target)) close(); });
  document.addEventListener("dashboard:view", () => close());
  document.addEventListener("submit", () => close(), true);
  document.addEventListener("change", () => refresh());
  window.addEventListener("resize", () => close());
  document.addEventListener("scroll", e => { if (current && e.target instanceof Node && !current.wrapper.contains(e.target)) close(); }, true);
  new MutationObserver(records => {
    if (!records.some(r => [...r.addedNodes, ...r.removedNodes].some(n => n.nodeType === 1 && (n.matches?.("select") || n.querySelector?.("select"))))) return;
    if (!scheduled) { scheduled = true; queueMicrotask(() => { scheduled = false; refresh(); }); }
  }).observe(document.body, {childList: true, subtree: true});
  refresh();
}(globalThis));
