const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('VAT preview and clipboard images use the existing OCR review flow',async()=>{
  const elements=new Map(),events={},calls=[];
  const element=selector=>{
    if(!elements.has(selector))elements.set(selector,{
      value:'',textContent:'',innerHTML:'',hidden:false,open:false,checked:true,
      querySelectorAll:()=>[],addEventListener:()=>{},
      showModal(){this.open=true},close(){this.open=false}
    });
    return elements.get(selector);
  };
  const fields=new Proxy({}, {get:(target,key)=>target[key]??(target[key]={value:''})});
  for(const key of ['amount','personal_amount','fee','tax_tag','company','code','date','method','receipt_no','tin','address','project','remarks','withholding'])fields[key];
  element('#materialForm').elements=fields;
  element('#materialForm').reset=()=>{for(const field of Object.values(fields))field.value=''};
  class FakeFormData{append(){}}
  const context={
    console,URLSearchParams,FormData:FakeFormData,$:element,esc:String,php:value=>Number(value).toFixed(2),
    document:{querySelector:()=>null,addEventListener:(name,handler)=>events[name]=handler},
    localStorage:{getItem:()=>null},load:async()=>{},
    WorkspaceLive:{start:()=>{},synced:()=>{}},
    window:{Tesseract:true,WorkspaceLive:{synced:()=>{}}},
    Tesseract:{createWorker:async()=>({recognize:async()=>({data:{text:'Invoice total 1120'}}),terminate:async()=>{}})},
    fetch:async(path,options)=>{
      calls.push({path,options});
      let value={};
      if(path==='/api/materials/config')value={modes:[],suppliers:[],accounts:[],month:'2026-10'};
      if(path.startsWith('/api/materials/entries'))value={rows:[]};
      if(path==='/api/upload')value={image:'clipboard-test.png'};
      if(path==='/api/materials/parse')value={draft:{amount:1120,company:'Example Hardware',date:'2026-10-27',receipt_no:'SI-123',tin:'123-456-789',address:'12 Main Street',project:'Warehouse',remarks:'Cement bags',tax_tag:'PG',withholding:20},warnings:[],duplicates:[]};
      return {ok:true,json:async()=>value};
    }
  };
  vm.runInNewContext(fs.readFileSync(__dirname+'/static/materials.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  element('#addMaterial').onclick();
  fields.amount.value='1120';fields.tax_tag.value='PG';fields.tax_tag.onchange();
  assert.match(element('#vatPreview').textContent,/base: 1000.00/);
  assert.match(element('#vatPreview').textContent,/goods: 120.00/);
  fields.tax_tag.value='PS';fields.tax_tag.onchange();
  assert.match(element('#vatPreview').textContent,/services: 120.00/);
  fields.tax_tag.value='EX';fields.tax_tag.onchange();
  assert.match(element('#vatPreview').textContent,/base: 1120.00/);
  let prevented=false;
  events.paste({clipboardData:{items:[{kind:'file',type:'image/png',getAsFile:()=>({name:'pasted.png'})}]},preventDefault:()=>prevented=true});
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(prevented);
  assert.ok(calls.some(call=>call.path==='/api/upload'));
  assert.ok(calls.some(call=>call.path==='/api/materials/parse'));
  assert.equal(element('#draftImage').src,'/uploads/clipboard-test.png');
  assert.equal(fields.amount.value,1120);
  for(const [key,value] of Object.entries({company:'Example Hardware',date:'2026-10-27',receipt_no:'SI-123',tin:'123-456-789',address:'12 Main Street',project:'Warehouse',remarks:'Cement bags',tax_tag:'PG',withholding:20}))assert.equal(fields[key].value,value,key);
  assert.equal(fields.withholding_status.value,'yes');
  fields.withholding_mode.value='auto';fields.tax_tag.value='PG';fields.withholding_status.onchange();
  assert.equal(fields.withholding.value,'10.00');
  fields.tax_tag.value='PS';fields.tax_tag.onchange();assert.equal(fields.withholding.value,'20.00');
  fields.withholding_status.value='no';fields.withholding_status.onchange();assert.equal(fields.withholding.value,'0');
  assert.equal(element('#saveMaterial').disabled,false);
  assert.ok(!calls.some(call=>call.path==='/api/record'),'Pasted OCR must remain a draft until reviewed');
});
