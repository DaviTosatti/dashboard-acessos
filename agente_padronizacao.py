"""Analisa a carga e gera um relatório, sem alterar a base publicada."""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from integracao import PADRAO_CONFIG, atualizar_dashboard


def salvar_relatorio(relatorio, pasta):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / 'analise_colunas.json').write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
    esc = lambda v: html.escape(str(v))
    erros = ''.join(f'<li>{esc(e["mensagem"])}</li>' for e in relatorio['erros']) or '<li>Nenhum erro de validação.</li>'
    avisos = ''.join(f'<li>{esc(e["mensagem"])}</li>' for e in relatorio['avisos'])
    linhas = ''.join('<tr>' + ''.join(f'<td>{esc(c.get(k, ""))}</td>' for k in ['fonte', 'original', 'padrao', 'regra', 'preenchidos', 'vazios']) + '</tr>' for c in relatorio['mapeamentos'])
    tabelas = ''.join('<tr>' + ''.join(f'<td>{esc(t.get(k, ""))}</td>' for k in ['tabela', 'linhas', 'chave_presente', 'chaves_distintas', 'chaves_vazias', 'chaves_repetidas', 'unicidade_exigida']) + '</tr>' for t in relatorio['tabelas'])
    sugestoes = ''.join(f'<li><strong>{esc(" / ".join(s["campos"]))}</strong>: candidato {esc(s["destino_sugerido"])}. {esc(s["motivo"])}</li>' for s in relatorio['sugestoes']) or '<li>Nenhuma equivalência candidata pendente.</li>'
    documento = f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Análise de padronização</title><style>body{{font:14px system-ui,sans-serif;color:#233b31;background:#f4f7f5;margin:0;padding:30px}}main{{max-width:1300px;margin:auto}}h1{{font-size:29px}}h2{{font-size:18px;margin-top:30px}}.panel{{background:white;border:1px solid #dce7df;padding:22px;border-radius:12px;margin-bottom:16px;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #e6eee8}}th{{background:#eff5ef}}p,li{{line-height:1.6}}code{{background:#edf2ec;padding:3px 6px;border-radius:4px}}.state{{color:#087c6a;font-weight:700}}@media(max-width:700px){{body{{padding:16px}}}}</style><main><h1>Análise de padronização</h1><p>Estado: <span class="state">{esc(relatorio['estado'])}</span> · Gerado em {esc(relatorio['gerado_em'])}</p><p>Esta análise não altera a base publicada. Sugestões precisam ser registradas no catálogo antes de virar equivalências.</p><section class="panel"><h2>Validações</h2><ul>{erros}</ul><ul>{avisos}</ul></section><section class="panel"><h2>Chaves por tabela</h2><table><tr><th>Tabela</th><th>Linhas</th><th>Tem chave</th><th>Distintas</th><th>Vazias</th><th>Repetidas</th><th>Exige unicidade</th></tr>{tabelas}</table></section><section class="panel"><h2>Equivalências para revisar</h2><ul>{sugestoes}</ul><p>Registre nomes equivalentes em <code>aliases</code>. Para campos de significados diferentes, use <code>fontes → colunas</code> e nomes padrão distintos.</p></section><section class="panel"><h2>Origem e nome padronizado</h2><table><tr><th>Fonte</th><th>Coluna original</th><th>Coluna padrão</th><th>Regra</th><th>Preenchidos</th><th>Vazios</th></tr>{linhas}</table></section></main></html>'''
    (pasta / 'analise_colunas.html').write_text(documento, encoding='utf-8')


def analisar_planilhas(config_path=PADRAO_CONFIG, saida=None):
    try:
        resumo = atualizar_dashboard(config_path, somente_analisar=True)
        relatorio = resumo['analise_padronizacao']
    except Exception as exc:
        relatorio = {'estado': 'BLOQUEADO', 'gerado_em': datetime.now(timezone.utc).isoformat(),
                     'tabelas': [], 'mapeamentos': [], 'sugestoes': [], 'avisos': [],
                     'erros': [{'codigo': 'LEITURA_INVALIDA', 'mensagem': str(exc)}], 'total_erros': 1}
    if saida is not None:
        salvar_relatorio(relatorio, saida)
    return relatorio


def main():
    parser = argparse.ArgumentParser(description='Analisa e padroniza as colunas, sem publicar os dados.')
    parser.add_argument('--config', default=str(PADRAO_CONFIG))
    parser.add_argument('--saida', help='Pasta dos relatórios HTML e JSON.')
    args = parser.parse_args()
    saida = Path(args.saida) if args.saida else Path(args.config).resolve().parent / 'relatorios'
    relatorio = analisar_planilhas(args.config, saida)
    print(f"Análise {relatorio['estado']}: {len(relatorio['mapeamentos'])} mapeamentos, {len(relatorio['sugestoes'])} sugestões, {relatorio.get('total_erros', len(relatorio['erros']))} erros.")
    print(f'Relatório: {(saida / "analise_colunas.html").resolve()}')
    if relatorio['estado'] == 'BLOQUEADO':
        parser.exit(2)


if __name__ == '__main__':
    main()
