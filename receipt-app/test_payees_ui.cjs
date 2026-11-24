const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
test('payee dropdown separates legal types and preserves existing entries',async()=>{
 const field=()=>({value:'',listeners:{},label:{hidden:false},addEventListener(n,f){this.listeners[n]=f},closest(){return this.label}});
 const f=Object.fromEntries(['company','payee_type','proprietor','business_name','tin','address'].map(k=>[k,field()]));
 f.company.options=[];f.company.add=function(o){this.options.push(o)};f.company.replaceChildren=function(o){this.options=[o]};
 const context={document:{querySelector:()=>({elements:f})},window:{},Option:function(text,value){this.text=text;this.value=value},
 fetch:async()=>({ok:true,json:async()=>({suppliers:[{name:'Owner - Prop.',proprietor:'Owner'},{name:'Example Corp.'},{name:'Unknown Store'}],records:[]})})};
 vm.runInNewContext(fs.readFileSync(__dirname+'/static/payees.js','utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 f.payee_type.value='proprietor';f.payee_type.listeners.change();
 assert.deepEqual(f.company.options.map(o=>o.value),['','Owner - Prop.']);
 assert.equal(f.proprietor.label.hidden,false);
 f.payee_type.value='corporation';f.payee_type.listeners.change();
 assert.deepEqual(f.company.options.map(o=>o.value),['','Example Corp.']);
 assert.equal(f.proprietor.label.hidden,true);
 f.payee_type.value='';f.payee_type.listeners.change();
 assert.deepEqual(f.company.options.map(o=>o.value),['','Unknown Store']);
 context.window.PayeeChoices.refresh({company:'Legacy supplier',payee_type:'proprietor'});
 assert.equal(f.company.value,'Legacy supplier');
});
