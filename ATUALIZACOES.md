# Atualização de períodos e consultores — 16/10/2026

## Períodos de/até

O topo da prospecção agora permite selecionar dois meses, incluindo ambos no intervalo. Há atalhos para o último mês fechado, últimos 3, 6 ou 12 meses e o ano até o último fechamento. A referência dos atalhos vem do fechamento da base, não do relógio do computador.

Contratos emitidos, aprovações e inaugurações são apurados por IDs distintos no intervalo. O aproveitamento é recalculado usando os contratos das safras selecionadas. Não há soma de taxas mensais. Os volumes de negócios somam os meses com cobertura completa, respeitando a gerência e o responsável de cada mês.

A situação de risco, as lojas da carteira, os marcos de continuidade, a utilização de serviços e as coberturas de treinamento/suporte mostram o fechamento do último mês do intervalo. Cada indicador informa seu recorte. O botão **Exportar fechamento** exporta essa lista de lojas do último mês. A aba de consultores oferece a exportação das atividades de todo o intervalo.

O comparativo anterior usa um intervalo imediatamente anterior com o mesmo número de meses. Exemplo: julho a setembro é comparado com abril a junho. O comparativo anual usa julho a setembro do ano anterior. Para indicadores de fechamento, os pontos comparados são os finais desses intervalos. Um intervalo de um mês preserva os resultados da versão anterior. Intervalos invertidos, incompletos, posteriores ao corte ou superiores a 120 meses são recusados.

Na consulta original de acessos, campos de data podem ser filtrados com **De** e **Até**, incluindo as duas datas. Se houver vários campos de data, escolha qual deles deseja filtrar. Os limites acompanham a busca, os demais filtros e a exportação.

## Produção de consultores

A aba **Produção de consultores** utiliza os filtros de período, gerência, responsável, município, ramo e safra do topo. Para listar os consultores de uma região, escolha a gerência e deixe o responsável em **Todos os responsáveis**. Para consultar uma pessoa, escolha seu nome ou clique nele no resumo.

O resumo mostra contratos emitidos, contratos aprovados, inaugurações, lojas, negócios, transações, treinamentos, suportes e pendências. Consultores com vínculo de carteira no período continuam no resumo regional mesmo quando não têm atividade registrada. Sem filtro regional, os responsáveis cadastrados também podem aparecer com zero registros. Busca e tipo de atividade refinam o resumo e a lista; nesse caso, os resultados representam os registros encontrados.

As atividades disponíveis vêm das bases de contratos, eventos de decisão, inaugurações, produção mensal, acompanhamentos e habilitações. A lista mostra data, responsável, gerência, tipo, contrato, loja, serviço/detalhe, quantidade, cobertura, atribuição e arquivo/aba/linha de origem.

As atribuições são explícitas:

- Emissões, decisões e inaugurações vinculadas usam o responsável de origem do contrato. O responsável de origem não é apresentado como executor da aprovação.
- Produção é atribuída à carteira vigente no fechamento de cada competência. A quantidade mensal não identifica quem realizou cada operação. A data exibida para produção é o fechamento da competência, limitado pelo corte.
- Treinamentos e suportes concluídos usam ID_EXECUTOR. Se estiver vazio, o registro aparece sem executor e não entra como execução individual de um consultor.
- A gerência de uma ação vem do vínculo da loja na data. Antes da inauguração, pode vir da origem contratual da loja. A pessoa executora pode ser diferente do responsável da carteira.
- Pendências consideram prazos dentro do intervalo e sem realização até seu fim. Elas usam o executor previsto ou o responsável para encaminhamento e ficam separadas das ações realizadas. A tela de acompanhamento continua mostrando o estoque de suportes vencidos no fechamento.
- Habilitações usam o responsável da carteira na data e informam que o executor não consta na base.

Produção com quantidade positiva e cobertura insuficiente fica visível como informada, mas fora dos volumes confirmados. A lista mostra registros positivos de produção; zeros confirmados permanecem nos indicadores e históricos por loja. A quantidade de registros de atividade não equivale à quantidade de negócios ou de contratos distintos.

O resumo usa todas as atividades filtradas. A lista é paginada em 25, 50 ou 100 registros. **Exportar atividades** inclui todas as páginas do mesmo recorte, mantendo a origem e a atribuição. Buscar contrato, loja ou serviço e escolher um tipo de atividade facilita consultar um conjunto específico.

## Filtros pesquisáveis e usabilidade

Ao abrir uma lista de filtro, um campo de pesquisa recebe o foco. A busca local ignora caixa e acentos e encontra opções pelo texto ou identificador. Use as setas para navegar, Enter para selecionar e Esc para fechar. Tab segue para o próximo controle. Os filtros por coluna criados dinamicamente também recebem a pesquisa.

Nos filtros de sistema e status da consulta de acessos, a pesquisa consulta a base, permitindo encontrar valores além das primeiras 100 sugestões. Quando há mais resultados, refine o texto. O campo de cliente mantém sua pesquisa de sugestões. Paginações continuam usando seletores simples.

Os filtros aplicados aparecem como etiquetas removíveis. Alterações ainda não aplicadas recebem um aviso. As escolhas do topo são lembradas durante a sessão do navegador; nenhum dado de produção ou credencial é armazenado por essa preferência. **Limpar filtros** volta ao último mês fechado e retira os demais recortes.

As consultas mais recentes substituem as anteriores, evitando que uma resposta atrasada volte a preencher a tela. Se uma consulta falhar, os resultados anteriores continuam visíveis, o erro é informado e a exportação daquela consulta fica suspensa até a próxima consulta bem-sucedida.

## Atualizar o projeto

Pare o servidor e extraia o ZIP inteiro em uma pasta local nova. Preserve suas configurações e planilhas reais. Copie suas configurações locais para a nova pasta, confira os caminhos e execute o inicializador ou os comandos do guia. Nenhuma dependência Python nova foi acrescentada. Os modelos de entrada continuam os mesmos.

Esta entrega modifica backend, HTML, CSS e JavaScript; copie o projeto completo. Os BATs e o guia do Windows continuam incluídos. Se o navegador ainda exibir a tela antiga, use Ctrl+F5.
