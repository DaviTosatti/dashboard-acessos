"""Atividades rastreáveis por origem, carteira mensal e executor informado."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date

from integracao import normalizar
from periodos import intervalo
from prospeccao_calculos import criar_indices, vinculo_inauguracao
from prospeccao_dados import fim_mes, mes, deslocar_mes

TIPOS_ATIVIDADE = ['Emissão de contrato', 'Aprovação', 'Reprovação', 'Desistência', 'Cancelamento',
    'Pendência de contrato', 'Inauguração', 'Produção de negócios', 'Transações bancárias',
    'Treinamento realizado', 'Suporte M2 realizado', 'Suporte M4 realizado',
    'Treinamento pendente', 'Suporte M2 pendente', 'Suporte M4 pendente', 'Habilitação de serviço']


def atividades(base, params):
    inicio, fim, _ = intervalo(base, params)
    de, ate = inicio + '-01', min(fim_mes(fim), base['opcoes']['data_corte'])
    ix = criar_indices(base['tabelas'])
    resumo = {(r['chave_loja'], r['competencia']): r for r in base['resumos']}
    origens_loja = {}
    for c in base['tabelas']['contrato_loja']:
        if vinculo_inauguracao(c, ix['credenciados'][c['CHAVE_LOJA']]):
            origens_loja[c['CHAVE_LOJA']] = ix['contratos'][c['ID_CONTRATO']]
    def vinculo(chave, dia):
        v = next((v for v in ix['vinculacoes'][chave] if v['INICIO_VIGENCIA'] <= dia and (not v['FIM_VIGENCIA'] or v['FIM_VIGENCIA'] >= dia)), None)
        if v:
            return v['ID_RESPONSAVEL'], v['GERENCIA']
        loja = ix['credenciados'][chave]
        origem = origens_loja.get(chave)
        if origem and dia < loja['DATA_INAUGURACAO']:
            return origem['RESPONSAVEL_ORIGEM'], origem['GERENCIA_ORIGEM']
        return None, 'Sem vinculação'
    itens = []
    def registrar(ident, dia, tipo, responsavel, gerencia, atribuicao, *, chave=None, contrato=None,
                  descricao='', quantidade=None, informada=None, completo=True, origem=None, negocio=False, transacao=False, natureza='evento'):
        if not dia or not de <= dia[:10] <= ate:
            return
        loja = ix['credenciados'].get(chave, {})
        pessoa = ix['responsaveis'].get(responsavel, {})
        r = dict(id=ident, data=dia[:10], competencia=mes(dia), tipo=tipo, natureza=natureza,
                 id_responsavel=responsavel, responsavel=pessoa.get('NOME', 'Sem executor/responsável informado'),
                 gerencia=gerencia or 'Sem vinculação', atribuicao=atribuicao, chave_loja=chave,
                 razao_social=loja.get('RAZAO_SOCIAL'), id_contrato=contrato, descricao=descricao,
                 quantidade=quantidade, quantidade_informada=informada, completo=completo,
                 origem=origem, negocios=(quantidade or 0) if negocio else 0,
                 transacoes=(quantidade or 0) if transacao else 0)
        if params.get('gerencia') and normalizar(r['gerencia']) != normalizar(params['gerencia']):
            return
        if params.get('responsavel') and responsavel != params['responsavel']:
            return
        if any(params.get(c) for c in ['municipio', 'ramo', 'safra']):
            candidatas = [loja] if loja else [ix['credenciados'][v['CHAVE_LOJA']] for v in ix['contrato_loja'].get(contrato, [])]
            if not any((not params.get('municipio') or normalizar(l.get('MUNICIPIO')) == normalizar(params['municipio'])) and
                       (not params.get('ramo') or normalizar(l.get('RAMO_ATIVIDADE')) == normalizar(params['ramo'])) and
                       (not params.get('safra') or mes(l['DATA_INAUGURACAO']) == params['safra']) for l in candidatas):
                return
        if params.get('tipo_atividade') and tipo != params['tipo_atividade']:
            return
        busca = normalizar(params.get('atividade_busca', '')).strip()
        if busca and busca not in normalizar(' '.join(str(r.get(c) or '') for c in ['responsavel', 'gerencia', 'tipo', 'id_contrato', 'chave_loja', 'razao_social', 'descricao'])):
            return
        itens.append(r)
    for c in base['tabelas']['contratos']:
        ident = c['ID_CONTRATO']
        dados = dict(contrato=ident, origem=c['_origem'])
        registrar('emissao:' + ident, c['DATA_EMISSAO'], 'Emissão de contrato', c['RESPONSAVEL_ORIGEM'], c['GERENCIA_ORIGEM'], 'Origem do contrato', **dados)
        nomes = {'APROVADO': 'Aprovação', 'REPROVADO': 'Reprovação', 'DESISTENCIA': 'Desistência', 'CANCELADO': 'Cancelamento', 'PENDENTE': 'Pendência de contrato'}
        for evento in ix['status_contrato'][ident]:
            registrar('decisao:' + evento['ID_EVENTO'], evento['DATA_EVENTO'], nomes[evento['STATUS']], c['RESPONSAVEL_ORIGEM'], c['GERENCIA_ORIGEM'], 'Origem do contrato; executor da decisão não consta na base',
                      contrato=ident, descricao=evento['MOTIVO'] or '', origem=evento['_origem'])
    for loja in base['tabelas']['credenciados']:
        chave = loja['CHAVE_LOJA']
        origem = origens_loja.get(chave)
        pessoa, gerencia = (origem['RESPONSAVEL_ORIGEM'], origem['GERENCIA_ORIGEM']) if origem else vinculo(chave, loja['DATA_INAUGURACAO'])
        registrar('inauguracao:' + chave, loja['DATA_INAUGURACAO'], 'Inauguração', pessoa, gerencia, 'Origem do contrato' if origem else 'Vínculo da loja na inauguração',
                  chave=chave, contrato=origem['ID_CONTRATO'] if origem else None, origem=loja['_origem'])
        acoes = ix['acompanhamentos'][chave]
        for marco in [2, 4]:
            if any(a['TIPO_ACAO'] == 'SUPORTE' and a['MARCO_OPERACIONAL'] == marco for a in acoes):
                continue
            prazo = fim_mes(deslocar_mes(loja['DATA_INAUGURACAO'], marco))
            if loja['DATA_ENCERRAMENTO'] and loja['DATA_ENCERRAMENTO'] < prazo:
                continue
            pessoa, gerencia = vinculo(chave, prazo)
            registrar(f'pendencia:{chave}:{marco}', prazo, f'Suporte M{marco} pendente', pessoa, gerencia, 'Encaminhamento ao responsável no prazo', chave=chave,
                      descricao='Ação não cadastrada. Prazo analítico do marco.', origem=loja['_origem'], natureza='pendencia')
    for r in base['tabelas']['producao']:
        if not inicio <= r['COMPETENCIA'] <= fim or r['QTD_VALIDA'] <= 0:
            continue
        servico = ix['servicos'][r['ID_SERVICO']]
        loja_mes = resumo.get((r['CHAVE_LOJA'], r['COMPETENCIA']))
        if not loja_mes or not loja_mes['operou_mes']:
            continue
        negocio = servico['TIPO_ATIVIDADE'] == 'NEGOCIO'
        completo = loja_mes['negocios' if negocio else 'transacoes'] is not None
        registrar(f"producao:{r['CHAVE_LOJA']}:{r['COMPETENCIA']}:{r['ID_SERVICO']}", min(fim_mes(r['COMPETENCIA']), ate),
            'Produção de negócios' if negocio else 'Transações bancárias', loja_mes['id_responsavel'], loja_mes['gerencia'], 'Carteira no fechamento da competência; não identifica quem realizou cada operação',
            chave=r['CHAVE_LOJA'], descricao=servico['NOME'], quantidade=r['QTD_VALIDA'] if completo else None,
            informada=r['QTD_VALIDA'], completo=completo, negocio=negocio, transacao=not negocio, origem=r['_origem'], natureza='producao')
    for a in base['tabelas']['acompanhamentos']:
        realizada = a['DATA_REALIZADA']
        prazo = a['DATA_PREVISTA']
        pessoa_vinculo, gerencia = vinculo(a['CHAVE_LOJA'], realizada or prazo or ate)
        treinamento = a['TIPO_ACAO'] == 'TREINAMENTO'
        titulo = 'Treinamento' if treinamento else f"Suporte M{a['MARCO_OPERACIONAL']}"
        if realizada:
            registrar('acao:' + a['ID_ACAO'], realizada, titulo + ' realizado', a['ID_EXECUTOR'], gerencia,
                'Executor informado na ação' if a['ID_EXECUTOR'] else 'Executor não informado; sem crédito individual de execução', chave=a['CHAVE_LOJA'],
                descricao=a['MODALIDADE'] or '', origem=a['_origem'], natureza='acompanhamento')
        if prazo and (not realizada or realizada > ate):
            loja = ix['credenciados'][a['CHAVE_LOJA']]
            if loja['DATA_ENCERRAMENTO'] and loja['DATA_ENCERRAMENTO'] < prazo:
                continue
            pessoa_prazo, regiao_prazo = vinculo(a['CHAVE_LOJA'], prazo)
            registrar('prazo:' + a['ID_ACAO'], prazo, titulo + ' pendente', a['ID_EXECUTOR'] or pessoa_prazo, regiao_prazo,
                'Executor previsto' if a['ID_EXECUTOR'] else 'Encaminhamento ao responsável no prazo', chave=a['CHAVE_LOJA'],
                descricao=a['MOTIVO_NAO_REALIZACAO'] or 'Sem realização até o fim do período.', origem=a['_origem'], natureza='pendencia')
    for h in base['tabelas']['habilitacoes']:
        if h['SITUACAO'] != 'HABILITADO':
            continue
        pessoa, gerencia = vinculo(h['CHAVE_LOJA'], h['DATA_INICIO'])
        registrar('habilitacao:' + h['ID_HABILITACAO'], h['DATA_INICIO'], 'Habilitação de serviço', pessoa, gerencia, 'Responsável pela carteira na data; executor não informado',
                  chave=h['CHAVE_LOJA'], descricao=ix['servicos'][h['ID_SERVICO']]['NOME'], origem=h['_origem'])
    itens.sort(key=lambda r: (r['data'], r['id']), reverse=True)
    return itens


def resumir_consultores(itens, base, params):
    grupos = defaultdict(list)
    for r in itens:
        grupos[r['id_responsavel']].append(r)
    gerencias = defaultdict(set)
    # Uma carteira sem eventos positivos continua aparecendo no resumo da região.
    if not params.get('tipo_atividade') and not params.get('atividade_busca'):
        de, ate, _ = intervalo(base, params)
        lojas = {r['CHAVE_LOJA']: r for r in base['tabelas']['credenciados']}
        for v in base['tabelas']['vinculacoes']:
            if v['INICIO_VIGENCIA'] > min(fim_mes(ate), base['opcoes']['data_corte']) or (v['FIM_VIGENCIA'] and v['FIM_VIGENCIA'] < de + '-01'):
                continue
            if params.get('gerencia') and normalizar(v['GERENCIA']) != normalizar(params['gerencia']):
                continue
            if params.get('responsavel') and v['ID_RESPONSAVEL'] != params['responsavel']:
                continue
            l = lojas[v['CHAVE_LOJA']]
            if any(params.get(p) and normalizar(l[c]) != normalizar(params[p]) for p,c in [('municipio','MUNICIPIO'),('ramo','RAMO_ATIVIDADE')]):
                continue
            if params.get('safra') and mes(l['DATA_INAUGURACAO']) != params['safra']:
                continue
            grupos[v['ID_RESPONSAVEL']]
            gerencias[v['ID_RESPONSAVEL']].add(v['GERENCIA'])
        if not any(params.get(k) for k in ['gerencia','municipio','ramo','safra']):
            for r in base['tabelas']['responsaveis']:
                if not params.get('responsavel') or r['ID_RESPONSAVEL'] == params['responsavel']:
                    grupos[r['ID_RESPONSAVEL']]
    pessoas = {r['ID_RESPONSAVEL']: r for r in base['tabelas']['responsaveis']}
    linhas = []
    for ident, grupo in grupos.items():
        def contratos(tipo):
            return len({r['id_contrato'] for r in grupo if r['tipo'] == tipo})
        linhas.append({'id': ident, 'nome': pessoas.get(ident, {}).get('NOME', 'Sem executor/responsável informado'), 'gerencias': ', '.join(sorted({r['gerencia'] for r in grupo} | gerencias[ident])) or 'Sem vínculo no período',
            'registros': len(grupo), 'emitidos': contratos('Emissão de contrato'), 'aprovados': contratos('Aprovação'),
            'inauguracoes': sum(r['tipo'] == 'Inauguração' for r in grupo),
            'lojas': len({r['chave_loja'] for r in grupo if r['chave_loja']}),
            'negocios': sum(r['negocios'] for r in grupo), 'transacoes': sum(r['transacoes'] for r in grupo),
            'treinamentos': sum(r['tipo'] == 'Treinamento realizado' for r in grupo),
            'suportes': sum(r['tipo'] in {'Suporte M2 realizado', 'Suporte M4 realizado'} for r in grupo),
            'pendencias': sum(r['natureza'] == 'pendencia' for r in grupo),
            'producao_sem_cobertura': sum(not r['completo'] for r in grupo)})
    return sorted(linhas, key=lambda r: normalizar(r['nome']))


def painel_consultores(base, params):
    itens = atividades(base, params)
    pagina = int(params.get('atividade_pagina', 1))
    tamanho = int(params.get('atividade_por_pagina', 25))
    if pagina < 1 or tamanho not in {25, 50, 100}:
        raise ValueError('Paginação de atividades inválida. Use 25, 50 ou 100 registros por página.')
    paginas = max(1, (len(itens) + tamanho - 1) // tamanho)
    pagina = min(pagina, paginas)
    resumos = resumir_consultores(itens, base, params)
    de, ate, duracao = intervalo(base, params)
    return {'carregado': True, 'versao': base['versao'], 'periodo': {'inicio': de, 'fim': ate, 'meses': duracao},
            'consultores': resumos, 'atividades': itens[(pagina - 1) * tamanho:pagina * tamanho],
            'total': len(itens), 'pagina': pagina, 'paginas': paginas, 'por_pagina': tamanho,
            'totais': {'consultores': len([r for r in resumos if r['id']]), 'emitidos': sum(r['emitidos'] for r in resumos),
                'aprovados': sum(r['aprovados'] for r in resumos), 'negocios': sum(r['negocios'] for r in resumos),
                'transacoes': sum(r['transacoes'] for r in resumos),
                'acompanhamentos': sum(r['treinamentos'] + r['suportes'] for r in resumos if r['id']),
                'sem_executor': sum(r['natureza'] == 'acompanhamento' and not r['id_responsavel'] for r in itens),
                'pendencias': sum(r['pendencias'] for r in resumos), 'producao_sem_cobertura': sum(not r['completo'] for r in itens)}}


def csv_consultores(base, params):
    linhas = atividades(base, params)
    campos = ['data', 'competencia', 'responsavel', 'id_responsavel', 'gerencia', 'tipo', 'natureza', 'id_contrato',
              'chave_loja', 'razao_social', 'descricao', 'quantidade', 'quantidade_informada', 'completo', 'atribuicao', 'arquivo', 'aba', 'linha']
    saida = io.StringIO(newline='')
    escritor = csv.DictWriter(saida, fieldnames=campos, delimiter=';', lineterminator='\r\n')
    escritor.writeheader()
    def seguro(valor):
        if valor is None:
            return ''
        if isinstance(valor, bool):
            return 'Sim' if valor else 'Não'
        texto = str(valor)
        return "'" + texto if texto.lstrip().startswith(('=', '+', '-', '@')) else texto
    for r in linhas:
        registro = {**r, **(r['origem'] or {})}
        escritor.writerow({c: seguro(registro.get(c)) for c in campos})
    return saida.getvalue().encode('utf-8-sig')
