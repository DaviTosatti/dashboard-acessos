"use strict";

(function () {
  const el = id => document.getElementById(id);
  const create = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const fmt = value => value == null ? "—" : Number(value).toLocaleString("pt-BR", {maximumFractionDigits: 1});
  const pct = value => value == null ? "—" : `${fmt(value)}%`;
  const month = value => value ? new Date(`${value.slice(0, 7)}-15T12:00:00`).toLocaleDateString("pt-BR", {month: "short", year: "2-digit"}).replace(". de ", "/").replace(" de ", "/") : "—";
  const day = value => value ? value.slice(0, 10).split("-").reverse().join("/") : "—";
  const stamp = value => value ? new Date(value).toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"}) : "Ainda não publicada";
  const normalized = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  const p = {meta: null, data: null, applied: {}, page: 1, tab: "geral", controller: null, request: 0, loading: false};
  let searchTimer, detailRequest = 0;
  const shiftMonth = (value, step) => {
    const [year, month] = value.split("-").map(Number), n = year * 12 + month - 1 + step;
    return `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, "0")}`;
  };
  function remember() { try { sessionStorage.setItem("expresso-periodo-filtros-v2", JSON.stringify(p.applied)); } catch {} }
  function dirty() {
    el("pro-dirty").hidden = JSON.stringify(appliedFilters()) === JSON.stringify(p.applied);
    window.FilterMenus?.refresh();
  }
  function peopleOptions() {
    if (!p.meta) return;
    const region = el("pro-region").value;
    // Mantém todos disponíveis: um executor pode atuar em loja de outra gerência.
    const ordered = [...p.meta.responsaveis].sort((a,b) => Number(!!region && b.gerencias?.includes(region)) - Number(!!region && a.gerencias?.includes(region)) || a.nome.localeCompare(b.nome, "pt-BR"));
    select("pro-person", ordered, "Todos os responsáveis", r => r.nome, r => r.id);
  }


  function showError(message) {
    el("pro-error").textContent = message || "";
    el("pro-error").hidden = !message;
  }

  async function getJSON(url, signal) {
    const response = await fetch(url, {signal, cache: "no-store", credentials: "same-origin"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.erro || "Não foi possível carregar a prospecção.");
    return payload;
  }

  function option(value, label) {
    const node = create("option", "", label);
    node.value = value;
    return node;
  }

  function select(id, values, all, labeler = x => x, valuer = x => x) {
    const control = el(id), previous = control.value;
    const options = values.map(v => option(valuer(v), labeler(v)));
    control.replaceChildren(...(all ? [option("", all)] : []), ...options);
    if (values.some(v => String(valuer(v)) === previous)) control.value = previous;
    window.FilterMenus?.refresh();
  }

  function syncHeader() {
    if (state.view !== "prospeccao") return;
    document.title = "Expresso | Prospecção e continuidade";
    el("page-title").textContent = "Prospecção e continuidade";
    el("page-description").textContent = "Acompanhe a conversão dos contratos e a qualidade da carteira.";
    el("updated").textContent = stamp(p.meta?.atualizado_em);
    el("sidebar-updated").textContent = stamp(p.meta?.atualizado_em);
    el("example-badge").hidden = !p.meta?.modo_exemplo;
    el("sync-state").textContent = p.meta?.carregado ? "Base disponível" : "Base não importada";
    el("sync-dot").classList.toggle("waiting", !p.meta?.carregado);
    el("base-total").textContent = p.data ? `${fmt(p.data.qualidade_dados.lojas)} lojas no recorte` : "Prospecção de credenciados";
  }

  function appliedFilters() {
    return Object.fromEntries([["inicio", "pro-start"], ["fim", "pro-month"], ["gerencia", "pro-region"], ["responsavel", "pro-person"], ["municipio", "pro-city"], ["ramo", "pro-branch"], ["safra", "pro-cohort"]].map(([key, id]) => [key, el(id).value]));
  }

  function params() {
    const query = new URLSearchParams({...p.applied, pagina: String(p.page), por_pagina: el("pro-page-size").value});
    for (const [key, id] of [["busca", "pro-search"], ["risco", "pro-risk"], ["treinamento", "pro-training"]]) {
      if (el(id).value.trim()) query.set(key, el(id).value.trim());
    }
    if (p.meta?.versao) query.set("versao", p.meta.versao);
    return query;
  }

  function loading(value) {
    p.loading = value;
    el("pro-content").setAttribute("aria-busy", String(value));
    el("pro-content").classList.toggle("pro-loading", value);
    el("pro-apply").disabled = value;
    el("pro-export").disabled = value || p.failed || !p.meta?.carregado;
  }

  async function refresh() {
    el("refresh").disabled = true;
    showError("");
    try {
      const first = !p.meta;
      p.meta = await getJSON("/api/prospeccao/metadados");
      el("pro-empty").hidden = p.meta.carregado;
      el("pro-content").hidden = !p.meta.carregado;
      syncHeader();
      if (!p.meta.carregado) return;
      let periods = [...p.meta.competencias].sort();
      const firstMonth = periods[0], lastMonth = periods.at(-1);
      if (firstMonth && lastMonth) {
        const continuous = []; let step = firstMonth;
        while (step <= lastMonth && continuous.length < 1200) { continuous.push(step); step = shiftMonth(step, 1); }
        if (step > lastMonth) periods = continuous;
      }
      select("pro-start", periods, null, month);
      select("pro-month", [...periods].reverse(), null, month);
      if (first || !el("pro-month").value) el("pro-month").value = p.meta.ultimo_mes_fechado;
      if (first || !el("pro-start").value) el("pro-start").value = p.meta.ultimo_mes_fechado;
      select("pro-region", p.meta.gerencias, "Todas as gerências");
      select("pro-person", p.meta.responsaveis, "Todos os responsáveis", r => r.nome, r => r.id);
      select("pro-city", p.meta.municipios, "Todos os municípios");
      select("pro-branch", p.meta.ramos, "Todos os ramos");
      select("pro-cohort", p.meta.safras, "Todas as safras", month);
      select("pro-activity-type", p.meta.tipos_atividade || [], "Todos os tipos");
      if (first) {
        try {
          const saved = JSON.parse(sessionStorage.getItem("expresso-periodo-filtros-v2") || "null");
          if (saved?.inicio && saved?.fim && saved.inicio <= saved.fim && saved.fim <= p.meta.data_corte.slice(0,7)) {
            for (const [key,id] of [["inicio","pro-start"],["fim","pro-month"],["gerencia","pro-region"],["responsavel","pro-person"],["municipio","pro-city"],["ramo","pro-branch"],["safra","pro-cohort"]]) {
              if ([...el(id).options].some(o => o.value === saved[key])) el(id).value = saved[key];
            }
          }
        } catch {}
      }
      peopleOptions();
      p.applied = appliedFilters(); dirty();
      await load();
    } catch (failure) { showError(failure.message); }
    finally { el("refresh").disabled = false; }
  }

  async function load(resetPage = false) {
    if (!p.meta?.carregado) return;
    if (!p.applied.inicio || !p.applied.fim || p.applied.inicio > p.applied.fim) {
      showError("Escolha um período válido: o início deve ser anterior ou igual ao fim.");
      if (p.committed) p.applied = {...p.committed}; dirty(); return;
    }
    if (resetPage) p.page = 1;
    p.controller?.abort();
    const controller = new AbortController();
    p.controller = controller;
    const request = ++p.request;
    p.failed = false;
    loading(true);
    showError("");
    try {
      const data = await getJSON(`/api/prospeccao/painel?${params()}`, controller.signal);
      if (request !== p.request) return;
      if (!data.carregado) { await refresh(); return; }
      p.data = data;
      p.page = data.pagina;
      p.committed = {...p.applied};
      remember(); dirty(); render();
      syncHeader();
      document.dispatchEvent(new CustomEvent("dashboard:prospeccao-data"));
    } catch (failure) {
      if (failure.name !== "AbortError" && request === p.request) {
        p.failed = true;
        if (p.committed) p.applied = {...p.committed}; dirty();
        showError(`${failure.message} Os resultados anteriores permanecem visíveis. Ajuste os filtros ou use Atualizar painel.`);
      }
    } finally { if (request === p.request) loading(false); }
  }

  function table(id, columns, rows, extra = "") {
    const wrapper = create("div", "pro-scroll");
    const grid = create("table", `pro-table ${extra}`);
    const head = create("thead"), header = create("tr"), body = create("tbody");
    for (const c of columns) {
      const th = create("th", c.numeric ? "numeric" : "", c.title);
      th.scope = "col";
      header.append(th);
    }
    head.append(header);
    for (const item of rows) {
      const row = create("tr");
      for (const c of columns) {
        const td = create("td", c.numeric ? "numeric" : "");
        const value = c.format ? c.format(item[c.key], item) : item[c.key] ?? "—";
        if (value instanceof Node) td.append(value);
        else td.textContent = value;
        row.append(td);
      }
      body.append(row);
    }
    if (!rows.length) {
      const row = create("tr"), cell = create("td", "table-message", "Nenhuma observação para este recorte.");
      cell.colSpan = columns.length;
      row.append(cell); body.append(row);
    }
    grid.append(head, body); wrapper.append(grid);
    el(id).replaceChildren(wrapper);
  }

  const col = (key, title, format, numeric = false) => ({key, title, format, numeric});
  const numeric = (key, title) => col(key, title, fmt, true);
  const percentage = (key, title) => col(key, title, pct, true);

  function measure(i) {
    return i.tipo === "taxa" ? pct(i.valor) : i.valor == null ? "—" : `${fmt(i.valor)}${i.tipo === "dias" ? " dias" : i.tipo === "meses" ? " meses" : ""}`;
  }

  function variation(value) {
    if (!value || value.variacao == null) return "Sem base";
    return `${value.variacao > 0 ? "+" : ""}${fmt(value.variacao)} ${value.unidade}`;
  }

  function card(label, value, note, primary = false, i = null) {
    const article = create("article", `metric${primary ? " primary-metric" : ""}`);
    article.append(create("div", "metric-label", label), create("strong", "", value), create("span", "", note));
    if (i) {
      const comp = create("div", "pro-comparison");
      comp.append(create("span", "", `${p.data?.periodo?.meses > 1 ? "Anterior" : "Mensal"} ${variation(i.mensal)}`), create("span", "", `Anual ${variation(i.anual)}`));
      article.append(comp);
    }
    return article;
  }

  function indicatorTable(id, prefix) {
    const items = Object.values(p.data.indicadores).filter(i => prefix.includes(i.codigo[0]));
    table(id, [col("titulo", "Indicador", (v, i) => {
      const cell = create("div", "", `${i.codigo} · ${v}`);
      if (i.nota) { cell.title = i.nota; cell.append(create("small", "", i.nota)); }
      return cell;
    }), col("valor", "Resultado", (v, i) => measure(i), true), col("denominador", "Base observada", (v, i) => i.denominador == null ? "—" : `${fmt(i.numerador ?? 0)} / ${fmt(i.denominador)}`, true),
      col("escopo", "Recorte"), col("mensal", p.data.periodo.meses > 1 ? "Δ período anterior" : "Δ mês anterior", variation, true), col("anual", "Δ período/ano anterior", variation, true)], items);
  }

  function trend() {
    const values = p.data.tendencia;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 780 230"); svg.setAttribute("class", "pro-chart");
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Emissões e aprovações mensais. Os valores estão na tabela logo abaixo.");
    function item(tag, attributes, text) {
      const node = document.createElementNS(ns, tag);
      Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
      if (text != null) node.textContent = text;
      return node;
    }
    const max = Math.max(5, ...values.flatMap(r => [r.emitidos, r.aprovados]));
    for (let i = 0; i <= 4; i++) {
      const y = 20 + i * 43;
      svg.append(item("line", {x1: 35, x2: 760, y1: y, y2: y, class: "axis"}), item("text", {x: 25, y: y + 4, "text-anchor": "end"}, fmt(max * (1 - i / 4))));
    }
    for (const [key, cls] of [["emitidos", "emissoes"], ["aprovados", "aprovacoes"]]) {
      const points = values.map((r, i) => [40 + i * (708 / Math.max(1, values.length - 1)), 192 - (r[key] / max) * 172]);
      svg.append(item("polyline", {points: points.map(v => v.join(",")).join(" "), class: cls}));
      points.forEach(([x, y], i) => {
        const dot = item("circle", {cx: x, cy: y, r: 4, class: cls});
        dot.append(item("title", {}, `${month(values[i].competencia)}: ${fmt(values[i][key])}${values[i].parcial ? " (parcial)" : ""}`));
        svg.append(dot);
      });
    }
    values.forEach((r, i) => { if (i % Math.max(1, Math.ceil(values.length / 7)) === 0 || i === values.length - 1) svg.append(item("text", {x: 40 + i * (708 / Math.max(1, values.length - 1)), y: 220, "text-anchor": "middle"}, month(r.competencia))); });
    el("pro-trend-chart").replaceChildren(svg);
    table("pro-trend-table", [col("competencia", "Mês", month), numeric("emitidos", "Emissões"), numeric("aprovados", "Aprovações"), numeric("negocios", "Negócios"), percentage("taxa_ativas", "Lojas com negócios"), col("parcial", "Fechamento", v => v ? "Parcial" : "Fechado")], values);
  }

  function badge(value) { return create("span", `pro-tag ${normalized(value)}`, value); }
  function storeLink(key, row) {
    const button = create("button", "pro-loja-button", key);
    button.type = "button";
    button.addEventListener("click", () => detail(row.chave_loja || key));
    return button;
  }

  function conditions() {
    if (!p.data) return;
    table("pro-conditions-table", [col("grupo", "Condição"), numeric("lojas", "Lojas"), numeric("observadas_pos_m4", "Observadas pós-M4"), numeric("ativas_pos_m4", "Com negócios"), percentage("taxa", "Atividade"),
      col("amostra_pequena", "Amostra", v => v ? "Menos de 5 observações" : "5 ou mais observações")], p.data.condicoes.filter(c => c.dimensao === el("pro-condition").value));
  }

  function render() {
    const d = p.data, i = d.indicadores;
    const period = d.periodo;
    el("pro-reference").textContent = period.inicio === period.fim ? month(period.fim) : `${month(period.inicio)} até ${month(period.fim)}`;
    el("pro-period-note").textContent = `Contratos e volume de negócios: ${month(period.inicio)} a ${month(period.fim)}. Risco, carteira, serviços e treinamento: fechamento em ${month(period.fim)}. Comparação anterior: intervalo imediatamente anterior com ${period.meses} mês(es).`;
    if (d.qualidade_dados.incompletas_periodo) el("pro-period-note").textContent += ` ${fmt(d.qualidade_dados.incompletas_periodo)} observação(ões) de loja/mês sem cobertura completa no período.`;
    el("pro-active-filters").replaceChildren(...[["gerencia","Gerência","pro-region"],["responsavel","Consultor","pro-person"],["municipio","Município","pro-city"],["ramo","Ramo","pro-branch"],["safra","Safra","pro-cohort"]].filter(([key]) => p.applied[key]).map(([key,label,id]) => {
      const text = [...el(id).options].find(o => o.value === p.applied[key])?.textContent || p.applied[key];
      const chip = create("button", "active-filter-chip", `${label}: ${text} ×`); chip.type = "button";
      chip.setAttribute("aria-label", `Remover filtro ${label}: ${text}`);
      chip.addEventListener("click", () => { el(id).value = ""; p.applied = appliedFilters(); dirty(); load(true); });
      return chip;
    }));
    el("pro-cutoff").textContent = day(d.data_corte);
    el("pro-close-state").textContent = d.fechamento;
    el("pro-close-state").classList.toggle("validado", d.fechamento === "VALIDADO");
    el("pro-rule").textContent = `M0 = inauguração · Regra ${d.versao_regra}`;
    el("pro-partial").hidden = !d.parcial;
    el("pro-kpis").replaceChildren(
      card("Contratos emitidos", measure(i.F01), "Emissões no período", false, i.F01),
      card("Aproveitamento da safra", measure(i.F03), `${fmt(i.F03.numerador)} aprovados / ${fmt(i.F03.denominador)} emitidos`, true, i.F03),
      card("Lojas com negócios", measure(i.Q03), `${fmt(i.Q03.numerador)} / ${fmt(i.Q03.denominador)} lojas em ${month(period.fim)}`, false, i.Q03),
      card("Lojas inativas em negócios", measure(i.Q09), `Situação em ${month(period.fim)}`, false, i.Q09));
    trend();
    const total = d.qualidade_dados.lojas;
    el("pro-risk-bars").replaceChildren(...["Ativo", "Atenção", "Risco crítico", "Inativo", "Indeterminado", "Em implantação", "Encerrado"].map(name => {
      const row = create("div", "pro-risk-row");
      const bar = create("meter"); bar.min = 0; bar.max = Math.max(total, 1); bar.value = d.riscos[name] || 0;
      bar.setAttribute("aria-label", `${name}: ${fmt(bar.value)} de ${fmt(total)} lojas`);
      row.append(create("span", "", name), bar, create("strong", "", fmt(d.riscos[name] || 0)));
      return row;
    }));
    el("pro-coverage-note").textContent = `${fmt(d.qualidade_dados.completas)} de ${fmt(d.qualidade_dados.cobertura_esperada)} lojas operantes no mês com cobertura completa em negócios e transações.`;
    const groupCols = [col("nome", "Gerência"), numeric("emitidos", "Emitidos"), numeric("aprovados", "Aprovados da safra"), percentage("aproveitamento", "Aproveitamento"), numeric("lojas", "Lojas"), numeric("negocios", "Negócios"), percentage("taxa_ativas", "Lojas com negócios"), numeric("inativas", "Inativas")];
    table("pro-regions-table", groupCols, d.gerencias);
    table("pro-people-table", [{...groupCols[0], title: "Consultor responsável"}, ...groupCols.slice(1), percentage("cobertura", "Cobertura de negócios")], d.responsaveis);
    el("pro-funnel").replaceChildren(...[["Emitidos", i.F01.valor, "Safra de emissão"], ["Aprovados", d.funil.aprovados_safra, "Aprovação registrada até o corte"], ["Originaram inauguração", d.funil.inaugurados_safra, "Contratos distintos com loja inaugurada"]].map(([label, value, note]) => {
      const node = create("div", "funnel-step"); node.append(create("span", "", label), create("strong", "", fmt(value)), create("small", "", note)); return node;
    }));
    el("pro-contract-state-note").textContent = `Situação final no corte: ${Object.entries(d.funil.situacoes_safra).map(([k, v]) => `${k.toLowerCase()}: ${fmt(v)}`).join(" · ") || "sem contratos"}. Cancelados após aprovação: ${fmt(d.funil.cancelados_apos_aprovacao)}. A janela de observação fixa é de ${fmt(p.meta.dias_observacao)} dias.`;
    indicatorTable("pro-funnel-indicators", "F"); indicatorTable("pro-quality-indicators", "Q"); indicatorTable("pro-training-indicators", "T");
    const cohortColumns = [col("safra", "Safra", month), numeric("lojas", "Lojas"), numeric("encerradas", "Encerradas")];
    for (const age of [1, 2, 3, 4, 5, 6, 9, 12]) cohortColumns.push(col("idades", `M${age}`, values => {
      const v = values[String(age)];
      const node = create("div", "", pct(v.valor));
      node.dataset.heat = v.valor == null ? "na" : String(Math.min(4, Math.floor(v.valor / 25)));
      node.append(create("small", "", `${fmt(v.numerador)} / ${fmt(v.denominador)}`));
      return node;
    }, true));
    table("pro-cohort-table", cohortColumns, d.safras, "pro-heatmap");
    el("pro-cohort-table").querySelectorAll("[data-heat]").forEach(node => node.parentElement.classList.add(`heat-${node.dataset.heat}`));
    conditions();
    table("pro-services-table", [col("nome", "Serviço"), col("tipo", "Tipo", v => v === "NEGOCIO" ? "Negócio" : "Transação"), numeric("produtoras", "Produtoras"), numeric("habilitadas_observaveis", "Habilitadas e observadas"), percentage("utilizacao", "Utilização"), numeric("habilitacoes_parciais", "Habilitações parciais"), col("sem_utilizacao", "Habilitadas sem uso", v => fmt(v.length), true)], d.servicos);
    table("pro-profiles-table", [col("perfil", "Perfil operacional"), numeric("lojas", "Lojas")], Object.entries(d.perfis).map(([perfil, lojas]) => ({perfil, lojas})));
    el("pro-diversification").textContent = `S02 · Mediana de categorias de negócios com produção por loja: ${fmt(i.S02.valor)}.`;
    table("pro-training-cohorts", [col("idade", "Marco", v => `M${v}`), col("treinamento", "Treinamento antes do marco"), numeric("lojas", "Observadas"), numeric("ativas", "Com negócios"), percentage("taxa", "Atividade"), col("amostra_pequena", "Amostra", v => v ? "Menos de 5 observações" : "5 ou mais observações")], d.treinamento_idade);
    table("pro-support-table", [col("chave_loja", "Loja", storeLink), col("razao_social", "Credenciado"), col("responsavel", "Responsável"), col("marco", "Suporte", v => `M${v}`), col("prevista", "Prazo", day), col("cadastrado", "Ação prevista", v => v ? "Cadastrada" : "Sem cadastro"), col("motivo", "Motivo informado")], d.pendencias_suporte || []);
    table("pro-stores-table", [col("chave_loja", "CHAVE_LOJA", storeLink), col("razao_social", "Credenciado"), col("responsavel", "Consultor"), col("idade", "Idade", v => `M${v}`), numeric("negocios", "Negócios"), numeric("transacoes", "Transações"), col("situacao_negocios", "Situação em negócios", badge), col("situacao_transacoes", "Situação em transações", badge), percentage("participacao_producao", "Participação na produção"), col("reativado", "Reativado", v => v ? "Sim" : "—"), col("treinamento", "Treinamento"), percentage("recorrencia_pos_m4", "Recorrência pós-M4")], d.lojas);
    el("pro-list-count").textContent = fmt(d.total_lojas);
    const start = d.total_lojas ? (d.pagina - 1) * d.por_pagina + 1 : 0;
    el("pro-page-info").textContent = `${fmt(start)}–${fmt(Math.min(d.pagina * d.por_pagina, d.total_lojas))} de ${fmt(d.total_lojas)} lojas`;
    el("pro-page-label").textContent = `${d.pagina} / ${d.paginas}`;
    el("pro-prev").disabled = d.pagina <= 1; el("pro-next").disabled = d.pagina >= d.paginas;
    const q = d.qualidade_dados;
    el("pro-data-kpis").replaceChildren(card("Cobertura completa", pct(q.cobertura), `${fmt(q.completas)} de ${fmt(q.cobertura_esperada)} lojas operantes`), card("Situação indeterminada", fmt(q.indeterminadas), "Sequência sem comprovação suficiente"), card("Avisos na carga", fmt(q.avisos), "Consulte os registros abaixo"), card("Sem vinculação no mês", fmt(q.sem_vinculo), `${fmt(q.suportes_sem_cadastro)} suportes vencidos sem cadastro`));
    table("pro-issues-table", [col("nivel", "Nível"), col("codigo", "Código"), col("mensagem", "Descrição"), col("origem", "Origem", v => v ? `${v.arquivo} · ${v.aba} · linha ${v.linha}` : "—")], q.itens);
    table("pro-sources-table", [col("tabela", "Tabela"), col("arquivo", "Arquivo"), numeric("linhas", "Linhas"), col("sha256", "Identificador da carga", v => v.slice(0, 16))], q.fontes);
    const latest = d.ultima_validacao;
    el("pro-validation-alert").hidden = latest?.estado !== "BLOQUEADO";
    el("pro-validation-alert").textContent = latest?.estado === "BLOQUEADO" ? `A última tentativa de importação foi bloqueada (${fmt(latest.erros)} erro(s)). O painel mantém a publicação anterior. ${latest.itens?.find(x => x.nivel === "ERRO")?.mensagem || ""}` : "";
  }

  function tab(name, focus = false) {
    p.tab = name;
    document.dispatchEvent(new CustomEvent("dashboard:prospeccao-tab", {detail: name}));
    document.querySelectorAll("[data-pro-tab]").forEach(button => {
      const selected = button.dataset.proTab === name;
      button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1;
      el(`pro-panel-${button.dataset.proTab}`).hidden = !selected;
      if (focus && selected) button.focus();
    });
  }

  async function detail(key) {
    const current = ++detailRequest;
    el("pro-loja-title").textContent = `Loja ${key}`;
    el("pro-loja-content").replaceChildren(create("p", "muted", "Carregando o histórico…"));
    if (!el("pro-loja-dialog").open) el("pro-loja-dialog").showModal();
    try {
      const query = new URLSearchParams({chave_loja: key, competencia: p.applied.fim, versao: p.meta.versao});
      const d = await getJSON(`/api/prospeccao/loja?${query}`);
      if (current !== detailRequest) return;
      const content = el("pro-loja-content");
      el("pro-loja-title").textContent = d.loja.RAZAO_SOCIAL;
      const cadastro = create("div", "pro-loja-grid");
      for (const [label, value] of [["CHAVE_LOJA", key], ["Município / UF", `${d.loja.MUNICIPIO || "—"} / ${d.loja.UF || "—"}`], ["Inauguração", day(d.loja.DATA_INAUGURACAO)], ["Ramo", d.loja.RAMO_ATIVIDADE || "—"], ["Encerramento", day(d.loja.DATA_ENCERRAMENTO)], ["Origem cadastral", `${d.loja._origem.arquivo} · linha ${d.loja._origem.linha}`]]) {
        const field = create("div"); field.append(create("span", "", label), create("strong", "", value)); cadastro.append(field);
      }
      content.replaceChildren(cadastro);
      const services = new Map(d.servicos.map(s => [s.ID_SERVICO, s.NOME]));
      for (const [id, heading] of [["pro-detail-history", "Produção mensal e situação"], ["pro-detail-production", "Produção por serviço e origem"], ["pro-detail-actions", "Treinamento e suportes"], ["pro-detail-services", "Habilitações cadastradas"]]) {
        content.append(create("h3", "", heading)); const holder = create("div"); holder.id = id; content.append(holder);
      }
      table("pro-detail-history", [col("competencia", "Mês", month), col("idade", "Idade", v => `M${v}`), numeric("negocios", "Negócios"), numeric("transacoes", "Transações"), col("situacao_negocios", "Negócios", badge), col("situacao_transacoes", "Transações", badge), col("cobertura_negocios", "Cobertura"), col("responsavel", "Responsável"), col("nunca_produziu", "Nunca produziu", v => v == null ? "Desconhecido" : v ? "Sim" : "Não")], d.historico);
      table("pro-detail-actions", [col("TIPO_ACAO", "Tipo"), col("MARCO_OPERACIONAL", "Marco", v => v == null ? "—" : `M${v}`), col("DATA_PREVISTA", "Previsto", day), col("DATA_REALIZADA", "Realizado", day), col("STATUS", "Situação"), col("COM_MULTIPLICADOR", "Multiplicador", v => v == null ? "Não informado" : v ? "Sim" : "Não"), col("ID_ACAO", "Conteúdo", v => d.conteudos_acoes.filter(a => a.ID_ACAO === v).map(a => services.get(a.ID_SERVICO) || a.ID_SERVICO).join(", ") || "—"), col("_origem", "Origem", v => `${v.arquivo} · linha ${v.linha}`)], d.acoes);
      table("pro-detail-production", [col("COMPETENCIA", "Mês", month), col("ID_SERVICO", "Serviço", v => services.get(v) || v), numeric("QTD_VALIDA", "Quantidade válida informada"), col("_origem", "Origem", v => `${v.arquivo} · ${v.aba} · linha ${v.linha}`)], d.producao);
      table("pro-detail-services", [col("ID_SERVICO", "Serviço", v => services.get(v) || v), col("DATA_INICIO", "Início", day), col("DATA_FIM", "Fim", day), col("SITUACAO", "Situação")], d.habilitacoes);
    } catch (failure) { if (current === detailRequest) el("pro-loja-content").replaceChildren(create("p", "pro-error-message", failure.message)); }
  }

  async function exportCSV() {
    el("pro-export").disabled = true;
    try {
      const response = await fetch(`/api/prospeccao/exportar.csv?${params()}`, {credentials: "same-origin"});
      if (!response.ok) throw new Error((await response.json()).erro || "Não foi possível exportar.");
      const url = URL.createObjectURL(await response.blob());
      const link = create("a"); link.href = url; link.download = "prospeccao_filtrada.csv";
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (failure) { showError(failure.message); }
    finally { el("pro-export").disabled = false; }
  }

  el("nav-prospeccao").addEventListener("click", () => switchView("prospeccao"));
  el("pro-filters").addEventListener("submit", event => { event.preventDefault(); p.applied = appliedFilters(); dirty(); load(true); });
  el("pro-clear").addEventListener("click", () => {
    for (const id of ["pro-region", "pro-person", "pro-city", "pro-branch", "pro-cohort", "pro-search", "pro-risk", "pro-training"]) el(id).value = "";
    el("pro-start").value = p.meta.ultimo_mes_fechado; el("pro-month").value = p.meta.ultimo_mes_fechado;
    p.applied = appliedFilters(); dirty(); load(true);
  });
  el("pro-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => load(true), 350); });
  for (const id of ["pro-risk", "pro-training", "pro-page-size"]) el(id).addEventListener("change", () => load(true));
  el("pro-prev").addEventListener("click", () => { if (p.page > 1) { p.page--; load(); } });
  el("pro-next").addEventListener("click", () => { if (p.data && p.page < p.data.paginas) { p.page++; load(); } });
  el("pro-condition").addEventListener("change", conditions);
  el("pro-export").addEventListener("click", exportCSV);
  el("pro-open-risk").addEventListener("click", () => tab("risco", true));
  document.querySelectorAll("[data-pro-tab]").forEach(button => {
    button.addEventListener("click", () => tab(button.dataset.proTab));
    button.addEventListener("keydown", event => {
      const buttons = [...document.querySelectorAll("[data-pro-tab]")], index = buttons.indexOf(button);
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % buttons.length;
      if (event.key === "ArrowLeft") next = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = buttons.length - 1;
      if (next !== undefined) { event.preventDefault(); tab(buttons[next].dataset.proTab, true); }
    });
  });
  document.addEventListener("dashboard:view", event => { if (event.detail === "prospeccao") { if (!p.meta) refresh(); else syncHeader(); } });
  setInterval(async () => {
    if (document.hidden || state.view !== "prospeccao" || p.loading || !p.meta) return;
    try {
      const meta = await getJSON("/api/prospeccao/metadados");
      if (meta.versao !== p.meta.versao) await refresh();
    } catch (failure) { /* A última publicação continua visível; Atualizar painel permite tentar novamente. */ }
  }, 60000);
  el("pro-filters").addEventListener("change", () => { peopleOptions(); dirty(); });
  document.querySelectorAll("[data-pro-range]").forEach(button => button.addEventListener("click", () => {
    const end = p.meta?.ultimo_mes_fechado;
    if (!end) return;
    let start = button.dataset.proRange === "ano" ? `${end.slice(0,4)}-01` : shiftMonth(end, 1 - Number(button.dataset.proRange));
    const first = [...el("pro-start").options].map(o => o.value).sort()[0];
    if (start < first) start = first;
    el("pro-start").value = start; el("pro-month").value = end;
    p.applied = appliedFilters(); dirty(); load(true);
  }));
  window.Prospec = {refresh, syncHeader, filters: () => ({...p.applied}), metadata: () => p.meta, activeTab: () => p.tab, openStore: detail,
    selectConsultor(id) {
      if (![...el("pro-person").options].some(o => o.value === id)) return;
      for (const [key,control] of [["inicio","pro-start"],["fim","pro-month"],["gerencia","pro-region"],["municipio","pro-city"],["ramo","pro-branch"],["safra","pro-cohort"]]) el(control).value = p.applied[key] || "";
      el("pro-person").value = id; p.applied = appliedFilters(); dirty(); load(true);
    }};
  switchView("prospeccao");
}());
