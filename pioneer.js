(()=>{'use strict';
const el=id=>document.getElementById(id);
let online=false,busy=false,muted=null;
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
 drawMute();
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
  el('volume').textContent=j.volume??'—';
  el('source').textContent='Input: '+(j.input??'unknown');
  muted=j.mute==='Muted'?true:j.mute==='Not muted'?false:null;
  el('mute').textContent='Mute: '+(j.mute??'unknown');
  if(!silent)notice(j.error||('Last manual check: '+new Date().toLocaleTimeString('en-GB')));
 }catch(e){online=false;muted=null;notice('Receiver check failed: '+e.message)}
 finally{busy=false;el('refresh').disabled=false;setButtons()}
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
   muted=name==='mute_on';drawMute();el('mute').textContent='Mute: '+(muted?'Muted':'Not muted');
  }
  notice('Command sent. Press Check receiver to refresh the displayed level and status.');
 }catch(e){notice('Command failed: '+e.message)}
 finally{busy=false;setButtons()}
}
el('refresh').addEventListener('click',()=>refresh());
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));
el('host').textContent='10.0.0.78 (change via PIONEER_HOST if wired IP differs)';
})();