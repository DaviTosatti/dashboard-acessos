"""Cenários independentes dos exemplos: fórmulas, fronteiras e publicação."""
import base64
import copy
import csv
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from consulta import abrir_base
from integracao import ErroImportacao, atualizar_dashboard, carregar_configuracao
from prospeccao import atualizar_prospeccao, preparar_prospeccao, ler_base
from prospeccao_calculos import analise, resumir_lojas, taxa
from prospeccao_dados import TABELAS, deslocar_mes, fim_mes
from servidor import criar_aplicacao

PROJETO = Path(__file__).resolve().parents[1]


def fixture():
    tabelas = {nome: [] for nome in TABELAS}
    def add(tabela, **campos):
        r = {c: None for c in TABELAS[tabela][1]}
        r.update(campos)
        r['_origem'] = {'arquivo': tabela + '.csv', 'aba': 'CSV', 'linha': len(tabelas[tabela]) + 2, 'tabela': tabela}
        tabelas[tabela].append(r)
        return r
    add('responsaveis', ID_RESPONSAVEL='R1', NOME='Consultor origem')
    add('responsaveis', ID_RESPONSAVEL='R2', NOME='Consultor atual')
    add('servicos', ID_SERVICO='B', NOME='Negócio exemplo', CATEGORIA='Crédito', TIPO_ATIVIDADE='NEGOCIO')
    add('servicos', ID_SERVICO='T', NOME='Transação exemplo', CATEGORIA='Bancário', TIPO_ATIVIDADE='TRANSACAO')
    sequencias = [[1, 2, 2, 2, 2, 0, 0, 0, 5], [1, 1, 1, 1, 1, 1, 1, 0, 0],
                  [1, 1, 1, 1, 1, 1, 0, 0, 0], [0] * 9, [0] * 9]
    for i, valores in enumerate(sequencias, 1):
        chave = f'{i:04d}'
        add('credenciados', CHAVE_LOJA=chave, RAZAO_SOCIAL='Loja exemplo ' + chave, MUNICIPIO='Curitiba', UF='PR', RAMO_ATIVIDADE='Mercado', DATA_INAUGURACAO='2026-01-10')
        add('vinculacoes', ID_VINCULACAO='V' + chave, CHAVE_LOJA=chave, GERENCIA='Sul', ID_RESPONSAVEL='R1', INICIO_VIGENCIA='2026-01-10', FIM_VIGENCIA='2026-06-30' if i == 1 else None)
        if i == 1:
            add('vinculacoes', ID_VINCULACAO='V2' + chave, CHAVE_LOJA=chave, GERENCIA='São Paulo', ID_RESPONSAVEL='R2', INICIO_VIGENCIA='2026-07-01')
        for servico in ['B', 'T']:
            add('habilitacoes', ID_HABILITACAO='H' + chave + servico, CHAVE_LOJA=chave, ID_SERVICO=servico, DATA_INICIO='2026-01-10', SITUACAO='HABILITADO')
        for n, qtd in enumerate(valores):
            competencia = deslocar_mes('2026-01', n)
            for dominio in ['NEGOCIO', 'TRANSACAO']:
                ausente = i == 5 and n == 6 and dominio == 'NEGOCIO'
                add('cobertura', CHAVE_LOJA=chave, COMPETENCIA=competencia, DOMINIO_DADOS=dominio,
                    STATUS_COMPLETUDE='AUSENTE' if ausente else 'COMPLETO', DATA_VALIDACAO=None if ausente else fim_mes(competencia))
            add('producao', CHAVE_LOJA=chave, COMPETENCIA=competencia, ID_SERVICO='B', QTD_VALIDA=qtd)
            add('producao', CHAVE_LOJA=chave, COMPETENCIA=competencia, ID_SERVICO='T', QTD_VALIDA=10)
    for i, emissao in enumerate(['2025-09-01', '2025-09-01', '2025-09-01', '2026-08-01', '2026-09-01'], 1):
        add('contratos', ID_CONTRATO='C' + str(i), DATA_EMISSAO=emissao, GERENCIA_ORIGEM='Sul', RESPONSAVEL_ORIGEM='R1')
    for contrato, data in [('C1', '2025-10-01'), ('C2', '2025-09-03'), ('C4', '2026-09-02')]:
        add('status_contrato', ID_EVENTO='E' + contrato, ID_CONTRATO=contrato, DATA_EVENTO=data, STATUS='APROVADO')
    add('status_contrato', ID_EVENTO='CAN', ID_CONTRATO='C2', DATA_EVENTO='2026-02-01', STATUS='CANCELADO')
    for contrato, chave in [('C1', '0001'), ('C1', '0002'), ('C2', '0003'), ('C4', '0004'), ('C3', '0005')]:
        add('contrato_loja', ID_CONTRATO=contrato, CHAVE_LOJA=chave)
    for chave, data in [('0001', '2026-08-05'), ('0002', '2026-02-01')]:
        add('acompanhamentos', ID_ACAO='A' + chave, CHAVE_LOJA=chave, TIPO_ACAO='TREINAMENTO', STATUS='CONCLUIDO', DATA_REALIZADA=data, COM_MULTIPLICADOR=True)
    return tabelas


class ProspeccaoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sources = self.root / 'entradas_pro'
        self.sources.mkdir()
        self.config_path = self.root / 'config.json'
        self.config = {'pasta_planilhas': 'entradas_acesso', 'banco': 'dados/base.sqlite3', 'catalogo_colunas': None,
                       'prospeccao': {'ativo': True, 'pasta': 'entradas_pro', 'catalogo': 'catalogo_pro.json',
                           'data_corte': '2026-10-15', 'ultimo_mes_fechado': '2026-09', 'dias_observacao': 30,
                           'quantidade_producao': 'liquida', 'modo_exemplo': True}}
        self.catalogo = {'fontes': {nome: {'arquivo': nome + '.csv'} for nome in TABELAS}}
        self.t = fixture()
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        (self.root / 'catalogo_pro.json').write_text(json.dumps(self.catalogo), encoding='utf-8')
        for tabela, registros in self.t.items():
            with (self.sources / (tabela + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=TABELAS[tabela][1], delimiter=';', extrasaction='ignore')
                w.writeheader(); w.writerows(registros)

    def base(self):
        return preparar_prospeccao(carregar_configuracao(self.config_path))

    def painel(self, **params):
        return analise(self.base(), params)

    def request(self, path='/api/prospeccao/painel', params=None, app=None, method='GET', auth=None):
        resposta = {}
        def start(status, headers):
            resposta.update(status=int(status[:3]), headers=dict(headers))
        env = {'PATH_INFO': path, 'QUERY_STRING': urlencode(params or {}), 'REQUEST_METHOD': method}
        if auth: env['HTTP_AUTHORIZATION'] = auth
        body = b''.join((app or criar_aplicacao(self.config_path))(env, start))
        return resposta, body

    def test_aproveitamento_usa_safra_e_nao_movimentacao(self):
        d = self.painel(competencia='2026-09')['indicadores']
        self.assertEqual(d['F01']['valor'], 1)
        self.assertEqual(d['F02']['valor'], 1)
        self.assertEqual(d['F03']['valor'], 0)

    def test_contrato_com_varias_lojas_nao_duplica_conversao(self):
        d = self.painel(competencia='2025-09')
        self.assertEqual(d['indicadores']['F03']['valor'], 200 / 3)
        self.assertEqual(d['indicadores']['F08']['valor'], 100)
        self.assertEqual(d['funil']['inaugurados_safra'], 2)

    def test_cancelamento_preserva_aprovacao_e_situacao_final_exclusiva(self):
        d = self.painel(competencia='2025-09')
        self.assertEqual(d['funil']['cancelados_apos_aprovacao'], 1)
        self.assertEqual(sum(d['funil']['situacoes_safra'].values()), 3)
        self.assertEqual(d['funil']['aprovados_safra'], 2)

    def test_janela_d_so_conta_emissoes_maduras(self):
        self.config['prospeccao']['data_corte'] = '2025-09-20'
        self.config['prospeccao']['ultimo_mes_fechado'] = '2025-08'
        self.save()
        i = self.painel(competencia='2025-09')['indicadores']['F03_D']
        self.assertIsNone(i['valor']); self.assertEqual(i['denominador'], 0)

    def test_m0_fica_fora_da_media_e_das_taxas_comparaveis(self):
        d = self.painel(competencia='2026-01')
        self.assertEqual(d['riscos'], {'Em implantação': 5})
        self.assertEqual(d['indicadores']['Q03']['denominador'], 0)
        self.assertIsNone(d['indicadores']['Q03']['valor'])

    def test_estados_sequencia_e_reativacao(self):
        d = self.painel(competencia='2026-09')
        linhas = {r['chave_loja']: r for r in d['lojas']}
        self.assertTrue(linhas['0001']['reativado'])
        self.assertEqual(linhas['0002']['situacao_negocios'], 'Risco crítico')
        self.assertEqual(linhas['0003']['situacao_negocios'], 'Inativo')
        self.assertEqual(linhas['0005']['situacao_negocios'], 'Indeterminado')
        self.assertEqual(linhas['0003']['situacao_transacoes'], 'Ativo')

    def test_zero_e_lacuna_nao_sao_equivalentes(self):
        r = next(r for r in self.painel(competencia='2026-07')['lojas'] if r['chave_loja'] == '0005')
        self.assertIsNone(r['negocios'])
        self.assertEqual(r['negocios_informados'], 0)
        self.assertIsNone(r['nunca_produziu'])
        self.assertEqual(r['situacao_negocios'], 'Indeterminado')

    def test_tres_zeros_confirmados_permitem_inatividade_apos_lacuna(self):
        for r in self.t['cobertura']:
            if r['CHAVE_LOJA'] == '0005' and r['COMPETENCIA'] == '2026-06' and r['DOMINIO_DADOS'] == 'NEGOCIO':
                r['STATUS_COMPLETUDE'] = 'AUSENTE'; r['DATA_VALIDACAO'] = None
            if r['CHAVE_LOJA'] == '0005' and r['COMPETENCIA'] == '2026-07':
                r['STATUS_COMPLETUDE'] = 'COMPLETO'; r['DATA_VALIDACAO'] = '2026-07-31'
        self.save()
        r = next(r for r in self.painel()['lojas'] if r['chave_loja'] == '0005')
        self.assertEqual(r['situacao_negocios'], 'Inativo')
        self.assertIsNone(r['nunca_produziu'])

    def test_medias_mediana_percentual_e_reativacao(self):
        d = self.painel()['indicadores']
        esperado = {'Q01': 5, 'Q02': 1, 'Q03': 20, 'Q04': 1, 'Q05': 5, 'Q06': 0, 'Q09': 2, 'Q10': 1, 'Q12': 0, 'Q13': 1}
        for codigo, valor in esperado.items(): self.assertEqual(d[codigo]['valor'], valor, codigo)
        self.assertEqual(d['Q11']['denominador'], 2)  # Lojas 0001 e 0004 já inativas em agosto.
        self.assertEqual(d['Q11']['valor'], 50)

    def test_idades_so_aceitam_elegiveis_observados(self):
        d = self.painel()['indicadores']
        self.assertEqual(d['Q07_M5']['valor'], 40)
        self.assertEqual(d['Q07_M6']['valor'], 25)
        self.assertEqual(d['Q07_M6']['denominador'], 4)
        self.assertIsNone(d['Q07_M12']['valor'])

    def test_treinamento_posterior_nao_vaza_para_m5_m6(self):
        d = self.painel()
        linhas = {r['chave_loja']: r for r in d['lojas']}
        self.assertEqual(linhas['0001']['treinamento'], 'Realizado')
        grupos = {(r['idade'], r['treinamento']): r for r in d['treinamento_idade']}
        self.assertEqual(grupos[5, 'Realizado']['lojas'], 1)
        self.assertEqual(grupos[5, 'Não informado']['lojas'], 4)

    def test_responsavel_mensal_e_origem_do_contrato(self):
        d = self.painel(gerencia='São Paulo', responsavel='R2')
        self.assertEqual(len(d['lojas']), 1)
        self.assertEqual(d['lojas'][0]['chave_loja'], '0001')
        self.assertEqual(d['indicadores']['F01']['valor'], 0)
        antigo = self.painel(competencia='2026-06', gerencia='Sul', responsavel='R1')
        self.assertEqual(len(antigo['lojas']), 5)

    def test_suporte_sem_registro_entra_como_pendencia(self):
        d = self.painel()
        self.assertEqual(d['indicadores']['T03']['denominador'], 5)
        self.assertEqual(d['indicadores']['T03']['valor'], 0)
        self.assertEqual(len(d['pendencias_suporte']), 10)

    def test_habilitacao_parcial_separada_do_denominador(self):
        d = self.painel(competencia='2026-01')
        self.assertEqual(d['servicos'][0]['habilitacoes_parciais'], 5)
        self.assertEqual(d['servicos'][0]['habilitadas_observaveis'], 0)

    def test_comparacao_taxa_em_pp_e_base_zero_indisponivel(self):
        d = self.painel()['indicadores']
        self.assertEqual(d['Q03']['mensal']['unidade'], 'p.p.')
        self.assertEqual(d['Q03']['mensal']['variacao'], 20)
        self.assertIsNone(d['Q02']['mensal']['variacao'])
        self.assertIsNone(taxa(1, 0))

    def test_competencia_parcial_nao_recebe_comparacoes(self):
        d = self.painel(competencia='2026-10')
        self.assertTrue(d['parcial'])
        self.assertEqual(d['fechamento'], 'PROVISÓRIO')
        self.assertTrue(all(i['mensal']['variacao'] is None for i in d['indicadores'].values()))

    def test_duplicidade_producao_bloqueia_e_mantem_publicacao(self):
        anterior = atualizar_prospeccao(self.config_path)
        self.t['producao'].append(copy.deepcopy(self.t['producao'][0])); self.save()
        with self.assertRaisesRegex(ErroImportacao, 'chave repetida'):
            atualizar_prospeccao(self.config_path)
        with abrir_base(carregar_configuracao(self.config_path)) as conn:
            self.assertEqual(ler_base(conn, carregar_configuracao(self.config_path))['versao'], anterior['versao'])
        d = json.loads(self.request()[1]); self.assertEqual(d['ultima_validacao']['estado'], 'BLOQUEADO')

    def test_chave_loja_repete_nos_fatos_e_nao_no_cadastro(self):
        self.assertGreater(len(self.t['producao']), len(self.t['credenciados']))
        self.base()
        self.t['credenciados'].append(copy.deepcopy(self.t['credenciados'][0])); self.save()
        with self.assertRaisesRegex(ErroImportacao, 'chave repetida'): self.base()

    def test_sobreposicao_de_vinculos_e_referencias_inexistentes(self):
        self.t['vinculacoes'][0]['FIM_VIGENCIA'] = None; self.save()
        with self.assertRaisesRegex(ErroImportacao, 'sobrepostas'): self.base()
        self.t = fixture(); self.t['producao'][0]['ID_SERVICO'] = 'INEXISTENTE'; self.save()
        with self.assertRaisesRegex(ErroImportacao, 'não existe'): self.base()

    def test_aprovacao_antes_da_emissao_bloqueia(self):
        self.t['status_contrato'][0]['DATA_EVENTO'] = '2020-01-01'; self.save()
        with self.assertRaisesRegex(ErroImportacao, 'anterior à emissão'): self.base()

    def test_producao_antes_do_mes_de_inauguracao_bloqueia(self):
        self.t['producao'][0]['COMPETENCIA'] = '2025-12'; self.save()
        with self.assertRaisesRegex(ErroImportacao, 'anterior ao mês de inauguração'): self.base()

    def test_producao_sem_habilitacao_e_aviso_sem_correcao(self):
        self.t['habilitacoes'] = []; self.save()
        b = self.base()
        self.assertGreater(b['auditoria']['avisos'], 0)
        self.assertEqual(analise(b, {})['indicadores']['Q01']['valor'], 5)
        self.assertEqual(analise(b, {})['fechamento'], 'PROVISÓRIO')

    def test_quantidade_liquida_nao_subtrai_estornos_novamente(self):
        for r in self.t['producao']: r['QTD_ESTORNADA'] = 999
        self.save()
        self.assertEqual(self.painel()['indicadores']['Q01']['valor'], 5)

    def test_quantidade_bruta_consolidada_uma_vez(self):
        self.config['prospeccao']['quantidade_producao'] = 'bruta_menos_estornos'
        for r in self.t['producao']:
            r['QTD_CONFIRMADA'], r['QTD_ESTORNADA'], r['QTD_VALIDA'] = r['QTD_VALIDA'] + 2, 2, None
        self.save()
        self.assertEqual(self.painel()['indicadores']['Q01']['valor'], 5)

    def test_cobertura_completa_exige_data_de_validacao(self):
        self.t['cobertura'][0]['DATA_VALIDACAO'] = None; self.save()
        with self.assertRaisesRegex(ErroImportacao, 'exige DATA_VALIDACAO'): self.base()

    def test_colunas_cnpj_e_mapeamento_explicito_preservam_ids(self):
        arquivo = self.sources / 'credenciados.csv'
        s = arquivo.read_text(encoding='utf-8-sig').replace('CNPJ;', 'NO_CNPJ;').replace('RAZAO_SOCIAL;', 'NOME_DA_EMPRESA;')
        arquivo.write_text(s, encoding='utf-8-sig')
        self.catalogo['fontes']['credenciados']['colunas'] = {'NOME_DA_EMPRESA': 'RAZAO_SOCIAL'}
        (self.root / 'catalogo_pro.json').write_text(json.dumps(self.catalogo), encoding='utf-8')
        b = self.base(); self.assertEqual(b['tabelas']['credenciados'][0]['CHAVE_LOJA'], '0001')
        self.assertTrue(any(m['origem'] == 'NO_CNPJ' and m['padrao'] == 'CNPJ' for m in b['mapeamentos']))

    def test_coluna_acumulada_desconhecida_nao_e_somada(self):
        arquivo = self.sources / 'producao.csv'
        arquivo.write_text(arquivo.read_text(encoding='utf-8-sig').replace('QTD_VALIDA', 'M6'), encoding='utf-8-sig')
        with self.assertRaisesRegex(ErroImportacao, 'sem mapeamento'): self.base()

    def test_exportacao_filtra_todas_as_paginas_e_escapa_formulas(self):
        self.t['credenciados'][0]['RAZAO_SOCIAL'] = '=HYPERLINK("exemplo")'; self.save()
        atualizar_prospeccao(self.config_path)
        response, body = self.request('/api/prospeccao/exportar.csv', {'busca': 'HYPERLINK'})
        self.assertEqual(response['status'], 200)
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 2); self.assertTrue(rows[1][1].startswith("'="))
        response, body = self.request('/api/prospeccao/exportar.csv', {'risco': 'Inativo'})
        self.assertEqual(len(list(csv.reader(io.StringIO(body.decode('utf-8-sig')), delimiter=';'))), 3)

    def test_autenticacao_metadados_detalhe_e_static_protegidos(self):
        atualizar_prospeccao(self.config_path)
        app = criar_aplicacao(self.config_path, usuario='davi', senha='segredo-teste')
        auth = 'Basic ' + base64.b64encode(b'davi:segredo-teste').decode()
        for path, params in [('/api/prospeccao/metadados', {}), ('/api/prospeccao/painel', {}),
                             ('/api/prospeccao/exportar.csv', {}), ('/api/prospeccao/loja', {'chave_loja': '0001'}),
                             ('/static/prospeccao.js', {}), ('/static/prospeccao.css', {})]:
            self.assertEqual(self.request(path, params, app=app)[0]['status'], 401)
            self.assertEqual(self.request(path, params, app=app, auth=auth)[0]['status'], 200)

    def test_api_recusa_futuro_duplicacao_de_parametro_e_post(self):
        atualizar_prospeccao(self.config_path)
        self.assertEqual(self.request(params={'competencia': '2030-01'})[0]['status'], 400)
        self.assertEqual(self.request(params={'parametro_inventado': 'x'})[0]['status'], 400)
        self.assertEqual(self.request(params=[('competencia', '2026-08'), ('competencia', '2026-09')])[0]['status'], 400)
        self.assertEqual(self.request(params={'competencia': '2026-09qualquertexto'})[0]['status'], 400)
        self.assertEqual(self.request(method='POST')[0]['status'], 405)
        self.assertEqual(self.request('/planilhas_prospeccao/producao.csv')[0]['status'], 404)
        self.assertEqual(self.request('/catalogo_prospeccao.json')[0]['status'], 404)

    def test_multiplos_contratos_de_origem_da_mesma_loja_sao_ambiguos(self):
        r = copy.deepcopy(self.t['contrato_loja'][0]); r['ID_CONTRATO'] = 'C2'
        self.t['contrato_loja'].append(r); self.save()
        with self.assertRaisesRegex(ErroImportacao, 'mais de um contrato de origem'): self.base()

    def test_quantidade_nao_liquida_nao_pode_ter_duas_formulas(self):
        self.config['prospeccao']['quantidade_producao'] = 'bruta_menos_estornos'; self.save()
        with self.assertRaisesRegex(ErroImportacao, 'QTD_VALIDA vazia'): self.base()

    def test_mes_ausente_em_arquivo_nao_cria_zeros_automaticos(self):
        self.t['cobertura'] = [r for r in self.t['cobertura'] if r['COMPETENCIA'] != '2026-09']; self.save()
        d = self.painel()
        self.assertIsNone(d['indicadores']['Q01']['valor'])
        self.assertEqual(d['riscos']['Indeterminado'], 5)

    def test_importacao_conjunta_reverte_consultas_se_prospeccao_falhar(self):
        shutil.copytree(PROJETO / 'planilhas_aprovadas', self.root / 'entradas_acesso')
        atualizar_dashboard(self.config_path)
        with sqlite3.connect(self.root / 'dados/base.sqlite3') as c:
            anterior = c.execute("SELECT valor FROM metadados WHERE chave='snapshot'").fetchone()[0]
        self.t['producao'].append(copy.deepcopy(self.t['producao'][0])); self.save()
        with self.assertRaises(ErroImportacao): atualizar_dashboard(self.config_path)
        with sqlite3.connect(self.root / 'dados/base.sqlite3') as c:
            self.assertEqual(c.execute("SELECT valor FROM metadados WHERE chave='snapshot'").fetchone()[0], anterior)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM registros').fetchone()[0], 84)

    def test_validar_sem_publicar_e_arquivo_ausente(self):
        self.base(); self.assertFalse((self.root / 'dados/base.sqlite3').exists())
        (self.sources / 'producao.csv').unlink()
        with self.assertRaisesRegex(ErroImportacao, 'não encontrado'): self.base()


if __name__ == '__main__':
    unittest.main()
