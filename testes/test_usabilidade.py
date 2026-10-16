"""Regressão de intervalos, atividades e atribuição histórica de consultores."""
import base64
import copy
import csv
import io
import json
import unittest

import test_prospeccao as fixtures
from consultores import atividades, painel_consultores
from prospeccao import atualizar_prospeccao
from prospeccao_calculos import analise
from servidor import criar_aplicacao


class MelhoriasTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.ProspeccaoTests(methodName='runTest')
        self.h.setUp()

    def tearDown(self):
        self.h.tearDown()

    def test_intervalo_inclusivo_soma_volumes_e_preserva_risco_do_ultimo_mes(self):
        d = self.h.painel(inicio='2026-07', fim='2026-09')
        self.assertEqual(d['periodo'], {'inicio':'2026-07','fim':'2026-09','meses':3})
        self.assertEqual(d['indicadores']['F01']['valor'], 2)
        self.assertEqual(d['indicadores']['Q01']['valor'], 6)
        self.assertEqual(d['indicadores']['Q09']['valor'], 2)
        self.assertEqual(d['indicadores']['Q03']['valor'], 20)
        self.assertEqual(len(d['tendencia']), 3)
        self.assertTrue(all(r['competencia'] == '2026-09' for r in d['lojas']))

    def test_taxa_do_periodo_e_recalculada_pelos_contratos(self):
        d = self.h.painel(inicio='2025-09', fim='2026-08')['indicadores']
        self.assertEqual(d['F01']['valor'], 4)
        self.assertEqual(d['F03']['numerador'], 3)
        self.assertEqual(d['F03']['valor'], 75)
        self.assertEqual(d['F08']['valor'], 200 / 3)

    def test_aprovacao_repetida_em_meses_diferentes_conta_um_contrato(self):
        molde = self.h.t['status_contrato'][0]
        for ident, data in [('RE1','2026-07-01'),('RE2','2026-08-01')]:
            r = copy.deepcopy(molde); r.update(ID_EVENTO=ident, DATA_EVENTO=data)
            self.h.t['status_contrato'].append(r)
        self.h.save()
        d = self.h.painel(inicio='2026-07', fim='2026-08')
        self.assertEqual(d['indicadores']['F02']['valor'],1)
        soma = sum(self.h.painel(competencia=m)['indicadores']['F02']['valor'] for m in ['2026-07','2026-08'])
        self.assertEqual(soma,2)

    def test_comparacao_anterior_tem_a_mesma_duracao(self):
        d = self.h.painel(inicio='2026-07', fim='2026-09')['indicadores']
        self.assertEqual(d['Q01']['mensal']['inicio'],'2026-04')
        self.assertEqual(d['Q01']['mensal']['competencia'],'2026-06')
        self.assertEqual(d['F01']['anual']['inicio'],'2025-07')
        self.assertEqual(d['F01']['anual']['competencia'],'2025-09')
        self.assertEqual(d['Q03']['mensal']['unidade'],'p.p.')

    def test_intervalo_de_um_mes_equivale_a_consulta_legada(self):
        a = self.h.painel(competencia='2026-09')
        b = self.h.painel(inicio='2026-09', fim='2026-09')
        self.assertEqual(a['indicadores'],b['indicadores'])
        self.assertEqual(a['lojas'],b['lojas'])

    def test_intervalos_invalidos_sao_recusados(self):
        atualizar_prospeccao(self.h.config_path)
        for params in [{'inicio':'2026-09'}, {'fim':'2026-09'}, {'inicio':'2026-09','fim':'2026-07'},
                       {'inicio':'2026-09','fim':'2027-01'}, {'inicio':'2026-01','fim':'2026-09','competencia':'2026-09'},
                       {'inicio':'2000-01','fim':'2026-09'}, {'inicio':'2026-01x','fim':'2026-09'}]:
            with self.subTest(params=params): self.assertEqual(self.h.request(params=params)[0]['status'],400)

    def test_producao_do_periodo_respeita_troca_de_responsavel(self):
        r1 = self.h.painel(inicio='2026-05',fim='2026-09',responsavel='R1')
        r2 = self.h.painel(inicio='2026-05',fim='2026-09',responsavel='R2')
        self.assertEqual(r1['indicadores']['Q01']['valor'],7)
        self.assertEqual(r2['indicadores']['Q01']['valor'],5)
        d = painel_consultores(self.h.base(), {'inicio':'2026-05','fim':'2026-09'})
        por_id = {r['id']:r for r in d['consultores']}
        self.assertEqual(por_id['R1']['negocios'],7)
        self.assertEqual(por_id['R2']['negocios'],5)

    def test_regiao_consulta_todos_os_consultores_do_recorte(self):
        d = painel_consultores(self.h.base(), {'inicio':'2026-07','fim':'2026-09','gerencia':'Sul'})
        self.assertEqual({r['id'] for r in d['consultores']},{'R1'})
        self.assertTrue(all(r['gerencia'] == 'Sul' for r in d['atividades']))

    def test_carteira_sem_atividade_continua_no_resumo(self):
        for r in self.h.t['producao']: r['QTD_VALIDA'] = 0
        self.h.t['contratos'] = []; self.h.t['status_contrato'] = []; self.h.t['contrato_loja'] = []
        self.h.t['acompanhamentos'] = []; self.h.save()
        d = painel_consultores(self.h.base(), {'inicio':'2026-07','fim':'2026-09','gerencia':'São Paulo'})
        self.assertEqual(d['total'],0)
        self.assertEqual(d['consultores'][0]['id'],'R2')
        self.assertEqual(d['consultores'][0]['negocios'],0)

    def test_executor_e_carteira_sao_atribuicoes_distintas(self):
        acao = self.h.t['acompanhamentos'][0]; acao['ID_EXECUTOR'] = 'R1'; self.h.save()
        itens = atividades(self.h.base(), {'inicio':'2026-08','fim':'2026-09','responsavel':'R1'})
        treino = next(r for r in itens if r['tipo'] == 'Treinamento realizado')
        self.assertEqual(treino['id_responsavel'],'R1')
        self.assertEqual(treino['gerencia'],'São Paulo')
        self.assertFalse(any(r['chave_loja']=='0001' and r['natureza']=='producao' for r in itens))

    def test_acao_sem_executor_nao_e_creditada_ao_consultor_da_carteira(self):
        d = painel_consultores(self.h.base(), {'inicio':'2026-08','fim':'2026-09'})
        self.assertEqual(d['totais']['sem_executor'],1)
        self.assertEqual(d['totais']['acompanhamentos'],0)

    def test_cobertura_ausente_exclui_quantidade_confirmada_das_atividades(self):
        for r in self.h.t['cobertura']:
            if r['CHAVE_LOJA']=='0001' and r['COMPETENCIA']=='2026-09' and r['DOMINIO_DADOS']=='NEGOCIO':
                r.update(STATUS_COMPLETUDE='PARCIAL',DATA_VALIDACAO=None)
        self.h.save()
        d = painel_consultores(self.h.base(), {'inicio':'2026-09','fim':'2026-09','responsavel':'R2'})
        self.assertEqual(d['totais']['negocios'],0)
        r = next(r for r in d['atividades'] if r['tipo']=='Produção de negócios')
        self.assertIsNone(r['quantidade']); self.assertEqual(r['quantidade_informada'],5)
        self.assertFalse(r['completo'])

    def test_pendencia_e_avaliada_ate_o_fim_do_intervalo(self):
        a = copy.deepcopy(self.h.t['acompanhamentos'][0])
        a.update(ID_ACAO='SUP',TIPO_ACAO='SUPORTE',MARCO_OPERACIONAL=4,DATA_PREVISTA='2026-05-31',DATA_REALIZADA='2026-08-01',STATUS='CONCLUIDO',ID_EXECUTOR='R1')
        self.h.t['acompanhamentos'].append(a); self.h.save()
        pend = atividades(self.h.base(), {'inicio':'2026-05','fim':'2026-06','tipo_atividade':'Suporte M4 pendente'})
        self.assertTrue(any(r['chave_loja']=='0001' for r in pend))
        feitos = atividades(self.h.base(), {'inicio':'2026-08','fim':'2026-08','tipo_atividade':'Suporte M4 realizado'})
        self.assertEqual(len(feitos),1)

    def test_busca_sem_acentos_tipo_e_consultor_se_combinam(self):
        d = painel_consultores(self.h.base(), {'inicio':'2026-01','fim':'2026-09','responsavel':'R1','tipo_atividade':'Produção de negócios','atividade_busca':'NEGOCIO'})
        self.assertTrue(d['total'])
        self.assertTrue(all(r['id_responsavel']=='R1' and r['tipo']=='Produção de negócios' for r in d['atividades']))
        d2 = painel_consultores(self.h.base(), {'inicio':'2026-01','fim':'2026-09','atividade_busca':"' OR 1=1"})
        self.assertEqual(d2['total'],0)

    def test_exportacao_de_atividades_contem_todas_as_paginas(self):
        atualizar_prospeccao(self.h.config_path)
        params={'inicio':'2026-01','fim':'2026-09','atividade_por_pagina':'25'}
        response, body = self.h.request('/api/prospeccao/consultores',params)
        d=json.loads(body); self.assertEqual(response['status'],200); self.assertGreater(d['total'],25)
        response, body = self.h.request('/api/prospeccao/consultores.csv',params)
        rows=list(csv.reader(io.StringIO(body.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(rows),d['total']+1)
        self.assertEqual(len(d['atividades']),25)
        proxima=json.loads(self.h.request('/api/prospeccao/consultores',dict(params,atividade_pagina='2'))[1])
        self.assertTrue({r['id'] for r in d['atividades']}.isdisjoint({r['id'] for r in proxima['atividades']}))

    def test_csv_de_atividades_escapa_formulas(self):
        self.h.t['credenciados'][0]['RAZAO_SOCIAL']='=COMANDO()';self.h.save();atualizar_prospeccao(self.h.config_path)
        body=self.h.request('/api/prospeccao/consultores.csv',{'inicio':'2026-01','fim':'2026-09','atividade_busca':'COMANDO'})[1]
        rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')),delimiter=';'))
        self.assertTrue(rows); self.assertTrue(all(r['razao_social'].startswith("'=") for r in rows))

    def test_api_atividades_autenticada_e_tipo_validado(self):
        atualizar_prospeccao(self.h.config_path)
        app=criar_aplicacao(self.h.config_path,usuario='teste',senha='teste-local')
        auth='Basic '+base64.b64encode(b'teste:teste-local').decode()
        for path in ['/api/prospeccao/consultores','/api/prospeccao/consultores.csv','/static/filter-selects.js','/static/filter-selects.css','/static/prospeccao-consultores.js']:
            self.assertEqual(self.h.request(path,app=app)[0]['status'],401)
            self.assertEqual(self.h.request(path,app=app,auth=auth)[0]['status'],200)
        self.assertEqual(self.h.request('/api/prospeccao/consultores',{'tipo_atividade':'inventada'})[0]['status'],400)

    def test_intervalo_parcial_suspende_comparacoes_e_exibe_lacunas(self):
        d=self.h.painel(inicio='2026-09',fim='2026-10')
        self.assertTrue(d['parcial'])
        self.assertGreater(d['qualidade_dados']['incompletas_periodo'],0)
        self.assertIsNone(d['indicadores']['F01']['mensal']['variacao'])

    def test_exportacao_de_risco_continua_sendo_fechamento_final(self):
        atualizar_prospeccao(self.h.config_path)
        body=self.h.request('/api/prospeccao/exportar.csv',{'inicio':'2026-07','fim':'2026-09'})[1]
        rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(rows),5)
        self.assertEqual({r['competencia'] for r in rows},{'2026-09'})


if __name__ == '__main__':
    unittest.main()
