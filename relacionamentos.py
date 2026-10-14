"""Enriquecimento configurado por CHAVE_LOJA sem multiplicar linhas."""
import json


def enriquecer_carga(conn, agente, colunas, por_chave):
    from integracao import chave_coluna

    plano = agente.catalogo['enriquecimento']
    principal = plano['tabela_principal']
    dimensoes = plano['dimensoes']
    contagem = conn.execute('SELECT COUNT(*) FROM carga_temporaria').fetchone()[0]
    if len(dimensoes) > 12:
        agente.erro('JUNCAO_INVALIDA', 'Configure no máximo 12 dimensões por publicação.')
        return contagem
    if principal not in agente.tabelas:
        agente.erro('TABELA_AUSENTE', f'Tabela principal {principal} não encontrada.')
        return contagem
    if agente.chave not in agente.tabelas[principal]['colunas']:
        agente.erro('CHAVE_AUSENTE', f'Tabela principal {principal} não contém {agente.chave}.')
        return contagem
    selecionadas = {por_chave[chave_coluna(c)] for c in agente.tabelas[principal]['colunas']
                    if chave_coluna(c) in por_chave}
    campos_dimensoes = []
    for dimensao in dimensoes:
        nome = dimensao['tabela']
        if nome not in agente.tabelas:
            agente.erro('TABELA_AUSENTE', f'Dimensão {nome} não encontrada.')
            continue
        info = agente.tabelas[nome]
        if agente.chave not in info['colunas'] or info['nulas'] or info['repeticoes']:
            agente.erro('DIMENSAO_INVALIDA', f'{nome}: a dimensão exige {agente.chave} preenchida e única.')
        requested = [agente.canonico(c) for c in dimensao['colunas']]
        campos = []
        for campo in requested:
            ident = por_chave.get(chave_coluna(campo))
            if campo not in info['colunas'] or not ident:
                agente.erro('COLUNA_JUNCAO_AUSENTE', f'{nome}: campo {campo} não disponível para enriquecimento.')
            else:
                campos.append((campo, ident))
                selecionadas.add(ident)
        campos_dimensoes.append(campos)
        ausentes = conn.execute('SELECT COUNT(*) FROM carga_temporaria p LEFT JOIN carga_temporaria d '
                                'ON d.tabela=? AND d.chave_loja=p.chave_loja WHERE p.tabela=? AND d.tabela IS NULL',
                                (nome, principal)).fetchone()[0]
        agente.relacionamentos.append({'principal': principal, 'dimensao': nome,
                                       'chave': agente.chave, 'sem_correspondencia': ausentes,
                                       'obrigatoria': dimensao.get('obrigatoria', True)})
        if ausentes:
            mensagem = f'{principal} → {nome}: {ausentes} linhas sem correspondência por {agente.chave}.'
            if dimensao.get('obrigatoria', True):
                agente.erro('REFERENCIA_AUSENTE', mensagem)
            else:
                agente.avisos.append({'codigo': 'REFERENCIA_OPCIONAL_AUSENTE', 'mensagem': mensagem})
    if agente.erros:
        return contagem
    conn.execute('CREATE INDEX idx_carga_chave ON carga_temporaria(tabela, chave_loja)')
    conn.execute('CREATE TABLE carga_enriquecida (payload TEXT, arquivo TEXT, aba TEXT, linha INTEGER, tabela TEXT, chave_loja TEXT, origens_campos TEXT)')
    selects = ['p.payload', 'p.arquivo', 'p.aba', 'p.linha', 'p.tabela', 'p.chave_loja', 'p.origens_campos']
    joins, params = [], []
    for i, dimensao in enumerate(dimensoes):
        alias = f'd{i}'
        selects.extend(f'{alias}.{campo}' for campo in ['payload', 'arquivo', 'aba', 'linha'])
        joins.append(f'LEFT JOIN carga_temporaria {alias} ON {alias}.tabela=? AND {alias}.chave_loja=p.chave_loja')
        params.append(dimensao['tabela'])
    params.append(principal)
    query = 'SELECT ' + ','.join(selects) + ' FROM carga_temporaria p ' + ' '.join(joins) + ' WHERE p.tabela=? ORDER BY p.rowid'
    quantidade = 0
    for row in conn.execute(query, params):
        payload = json.loads(row[0])
        origens = json.loads(row[6])
        for i, campos in enumerate(campos_dimensoes):
            offset = 7 + 4 * i
            dados = json.loads(row[offset]) if row[offset] is not None else {}
            for nome, ident in campos:
                novo = dados.get(ident)
                if novo is None:
                    continue
                if payload.get(ident) is not None and payload[ident] != novo:
                    agente.erro('CAMPO_JUNCAO_DIVERGENTE', f'{row[1]}::{row[2]}, linha {row[3]}: {nome} diverge entre a tabela principal e {dimensoes[i]["tabela"]}.',
                                fonte=row[1] + '::' + row[2], linha=row[3], coluna=nome)
                elif payload.get(ident) is None:
                    payload[ident] = novo
                    origens[ident] = {'arquivo': row[offset + 1], 'aba': row[offset + 2], 'linha': row[offset + 3]}
        conn.execute('INSERT INTO carga_enriquecida VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (json.dumps(payload, ensure_ascii=False), *row[1:6], json.dumps(origens, ensure_ascii=False)))
        quantidade += 1
    if not agente.erros:
        conn.execute('DROP TABLE carga_temporaria')
        conn.execute('ALTER TABLE carga_enriquecida RENAME TO carga_temporaria')
        colunas[:] = [c for c in colunas if c['id'] in selecionadas]
        for chave in list(por_chave):
            if por_chave[chave] not in selecionadas:
                del por_chave[chave]
    return quantidade
