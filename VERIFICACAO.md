# Verificação desta entrega

Data: 16/10/2026. Regra de indicadores: `expresso-1.0`.

- 90 testes automatizados em Python do importador, regras de padronização, consultas, APIs, autenticação e prospecção passaram.
- A prospecção foi testada com cenários independentes dos exemplos: safra versus movimentação, aprovação em D dias, contratos com várias lojas, cancelamento posterior, M0, cobertura ausente, sequência de zeros, reativação, idade elegível, treinamento posterior, vigência de responsável, suporte sem cadastro, habilitação parcial, estornos, CSV e preservação da publicação após erro.
- Três testes JavaScript cobrem a busca sem acentos, busca por identificador e opções além das primeiras 200.
- JavaScript dos quatro módulos passou por verificação de sintaxe com `node --check`.
- Testes adicionais verificam intervalos inclusivos, comparações com a mesma duração, contratos distintos, produção com troca de responsável, executor separado da carteira, consultor sem atividade, paginação e exportação integral de atividades.
- HTML foi conferido quanto a IDs duplicados, destinos de abas, referências de elementos e recursos locais.
- O pacote foi extraído em pasta com espaços e sua importação foi executada a partir de outro diretório. Os endpoints dos dois módulos foram exercitados com a aplicação WSGI.
- Foram mantidos os testes da correção de URI do SQLite para caminhos do Windows.

Não foi realizada validação visual com navegador nesta execução, nem execução dos arquivos BAT ou acesso ao compartilhamento Windows da empresa. O ambiente de verificação é Linux. As bases e os cabeçalhos reais ainda precisam ser mapeados no catálogo da prospecção; os exemplos incluídos são inteiramente fictícios.

Para repetir os testes, na pasta do projeto:

```bat
python -m unittest discover -s testes -v
node --test testes/test_filter_selects.cjs
```

Node é opcional e serve apenas para repetir os testes JavaScript. O dashboard em uso não exige Node.
