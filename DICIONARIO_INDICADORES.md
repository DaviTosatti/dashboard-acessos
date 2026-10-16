# Dicionário dos indicadores

Regra `expresso-1.0`. Contagens usam IDs distintos na granularidade indicada. Taxas são percentuais de 0 a 100. Denominador zero resulta em valor ausente (`—`), sem converter para zero. O painel recalcula totais pelos numeradores e denominadores, sem média simples das taxas regionais.

## Aplicação de intervalos

Com **De/Até**, os dois meses são incluídos. F01 a F10 e F03_D são recalculados pelos registros do período, contando contratos e lojas distintos na granularidade correspondente. Q01 soma a produção confirmada de todos os meses do intervalo. Os demais indicadores Q, S e T permanecem vinculados ao fechamento do último mês; não são somados entre competências. A situação operacional, os perfis, as safras e a exportação de fechamento também usam esse último mês.

O comparativo anterior usa um intervalo anterior da mesma duração; o anual desloca os dois limites em 12 meses. Para indicadores de fechamento, comparam-se os finais desses intervalos. A API mantém os campos `mensal` e `anual` para compatibilidade e informa `inicio` e `competencia` do intervalo comparado. O campo `escopo` identifica o recorte de cada indicador. A aba de consultores oferece outra apuração: eventos e volumes registrados no intervalo, com a atribuição de cada fonte. Veja [ATUALIZACOES.md](ATUALIZACOES.md).

## Contratos

Safra é o mês da emissão. Os resultados de safra acumulam decisões até a data de corte da carga. Portanto, uma safra antiga teve mais tempo de observação; **F03_D** oferece a janela comparável em D dias. O filtro de consultor e gerência usa a origem do contrato.

| Código | Indicador | Cálculo |
| --- | --- | --- |
| F01 | Contratos emitidos | Contratos emitidos na competência |
| F02 | Aprovações ocorridas | Contratos com evento APROVADO ocorrido na competência até o corte; um contrato conta uma vez por mês |
| F03 | Aproveitamento da safra | Contratos da safra com alguma aprovação até o corte / contratos emitidos da safra |
| F03_D | Aproveitamento em D dias | Aprovação até D dias da emissão / contratos da safra que já completaram D dias |
| F04 | Pendência da safra | Situação final PENDENTE no corte / emitidos da safra |
| F05 | Reprovação da safra | Situação final REPROVADO no corte / emitidos da safra |
| F06 | Desistência da safra | Situação final DESISTENCIA no corte / emitidos da safra |
| F07 | Inaugurações ocorridas | Unidades vinculadas aos contratos do recorte, inauguradas na competência até o corte |
| F08 | Conversão em inauguração | Contratos aprovados da safra que originaram alguma inauguração válida / contratos aprovados da safra |
| F09 | Tempo de decisão | Mediana dos dias entre emissão e primeiro evento de decisão diferente de PENDENTE, na safra |
| F10 | Tempo de implantação | Mediana dos dias entre primeira aprovação e primeira inauguração válida, por contrato aprovado da safra |

F02 / F01 não é usado como aproveitamento. Para F08 e F10, múltiplas lojas de um contrato não multiplicam o contrato. Inauguração anterior à aprovação gera aviso e fica fora da conversão e do cálculo de tempo desse vínculo. Um contrato cancelado após aprovação conserva sua aprovação histórica em F03 e aparece em contagem separada de cancelamentos. As situações finais exibidas no funil são mutuamente exclusivas; elas não devem ser somadas às aprovações históricas como se fossem etapas independentes.

## Produção e continuidade

O mês é observável em um domínio quando está fechado e tem cobertura COMPLETO, validada até o corte. `E(t)` contém lojas de M1 em diante, operantes no início do mês e com negócios observáveis. Uma loja encerrada durante o mês ainda pode integrar a produção daquele mês; o estado de encerramento é exibido separadamente. Quantidades de domínios incompletos não entram nas métricas confirmadas.

| Código | Indicador | Cálculo |
| --- | --- | --- |
| Q01 | Negócios mensais confirmados | Soma dos negócios nas lojas com cobertura completa que operaram no mês; inclui M0 |
| Q02 | Lojas com negócios | Lojas de E(t) com negócios > 0 |
| Q03 | Percentual de lojas com negócios | Q02 / quantidade de lojas de E(t) |
| Q04 | Negócios por loja elegível | Negócios das lojas de E(t) / quantidade de lojas de E(t) |
| Q05 | Negócios por loja produtora | Negócios das lojas de E(t) / Q02 |
| Q06 | Mediana de negócios por loja | Mediana nas lojas de E(t), incluindo zeros confirmados |
| Q07_M5/M6/M12 | Atividade na idade | Lojas produtoras no marco / lojas que alcançaram o marco com mês fechado e cobertura válida |
| Q08 | Recorrência pós-M4 | Por loja: meses com negócios em M5 em diante / meses observáveis no intervalo. Total: soma desses meses produtivos / soma dos meses observáveis |
| Q09 | Inatividade operacional | Lojas com três ou mais meses completos consecutivos sem negócios e sem encerramento formal no mês |
| Q10 | Reativação mensal | Lojas inativas no fechamento anterior que voltaram a produzir no mês, com observação válida |
| Q11 | Taxa de reativação | Q10 / lojas inativas no fechamento anterior com observação válida e operação no mês atual |
| Q12 | Meses até primeiro negócio | Mediana das idades do primeiro mês com negócios, exigindo cobertura desde M0 até aquele mês |
| Q13 | Nunca produziu | Lojas sem negócios e com histórico completo desde M0; lacunas resultam em condição desconhecida |

Q12 usa **meses**, pois não há fatos diários. Não estima dias a partir de quantidades mensais. Quantidade de negócios / lojas é uma média, não uma taxa de lojas. A participação de cada loja na produção é sua quantidade / total de negócios confirmados do recorte; aparece separadamente na lista e no CSV.

Na matriz por idade, uma loja precisa ter completado o marco até o mês de referência. Uma loja encerrada até o marco não compõe o denominador de atividade daquele marco. Os encerramentos continuam na coluna da safra; confira essa coluna para evitar interpretar a atividade das observadas como retenção de toda a safra. Um encerramento posterior não apaga observações válidas de marcos anteriores.

## Situação operacional

M0 é o mês da inauguração; a contagem de meses consecutivos começa em M1. A classificação é calculada separadamente para negócios e transações.

| Situação | Regra |
| --- | --- |
| Em implantação | Ainda em M0 |
| Ativo | Quantidade positiva no mês fechado e observável |
| Atenção | Um mês zero, com sequência conhecida |
| Risco crítico | Dois meses zero, com sequência conhecida |
| Inativo | Pelo menos três meses zero consecutivos comprovados |
| Encerrado | Encerramento formal registrado até o fechamento da competência |
| Indeterminado | Competência incompleta ou sequência não comprovada |

Um mês desconhecido interrompe a sequência comprovada. Depois dele, um ou dois zeros ainda não distinguem atenção de uma inatividade anterior; três zeros comprovam inatividade. `reativado` e `nunca_produziu` são marcadores adicionais. Transações positivas não substituem negócios na regra de risco em negócios.

## Serviços e acompanhamento

| Código | Indicador | Cálculo |
| --- | --- | --- |
| S01 | Utilização de serviço | Produtoras do serviço / lojas de M1 em diante habilitadas durante o mês inteiro e observáveis no domínio do serviço |
| S02 | Diversificação | Por loja: número de categorias de negócios com produção positiva. No agregado: mediana entre lojas observadas |
| S03 | Perfil operacional | Somente transações; somente negócios; ambos; nenhuma atividade; indeterminado se algum domínio não é observável |
| T01 | Cobertura de treinamento | Lojas com ação de treinamento concluída até o mês / lojas inauguradas do recorte |
| T02 | Treinadas com multiplicador | Lojas com treinamento realizado por multiplicador / lojas com treinamento concluído |
| T03 | Cobertura M2 | Suportes M2 realizados até o mês / lojas com prazo M2 vencido e não encerradas antes do prazo |
| T04 | Cobertura M4 | Suportes M4 realizados até o mês / lojas com prazo M4 vencido e não encerradas antes do prazo |
| T05 | Suportes no prazo | Suportes M2/M4 realizados até a data prevista / suportes cujo prazo venceu |
| T06 | Atividade por treinamento | Q07 por condição de treinamento registrada antes do início da idade avaliada |

S01 é apresentado serviço a serviço, com numerador, denominador e quantidade de habilitações parciais. A vigência do serviço também precisa cobrir o mês completo. A categoria e a autorização vêm das bases do usuário; os serviços de demonstração são fictícios.

Treinamento não informado não é convertido em não realizado. A cobertura de treinamento usa todas as unidades inauguradas do recorte, inclusive as encerradas, e pode ser refinada por safra. T02 não exclui treinamentos sem informação de multiplicador do denominador, mas só marca como com multiplicador quando há confirmação. Ações posteriores não alteram a condição histórica em T06. Grupos com menos de cinco observações são sinalizados.

## Comparação mensal e anual

| Medida | Cálculo |
| --- | --- |
| Diferença absoluta | Atual − anterior, disponível na API |
| Variação de quantidades, médias e prazos | (Atual / anterior − 1) × 100 |
| Diferença de taxas | Atual − anterior, em pontos percentuais |
| Comparação mensal | Competência anterior |
| Comparação anual | Mesmo mês do ano anterior |

Base anterior zero, ausência de observações e competência parcial produzem comparação indisponível. A interface exibe `Sem base`. Para Q07, cada comparação usa o mesmo marco M5, M6 ou M12. As comparações históricas usam os dados disponíveis até o corte da carga, não recuperam versões antigas das planilhas. Alterações atuais de ramo e município são aplicadas ao cadastro inteiro; para analisá-las historicamente é necessário estender essas dimensões.

## Cobertura e fechamento

Cobertura = lojas operantes no mês com ambos os domínios completos / lojas para as quais há cobertura esperada no mês. Lojas encerradas antes do início do mês continuam no cadastro e na safra, mas não exigem cobertura de produção após o encerramento.

O fechamento do recorte fica PROVISÓRIO quando há competência parcial, avisos na carga, falta de cobertura ou ausência de vinculação mensal. A tela mostra os numeradores e as lacunas. Uma carga com erros é recusada integralmente; os indicadores continuam usando a publicação anterior, acompanhada do aviso de tentativa bloqueada.
