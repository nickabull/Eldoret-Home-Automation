(()=> {
  const isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent);
  document.documentElement.classList.toggle("ios-device",isIOS);
  if("serviceWorker" in navigator && location.protocol==="https:"){
    navigator.serviceWorker.register("/sw.js").catch(()=>{});
  }
  const tabs=document.querySelector(".tabs");
  if(tabs && !document.querySelector(".mobile-dock")){
    const wanted=[
      ["index.html","Home","⌂"],
      ["lights.html","Lights","◉"],
      ["sky.html","Sky","▣"],
      ["av.html","AV","▶"],
      ["network.html","Network","⌁"]
    ];
    const dock=document.createElement("nav");
    dock.className="mobile-dock";
    dock.setAttribute("aria-label","Primary");
    const path=(location.pathname.split("/").pop()||"index.html");
    dock.innerHTML=wanted.map(([href,label,icon])=>'<a href="'+href+'" class="'+(path===href?"active":"")+'"><span>'+icon+'</span><small>'+label+'</small></a>').join("");
    document.body.appendChild(dock);
  }
})();

// One shared power control for every Sky Q quick remote.
(()=>{
 const controls=document.querySelector('.sport-now-controls');
 if(!controls||controls.querySelector('[data-sky-key="power"]'))return;
 const button=document.createElement('button');
 button.type='button';button.className='sky-power-switch';button.dataset.skyKey='power';
 button.setAttribute('aria-label','Sky Q power: on or standby');
 button.title='Toggle Sky Q between on and standby';
 button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v9M6.3 5.8a8 8 0 1 0 11.4 0"/></svg><span>On / Standby</span>';
 controls.prepend(button);
 const live=location.protocol==='http:'||location.hostname.endsWith('.ts.net');
 if(!live){button.disabled=true;button.title='Open Eldoret through the home connector to control Sky Q';}
 async function sendPower(){
  if(button.disabled)return;
  button.disabled=true;button.classList.add('sending');
  const label=button.querySelector('span');label.textContent='Sending…';
  try{
   const res=await fetch('/api/sky/key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'power'})});
   if(!res.ok)throw new Error('Power command failed');
   label.textContent='Command sent';
   if(typeof refreshNow==='function')setTimeout(refreshNow,1700);
  }catch(error){button.classList.add('failed');label.textContent='Try again';}
  finally{setTimeout(()=>{button.disabled=false;button.classList.remove('sending','failed');label.textContent='On / Standby';},2200);}
 }
 button.addEventListener('click',()=>{
  if(!live||button.disabled)return;
  if(typeof stageEldoretAction==='function'){stageEldoretAction('Sky Q · On / Standby',sendPower,button);return;}
  const old=document.querySelector('#eldoretPowerConfirm');if(old)old.remove();
  const box=document.createElement('div');box.id='eldoretPowerConfirm';box.className='eldoret-confirm';
  box.innerHTML='<span>Sky Q · On / Standby</span><button type="button">CONFIRM</button>';
  button.classList.add('eldoret-pending');
  const clear=()=>{box.remove();button.classList.remove('eldoret-pending');};
  const timer=setTimeout(clear,10000);
  box.querySelector('button').onclick=()=>{clearTimeout(timer);clear();sendPower();};
  document.body.appendChild(box);
 });
})();


(()=>{
 const tabs=document.querySelector('.tabs');if(!tabs)return;
 const existing=[...tabs.querySelectorAll('a')].find(a=>a.getAttribute('href')==='office.html');
 if(existing){existing.textContent='Epson';existing.href='office.html#epson';}
 else{const link=document.createElement('a');link.href='office.html#epson';link.textContent='Epson';tabs.appendChild(link);}
})();
