# Expresso — Gestão, prospecção e consultas

Projeto em Python com uma interface HTML, CSS e JavaScript para consultar as planilhas que sua rotina publica. Funciona em um servidor Windows ou Linux; os colegas acessam pelo navegador, sem instalar Python em cada computador.

A busca funciona em qualquer coluna, ignora acentos e maiúsculas e aceita filtros combinados. O painel oferece atalhos para cliente, sistema, status e arquivo, condições por coluna, ordenação, paginação, seleção de colunas, detalhes da origem e exportação CSV de **todos os resultados filtrados**, não apenas da página atual.

## Novidades de períodos e consultores

O painel agora oferece intervalos de/até, atalhos de 3/6/12 meses, uma aba de produção e atividades dos consultores e pesquisa dentro dos menus de filtros. Também lembra os filtros durante a sessão, mostra recortes aplicados e avisa sobre alterações pendentes. Leia [ATUALIZACOES.md](ATUALIZACOES.md) para conferir como cada indicador usa o intervalo ou o último fechamento.

## Prospecção integrada

A nova tela **Prospecção** acompanha contratos, safras, continuidade, risco, serviços, treinamento, suportes e qualidade dos dados, com filtros por gerência e consultor. O layout foi mantido e recebeu uma paleta de vermelho e vinho. As consultas de acessos e o agente original continuam disponíveis na lateral.

Leia [GUIA_PROSPECCAO.md](GUIA_PROSPECCAO.md) para configurar suas bases e [DICIONARIO_INDICADORES.md](DICIONARIO_INDICADORES.md) para conferir fórmulas, denominadores e regras. Há modelos vazios em `modelos_prospeccao` e dados fictícios em `planilhas_prospeccao`. Nunca misture os arquivos de fatos da prospecção com o cadastro de consultas que exige CHAVE_LOJA única por tabela.

No Windows, após extrair o ZIP inteiro, execute `INSTALAR_DEPENDENCIAS.bat` uma vez e `INICIAR_DASHBOARD.bat` para importar e iniciar o painel. O inicializador usa `configuracao.local.json` quando esse arquivo existe.

## Testar com os exemplos

Requer Python 3.10 ou superior. Extraia o ZIP inteiro e abra o terminal na pasta `dashboard_acessos`. Se recebeu o projeto pelo GitHub, abra a pasta clonada do repositório.

A pasta das planilhas agora se chama **`planilhas_aprovadas`**. Ela é uma única pasta, já incluída no ZIP, e fica ao lado de `integracao.py` e `configuracao.json`. Coloque os arquivos Excel, CSV ou TSV diretamente nela.

```bash
python -m pip install -r requirements.txt
python integracao.py
python servidor.py
```

Abra **http://127.0.0.1:8000**. As duas planilhas de acessos incluídas contêm 84 registros fictícios. A prospecção inclui 48 lojas, 168 contratos e históricos fictícios, com fechamento de setembro de 2026. O painel identifica esses dados como exemplos. Não precisa de conexão com a internet para carregar a interface; seus recursos são locais.

Para isolar as dependências, crie um ambiente com `python -m venv .venv`. No Windows, substitua `python` nos comandos acima por `.\.venv\Scripts\python.exe`. No Linux, substitua por `./.venv/bin/python`.

Se estiver apenas testando e ainda não tiver o Waitress, `python servidor.py --teste` usa o servidor local simples do Python. Para servir a rede, use o comando normal com as dependências instaladas.

## Usar as suas planilhas

1. Retire `exemplo_matriz.xlsx` e `exemplo_filiais.xlsx` da pasta `planilhas_aprovadas`.
2. Coloque nessa pasta o conjunto completo de planilhas que deve ficar disponível para consulta. Subpastas também são lidas.
3. Ajuste `configuracao.json` e defina `modo_exemplo` como `false`.
4. Configure também as fontes reais de prospecção, conforme o guia, ou defina `prospeccao.ativo` como `false` para importar somente acessos.
5. Depois da sua etapa de aprovação, execute `python integracao.py`. Com o servidor aberto, os dados novos ficam disponíveis sem reiniciá-lo.

O painel verifica novas publicações a cada minuto. O botão **Atualizar consulta** recarrega imediatamente a base publicada.

As fontes aceitas são `.xlsx`, `.xlsm`, `.csv` e `.tsv`. Converta arquivos antigos `.xls` para `.xlsx`. As planilhas de origem são lidas, sem alteração ou execução de macros.

O `.gitignore` inclui apenas as duas planilhas fictícias no controle de versão e exclui novas entradas em `planilhas_aprovadas`, bancos gerados, relatórios, ambientes Python e arquivos `.env`. Para usar caminhos da empresa, faça uma cópia de `configuracao.json` chamada `configuracao.local.json` e informe `--config configuracao.local.json` nos comandos. Se o catálogo contiver nomes internos, use `catalogo_colunas.local.json` e indique esse caminho na configuração local. Esses dois arquivos locais também ficam fora do Git.

Se você mantiver um arquivo de configuração de uma versão anterior, ajuste também nele a pasta de entrada:

```json
"pasta_planilhas": "planilhas_aprovadas"
```

## Agente de padronização das colunas

O projeto inclui um agente **local, baseado em regras e perfil de dados**. Ele lê as fontes, aplica o catálogo de equivalências e sugere correspondências novas. Os nomes finais usam maiúsculas e separador `_`, por exemplo `NO_CNPJ` vira `CNPJ` e `Nome do cliente` vira `NOME_DO_CLIENTE` até receber um mapeamento de significado no catálogo.

O agente já conhece a equivalência que você informou:

| Coluna de origem | Coluna usada na consulta | Tipo |
| --- | --- | --- |
| `CNPJ` | `CNPJ` | Texto identificador |
| `NO_CNPJ` | `CNPJ` | Texto identificador |
| `CHAVE_LOJA` | `CHAVE_LOJA` | Texto identificador |

Ele valida **uma ocorrência de cada valor de CHAVE_LOJA por tabela**. A mesma chave em tabelas diferentes é esperada. Tabelas sem esse campo recebem um aviso; use `exigir_chave` para torná-lo obrigatório nas fontes necessárias.

Primeiro execute a análise, na pasta do projeto:

```bash
python agente_padronizacao.py
```

Abra `relatorios/analise_colunas.html` no navegador. A análise não altera a base publicada. O JSON correspondente está em `relatorios/analise_colunas.json`. O comando retorna código 2 quando detecta impedimentos para publicar.

Depois de revisar o catálogo, publique normalmente:

```bash
python integracao.py
```

Essa importação sempre executa a validação. A sua rotina existente pode continuar chamando `atualizar_dashboard(config)`; o agente já está integrado. No painel, **Fontes de dados** mostra os nomes de origem, os nomes finais e a validação das chaves da publicação bem-sucedida. O relatório gerado pelo comando mostra também as cargas recusadas.

### Registrar equivalências novas

Edite `catalogo_colunas.json`. Por exemplo, depois de confirmar o significado:

```json
"aliases": {
  "CHAVE_LOJA": ["CHAVE_LOJA"],
  "CNPJ": ["CNPJ", "NO_CNPJ"],
  "CLIENTE": ["CLIENTE", "NM_CLIENTE", "NOME_CLIENTE"],
  "NOME_FANTASIA": ["NOME_FANTASIA", "NM_FANTASIA"]
}
```

Esse trecho é a propriedade `aliases` dentro do catálogo. Os nomes de origem são comparados ignorando acentos, maiúsculas, espaços e pontuação. O mesmo alias não pode apontar para dois significados.

O agente procura candidatos por diferenças de prefixos e pelo formato dos valores. As sugestões continuam como campos separados até você registrar sua equivalência. Com `bloquear_sugestoes_pendentes: true`, uma sugestão pendente impede a publicação da nova carga. Identificar todos os significados exige os cabeçalhos e as regras reais das suas tabelas; o perfil de valores oferece evidências para a revisão.

Para campos que variam de significado conforme a tabela, declare uma regra por fonte:

```json
"fontes": {
  "tabela_y.csv::CSV": {
    "tabela": "TABELA_Y",
    "colunas": {"NO_CNPJ": "CNPJ_MATRIZ"},
    "exigir_chave": true,
    "chave_unica": true
  }
}
```

O padrão usa `arquivo::aba`, com o caminho relativo à pasta de entrada. Excel usa o nome da aba; CSV usa `CSV`; TSV usa `TSV`. Padrões como `tabela_y.*::*` são aceitos. Cada fonte deve corresponder a uma única regra.

Regras específicas de fonte têm prioridade. Depois vêm `renomear_colunas`, as equivalências do catálogo e a formatação do cabeçalho. Declare `CNPJ_MATRIZ` em `tipos` como `cnpj` se quiser a mesma normalização de valores. `CNPJ_MATRIZ` e `CNPJ_FILIAL` permanecem campos separados.

Por padrão, cada arquivo/aba é uma tabela. Se uma tabela for dividida em vários arquivos, dê a todos o mesmo nome em `tabela`; assim, uma chave repetida entre essas partes também será detectada.

### Validar valores e conflitos

- `CHAVE_LOJA` mantém zeros iniciais presentes no arquivo. Chaves `001` e `1` permanecem distintas; a regra de origem deve indicar se representam a mesma loja.
- `CNPJ` recebe texto em maiúsculas, sem máscara, com 14 posições. Números do Excel nesse campo são preenchidos à esquerda para 14 posições. Identificadores alfanuméricos são aceitos. Essa validação cobre o formato; a conferência dos dígitos e do cadastro permanece na rotina de origem.
- Duas colunas que apontam para o mesmo nome são combinadas quando uma está vazia ou seus valores normalizados coincidem. Valores diferentes bloqueiam a carga.
- `consistencia_por_chave` inicialmente contém `CNPJ`: se a mesma loja tiver dois CNPJs diferentes no campo padronizado, o agente sinaliza o conflito.
- Chaves nulas, chaves repetidas dentro da tabela, ausência de colunas obrigatórias e tipos inválidos impedem a publicação. A base anterior continua disponível.

O catálogo permite configurar `tipos` como `texto`, `identificador`, `cnpj`, `numero` ou `data`. A regra de nome nunca remove automaticamente qualificadores como `MATRIZ`, `FILIAL` e `FORNECEDOR`.

### Cruzar as tabelas por CHAVE_LOJA

Quando você definir qual tabela representa as linhas do dashboard, pode enriquecê-la com campos das demais. O arquivo `catalogo_exemplo_relacional.json` mostra uma configuração completa para arquivos fictícios chamados `tabela_x.*` e `tabela_y.*`:

```json
"enriquecimento": {
  "tabela_principal": "ACESSOS",
  "dimensoes": [
    {"tabela": "LOJAS", "colunas": ["CNPJ", "CLIENTE"], "obrigatoria": true}
  ]
}
```

Nesse exemplo, o painel usa as linhas de `ACESSOS` e preenche `CNPJ` e `CLIENTE` a partir de `LOJAS`, usando `CHAVE_LOJA`. Cada dimensão deve conter uma chave preenchida e única. As linhas são mantidas na ordem da tabela principal e o cruzamento não multiplica registros.

Com `obrigatoria: true`, uma loja sem correspondência bloqueia a carga. Com `false`, a linha é mantida com os campos não encontrados vazios e um aviso no relatório. Valores preenchidos divergentes também impedem a publicação.

Nos detalhes do registro aparece a origem de cada campo trazido de outra tabela. O CSV inclui essa origem em uma coluna JSON adicional. Somente as colunas da tabela principal e os campos explicitamente selecionados das dimensões ficam disponíveis na consulta.

Para ativar, ajuste os nomes das fontes e das tabelas do exemplo e indique esse arquivo em `configuracao.json`:

```json
"catalogo_colunas": "catalogo_exemplo_relacional.json"
```

Até essa configuração, `enriquecimento` permanece `null` e as fontes são concatenadas após a padronização. O projeto recebe as tabelas via Excel/CSV/TSV; a conexão direta com seu SQL depende do driver e da rotina real.

## Conectar ao seu script atual

Use a função **ao final da etapa que já salvou e aprovou os arquivos**. Se o script estiver na mesma pasta do projeto:

```python
from pathlib import Path
from integracao import atualizar_dashboard

config = Path(__file__).resolve().parent / "configuracao.json"

# Sua rotina atual atualiza, salva e aprova as planilhas antes deste ponto.
resumo = atualizar_dashboard(config)
print(f"Dashboard atualizado: {resumo['total']} registros")
```

Se o script estiver em outra pasta, o subprocesso evita alterações no caminho dos módulos:

```python
from pathlib import Path
import subprocess
import sys

projeto = Path(r"C:\Ferramentas\dashboard_acessos")

# Execute este trecho após concluir a publicação/aprovação da rotina atual.
subprocess.run(
    [sys.executable, str(projeto / "integracao.py"),
     "--config", str(projeto / "configuracao.json")],
    check=True,
)
```

O interpretador que executa a importação precisa ter `openpyxl` instalado. Com um ambiente separado, use o caminho de seu Python no primeiro argumento do subprocesso.

Também é possível passar os caminhos explicitamente:

```python
resumo = atualizar_dashboard(
    config,
    planilhas=[r"C:\Publicados\acessos_matriz.xlsx",
               r"C:\Publicados\acessos_filiais.xlsx"],
)
```

**Cada chamada substitui o consolidado inteiro.** A lista explícita deve conter todas as planilhas da publicação. Linhas removidas na origem desaparecem na próxima carga. Por padrão, os arquivos são concatenados após a padronização dos cabeçalhos; com `enriquecimento` configurado, o painel recebe as linhas da tabela principal cruzadas com as dimensões. Repetições da chave dentro de uma tabela são recusadas conforme a regra do catálogo.

O projeto oferece a etapa de consulta. A conexão com o seu sistema de aprovação deve continuar no ponto correspondente da rotina existente.

## Configuração

Os caminhos relativos são resolvidos a partir de `configuracao.json`, independentemente da pasta de execução. Você pode manter esse arquivo fora do projeto e informar `--config` tanto na importação quanto no servidor.

| Campo | O que configurar |
| --- | --- |
| `titulo` | Título exibido no painel. |
| `pasta_planilhas` | Pasta com o conjunto completo de arquivos publicados. O padrão é `planilhas_aprovadas`, dentro da pasta do projeto. |
| `banco` | Base SQLite criada pela importação. Mantenha-a em disco local no servidor. |
| `padroes` | Padrões dos nomes de arquivo que serão importados. |
| `abas` | `null` para todas as abas; ou, por exemplo, `["Acessos"]`. Com uma lista, todas as abas indicadas devem existir em cada Excel. |
| `linha_cabecalho` | Número da linha com os nomes dos campos. |
| `codificacao_csv` | `utf-8-sig`; use `cp1252` se suas exportações tiverem essa codificação. |
| `separador_csv` | `null` para detectar; ou `";"`, `","` ou `"\t"`. |
| `renomear_colunas` | Une nomes diferentes, por exemplo `{"Nome do cliente": "Cliente", "Login": "Usuário"}`. |
| `catalogo_colunas` | Arquivo do agente com equivalências, tipos, regras por tabela e enriquecimento opcional. Use `null` para desativar essa etapa. |
| `colunas_ocultas` | Campos excluídos da base, da busca, dos detalhes e da exportação. |
| `colunas_data` | Converte valores destas colunas em datas. Aceita datas do Excel, `DD/MM/AAAA` e ISO. |
| `colunas_numero` | Converte valores destas colunas em números, inclusive CSV. Aceita `1234.50` ou `1.234,50`. |
| `coluna_cliente`, `coluna_sistema`, `coluna_status` | Nomes **após renomear** para os atalhos e contadores. Se um campo não existir, seu atalho é ocultado. |
| `colunas_iniciais` | Colunas visíveis ao abrir o painel. O usuário pode mudar a seleção. |
| `limite_registros`, `limite_colunas` | Limites de importação, inicialmente 200 mil registros e 128 colunas. A carga é recusada por inteiro quando excede um limite. |
| `modo_exemplo` | `false` para sua base real. |

Os nomes de cabeçalho são comparados ignorando acentos, maiúsculas, espaços e pontuação. Com o catálogo ativo, o painel usa os nomes padronizados; com `catalogo_colunas: null`, mantém a primeira grafia encontrada. Colunas de mesmo nome devem representar a mesma informação.

Datas digitadas como texto precisam constar em `colunas_data` ou ter tipo `data` no catálogo. Números lidos do Excel são reconhecidos automaticamente. Códigos em CSV permanecem texto e mantêm zeros iniciais. No Excel, guarde códigos como texto ou com um formato composto por zeros, como `000000`; zeros que já foram perdidos no arquivo não podem ser recuperados, salvo quando uma largura fixa conhecida estiver definida, como as 14 posições do CNPJ.

Os filtros **Maior ou igual a** e **Menor ou igual a** estão disponíveis para números e datas. Para um intervalo, aplique duas condições na mesma coluna. “É diferente de” compara valores preenchidos; use “Está vazio” para encontrar campos sem valor.

## Compartilhar na rede interna

Instale e execute o projeto em uma máquina ou servidor que permanecerá ligado:

```bash
python servidor.py --host 0.0.0.0 --porta 8000
```

Os colegas acessam `http://IP-DO-SERVIDOR:8000`, conforme a liberação da rede interna. O endereço `0.0.0.0` é usado pelo servidor para escutar a rede, não é o endereço a enviar aos colegas. Somente o servidor precisa ter Python e acesso aos arquivos publicados.

O painel permite consulta e exportação. A publicação dos dados é feita pelo script de importação, que precisa de permissão de escrita no diretório do banco. A base usa SQLite com WAL e deve permanecer em **disco local**, mesmo quando as planilhas forem lidas de uma pasta compartilhada.

### Caminhos de rede no Windows

Unidades mapeadas podem ser resolvidas pelo Windows para um caminho UNC, como `\\servidor\compartilhamento\pasta`. A abertura da base trata esse formato e mantém o acesso somente para leitura. Espaços, acentos e símbolos no nome do arquivo são preservados.

Para atualizar uma instalação anterior que mostra `invalid uri authority`, pare o servidor com `Ctrl+C`, substitua `consulta.py` pela versão deste pacote e execute novamente `python servidor.py`. Se você usa `--config`, mantenha o mesmo argumento. Essa correção não exige substituir as planilhas, alterar a configuração ou recriar a base.

Configure `banco` para uma pasta local com permissão de escrita na máquina que executa a importação e o servidor. A correção do endereço UNC não altera o modo WAL: esse modo exige armazenamento local. As planilhas de entrada podem continuar na rede. Veja as referências oficiais sobre [URIs do SQLite](https://www.sqlite.org/uri.html) e [WAL](https://www.sqlite.org/wal.html).

Para uma implantação corporativa, coloque o serviço atrás do proxy interno com HTTPS e do controle de acesso da empresa. Como alternativa simples, o servidor aceita autenticação compartilhada por `DASHBOARD_USUARIO` e `DASHBOARD_SENHA`. No PowerShell:

```powershell
$env:DASHBOARD_USUARIO = "consulta"
$env:DASHBOARD_SENHA = Read-Host "Senha do painel" -MaskInput
python servidor.py --host 0.0.0.0 --porta 8000
```

`-MaskInput` está disponível no PowerShell 7. Em outros ambientes, forneça as variáveis pelo gerenciador do serviço. Não grave a senha no código ou em `configuracao.json`. A autenticação Basic deve ser usada com HTTPS no acesso pela rede. Sem essas variáveis ou um proxy autenticado, qualquer pessoa que alcance o serviço poderá consultar todos os dados publicados.

Permissões individuais por cliente, login corporativo e auditoria de usuários exigem integração com a identidade da empresa. Esta versão tem uma base de consulta compartilhada.

## Atualizações e erros

Uma transação publica a nova base somente quando todas as fontes passam na leitura e validação. Se houver erro de arquivo, cabeçalho duplicado, campo sem cabeçalho, data inválida, erro de fórmula ou alteração do arquivo durante a leitura, a base anterior é mantida e o comando termina com código 1. `check=True` faz sua rotina detectar esse erro.

Uma pasta sem arquivos ou uma carga sem registros também é recusada. Para limpar a base intencionalmente, execute `python integracao.py --permitir-vazio` ou use `atualizar_dashboard(config, permitir_vazio=True)`.

Fórmulas são consultadas pelos **resultados já salvos no Excel**. Recalcule e salve os arquivos antes da importação. A carga recusa fórmulas sem resultado salvo; não recalcula fórmulas e não consegue identificar se um resultado salvo está desatualizado.

O CSV exporta os dados e a origem de cada linha, em UTF-8 com BOM e separador `;`. Valores que poderiam ser interpretados como fórmulas recebem um apóstrofo inicial. Isso inclui valores negativos na exportação; eles continuam numericamente filtráveis no painel.

## Arquivos do projeto

- `integracao.py`: função de integração e comando de importação.
- `agente_padronizacao.py`: análise sem publicação e relatórios HTML/JSON.
- `padronizacao.py`: catálogo, sugestões e validações de colunas e chaves.
- `relacionamentos.py`: cruzamentos configurados por CHAVE_LOJA.
- `catalogo_colunas.json`: equivalências e regras em uso.
- `catalogo_exemplo_relacional.json`: exemplo de configuração para cruzar tabelas.
- `consulta.py`: pesquisa, filtros, totais e exportação.
- `servidor.py`: aplicação WSGI, autenticação opcional e servidor Waitress.
- `configuracao.json`: fontes e nomes dos campos.
- `index.html` e `static/`: interface, sem dependência de CDN.
- `planilhas_aprovadas/`: exemplos substituíveis pelas suas fontes reais.
- `testes/`: testes automatizados com a biblioteca padrão do Python.

Para executar os testes:

```bash
python -m unittest discover -s testes -v
```

Referências técnicas: [leitura de Excel e resultados de fórmulas](https://openpyxl.readthedocs.io/en/stable/_modules/openpyxl/reader/excel.html) e [servidor Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/usage.html).

Referência do formato de CNPJ: [CNPJ alfanumérico — Receita Federal](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/cnpj-alfanumerico).
