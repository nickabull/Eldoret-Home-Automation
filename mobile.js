(()=> {
  const isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent);
  document.documentElement.classList.toggle("ios-device",isIOS);
  if("serviceWorker" in navigator && location.protocol==="https:"){
    navigator.serviceWorker.register("/sw.js").catch(()=>{});
  }
  const tabs=document.querySelector(".tabs");
  if(tabs && !document.body.classList.contains("eldoret-shell") && !document.querySelector(".mobile-dock")){
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

// The shared mobile shell also covers older detailed pages without a kiosk script.
(()=>{
 if(document.querySelector('script[src^="kiosk.js"]')||location.pathname==='/'||location.pathname.endsWith('/index.html'))return;
 const script=document.createElement('script');script.src='kiosk.js?v=2';document.body.appendChild(script);
})();

// One shared page frame across Eldoret. Landscape dashboards never scroll.
(()=>{
 if(!document.body.classList.contains('eldoret-shell'))return;
 const wide=matchMedia('(min-aspect-ratio:4/3) and (min-width:760px)');
 const main=document.querySelector('body>main');if(!main)return;
 const content=document.createElement('div');content.className='eldoret-content';
 while(main.firstChild)content.append(main.firstChild);main.append(content);
 function clock(){const now=new Date();const t=document.getElementById('shellTime'),d=document.getElementById('shellDate');if(t)t.textContent=now.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/London'});if(d)d.textContent=now.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',timeZone:'Europe/London'});}
 clock();setInterval(clock,10000);
 // Keep large inventories accessible using buttons, rather than hidden scroll areas.
 const pagers=new Map();
 function inventoryPages(){
  for(const grid of content.querySelectorAll('#deviceGrid,#rooms,#recordingsGrid,#guideGrid,#skyAppsGrid')){
   let state=pagers.get(grid);
   if(!state){
    const bar=document.createElement('nav');bar.className='shell-pager';bar.setAttribute('aria-label','Inventory pages');
    const prev=document.createElement('button'),label=document.createElement('span'),next=document.createElement('button');prev.type=next.type='button';prev.textContent='‹';next.textContent='›';prev.setAttribute('aria-label','Previous page');next.setAttribute('aria-label','Next page');label.setAttribute('aria-live','polite');bar.append(prev,label,next);grid.after(bar);
    state={page:0,bar,prev,label,next};pagers.set(grid,state);
    prev.onclick=()=>{state.page--;inventoryPages();schedule();};next.onclick=()=>{state.page++;inventoryPages();schedule();};
   }
   const items=[...grid.children],size=wide.matches?(grid.id==='recordingsGrid'||grid.id==='guideGrid'?14:8):items.length||1,pages=Math.max(1,Math.ceil(items.length/size));state.page=Math.max(0,Math.min(state.page,pages-1));
   items.forEach((item,i)=>{const hide=wide.matches&&(i<state.page*size||i>=(state.page+1)*size);if(item.hasAttribute('data-shell-hidden')!==hide)item.toggleAttribute('data-shell-hidden',hide);});
   if(state.bar.hidden!==(pages<=1))state.bar.hidden=pages<=1;const text=(state.page+1)+' / '+pages;if(state.label.textContent!==text)state.label.textContent=text;state.prev.disabled=state.page===0;state.next.disabled=state.page===pages-1;
  }
 }
 // Network telemetry and its longer device inventory are separate, stable views.
 const devices=content.querySelector('.net-devices');
 if(devices){
  const overview=document.createElement('div'),tabs=document.createElement('nav');tabs.className='shell-subnav';tabs.setAttribute('aria-label','Network views');
  while(content.firstChild&&content.firstChild!==devices)overview.append(content.firstChild);
  content.prepend(tabs,overview);
  [['Overview',overview],['Devices',devices]].forEach(([name,panel],index)=>{const b=document.createElement('a');b.href=index?'#devices':'#overview';b.textContent=name;tabs.append(b);b.onclick=e=>{e.preventDefault();[overview,devices].forEach(p=>p.hidden=p!==panel);tabs.querySelectorAll('a').forEach(a=>a.classList.toggle('active',a===b));schedule();};if(!index)b.className='active';});devices.hidden=true;
 }
 // Keep maintenance notes available without pushing room controls off the canvas.
 const notes=content.querySelector('.health');
 if(notes){const toggle=document.createElement('button');toggle.className='dashboard-refresh';toggle.type='button';toggle.textContent='Maintenance notes';notes.before(toggle);notes.hidden=true;toggle.onclick=()=>{notes.hidden=!notes.hidden;toggle.textContent=notes.hidden?'Maintenance notes':'Hide maintenance notes';schedule();};}
 let queued=false;
 function fit(){
  queued=false;
  document.documentElement.style.setProperty('--eldoret-screen-scale',Math.min(innerWidth/1600,innerHeight/900));
  inventoryPages();
  if(!wide.matches){content.style.zoom='';content.style.width='';return;}
  content.style.zoom='1';content.style.width='100%';
  const available=main.clientHeight-34;
  let scale=Math.min(1,available/Math.max(1,content.scrollHeight));
  // Allow reflow once at the fitted width; retain all controls in the viewport.
  for(let i=0;i<2;i++){content.style.zoom=String(scale);content.style.width=((main.clientWidth-72)/scale)+'px';const height=content.getBoundingClientRect().height/(Math.min(innerWidth/1600,innerHeight/900)||1);if(height>available+1)scale*=available/height;}
  content.style.zoom=String(scale);content.style.width=((main.clientWidth-72)/scale)+'px';
  document.body.dataset.shellFit=scale.toFixed(3);
 }
 function schedule(){if(!queued){queued=true;requestAnimationFrame(fit);}}
 new MutationObserver(schedule).observe(content,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['hidden','class','src']});
 window.addEventListener('resize',schedule);wide.addEventListener('change',schedule);content.addEventListener('load',schedule,true);content.addEventListener('click',()=>setTimeout(schedule,30));document.fonts?.ready.then(schedule);schedule();
})();
