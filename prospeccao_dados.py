"""Contrato de entrada, normalização explícita e validação da prospecção.

CHAVE_LOJA é única no cadastro. Nas bases de fatos, a unicidade é composta.
Nenhuma consulta a serviços externos é feita por este módulo.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from integracao import ErroImportacao, data_iso, linhas_csv, linhas_excel, normalizar
from padronizacao import texto_cnpj, texto_identificador

GERENCIAS = ['Sul', 'Sudeste', 'Nordeste 1', 'Nordeste 2', 'Centro-Oeste/Norte', 'São Paulo']
VERSAO_REGRA = 'expresso-1.0'

# O primeiro conjunto contém os campos que precisam estar preenchidos em cada linha.
TABELAS = {
    'credenciados': (['CHAVE_LOJA', 'RAZAO_SOCIAL', 'DATA_INAUGURACAO'],
        ['CHAVE_LOJA', 'CNPJ', 'RAZAO_SOCIAL', 'MUNICIPIO', 'UF', 'BAIRRO', 'RAMO_ATIVIDADE', 'DATA_INAUGURACAO', 'DATA_ENCERRAMENTO', 'MOTIVO_ENCERRAMENTO', 'TREINAMENTO_STATUS']),
    'responsaveis': (['ID_RESPONSAVEL', 'NOME'], ['ID_RESPONSAVEL', 'NOME', 'TIPO_RESPONSAVEL']),
    'servicos': (['ID_SERVICO', 'NOME', 'CATEGORIA', 'TIPO_ATIVIDADE'],
        ['ID_SERVICO', 'NOME', 'CATEGORIA', 'TIPO_ATIVIDADE', 'VIGENCIA_INICIO', 'VIGENCIA_FIM']),
    'contratos': (['ID_CONTRATO', 'DATA_EMISSAO', 'GERENCIA_ORIGEM', 'RESPONSAVEL_ORIGEM'],
        ['ID_CONTRATO', 'DATA_EMISSAO', 'GERENCIA_ORIGEM', 'RESPONSAVEL_ORIGEM', 'ID_CONTRATO_ANTERIOR']),
    'status_contrato': (['ID_EVENTO', 'ID_CONTRATO', 'STATUS', 'DATA_EVENTO'],
        ['ID_EVENTO', 'ID_CONTRATO', 'STATUS', 'DATA_EVENTO', 'MOTIVO']),
    'contrato_loja': (['ID_CONTRATO', 'CHAVE_LOJA'],
        ['ID_CONTRATO', 'CHAVE_LOJA', 'TIPO_VINCULO', 'DATA_INICIO', 'DATA_FIM']),
    'vinculacoes': (['ID_VINCULACAO', 'CHAVE_LOJA', 'GERENCIA', 'ID_RESPONSAVEL', 'INICIO_VIGENCIA'],
        ['ID_VINCULACAO', 'CHAVE_LOJA', 'GERENCIA', 'ID_RESPONSAVEL', 'INICIO_VIGENCIA', 'FIM_VIGENCIA']),
    'producao': (['CHAVE_LOJA', 'COMPETENCIA', 'ID_SERVICO'],
        ['CHAVE_LOJA', 'COMPETENCIA', 'ID_SERVICO', 'QTD_CONFIRMADA', 'QTD_ESTORNADA', 'QTD_VALIDA', 'VALOR_FINANCEIRO']),
    'habilitacoes': (['ID_HABILITACAO', 'CHAVE_LOJA', 'ID_SERVICO', 'DATA_INICIO', 'SITUACAO'],
        ['ID_HABILITACAO', 'CHAVE_LOJA', 'ID_SERVICO', 'DATA_INICIO', 'DATA_FIM', 'SITUACAO']),
    'cobertura': (['CHAVE_LOJA', 'COMPETENCIA', 'DOMINIO_DADOS', 'STATUS_COMPLETUDE'],
        ['CHAVE_LOJA', 'COMPETENCIA', 'DOMINIO_DADOS', 'STATUS_COMPLETUDE', 'DATA_VALIDACAO']),
    'acompanhamentos': (['ID_ACAO', 'CHAVE_LOJA', 'TIPO_ACAO', 'STATUS'],
        ['ID_ACAO', 'CHAVE_LOJA', 'TIPO_ACAO', 'MARCO_OPERACIONAL', 'DATA_PREVISTA', 'DATA_REALIZADA', 'STATUS', 'MODALIDADE', 'COM_MULTIPLICADOR', 'ID_EXECUTOR', 'MOTIVO_NAO_REALIZACAO']),
    'acao_servico': (['ID_ACAO', 'ID_SERVICO'], ['ID_ACAO', 'ID_SERVICO']),
}
CHAVES = {
    'credenciados': ['CHAVE_LOJA'], 'responsaveis': ['ID_RESPONSAVEL'], 'servicos': ['ID_SERVICO'],
    'contratos': ['ID_CONTRATO'], 'status_contrato': ['ID_EVENTO'],
    'contrato_loja': ['ID_CONTRATO', 'CHAVE_LOJA', 'DATA_INICIO'], 'vinculacoes': ['ID_VINCULACAO'],
    'producao': ['CHAVE_LOJA', 'COMPETENCIA', 'ID_SERVICO'], 'habilitacoes': ['ID_HABILITACAO'],
    'cobertura': ['CHAVE_LOJA', 'COMPETENCIA', 'DOMINIO_DADOS'], 'acompanhamentos': ['ID_ACAO'],
    'acao_servico': ['ID_ACAO', 'ID_SERVICO'],
}
ALIASES = {'NO_CNPJ': 'CNPJ', 'ID_CREDENCIADO': 'CHAVE_LOJA', 'CHAVE_DA_LOJA': 'CHAVE_LOJA',
           'DATA_HORA_EVENTO': 'DATA_EVENTO'}
ENUMS = {
    ('servicos', 'TIPO_ATIVIDADE'): {'NEGOCIO', 'TRANSACAO'},
    ('status_contrato', 'STATUS'): {'PENDENTE', 'APROVADO', 'REPROVADO', 'DESISTENCIA', 'CANCELADO'},
    ('cobertura', 'DOMINIO_DADOS'): {'NEGOCIO', 'TRANSACAO'},
    ('cobertura', 'STATUS_COMPLETUDE'): {'COMPLETO', 'PARCIAL', 'AUSENTE'},
    ('habilitacoes', 'SITUACAO'): {'HABILITADO', 'SUSPENSO'},
    ('acompanhamentos', 'TIPO_ACAO'): {'TREINAMENTO', 'SUPORTE'},
    ('acompanhamentos', 'STATUS'): {'CONCLUIDO', 'PLANEJADO', 'NAO_REALIZADO', 'NAO_INFORMADO'},
    ('credenciados', 'TREINAMENTO_STATUS'): {'REALIZADO', 'NAO_REALIZADO', 'NAO_INFORMADO'},
}


def nome_campo(valor):
    return re.sub(r'[^A-Z0-9]+', '_', normalizar(valor).upper()).strip('_')


def mes(valor):
    texto = str(valor)
    try:
        if re.fullmatch(r'\d{4}-\d{2}', texto):
            date.fromisoformat(texto + '-01')
        elif re.match(r'^\d{4}-\d{2}-\d{2}(?:T|$)', texto):
            datetime.fromisoformat(texto)
        else:
            raise ValueError
    except ValueError as exc:
        raise ErroImportacao('Competência inválida. Use AAAA-MM ou uma data ISO válida.') from exc
    return texto[:7]


def deslocar_mes(valor, quantidade):
    ano, numero = map(int, mes(valor).split('-'))
    indice = ano * 12 + numero - 1 + quantidade
    return f'{indice // 12:04d}-{indice % 12 + 1:02d}'


def fim_mes(valor):
    ano, numero = map(int, mes(valor).split('-'))
    return f'{ano:04d}-{numero:02d}-{calendar.monthrange(ano, numero)[1]:02d}'


def idade(inauguracao, competencia):
    a, m = map(int, mes(inauguracao).split('-'))
    b, n = map(int, mes(competencia).split('-'))
    return (b - a) * 12 + n - m


class Validacao:
    def __init__(self):
        self.itens = []
        self.erros = 0
        self.avisos = 0

    def registrar(self, nivel, codigo, mensagem, origem=None):
        if nivel == 'ERRO':
            self.erros += 1
        else:
            self.avisos += 1
        if len(self.itens) < 1000:
            self.itens.append({'nivel': nivel, 'codigo': codigo, 'mensagem': mensagem, 'origem': origem})

    def exigir_valido(self):
        if self.erros:
            primeiro = next(i for i in self.itens if i['nivel'] == 'ERRO')
            erro = ErroImportacao(f"Prospecção: {self.erros} erro(s). {primeiro['mensagem']} A base anterior foi mantida.")
            erro.relatorio = {'erros': self.erros, 'avisos': self.avisos, 'itens': self.itens}
            raise erro


def configuracao_prospeccao(config):
    op = config.valores.get('prospeccao')
    if not op:
        return None
    if not isinstance(op, dict):
        raise ErroImportacao('prospeccao deve ser um objeto na configuração.')
    if type(op.get('ativo')) is not bool:
        raise ErroImportacao('prospeccao.ativo deve ser true ou false, sem aspas.')
    if not op.get('ativo', False):
        return None
    op = dict(op)
    corte = str(op.get('data_corte', ''))
    try:
        date.fromisoformat(corte)
    except ValueError as exc:
        raise ErroImportacao('Defina prospeccao.data_corte como AAAA-MM-DD.') from exc
    ultimo = mes(op.get('ultimo_mes_fechado', deslocar_mes(corte, -1)))
    if fim_mes(ultimo) > corte:
        raise ErroImportacao('O último mês fechado deve terminar até a data de corte.')
    op['data_corte'], op['ultimo_mes_fechado'] = corte, ultimo
    dias = op.setdefault('dias_observacao', 30)
    if type(dias) is not int or not 1 <= dias <= 730:
        raise ErroImportacao('dias_observacao deve ser um inteiro entre 1 e 730.')
    modo = op.setdefault('quantidade_producao', 'liquida')
    if modo not in {'liquida', 'bruta_menos_estornos'}:
        raise ErroImportacao('quantidade_producao deve ser liquida ou bruta_menos_estornos.')
    for campo, padrao in [('limite_linhas', 300000), ('limite_meses_por_loja', 240)]:
        if type(op.get(campo, padrao)) is not int or op.get(campo, padrao) < 1:
            raise ErroImportacao(f'{campo} deve ser um inteiro positivo.')
    return op


def converter(campo, valor, formato, tabela):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if campo == 'COMPETENCIA':
        return mes(valor.isoformat() if isinstance(valor, (datetime, date)) else valor)
    if campo.startswith('DATA_') or campo in {'INICIO_VIGENCIA', 'FIM_VIGENCIA', 'VIGENCIA_INICIO', 'VIGENCIA_FIM'}:
        if campo == 'DATA_EVENTO':
            evento = datetime.fromisoformat(data_iso(valor))
            if evento.tzinfo is not None:
                raise ValueError('Normalize DATA_EVENTO para o horário local da operação, sem sufixo de fuso.')
            return evento.isoformat(timespec='seconds')
        return data_iso(valor)[:10]
    if campo.startswith('QTD_') or campo == 'MARCO_OPERACIONAL':
        numero = float(str(valor).replace(',', '.'))
        if not numero.is_integer() or numero < 0:
            raise ValueError('Use uma quantidade inteira, finita e não negativa.')
        return int(numero)
    if campo == 'VALOR_FINANCEIRO':
        from integracao import numero_texto
        return numero_texto(valor)
    if campo == 'CNPJ':
        return texto_cnpj(valor, formato)
    if campo == 'COM_MULTIPLICADOR':
        texto = normalizar(valor).strip()
        if texto in {'sim', 'true', '1'}:
            return True
        if texto in {'nao', 'false', '0'}:
            return False
        raise ValueError('Use SIM, NÃO ou deixe vazio quando desconhecido.')
    texto = texto_identificador(valor, formato) if campo.startswith('ID_') or campo in {'CHAVE_LOJA', 'RESPONSAVEL_ORIGEM'} else str(valor).strip()
    if (tabela, campo) in ENUMS:
        texto = nome_campo(texto)
        if texto not in ENUMS[tabela, campo]:
            raise ValueError('Valor fora do domínio: ' + ', '.join(sorted(ENUMS[tabela, campo])))
    if campo in {'GERENCIA', 'GERENCIA_ORIGEM'}:
        opcoes = {nome_campo(g): g for g in GERENCIAS}
        if nome_campo(texto) not in opcoes:
            raise ValueError('Gerência deve corresponder a uma das seis gerências cadastradas.')
        texto = opcoes[nome_campo(texto)]
    return texto


def carregar_entradas(config, op):
    pasta = (config.arquivo.parent / op.get('pasta', 'planilhas_prospeccao')).resolve()
    caminho_catalogo = (config.arquivo.parent / op.get('catalogo', 'catalogo_prospeccao.json')).resolve()
    catalogo = json.loads(caminho_catalogo.read_text(encoding='utf-8'))
    if not isinstance(catalogo, dict):
        raise ErroImportacao('O catálogo de prospecção deve ser um objeto JSON.')
    fontes = catalogo.get('fontes', {})
    if not isinstance(fontes, dict) or set(fontes) != set(TABELAS):
        raise ErroImportacao('O catálogo de prospecção deve declarar todas as 12 tabelas; bases opcionais podem ter só o cabeçalho.')
    validacao = Validacao()
    tabelas = {t: [] for t in TABELAS}
    arquivos_lidos, mapeamentos = [], []
    configuracao_leitura = type(config)(config.arquivo, dict(config.valores, abas=None, linha_cabecalho=1), pasta, config.banco)
    limite = op.get('limite_linhas', 300000)
    quantidade = 0
    for tabela, fonte in fontes.items():
        if not isinstance(fonte, dict) or not isinstance(fonte.get('arquivo'), str) or not fonte['arquivo'].strip():
            raise ErroImportacao(f'Informe um arquivo para a tabela {tabela}.')
        if fonte.get('aba') is not None and not isinstance(fonte['aba'], str):
            raise ErroImportacao(f'{tabela}: aba deve ser um nome.')
        mapa = fonte.get('colunas', {})
        if not isinstance(mapa, dict) or not all(isinstance(k, str) and isinstance(val, str) and val.strip() for k, val in mapa.items()):
            raise ErroImportacao(f'{tabela}: colunas deve mapear nomes de origem para nomes de destino.')
        normalizados = {}
        for k, val in mapa.items():
            if nome_campo(k) in normalizados and normalizados[nome_campo(k)] != nome_campo(val):
                raise ErroImportacao(f'{tabela}: aliases conflitantes após normalizar os nomes.')
            normalizados[nome_campo(k)] = nome_campo(val)
        arquivo = (pasta / fonte['arquivo']).resolve()
        if not arquivo.is_file():
            raise ErroImportacao(f'Prospecção: arquivo da tabela {tabela} não encontrado: {arquivo.name}.')
        antes = arquivo.stat()
        leitor = linhas_excel if arquivo.suffix.lower() in {'.xlsx', '.xlsm'} else linhas_csv if arquivo.suffix.lower() in {'.csv', '.tsv'} else None
        if leitor is None:
            raise ErroImportacao(f'Formato não suportado: {arquivo.name}.')
        campos = None
        abas = set()
        aliases = {**ALIASES, **normalizados}
        vistos = set()
        contagem = 0
        leitura = type(config)(config.arquivo, dict(configuracao_leitura.valores, abas=[fonte['aba']] if fonte.get('aba') and leitor is linhas_excel else None), pasta, config.banco)
        for aba, linha, valores, formatos in leitor(arquivo, leitura):
            if fonte.get('aba') and aba != fonte['aba']:
                continue
            if aba not in abas:
                abas.add(aba)
                if len(abas) > 1:
                    raise ErroImportacao(f'{arquivo.name}: declare uma aba no catálogo para evitar misturar tabelas.')
                campos = []
                for valor in valores:
                    original = str(valor or '').strip()
                    padrao = aliases.get(nome_campo(original), nome_campo(original))
                    campos.append(padrao)
                    if original:
                        mapeamentos.append({'tabela': tabela, 'origem': original, 'padrao': padrao})
                    if padrao and padrao != 'IGNORAR' and padrao not in TABELAS[tabela][1]:
                        validacao.registrar('ERRO', 'COLUNA_NAO_MAPEADA', f'{tabela}: coluna {original} sem mapeamento. Ajuste o catálogo.')
                if len([c for c in campos if c and c != 'IGNORAR']) != len(set(c for c in campos if c and c != 'IGNORAR')):
                    validacao.registrar('ERRO', 'COLUNAS_AMBIGUAS', f'{tabela}: duas colunas apontam para o mesmo campo. Consolide ou mapeie explicitamente uma como IGNORAR.')
                faltantes = set(TABELAS[tabela][0]) - set(campos)
                if faltantes:
                    validacao.registrar('ERRO', 'CABECALHO', f'{tabela}: faltam colunas: {", ".join(sorted(faltantes))}.')
                continue
            if not any(v is not None and str(v).strip() for v in valores):
                continue
            origem = {'arquivo': arquivo.name, 'aba': aba, 'linha': linha, 'tabela': tabela}
            registro = {c: None for c in TABELAS[tabela][1]}
            for i, valor in enumerate(valores):
                campo = campos[i] if i < len(campos) else ''
                if not campo:
                    if valor is not None and str(valor).strip():
                        validacao.registrar('ERRO', 'SEM_CABECALHO', f'{tabela}, linha {linha}: valor sem cabeçalho.', origem)
                    continue
                if campo == 'IGNORAR' or campo not in registro:
                    continue
                try:
                    registro[campo] = converter(campo, valor, formatos[i], tabela)
                except (ValueError, OverflowError) as exc:
                    validacao.registrar('ERRO', 'VALOR_INVALIDO', f'{tabela}, linha {linha}, {campo}: {exc}', origem)
            for campo in TABELAS[tabela][0]:
                if registro[campo] is None:
                    validacao.registrar('ERRO', 'OBRIGATORIO', f'{tabela}, linha {linha}: {campo} é obrigatório.', origem)
            chave = tuple(registro.get(c) for c in CHAVES[tabela])
            if chave in vistos:
                validacao.registrar('ERRO', 'DUPLICIDADE', f'{tabela}, linha {linha}: chave repetida ({" + ".join(CHAVES[tabela])}).', origem)
            vistos.add(chave)
            registro['_origem'] = origem
            tabelas[tabela].append(registro)
            contagem += 1
            quantidade += 1
            if quantidade > limite:
                raise ErroImportacao('A prospecção excedeu o limite de linhas configurado.')
        if campos is None:
            validacao.registrar('ERRO', 'SEM_ABA', f'{tabela}: aba ou cabeçalho não encontrado.')
        depois = arquivo.stat()
        if (antes.st_mtime_ns, antes.st_size) != (depois.st_mtime_ns, depois.st_size):
            raise ErroImportacao(f'{arquivo.name} mudou durante a leitura. Salve e tente novamente.')
        arquivos_lidos.append({'tabela': tabela, 'arquivo': arquivo.name, 'linhas': contagem,
                              'sha256': hashlib.sha256(arquivo.read_bytes()).hexdigest()})
    validacao.exigir_valido()
    if not tabelas['credenciados'] or not tabelas['servicos']:
        raise ErroImportacao('Prospecção: cadastros de credenciados e serviços não podem estar vazios.')
    validar_relacoes(tabelas, op, validacao)
    validacao.exigir_valido()
    return tabelas, validacao, arquivos_lidos, mapeamentos


def validar_relacoes(t, op, v):
    ids = {tabela: {r[CHAVES[tabela][0]] for r in linhas} for tabela, linhas in t.items() if len(CHAVES[tabela]) == 1}
    for tabela, linhas in t.items():
        for r in linhas:
            for campo, destino in [('CHAVE_LOJA', 'credenciados'), ('ID_SERVICO', 'servicos'), ('ID_CONTRATO', 'contratos'), ('ID_RESPONSAVEL', 'responsaveis'), ('RESPONSAVEL_ORIGEM', 'responsaveis'), ('ID_EXECUTOR', 'responsaveis'), ('ID_ACAO', 'acompanhamentos'), ('ID_CONTRATO_ANTERIOR', 'contratos')]:
                if r.get(campo) and not (tabela == destino and campo == CHAVES[tabela][0]) and r[campo] not in ids[destino]:
                    v.registrar('ERRO', 'REFERENCIA', f'{tabela}: {campo} não existe no cadastro de {destino}.', r['_origem'])
            for inicio, fim in [('DATA_INAUGURACAO', 'DATA_ENCERRAMENTO'), ('DATA_INICIO', 'DATA_FIM'), ('INICIO_VIGENCIA', 'FIM_VIGENCIA'), ('VIGENCIA_INICIO', 'VIGENCIA_FIM')]:
                if r.get(inicio) and r.get(fim) and r[fim] < r[inicio]:
                    v.registrar('ERRO', 'VIGENCIA_INVALIDA', f'{tabela}: {fim} é anterior a {inicio}.', r['_origem'])
    v.exigir_valido()
    for tabela, campos, inicio, fim in [('vinculacoes', ['CHAVE_LOJA'], 'INICIO_VIGENCIA', 'FIM_VIGENCIA'),
                                        ('habilitacoes', ['CHAVE_LOJA', 'ID_SERVICO'], 'DATA_INICIO', 'DATA_FIM'),
                                        ('contrato_loja', ['ID_CONTRATO', 'CHAVE_LOJA'], 'DATA_INICIO', 'DATA_FIM')]:
        grupos = defaultdict(list)
        for r in t[tabela]:
            grupos[tuple(r[c] for c in campos)].append(r)
        for grupo in grupos.values():
            anterior = None
            for r in sorted(grupo, key=lambda a: a.get(inicio) or '0001-01-01'):
                if anterior and (r.get(inicio) or '0001-01-01') <= (anterior.get(fim) or '9999-12-31'):
                    v.registrar('ERRO', 'SOBREPOSICAO', f'{tabela}: vigências sobrepostas; a data final é inclusiva.', r['_origem'])
                anterior = r
    lojas = {r['CHAVE_LOJA']: r for r in t['credenciados']}
    contratos = {r['ID_CONTRATO']: r for r in t['contratos']}
    eventos = defaultdict(list)
    for r in t['status_contrato']:
        eventos[r['ID_CONTRATO']].append(r)
        if r['DATA_EVENTO'][:10] < contratos[r['ID_CONTRATO']]['DATA_EMISSAO']:
            v.registrar('ERRO', 'DECISAO_ANTERIOR_EMISSAO', 'Decisão anterior à emissão do contrato.', r['_origem'])
    for contrato, itens in eventos.items():
        datas = [r['DATA_EVENTO'] for r in itens]
        if len(datas) != len(set(datas)):
            v.registrar('ERRO', 'EVENTO_AMBIGUO', 'Eventos do mesmo contrato no mesmo instante. Informe horário para ordenar o histórico.', itens[0]['_origem'])
    origens_inauguracao = defaultdict(set)
    for r in t['contrato_loja']:
        aprovacoes = [e['DATA_EVENTO'][:10] for e in eventos[r['ID_CONTRATO']] if e['STATUS'] == 'APROVADO']
        if aprovacoes and lojas[r['CHAVE_LOJA']]['DATA_INAUGURACAO'] < min(aprovacoes):
            v.registrar('AVISO', 'INAUGURACAO_ANTERIOR_APROVACAO', 'Inauguração anterior à aprovação. Confira o vínculo ou as datas.', r['_origem'])
        if not aprovacoes:
            v.registrar('AVISO', 'INAUGURACAO_SEM_APROVACAO', 'Loja vinculada a contrato sem aprovação registrada. Confira o histórico.', r['_origem'])
        inauguracao = lojas[r['CHAVE_LOJA']]['DATA_INAUGURACAO']
        if nome_campo(r['TIPO_VINCULO'] or 'INAUGURACAO') == 'INAUGURACAO' and (not r['DATA_INICIO'] or r['DATA_INICIO'] <= inauguracao) and (not r['DATA_FIM'] or r['DATA_FIM'] >= inauguracao):
            origens_inauguracao[r['CHAVE_LOJA']].add(r['ID_CONTRATO'])
    for chave, origens in origens_inauguracao.items():
        if len(origens) > 1:
            v.registrar('ERRO', 'ORIGEM_INAUGURACAO_AMBIGUA', 'Uma loja tem mais de um contrato de origem na inauguração. Defina o tipo e a vigência dos vínculos.', lojas[chave]['_origem'])
    vinculadas = {r['CHAVE_LOJA'] for r in t['contrato_loja']}
    for r in t['credenciados']:
        if r['CHAVE_LOJA'] not in vinculadas:
            v.registrar('AVISO', 'LOJA_SEM_CONTRATO', 'Loja sem contrato vinculado: participa da carteira, mas não da conversão do funil.', r['_origem'])
    habilitacoes = defaultdict(list)
    servicos = {r['ID_SERVICO']: r for r in t['servicos']}
    for r in t['habilitacoes']:
        habilitacoes[r['CHAVE_LOJA'], r['ID_SERVICO']].append(r)
    for r in t['producao']:
        if op['quantidade_producao'] == 'liquida':
            if r['QTD_VALIDA'] is None:
                v.registrar('ERRO', 'QUANTIDADE', 'Modo líquido exige QTD_VALIDA; estornos não são subtraídos novamente.', r['_origem'])
        else:
            if r['QTD_VALIDA'] is not None or r['QTD_CONFIRMADA'] is None or r['QTD_ESTORNADA'] is None:
                v.registrar('ERRO', 'QUANTIDADE', 'Modo bruto exige confirmada e estornada, com QTD_VALIDA vazia.', r['_origem'])
            else:
                r['QTD_VALIDA'] = r['QTD_CONFIRMADA'] - r['QTD_ESTORNADA']
                if r['QTD_VALIDA'] < 0:
                    v.registrar('ERRO', 'ESTORNOS', 'Estornos excedem a quantidade confirmada.', r['_origem'])
        loja = lojas[r['CHAVE_LOJA']]
        if r['COMPETENCIA'] < mes(loja['DATA_INAUGURACAO']):
            v.registrar('ERRO', 'PRODUCAO_ANTERIOR_INAUGURACAO', 'Produção anterior ao mês de inauguração.', r['_origem'])
        if loja['DATA_ENCERRAMENTO'] and r['COMPETENCIA'] > mes(loja['DATA_ENCERRAMENTO']):
            v.registrar('AVISO', 'PRODUCAO_APOS_ENCERRAMENTO', 'Produção após o encerramento cadastrado.', r['_origem'])
        servico = servicos[r['ID_SERVICO']]
        habilitado = any(h['SITUACAO'] == 'HABILITADO' and h['DATA_INICIO'] <= fim_mes(r['COMPETENCIA']) and (not h['DATA_FIM'] or h['DATA_FIM'] >= r['COMPETENCIA'] + '-01') for h in habilitacoes[r['CHAVE_LOJA'], r['ID_SERVICO']])
        if r.get('QTD_VALIDA', 0) and not habilitado:
            v.registrar('AVISO', 'SEM_HABILITACAO', 'Serviço produzido sem habilitação registrada na competência.', r['_origem'])
        if (servico['VIGENCIA_INICIO'] and servico['VIGENCIA_INICIO'] > fim_mes(r['COMPETENCIA'])) or (servico['VIGENCIA_FIM'] and servico['VIGENCIA_FIM'] < r['COMPETENCIA'] + '-01'):
            v.registrar('AVISO', 'SERVICO_FORA_VIGENCIA', 'Produção fora da vigência do serviço.', r['_origem'])
    for r in t['cobertura']:
        if r['STATUS_COMPLETUDE'] == 'COMPLETO' and not r['DATA_VALIDACAO']:
            v.registrar('ERRO', 'COBERTURA_SEM_VALIDACAO', 'Cobertura completa exige DATA_VALIDACAO.', r['_origem'])
    for r in t['acompanhamentos']:
        if (r['STATUS'] == 'CONCLUIDO') != bool(r['DATA_REALIZADA']):
            v.registrar('ERRO', 'ACAO_INCONSISTENTE', 'Ação concluída exige data realizada; demais estados devem deixá-la vazia.', r['_origem'])
        if r['TIPO_ACAO'] == 'SUPORTE':
            if r['MARCO_OPERACIONAL'] not in {2, 4}:
                v.registrar('ERRO', 'MARCO_SUPORTE', 'Suporte deve informar marco operacional 2 ou 4.', r['_origem'])
            elif not r['DATA_PREVISTA']:
                r['DATA_PREVISTA'] = fim_mes(deslocar_mes(lojas[r['CHAVE_LOJA']]['DATA_INAUGURACAO'], r['MARCO_OPERACIONAL']))
        if r['DATA_REALIZADA'] and r['DATA_REALIZADA'] < lojas[r['CHAVE_LOJA']]['DATA_INAUGURACAO'] and r['TIPO_ACAO'] != 'TREINAMENTO':
            v.registrar('AVISO', 'SUPORTE_ANTES_INAUGURACAO', 'Suporte registrado antes da inauguração.', r['_origem'])
    suportes = set()
    for r in t['acompanhamentos']:
        if r['TIPO_ACAO'] == 'SUPORTE':
            chave = (r['CHAVE_LOJA'], r['MARCO_OPERACIONAL'])
            if chave in suportes:
                v.registrar('ERRO', 'SUPORTE_REPETIDO', 'Cadastre uma ação prevista por loja e marco M2/M4; consolide seus registros de execução.', r['_origem'])
            suportes.add(chave)
