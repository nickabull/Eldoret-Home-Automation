(()=>{'use strict';
const el=id=>document.getElementById(id);
const knob=el('volumeKnob');
let online=false,busy=false,muted=null,volumeCode=null,drag=null;
function notice(t){el('message').textContent=t}
function drawMute(){
 const b=el('muteButton');
 b.classList.toggle('muted-active',muted===true);
 b.setAttribute('aria-pressed',muted===true?'true':'false');
 b.textContent=muted===true?'Muted · tap to unmute':'Mute';
 b.disabled=busy||!online||muted===null;
}
function setButtons(){
 document.querySelectorAll('[data-action]').forEach(b=>b.disabled=busy||!online);
 const enabled=online&&!busy&&volumeCode!==null;
 knob.classList.toggle('knob-disabled',!enabled);
 knob.setAttribute('aria-disabled',String(!enabled));
 drawMute();
}
function setVolume(value){
 volumeCode=(value!==null&&value!==undefined&&/^\d+$/.test(String(value)))?String(value):null;
 el('volume').textContent=volumeCode??'—';
 knob.setAttribute('aria-label','Pioneer volume '+(volumeCode??'unknown')+'. Drag clockwise or anticlockwise one step, or use arrow keys.');
}
async function refresh(silent=false){
 if(busy)return;
 busy=true;el('refresh').disabled=true;setButtons();
 if(!silent)notice('Contacting Pioneer once…');
 try{
  const r=await fetch('/api/pioneer/status',{cache:'no-store'});
  if(!r.ok)throw Error('HTTP '+r.status);
  const j=await r.json();
  online=!!j.connected;
  el('state').textContent=online?'Responding':'Unavailable';
  el('dot').className='dot'+(online?' ok':'');
  el('host').textContent=j.host||'—';
  el('power').textContent='Power: '+(j.power??'unknown');
  setVolume(j.volume);
  el('source').textContent='Input: '+(j.input??'unknown');
  muted=j.mute==='Muted'?true:j.mute==='Not muted'?false:null;
  el('mute').textContent='Mute: '+(j.mute??'unknown');
  const steps=Array.isArray(j.query_results)?j.query_results.map(x=>x.field+': '+x.status+(x.error?' ('+x.error+')':'')+(Number.isFinite(x.elapsed_ms)?' · '+x.elapsed_ms+'ms':'')).join(' · '):'';
  el('queryDiagnostics').textContent=steps?('Individual reads: '+steps):'No per-query diagnostics supplied';
  if(!silent)notice(j.error||('Volume and status read from Pioneer at '+new Date().toLocaleTimeString('en-GB')));
 }catch(e){
  online=false;muted=null;setVolume(null);
  notice('Receiver check failed: '+e.message);
 }finally{busy=false;el('refresh').disabled=false;setButtons()}
}
async function action(requested){
 if(busy||!online)return;
 const name=requested==='mute_toggle'?(muted===true?'mute_off':muted===false?'mute_on':null):requested;
 if(!name){notice('Check receiver first to identify mute state.');return;}
 busy=true;setButtons();notice('Sending one command…');
 try{
  const r=await fetch('/api/pioneer/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:name})});
  const j=await r.json();
  if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
  if(requested==='mute_toggle'){
   muted=name==='mute_on';
   el('mute').textContent='Mute: '+(muted?'Muted':'Not muted');
  }
  notice('Command sent. Reading actual receiver status…');
 }catch(e){notice('Command failed: '+e.message);return}
 finally{busy=false;setButtons()}
 // One read initiated by the user's completed action. No continuous polling.
 await refresh(true);
}
function angle(e){
 const r=knob.getBoundingClientRect(),x=e.clientX-r.left-r.width/2,y=e.clientY-r.top-r.height/2;
 return Math.atan2(x,-y)*180/Math.PI;
}
knob.addEventListener('pointerdown',e=>{
 if(busy||!online||volumeCode===null||e.button>0)return;
 drag={id:e.pointerId,angle:angle(e),last:angle(e),delta:0};
 knob.setPointerCapture(e.pointerId);
});
knob.addEventListener('pointermove',e=>{
 if(!drag||e.pointerId!==drag.id)return;
 const a=angle(e);
 let d=a-drag.last;
 if(d>180)d-=360;
 if(d< -180)d+=360;
 drag.delta+=d;
 drag.last=a;
 const twist=Math.max(-22,Math.min(22,drag.delta));
 knob.style.setProperty('--knob-twist',twist+'deg');
});
knob.addEventListener('pointerup',e=>{
 if(!drag||e.pointerId!==drag.id)return;
 const d=drag.delta;
 drag=null;
 knob.style.setProperty('--knob-twist','0deg');
 if(Math.abs(d)>=12)action(d>0?'volume_up':'volume_down');
});
knob.addEventListener('pointercancel',()=>{drag=null;knob.style.setProperty('--knob-twist','0deg')});
knob.addEventListener('keydown',e=>{
 if(busy||!online||volumeCode===null)return;
 if(e.key==='ArrowUp'||e.key==='ArrowRight'){e.preventDefault();action('volume_up')}
 if(e.key==='ArrowDown'||e.key==='ArrowLeft'){e.preventDefault();action('volume_down')}
});
el('refresh').addEventListener('click',()=>refresh());
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));
el('host').textContent='Configured in Bulldog (check receiver to confirm)';

async function diagnoseConnection(){
 const b=el('connectionRefresh'),root=el('connectionResult');
 b.disabled=true;root.replaceChildren();
 try{
  const response=await fetch('/api/pioneer/connection',{cache:'no-store'});
  if(!response.ok)throw Error('HTTP '+response.status);
  const result=await response.json();
  const rows=[
    ['Network ping',result.ping?.last_probe_reachable===true?'Responding':result.ping?.last_probe_reachable===false?'Not responding':'Unknown'],
    ['Pioneer control (TCP 8102)',result.control_port_open?'Accepting connections':'Unavailable'+(result.control_port_open_error?' · '+result.control_port_open_error:'')],
    ['Web interface (TCP 80)',result.web_port_open?'Port open':'Port closed'],
    ['IP address',result.host||'—'],
    ['Checked',result.checked_at?new Date(result.checked_at).toLocaleString('en-GB'):'—']
  ];
  for(const [label,value] of rows){
   const item=document.createElement('div');item.className='stability-event'+(value==='Accepting connections'?' up':'');
   const n=document.createElement('span');n.textContent=label;const v=document.createElement('b');v.textContent=value;
   item.append(n,v);root.append(item);
  }
  const note=document.createElement('p');note.className='mini';note.textContent=result.diagnosis||'';
  root.append(note);el('host').textContent=result.host||'Unknown';
  if(result.control_port_open){
   notice('Pioneer control port is responding. Press Retry receiver status to read power, volume and mute.');
  }else{
   notice('Control port is not responding. Network ping alone cannot confirm the amplifier is ready.');
  }
 }catch(e){const p=document.createElement('p');p.className='mini';p.textContent='Connection test failed: '+e.message;root.append(p)}
 finally{b.disabled=false}
}
el('connectionRefresh').addEventListener('click',diagnoseConnection);
el('receiverRetry').addEventListener('click',()=>refresh());


async function showMonitor(){
 const button=el('monitorRefresh');
 button.disabled=true;
 const root=el('monitorEvents');
 root.replaceChildren();
 try{
  const r=await fetch('/api/pioneer/monitor',{cache:'no-store'});
  if(!r.ok)throw Error('HTTP '+r.status);
  const j=await r.json(),events=(j.events||[]).slice().reverse(),live=j.live||{};
  const fmt=t=>t?new Date(t).toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
  el('monitorSummary').textContent='Latest: '+(live.state||'unknown')+' · '+fmt(live.observed_at)+' · '+j.outages_observed+' network-loss events logged (last 200 events examined)';
  if(!events.length){const p=document.createElement('p');p.className='mini';p.textContent='No changes recorded yet. Logging begins with the updated connector.';root.append(p);}
  for(const e of events.slice(0,12)){
   const row=document.createElement('div');row.className='stability-event '+(e.state==='reachable'?'up':'');
   const time=document.createElement('span');time.textContent=fmt(e.at);
   const state=document.createElement('b');state.textContent=e.state==='reachable'?'Connected':'Connection lost';
   row.append(time,state);root.append(row);
  }
 }catch(e){const p=document.createElement('p');p.className='mini';p.textContent='Monitor unavailable: '+e.message;root.append(p)}
 finally{button.disabled=false}
}
el('monitorRefresh').addEventListener('click',showMonitor);
showMonitor();

})();