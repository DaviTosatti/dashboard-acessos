"""Gera exclusivamente dados fictícios, em uma pasta nova, para demonstração."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

from prospeccao_dados import GERENCIAS, TABELAS, deslocar_mes, fim_mes, idade, mes


def gerar(destino):
    destino = Path(destino)
    if destino.exists() and any(destino.iterdir()):
        raise ValueError('Escolha uma pasta vazia. O gerador não substitui arquivos existentes.')
    destino.mkdir(parents=True, exist_ok=True)
    t = {tabela: [] for tabela in TABELAS}
    def adicionar(tabela, **campos):
        t[tabela].append(campos)
    servicos = [('TR', 'Transações bancárias', 'Atendimento', 'TRANSACAO'),
                ('CR', 'Crédito demonstrativo', 'Crédito', 'NEGOCIO'),
                ('CO', 'Consórcio demonstrativo', 'Consórcio', 'NEGOCIO'),
                ('OU', 'Outro negócio demonstrativo', 'Outros', 'NEGOCIO')]
    for ident, nome, categoria, tipo in servicos:
        adicionar('servicos', ID_SERVICO=ident, NOME=nome, CATEGORIA=categoria, TIPO_ATIVIDADE=tipo)
    safras = ['2024-09', '2025-09', '2026-02', '2026-04', '2026-05', '2026-06', '2026-08', '2026-09']
    municipios = ['Curitiba', 'Belo Horizonte', 'Recife', 'Salvador', 'Goiânia', 'Campinas']
    ufs = ['PR', 'MG', 'PE', 'BA', 'GO', 'SP']
    for regiao, gerencia in enumerate(GERENCIAS):
        for numero in [1, 2]:
            adicionar('responsaveis', ID_RESPONSAVEL=f'R{regiao + 1}{numero}', NOME=f'Consultor exemplo {regiao + 1}.{numero}', TIPO_RESPONSAVEL='CONSULTOR')
        for safra_indice, safra in enumerate(safras):
            indice = regiao * len(safras) + safra_indice
            chave = f'{1000 + indice:06d}'
            contrato = f'CT{1000 + indice}'
            responsavel = f'R{regiao + 1}{1 + indice % 2}'
            inauguracao = safra + '-10'
            emissao = deslocar_mes(safra, -1) + '-05'
            aprovacao = deslocar_mes(safra, -1) + '-18'
            encerramento = '2026-08-20' if indice % 11 == 10 and safra < '2026-08' else None
            condicao_treino = indice % 3
            adicionar('credenciados', CHAVE_LOJA=chave, RAZAO_SOCIAL=f'Comércio fictício {indice + 1:02d}',
                MUNICIPIO=municipios[regiao], UF=ufs[regiao], BAIRRO=f'Bairro exemplo {1 + indice % 3}',
                RAMO_ATIVIDADE=['Mercado', 'Farmácia', 'Papelaria'][indice % 3], DATA_INAUGURACAO=inauguracao,
                DATA_ENCERRAMENTO=encerramento, MOTIVO_ENCERRAMENTO='Encerramento fictício' if encerramento else None,
                TREINAMENTO_STATUS='NAO_REALIZADO' if condicao_treino == 1 else 'NAO_INFORMADO')
            adicionar('contratos', ID_CONTRATO=contrato, DATA_EMISSAO=emissao, GERENCIA_ORIGEM=gerencia, RESPONSAVEL_ORIGEM=responsavel)
            adicionar('status_contrato', ID_EVENTO='EV' + contrato, ID_CONTRATO=contrato, STATUS='APROVADO', DATA_EVENTO=aprovacao)
            adicionar('contrato_loja', ID_CONTRATO=contrato, CHAVE_LOJA=chave, DATA_INICIO=aprovacao, TIPO_VINCULO='INAUGURACAO')
            adicionar('vinculacoes', ID_VINCULACAO='V' + chave, CHAVE_LOJA=chave, GERENCIA=gerencia, ID_RESPONSAVEL=responsavel, INICIO_VIGENCIA=inauguracao)
            for ident, *_ in servicos:
                adicionar('habilitacoes', ID_HABILITACAO='H' + chave + ident, CHAVE_LOJA=chave, ID_SERVICO=ident, DATA_INICIO=inauguracao, SITUACAO='HABILITADO')
            if condicao_treino == 0:
                acao = 'T' + chave
                data_treino = (date.fromisoformat(inauguracao) - timedelta(days=3)).isoformat()
                adicionar('acompanhamentos', ID_ACAO=acao, CHAVE_LOJA=chave, TIPO_ACAO='TREINAMENTO',
                    DATA_PREVISTA=data_treino, DATA_REALIZADA=data_treino, STATUS='CONCLUIDO', MODALIDADE='Presencial', COM_MULTIPLICADOR='SIM', ID_EXECUTOR=responsavel)
                for ident in ['CR', 'CO']:
                    adicionar('acao_servico', ID_ACAO=acao, ID_SERVICO=ident)
            for marco in [2, 4]:
                prevista = fim_mes(deslocar_mes(safra, marco))
                if prevista <= '2026-09-30' and indice % 4 != 3:
                    realizada = (date.fromisoformat(prevista) + timedelta(days=3 if indice % 4 == 2 else -2)).isoformat()
                    if realizada > '2026-10-15':
                        realizada = None
                    adicionar('acompanhamentos', ID_ACAO=f'S{chave}{marco}', CHAVE_LOJA=chave, TIPO_ACAO='SUPORTE',
                        MARCO_OPERACIONAL=marco, DATA_PREVISTA=prevista, DATA_REALIZADA=realizada,
                        STATUS='CONCLUIDO' if realizada else 'PLANEJADO', MODALIDADE='Remoto', ID_EXECUTOR=responsavel)
            for numero_mes in range(idade(inauguracao, '2026-10') + 1):
                competencia = deslocar_mes(safra, numero_mes)
                if encerramento and competencia > mes(encerramento):
                    continue
                perfil = indice % 8
                recuo = idade(competencia, '2026-09')
                zero = perfil == 5 or (perfil == 1 and recuo == 0) or (perfil == 2 and recuo in {0, 1}) or (perfil == 3 and recuo in {0, 1, 2, 3}) or (perfil == 4 and recuo in {1, 2, 3})
                incompleto = perfil == 6 and competencia == '2026-09'
                for dominio in ['NEGOCIO', 'TRANSACAO']:
                    completo = competencia < '2026-10' and not (incompleto and dominio == 'NEGOCIO')
                    validacao = (date.fromisoformat(fim_mes(competencia)) + timedelta(days=2)).isoformat() if completo else None
                    adicionar('cobertura', CHAVE_LOJA=chave, COMPETENCIA=competencia, DOMINIO_DADOS=dominio,
                        STATUS_COMPLETUDE='COMPLETO' if completo else 'PARCIAL', DATA_VALIDACAO=validacao)
                for s, *_ in servicos:
                    qtd = 30 + indice % 20 if s == 'TR' else 0 if zero else 1 + (indice + numero_mes + len(s)) % 7
                    if s == 'OU' and indice % 2:
                        qtd = 0
                    adicionar('producao', CHAVE_LOJA=chave, COMPETENCIA=competencia, ID_SERVICO=s, QTD_VALIDA=qtd)
        # Safras comparáveis de emissão; incluem contratos sem loja e diferentes decisões.
        for competencia in ['2025-09', '2026-08', '2026-09', '2026-10']:
            for n, situacao in enumerate(['APROVADO', 'PENDENTE', 'REPROVADO', 'DESISTENCIA', 'APROVADO']):
                ident = f'EX{regiao}{competencia.replace("-", "")}{n}'
                adicionar('contratos', ID_CONTRATO=ident, DATA_EMISSAO=competencia + '-02', GERENCIA_ORIGEM=gerencia, RESPONSAVEL_ORIGEM=f'R{regiao + 1}{1 + n % 2}')
                if situacao != 'PENDENTE':
                    adicionar('status_contrato', ID_EVENTO='E' + ident, ID_CONTRATO=ident, STATUS=situacao, DATA_EVENTO=competencia + '-08')
                if n == 4 and competencia != '2026-10':
                    adicionar('status_contrato', ID_EVENTO='C' + ident, ID_CONTRATO=ident, STATUS='CANCELADO', DATA_EVENTO=competencia + '-21', MOTIVO='Cancelamento fictício após aprovação')
    for tabela, (_, campos) in TABELAS.items():
        with (destino / (tabela + '.csv')).open('w', encoding='utf-8-sig', newline='') as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=';', extrasaction='raise')
            escritor.writeheader()
            escritor.writerows(t[tabela])
    return {nome: len(linhas) for nome, linhas in t.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', default='exemplos_prospeccao')
    args = parser.parse_args()
    print(json.dumps(gerar(args.destino), ensure_ascii=False, indent=2))
