"""Importação transacional e consultas do módulo Bradesco Expresso.

Uso independente: python prospeccao.py --config configuracao.json
Uso na rotina: from prospeccao import atualizar_prospeccao
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from integracao import PADRAO_CONFIG, ErroImportacao, carregar_configuracao, normalizar
from prospeccao_calculos import analise, resumir_lojas
from prospeccao_dados import GERENCIAS, VERSAO_REGRA, carregar_entradas, configuracao_prospeccao, mes
from periodos import intervalo


def gravar_relatorio(config, relatorio):
    destino = config.arquivo.parent / 'relatorios' / 'validacao_prospeccao.json'
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name('.' + uuid.uuid4().hex + '.tmp')
    temporario.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
    temporario.replace(destino)


def preparar_prospeccao(config):
    op = configuracao_prospeccao(config)
    if op is None:
        return None
    instante = datetime.now(timezone.utc).isoformat()
    try:
        tabelas, validacao, fontes, mapeamentos = carregar_entradas(config, op)
        resumos = resumir_lojas(tabelas, op)
    except (ErroImportacao, OSError, ValueError) as exc:
        relatorio = getattr(exc, 'relatorio', {'erros': 1, 'avisos': 0, 'itens': [dict(nivel='ERRO', codigo='CARGA_RECUSADA', mensagem=str(exc), origem=None)]})
        gravar_relatorio(config, dict(relatorio, estado='BLOQUEADO', analisado_em=instante, publicado=False))
        raise ErroImportacao(str(exc)) from exc
    auditoria = {'erros': 0, 'avisos': validacao.avisos, 'itens': validacao.itens, 'registros_rejeitados': 0}
    base = {'versao': uuid.uuid4().hex, 'atualizado_em': instante, 'opcoes': op, 'versao_regra': VERSAO_REGRA,
            'tabelas': tabelas, 'resumos': resumos, 'fontes': fontes, 'mapeamentos': mapeamentos, 'auditoria': auditoria}
    gravar_relatorio(config, dict(auditoria, estado='REVISAR' if validacao.avisos else 'APTO', analisado_em=instante, publicado=False))
    return base


def publicar_prospeccao(conn, config):
    """Participa da transação do chamador; nunca confirma uma carga pela metade."""
    base = preparar_prospeccao(config)
    if base is None:
        return None
    conn.execute('CREATE TABLE IF NOT EXISTS pro_snapshot (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS pro_controle_carga (id_carga TEXT PRIMARY KEY, data_corte TEXT, importado_em TEXT, versao_regra TEXT, fontes TEXT)')
    conn.execute('INSERT OR REPLACE INTO pro_snapshot VALUES (?, ?)', ('atual', json.dumps(base, ensure_ascii=False)))
    conn.execute('INSERT INTO pro_controle_carga VALUES (?, ?, ?, ?, ?)',
                 (base['versao'], base['opcoes']['data_corte'], base['atualizado_em'], VERSAO_REGRA, json.dumps(base['fontes'], ensure_ascii=False)))
    conn.execute('DROP TABLE IF EXISTS resumo_loja_mes')
    conn.execute('CREATE TABLE resumo_loja_mes (chave_loja TEXT NOT NULL, competencia TEXT NOT NULL, gerencia TEXT, id_responsavel TEXT, payload TEXT NOT NULL, PRIMARY KEY (chave_loja, competencia))')
    conn.executemany('INSERT INTO resumo_loja_mes VALUES (?, ?, ?, ?, ?)',
        ((r['chave_loja'], r['competencia'], r['gerencia'], r['id_responsavel'], json.dumps(r, ensure_ascii=False)) for r in base['resumos']))
    conn.execute('CREATE INDEX idx_resumo_competencia ON resumo_loja_mes (competencia)')
    return {'versao': base['versao'], 'lojas': len(base['tabelas']['credenciados']),
            'resumos_mensais': len(base['resumos']), 'avisos': base['auditoria']['avisos']}


def atualizar_prospeccao(config_path=PADRAO_CONFIG):
    config = carregar_configuracao(config_path)
    if configuracao_prospeccao(config) is None:
        raise ErroImportacao('Ative prospeccao.ativo na configuração antes de importar.')
    config.banco.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.banco, timeout=60) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('BEGIN IMMEDIATE')
        resultado = publicar_prospeccao(conn, config)
    return resultado


@lru_cache(maxsize=2)
def decodificar(versao, payload):
    return json.loads(payload)


def ler_base(conn, config):
    if configuracao_prospeccao(config) is None or conn is None:
        return None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pro_snapshot'").fetchone():
        return None
    linha = conn.execute('SELECT valor FROM pro_snapshot WHERE chave=?', ('atual',)).fetchone()
    if linha is None:
        return None
    # Cache contém apenas o snapshot publicado; funções de consulta não o alteram.
    payload = linha[0]
    versao = json.loads(payload)['versao']
    return decodificar(versao, payload)


def metadados(base):
    if base is None:
        return {'carregado': False, 'mensagem': 'Importe as bases de prospecção para começar.', 'gerencias': GERENCIAS}
    meses = {r['competencia'] for r in base['resumos']}
    meses.update(mes(c['DATA_EMISSAO']) for c in base['tabelas']['contratos'] if c['DATA_EMISSAO'] <= base['opcoes']['data_corte'])
    meses.update([base['opcoes']['ultimo_mes_fechado'], mes(base['opcoes']['data_corte'])])
    from consultores import TIPOS_ATIVIDADE
    regioes_responsavel = {}
    for r in base['tabelas']['vinculacoes']:
        regioes_responsavel.setdefault(r['ID_RESPONSAVEL'], set()).add(r['GERENCIA'])
    for r in base['tabelas']['contratos']:
        regioes_responsavel.setdefault(r['RESPONSAVEL_ORIGEM'], set()).add(r['GERENCIA_ORIGEM'])
    return {'carregado': True, 'versao': base['versao'], 'atualizado_em': base['atualizado_em'],
        'tipos_atividade': TIPOS_ATIVIDADE,
        'data_corte': base['opcoes']['data_corte'], 'ultimo_mes_fechado': base['opcoes']['ultimo_mes_fechado'],
        'modo_exemplo': base['opcoes'].get('modo_exemplo', False), 'versao_regra': VERSAO_REGRA,
        'dias_observacao': base['opcoes']['dias_observacao'], 'competencias': sorted(meses, reverse=True),
        'gerencias': GERENCIAS, 'responsaveis': [{'id': r['ID_RESPONSAVEL'], 'nome': r['NOME'], 'gerencias': sorted(regioes_responsavel.get(r['ID_RESPONSAVEL'], set()))} for r in base['tabelas']['responsaveis']],
        'municipios': sorted({r['MUNICIPIO'] for r in base['tabelas']['credenciados'] if r['MUNICIPIO']}),
        'ramos': sorted({r['RAMO_ATIVIDADE'] for r in base['tabelas']['credenciados'] if r['RAMO_ATIVIDADE']}),
        'safras': sorted({mes(r['DATA_INAUGURACAO']) for r in base['tabelas']['credenciados']}, reverse=True)}


PARAMETROS = {'competencia', 'inicio', 'fim', 'gerencia', 'responsavel', 'municipio', 'ramo', 'safra', 'busca', 'risco', 'treinamento', 'pagina', 'por_pagina', 'versao', 'chave_loja', 'tipo_atividade', 'atividade_busca', 'atividade_pagina', 'atividade_por_pagina'}


def validar_parametros(params, base):
    if set(params) - PARAMETROS:
        raise ValueError('Parâmetro de prospecção desconhecido.')
    if any(len(v) > 500 for v in params.values()):
        raise ValueError('Filtro muito longo.')
    if params.get('versao') and base and params['versao'] != base['versao']:
        raise ValueError('A base de prospecção mudou. Atualize o painel.')
    if params.get('competencia'):
        if mes(params['competencia']) != params['competencia']:
            raise ValueError('Use competência no formato AAAA-MM.')
    if params.get('safra'):
        if mes(params['safra']) != params['safra']:
            raise ValueError('Use safra no formato AAAA-MM.')
    if base is not None:
        intervalo(base, params)


def consultar_prospeccao(conn, config, params):
    base = ler_base(conn, config)
    validar_parametros(params, base)
    if base is None:
        return metadados(None)
    resultado = analise(base, params)
    relatorio = config.arquivo.parent / 'relatorios' / 'validacao_prospeccao.json'
    if relatorio.is_file() and relatorio.stat().st_size < 2_000_000:
        resultado['ultima_validacao'] = json.loads(relatorio.read_text(encoding='utf-8'))
    return resultado


def consultar_consultores(conn, config, params, *, exportar=False):
    base = ler_base(conn, config)
    validar_parametros(params, base)
    if base is None:
        if exportar:
            raise ValueError('Importe as bases antes de exportar as atividades.')
        return metadados(None)
    from consultores import TIPOS_ATIVIDADE, csv_consultores, painel_consultores
    if params.get('tipo_atividade') and params['tipo_atividade'] not in TIPOS_ATIVIDADE:
        raise ValueError('Tipo de atividade desconhecido.')
    return csv_consultores(base, params) if exportar else painel_consultores(base, params)


def detalhe_loja(conn, config, params):
    base = ler_base(conn, config)
    validar_parametros(params, base)
    if base is None:
        return metadados(None)
    chave = params.get('chave_loja')
    loja = next((r for r in base['tabelas']['credenciados'] if r['CHAVE_LOJA'] == chave), None)
    if loja is None:
        raise ValueError('Loja não encontrada.')
    _, ref, _ = intervalo(base, params)
    if mes(ref) > mes(base['opcoes']['data_corte']):
        raise ValueError('Competência posterior à data de corte.')
    historico = [r for r in base['resumos'] if r['chave_loja'] == chave and r['competencia'] <= ref]
    acoes = [r for r in base['tabelas']['acompanhamentos'] if r['CHAVE_LOJA'] == chave]
    produtos = [r for r in base['tabelas']['producao'] if r['CHAVE_LOJA'] == chave and r['COMPETENCIA'] <= ref]
    habilitacoes = [r for r in base['tabelas']['habilitacoes'] if r['CHAVE_LOJA'] == chave]
    return {'carregado': True, 'loja': loja, 'historico': historico, 'acoes': acoes, 'producao': produtos,
            'habilitacoes': habilitacoes, 'servicos': base['tabelas']['servicos'],
            'conteudos_acoes': [r for r in base['tabelas']['acao_servico'] if r['ID_ACAO'] in {a['ID_ACAO'] for a in acoes}]}


def csv_prospeccao(conn, config, params):
    base = ler_base(conn, config)
    validar_parametros(params, base)
    if base is None:
        raise ValueError('Importe a prospecção antes de exportar.')
    # O mesmo recorte, a mesma busca e o mesmo filtro de risco são usados em todas as páginas.
    from prospeccao_calculos import filtrar
    _, referencia, _ = intervalo(base, params)
    if referencia > mes(base['opcoes']['data_corte']):
        raise ValueError('Competência posterior à data de corte.')
    linhas = filtrar([r for r in base['resumos'] if r['competencia'] == referencia], params)
    total_negocios = sum(r['negocios'] for r in linhas if r['negocios'] is not None)
    from prospeccao_calculos import taxa
    linhas = [dict(r, participacao_producao=taxa(r['negocios'], total_negocios) if r['negocios'] is not None else None) for r in linhas]
    busca = normalizar(params.get('busca', '')).strip()
    linhas = [r for r in linhas if (not params.get('risco') or r['situacao_negocios'] == params['risco']) and
        (not params.get('treinamento') or r['treinamento'] == params['treinamento']) and
        (not busca or busca in normalizar(' '.join(str(r.get(c) or '') for c in ['chave_loja', 'razao_social', 'cnpj', 'municipio', 'responsavel'])))]
    campos = ['chave_loja', 'razao_social', 'competencia', 'gerencia', 'responsavel', 'municipio', 'uf', 'ramo', 'safra',
              'idade', 'negocios', 'transacoes', 'situacao_negocios', 'situacao_transacoes', 'meses_sem_negocios',
              'reativado', 'nunca_produziu', 'recorrencia_pos_m4', 'participacao_producao', 'perfil', 'treinamento', 'com_multiplicador',
              'cobertura_negocios', 'cobertura_transacoes', 'data_corte', 'versao_regra']
    saida = io.StringIO(newline='')
    escritor = csv.writer(saida, delimiter=';', lineterminator='\r\n')
    escritor.writerow(campos)
    def seguro(valor):
        if valor is None:
            return ''
        if isinstance(valor, bool):
            return 'Sim' if valor else 'Não'
        texto = str(valor)
        if texto.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            texto = "'" + texto
        if isinstance(valor, float):
            texto = texto.replace('.', ',')
        return texto
    for r in linhas:
        escritor.writerow([seguro(r[c]) for c in campos])
    return saida.getvalue().encode('utf-8-sig')


def main():
    parser = argparse.ArgumentParser(description='Valida e publica as bases de prospecção no dashboard.')
    parser.add_argument('--config', default=str(PADRAO_CONFIG))
    parser.add_argument('--validar', action='store_true', help='Analisa e gera relatório sem publicar.')
    args = parser.parse_args()
    try:
        if args.validar:
            base = preparar_prospeccao(carregar_configuracao(args.config))
            if base is None:
                raise ErroImportacao('Ative a prospecção na configuração.')
            print(f"Validação concluída: {base['auditoria']['avisos']} aviso(s). Consulte relatorios/validacao_prospeccao.json.")
        else:
            resumo = atualizar_prospeccao(args.config)
            print(f"Prospecção publicada: {resumo['lojas']} lojas, {resumo['resumos_mensais']} observações mensais, {resumo['avisos']} aviso(s).")
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Importação recusada: {exc}\n')


if __name__ == '__main__':
    main()
