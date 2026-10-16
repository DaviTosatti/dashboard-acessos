import csv
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from agente_padronizacao import analisar_planilhas
from integracao import ErroImportacao, atualizar_dashboard
from padronizacao import texto_cnpj, texto_identificador
from servidor import criar_aplicacao

PROJETO = Path(__file__).resolve().parents[1]
CNPJ_A = '01234567000190'
CNPJ_B = 'AB12CD34000156'


class PadronizacaoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'entradas').mkdir()
        config = json.loads((PROJETO / 'configuracao.json').read_text(encoding='utf-8'))
        config.pop('prospeccao', None)  # Estes testes exercitam o módulo de consultas isoladamente.
        config.update({'pasta_planilhas': 'entradas', 'banco': 'base.sqlite3', 'colunas_data': []})
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(config), encoding='utf-8')
        self.catalog_path = self.root / 'catalogo_colunas.json'
        self.catalog = json.loads((PROJETO / 'catalogo_colunas.json').read_text(encoding='utf-8'))
        self.save_catalog()

    def tearDown(self):
        self.temp.cleanup()

    def save_catalog(self):
        self.catalog_path.write_text(json.dumps(self.catalog, ensure_ascii=False), encoding='utf-8')

    def source(self, name, rows):
        with (self.root / 'entradas' / name).open('w', encoding='utf-8-sig', newline='') as output:
            csv.writer(output, delimiter=';').writerows(rows)

    def get(self, path='/api/registros', params=None):
        environ = {}
        setup_testing_defaults(environ)
        environ.update({'PATH_INFO': path, 'QUERY_STRING': urlencode(params or {})})
        result = {}
        def start(status, headers):
            result['status'] = int(status[:3])
        response = criar_aplicacao(self.config)(environ, start)
        try:
            body = b''.join(response)
        finally:
            if hasattr(response, 'close'):
                response.close()
        return result['status'], body

    def test_known_aliases_share_one_field_and_identifiers_are_text(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', '01.234.567/0001-90']])
        self.source('y.csv', [['chave loja', 'NO_CNPJ'], ['001', CNPJ_A]])
        meta = atualizar_dashboard(self.config)
        self.assertEqual([c['nome'] for c in meta['colunas']], ['CHAVE_LOJA', 'CNPJ'])
        self.assertTrue(all(c['tipo'] == 'texto' for c in meta['colunas']))
        self.assertEqual(meta['total'], 2)  # A repetição entre tabelas é legítima.
        self.assertEqual(meta['analise_padronizacao']['estado'], 'APTO')
        self.assertTrue(all(t['chaves_repetidas'] == 0 for t in meta['analise_padronizacao']['tabelas']))
        key = next(c['id'] for c in meta['colunas'] if c['nome'] == 'CHAVE_LOJA')
        status, body = self.get()
        self.assertEqual(status, 200)
        self.assertTrue(all(r['valores'][key] == '001' for r in json.loads(body)['itens']))

    def test_cnpj_queries_accept_formatted_values_and_alphanumeric(self):
        self.source('x.csv', [['CHAVE_LOJA', 'NO_CNPJ'], ['001', '01.234.567/0001-90'], ['002', 'AB.12C.D34/0001-56']])
        meta = atualizar_dashboard(self.config)
        cnpj = next(c['id'] for c in meta['colunas'] if c['nome'] == 'CNPJ')
        params = {'filtros': json.dumps([{'coluna': cnpj, 'operador': 'igual', 'valor': '01.234.567/0001-90'}])}
        self.assertEqual(json.loads(self.get(params=params)[1])['total'], 1)
        self.assertEqual(json.loads(self.get(params={'q': 'AB.12C.D34/0001-56'})[1])['total'], 1)
        self.assertEqual(texto_cnpj('ab.12c.d34/0001-56'), CNPJ_B)
        self.assertEqual(texto_identificador(7, '000'), '007')
        self.assertEqual(texto_cnpj(1234567000190), CNPJ_A)

    def test_same_target_columns_coalesce_only_if_consistent(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ', 'NO_CNPJ'], ['001', '01.234.567/0001-90', CNPJ_A], ['002', '', CNPJ_B]])
        meta = atualizar_dashboard(self.config)
        self.assertEqual(meta['total'], 2)
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ', 'NO_CNPJ'], ['001', CNPJ_A, CNPJ_B]])
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)
        report = analisar_planilhas(self.config)
        self.assertIn('COLUNAS_DIVERGENTES', {e['codigo'] for e in report['erros']})
        self.assertEqual(json.loads(self.get('/api/metadados')[1])['versao'], meta['versao'])

    def test_duplicate_and_null_keys_are_errors_inside_one_table(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A], ['001', CNPJ_A], ['', CNPJ_B]])
        report = analisar_planilhas(self.config)
        self.assertEqual(report['estado'], 'BLOQUEADO')
        self.assertTrue({'CHAVE_DUPLICADA', 'CHAVE_VAZIA'} <= {e['codigo'] for e in report['erros']})
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)
        self.assertFalse(json.loads(self.get('/api/metadados')[1])['carregado'])

    def test_duplicate_key_across_files_of_same_logical_table_is_detected(self):
        self.catalog['fontes'] = {'parte_*.csv::CSV': {'tabela': 'LOJAS'}}
        self.save_catalog()
        self.source('parte_a.csv', [['CHAVE_LOJA'], ['001']])
        self.source('parte_b.csv', [['CHAVE_LOJA'], ['001']])
        self.assertIn('CHAVE_DUPLICADA', {e['codigo'] for e in analisar_planilhas(self.config)['erros']})

    def test_same_key_different_cnpj_blocks_publication(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A]])
        self.source('y.csv', [['CHAVE_LOJA', 'NO_CNPJ'], ['001', CNPJ_B]])
        report = analisar_planilhas(self.config)
        self.assertIn('VALOR_DIVERGENTE', {e['codigo'] for e in report['erros']})
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)

    def test_uncertain_prefix_match_is_suggested_then_explicit_alias_resolves_it(self):
        self.source('x.csv', [['CHAVE_LOJA', 'NOME_FANTASIA'], ['001', 'Loja exemplo']])
        self.source('y.csv', [['CHAVE_LOJA', 'NM_FANTASIA'], ['001', 'Loja exemplo']])
        report = analisar_planilhas(self.config)
        self.assertEqual(report['estado'], 'BLOQUEADO')
        self.assertEqual(report['sugestoes'][0]['destino_sugerido'], 'NM_FANTASIA')
        self.catalog['aliases']['NOME_FANTASIA'] = ['NOME_FANTASIA', 'NM_FANTASIA']
        self.save_catalog()
        meta = atualizar_dashboard(self.config)
        self.assertFalse(meta['analise_padronizacao']['sugestoes'])
        self.assertEqual({c['nome'] for c in meta['colunas']}, {'CHAVE_LOJA', 'NOME_FANTASIA'})

    def test_value_profile_identifies_an_unknown_candidate_without_auto_mapping(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CAMPO_DESCONHECIDO'], ['001', CNPJ_A]])
        report = analisar_planilhas(self.config)
        self.assertEqual(report['estado'], 'BLOQUEADO')
        self.assertEqual(report['sugestoes'][0]['destino_sugerido'], 'CNPJ')
        self.assertEqual(report['mapeamentos'][1]['padrao'], 'CAMPO_DESCONHECIDO')

    def test_scoped_cnpj_columns_stay_separate_and_per_source_override_is_supported(self):
        self.catalog['fontes'] = {'y.csv::CSV': {'colunas': {'NO_CNPJ': 'CNPJ_MATRIZ'}}}
        self.catalog['tipos']['CNPJ_MATRIZ'] = 'cnpj'
        self.save_catalog()
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A]])
        self.source('y.csv', [['CHAVE_LOJA', 'NO_CNPJ', 'CNPJ_FILIAL'], ['001', CNPJ_B, CNPJ_A]])
        meta = atualizar_dashboard(self.config)
        self.assertTrue({'CNPJ', 'CNPJ_MATRIZ', 'CNPJ_FILIAL'} <= {c['nome'] for c in meta['colunas']})
        self.assertFalse(meta['analise_padronizacao']['sugestoes'])

    def test_dry_analysis_and_report_do_not_change_the_published_database(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A]])
        meta = atualizar_dashboard(self.config)
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A], ['002', CNPJ_B]])
        report = analisar_planilhas(self.config, self.root / 'relatorios')
        self.assertEqual(report['estado'], 'APTO')
        self.assertEqual(json.loads(self.get('/api/metadados')[1])['versao'], meta['versao'])
        self.assertEqual(json.loads(self.get()[1])['total'], 1)
        report_text = (self.root / 'relatorios' / 'analise_colunas.html').read_text(encoding='utf-8')
        self.assertNotIn(CNPJ_A, report_text)
        self.assertNotIn(CNPJ_B, report_text)
        self.assertIn('CHAVE_LOJA', report_text)

    def setup_join(self):
        self.catalog['fontes'] = {'lojas.csv::CSV': {'tabela': 'LOJAS', 'exigir_chave': True},
                                   'acessos.csv::CSV': {'tabela': 'ACESSOS', 'exigir_chave': True}}
        self.catalog['enriquecimento'] = {'tabela_principal': 'ACESSOS', 'dimensoes': [
            {'tabela': 'LOJAS', 'colunas': ['CNPJ', 'CLIENTE'], 'obrigatoria': True}]}
        self.save_catalog()
        self.source('lojas.csv', [['CHAVE_LOJA', 'NO_CNPJ', 'CLIENTE'], ['001', CNPJ_A, 'Loja um'], ['002', CNPJ_B, 'Loja dois']])
        self.source('acessos.csv', [['CHAVE_LOJA', 'SISTEMA'], ['002', 'ERP'], ['001', 'CRM']])

    def test_join_by_store_key_preserves_rows_and_records_field_provenance(self):
        self.setup_join()
        meta = atualizar_dashboard(self.config)
        self.assertEqual(meta['total'], 2)
        columns = {c['nome']: c['id'] for c in meta['colunas']}
        data = json.loads(self.get(params={'cliente': 'Loja dois'})[1])
        self.assertEqual(data['total'], 1)
        row = data['itens'][0]
        self.assertEqual(row['valores'][columns['CHAVE_LOJA']], '002')
        self.assertEqual(row['valores'][columns['CNPJ']], CNPJ_B)
        self.assertEqual(row['origem']['arquivo'], 'acessos.csv')
        self.assertEqual(row['origens_campos'][columns['CNPJ']]['arquivo'], 'lojas.csv')
        status, body = self.get('/api/exportar.csv')
        self.assertEqual(status, 200)
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][-1], 'Origem: campos enriquecidos')

    def test_required_missing_reference_and_duplicate_dimension_block_join(self):
        self.setup_join()
        old = atualizar_dashboard(self.config)
        self.source('acessos.csv', [['CHAVE_LOJA', 'SISTEMA'], ['999', 'ERP']])
        self.assertIn('REFERENCIA_AUSENTE', {e['codigo'] for e in analisar_planilhas(self.config)['erros']})
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)
        self.assertEqual(json.loads(self.get('/api/metadados')[1])['versao'], old['versao'])
        self.source('lojas.csv', [['CHAVE_LOJA', 'CNPJ', 'CLIENTE'], ['999', CNPJ_A, 'A'], ['999', CNPJ_A, 'A']])
        self.assertIn('DIMENSAO_INVALIDA', {e['codigo'] for e in analisar_planilhas(self.config)['erros']})

    def test_optional_reference_does_not_drop_unmatched_rows(self):
        self.setup_join()
        self.catalog['enriquecimento']['dimensoes'][0]['obrigatoria'] = False
        self.save_catalog()
        self.source('acessos.csv', [['CHAVE_LOJA', 'SISTEMA'], ['999', 'ERP'], ['001', 'CRM']])
        meta = atualizar_dashboard(self.config)
        self.assertEqual(meta['total'], 2)
        self.assertEqual(meta['analise_padronizacao']['relacionamentos'][0]['sem_correspondencia'], 1)

    def test_empty_main_table_does_not_erase_an_existing_base(self):
        self.setup_join()
        old = atualizar_dashboard(self.config)
        self.source('acessos.csv', [['CHAVE_LOJA', 'SISTEMA']])
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)
        self.assertEqual(json.loads(self.get('/api/metadados')[1])['versao'], old['versao'])

    def test_missing_required_header_is_checked_in_every_table_part(self):
        self.catalog['fontes'] = {'parte_*.csv::CSV': {'tabela': 'LOJAS', 'colunas_obrigatorias': ['CNPJ']}}
        self.save_catalog()
        self.source('parte_a.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A]])
        self.source('parte_b.csv', [['CHAVE_LOJA'], ['002']])
        self.assertIn('COLUNA_AUSENTE', {e['codigo'] for e in analisar_planilhas(self.config)['erros']})

    def test_ambiguous_alias_definition_is_rejected(self):
        self.catalog['aliases']['CNPJ_FORNECEDOR'] = ['NO_CNPJ']
        self.save_catalog()
        self.source('x.csv', [['CHAVE_LOJA'], ['001']])
        report = analisar_planilhas(self.config)
        self.assertEqual(report['estado'], 'BLOQUEADO')
        self.assertIn('Alias ambíguo', report['erros'][0]['mensagem'])

    def test_disabled_catalog_keeps_legacy_labels_and_accepts_repeated_keys(self):
        config = json.loads(self.config.read_text(encoding='utf-8'))
        config['catalogo_colunas'] = None
        self.config.write_text(json.dumps(config), encoding='utf-8')
        self.source('x.csv', [['CHAVE_LOJA', 'Nome cliente', 'NO_CNPJ'],
                              ['001', 'Loja um', CNPJ_A], ['001', 'Loja um', CNPJ_A]])
        meta = atualizar_dashboard(self.config)
        self.assertEqual(meta['total'], 2)
        self.assertEqual({c['nome'] for c in meta['colunas']}, {'CHAVE_LOJA', 'Nome cliente', 'NO_CNPJ'})
        self.assertFalse(meta['analise_padronizacao']['ativo'])

    def test_invalid_cnpj_is_reported_without_replacing_previous_publication(self):
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', CNPJ_A]])
        old = atualizar_dashboard(self.config)
        self.source('x.csv', [['CHAVE_LOJA', 'CNPJ'], ['001', 'valor inválido']])
        report = analisar_planilhas(self.config)
        self.assertIn('VALOR_INVALIDO', {e['codigo'] for e in report['erros']})
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)
        self.assertEqual(json.loads(self.get('/api/metadados')[1])['versao'], old['versao'])

    def test_overlapping_source_rules_are_rejected(self):
        self.catalog['fontes'] = {'*.csv::CSV': {'tabela': 'GERAL'},
                                  'x.csv::CSV': {'tabela': 'LOJAS'}}
        self.save_catalog()
        self.source('x.csv', [['CHAVE_LOJA'], ['001']])
        report = analisar_planilhas(self.config)
        self.assertEqual(report['estado'], 'BLOQUEADO')
        self.assertIn('mais de uma regra', report['erros'][0]['mensagem'])

    def test_join_conflict_does_not_overwrite_a_filled_main_field(self):
        self.setup_join()
        old = atualizar_dashboard(self.config)
        self.source('acessos.csv', [['CHAVE_LOJA', 'SISTEMA', 'CLIENTE'],
                                    ['001', 'CRM', 'Outro cliente']])
        report = analisar_planilhas(self.config)
        self.assertIn('CAMPO_JUNCAO_DIVERGENTE', {e['codigo'] for e in report['erros']})
        with self.assertRaises(ErroImportacao):
            atualizar_dashboard(self.config)
        self.assertEqual(json.loads(self.get('/api/metadados')[1])['versao'], old['versao'])


if __name__ == '__main__':
    unittest.main()
