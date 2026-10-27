const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');

test('workbook editor updates tax fields immediately from principal and selected tag',()=>{
 const fields=Object.fromEntries(['amount','personal_amount','fee','kind','tax_tag','input_tax_goods','input_tax_services','withholding_status','withholding','withholding_mode','net_override'].map(key=>[key,{value:''}]));
 const preview={textContent:''},withholdingPreview={textContent:''},modeField={};
 const context={$:selector=>selector==='#entry'?{elements:fields}:selector==='#entryVatPreview'?preview:selector==='#withholdingPreview'?withholdingPreview:modeField,money:value=>Number(value).toFixed(2)};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('function previewVat(){'),source.indexOf("$('#entry').elements.company.onchange=")),context);
 fields.kind.value='receipt';fields.amount.value='1120';fields.tax_tag.value='PG';
 fields.tax_tag.onchange();
 assert.equal(fields.input_tax_goods.value,'120.00');
 assert.equal(fields.input_tax_services.value,'0.00');
 assert.match(preview.textContent,/base: 1000.00/);
 fields.tax_tag.value='PS';fields.tax_tag.oninput();
 assert.equal(fields.input_tax_goods.value,'0.00');
 assert.equal(fields.input_tax_services.value,'120.00');
 fields.amount.value='2240';context.previewVat();
 assert.equal(fields.input_tax_services.value,'240.00');
 fields.tax_tag.value='EX';fields.tax_tag.onchange();
 assert.equal(fields.input_tax_services.value,'0.00');
 assert.match(preview.textContent,/base: 2240.00/);
 assert.equal(fields.amount.value,'2240','Principal must not be replaced by the VAT-exclusive base');
 fields.kind.value='payment';fields.personal_amount.value='1120';fields.tax_tag.value='PG';fields.fee.value='50';context.previewVat();
 assert.equal(fields.input_tax_goods.value,'120.00');
 fields.tax_tag.value='';fields.tax_tag.onchange();
 assert.equal(fields.input_tax_goods.readOnly,false);
 fields.kind.value='receipt';fields.amount.value='1120';fields.withholding_status.value='yes';fields.withholding.value='20';
 fields.withholding.oninput();
 assert.match(withholdingPreview.textContent,/Net payable before fees: 1100.00/);
 assert.equal(fields.net_override.value,'');
 fields.withholding_mode.value='auto';fields.tax_tag.value='PG';fields.withholding_status.value='yes';fields.withholding_status.onchange();
 assert.equal(fields.withholding.value,'10.00');assert.equal(fields.withholding.readOnly,true);
 fields.tax_tag.value='PS';fields.tax_tag.onchange();assert.equal(fields.withholding.value,'20.00');
 fields.amount.value='2240';context.previewVat();context.previewWithholding(true);assert.equal(fields.withholding.value,'40.00');
 fields.amount.value='1120';fields.withholding_status.value='no';fields.withholding_status.onchange();
 assert.equal(fields.withholding.value,'0');assert.equal(fields.withholding.disabled,true);
 assert.match(withholdingPreview.textContent,/Net payable before fees: 1120.00/);
});

test('workbook paste queues an image for the current editor without saving',()=>{
 const events={},editor={open:true},error={textContent:''};
 let reused=null,prevented=false;
 const context={document:{addEventListener:(name,handler)=>events[name]=handler,querySelector:()=>editor},
   $:selector=>selector==='#editor'?editor:error,readingImage:false,attachment:'',uploadQueue:[],
   nextUpload:reuse=>reused=reuse,status:()=>{}};
 vm.runInNewContext(source.slice(source.indexOf("document.addEventListener('paste'"),source.indexOf("$('#files').onchange=")),context);
 events.paste({clipboardData:{items:[{kind:'file',type:'image/png',getAsFile:()=>({name:'receipt.png'})}]},preventDefault:()=>prevented=true});
 assert.ok(prevented);assert.equal(reused,true);assert.equal(context.uploadQueue.length,1);
 context.attachment='existing.png';events.paste({clipboardData:{items:[{kind:'file',type:'image/png',getAsFile:()=>({})}]},preventDefault:()=>{}});
 assert.match(error.textContent,/already has an image/);assert.equal(context.uploadQueue.length,1);
});

test('workbook OCR result populates the current entry without a manual refill click',async()=>{
 const draft={company:'Example Hardware',date:'2026-10-27',amount:'1120.00',receipt_no:'SI-123',
   tin:'123-456-789',address:'12 Main Street',project:'Warehouse',remarks:'Cement bags',tax_tag:'PG',withholding:'20.00'};
 const fields=Object.fromEntries([...Object.keys(draft),'kind','withholding_status','withholding_mode'].map(key=>[key,{value:''}]));
 fields.kind.value='receipt';
 const elements=new Map();
 const element=selector=>{if(!elements.has(selector))elements.set(selector,{value:'',open:true});return elements.get(selector)};
 element('#entry').elements=fields;
 let parsed=false,vatRefreshed=false;
 class FakeFormData{append(){}}
 const context={$:element,readingImage:false,uploadQueue:[{name:'pasted.png'}],attachment:'',activeModule:null,
   tab:'receipts',status:()=>{},FormData:FakeFormData,window:{Tesseract:true},
   Tesseract:{createWorker:async()=>({recognize:async()=>({data:{text:'OCR invoice text'}}),terminate:async()=>{}})},
   showDuplicates:()=>{},previewVat:()=>vatRefreshed=true,previewWithholding:()=>{},
   api:async(path,body)=>{
     if(path==='/api/upload')return {image:'pasted-test.png'};
     assert.equal(path,'/api/intake/parse');assert.equal(body.text,'OCR invoice text');assert.equal(body.mode,'receipt');parsed=true;
     return {draft,warnings:[],duplicates:[]};
   }
 };
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('async function interpretText('),source.indexOf('function parseText(')),context);
 vm.runInContext(source.slice(source.indexOf('async function nextUpload('),source.indexOf("document.addEventListener('paste'")),context);
 await context.nextUpload(true);
 assert.ok(parsed);assert.ok(vatRefreshed);
 for(const [key,value] of Object.entries(draft))assert.equal(fields[key].value,value,key);
 assert.equal(fields.withholding_status.value,'yes');
 assert.equal(element('#imagePreview').src,'/uploads/pasted-test.png');
 assert.equal(element('#entry button[type="submit"]').disabled,false);
});
