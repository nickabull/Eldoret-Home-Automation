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
})();