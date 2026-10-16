"""Indicadores puros: safras, cobertura, idades e atribuição histórica."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from integracao import ErroImportacao, normalizar
from prospeccao_dados import GERENCIAS, VERSAO_REGRA, deslocar_mes, fim_mes, idade, mes, nome_campo
from periodos import intervalo, meses


def taxa(numerador, denominador):
    return 100 * numerador / denominador if denominador else None


def mediana(valores):
    return statistics.median(valores) if valores else None


def indicador(codigo, titulo, valor, tipo='numero', numerador=None, denominador=None, nota=''):
    return dict(codigo=codigo, titulo=titulo, valor=valor, tipo=tipo, numerador=numerador,
                denominador=denominador, nota=nota)


def vinculo_inauguracao(vinculo, loja):
    inicio = loja['DATA_INAUGURACAO']
    return nome_campo(vinculo.get('TIPO_VINCULO') or 'INAUGURACAO') == 'INAUGURACAO' and (not vinculo['DATA_INICIO'] or vinculo['DATA_INICIO'] <= inicio) and (not vinculo['DATA_FIM'] or vinculo['DATA_FIM'] >= inicio)


def classificar(quantidade, sequencia, conhecida, faixa, encerrada=False):
    if encerrada:
        return 'Encerrado'
    if faixa == 0:
        return 'Em implantação'
    if quantidade is None:
        return 'Indeterminado'
    if quantidade > 0:
        return 'Ativo'
    if sequencia >= 3:
        return 'Inativo'
    if not conhecida:
        return 'Indeterminado'
    return 'Atenção' if sequencia == 1 else 'Risco crítico'


def criar_indices(t):
    indices = {}
    for tabela, campo in [('credenciados', 'CHAVE_LOJA'), ('servicos', 'ID_SERVICO'),
                           ('responsaveis', 'ID_RESPONSAVEL'), ('contratos', 'ID_CONTRATO')]:
        indices[tabela] = {r[campo]: r for r in t[tabela]}
    for tabela, campo in [('vinculacoes', 'CHAVE_LOJA'), ('acompanhamentos', 'CHAVE_LOJA'),
                          ('status_contrato', 'ID_CONTRATO'), ('contrato_loja', 'ID_CONTRATO')]:
        grupos = defaultdict(list)
        for r in t[tabela]:
            grupos[r[campo]].append(r)
        indices[tabela] = grupos
    indices['cobertura'] = {(r['CHAVE_LOJA'], r['COMPETENCIA'], r['DOMINIO_DADOS']): r for r in t['cobertura']}
    indices['producao'] = defaultdict(dict)
    for r in t['producao']:
        indices['producao'][r['CHAVE_LOJA'], r['COMPETENCIA']][r['ID_SERVICO']] = r['QTD_VALIDA']
    indices['habilitacoes'] = defaultdict(list)
    for r in t['habilitacoes']:
        indices['habilitacoes'][r['CHAVE_LOJA'], r['ID_SERVICO']].append(r)
    return indices


def treinamento(loja, acoes, corte):
    realizadas = [a for a in acoes if a['TIPO_ACAO'] == 'TREINAMENTO' and a['DATA_REALIZADA'] and a['DATA_REALIZADA'] <= corte]
    if realizadas:
        return 'Realizado', any(a['COM_MULTIPLICADOR'] is True for a in realizadas), min(a['DATA_REALIZADA'] for a in realizadas)
    nao_realizado = loja['TREINAMENTO_STATUS'] == 'NAO_REALIZADO' or any(
        a['TIPO_ACAO'] == 'TREINAMENTO' and a['STATUS'] == 'NAO_REALIZADO' and a['DATA_PREVISTA'] and a['DATA_PREVISTA'] <= corte for a in acoes)
    return ('Não realizado' if nao_realizado else 'Não informado'), None, None


def resumir_lojas(t, op):
    ix = criar_indices(t)
    implantacao = defaultdict(list)
    for vinculo in t['contrato_loja']:
        loja = ix['credenciados'][vinculo['CHAVE_LOJA']]
        if not vinculo_inauguracao(vinculo, loja):
            continue
        aprovacoes = [e['DATA_EVENTO'][:10] for e in ix['status_contrato'][vinculo['ID_CONTRATO']] if e['STATUS'] == 'APROVADO' and e['DATA_EVENTO'][:10] <= op['data_corte']]
        if aprovacoes and min(aprovacoes) <= loja['DATA_INAUGURACAO']:
            implantacao[vinculo['CHAVE_LOJA']].append((date.fromisoformat(loja['DATA_INAUGURACAO']) - date.fromisoformat(min(aprovacoes))).days)
    resumos = []
    for loja in t['credenciados']:
        chave = loja['CHAVE_LOJA']
        inicio = mes(loja['DATA_INAUGURACAO'])
        if inicio > mes(op['data_corte']):
            continue
        meses = idade(inicio, op['data_corte']) + 1
        if meses > op.get('limite_meses_por_loja', 240):
            raise ErroImportacao('Histórico superior ao limite de meses por loja. Confira as datas ou ajuste limite_meses_por_loja.')
        sequencias = {'NEGOCIO': 0, 'TRANSACAO': 0}
        conhecidas = {'NEGOCIO': True, 'TRANSACAO': True}
        anteriores = {'NEGOCIO': None, 'TRANSACAO': None}
        completo_desde_inicio, ja_produziu, primeiro = True, False, None
        observaveis_pos, positivos_pos = 0, 0
        for numero in range(meses):
            competencia = deslocar_mes(inicio, numero)
            final = min(fim_mes(competencia), op['data_corte'])
            encerrada = bool(loja['DATA_ENCERRAMENTO'] and loja['DATA_ENCERRAMENTO'] <= final)
            operou_mes = not loja['DATA_ENCERRAMENTO'] or loja['DATA_ENCERRAMENTO'] >= competencia + '-01'
            fechado = competencia <= op['ultimo_mes_fechado']
            vinculos = [v for v in ix['vinculacoes'][chave] if v['INICIO_VIGENCIA'] <= final and (not v['FIM_VIGENCIA'] or v['FIM_VIGENCIA'] >= final)]
            vinculo = vinculos[0] if vinculos else {}
            responsavel = vinculo.get('ID_RESPONSAVEL')
            acoes = ix['acompanhamentos'][chave]
            treinado, multiplicador, data_treinamento = treinamento(loja, acoes, final)
            quantidades, estados, coberturas, brutas = {}, {}, {}, {}
            producao = ix['producao'][chave, competencia]
            for dominio in ['NEGOCIO', 'TRANSACAO']:
                cobertura = ix['cobertura'].get((chave, competencia, dominio))
                completo = bool(cobertura and cobertura['STATUS_COMPLETUDE'] == 'COMPLETO' and cobertura['DATA_VALIDACAO'] <= op['data_corte'] and fechado and operou_mes)
                coberturas[dominio] = 'COMPLETO' if completo else 'PARCIAL' if cobertura and cobertura['STATUS_COMPLETUDE'] != 'AUSENTE' else 'AUSENTE'
                brutas[dominio] = sum(q for s, q in producao.items() if ix['servicos'][s]['TIPO_ATIVIDADE'] == dominio)
                qtd = brutas[dominio] if completo else None
                quantidades[dominio] = qtd
                if numero >= 1:
                    if qtd is None:
                        sequencias[dominio] = 0
                        conhecidas[dominio] = False
                    elif qtd > 0:
                        sequencias[dominio] = 0
                        conhecidas[dominio] = True
                    else:
                        sequencias[dominio] += 1
                estados[dominio] = classificar(qtd, sequencias[dominio], conhecidas[dominio], numero, encerrada)
            negocios, transacoes = quantidades['NEGOCIO'], quantidades['TRANSACAO']
            if negocios is not None and negocios > 0:
                if not ja_produziu and completo_desde_inicio:
                    primeiro = numero
                ja_produziu = True
            completo_desde_inicio = completo_desde_inicio and negocios is not None
            if numero >= 5 and negocios is not None and operou_mes:
                observaveis_pos += 1
                positivos_pos += int(negocios > 0)
            if negocios is None or transacoes is None:
                perfil = 'Indeterminado'
            elif negocios > 0 and transacoes > 0:
                perfil = 'Transações e negócios'
            elif negocios > 0:
                perfil = 'Somente negócios'
            elif transacoes > 0:
                perfil = 'Somente transações'
            else:
                perfil = 'Nenhuma atividade'
            suportes = {}
            for marco in [2, 4]:
                acao = next((a for a in acoes if a['TIPO_ACAO'] == 'SUPORTE' and a['MARCO_OPERACIONAL'] == marco), None)
                prevista = acao['DATA_PREVISTA'] if acao else fim_mes(deslocar_mes(inicio, marco))
                realizada = acao['DATA_REALIZADA'] if acao and acao['DATA_REALIZADA'] and acao['DATA_REALIZADA'] <= final else None
                elegivel = not loja['DATA_ENCERRAMENTO'] or loja['DATA_ENCERRAMENTO'] >= prevista
                suportes[str(marco)] = {'prevista': prevista, 'realizada': realizada,
                    'vencido': prevista <= final and elegivel, 'no_prazo': bool(realizada and realizada <= prevista),
                    'cadastrado': bool(acao), 'motivo': acao['MOTIVO_NAO_REALIZACAO'] if acao else None}
            resumos.append({'chave_loja': chave, 'razao_social': loja['RAZAO_SOCIAL'], 'cnpj': loja['CNPJ'],
                'competencia': competencia, 'gerencia': vinculo.get('GERENCIA', 'Sem vinculação'),
                'id_responsavel': responsavel, 'responsavel': ix['responsaveis'].get(responsavel, {}).get('NOME', 'Sem vinculação'),
                'municipio': loja['MUNICIPIO'], 'uf': loja['UF'], 'bairro': loja['BAIRRO'], 'ramo': loja['RAMO_ATIVIDADE'],
                'safra': inicio, 'idade': numero, 'inauguracao': loja['DATA_INAUGURACAO'],
                'tempo_implantacao_dias': min(implantacao[chave]) if implantacao[chave] else None,
                'tempo_implantacao': 'Não informado' if not implantacao[chave] else 'Até 14 dias' if min(implantacao[chave]) <= 14 else '15 a 30 dias' if min(implantacao[chave]) <= 30 else 'Mais de 30 dias',
                'encerramento': loja['DATA_ENCERRAMENTO'], 'motivo_encerramento': loja['MOTIVO_ENCERRAMENTO'],
                'negocios': negocios, 'transacoes': transacoes, 'negocios_informados': brutas['NEGOCIO'],
                'transacoes_informadas': brutas['TRANSACAO'], 'cobertura_negocios': coberturas['NEGOCIO'],
                'cobertura_transacoes': coberturas['TRANSACAO'], 'fechado': fechado, 'operou_mes': operou_mes,
                'situacao_negocios': estados['NEGOCIO'], 'situacao_transacoes': estados['TRANSACAO'],
                'meses_sem_negocios': sequencias['NEGOCIO'] if negocios is not None and numero >= 1 else None,
                'sequencia_completa': conhecidas['NEGOCIO'],
                'reativado': bool(negocios is not None and negocios > 0 and anteriores['NEGOCIO'] == 'Inativo'),
                'nunca_produziu': False if ja_produziu else True if completo_desde_inicio else None,
                'meses_ate_primeiro_negocio': primeiro, 'meses_pos_m4_observados': observaveis_pos,
                'meses_pos_m4_produtivos': positivos_pos, 'recorrencia_pos_m4': taxa(positivos_pos, observaveis_pos),
                'treinamento': treinado, 'com_multiplicador': multiplicador, 'data_treinamento': data_treinamento,
                'suportes': suportes, 'perfil': perfil,
                'diversificacao': len({ix['servicos'][s]['CATEGORIA'] for s, q in producao.items() if q > 0 and ix['servicos'][s]['TIPO_ATIVIDADE'] == 'NEGOCIO'}) if negocios is not None else None,
                'data_corte': op['data_corte'], 'versao_regra': VERSAO_REGRA})
            anteriores = dict(estados)
    return resumos


def filtrar(linhas, params):
    campos = {'gerencia': 'gerencia', 'responsavel': 'id_responsavel', 'municipio': 'municipio', 'ramo': 'ramo', 'safra': 'safra'}
    return [r for r in linhas if all(not params.get(p) or normalizar(r.get(c)) == normalizar(params[p]) for p, c in campos.items())]


def contratos_filtrados(base, params, ix):
    resultado = []
    for contrato in base['tabelas']['contratos']:
        if contrato['DATA_EMISSAO'] > base['opcoes']['data_corte']:
            continue
        if params.get('gerencia') and normalizar(contrato['GERENCIA_ORIGEM']) != normalizar(params['gerencia']):
            continue
        if params.get('responsavel') and contrato['RESPONSAVEL_ORIGEM'] != params['responsavel']:
            continue
        # Localização e safra só se aplicam a contratos com uma unidade vinculada.
        if any(params.get(p) for p in ['municipio', 'ramo', 'safra']):
            lojas = [ix['credenciados'][p['CHAVE_LOJA']] for p in ix['contrato_loja'][contrato['ID_CONTRATO']]]
            if not any((not params.get('municipio') or normalizar(l['MUNICIPIO']) == normalizar(params['municipio'])) and
                       (not params.get('ramo') or normalizar(l['RAMO_ATIVIDADE']) == normalizar(params['ramo'])) and
                       (not params.get('safra') or mes(l['DATA_INAUGURACAO']) == params['safra']) for l in lojas):
                continue
        resultado.append(contrato)
    return resultado


def funil(base, referencia, params, ix=None, inicio=None):
    inicio = inicio or referencia
    ix = ix or criar_indices(base['tabelas'])
    op = base['opcoes']
    corte = op['data_corte']
    contratos = contratos_filtrados(base, params, ix)
    coorte = [c for c in contratos if inicio <= mes(c['DATA_EMISSAO']) <= referencia]
    aprovacoes, decisoes, situacoes = {}, {}, {}
    for c in contratos:
        ident = c['ID_CONTRATO']
        eventos = sorted((e for e in ix['status_contrato'][ident] if e['DATA_EVENTO'][:10] <= corte), key=lambda e: e['DATA_EVENTO'])
        aprovados = [e['DATA_EVENTO'][:10] for e in eventos if e['STATUS'] == 'APROVADO']
        finais = [e['DATA_EVENTO'][:10] for e in eventos if e['STATUS'] != 'PENDENTE']
        aprovacoes[ident] = min(aprovados) if aprovados else None
        decisoes[ident] = min(finais) if finais else None
        situacoes[ident] = eventos[-1]['STATUS'] if eventos else 'PENDENTE'
    aprovados = [c for c in coorte if aprovacoes[c['ID_CONTRATO']]]
    distribuicao = Counter(situacoes[c['ID_CONTRATO']] for c in coorte)
    inaugurados, tempos = set(), []
    for c in aprovados:
        aprovacao = aprovacoes[c['ID_CONTRATO']]
        datas = [ix['credenciados'][p['CHAVE_LOJA']]['DATA_INAUGURACAO'] for p in ix['contrato_loja'][c['ID_CONTRATO']]
                 if vinculo_inauguracao(p, ix['credenciados'][p['CHAVE_LOJA']])]
        datas = [d for d in datas if aprovacao <= d <= corte]
        if datas:
            inaugurados.add(c['ID_CONTRATO'])
            tempos.append((date.fromisoformat(min(datas)) - date.fromisoformat(aprovacao)).days)
    dias = op['dias_observacao']
    maduros = [c for c in coorte if (date.fromisoformat(corte) - date.fromisoformat(c['DATA_EMISSAO'])).days >= dias]
    no_prazo = sum(bool(aprovacoes[c['ID_CONTRATO']] and (date.fromisoformat(aprovacoes[c['ID_CONTRATO']]) - date.fromisoformat(c['DATA_EMISSAO'])).days <= dias) for c in maduros)
    loja_ids = {p['CHAVE_LOJA'] for c in contratos for p in ix['contrato_loja'][c['ID_CONTRATO']] if vinculo_inauguracao(p, ix['credenciados'][p['CHAVE_LOJA']])}
    lojas_mov = [l for l in ix['credenciados'].values() if inicio <= mes(l['DATA_INAUGURACAO']) <= referencia and l['DATA_INAUGURACAO'] <= corte and l['CHAVE_LOJA'] in loja_ids]
    movimentos = sum(any(e['STATUS'] == 'APROVADO' and inicio <= mes(e['DATA_EVENTO']) <= referencia and e['DATA_EVENTO'][:10] <= corte for e in ix['status_contrato'][c['ID_CONTRATO']]) for c in contratos)
    decisoes_dias = [(date.fromisoformat(decisoes[c['ID_CONTRATO']]) - date.fromisoformat(c['DATA_EMISSAO'])).days for c in coorte if decisoes[c['ID_CONTRATO']]]
    total = len(coorte)
    nota = 'Emissões do período; decisões acumuladas até a data de corte. Veja também a janela fixa em D dias.'
    itens = [indicador('F01', 'Contratos emitidos', total), indicador('F02', 'Aprovações ocorridas', movimentos),
        indicador('F03', 'Aproveitamento da safra', taxa(len(aprovados), total), 'taxa', len(aprovados), total, nota),
        indicador('F04', 'Pendência da safra', taxa(distribuicao['PENDENTE'], total), 'taxa', distribuicao['PENDENTE'], total),
        indicador('F05', 'Reprovação da safra', taxa(distribuicao['REPROVADO'], total), 'taxa', distribuicao['REPROVADO'], total),
        indicador('F06', 'Desistência da safra', taxa(distribuicao['DESISTENCIA'], total), 'taxa', distribuicao['DESISTENCIA'], total),
        indicador('F07', 'Inaugurações ocorridas', len(lojas_mov), nota='Unidades vinculadas aos contratos do recorte; sem vínculo ficam na qualidade dos dados.'),
        indicador('F08', 'Conversão em inauguração', taxa(len(inaugurados), len(aprovados)), 'taxa', len(inaugurados), len(aprovados), 'Cada contrato conta uma vez, mesmo quando origina várias lojas.'),
        indicador('F09', 'Tempo de decisão', mediana(decisoes_dias), 'dias'),
        indicador('F10', 'Tempo de implantação', mediana(tempos), 'dias'),
        indicador('F03_D', f'Aproveitamento em {dias} dias', taxa(no_prazo, len(maduros)), 'taxa', no_prazo, len(maduros), 'Somente emissões com janela de observação completa.')]
    return {'indicadores': itens, 'situacoes_safra': dict(distribuicao), 'aprovados_safra': len(aprovados),
            'inaugurados_safra': len(inaugurados), 'cancelados_apos_aprovacao': sum(situacoes[c['ID_CONTRATO']] == 'CANCELADO' for c in aprovados)}


def pontos_idade(base, linhas, alvo):
    por_loja_mes = {(r['chave_loja'], r['competencia']): r for r in base['resumos']}
    elegiveis = []
    for r in linhas:
        if r['idade'] < alvo:
            continue
        ponto = por_loja_mes.get((r['chave_loja'], deslocar_mes(r['safra'], alvo)))
        # Encerramento após a idade não apaga o ponto; antes/durante aparece à parte.
        if ponto and ponto['fechado'] and ponto['negocios'] is not None and ponto['situacao_negocios'] != 'Encerrado':
            elegiveis.append(ponto)
    return elegiveis


def qualidade(base, referencia, linhas):
    elegiveis = [r for r in linhas if r['idade'] >= 1 and r['operou_mes'] and r['negocios'] is not None]
    produtores = [r for r in elegiveis if r['negocios'] > 0]
    observados = [r for r in linhas if r['negocios'] is not None and r['operou_mes']]
    total = sum(r['negocios'] for r in observados) if observados else None
    quantidade = sum(r['negocios'] for r in elegiveis)
    anteriores = {r['chave_loja']: r for r in base['resumos'] if r['competencia'] == deslocar_mes(referencia, -1)}
    inativos_anteriores = [r for r in linhas if anteriores.get(r['chave_loja'], {}).get('situacao_negocios') == 'Inativo' and r['negocios'] is not None and r['operou_mes']]
    reativados = sum(r['reativado'] for r in inativos_anteriores)
    pos = [r for r in linhas if r['meses_pos_m4_observados'] > 0]
    numerador = sum(r['meses_pos_m4_produtivos'] for r in pos)
    denominador = sum(r['meses_pos_m4_observados'] for r in pos)
    itens = [indicador('Q01', 'Negócios mensais confirmados', total, nota='Soma nas lojas com cobertura completa, incluindo M0. Lojas sem cobertura ficam fora da soma.'),
        indicador('Q02', 'Lojas com negócios', len(produtores)),
        indicador('Q03', 'Lojas com negócios', taxa(len(produtores), len(elegiveis)), 'taxa', len(produtores), len(elegiveis), 'Somente M1 em diante, operantes no início do mês e com dados completos.'),
        indicador('Q04', 'Negócios por loja elegível', quantidade / len(elegiveis) if elegiveis else None, denominador=len(elegiveis)),
        indicador('Q05', 'Negócios por loja produtora', quantidade / len(produtores) if produtores else None, denominador=len(produtores)),
        indicador('Q06', 'Mediana de negócios por loja', mediana([r['negocios'] for r in elegiveis])),
        indicador('Q08', 'Recorrência pós-M4', taxa(numerador, denominador), 'taxa', numerador, denominador, 'Razão entre meses produtivos e meses observáveis de M5 em diante; detalhe por loja na lista.'),
        indicador('Q09', 'Lojas inativas em negócios', sum(r['situacao_negocios'] == 'Inativo' for r in linhas)),
        indicador('Q10', 'Reativações no mês', reativados),
        indicador('Q11', 'Taxa de reativação', taxa(reativados, len(inativos_anteriores)), 'taxa', reativados, len(inativos_anteriores)),
        indicador('Q12', 'Meses até o primeiro negócio', mediana([r['meses_ate_primeiro_negocio'] for r in linhas if r['meses_ate_primeiro_negocio'] is not None]), 'meses', nota='Base mensal: não estima dias. Só calcula quando não há lacunas antes do primeiro negócio.'),
        indicador('Q13', 'Lojas que nunca produziram', sum(r['nunca_produziu'] is True for r in linhas), nota='Exige cobertura completa desde M0; desconhecido não vira nunca produziu.')]
    for alvo in [5, 6, 12]:
        pontos = pontos_idade(base, linhas, alvo)
        positivos = sum(r['negocios'] > 0 for r in pontos)
        itens.append(indicador(f'Q07_M{alvo}', f'Atividade em M{alvo}', taxa(positivos, len(pontos)), 'taxa', positivos, len(pontos), 'Somente lojas que chegaram à idade, com mês fechado e cobertura completa. Encerradas no marco ficam fora e são contadas na safra.'))
    return itens


def servicos_acompanhamento(base, referencia, linhas, ix=None):
    ix = ix or criar_indices(base['tabelas'])
    servicos = []
    for servico in base['tabelas']['servicos']:
        ident = servico['ID_SERVICO']
        dominio = servico['TIPO_ATIVIDADE']
        elegiveis, positivos, parciais, sem_uso = [], 0, 0, []
        for r in linhas:
            periodos = [h for h in ix['habilitacoes'][r['chave_loja'], ident] if h['SITUACAO'] == 'HABILITADO' and h['DATA_INICIO'] <= fim_mes(referencia) and (not h['DATA_FIM'] or h['DATA_FIM'] >= referencia + '-01')]
            completo = any(h['DATA_INICIO'] <= referencia + '-01' and (not h['DATA_FIM'] or h['DATA_FIM'] >= fim_mes(referencia)) for h in periodos)
            vigente = (not servico['VIGENCIA_INICIO'] or servico['VIGENCIA_INICIO'] <= referencia + '-01') and (not servico['VIGENCIA_FIM'] or servico['VIGENCIA_FIM'] >= fim_mes(referencia))
            parciais += int(bool(periodos) and not completo)
            observado = r['negocios'] is not None if dominio == 'NEGOCIO' else r['transacoes'] is not None
            if completo and vigente and observado and r['idade'] >= 1 and r['operou_mes']:
                elegiveis.append(r)
                produziu = ix['producao'][r['chave_loja'], referencia].get(ident, 0) > 0
                positivos += int(produziu)
                if not produziu:
                    sem_uso.append(r['chave_loja'])
        servicos.append({'id': ident, 'nome': servico['NOME'], 'categoria': servico['CATEGORIA'], 'tipo': dominio,
            'habilitadas_observaveis': len(elegiveis), 'produtoras': positivos, 'utilizacao': taxa(positivos, len(elegiveis)),
            'habilitacoes_parciais': parciais, 'sem_utilizacao': sem_uso})
    treinadas = [r for r in linhas if r['treinamento'] == 'Realizado']
    multiplicador = sum(r['com_multiplicador'] is True for r in treinadas)
    suportes = [r['suportes'][str(m)] for r in linhas for m in [2, 4] if r['suportes'][str(m)]['vencido']]
    itens = [indicador('S02', 'Categorias de negócios por loja', mediana([r['diversificacao'] for r in linhas if r['diversificacao'] is not None]), nota='Mediana de categorias com produção positiva; detalhes por loja.'),
        indicador('T01', 'Cobertura de treinamento', taxa(len(treinadas), len(linhas)), 'taxa', len(treinadas), len(linhas), 'Elegíveis: unidades inauguradas até o mês do recorte, inclusive encerradas.'),
        indicador('T02', 'Treinadas com multiplicador', taxa(multiplicador, len(treinadas)), 'taxa', multiplicador, len(treinadas)),
        indicador('T05', 'Suportes no prazo', taxa(sum(a['no_prazo'] for a in suportes), len(suportes)), 'taxa', sum(a['no_prazo'] for a in suportes), len(suportes))]
    for marco in [2, 4]:
        vencidos = [r['suportes'][str(marco)] for r in linhas if r['suportes'][str(marco)]['vencido']]
        realizados = sum(bool(a['realizada']) for a in vencidos)
        itens.append(indicador(f'T0{3 if marco == 2 else 4}', f'Cobertura do suporte M{marco}', taxa(realizados, len(vencidos)), 'taxa', realizados, len(vencidos), 'Prazo padrão: último dia do marco. A data cadastrada prevalece; ausência de ação prevista também é mostrada como pendência.'))
    comparativo = []
    for alvo in [5, 6, 12]:
        pontos = pontos_idade(base, linhas, alvo)
        grupos = defaultdict(list)
        for r in pontos:
            loja = ix['credenciados'][r['chave_loja']]
            antes = (date.fromisoformat(r['competencia'] + '-01') - timedelta(days=1)).isoformat()
            condicao = treinamento(loja, ix['acompanhamentos'][r['chave_loja']], antes)[0]
            grupos[condicao].append(r)
        for nome, grupo in grupos.items():
            positivos = sum(r['negocios'] > 0 for r in grupo)
            comparativo.append({'idade': alvo, 'treinamento': nome, 'lojas': len(grupo), 'ativas': positivos,
                               'taxa': taxa(positivos, len(grupo)), 'amostra_pequena': len(grupo) < 5})
    return {'servicos': servicos, 'indicadores': itens, 'perfis': dict(Counter(r['perfil'] for r in linhas)),
            'treinamento_idade': comparativo}


def comparar(atual, anterior, permitido=True):
    if not permitido or atual['valor'] is None or anterior is None or anterior['valor'] is None:
        return {'diferenca': None, 'variacao': None, 'unidade': 'p.p.' if atual['tipo'] == 'taxa' else '%', 'motivo': 'Período parcial ou sem observação comparável.'}
    a, b = atual['valor'], anterior['valor']
    return {'diferenca': a - b, 'variacao': a - b if atual['tipo'] == 'taxa' else (100 * (a / b - 1) if b else None),
            'unidade': 'p.p.' if atual['tipo'] == 'taxa' else '%', 'motivo': 'Sem base para comparação.' if not b and atual['tipo'] != 'taxa' else ''}


def qualidade_intervalo(base, inicio, fim, linhas_finais, params):
    indicadores = qualidade(base, fim, linhas_finais)
    observados = filtrar([r for r in base['resumos'] if inicio <= r['competencia'] <= fim and r['operou_mes'] and r['negocios'] is not None], params)
    indicadores[0]['valor'] = sum(r['negocios'] for r in observados) if observados else None
    indicadores[0]['titulo'] = 'Negócios mensais confirmados' if inicio == fim else 'Negócios confirmados no período'
    indicadores[0]['nota'] = 'Soma da produção com cobertura completa nos meses selecionados, incluindo M0. A atribuição acompanha o responsável e a gerência de cada mês.'
    return indicadores


def analise(base, params):
    inicio, referencia, duracao = intervalo(base, params)
    linhas = filtrar([r for r in base['resumos'] if r['competencia'] == referencia], params)
    linhas_periodo = filtrar([r for r in base['resumos'] if inicio <= r['competencia'] <= referencia], params)
    ix = criar_indices(base['tabelas'])
    atual_funil = funil(base, referencia, params, ix, inicio)
    sa = servicos_acompanhamento(base, referencia, linhas, ix)
    indicadores = atual_funil['indicadores'] + qualidade_intervalo(base, inicio, referencia, linhas, params) + sa['indicadores']
    parcial = referencia > base['opcoes']['ultimo_mes_fechado']
    for nome, periodo, inicio_comparacao in [('mensal', deslocar_mes(inicio, -1), deslocar_mes(inicio, -duracao)), ('anual', deslocar_mes(referencia, -12), deslocar_mes(inicio, -12))]:
        outras = filtrar([r for r in base['resumos'] if r['competencia'] == periodo], params)
        anteriores = funil(base, periodo, params, ix, inicio_comparacao)['indicadores'] + qualidade_intervalo(base, inicio_comparacao, periodo, outras, params) + servicos_acompanhamento(base, periodo, outras, ix)['indicadores']
        por_codigo = {i['codigo']: i for i in anteriores}
        tem_contratos = any(inicio_comparacao <= mes(c['DATA_EMISSAO']) <= periodo for c in base['tabelas']['contratos'])
        tem_producao = any(inicio_comparacao <= r['competencia'] <= periodo for r in base['resumos'])
        for i in indicadores:
            comparavel = not parcial and (tem_contratos if i['codigo'][0] == 'F' else tem_producao if i['codigo'] == 'Q01' else bool(outras))
            i[nome] = comparar(i, por_codigo.get(i['codigo']), comparavel)
            i[nome]['competencia'] = periodo
            i[nome]['inicio'] = inicio_comparacao
            i['escopo'] = 'Período selecionado' if i['codigo'].startswith('F') or i['codigo'] == 'Q01' else 'Fechamento em ' + referencia
    por_indicador = {i['codigo']: i for i in indicadores}
    regioes, responsaveis = [], []
    for campo, valores, destino in [('gerencia', GERENCIAS + (['Sem vinculação'] if any(r['gerencia'] == 'Sem vinculação' for r in linhas_periodo) else []), regioes),
                                     ('responsavel', sorted({r['id_responsavel'] for r in linhas_periodo if r['id_responsavel']} | {c['RESPONSAVEL_ORIGEM'] for c in contratos_filtrados(base, params, ix)}), responsaveis)]:
        for valor in valores:
            if params.get(campo) and params[campo] != valor:
                continue
            filtro = dict(params, **{campo: valor})
            grupo = filtrar(linhas, filtro)
            f = funil(base, referencia, filtro, ix, inicio)
            q = qualidade_intervalo(base, inicio, referencia, grupo, filtro)
            fq = {i['codigo']: i['valor'] for i in f['indicadores'] + q}
            nome = valor if campo == 'gerencia' else ix['responsaveis'][valor]['NOME']
            destino.append({'nome': nome, 'id': valor, 'emitidos': fq['F01'], 'aprovados': f['aprovados_safra'],
                'aproveitamento': fq['F03'], 'lojas': len(grupo), 'negocios': fq['Q01'], 'ativas': fq['Q02'],
                'taxa_ativas': fq['Q03'], 'inativas': fq['Q09'], 'risco': sum(r['situacao_negocios'] == 'Risco crítico' for r in grupo),
                'cobertura': taxa(sum(r['negocios'] is not None for r in grupo), len(grupo))})
    safras = []
    for safra in sorted({r['safra'] for r in linhas}):
        grupo = [r for r in linhas if r['safra'] == safra]
        pontos = {}
        for alvo in [1, 2, 3, 4, 5, 6, 9, 12]:
            observados = pontos_idade(base, grupo, alvo)
            ativos = sum(r['negocios'] > 0 for r in observados)
            pontos[str(alvo)] = {'valor': taxa(ativos, len(observados)), 'numerador': ativos, 'denominador': len(observados)}
        safras.append({'safra': safra, 'lojas': len(grupo), 'encerradas': sum(r['situacao_negocios'] == 'Encerrado' for r in grupo), 'idades': pontos})
    condicoes = []
    for campo in ['gerencia', 'municipio', 'bairro', 'ramo', 'safra', 'tempo_implantacao', 'treinamento']:
        grupos = defaultdict(list)
        for r in linhas:
            grupos[r[campo] or 'Não informado'].append(r)
        for nome, grupo in sorted(grupos.items()):
            pos = [r for r in grupo if r['idade'] >= 5 and r['negocios'] is not None and r['operou_mes']]
            ativos = sum(r['negocios'] > 0 for r in pos)
            condicoes.append({'dimensao': campo, 'grupo': nome, 'lojas': len(grupo), 'observadas_pos_m4': len(pos),
                'ativas_pos_m4': ativos, 'taxa': taxa(ativos, len(pos)), 'amostra_pequena': len(pos) < 5})
    tendencias = []
    for periodo in meses(inicio if duracao > 1 else deslocar_mes(referencia, -12), referencia):
        ls = filtrar([r for r in base['resumos'] if r['competencia'] == periodo], params)
        f = funil(base, periodo, params, ix)
        q = {i['codigo']: i['valor'] for i in qualidade(base, periodo, ls)}
        tendencias.append({'competencia': periodo, 'emitidos': f['indicadores'][0]['valor'], 'aprovados': f['indicadores'][1]['valor'],
            'negocios': q['Q01'], 'taxa_ativas': q['Q03'], 'parcial': periodo > base['opcoes']['ultimo_mes_fechado']})
    # Busca e risco refinam somente a lista operacional; os indicadores mantêm o recorte acima.
    busca = normalizar(params.get('busca', '')).strip()
    lista = [r for r in linhas if (not params.get('risco') or r['situacao_negocios'] == params['risco'])
             and (not params.get('treinamento') or r['treinamento'] == params['treinamento'])
             and (not busca or busca in normalizar(' '.join(str(r.get(c) or '') for c in ['chave_loja', 'razao_social', 'cnpj', 'municipio', 'responsavel'])))]
    lista.sort(key=lambda r: r['chave_loja'])
    pagina = int(params.get('pagina', 1))
    tamanho = int(params.get('por_pagina', 25))
    if pagina < 1 or tamanho not in {25, 50, 100}:
        raise ValueError('Página inválida. Use 25, 50 ou 100 registros por página.')
    total_lista = len(lista)
    total_negocios = sum(r['negocios'] for r in linhas if r['negocios'] is not None)
    lista = [dict(r, participacao_producao=taxa(r['negocios'], total_negocios) if r['negocios'] is not None else None) for r in lista]
    paginas = max(1, (total_lista + tamanho - 1) // tamanho)
    pagina = min(pagina, paginas)
    esperadas = [r for r in linhas if r['operou_mes']]
    cobertura = sum(r['negocios'] is not None and r['transacoes'] is not None for r in esperadas)
    sem_vinculo = sum(r['gerencia'] == 'Sem vinculação' for r in linhas)
    incompletas_periodo = sum(r['operou_mes'] and (r['negocios'] is None or r['transacoes'] is None) for r in linhas_periodo)
    status = 'PROVISÓRIO' if parcial or base['auditoria']['avisos'] or cobertura < len(esperadas) or sem_vinculo or incompletas_periodo else 'VALIDADO'
    if not linhas and not por_indicador['F01']['valor'] and not por_indicador['F02']['valor']:
        status = 'SEM OBSERVAÇÃO'
    return {'carregado': True, 'versao': base['versao'], 'versao_regra': VERSAO_REGRA,
        'periodo': {'inicio': inicio, 'fim': referencia, 'meses': duracao},
        'competencia': referencia, 'data_corte': base['opcoes']['data_corte'], 'parcial': parcial,
        'modo_exemplo': base['opcoes'].get('modo_exemplo', False), 'fechamento': status,
        'funil': atual_funil, 'gerencias': regioes, 'responsaveis': responsaveis,
        'safras': safras, 'condicoes': condicoes, 'tendencia': tendencias, **sa,
        'indicadores': por_indicador,
        'riscos': dict(Counter(r['situacao_negocios'] for r in linhas)),
        'qualidade_dados': {'lojas': len(linhas), 'cobertura_esperada': len(esperadas), 'completas': cobertura, 'cobertura': taxa(cobertura, len(esperadas)),
            'observacoes_periodo': len([r for r in linhas_periodo if r['operou_mes']]),
            'incompletas_periodo': incompletas_periodo,
            'indeterminadas': sum(r['situacao_negocios'] == 'Indeterminado' for r in linhas), 'sem_vinculo': sem_vinculo,
            'suportes_sem_cadastro': sum(not a['cadastrado'] and a['vencido'] for r in linhas for a in r['suportes'].values()),
            **base['auditoria'], 'fontes': base['fontes'], 'mapeamentos': base['mapeamentos']},
        'pendencias_suporte': [dict(chave_loja=r['chave_loja'], razao_social=r['razao_social'], responsavel=r['responsavel'], marco=int(m), **a) for r in linhas for m, a in r['suportes'].items() if a['vencido'] and not a['realizada']],
        'lojas': lista[(pagina - 1) * tamanho:pagina * tamanho], 'total_lojas': total_lista,
        'pagina': pagina, 'paginas': paginas, 'por_pagina': tamanho}
