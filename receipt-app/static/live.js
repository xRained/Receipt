/* Refresh changed records without reloading pages or interrupting a draft. */
window.WorkspaceLive=(()=>{
 let refresh=null,busy=()=>false,revision=null,pending=false,running=false,checking=false,ownWrite=false,timer=null;
 const rawFetch=window.fetch.bind(window);
 const channel=window.BroadcastChannel?new BroadcastChannel('jolyn-workspace'):null;
 function label(text,error=false){const el=document.querySelector('#liveStatus');if(el){el.textContent=text;el.classList.toggle('offline',error)}}
 async function readRevision(){const r=await rawFetch('/api/changes',{cache:'no-store'});if(!r.ok)throw Error('Connection unavailable');return (await r.json()).revision}
 async function apply(){if(!refresh||running||busy()||document.hidden)return;running=true;pending=false;label('Updating records?');try{await refresh();label('Up to date ? '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}))}catch(e){pending=true;label('Refresh failed ? retrying',true)}finally{running=false}}
 async function check(force=false){if(checking||document.hidden)return;checking=true;try{const next=await readRevision();if(revision!==null&&next!==revision)pending=true;revision=next;if(force)pending=true;if(pending)await apply();else label('Live updates on')}catch(e){label('Connection lost ? retrying',true)}finally{checking=false}}
 window.fetch=async(input,options={})=>{const r=await rawFetch(input,options);const method=String(options.method||(input instanceof Request?input.method:'GET')).toUpperCase();if(r.ok&&!['GET','HEAD','OPTIONS'].includes(method)){ownWrite=true;pending=true;channel?.postMessage('changed');setTimeout(()=>check(),500);readRevision().then(v=>{revision=v}).catch(()=>{}).finally(()=>{ownWrite=false})}return r};
 channel?.addEventListener('message',()=>{pending=true;check()});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)check()});window.addEventListener('focus',()=>check());
 return {synced(){pending=false;label('Up to date ? '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}))},start(callback,isBusy){if(timer)clearInterval(timer);refresh=callback;busy=isBusy||busy;check();timer=setInterval(()=>{if(!ownWrite)check()},4000);const button=document.querySelector('#refreshNow');if(button)button.onclick=()=>check(true)}};
})();
