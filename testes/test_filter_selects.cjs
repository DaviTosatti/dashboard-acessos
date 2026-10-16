const test = require("node:test");
const assert = require("node:assert/strict");
const {matching} = require("../static/filter-selects.js");

test("busca de opções ignora caixa e acentos", () => {
  const options = [{value:"SP",label:"São Paulo"},{value:"S",label:"Sul"}];
  assert.deepEqual(matching(options,"sao PAULO"),[options[0]]);
});
test("a busca combina palavras e permite localizar pelo identificador", () => {
  const options = [{value:"R12",label:"Consultor exemplo 1.2"},{value:"R11",label:"Consultor exemplo 1.1"}];
  assert.deepEqual(matching(options,"r12 exemplo"),[options[0]]);
  assert.equal(matching(options,"zz").length,0);
});
test("a pesquisa encontra opções além das primeiras 200 e exclui desabilitadas", () => {
  const options = Array.from({length:600},(_,i)=>({value:String(i),label:`Cliente ${i}`}));
  options.push({value:"secreto",label:"Desabilitada",disabled:true});
  assert.equal(matching(options,"Cliente 599")[0].value,"599");
  assert.equal(matching(options,"Desabilitada").length,0);
  assert.equal(matching(options,"").length,600);
});
