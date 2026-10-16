"use strict";

(function () {
  const el = id => document.getElementById(id);
  const c = {data: null, page: 1, controller: null, request: 0, busy: false};
  const fmt = v => v == null ? "—" : Number(v).toLocaleString("pt-BR", {maximumFractionDigits: 1});
  const day = v => v ? v.slice(0,10).split("-").reverse().join("/") : "—";
  let timer;
  function make(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function query() {
    return new URLSearchParams({...window.Prospec.filters(), versao: window.Prospec.metadata().versao,
      tipo_atividade: el("pro-activity-type").value, atividade_busca: el("pro-activity-search").value.trim(),
      atividade_pagina: String(c.page), atividade_por_pagina: el("pro-activity-size").value});
  }
  function error(text) { el("pro-consult-error").textContent = text || ""; el("pro-consult-error").hidden = !text; }
  function busy(value) {
    c.busy = value;
    for (const id of ["pro-consult-kpis", "pro-consult-summary", "pro-activities-table"]) { el(id).setAttribute("aria-busy", String(value)); el(id).classList.toggle("pro-loading", value); }
    el("pro-consult-export").disabled = value || c.failed || !c.data?.total;
    el("pro-activity-prev").disabled = value || !c.data || c.page <= 1;
    el("pro-activity-next").disabled = value || !c.data || c.page >= c.data.paginas;
    if (value) el("pro-activities-range").textContent = "Carregando atividades…";
  }
  async function load(reset = false) {
    if (!window.Prospec?.metadata()?.carregado || window.Prospec.activeTab() !== "consultores") return;
    if (reset) c.page = 1;
    c.controller?.abort(); const controller = new AbortController(); c.controller = controller;
    const request = ++c.request;
    c.failed = false;
    busy(true); error("");
    try {
      const response = await fetch(`/api/prospeccao/consultores?${query()}`, {signal: controller.signal, cache: "no-store", credentials: "same-origin"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || "Não foi possível consultar os consultores.");
      if (request !== c.request) return;
      c.data = data; c.page = data.pagina; render();
    } catch (failure) { if (failure.name !== "AbortError" && request === c.request) { c.failed = true; error(failure.message); el("pro-activities-range").textContent = "Consulta não concluída."; } }
    finally { if (request === c.request) busy(false); }
  }
  function table(id, columns, rows) {
    const wrapper = make("div", "pro-scroll"), table = make("table", "pro-table"), head = make("thead"), body = make("tbody"), header = make("tr");
    columns.forEach(([key,title,formatter,numeric]) => { const th = make("th", numeric ? "numeric" : "", title); th.scope = "col"; header.append(th); });
    head.append(header);
    rows.forEach(row => {
      const tr = make("tr");
      columns.forEach(([key,title,formatter,numeric]) => {
        const td = make("td", numeric ? "numeric" : ""), value = formatter ? formatter(row[key],row) : row[key] ?? "—";
        if (value instanceof Node) td.append(value); else td.textContent = value;
        tr.append(td);
      }); body.append(tr);
    });
    if (!rows.length) { const tr = make("tr"), td = make("td", "table-message", "Nenhuma atividade encontrada neste período e recorte. Tente limpar a busca ou ampliar as datas."); td.colSpan = columns.length; tr.append(td); body.append(tr); }
    table.append(head, body); wrapper.append(table); el(id).replaceChildren(wrapper);
  }
  function card(label, value, note) { const n = make("article", "metric"); n.append(make("div", "metric-label", label), make("strong", "", fmt(value)), make("span", "", note)); return n; }
  function person(value, row) {
    if (!row.id) return value;
    const button = make("button", "pro-loja-button", value); button.type = "button";
    button.addEventListener("click", () => window.Prospec.selectConsultor(row.id)); return button;
  }
  function store(value) { if (!value) return "—"; const button = make("button", "pro-loja-button", value); button.type = "button"; button.addEventListener("click", () => window.Prospec.openStore(value)); return button; }
  function render() {
    const d = c.data, t = d.totais;
    el("pro-consult-kpis").replaceChildren(card("Consultores no recorte", t.consultores, "Inclui carteiras sem atividade registrada"), card("Contratos emitidos", t.emitidos, `${fmt(t.aprovados)} com aprovação no período`), card("Negócios da carteira", t.negocios, `${fmt(t.transacoes)} transações bancárias confirmadas`), card("Acompanhamentos executados", t.acompanhamentos, `${fmt(t.pendencias)} pendências no período`));
    table("pro-consult-summary", [["nome","Consultor",person],["gerencias","Gerências"],["emitidos","Emitidos",fmt,true],["aprovados","Aprovados",fmt,true],
      ["inauguracoes","Inaugurações",fmt,true],["lojas","Lojas",fmt,true],["negocios","Negócios",fmt,true],["transacoes","Transações",fmt,true],
      ["treinamentos","Treinamentos",fmt,true],["suportes","Suportes",fmt,true],["pendencias","Pendências",fmt,true]],d.consultores);
    el("pro-consult-note").textContent = `${fmt(d.total)} registros de atividade. ${fmt(t.sem_executor)} atendimento(s) concluído(s) sem executor informado ficam sem crédito individual. ${fmt(t.producao_sem_cobertura)} registro(s) de produção sem cobertura completa não entram nos volumes confirmados. A produção usa a competência mensal e aparece na data de fechamento; ela não identifica quem realizou cada operação. Pendências usam o prazo previsto dentro do intervalo.`;
    table("pro-activities-table", [["data","Data",day],["responsavel","Consultor"],["gerencia","Gerência"],["tipo","Atividade"],["id_contrato","Contrato"],
      ["chave_loja","Loja",store],["razao_social","Credenciado"],["descricao","Detalhe"],["quantidade","Quantidade confirmada",fmt,true],
      ["quantidade_informada","Quantidade informada",fmt,true],["completo","Cobertura",(v,r) => r.natureza === "producao" ? v ? "Completa" : "Parcial/ausente" : "—"],
      ["atribuicao","Atribuição"],["origem","Fonte",v => v ? `${v.arquivo} · ${v.aba} · linha ${v.linha}` : "—"]],d.atividades);
    el("pro-activity-count").textContent = fmt(d.total);
    const first = d.total ? (d.pagina - 1) * d.por_pagina + 1 : 0;
    el("pro-activities-range").textContent = `${fmt(first)}–${fmt(Math.min(d.pagina * d.por_pagina,d.total))} de ${fmt(d.total)} registros`;
    el("pro-activity-page").textContent = `${d.pagina} / ${d.paginas}`;
  }
  async function exportCSV() {
    el("pro-consult-export").disabled = true;
    try {
      const response = await fetch(`/api/prospeccao/consultores.csv?${query()}`, {credentials:"same-origin"});
      if (!response.ok) throw new Error((await response.json()).erro || "Não foi possível exportar.");
      const url = URL.createObjectURL(await response.blob()), link = make("a");
      link.href = url; link.download = "atividades_consultores.csv"; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url),10000);
    } catch (failure) { error(failure.message); }
    finally { el("pro-consult-export").disabled = !c.data?.total; }
  }
  el("pro-activity-search").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(true),300); });
  for (const id of ["pro-activity-type","pro-activity-size"]) el(id).addEventListener("change", () => load(true));
  el("pro-activity-clear").addEventListener("click", () => { el("pro-activity-search").value = ""; el("pro-activity-type").value = ""; window.FilterMenus?.refresh(); load(true); });
  el("pro-activity-prev").addEventListener("click", () => { if (c.page > 1) { c.page--; load(); } });
  el("pro-activity-next").addEventListener("click", () => { if (c.page < c.data?.paginas) { c.page++; load(); } });
  el("pro-consult-export").addEventListener("click", exportCSV);
  document.addEventListener("dashboard:prospeccao-data", () => { c.controller?.abort(); ++c.request; load(true); });
  document.addEventListener("dashboard:prospeccao-tab", event => { if (event.detail === "consultores") load(); });
}());
