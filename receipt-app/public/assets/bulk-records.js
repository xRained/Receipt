/* Entry-only selection; master lists never receive selection checkboxes. */
(()=>{
 const toolbar=document.createElement('div');toolbar.className='entryActions';toolbar.style.padding='16px';
 toolbar.innerHTML='<label><input type="checkbox" id="selectVisibleEntries"> Select all shown entries</label><button type="button" id="deleteSelectedEntries" disabled>Delete selected entries</button><button type="button" class="secondary" id="deleteAllEntries">Delete all entries (all months)</button><span id="entrySelectionCount" role="status"></span>';
 const host=document.querySelector('#content')||document.querySelector('#materialLedger');if(!host)return;
 host.before(toolbar);
 const boxes=()=>Array.from(host.querySelectorAll('[data-select-entry]'));
 const all=toolbar.querySelector('#selectVisibleEntries'),remove=toolbar.querySelector('#deleteSelectedEntries'),count=toolbar.querySelector('#entrySelectionCount');
 function update(){const list=boxes(),selected=list.filter(b=>b.checked).length;all.checked=!!list.length&&selected===list.length;all.indeterminate=selected>0&&selected<list.length;remove.disabled=!selected;count.textContent=selected+' selected';}
 function decorate(){
  host.querySelectorAll('[data-delete-record]').forEach(button=>{
   if(button.parentElement.querySelector('[data-select-entry]'))return;
   const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.selectEntry=button.dataset.deleteRecord;checkbox.setAttribute('aria-label','Select entry');checkbox.addEventListener('change',update);button.parentElement.prepend(checkbox);
  });update();
 }
 all.onchange=()=>{boxes().forEach(b=>b.checked=all.checked);update()};
 async function deleteEntries(everything){
  const ids=boxes().filter(b=>b.checked).map(b=>b.dataset.selectEntry);
  if(!everything&&!ids.length)return;
  if(!confirm(everything?'Delete ALL payment and receipt entries across ALL months? Suppliers, COA, settings, templates and automation stay. A database backup will be saved first.':'Delete '+ids.length+' selected entries and their matching links? Suppliers and COA stay. A database backup will be saved first.'))return;
  remove.disabled=true;toolbar.querySelector('#deleteAllEntries').disabled=true;
  try{const response=await fetch('/api/records/delete-selected',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(everything?{all_entries:true}:{ids})});const result=await response.json();if(!response.ok)throw Error(result.error||'Delete failed');location.reload()}
  catch(error){alert(error.message);toolbar.querySelector('#deleteAllEntries').disabled=false;update()}
 }
 remove.onclick=()=>deleteEntries(false);toolbar.querySelector('#deleteAllEntries').onclick=()=>deleteEntries(true);
 new MutationObserver(decorate).observe(host,{childList:true,subtree:true});decorate();
})();
