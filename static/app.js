"use strict";

const $ = id => document.getElementById(id);
const number = value => value == null ? "—" : Number(value).toLocaleString("pt-BR");
const fold = text => String(text ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const headerKey = text => fold(text).replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
const state = {meta: null, result: null, filters: [], visible: new Set(), page: 1, sort: "", direction: "asc", request: 0, controller: null, view: "consulta", loading: false};
const operators = [["contem", "Contém"], ["igual", "É igual a"], ["diferente", "É diferente de"], ["comeca", "Começa com"], ["vazio", "Está vazio"], ["preenchido", "Está preenchido"], ["maior_igual", "Maior ou igual a"], ["menor_igual", "Menor ou igual a"]];
let toastTimer, searchTimer, clientTimer, optionsRequest = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function option(value, label) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

function timestamp(value) {
  if (!value) return "Ainda não publicada";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"});
}

function display(value, column) {
  if (value == null || value === "") return "—";
  if (column.tipo === "data") {
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}:\d{2}))?/);
    if (match) return `${match[3]}/${match[2]}/${match[1]}${match[4] ? " " + match[4] : ""}`;
  }
  if (column.tipo === "numero" && Number.isFinite(Number(value))) {
    return Number(value).toLocaleString("pt-BR", {maximumFractionDigits: 12});
  }
  return String(value);
}

function statusClass(value) {
  const name = fold(value);
  if (["ativo", "ativa", "aprovado", "aprovada", "liberado", "liberada"].includes(name)) return "success";
  if (["pendente", "em analise", "em aprovacao", "solicitado"].includes(name)) return "warning";
  if (["inativo", "inativa", "bloqueado", "bloqueada", "revogado", "revogada", "reprovado"].includes(name)) return "danger";
  return "";
}

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4200);
}

function error(message) {
  $("error-text").textContent = message;
  $("error-banner").hidden = !message;
}

async function jsonRequest(url, signal) {
  const response = await fetch(url, {signal, credentials: "same-origin", cache: "no-store"});
  const payload = await response.json();
  if (!response.ok) {
    const failure = new Error(payload.erro || "Não foi possível carregar os dados.");
    failure.status = response.status;
    failure.payload = payload;
    throw failure;
  }
  return payload;
}

function fillSelect(select, values, allLabel) {
  const previous = select.value;
  select.replaceChildren(option("", allLabel), ...values.map(v => option(v, v)));
  if (values.includes(previous)) select.value = previous;
}

function applyMeta(meta) {
  const firstLoad = state.meta === null;
  state.meta = meta;
  document.title = meta.titulo;
  $("page-title").textContent = state.view === "fontes" ? "Fontes de dados" : meta.titulo;
  $("example-badge").hidden = !meta.modo_exemplo;
  $("updated").textContent = timestamp(meta.atualizado_em);
  $("sidebar-updated").textContent = timestamp(meta.atualizado_em);
  $("sync-state").textContent = meta.carregado ? "Base disponível" : "Base não importada";
  $("sync-dot").classList.toggle("waiting", !meta.carregado);
  $("nav-count").textContent = number(meta.fontes.length);
  $("base-total").textContent = `${number(meta.total)} registros na base`;
  const valid = new Set(meta.colunas.map(c => c.id));
  state.filters = state.filters.filter(f => valid.has(f.coluna));
  if (!valid.has(state.sort)) state.sort = "";
  if (firstLoad || !state.visible.size) {
    const initial = new Set(meta.colunas_iniciais.map(headerKey));
    const chosen = meta.colunas.filter(c => initial.has(headerKey(c.nome)));
    state.visible = new Set((chosen.length ? chosen : meta.colunas.slice(0, 7)).map(c => c.id));
  } else {
    state.visible = new Set([...state.visible].filter(id => valid.has(id)));
    if (!state.visible.size && meta.colunas.length) state.visible.add(meta.colunas[0].id);
  }
  const previous = $("search-column").value;
  $("search-column").replaceChildren(option("", "Todas as colunas"), ...meta.colunas.map(c => option(c.id, c.nome)));
  if (valid.has(previous)) $("search-column").value = previous;
  for (const [role, control, input] of [["cliente", "client-control", "client"], ["sistema", "system-control", "system"], ["status", "status-control", "status"]]) {
    $(control).hidden = !meta.papeis[role];
    if (!meta.papeis[role]) $(input).value = "";
  }
  fillSelect($("source"), meta.fontes.map(f => f.arquivo), "Todos os arquivos");
  buildColumns();
  $("filter-rows").replaceChildren();
  state.filters.forEach(addFilterRow);
  updateFilterCount();
  renderSources();
}

async function loadOptions() {
  const meta = state.meta;
  if (!meta?.carregado) return;
  const roles = [["cliente", "client-options", ""], ["sistema", "system", "Todos os sistemas"], ["status", "status", "Todos os status"]];
  const results = await Promise.allSettled(roles.map(async ([role, id, allLabel]) => {
    const column = meta.papeis[role];
    if (!column) return false;
    const values = await jsonRequest(`/api/opcoes?${new URLSearchParams({coluna: column})}`);
    if (state.meta.versao !== meta.versao) return false;
    if (role === "cliente") $(id).replaceChildren(...values.valores.map(v => option(v, v)));
    else fillSelect($(id), values.valores, allLabel);
    return values.mais_resultados;
  }));
  if (state.meta.versao !== meta.versao) return;
  $("options-note").hidden = !results.some(r => r.status === "fulfilled" && r.value);
  if (results.some(r => r.status === "rejected")) toast("Algumas sugestões não foram carregadas. A busca continua disponível.");
}

async function clientSuggestions() {
  if (!state.meta?.papeis.cliente) return;
  const request = ++optionsRequest;
  try {
    const result = await jsonRequest(`/api/opcoes?${new URLSearchParams({coluna: state.meta.papeis.cliente, busca: $("client").value})}`);
    if (request === optionsRequest) $("client-options").replaceChildren(...result.valores.map(v => option(v, v)));
  } catch (failure) { /* Sugestões são opcionais; a consulta mostra seus próprios erros. */ }
}

function currentParams() {
  const params = new URLSearchParams({pagina: String(state.page), por_pagina: $("page-size").value});
  const filters = [...state.filters];
  const search = $("search").value.trim();
  if (search) {
    if ($("search-column").value) filters.push({coluna: $("search-column").value, operador: "contem", valor: search});
    else params.set("q", search);
  }
  if (filters.length) params.set("filtros", JSON.stringify(filters));
  for (const [id, name] of [["client", "cliente"], ["system", "sistema"], ["status", "status"], ["source", "arquivo"]]) {
    if ($(id).value.trim()) params.set(name, $(id).value.trim());
  }
  if (state.sort) { params.set("ordenar", state.sort); params.set("direcao", state.direction); }
  if (state.meta?.versao) params.set("versao", state.meta.versao);
  return params;
}

function setLoading(value) {
  state.loading = value;
  $("table-scroll").setAttribute("aria-busy", String(value));
  $("export").disabled = value || !state.meta?.carregado || !state.result?.total;
  $("previous").disabled = value || !state.result || state.result.pagina <= 1;
  $("next").disabled = value || !state.result || state.result.pagina >= state.result.paginas;
}

async function loadData(retryVersion = true) {
  if (!state.meta) return;
  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;
  const request = ++state.request;
  setLoading(true);
  try {
    const result = await jsonRequest(`/api/registros?${currentParams()}`, controller.signal);
    if (request !== state.request) return;
    state.result = result;
    state.page = result.pagina;
    error("");
    renderResults();
  } catch (failure) {
    if (failure.name === "AbortError" || request !== state.request) return;
    if (failure.status === 409 && failure.payload.metadados && retryVersion) {
      applyMeta(failure.payload.metadados);
      state.page = 1;
      loadOptions();
      await loadData(false);
      return;
    }
    error(failure.message);
    $("result-range").textContent = "A consulta não foi concluída.";
    state.result = null;
    const row = element("tr");
    const cell = element("td", "table-message", "Não foi possível carregar esta consulta. Verifique os filtros e tente novamente.");
    cell.colSpan = Math.max(1, state.visible.size);
    row.append(cell);
    $("table-body").replaceChildren(row);
  } finally {
    if (request === state.request) setLoading(false);
  }
}

async function refresh() {
  $("refresh").disabled = true;
  try {
    const meta = await jsonRequest("/api/metadados");
    const changed = state.meta && state.meta.versao !== meta.versao;
    applyMeta(meta);
    await Promise.all([loadOptions(), loadData()]);
    if (changed) toast("A nova base publicada já está disponível.");
  } catch (failure) { error(failure.message); }
  finally { $("refresh").disabled = false; }
}

function newSearch() { state.page = 1; loadData(); }

function buildColumns() {
  const fieldset = $("column-options");
  fieldset.replaceChildren(element("legend", "", "Colunas visíveis"));
  state.meta.colunas.forEach(column => {
    const label = element("label");
    const input = element("input");
    input.type = "checkbox";
    input.value = column.id;
    input.checked = state.visible.has(column.id);
    input.addEventListener("change", () => {
      if (input.checked) state.visible.add(column.id);
      else {
        if (state.visible.size === 1) { input.checked = true; toast("Mantenha pelo menos uma coluna visível."); return; }
        state.visible.delete(column.id);
      }
      if (state.result) renderTable();
    });
    label.append(input, document.createTextNode(column.nome));
    fieldset.append(label);
  });
}

function addFilterRow(initial = null) {
  if (!state.meta?.colunas.length) { toast("Importe a base para selecionar as colunas."); return; }
  if ($("filter-rows").children.length >= 15) { toast("Use até 15 condições por consulta."); return; }
  const row = element("div", "filter-row");
  const columnLabel = element("label", "", "Coluna");
  const columnSelect = element("select");
  columnSelect.className = "filter-column";
  columnSelect.append(...state.meta.colunas.map(c => option(c.id, c.nome)));
  if (initial) columnSelect.value = initial.coluna;
  columnLabel.append(columnSelect);
  const operatorLabel = element("label", "", "Condição");
  const operatorSelect = element("select", "filter-operator");
  operatorLabel.append(operatorSelect);
  const valueLabel = element("label", "value-label", "Valor");
  const valueInput = element("input", "filter-value");
  valueInput.maxLength = 500;
  valueInput.placeholder = "Digite um valor";
  if (initial) valueInput.value = initial.valor || "";
  valueLabel.append(valueInput);
  function updateInput() {
    const column = state.meta.colunas.find(c => c.id === columnSelect.value);
    const op = operatorSelect.value;
    valueInput.disabled = ["vazio", "preenchido"].includes(op);
    const previous = valueInput.value;
    valueInput.type = column?.tipo === "data" && !["contem", "comeca"].includes(op) ? "date" : "text";
    if (valueInput.type === "date") valueInput.value = /^\d{4}-\d{2}-\d{2}/.test(previous) ? previous.slice(0, 10) : "";
    valueInput.inputMode = column?.tipo === "numero" ? "decimal" : "text";
  }
  function updateOperators() {
    const column = state.meta.colunas.find(c => c.id === columnSelect.value);
    const previous = operatorSelect.value || initial?.operador;
    const choices = operators.filter(([op]) => !["maior_igual", "menor_igual"].includes(op) || ["data", "numero"].includes(column?.tipo));
    operatorSelect.replaceChildren(...choices.map(([value, label]) => option(value, label)));
    if (choices.some(([op]) => op === previous)) operatorSelect.value = previous;
    updateInput();
  }
  columnSelect.addEventListener("change", updateOperators);
  operatorSelect.addEventListener("change", updateInput);
  const remove = element("button", "remove-filter", "×");
  remove.type = "button";
  remove.setAttribute("aria-label", "Remover esta condição e aplicar os filtros restantes");
  remove.addEventListener("click", () => { row.remove(); applyFilters(); });
  row.append(columnLabel, operatorLabel, valueLabel, remove);
  $("filter-rows").append(row);
  updateOperators();
}

function updateFilterCount() {
  $("advanced-count").textContent = String(state.filters.length);
  $("advanced-count").hidden = !state.filters.length;
}

function applyFilters() {
  const filters = [...$("filter-rows").children].map(row => ({coluna: row.querySelector(".filter-column").value, operador: row.querySelector(".filter-operator").value, valor: row.querySelector(".filter-value").value.trim()}));
  if (filters.some(f => !["vazio", "preenchido"].includes(f.operador) && !f.valor)) {
    error("Preencha o valor de cada condição ou remova as condições vazias.");
    return;
  }
  state.filters = filters;
  updateFilterCount();
  newSearch();
}

function renderResults() {
  const result = state.result;
  $("metric-records").textContent = number(result.total);
  $("metric-clients").textContent = number(result.resumo.clientes);
  $("metric-systems").textContent = number(result.resumo.sistemas);
  $("metric-files").textContent = number(result.resumo.arquivos);
  $("metric-records-note").textContent = `De ${number(state.meta.total)} registros na base`;
  $("result-count").textContent = number(result.total);
  const from = result.total ? (result.pagina - 1) * result.por_pagina + 1 : 0;
  const to = result.total ? from + result.itens.length - 1 : 0;
  $("result-range").textContent = `${number(from)}–${number(to)} de ${number(result.total)} registros`;
  $("page-label").textContent = `${result.pagina} / ${number(result.paginas)}`;
  $("status-strip").replaceChildren(...result.resumo.estados.map(status => {
    const chip = element("button", "status-chip " + statusClass(status.nome));
    chip.type = "button";
    chip.title = `Filtrar status: ${status.nome}`;
    chip.append(element("span", "dot"), document.createTextNode(status.nome), element("strong", "", number(status.quantidade)));
    chip.addEventListener("click", () => {
      const column = state.meta.papeis.status;
      const condition = {coluna: column, operador: status.vazio ? "vazio" : "igual", valor: status.nome};
      if (state.filters.length >= 15 && !state.filters.some(f => f.coluna === column)) {
        toast("Remova uma condição antes de adicionar este filtro de status.");
        return;
      }
      state.filters = state.filters.filter(f => f.coluna !== column);
      state.filters.push(condition);
      $("status").value = "";
      $("filter-rows").replaceChildren();
      state.filters.forEach(addFilterRow);
      updateFilterCount();
      newSearch();
    });
    return chip;
  }));
  $("status-strip").hidden = !result.resumo.estados.length;
  renderTable();
}

function renderTable() {
  const columns = state.meta.colunas.filter(c => state.visible.has(c.id));
  const header = element("tr");
  columns.forEach(column => {
    const th = element("th");
    th.scope = "col";
    th.setAttribute("aria-sort", state.sort === column.id ? (state.direction === "asc" ? "ascending" : "descending") : "none");
    const button = element("button");
    button.append(document.createTextNode(column.nome), element("span", "sort-indicator", state.sort === column.id ? (state.direction === "asc" ? "↑" : "↓") : "↕"));
    button.setAttribute("aria-label", `Ordenar por ${column.nome}`);
    button.addEventListener("click", () => {
      state.direction = state.sort === column.id && state.direction === "asc" ? "desc" : "asc";
      state.sort = column.id;
      newSearch();
    });
    th.append(button);
    header.append(th);
  });
  $("table-head").replaceChildren(header);
  const rows = state.result.itens.map(item => {
    const row = element("tr");
    row.dataset.record = String(item.id);
    columns.forEach((column, index) => {
      const value = item.valores[column.id];
      const cell = element("td", column.tipo === "numero" ? "number-cell" : "");
      cell.title = display(value, column);
      if (index === 0) {
        const link = element("button", "record-link", display(value, column));
        link.setAttribute("aria-label", `Ver detalhes do registro ${display(value, column)}`);
        cell.append(link);
      } else if (column.id === state.meta.papeis.status && value != null) cell.append(element("span", "tag " + statusClass(value), display(value, column)));
      else cell.textContent = display(value, column);
      row.append(cell);
    });
    row.addEventListener("click", () => showRecord(item));
    return row;
  });
  if (!rows.length) {
    const row = element("tr");
    const cell = element("td", "table-message");
    cell.colSpan = Math.max(1, columns.length);
    cell.append(element("strong", "", state.meta.carregado ? "Nenhum registro encontrado" : "A base ainda não foi publicada"), document.createTextNode(state.meta.carregado ? "Tente outro termo ou limpe os filtros para ampliar a busca." : "Execute a importação das planilhas e atualize esta consulta."));
    row.append(cell);
    rows.push(row);
  }
  $("table-body").replaceChildren(...rows);
}

function showRecord(item) {
  const client = item.valores[state.meta.papeis.cliente];
  $("record-title").textContent = client || `Registro ${item.id}`;
  $("record-fields").replaceChildren(...state.meta.colunas.map(column => {
    const field = element("div", "record-field");
    field.append(element("dt", "", column.nome), element("dd", "", display(item.valores[column.id], column)));
    const origin = item.origens_campos?.[column.id];
    if (origin) field.append(element("small", "field-origin", `Fonte: ${origin.arquivo} · ${origin.aba} · linha ${origin.linha}`));
    return field;
  }));
  $("record-source").replaceChildren(element("strong", "", "Origem do registro: "), document.createTextNode(`${item.origem.arquivo} · aba ${item.origem.aba} · linha ${item.origem.linha}`));
  $("record-dialog").showModal();
}

function renderSources() {
  const cards = state.meta.fontes.map(source => {
    const card = element("article", "source-card");
    card.append(element("h3", "", source.arquivo), element("p", "", `${number(source.registros)} registros · Arquivo salvo em ${timestamp(source.modificado_em)}`));
    const list = element("ul");
    source.abas.forEach(sheet => {
      const item = element("li");
      item.append(element("span", "", sheet.nome), element("strong", "", `${number(sheet.registros)} registros`));
      list.append(item);
    });
    card.append(list);
    return card;
  });
  if (!cards.length) cards.push(element("div", "empty-sources", "Nenhuma planilha foi publicada na base ainda."));
  $("source-cards").replaceChildren(...cards);
  renderSchemaAudit();
}

function renderSchemaAudit() {
  const analysis = state.meta.analise_padronizacao;
  $("schema-audit").hidden = !analysis?.ativo;
  if (!analysis?.ativo) return;
  $("schema-state").textContent = analysis.estado;
  $("schema-key-title").textContent = `${analysis.chave_loja} por tabela`;
  $("schema-summary").textContent = `${number(analysis.mapeamentos.length)} cabeçalhos analisados. ${number(analysis.avisos.length)} avisos na última publicação.`;
  $("schema-warnings").replaceChildren(...analysis.avisos.map(w => element("li", "", w.mensagem)));
  const keyRows = analysis.tabelas.map(t => {
    const row = element("tr");
    for (const value of [t.tabela, number(t.linhas), t.chave_presente ? number(t.chaves_distintas) : `Sem ${t.chave}`, number(t.chaves_repetidas), t.unicidade_exigida ? "Exigida" : "Não exigida"]) row.append(element("td", "", value));
    return row;
  });
  $("schema-keys").replaceChildren(...keyRows);
  $("schema-mappings").replaceChildren(...analysis.mapeamentos.map(m => {
    const row = element("tr");
    const label = {alias: "Equivalência do catálogo", fonte: "Regra da fonte", nome: "Formato do nome", renomear_colunas: "Mapeamento configurado", legado: "Mapeamento configurado"}[m.regra] || m.regra;
    for (const value of [m.fonte, m.original, m.padrao, label + (m.oculta ? " · Excluída da consulta" : "")]) row.append(element("td", "", value));
    return row;
  }));
}

function switchView(view) {
  state.view = view;
  $("consulta-view").hidden = view !== "consulta";
  $("fontes-view").hidden = view !== "fontes";
  $("breadcrumb-view").textContent = view === "consulta" ? "Acessos" : "Fontes";
  $("page-title").textContent = view === "consulta" ? (state.meta?.titulo || "Consulta de acessos") : "Fontes de dados";
  $("page-description").textContent = view === "consulta" ? "Pesquise clientes, sistemas e permissões em um só lugar." : "Consulte a origem dos registros publicados no painel.";
  for (const name of ["consulta", "fontes"]) {
    $("nav-" + name).classList.toggle("active", name === view);
    if (name === view) $("nav-" + name).setAttribute("aria-current", "page");
    else $("nav-" + name).removeAttribute("aria-current");
  }
}

async function exportResults() {
  const button = $("export");
  button.disabled = true;
  try {
    const response = await fetch(`/api/exportar.csv?${currentParams()}`, {credentials: "same-origin"});
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.erro || "Não foi possível exportar.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = element("a");
    link.href = url;
    link.download = "acessos_filtrados.csv";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast("Resultado da consulta exportado.");
  } catch (failure) { error(failure.message); }
  finally { button.disabled = state.loading || !state.result?.total; }
}

$("search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(newSearch, 300); });
$("search-column").addEventListener("change", newSearch);
$("client").addEventListener("input", () => { clearTimeout(clientTimer); clientTimer = setTimeout(() => { newSearch(); clientSuggestions(); }, 300); });
for (const id of ["system", "status", "source"]) $(id).addEventListener("change", newSearch);
$("clear").addEventListener("click", () => {
  clearTimeout(searchTimer); clearTimeout(clientTimer);
  for (const id of ["search", "search-column", "client", "system", "status", "source"]) $(id).value = "";
  state.filters = []; state.sort = ""; state.direction = "asc";
  $("filter-rows").replaceChildren(); updateFilterCount(); newSearch();
});
$("add-filter").addEventListener("click", () => addFilterRow());
$("apply-filters").addEventListener("click", applyFilters);
$("refresh").addEventListener("click", refresh);
$("retry").addEventListener("click", refresh);
$("export").addEventListener("click", exportResults);
$("page-size").addEventListener("change", newSearch);
$("previous").addEventListener("click", () => { if (state.page > 1) { state.page--; loadData(); } });
$("next").addEventListener("click", () => { if (state.result && state.page < state.result.paginas) { state.page++; loadData(); } });
$("nav-consulta").addEventListener("click", () => switchView("consulta"));
$("nav-fontes").addEventListener("click", () => switchView("fontes"));
$("help-button").addEventListener("click", () => $("help-dialog").showModal());
document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => $(button.dataset.close).close()));
document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } }));
document.addEventListener("keydown", event => {
  if (event.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) && !document.querySelector("dialog[open]")) {
    event.preventDefault(); switchView("consulta"); $("search").focus();
  }
});
document.addEventListener("click", event => { if (!$("columns-menu").contains(event.target)) $("columns-menu").open = false; });
setInterval(async () => {
  if (document.hidden || !state.meta || state.loading) return;
  try {
    const meta = await jsonRequest("/api/metadados");
    if (meta.versao !== state.meta.versao) { applyMeta(meta); await Promise.all([loadOptions(), loadData()]); toast("Uma atualização da base foi publicada."); }
  } catch (failure) { /* A última consulta segue visível; o botão permite tentar novamente. */ }
}, 60000);
refresh();
