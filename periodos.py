"""Intervalos mensais inclusivos e comparações de mesma duração."""
from prospeccao_dados import deslocar_mes, idade, mes


def intervalo(base, params):
    inicio, fim = params.get('inicio'), params.get('fim')
    if bool(inicio) != bool(fim):
        raise ValueError('Informe os dois limites do período: de e até.')
    if inicio and params.get('competencia'):
        raise ValueError('Use um intervalo ou uma competência, sem combinar os dois.')
    fim = fim or params.get('competencia') or base['opcoes']['ultimo_mes_fechado']
    inicio = inicio or fim
    for valor in [inicio, fim]:
        if mes(valor) != valor:
            raise ValueError('Use os limites do período no formato AAAA-MM.')
    if inicio > fim:
        raise ValueError('O início do período deve ser anterior ou igual ao fim.')
    if fim > mes(base['opcoes']['data_corte']):
        raise ValueError('O período não pode ultrapassar o mês da data de corte.')
    tamanho = idade(inicio, fim) + 1
    if tamanho > 120:
        raise ValueError('Selecione no máximo 120 meses por consulta.')
    return inicio, fim, tamanho


def meses(inicio, fim):
    return [deslocar_mes(inicio, i) for i in range(idade(inicio, fim) + 1)]
