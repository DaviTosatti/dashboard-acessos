"""Aplicação WSGI de leitura. Servida pelo Waitress, no Windows ou Linux."""
from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs

from consulta import ErroConsulta, abrir_base, consultar, exportar_csv, ler_metadados, montar_consulta, opcoes
from integracao import PADRAO_CONFIG, carregar_configuracao
from prospeccao import consultar_prospeccao, consultar_consultores, csv_prospeccao, detalhe_loja, ler_base as ler_prospeccao, metadados as meta_prospeccao

RAIZ = Path(__file__).resolve().parent
ARQUIVOS = {
    '/': (RAIZ / 'index.html', 'text/html; charset=utf-8'),
    '/static/style.css': (RAIZ / 'static/style.css', 'text/css; charset=utf-8'),
    '/static/app.js': (RAIZ / 'static/app.js', 'text/javascript; charset=utf-8'),
    '/static/prospeccao.js': (RAIZ / 'static/prospeccao.js', 'text/javascript; charset=utf-8'),
    '/static/prospeccao-consultores.js': (RAIZ / 'static/prospeccao-consultores.js', 'text/javascript; charset=utf-8'),
    '/static/prospeccao.css': (RAIZ / 'static/prospeccao.css', 'text/css; charset=utf-8'),
    '/static/filter-selects.js': (RAIZ / 'static/filter-selects.js', 'text/javascript; charset=utf-8'),
    '/static/filter-selects.css': (RAIZ / 'static/filter-selects.css', 'text/css; charset=utf-8'),
    '/static/favicon.svg': (RAIZ / 'static/favicon.svg', 'image/svg+xml'),
}
CABECALHOS = [
    ('X-Content-Type-Options', 'nosniff'),
    ('X-Frame-Options', 'SAMEORIGIN'),
    ('Referrer-Policy', 'same-origin'),
    ('Cache-Control', 'no-store'),
    ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"),
]


class Dashboard:
    def __init__(self, config_path=PADRAO_CONFIG, *, usuario=None, senha=None):
        self.config = carregar_configuracao(config_path)
        if bool(usuario) != bool(senha):
            raise ValueError('Informe tanto DASHBOARD_USUARIO quanto DASHBOARD_SENHA, ou nenhum dos dois.')
        self.usuario = usuario
        self.senha = senha

    def autorizado(self, environ):
        if not self.usuario:
            return True
        try:
            esquema, token = environ.get('HTTP_AUTHORIZATION', '').split(' ', 1)
            if esquema.casefold() != 'basic':
                return False
            usuario, senha = base64.b64decode(token, validate=True).decode('utf-8').split(':', 1)
            return hmac.compare_digest(usuario.encode(), self.usuario.encode()) & hmac.compare_digest(senha.encode(), self.senha.encode())
        except (ValueError, UnicodeError, binascii.Error):
            return False

    def responder(self, start_response, status, payload, content_type='application/json; charset=utf-8', extras=()):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        start_response(status, CABECALHOS + [('Content-Type', content_type), ('Content-Length', str(len(data)))] + list(extras))
        return [data]

    def __call__(self, environ, start_response):
        if not self.autorizado(environ):
            return self.responder(start_response, '401 Unauthorized', {'erro': 'Autenticação necessária.'},
                                  extras=[('WWW-Authenticate', 'Basic realm="Dashboard de acessos", charset="UTF-8"')])
        if environ.get('REQUEST_METHOD') != 'GET':
            return self.responder(start_response, '405 Method Not Allowed', {'erro': 'Esta interface permite apenas consultas.'}, extras=[('Allow', 'GET')])
        caminho = environ.get('PATH_INFO', '/')
        try:
            if caminho in ARQUIVOS:
                arquivo, mime = ARQUIVOS[caminho]
                return self.responder(start_response, '200 OK', arquivo.read_bytes(), mime)
            rotas_prospeccao = {'/api/prospeccao/metadados', '/api/prospeccao/painel', '/api/prospeccao/loja', '/api/prospeccao/exportar.csv', '/api/prospeccao/consultores', '/api/prospeccao/consultores.csv'}
            if caminho not in {'/api/metadados', '/api/registros', '/api/opcoes', '/api/exportar.csv'} | rotas_prospeccao:
                return self.responder(start_response, '404 Not Found', {'erro': 'Página não encontrada.'})
            raw = environ.get('QUERY_STRING', '')
            if len(raw) > 16384:
                raise ErroConsulta('A consulta excede o tamanho permitido.')
            parsed = parse_qs(raw, keep_blank_values=True, max_num_fields=30)
            if any(len(values) != 1 for values in parsed.values()):
                raise ErroConsulta('Não repita parâmetros da consulta.')
            params = {k: v[0] for k, v in parsed.items()}
            if caminho in rotas_prospeccao:
                with abrir_base(self.config) as conn:
                    if caminho.endswith('/metadados'):
                        payload = meta_prospeccao(ler_prospeccao(conn, self.config))
                    elif caminho.endswith('/loja'):
                        payload = detalhe_loja(conn, self.config, params)
                    elif caminho.endswith('/consultores'):
                        payload = consultar_consultores(conn, self.config, params)
                    elif caminho.endswith('/consultores.csv'):
                        return self.responder(start_response, '200 OK', consultar_consultores(conn, self.config, params, exportar=True),
                            'text/csv; charset=utf-8', extras=[('Content-Disposition', 'attachment; filename="atividades_consultores.csv"')])
                    elif caminho.endswith('/exportar.csv'):
                        return self.responder(start_response, '200 OK', csv_prospeccao(conn, self.config, params),
                            'text/csv; charset=utf-8', extras=[('Content-Disposition', 'attachment; filename="prospeccao_filtrada.csv"')])
                    else:
                        payload = consultar_prospeccao(conn, self.config, params)
                    return self.responder(start_response, '200 OK', payload)
            # A exportação mantém seu próprio snapshot aberto até o fim do streaming.
            if caminho == '/api/exportar.csv':
                return self.exportar(params, start_response)
            with abrir_base(self.config) as conn:
                meta = ler_metadados(conn, self.config)
                if params.get('versao') and params['versao'] != meta['versao']:
                    return self.responder(start_response, '409 Conflict', {'erro': 'A base foi atualizada. Recarregue a consulta.', 'metadados': meta})
                if caminho == '/api/metadados':
                    payload = meta
                elif caminho == '/api/registros':
                    payload = consultar(conn, meta, params)
                else:
                    payload = opcoes(conn, meta, params)
                return self.responder(start_response, '200 OK', payload)
        except (ErroConsulta, ValueError) as exc:
            return self.responder(start_response, '400 Bad Request', {'erro': str(exc)})
        except Exception:
            logging.exception('Erro ao atender uma consulta do dashboard')
            return self.responder(start_response, '500 Internal Server Error', {'erro': 'Não foi possível consultar a base. Consulte o log do servidor.'})

    def exportar(self, params, start_response):
        contexto = abrir_base(self.config)
        conn = contexto.__enter__()
        try:
            meta = ler_metadados(conn, self.config)
            if params.get('versao') and params['versao'] != meta['versao']:
                contexto.__exit__(None, None, None)
                return self.responder(start_response, '409 Conflict', {'erro': 'A base mudou. Atualize a consulta antes de exportar.'})
            montar_consulta(meta, params)
            gerador = exportar_csv(conn, meta, params)
            primeiro = next(gerador)  # Valida e executa antes de enviar o cabeçalho HTTP.
        except Exception:
            contexto.__exit__(None, None, None)
            raise
        start_response('200 OK', CABECALHOS + [('Content-Type', 'text/csv; charset=utf-8'),
                       ('Content-Disposition', 'attachment; filename="acessos_filtrados.csv"')])
        def transmitir():
            try:
                yield primeiro
                yield from gerador
            finally:
                gerador.close()
                contexto.__exit__(None, None, None)
        return transmitir()


def criar_aplicacao(config_path=PADRAO_CONFIG, **kwargs):
    return Dashboard(config_path, **kwargs)


def main():
    parser = argparse.ArgumentParser(description='Serve o dashboard de acessos na intranet.')
    parser.add_argument('--config', default=str(PADRAO_CONFIG))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--porta', type=int, default=8000)
    parser.add_argument('--teste', action='store_true', help='Usa o servidor simples da biblioteca padrão, apenas para teste local.')
    args = parser.parse_args()
    if not 1 <= args.porta <= 65535:
        parser.error('A porta deve estar entre 1 e 65535.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        app = criar_aplicacao(args.config, usuario=os.getenv('DASHBOARD_USUARIO'), senha=os.getenv('DASHBOARD_SENHA'))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f'Dashboard: http://{args.host}:{args.porta}', flush=True)
    if args.teste:
        if args.host not in {'127.0.0.1', 'localhost', '::1'}:
            parser.error('--teste aceita somente um endereço local. Use Waitress para a rede.')
        from wsgiref.simple_server import make_server
        with make_server(args.host, args.porta, app) as server:
            server.serve_forever()
    else:
        try:
            from waitress import serve
        except ImportError:
            parser.exit(1, 'Instale as dependências: python -m pip install -r requirements.txt\n')
        serve(app, host=args.host, port=args.porta, threads=8)


if __name__ == '__main__':
    main()
