/* Separate supplier choices by explicit classification or legal-name evidence. */
(function(){
  const form=document.querySelector('#entry')||document.querySelector('#materialForm');
  if(!form)return;
  const f=form.elements;
  let suppliers=[],history=[];
  function typeOf(s){
    const saved=new Set(history.filter(r=>r.company===s.name&&r.payee_type).map(r=>r.payee_type));
    if(saved.size===1)return [...saved][0];
    if(s.proprietor||/\bprop(?:rietor)?\.?\s*$/i.test(s.name))return 'proprietor';
    if(/\b(?:corp(?:oration)?|inc(?:orporated)?)\b/i.test(s.name))return 'corporation';
    return '';
  }
  function refresh(row=null){
    const current=row?.company||f.company.value;
    const supplier=suppliers.find(s=>s.name===current);
    if(row?.payee_type)f.payee_type.value=row.payee_type;
    else if(supplier&&!f.payee_type.value)f.payee_type.value=typeOf(supplier);
    const type=f.payee_type.value;
    f.company.replaceChildren(new Option(type?'Select '+type+' payee':'Select an unclassified payee',''));
    for(const s of suppliers.filter(s=>typeOf(s)===type))f.company.add(new Option(s.name,s.name));
    // Preserve existing records and extracted names; do not silently rewrite them.
    if(current&&!Array.from(f.company.options).some(o=>o.value===current))f.company.add(new Option(current+' (current entry)',current));
    f.company.value=current||'';
    f.proprietor.closest('label').hidden=type!=='proprietor';
    f.business_name.closest('label').hidden=type==='corporation';
  }
  f.payee_type.addEventListener('change',()=>{
    f.company.value='';f.proprietor.value='';f.business_name.value='';f.tin.value='';f.address.value='';refresh();
  });
  f.company.addEventListener('change',()=>{
    const supplier=suppliers.find(s=>s.name===f.company.value);
    if(!supplier)return;
    f.proprietor.value=supplier.proprietor||'';
    f.business_name.value=supplier.business_name||'';
    f.tin.value=supplier.tin||'';f.address.value=supplier.address||'';
  });
  window.PayeeChoices={refresh};
  fetch('/api/state').then(r=>{if(!r.ok)throw Error('Could not load payees');return r.json()}).then(state=>{
    suppliers=state.suppliers;history=state.records;refresh();
  }).catch(error=>{f.company.add(new Option(error.message,''))});
})();
