"""Testes de integração do importador, consultas e aplicação WSGI."""
import base64
import csv
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from consulta import abrir_base, ler_metadados
from integracao import ErroImportacao, atualizar_dashboard, carregar_configuracao, chave_coluna
from servidor import criar_aplicacao

PROJETO = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sources = self.root / 'entradas'
        shutil.copytree(PROJETO / 'planilhas_aprovadas', self.sources)
        shutil.copy(PROJETO / 'catalogo_colunas.json', self.root / 'catalogo_colunas.json')
        config = json.loads((PROJETO / 'configuracao.json').read_text(encoding='utf-8'))
        config.pop('prospeccao', None)  # Estes testes exercitam o módulo de consultas isoladamente.
        config.update({'pasta_planilhas': 'entradas', 'banco': 'base.sqlite3'})
        self.config_path = self.root / 'config.json'
        self.config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        self.meta = atualizar_dashboard(self.config_path)
        self.app = criar_aplicacao(self.config_path)
        self.ids = {chave_coluna(c['nome']): c['id'] for c in self.meta['colunas']}

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, params=None, auth=None, method='GET', app=None):
        environ = {}
        setup_testing_defaults(environ)
        environ.update({'PATH_INFO': path, 'QUERY_STRING': urlencode(params or {}), 'REQUEST_METHOD': method})
        if auth:
            environ['HTTP_AUTHORIZATION'] = auth
        captured = {}
        def start(status, headers):
            captured['status'] = int(status[:3])
            captured['headers'] = dict(headers)
        response = (app or self.app)(environ, start)
        try:
            body = b''.join(response)
        finally:
            if hasattr(response, 'close'):
                response.close()
        return captured, body

    def data(self, params=None):
        response, body = self.request('/api/registros', params)
        self.assertEqual(response['status'], 200, body.decode())
        return json.loads(body)

    def csv_source(self, name, rows):
        with (self.sources / name).open('w', encoding='utf-8-sig', newline='') as output:
            csv.writer(output, delimiter=';').writerows(rows)

    def test_excel_union_origins_dates_and_leading_zeros(self):
        self.assertEqual(self.meta['total'], 84)
        self.assertEqual(len(self.meta['fontes']), 2)
        self.assertIn('chamado', self.ids)
        data = self.data({'q': 'AC-0001'})
        item = data['itens'][0]
        self.assertEqual(item['valores'][self.ids['codigo do cliente']], '000401')
        self.assertTrue(item['valores'][self.ids['atualizado em']].startswith('2026-10-07'))
        self.assertEqual(item['origem']['arquivo'], 'exemplo_matriz.xlsx')
        self.assertEqual(item['origem']['aba'], 'Acessos')
        self.assertEqual(item['origem']['linha'], 2)
        self.assertIsNone(item['valores'][self.ids['chamado']])
        self.assertEqual(self.data()['resumo']['clientes'], 8)

    def test_accent_search_and_combined_filters(self):
        result = self.data({'q': 'VERTICE'})
        self.assertGreater(result['total'], 0)
        self.assertTrue(all(i['valores'][self.ids['cliente']] == 'Vértice Tecnologia' for i in result['itens']))
        combined = self.data({'cliente': 'aurora', 'sistema': 'ERP', 'status': 'Ativo'})
        self.assertGreater(combined['total'], 0)
        for item in combined['itens']:
            self.assertEqual(item['valores'][self.ids['cliente']], 'Aurora Comercial')
            self.assertEqual(item['valores'][self.ids['sistema']], 'ERP')
            self.assertEqual(item['valores'][self.ids['status']], 'Ativo')

    def test_arbitrary_column_date_interval_empty_and_literal_wildcards(self):
        def query(column, op, value=''):
            return self.data({'filtros': json.dumps([{'coluna': self.ids[column], 'operador': op, 'valor': value}])})
        self.assertEqual(query('perfil', 'igual', 'Administrador')['total'], 21)
        self.assertEqual(query('chamado', 'vazio')['total'], 56)
        self.assertEqual(query('chamado', 'preenchido')['total'], 28)
        self.assertEqual(self.data({'q': '%'})['total'], 0)
        date_result = query('atualizado em', 'maior_igual', '2026-10-05')
        self.assertTrue(all(i['valores'][self.ids['atualizado em']][:10] >= '2026-10-05' for i in date_result['itens']))

    def test_pagination_sort_and_clamped_page(self):
        first = self.data({'por_pagina': '10', 'pagina': '1', 'ordenar': self.ids['id'], 'direcao': 'desc'})
        second = self.data({'por_pagina': '10', 'pagina': '2', 'ordenar': self.ids['id'], 'direcao': 'desc'})
        self.assertEqual(first['paginas'], 9)
        self.assertEqual(first['itens'][0]['valores'][self.ids['id']], 'AC-0084')
        self.assertFalse({r['id'] for r in first['itens']} & {r['id'] for r in second['itens']})
        self.assertEqual(self.data({'por_pagina': '10', 'pagina': '999'})['pagina'], 9)

    def test_export_contains_all_matching_records_not_only_page(self):
        result = self.data({'cliente': 'aurora', 'por_pagina': '1'})
        response, body = self.request('/api/exportar.csv', {'cliente': 'aurora', 'por_pagina': '1'})
        self.assertEqual(response['status'], 200)
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows) - 1, result['total'])
        self.assertIn('Origem: linha', rows[0])

    def test_bad_input_does_not_replace_previous_publication(self):
        self.csv_source('quebrado.csv', [['Cliente', 'Cliente'], ['A', 'B']])
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config_path)
        response, body = self.request('/api/metadados')
        self.assertEqual(response['status'], 200)
        self.assertEqual(json.loads(body)['versao'], self.meta['versao'])
        self.assertEqual(self.data()['total'], 84)

    def test_reimport_replaces_rows_and_empty_input_is_guarded(self):
        atualizar_dashboard(self.config_path)
        self.assertEqual(self.data()['total'], 84)
        for source in self.sources.iterdir():
            source.unlink()
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config_path)
        self.assertEqual(self.data()['total'], 84)
        atualizar_dashboard(self.config_path, permitir_vazio=True)
        self.assertEqual(self.data()['total'], 0)

    def test_untrusted_filters_static_files_and_methods(self):
        attacks = [
            {'ordenar': 'id; DROP TABLE registros'},
            {'filtros': json.dumps([{'coluna': 'malicioso', 'operador': 'igual', 'valor': 'A'}])},
            {'filtros': '{}'}, {'filtros': 'not-json'}, {'por_pagina': '101'},
            {'filtros': json.dumps([{'coluna': self.ids['cliente'], 'operador': []}])},
            {'direcao': 'desc; DELETE FROM registros'},
        ]
        for attack in attacks:
            response, _ = self.request('/api/registros', attack)
            self.assertEqual(response['status'], 400, attack)
        self.assertEqual(self.data({'q': "' OR 1=1 --"})['total'], 0)
        for path in ['/', '/static/style.css', '/static/app.js', '/static/favicon.svg']:
            response, body = self.request(path)
            self.assertEqual(response['status'], 200)
            self.assertGreater(len(body), 20)
            self.assertIn('Content-Security-Policy', response['headers'])
        for path in ['/configuracao.json', '/dados/dashboard.sqlite3', '/static/../integracao.py']:
            self.assertEqual(self.request(path)[0]['status'], 404)
        self.assertEqual(self.request('/api/registros', method='POST')[0]['status'], 405)
        self.assertEqual(self.data()['total'], 84)

    def test_authentication_protects_data_assets_and_export(self):
        app = criar_aplicacao(self.config_path, usuario='consulta', senha='senha-de-teste')
        token = 'Basic ' + base64.b64encode(b'consulta:senha-de-teste').decode()
        for path in ['/', '/api/metadados', '/api/registros', '/api/exportar.csv', '/static/app.js']:
            self.assertEqual(self.request(path, app=app)[0]['status'], 401)
            self.assertEqual(self.request(path, app=app, auth='Basic invalid')[0]['status'], 401)
            self.assertEqual(self.request(path, app=app, auth=token)[0]['status'], 200)

    def test_csv_aliases_hidden_fields_numbers_and_formula_escape(self):
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        config.update({'renomear_colunas': {'Empresa': 'Cliente'}, 'colunas_ocultas': ['Segredo'], 'colunas_numero': ['Quantidade']})
        self.config_path.write_text(json.dumps(config), encoding='utf-8')
        self.csv_source('extra.csv', [['Empresa', 'Quantidade', 'Segredo', 'Observação'],
                                      ['Teste CSV', '1.234,50', 'CONFIDENCIAL', '=1+1'],
                                      ['Outra CSV', '2', 'CONFIDENCIAL', '@comando']])
        meta = atualizar_dashboard(self.config_path)
        self.app = criar_aplicacao(self.config_path)
        self.assertEqual(meta['total'], 86)
        self.assertNotIn('segredo', {chave_coluna(c['nome']) for c in meta['colunas']})
        column = next(c['id'] for c in meta['colunas'] if c['nome'] == 'QUANTIDADE')
        result = self.data({'filtros': json.dumps([{'coluna': column, 'operador': 'maior_igual', 'valor': '1000'}])})
        self.assertEqual(result['total'], 1)
        self.assertEqual(self.data({'q': 'CONFIDENCIAL'})['total'], 0)
        response, body = self.request('/api/exportar.csv', {'cliente': 'Teste CSV'})
        self.assertEqual(response['status'], 200)
        self.assertIn("'=1+1", body.decode('utf-8-sig'))

    def test_reader_keeps_snapshot_while_a_new_base_is_published(self):
        config = carregar_configuracao(self.config_path)
        with abrir_base(config) as reader:
            old = ler_metadados(reader, config)
            self.csv_source('novo.csv', [['Cliente'], ['Novo cliente']])
            new = atualizar_dashboard(self.config_path)
            self.assertNotEqual(new['versao'], old['versao'])
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM registros').fetchone()[0], 84)
        self.assertEqual(self.data()['total'], 85)
        response, body = self.request('/api/registros', {'versao': old['versao']})
        self.assertEqual(response['status'], 409)
        self.assertEqual(json.loads(body)['metadados']['versao'], new['versao'])

    def test_missing_database_gives_a_usable_empty_interface(self):
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        config['banco'] = 'nao_importado.sqlite3'
        self.config_path.write_text(json.dumps(config), encoding='utf-8')
        self.app = criar_aplicacao(self.config_path)
        self.assertFalse(json.loads(self.request('/api/metadados')[1])['carregado'])
        self.assertEqual(self.data()['total'], 0)
        self.assertEqual(self.request('/api/exportar.csv')[0]['status'], 400)

    def test_options_and_a_literal_sem_status_label(self):
        response, body = self.request('/api/opcoes', {'coluna': self.ids['cliente'], 'busca': 'vertice'})
        self.assertEqual(response['status'], 200)
        self.assertEqual(json.loads(body)['valores'], ['Vértice Tecnologia'])
        self.csv_source('status.csv', [['Cliente', 'Status'], ['Sem status literal', 'Sem status'], ['Sem status vazio', '']])
        atualizar_dashboard(self.config_path)
        result = self.data()
        matches = [s for s in result['resumo']['estados'] if s['nome'] == 'Sem status']
        self.assertEqual(len(matches), 2)
        self.assertEqual({s['vazio'] for s in matches}, {True, False})


if __name__ == '__main__':
    unittest.main()
