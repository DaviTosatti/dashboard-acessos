# Prospecção e continuidade do Bradesco Expresso

Este módulo foi integrado ao painel de consultas. A navegação lateral mantém **Consultar acessos** e **Fontes de dados** e acrescenta **Prospecção**, com o mesmo layout e uma paleta de vermelho, vinho e neutros. A interface usa ícones e gráficos locais; não carrega imagens, fontes ou scripts externos.

## Começar no Windows

1. Extraia **todo** o ZIP em uma pasta nova, por exemplo `C:\dashboard_expresso`. Não execute de dentro do ZIP.
2. Abra a pasta `dashboard_acessos` extraída. Ela contém `servidor.py`, `configuracao.json` e os arquivos `.bat`.
3. Na primeira utilização, dê dois cliques em `INSTALAR_DEPENDENCIAS.bat`. Requer Python 3.10 ou superior. Se a rede bloquear a instalação, use o procedimento de instalação de pacotes da sua equipe de TI.
4. Dê dois cliques em `INICIAR_DASHBOARD.bat`. Ele importa os exemplos e inicia o servidor. Mantenha a janela aberta.
5. Abra http://127.0.0.1:8000 no navegador. Para encerrar, pressione Ctrl+C na janela do servidor.

Também pode usar o terminal. No Explorador, abra a pasta do projeto, clique na barra de endereço, digite `cmd` e pressione Enter. Execute:

```bat
python -m pip install -r requirements.txt
python integracao.py
python servidor.py
```

O ZIP inclui **84 acessos fictícios**, além de **48 lojas fictícias, 12 responsáveis fictícios, 168 contratos e históricos de produção**. Os dados de prospecção têm corte em **15/10/2026** e fechamento até **09/2026**. Outubro aparece como parcial. São exemplos para validar a navegação; os produtos e nomes não representam cadastros oficiais.

## Atualizar uma instalação anterior

Pare o servidor. Extraia o novo ZIP em outra pasta e teste com os exemplos. Depois, leve suas planilhas e configurações locais para a nova pasta. Nesta versão há vários módulos novos: substituir apenas `consulta.py` não instala a prospecção.

Preserve as regras que já usa em `catalogo_colunas.local.json` e a configuração das consultas. Acrescente a seção `prospeccao` do exemplo abaixo ao seu `configuracao.local.json`. Nos comandos, use sempre `--config configuracao.local.json`. Não substitua suas planilhas reais pelos exemplos.

O banco SQLite deve ficar no disco local do computador que roda o servidor, por exemplo `C:\dashboard_dados\dashboard.sqlite3`. A correção de URI do Windows continua incluída. As pastas de planilhas podem ficar na rede. O README principal explica a publicação na intranet e a autenticação.

## Intervalos e nova aba de consultores

Escolha os meses **De** e **Até**, incluindo os dois no período, e clique em Aplicar filtros. Há atalhos para o último mês fechado e os últimos 3, 6 ou 12 meses. A produção e os volumes do funil usam o intervalo; os estados da carteira e as demais coberturas usam o fechamento do último mês. A tela identifica esses recortes.

Na aba **Produção de consultores**, escolha um consultor ou filtre a gerência para listar seus responsáveis, os volumes e as atividades registradas. A busca por texto, o tipo de atividade e a exportação usam todas as páginas. Contratos usam a origem, produção usa a carteira de cada mês e ações usam o executor informado. As explicações e os exemplos de comparação estão em [ATUALIZACOES.md](ATUALIZACOES.md).

Ao abrir uma lista de filtro, digite no campo de pesquisa para localizar a opção. Use setas, Enter e Esc pelo teclado. O topo lembra suas escolhas durante a sessão do navegador.

## O que cada tela mostra

| Tela | Conteúdo |
| --- | --- |
| Visão geral | Emissões, aproveitamento da safra, lojas com negócios, inativas, evolução e resultados por gerência |
| Produção de consultores | Resumo e atividades por consultor/região, origem, período, busca, tipo e exportação integral |
| Funil | Safra de emissão, decisões, cancelamentos após aprovação, janela em D dias, prazos e volumes por consultor |
| Continuidade | Matriz de safras por idade, M5/M6/M12, recorrência, médias, medianas e condições de continuidade |
| Risco operacional | Busca por loja, CNPJ, município ou consultor; situação em negócios e em transações; reativação; histórico por loja |
| Serviços | Habilitação, utilização por serviço, habilitações parciais e perfil operacional |
| Acompanhamento | Treinamentos, multiplicador, suportes M2/M4, atrasos e comparação por condição antes de cada marco |
| Qualidade dos dados | Cobertura, indeterminação, arquivos, avisos e aviso de última carga bloqueada |

Os filtros do topo são aplicados ao clicar em **Aplicar filtros**. A busca e os filtros da lista de risco refinam somente a lista operacional e a exportação. A exportação contém todas as lojas filtradas, independentemente da página visível. O histórico é aberto clicando na chave da loja.

## Configuração para as bases reais

Faça uma cópia dos arquivos de configuração, usando nomes terminados em `.local.json`:

```json
"prospeccao": {
  "ativo": true,
  "pasta": "planilhas_prospeccao_reais",
  "catalogo": "catalogo_prospeccao.local.json",
  "data_corte": "2026-10-15",
  "ultimo_mes_fechado": "2026-09",
  "dias_observacao": 30,
  "quantidade_producao": "liquida",
  "modo_exemplo": false
}
```

Esse trecho é uma propriedade dentro do objeto principal da configuração. Não substitui as demais propriedades. Atualize as datas a cada carga; elas **não avançam automaticamente**. Também ajuste o `modo_exemplo` das consultas para `false` quando substituir seus exemplos. Com `prospeccao.ativo: false`, o módulo fica sem consulta publicada e as consultas de acessos continuam funcionando.

Os caminhos relativos partem da pasta do arquivo de configuração, inclusive quando a execução começa em outro diretório. As duas pastas têm nomes simples: `planilhas_aprovadas` e `planilhas_prospeccao`. Nenhum nome de pasta contém `/`.

O banco não acompanha o ZIP: ele é gerado pela importação. O limite padrão é 300 mil linhas de entrada e 240 meses de histórico por loja; podem ser ajustados nas propriedades `limite_linhas` e `limite_meses_por_loja` da seção de prospecção. O sistema lê um snapshot completo em memória; volumes muito maiores exigem outra estratégia de armazenamento e apuração.

## Preparar os arquivos sem renomear as colunas originais

`modelos_prospeccao` contém 12 CSVs vazios, com os cabeçalhos aceitos. Copie-os para a pasta real definida na configuração e preencha apenas as bases de que dispõe. Bases opcionais podem ficar com só o cabeçalho. Os cadastros de lojas e serviços precisam conter registros; as demais bases podem começar vazias e deixam os respectivos indicadores sem observação ou com avisos.

Os cabeçalhos ficam na primeira linha. Os CSVs de exemplo e os modelos usam UTF-8 e ponto e vírgula; a configuração geral permite ajustar a codificação e o separador para sua origem. Também são aceitos Excel `.xlsx` e `.xlsm`, além de CSV e TSV. Para apontar para um Excel com várias abas, declare a aba de cada tabela no catálogo. Um mesmo workbook pode alimentar várias tabelas, uma aba para cada granularidade:

```json
"credenciados": {
  "arquivo": "cadastros.xlsx",
  "aba": "Lojas",
  "colunas": {
    "NO_CNPJ": "CNPJ",
    "NM_ESTABELECIMENTO": "RAZAO_SOCIAL",
    "DT_INICIO_OPERACAO": "DATA_INAUGURACAO"
  }
}
```

Esse trecho substitui somente a entrada `credenciados` em `catalogo_prospeccao.local.json`. Mantenha as 12 entradas na propriedade `fontes`. Cada tabela usa um arquivo/aba consolidado; se sua origem está em vários arquivos de uma mesma tabela, sua rotina deve consolidá-los antes da importação.

O módulo normaliza acentos, espaços e maiúsculas dos cabeçalhos e já conhece `CNPJ`/`NO_CNPJ` e `CHAVE_LOJA`/`ID_CREDENCIADO`. Outras equivalências devem ser declaradas no catálogo da tabela. Uma coluna desconhecida bloqueia a carga. Para uma coluna deliberadamente fora do estudo, mapeie seu nome para `IGNORAR`. Duas colunas apontando para o mesmo destino também são bloqueadas, evitando escolher uma silenciosamente.

No módulo original de acessos, o agente de sugestões e o catálogo `catalogo_colunas.json` continuam funcionando. Na prospecção, o esquema conhecido e os mapeamentos por tabela validam as entradas; nomes sem significado confirmado não são adivinhados.

### Granularidade e campos mínimos

| Arquivo/tabela | Uma linha representa | Campos obrigatórios por registro |
| --- | --- | --- |
| `credenciados` | Uma unidade | CHAVE_LOJA, RAZAO_SOCIAL e DATA_INAUGURACAO |
| `responsaveis` | Um consultor ou executor | ID_RESPONSAVEL, NOME |
| `servicos` | Um serviço | ID_SERVICO, NOME, CATEGORIA, TIPO_ATIVIDADE |
| `contratos` | Um contrato | ID_CONTRATO, DATA_EMISSAO, GERENCIA_ORIGEM, RESPONSAVEL_ORIGEM |
| `status_contrato` | Um evento de situação | ID_EVENTO, ID_CONTRATO, STATUS, DATA_EVENTO |
| `contrato_loja` | Um vínculo contrato × loja × início | ID_CONTRATO, CHAVE_LOJA |
| `vinculacoes` | Uma vigência da carteira | ID_VINCULACAO, CHAVE_LOJA, GERENCIA, ID_RESPONSAVEL, INICIO_VIGENCIA |
| `producao` | Loja × mês × serviço | CHAVE_LOJA, COMPETENCIA, ID_SERVICO e quantidade conforme o modo configurado |
| `habilitacoes` | Uma vigência de serviço | ID_HABILITACAO, CHAVE_LOJA, ID_SERVICO, DATA_INICIO, SITUACAO |
| `cobertura` | Loja × mês × domínio | CHAVE_LOJA, COMPETENCIA, DOMINIO_DADOS, STATUS_COMPLETUDE; DATA_VALIDACAO se completo |
| `acompanhamentos` | Uma ação prevista ou concluída | ID_ACAO, CHAVE_LOJA, TIPO_ACAO, STATUS |
| `acao_servico` | Um conteúdo de uma ação | ID_ACAO, ID_SERVICO |

CNPJ, município, UF, bairro e ramo são campos adicionais recomendados do cadastro. CNPJ é texto, pode ter máscara e não substitui a chave da unidade. O formato é validado; não há consulta ao cadastro fiscal nem validação de dígito verificador.

**CHAVE_LOJA é única no cadastro de credenciados.** Nos fatos de produção, a chave é **CHAVE_LOJA + COMPETENCIA + ID_SERVICO**. Nas ações, é ID_ACAO. Repetir a loja em meses e serviços diferentes é necessário, não erro de duplicidade. Não coloque essas bases de fatos na pasta de consultas que exige unicidade da loja por tabela.

Datas aceitam `AAAA-MM-DD`, datas reais do Excel ou `DD/MM/AAAA`. Competência usa `AAAA-MM` ou uma data real do Excel. Identificadores devem ser texto para conservar zeros. `DATA_EVENTO` também aceita data/hora ISO; eventos de um contrato no mesmo instante são recusados por ambiguidade. Normalize DATA_EVENTO para o horário local da operação, sem sufixo de fuso. Datas sem hora são tratadas como meia-noite, para detectar duplicidades do mesmo instante.

### Domínios

| Campo | Valores |
| --- | --- |
| GERENCIA / GERENCIA_ORIGEM | Sul, Sudeste, Nordeste 1, Nordeste 2, Centro-Oeste/Norte, São Paulo |
| TIPO_ATIVIDADE / DOMINIO_DADOS | NEGOCIO, TRANSACAO |
| STATUS do contrato | PENDENTE, APROVADO, REPROVADO, DESISTENCIA, CANCELADO |
| STATUS_COMPLETUDE | COMPLETO, PARCIAL, AUSENTE |
| SITUACAO de habilitação | HABILITADO, SUSPENSO |
| TIPO_ACAO | TREINAMENTO, SUPORTE |
| STATUS da ação | CONCLUIDO, PLANEJADO, NAO_REALIZADO, NAO_INFORMADO |
| MARCO_OPERACIONAL do suporte | 2 ou 4 |
| COM_MULTIPLICADOR | SIM, NÃO ou vazio quando desconhecido |
| TREINAMENTO_STATUS do cadastro | NAO_REALIZADO, NAO_INFORMADO ou REALIZADO; realizado sem data não confirma a condição em períodos históricos |

Valores de domínio ignoram acentos e diferenças de caixa. Município, ramo, gerência e responsável são utilizados como vieram dos cadastros válidos; São Paulo é uma gerência própria, sem inferência pela UF.

### Zero e cobertura

Para afirmar que a loja não fez negócios em um mês, registre cobertura COMPLETO para NEGOCIO, com data de validação até o corte, e feche a competência. Dentro desse domínio validado, a ausência de linha de um serviço representa zero. Sem cobertura, até uma quantidade informada fica como produção parcial, fora das métricas que exigem confirmação.

Uma loja sem três meses comprovados não vira inativa por falta de dados. Depois de uma lacuna, três novos meses completos de zero comprovam inatividade. Um ou dois zeros após a lacuna ainda podem deixar a situação indeterminada. Negócios e transações têm cobertura própria.

Meses anteriores ao M0 são recusados se houver produção. Dentro de M0 a base mensal não permite afirmar em qual dia a produção ocorreu. Não some colunas M3, M6 ou M12 sem confirmar se são meses isolados ou janelas acumuladas: o importador exige transformar a origem em loja × competência × serviço e não infere esse significado.

### Quantidades e estornos

Com `quantidade_producao: "liquida"`, preencha QTD_VALIDA. QTD_ESTORNADA é informativa e não é subtraída novamente. Com `"bruta_menos_estornos"`, deixe QTD_VALIDA vazia e preencha QTD_CONFIRMADA e QTD_ESTORNADA; o cálculo é confirmada menos estornada. O resultado deve ser inteiro e não negativo. A escolha é única para a carga; normalize fontes com convenções diferentes na sua rotina antes de publicá-las.

### Vínculos, decisões e ações

Não sobrescreva a gerência nem o responsável anterior: encerre a vigência e cadastre a seguinte. A data final é inclusiva; a nova vigência começa no dia seguinte. Sobreposições bloqueiam a carga. O funil usa a origem do contrato; a carteira mensal usa o vínculo no último dia do mês, ou no corte quando o mês é parcial. Filtros de município, ramo e safra no funil requerem uma loja vinculada e excluem contratos ainda sem esse vínculo.

O histórico registra cada decisão e preserva a primeira aprovação mesmo após cancelamento. Uma loja sem vínculo contratual participa da carteira, mas não é atribuída a uma inauguração do funil; isso gera aviso. Os cadastros são fotografias atuais, enquanto gerência/responsável, habilitação e status têm histórico. Mudanças históricas de município e ramo não são modeladas nesta versão.

Em `contrato_loja`, TIPO_VINCULO vazio equivale a INAUGURACAO. O funil de inauguração usa somente esse tipo e os vínculos vigentes na data de abertura. Uma loja não pode ter dois contratos de origem concorrentes na inauguração. Outros vínculos, como renovação, podem ser cadastrados com outro tipo e não multiplicam a inauguração.

Treinamento exige uma ação concluída com DATA_REALIZADA. O estado do cadastro pode informar não realizado ou não informado; não substitui a data de conclusão. O módulo permite registrar modalidade, executor, multiplicador e conteúdo por serviço na ponte `acao_servico`. O histórico por loja exibe ações e habilitações; o conteúdo e a produção por serviço também estão no endpoint de detalhe para extensões.

Cada loja tem uma ação de suporte por marco M2/M4. A data prevista cadastrada prevalece. Se não houver ação, o prazo analítico é o último dia de M2/M4 e a pendência aparece como sem cadastro. Encerramento antes do prazo exclui a loja daquele denominador de suporte.

## Validar, publicar e integrar

Antes de publicar, execute:

```bat
python prospeccao.py --config configuracao.local.json --validar
```

O relatório fica em `relatorios/validacao_prospeccao.json`. A validação não cria nem substitui o banco. Para publicar somente a prospecção, mantendo a consulta de acessos existente:

```bat
python prospeccao.py --config configuracao.local.json
```

Para atualizar os dois módulos em uma mesma transação:

```bat
python integracao.py --config configuracao.local.json
```

Sua rotina existente pode continuar chamando:

```python
from integracao import atualizar_dashboard

# Execute após concluir o salvamento e a aprovação das entradas.
resumo = atualizar_dashboard(r"C:\dashboard_expresso\configuracao.local.json")
```

Se só precisar atualizar a prospecção:

```python
from prospeccao import atualizar_prospeccao
resumo = atualizar_prospeccao(r"C:\dashboard_expresso\configuracao.local.json")
```

O snapshot substitui o conjunto anterior: envie o histórico completo, não apenas o último mês. Arquivos originais são apenas lidos e permanecem na origem. Os eventos e vigências recebidos são preservados no snapshot; o banco mantém a trilha de cargas com hash dos arquivos e versão da regra, mas não mantém cópias integrais de todos os snapshots anteriores. Mantenha o backup das fontes conforme sua rotina.

Duplicidades, referências inexistentes, vigências sobrepostas, quantidades inválidas, cobertura completa sem validação, decisões anteriores à emissão e produção anterior ao mês de inauguração bloqueiam a publicação. Inauguração anterior à aprovação e produção sem habilitação geram avisos. Uma carga bloqueada conserva a base anterior; a tela de qualidade mostra o motivo da última tentativa. O relatório de validação indica a análise das entradas; a confirmação de publicação vem do comando concluído com sucesso.

`resumo_loja_mes` é uma tabela derivada, com chave loja + competência e payload contendo os indicadores da unidade. `pro_controle_carga` mantém data, versão e identificação das fontes. `pro_snapshot` contém as entradas normalizadas e os resumos da publicação. O navegador consulta apenas APIs GET autenticadas pelo mesmo mecanismo do painel original.

## Roteiro de estudo

1. Semanalmente, valide as cargas, confira as lacunas e abra a lista de risco crítico para encaminhar os contatos ao responsável vigente.
2. No fechamento mensal, confirme competência e corte, examine o funil por gerência e compare aproveitamento na mesma janela em D dias.
3. Compare safras na mesma idade operacional, conferindo os numeradores, os denominadores e os encerramentos.
4. Revise lojas após M4, serviços habilitados sem utilização e suportes vencidos. Registre as execuções nas bases de acompanhamento.
5. A cada trimestre, investigue os recortes de região, município, bairro, ramo, safra, implantação e treinamento. Grupos com menos de cinco observações são identificados; não trate esses grupos como padrão consolidado.
6. Registre a pergunta, o período, o tamanho do grupo, o indicador, as limitações, a hipótese, a ação proposta e o critério de acompanhamento. As hipóteses não alteram os dados da origem.

Os indicadores seguem a especificação analítica do TXT. O PDF de programa interno mencionado no texto não foi fornecido; nenhuma regra específica dele foi presumida. A convenção implementada é **M0 = inauguração**, suporte em M2/M4 e pós-suporte a partir de M5. Mudar a convenção exige ajustar a regra e sua versão, não apenas trocar os rótulos.
