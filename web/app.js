'use strict';
let state = null, selectedId = null, busy = false;
const $ = id => document.getElementById(id);
const time = ts => new Date(ts * 1000).toISOString().slice(11,19);
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if(cls)n.className=cls;return n; };
function findings(frame) {
  const out=[];
  if(frame.services.some(s=>s.id==='db'&&s.status==='down'))out.push('Database is down. The API, gateway, and archive depend on it in this demo. Check database availability first.');
  [['cpu_pct','CPU'],['memory_pct','Memory'],['disk_pct','Disk']].forEach(([k,n])=>{if(frame.metrics[k]!==null&&frame.metrics[k]>=90)out.push(`${n} exceeds 90%. Inspect the workload or capacity before making changes.`);});
  return out.length?out:['No configured threshold or dependency rule is triggered in this frame.'];
}
function render(){
 const frames=state.frames;
 if(!frames.length)return;
 let index=selectedId===null?frames.length-1:frames.findIndex(f=>f.id===selectedId);
 if(index<0){ index=0;selectedId=frames[0].id; }
 const f=frames[index],live=selectedId===null;
 $('mode').textContent=f.mode==='demo'?'DEMO UNIVERSE':'LOCAL HOST / READ ONLY';
 $('health').textContent=f.services.some(s=>s.status!=='healthy')||Object.entries(f.metrics).some(([k,v])=>k.endsWith('_pct')&&v>=90)?'ATTENTION REQUIRED':'MISSION NOMINAL';
 $('view').textContent=live?'LIVE FEED / 2s':'REPLAY / FRAME '+f.id;
 $('metrics').replaceChildren();
 [['cpu_pct','CPU LOAD','%'],['memory_pct','MEMORY','%'],['disk_pct','DISK USED','%'],['network_rx_kbps','NETWORK RX','KiB/s']].forEach(([k,label,unit])=>{
  const v=f.metrics[k],card=el('div',undefined,'metric'+(v>=90&&k!=='network_rx_kbps'?' warn':''));
  card.append(el('label',label));const number=el('strong',v===null?'—':v.toFixed(1));number.append(el('small',unit));card.append(number);
  const meter=el('div',undefined,'meter'),fill=el('b');fill.style.width=(v===null?0:Math.max(0,Math.min(100,k==='network_rx_kbps'?v/4:v)))+'%';meter.append(fill);card.append(meter);$('metrics').append(card);
 });
 $('nodes').replaceChildren();
 const names=Object.fromEntries(f.services.map(s=>[s.id,s.name]));
 f.services.forEach(s=>{const node=el('div',undefined,'node '+s.status);node.title=s.reason;node.append(el('small',s.kind),el('strong',s.name),el('p',s.status.toUpperCase()+' / '+s.latency_ms+' ms'),el('em',s.depends.length?'→ '+s.depends.map(id=>names[id]).join(', '):'● No upstream dependency'));$('nodes').append(node);});
 if(!f.services.length)$('nodes').append(el('p','Host telemetry only. Service discovery is not enabled.','caption'));
 $('topology-note').textContent=f.mode==='demo'?'Fictional services · arrows point to dependencies':f.notes.join(' ');
 document.querySelectorAll('[data-scenario]').forEach(b=>b.disabled=state.mode!=='demo'||busy||!live);
 $('chaos-note').textContent=state.mode!=='demo'?'Host mode has no service controls.':live?'Demo controls never change real services.':'Return to live to run another simulation.';
 $('scrubber').max=frames.length-1;$('scrubber').value=index;
 $('time-start').textContent=time(frames[0].ts);$('time-end').textContent=time(frames.at(-1).ts);
 $('selected-time').textContent=time(f.ts)+' UTC / '+f.scenario;
 $('report').href='/api/report?frame='+f.id;
 $('chart').replaceChildren();
 // Downsample to at most 120 bars, preserving the selected frame as its own bar.
 const step=Math.max(1,Math.ceil(frames.length/119));const indices=new Set([index]);for(let i=0;i<frames.length;i+=step)indices.add(i);
 [...indices].sort((a,b)=>a-b).forEach(i=>{const bar=el('div',undefined,'bar'+(i===index?' selected':''));bar.style.height=Math.max(2,frames[i].metrics.cpu_pct||0)+'%';bar.title=time(frames[i].ts)+' CPU '+(frames[i].metrics.cpu_pct??'unavailable');$('chart').append(bar);});
 $('findings').replaceChildren(...findings(f).map(s=>el('p',s)));
 $('events').replaceChildren(...state.events.filter(e=>e.frame_id===null?e.ts<=f.ts:e.frame_id<=f.id).slice(0,15).map(e=>{const row=el('div',undefined,'event');row.append(el('time',time(e.ts)),el('span',e.message));return row;}));
 $('scope').textContent=state.mode==='demo'?'SIMULATED TELEMETRY · NO EXTERNAL REQUESTS':'LOCAL /PROC + DISK · NO SERVICE CONTROL';
}
async function refresh(){
 try{const r=await fetch('/api/state');if(!r.ok)throw Error('Telemetry request failed');state=await r.json();$('connection').textContent='TELEMETRY ONLINE';$('error').hidden=true;render();}
 catch(e){$('connection').textContent='OFFLINE';$('error').textContent=e.message+' — retrying in 2 seconds.';$('error').hidden=false;}
}
document.querySelectorAll('[data-scenario]').forEach(b=>b.addEventListener('click',async()=>{
 if(!state||busy)return;busy=true;render();
 try{const r=await fetch('/api/scenario',{method:'POST',headers:{'Content-Type':'application/json','X-Mission-Token':state.token},body:JSON.stringify({scenario:b.dataset.scenario})});if(!r.ok)throw Error('Scenario change failed');selectedId=null;await refresh();}
 catch(e){$('error').textContent=e.message;$('error').hidden=false;}
 finally{busy=false;render();}
}));
$('scrubber').addEventListener('input',e=>{if(state){selectedId=state.frames[Number(e.target.value)]?.id??null;render();}});
$('live').addEventListener('click',()=>{selectedId=null;if(state)render();});
setInterval(()=>{$('clock').textContent=new Date().toISOString().slice(11,19)+' UTC';},1000);
(async function poll(){await refresh();setTimeout(poll,2000);})();
