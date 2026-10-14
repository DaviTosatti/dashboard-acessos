"""Agente local de análise de esquema, catálogo e validação de relacionamentos.

Aplica equivalências declaradas; descobre candidatos por cabeçalho e perfil de
valores. Sugestões sem confirmação nunca viram equivalências automaticamente.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


class ErroPadronizacao(ValueError):
    pass


def nome_padrao(nome):
    texto = unicodedata.normalize('NFKD', str(nome).strip())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', '_', texto.upper()).strip('_')


def texto_identificador(valor, formato='General'):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, (bool, date, datetime)):
        raise ErroPadronizacao('Identificador deve ser texto ou número inteiro, não data ou booleano.')
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and (not math.isfinite(valor) or not valor.is_integer()):
            raise ErroPadronizacao('Identificador numérico deve ser inteiro e finito.')
        texto = str(int(valor))
        if re.fullmatch(r'0{2,}', formato):
            texto = texto.zfill(len(formato))
        return texto
    return str(valor).strip()


def texto_cnpj(valor, formato='General'):
    texto = texto_identificador(valor, formato)
    if texto is None:
        return None
    if isinstance(valor, (int, float)):
        texto = texto.zfill(14)
    texto = re.sub(r'[.\s/\-]', '', texto).upper()
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', texto):
        raise ErroPadronizacao('CNPJ deve ter 14 posições: 12 alfanuméricas e 2 dígitos finais.')
    return texto


def assinatura_nome(nome):
    tokens = nome_padrao(nome).split('_')
    prefixos = {'NO', 'NR', 'NU', 'NUM', 'NUMERO', 'NM', 'NOME', 'CD', 'COD', 'CODIGO', 'ID', 'DS', 'DESC', 'DESCRICAO'}
    while len(tokens) > 1 and tokens[0] in prefixos:
        tokens.pop(0)
    tokens = [t for t in tokens if t not in {'DO', 'DA', 'DE', 'DOS', 'DAS'}]
    return '_'.join(tokens)


def hash_texto(texto):
    return hashlib.sha256(str(texto).encode('utf-8')).hexdigest()


class AgentePadronizador:
    def __init__(self, config):
        self.config = config
        caminho = config.valores.get('catalogo_colunas')
        self.ativo = bool(caminho)
        self.catalogo = {'aliases': {}, 'tipos': {}, 'fontes': {}, 'chave_loja': 'CHAVE_LOJA',
                         'chave_unica_por_tabela': True, 'exigir_chave_loja': False,
                         'consistencia_por_chave': [], 'bloquear_sugestoes_pendentes': True,
                         'enriquecimento': None}
        if self.ativo:
            arquivo = Path(caminho)
            if not arquivo.is_absolute():
                arquivo = config.arquivo.parent / arquivo
            with arquivo.open(encoding='utf-8') as entrada:
                conteudo = json.load(entrada)
            if not isinstance(conteudo, dict):
                raise ErroPadronizacao('catalogo_colunas deve conter um objeto JSON.')
            self.catalogo.update(conteudo)
        self.aliases = {}
        self._validar_catalogo()
        self.tipos = {nome_padrao(k): v for k, v in self.catalogo['tipos'].items()}
        self.legado = {nome_padrao(k): v for k, v in config.valores['renomear_colunas'].items()}
        self.chave = self.canonico(self.catalogo['chave_loja'])
        self.consistentes = {self.canonico(c) for c in self.catalogo['consistencia_por_chave']}
        self.mapeamentos = {}
        self.regras_fontes = {}
        self.tabelas = {}
        self.valores_consistentes = {}
        self.erros = []
        self.total_erros = 0
        self.avisos = []
        self.relacionamentos = []
        self.relatorio = None

    def _validar_catalogo(self):
        for flag in ['chave_unica_por_tabela', 'exigir_chave_loja', 'bloquear_sugestoes_pendentes']:
            if type(self.catalogo[flag]) is not bool:
                raise ErroPadronizacao(f'{flag} deve ser true ou false.')
        if not isinstance(self.catalogo['chave_loja'], str) or not nome_padrao(self.catalogo['chave_loja']):
            raise ErroPadronizacao('chave_loja deve ser um nome de coluna.')
        for key in ['aliases', 'tipos', 'fontes']:
            if not isinstance(self.catalogo[key], dict):
                raise ErroPadronizacao(f'{key} deve ser um objeto JSON.')
        for destino, origens in self.catalogo['aliases'].items():
            if not isinstance(destino, str) or not nome_padrao(destino) or not isinstance(origens, list) or not all(isinstance(n, str) and nome_padrao(n) for n in origens):
                raise ErroPadronizacao('aliases deve ligar um nome padrão a uma lista de nomes de origem.')
            padrao = nome_padrao(destino)
            for origem in [destino] + origens:
                chave = nome_padrao(origem)
                if chave in self.aliases and self.aliases[chave] != padrao:
                    raise ErroPadronizacao(f'Alias ambíguo: {origem!r} aponta para mais de um campo.')
                self.aliases[chave] = padrao
        if not all(isinstance(k, str) and v in {'identificador', 'cnpj', 'texto', 'numero', 'data'} for k, v in self.catalogo['tipos'].items()):
            raise ErroPadronizacao('tipos aceita identificador, cnpj, texto, numero ou data.')
        lista = self.catalogo['consistencia_por_chave']
        if not isinstance(lista, list) or not all(isinstance(c, str) for c in lista):
            raise ErroPadronizacao('consistencia_por_chave deve ser uma lista de nomes.')
        for padrao, regra in self.catalogo['fontes'].items():
            if not isinstance(padrao, str) or not isinstance(regra, dict):
                raise ErroPadronizacao('fontes deve mapear padrões arquivo::aba para regras.')
            if 'tabela' in regra and (not isinstance(regra['tabela'], str) or not regra['tabela'].strip()):
                raise ErroPadronizacao('tabela deve ser um nome não vazio.')
            cols = regra.get('colunas', {})
            if not isinstance(cols, dict) or not all(isinstance(k, str) and isinstance(v, str) and nome_padrao(v) for k, v in cols.items()):
                raise ErroPadronizacao('colunas da fonte deve conter nomes de origem e destino.')
            for flag in ['chave_unica', 'exigir_chave']:
                if flag in regra and type(regra[flag]) is not bool:
                    raise ErroPadronizacao(f'{flag} da fonte deve ser true ou false.')
            required = regra.get('colunas_obrigatorias', [])
            if not isinstance(required, list) or not all(isinstance(c, str) for c in required):
                raise ErroPadronizacao('colunas_obrigatorias deve ser uma lista de nomes.')
        enriquecimento = self.catalogo['enriquecimento']
        if enriquecimento is not None:
            if not isinstance(enriquecimento, dict) or not isinstance(enriquecimento.get('tabela_principal'), str):
                raise ErroPadronizacao('enriquecimento exige tabela_principal.')
            dimensoes = enriquecimento.get('dimensoes')
            if not isinstance(dimensoes, list) or not dimensoes:
                raise ErroPadronizacao('enriquecimento exige uma lista não vazia de dimensoes.')
            nomes = [enriquecimento['tabela_principal']]
            for dimensao in dimensoes:
                if not isinstance(dimensao, dict) or not isinstance(dimensao.get('tabela'), str) or not dimensao['tabela']:
                    raise ErroPadronizacao('Cada dimensão exige tabela.')
                cols = dimensao.get('colunas')
                if not isinstance(cols, list) or not cols or not all(isinstance(c, str) for c in cols):
                    raise ErroPadronizacao('Cada dimensão exige uma lista de colunas a trazer.')
                if type(dimensao.get('obrigatoria', True)) is not bool:
                    raise ErroPadronizacao('obrigatoria da dimensão deve ser true ou false.')
                nomes.append(dimensao['tabela'])
            if len(nomes) != len(set(nomes)):
                raise ErroPadronizacao('As tabelas do enriquecimento devem ser distintas.')

    def canonico(self, nome):
        if not self.ativo:
            return str(nome).strip()
        codigo = nome_padrao(nome)
        return self.aliases.get(codigo, codigo)

    def regra_fonte(self, fonte):
        if fonte not in self.regras_fontes:
            matches = [regra for padrao, regra in self.catalogo['fontes'].items()
                       if fnmatch.fnmatch(fonte.casefold(), padrao.casefold())]
            if len(matches) > 1:
                raise ErroPadronizacao(f'{fonte}: mais de uma regra de fonte corresponde ao arquivo e à aba.')
            regra = dict(matches[0]) if matches else {}
            regra.setdefault('tabela', fonte)
            regra.setdefault('chave_unica', self.catalogo['chave_unica_por_tabela'])
            regra.setdefault('exigir_chave', self.catalogo['exigir_chave_loja'])
            self.regras_fontes[fonte] = regra
        return self.regras_fontes[fonte]

    def resolver(self, nome, fonte):
        if not self.ativo:
            return self.legado.get(nome_padrao(nome), str(nome).strip()), 'legado'
        regra = self.regra_fonte(fonte)
        locais = {nome_padrao(k): v for k, v in regra.get('colunas', {}).items()}
        codigo = nome_padrao(nome)
        if codigo in locais:
            # Um mapeamento específico pode separar CNPJ_MATRIZ de CNPJ_LOJA.
            return nome_padrao(locais[codigo]), 'fonte'
        if codigo in self.legado:
            return self.canonico(self.legado[codigo]), 'renomear_colunas'
        return self.canonico(nome), 'alias' if codigo in self.aliases else 'nome'

    def registrar_cabecalho(self, fonte, nomes):
        regra = self.regra_fonte(fonte)
        tabela = regra['tabela']
        registro = self.tabelas.setdefault(tabela, {'fontes': set(), 'colunas': set(), 'linhas': 0,
                                                 'chaves': {}, 'nulas': 0, 'repeticoes': 0,
                                                 'unica': regra['chave_unica'], 'exigir': regra['exigir_chave']})
        if registro['unica'] != regra['chave_unica'] or registro['exigir'] != regra['exigir_chave']:
            raise ErroPadronizacao(f'{tabela}: regras de chave conflitantes entre arquivos da mesma tabela.')
        registro['fontes'].add(fonte)
        raw = set()
        colunas_fonte = set()
        for original in nomes:
            if not original:
                continue
            assinatura = nome_padrao(original)
            if assinatura in raw:
                raise ErroPadronizacao(f'{fonte}: cabeçalho duplicado: {original!r}.')
            raw.add(assinatura)
            padrao, metodo = self.resolver(original, fonte)
            registro['colunas'].add(padrao)
            colunas_fonte.add(padrao)
            self.mapeamentos[(fonte, original)] = {'fonte': fonte, 'tabela': tabela, 'original': original,
                  'padrao': padrao, 'regra': metodo, 'tipo_configurado': self.tipos.get(padrao),
                  'preenchidos': 0, 'vazios': 0, 'tipos': Counter(), 'formatos': Counter(), 'amostra': set()}
        required = {self.canonico(c) for c in regra.get('colunas_obrigatorias', [])}
        if regra['exigir_chave']:
            required.add(self.chave)
        for campo in sorted(required - colunas_fonte):
            self.erro('COLUNA_AUSENTE', f'{fonte}: coluna obrigatória {campo} não encontrada.', fonte=fonte, coluna=campo)
        if self.chave not in colunas_fonte:
            self.avisos.append({'codigo': 'FONTE_SEM_CHAVE', 'fonte': fonte,
                                'mensagem': f'{fonte}: não contém {self.chave}; relacionamento por loja indisponível.'})

    def observar_campo(self, fonte, original, valor, tipo):
        campo = self.mapeamentos.get((fonte, original))
        if campo is None:
            return
        if valor is None:
            campo['vazios'] += 1
            return
        campo['preenchidos'] += 1
        campo['tipos'][tipo or 'texto'] += 1
        texto = str(valor)
        sem_mascara = re.sub(r'[.\s/\-]', '', texto).upper()
        formato = 'cnpj' if re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', sem_mascara) else 'digitos' if texto.isdigit() else 'data' if re.match(r'^\d{4}-\d{2}-\d{2}', texto) else 'outro'
        campo['formatos'][formato] += 1
        if len(campo['amostra']) < 256:
            campo['amostra'].add(hash_texto(texto.casefold()))

    def observar_linha(self, fonte, linha, valores):
        tabela = self.regra_fonte(fonte)['tabela']
        info = self.tabelas[tabela]
        info['linhas'] += 1
        if not self.ativo:
            return
        chave = valores.get(self.chave)
        if self.chave not in info['colunas']:
            return
        if chave is None:
            info['nulas'] += 1
            if info['unica'] or info['exigir']:
                self.erro('CHAVE_VAZIA', f'{fonte}, linha {linha}: {self.chave} está vazia.', fonte=fonte, linha=linha, coluna=self.chave)
            return
        resumo = hash_texto(chave)
        local = {'fonte': fonte, 'linha': linha}
        if resumo in info['chaves']:
            info['repeticoes'] += 1
            if info['unica']:
                self.erro('CHAVE_DUPLICADA', f'{fonte}, linha {linha}: {self.chave} repetida dentro da tabela {tabela}.',
                          fonte=fonte, linha=linha, primeira_ocorrencia=info['chaves'][resumo], tabela=tabela)
        else:
            info['chaves'][resumo] = local
        for coluna in self.consistentes:
            valor = valores.get(coluna)
            if valor is None:
                continue
            index = (resumo, coluna)
            valor_hash = hash_texto(valor)
            antigo = self.valores_consistentes.get(index)
            if antigo and antigo[0] != valor_hash:
                self.erro('VALOR_DIVERGENTE', f'{fonte}, linha {linha}: {coluna} diverge para a mesma {self.chave}.',
                          fonte=fonte, linha=linha, coluna=coluna, primeira_ocorrencia=antigo[1])
            else:
                self.valores_consistentes[index] = (valor_hash, local)

    def erro(self, codigo, mensagem, **contexto):
        self.total_erros += 1
        if len(self.erros) < 1000:
            self.erros.append({'codigo': codigo, 'mensagem': mensagem, **contexto})

    def sugestoes(self):
        grupos = defaultdict(list)
        for campo in self.mapeamentos.values():
            grupos[assinatura_nome(campo['padrao'])].append(campo)
        sugestoes = []
        for assinatura, campos in grupos.items():
            destinos = sorted({c['padrao'] for c in campos})
            if len(destinos) < 2:
                continue
            perfis = {c['padrao']: c for c in campos}
            formatos = {p: max(c['formatos'], key=c['formatos'].get, default=None) for p, c in perfis.items()}
            relevantes = [p for p in destinos if formatos[p] is not None]
            # Valores textuais livres e códigos numéricos têm significados diferentes.
            if len(relevantes) > 1 and 'outro' in {formatos[p] for p in relevantes} and 'digitos' in {formatos[p] for p in relevantes}:
                continue
            comuns = set.intersection(*(perfis[p]['amostra'] for p in relevantes)) if relevantes else set()
            destino = assinatura if assinatura in destinos else min(destinos, key=lambda p: (len(p), p))
            sugestoes.append({'campos': destinos, 'destino_sugerido': destino,
                              'motivo': 'Cabeçalhos diferem por prefixos; confirme que descrevem a mesma informação.',
                              'fontes': sorted({c['fonte'] for c in campos}),
                              'formatos_observados': formatos, 'valores_comuns_na_amostra': len(comuns)})
        # Um cabeçalho desconhecido com formato de CNPJ é apenas um candidato.
        # IDs e campos explicitamente qualificados continuam com seu significado.
        candidatos = set()
        for campo in self.mapeamentos.values():
            nome = campo['padrao']
            tokens = set(nome.split('_'))
            if campo['regra'] != 'nome' or 'CNPJ' in tokens or tokens & {'ID', 'CHAVE', 'COD', 'CODIGO', 'CPF', 'TELEFONE'}:
                continue
            if campo['preenchidos'] and campo['formatos'].get('cnpj') == campo['preenchidos'] and self.tipos.get('CNPJ') == 'cnpj':
                candidatos.add(nome)
        for nome in sorted(candidatos):
            if any(nome in s['campos'] for s in sugestoes):
                continue
            campos = [c for c in self.mapeamentos.values() if c['padrao'] == nome]
            sugestoes.append({'campos': [nome, 'CNPJ'], 'destino_sugerido': 'CNPJ',
                              'motivo': 'Valores com formato de CNPJ em campo desconhecido; confirme o significado e o escopo.',
                              'fontes': sorted({c['fonte'] for c in campos}),
                              'formatos_observados': {nome: 'cnpj'}, 'valores_comuns_na_amostra': None})
        return sugestoes

    def finalizar(self):
        if self.relatorio is not None:
            return self.relatorio
        sugestoes = self.sugestoes() if self.ativo else []
        if sugestoes and self.catalogo['bloquear_sugestoes_pendentes']:
            self.erro('MAPEAMENTO_PENDENTE', 'Há equivalências candidatas sem confirmação no catálogo. Analise o relatório e registre o significado correto.')
        tabelas = [{'tabela': nome, 'fontes': sorted(t['fontes']), 'linhas': t['linhas'],
                    'chave_presente': self.chave in t['colunas'], 'chave': self.chave,
                    'chaves_distintas': len(t['chaves']), 'chaves_vazias': t['nulas'],
                    'chaves_repetidas': t['repeticoes'], 'unicidade_exigida': t['unica'],
                    'colunas': sorted(t['colunas'])} for nome, t in self.tabelas.items()]
        mapas = [{k: (dict(v) if isinstance(v, Counter) else v) for k, v in c.items() if k != 'amostra'} for c in self.mapeamentos.values()]
        self.relatorio = {'ativo': self.ativo, 'gerado_em': datetime.now(timezone.utc).isoformat(),
                         'estado': 'BLOQUEADO' if self.erros else 'REVISAR' if sugestoes else 'APTO',
                         'chave_loja': self.chave, 'tabelas': tabelas, 'mapeamentos': mapas,
                         'sugestoes': sugestoes, 'erros': self.erros, 'total_erros': self.total_erros,
                         'avisos': self.avisos, 'relacionamentos': self.relacionamentos,
                         'catalogo_hash': hash_texto(json.dumps(self.catalogo, sort_keys=True, ensure_ascii=False))}
        return self.relatorio

    def exigir_valido(self):
        report = self.finalizar()
        if report['erros']:
            raise ErroPadronizacao(report['erros'][0]['mensagem'] + ' Execute agente_padronizacao.py para gerar o relatório.')
