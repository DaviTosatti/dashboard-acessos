"""Consultas parametrizadas, paginação e exportação do consolidado."""
from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
from contextlib import contextmanager

from integracao import Configuracao, chave_coluna, data_iso, normalizar, numero_texto
from padronizacao import texto_cnpj


class ErroConsulta(ValueError):
    pass


def uri_somente_leitura(caminho):
    """Preserva caminhos UNC no pathname, sem depender de URI authority no SQLite."""
    uri = caminho.as_uri()
    if uri.startswith('file://') and not uri.startswith('file:///'):
        # file://servidor/pasta -> file:////servidor/pasta (authority vazia).
        uri = 'file:////' + uri[len('file://'):]
    return uri + '?mode=ro'


@contextmanager
def abrir_base(config: Configuracao):
    if not config.banco.exists():
        yield None
        return
    conn = sqlite3.connect(uri_somente_leitura(config.banco), uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.create_function('fold', 1, normalizar, deterministic=True)
    conn.create_collation('FOLD', lambda a, b: (normalizar(a) > normalizar(b)) - (normalizar(a) < normalizar(b)))
    try:
        conn.execute('BEGIN')  # Metadados e linhas sempre leem a mesma versão.
        yield conn
    finally:
        conn.rollback()
        conn.close()


def ler_metadados(conn, config: Configuracao) -> dict:
    base = {'titulo': config.valores.get('titulo', 'Consulta de acessos'),
            'modo_exemplo': bool(config.valores.get('modo_exemplo', False)),
            'colunas_iniciais': config.valores['colunas_iniciais'],
            'carregado': False, 'colunas': [], 'papeis': {}, 'fontes': [],
            'total': 0, 'atualizado_em': None, 'versao': None}
    if conn is not None:
        tabela = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadados'").fetchone()
        if tabela:
            linha = conn.execute('SELECT valor FROM metadados WHERE chave=?', ('snapshot',)).fetchone()
            if linha:
                base.update(json.loads(linha['valor']))
                base['carregado'] = True
    return base


def inteiro(valor, padrao, minimo, maximo, nome):
    if valor is None:
        return padrao
    try:
        numero = int(valor)
    except (ValueError, TypeError) as exc:
        raise ErroConsulta(f'{nome} inválido.') from exc
    if not minimo <= numero <= maximo:
        raise ErroConsulta(f'{nome} deve estar entre {minimo} e {maximo}.')
    return numero


def texto_parametro(params, nome, limite=500):
    texto = params.get(nome, '')
    if not isinstance(texto, str) or len(texto) > limite:
        raise ErroConsulta(f'{nome} excede o limite de {limite} caracteres.')
    return texto.strip()


def padrao_like(texto):
    return normalizar(texto).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def montar_consulta(meta, params):
    colunas = {c['id']: c for c in meta['colunas']}
    termos, valores = [], []
    busca = texto_parametro(params, 'q', 300)
    if busca:
        cnpj = re.sub(r'[.\s/\-]', '', busca).upper()
        if cnpj != busca and re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', cnpj):
            termos.append("(busca LIKE ? ESCAPE '\\' OR busca LIKE ? ESCAPE '\\')")
            valores.extend(['%' + padrao_like(busca) + '%', '%' + padrao_like(cnpj) + '%'])
        else:
            termos.append("busca LIKE ? ESCAPE '\\'")
            valores.append('%' + padrao_like(busca) + '%')
    try:
        filtros = json.loads(params.get('filtros', '[]'))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ErroConsulta('Lista de filtros inválida.') from exc
    if not isinstance(filtros, list) or len(filtros) > 20:
        raise ErroConsulta('Use, no máximo, 20 filtros.')
    for papel in ['cliente', 'sistema', 'status']:
        valor = texto_parametro(params, papel)
        if valor:
            campo = meta['papeis'].get(papel)
            if not campo:
                raise ErroConsulta(f'A coluna para {papel} não está configurada.')
            filtros.append({'coluna': campo, 'operador': 'contem' if papel == 'cliente' else 'igual', 'valor': valor})
    arquivo = texto_parametro(params, 'arquivo')
    if arquivo:
        termos.append('arquivo = ?')
        valores.append(arquivo)
    for filtro in filtros:
        if not isinstance(filtro, dict):
            raise ErroConsulta('Filtro inválido.')
        coluna = filtro.get('coluna')
        if not isinstance(coluna, str) or coluna not in colunas:
            raise ErroConsulta('Coluna não encontrada. Atualize a consulta.')
        operador = filtro.get('operador')
        valor = filtro.get('valor', '')
        if not isinstance(operador, str):
            raise ErroConsulta('Operador de filtro inválido.')
        if not isinstance(valor, str) or len(valor) > 500:
            raise ErroConsulta('Valor do filtro inválido.')
        valor = valor.strip()
        campo = '"' + coluna + '"'  # Apenas IDs internos presentes no esquema.
        if colunas[coluna].get('formato') == 'cnpj' and operador not in {'vazio', 'preenchido'}:
            if operador in {'igual', 'diferente'}:
                try:
                    valor = texto_cnpj(valor)
                except ValueError as exc:
                    raise ErroConsulta(str(exc)) from exc
            else:
                valor = re.sub(r'[.\s/\-]', '', valor).upper()
        if operador == 'vazio':
            termos.append(f'({campo} IS NULL OR {campo} = \'\')')
        elif operador == 'preenchido':
            termos.append(f'({campo} IS NOT NULL AND {campo} <> \'\')')
        elif operador in {'contem', 'comeca'}:
            if not valor:
                raise ErroConsulta('Informe o valor do filtro.')
            termos.append(f"fold({campo}) LIKE ? ESCAPE '\\'")
            valores.append(('%' if operador == 'contem' else '') + padrao_like(valor) + '%')
        elif operador in {'igual', 'diferente', 'maior_igual', 'menor_igual'}:
            if not valor:
                raise ErroConsulta('Informe o valor do filtro.')
            tipo = colunas[coluna]['tipo']
            if operador in {'maior_igual', 'menor_igual'} and tipo not in {'numero', 'data'}:
                raise ErroConsulta('Comparações por faixa exigem uma coluna de data ou número.')
            if tipo == 'numero':
                try:
                    valor = numero_texto(valor)
                except ValueError as exc:
                    raise ErroConsulta(str(exc)) from exc
                campo = f'CAST({campo} AS REAL)'
                valor = float(valor)
                if not math.isfinite(valor):
                    raise ErroConsulta('Número do filtro fora do intervalo suportado.')
            elif tipo == 'data':
                try:
                    valor = data_iso(valor)
                except ValueError as exc:
                    raise ErroConsulta(str(exc)) from exc
                # Uma data sem hora seleciona todo o dia em colunas de timestamp.
                if len(valor) == 10:
                    campo = f'substr({campo}, 1, 10)'
            else:
                campo = f'fold({campo})'
                valor = normalizar(valor)
            simbolo = {'igual': '=', 'diferente': '<>', 'maior_igual': '>=', 'menor_igual': '<='}[operador]
            termos.append(f'{campo} {simbolo} ?')
            valores.append(valor)
        else:
            raise ErroConsulta('Operador de filtro inválido.')
    ordenar = texto_parametro(params, 'ordenar')
    direcao = texto_parametro(params, 'direcao') or 'asc'
    if direcao not in {'asc', 'desc'}:
        raise ErroConsulta('Direção de ordenação inválida.')
    ordem = 'id ASC'
    if ordenar:
        if ordenar not in colunas:
            raise ErroConsulta('Coluna de ordenação inválida.')
        campo = '"' + ordenar + '"'
        expressao = f'CAST({campo} AS REAL)' if colunas[ordenar]['tipo'] == 'numero' else f'{campo} COLLATE FOLD'
        ordem = f'({campo} IS NULL), {expressao} {direcao.upper()}, id ASC'
    return (' WHERE ' + ' AND '.join(termos) if termos else ''), valores, ordem


def resumo_filtrado(conn, meta, where, values, total):
    if not meta['carregado']:
        return {'registros': 0, 'clientes': None, 'sistemas': None, 'arquivos': 0, 'estados': []}
    def distintos(coluna):
        if not coluna:
            return None
        return conn.execute(f'SELECT COUNT(DISTINCT fold("{coluna}")) FROM registros' + where
                            + (' AND ' if where else ' WHERE ') + f'"{coluna}" IS NOT NULL', values).fetchone()[0]
    arquivos = conn.execute('SELECT COUNT(DISTINCT arquivo) FROM registros' + where, values).fetchone()[0]
    estados = []
    status = meta['papeis'].get('status')
    if status:
        estados = [{'nome': linha[0] or 'Sem status', 'quantidade': linha[1], 'vazio': linha[0] is None or linha[0] == ''} for linha in conn.execute(
            f'SELECT "{status}", COUNT(*) FROM registros' + where + f' GROUP BY fold("{status}") ORDER BY COUNT(*) DESC LIMIT 10', values)]
    return {'registros': total, 'clientes': distintos(meta['papeis'].get('cliente')),
            'sistemas': distintos(meta['papeis'].get('sistema')), 'arquivos': arquivos, 'estados': estados}


def consultar(conn, meta, params):
    por_pagina = inteiro(params.get('por_pagina'), 25, 1, 100, 'por_pagina')
    pagina = inteiro(params.get('pagina'), 1, 1, 1000000, 'pagina')
    where, valores, ordem = montar_consulta(meta, params)
    total = conn.execute('SELECT COUNT(*) FROM registros' + where, valores).fetchone()[0] if meta['carregado'] else 0
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = min(pagina, paginas)
    itens = []
    if meta['carregado']:
        for row in conn.execute('SELECT * FROM registros' + where + ' ORDER BY ' + ordem + ' LIMIT ? OFFSET ?', valores + [por_pagina, (pagina - 1) * por_pagina]):
            itens.append({'id': row['id'], 'valores': {c['id']: row[c['id']] for c in meta['colunas']},
                          'origem': {'arquivo': row['arquivo'], 'aba': row['aba'], 'linha': row['linha']},
                          'origens_campos': json.loads(row['origens_campos']) if 'origens_campos' in row.keys() else {}})
    return {'itens': itens, 'total': total, 'pagina': pagina, 'por_pagina': por_pagina, 'paginas': paginas,
            'resumo': resumo_filtrado(conn, meta, where, valores, total),
            'versao': meta['versao'], 'atualizado_em': meta['atualizado_em']}


def opcoes(conn, meta, params):
    coluna = texto_parametro(params, 'coluna')
    if coluna not in {c['id'] for c in meta['colunas']}:
        raise ErroConsulta('Coluna de opções inválida.')
    busca = texto_parametro(params, 'busca', 300)
    rows = list(conn.execute(f'SELECT "{coluna}", COUNT(*) FROM registros WHERE "{coluna}" IS NOT NULL AND fold("{coluna}") LIKE ? ESCAPE \'\\\' GROUP BY fold("{coluna}") ORDER BY COUNT(*) DESC, fold("{coluna}") LIMIT 101',
                             ['%' + padrao_like(busca) + '%']))
    return {'valores': [r[0] for r in rows[:100]], 'mais_resultados': len(rows) > 100}


def proteger_csv(valor):
    texto = '' if valor is None else str(valor)
    if texto and (texto[0] in '\t\r\n' or texto.lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + texto
    return texto


def exportar_csv(conn, meta, params):
    """Gera CSV em blocos com os mesmos filtros e ordenação da consulta."""
    where, values, order = montar_consulta(meta, params)
    if not meta['carregado']:
        raise ErroConsulta('A base ainda não foi importada.')
    cursor = conn.execute('SELECT * FROM registros' + where + ' ORDER BY ' + order, values)
    buffer = io.StringIO(newline='')
    escritor = csv.writer(buffer, delimiter=';', lineterminator='\r\n')
    enriquecida = bool(meta.get('analise_padronizacao', {}).get('relacionamentos'))
    escritor.writerow([proteger_csv(c['nome']) for c in meta['colunas']] + ['Origem: arquivo', 'Origem: aba', 'Origem: linha'] + (['Origem: campos enriquecidos'] if enriquecida else []))
    yield ('\ufeff' + buffer.getvalue()).encode('utf-8')
    buffer.seek(0)
    buffer.truncate(0)
    for row in cursor:
        escritor.writerow([proteger_csv(row[c['id']]) for c in meta['colunas']] + [proteger_csv(row['arquivo']), proteger_csv(row['aba']), row['linha']] + ([row['origens_campos']] if enriquecida else []))
        if buffer.tell() >= 65536:
            yield buffer.getvalue().encode('utf-8')
            buffer.seek(0)
            buffer.truncate(0)
    if buffer.tell():
        yield buffer.getvalue().encode('utf-8')
