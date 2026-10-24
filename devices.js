const deviceGroups={"network":[["Main Router","10.0.0.1","DrayTek","Router","🌐"],["House Hue Bridge","10.0.0.2","Philips Hue","Bridge","💡"],["Utility Hue Bridge","10.0.0.4","Philips Hue","Bridge","💡"],["Old Raspberry Pi","10.0.0.5","Raspberry Pi","Legacy host","🥧"],["UniFi Office/Kitchen","10.0.0.6","Ubiquiti","Access point","📶"],["UniFi Utility","10.0.0.7","Ubiquiti","Access point","📶"],["UniFi Garden","10.0.0.8","Ubiquiti","Access point","📶"],["UniFi Landing","10.0.0.9","Ubiquiti","Access point","📶"],["BBC Aruba","10.0.0.20","HPE Aruba","Network device","📡"],["Eldoret Chromebook","10.0.0.27","Intel / ChromeOS","Current host","🫏"]],"av":[["Sky Q","10.0.0.18","Sky","Set-top box","📺"],["LG webOS TV","10.0.0.33","LG Electronics","webOS TV","📺"],["LG device","10.0.0.43","LG Innotek","Needs identification","📺"],["LG device","10.0.0.47","LG Electronics","Needs identification","📺"],
 ["LG webOS TV","10.0.0.51","LG Electronics","Newly discovered · room to identify","📺"],["Android-2","10.0.0.25","Allwinner","Android device","▶️"],["Android-3","10.0.0.31","Amazon","Android / Fire device","▶️"],["PlayStation","10.0.0.48","Sony","Games console","🎮"]],"appliances":[["Extractor Hood","10.0.0.12","BSH / Home Connect","Kitchen","🍳"],["Hob","10.0.0.13","BSH / Home Connect","Kitchen","🔥"],["Dishwasher","10.0.0.14","BSH / Home Connect","Kitchen","🫧"],["Left Oven","10.0.0.16","BSH / Home Connect","Kitchen","♨️"],["Right Oven","10.0.0.17","BSH / Home Connect","Kitchen","♨️"],["VELUX Gateway","10.0.0.22","Netatmo / VELUX","Windows & blinds","🪟"],["Tuya device","10.0.0.10","Tuya","Needs identification","🔌"],["Smart device","10.0.0.19","Espressif","Needs identification","🔌"],["Smart device","10.0.0.21","Texas Instruments","Needs identification","🔌"]],"office":[["Epson printer","10.0.0.3","Epson","Printer","🖨️"],["MacBook Pro","10.0.0.26","Apple","Computer","💻"],["Apple device","10.0.0.23","Apple","Needs identification","🍎"],["Apple device","10.0.0.39","Apple","Needs identification","🍎"],["Amazon device","10.0.0.24","Amazon","Needs identification","🔊"],["Amazon device","10.0.0.28","Amazon","Needs identification","🔊"],["Amazon device","10.0.0.35","Amazon","Needs identification","🔊"],["Amazon device","10.0.0.38","Amazon","Needs identification","🔊"]]};

function deviceArtwork(d){
 const name=d[0].toLowerCase();
 const shapes=name.includes("velux")?'<path d="M26 56h76L90 14H38L26 56Zm12-42 52 42M64 14v42"/>':
 /tv|sky|android/.test(name)?'<rect x="14" y="13" width="100" height="56" rx="6"/><path d="M49 82h30M64 69v13"/>':
 /oven|dishwasher|hob/.test(name)?'<rect x="32" y="7" width="64" height="78" rx="7"/><path d="M32 28h64M45 17h2m12 0h2m12 0h2"/><rect x="43" y="39" width="42" height="33" rx="4"/>':
 /printer/.test(name)?'<path d="M37 30V8h54v22M37 63H20V30h88v33H91M37 51h54v32H37zM92 42h3"/>':
 /playstation/.test(name)?'<path d="M37 31h54c12 0 22 39 12 45-7 4-19-16-26-16H51c-7 0-19 20-26 16-10-6 0-45 12-45Z"/><path d="M39 42v15m-7-8h14m35-4h1m10 8h1"/>':
 /router|unifi|bridge/.test(name)?'<rect x="24" y="40" width="80" height="30" rx="9"/><path d="M38 40V17m52 23V17M42 55h2m12 0h2m12 0h2M49 23q15-13 30 0M56 30q8-7 16 0"/>':
 '<rect x="22" y="15" width="84" height="54" rx="6"/><path d="M13 80h102M50 69v11m28-11v11"/>';
 return '<svg viewBox="0 0 128 96" aria-hidden="true">'+shapes+'</svg>';
}

function renderDevices(group){
 const grid=document.querySelector("#deviceGrid"); if(!grid)return;
 grid.setAttribute("aria-label","Devices and connection status");
 grid.innerHTML=(deviceGroups[group]||[]).map(function(d){
  return '<article class="device-card" data-ip="'+d[1]+'"><div class="device-art" aria-hidden="true">'+deviceArtwork(d)+'</div><div class="device-copy"><p class="device-brand">'+d[2]+'</p><h3>'+d[0]+'</h3><p>'+d[3]+'</p><code>'+d[1]+'</code></div><span class="device-state">Checking</span></article>';
 }).join("");
 refreshDeviceStatus();
}
async function refreshDeviceStatus(){
 try{
  const r=await fetch("/api/network/status",{cache:"no-store"}); const data=await r.json();
  const map=new Map((data.devices||[]).map(function(x){return [x.ip,x];}));
  document.querySelectorAll(".device-card").forEach(function(card){
   const item=map.get(card.dataset.ip), state=card.querySelector(".device-state");
   if(!item){state.textContent="Inventory";return;}
   state.textContent=item.online?"Online":"No response"; state.classList.toggle("online",!!item.online);
   if(item.detail)card.title=item.detail;
  });
  const pi=map.get("10.0.0.5"), note=document.querySelector("#piProbe");
  if(note)note.textContent=pi&&pi.online?"Old Raspberry Pi is reachable on the network.":"Old Raspberry Pi did not answer the quick service probe.";
 }catch(e){document.querySelectorAll(".device-state").forEach(function(x){x.textContent="Local only";});}
}
if(location.protocol==="http:" || location.hostname.endsWith(".ts.net"))setInterval(refreshDeviceStatus,30000);
let printerBusy=false;
function renderInkLevels(ink,estimated=false){
 const grid=document.querySelector('#printerInkGrid');if(!grid)return;
 const colours=[['Black','#8091a4'],['Cyan','#14c6ee'],['Magenta','#f63c9b'],['Yellow','#f3cf36']];
 grid.replaceChildren(...colours.map(([name,colour])=>{
  const value=(ink||[]).find(x=>String(x.colour).toLowerCase()===name.toLowerCase())?.percent;
  const known=typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100;
  const card=document.createElement('article');card.className='ink-card'+(known&&value<=15?' low':'')+(known?'':' unknown');card.style.setProperty('--ink-colour',colour);
  card.innerHTML='<div class="ink-card-head"><span class="ink-dot"></span><h3>'+name+'</h3><span class="ink-level-label"></span></div><div class="ink-tank" role="img"><div class="ink-fill"></div><div class="ink-tank-shine"></div></div><strong class="ink-percent"></strong><p></p>';
  card.querySelector('.ink-fill').style.height=known?value+'%':'0%';
  card.querySelector('.ink-percent').textContent=known?Math.round(value)+'%':'—';
  card.querySelector('.ink-level-label').textContent=known?(value<=15?'LOW':estimated?'ESTIMATED':'REPORTED'):'UNKNOWN';
  card.querySelector('p').textContent=known?(estimated?'Estimated from printer gauge':'Reported by printer'):'Not reported';
  card.querySelector('.ink-tank').setAttribute('aria-label',name+' ink: '+(known?value+' percent':'not reported'));
  return card;
 }));
}
async function refreshPrinterStatus(){
 const panel=document.querySelector('#printerPanel');if(!panel||printerBusy)return;
 printerBusy=true;
 const badge=document.querySelector('#printerBadge'),name=document.querySelector('#printerName'),detail=document.querySelector('#printerDetail');
 const live=document.querySelector('#printerLive'),protocols=document.querySelector('#printerProtocols'),identity=document.querySelector('#printerIdentity');
 const checked=document.querySelector('#printerChecked'),note=document.querySelector('#printerInkNote'),refresh=document.querySelector('#printerRefresh');
 if(refresh)refresh.disabled=true;
 const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),25000);
 try{
  const r=await fetch('/api/printer/status',{cache:'no-store',signal:abort.signal});if(!r.ok)throw new Error('Status unavailable');const p=await r.json();
  if(typeof p.online!=='boolean')throw new Error('Status unavailable');
  badge.textContent=p.online?'ONLINE':'NO RESPONSE';badge.classList.toggle('online',p.online);
  name.textContent=p.model||'Epson ET-3850';
  identity.textContent=(p.model||'Epson ET-3850')+' · '+(p.ip||'10.0.0.3');
  live.textContent=p.online?(p.state||'Connected'):'No response';
  const ports=p.ports||[],bits=[];if(p.http||ports.includes(80))bits.push('Web');if(p.https||ports.includes(443))bits.push('HTTPS');if(p.ipp||ports.includes(631))bits.push('IPP');if(p.raw_print||ports.includes(9100))bits.push('Print service');
  protocols.textContent=[p.connection,...bits].filter(Boolean).join(' · ')||'No printer services detected';
  const webLink=document.querySelector('#printerWebLink');if(webLink&&/^10\.0\.0\.\d{1,3}$/.test(p.ip||''))webLink.href='https://'+p.ip+'/PRESENTATION/HTML/TOP/PRTINFO.HTML';
  const ink=p.online?(p.ink||[]):[];renderInkLevels(ink,!!p.ink_estimated);
  const available=ink.filter(x=>typeof x.percent==='number'&&x.percent>=0&&x.percent<=100).length;
  if(note)note.textContent=available?available+' colour'+(available===1?'':'s')+(p.ink_estimated?' · estimated':' reported'):p.online?'Levels not supplied':'Printer unavailable';
  detail.textContent=p.online?(available?[(p.state||'Connected'),p.connection].filter(Boolean).join(' · '):'Printer connected. Numeric ink levels are not currently being reported.'):'The printer did not answer. Check that it is switched on and connected.';
  const stamp=p.checked_at?new Date(p.checked_at):new Date();
  if(checked)checked.textContent=Number.isNaN(stamp.getTime())?'—':stamp.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
 }catch(e){
  badge.textContent='UNAVAILABLE';badge.classList.remove('online');detail.textContent='Printer status could not be read. Try refreshing when Donkey is connected.';live.textContent='Status unavailable';renderInkLevels([]);if(note)note.textContent='No live reading';if(checked)checked.textContent='—';
 }finally{clearTimeout(timeout);printerBusy=false;if(refresh)refresh.disabled=false;}
}
renderInkLevels([]);
const printerRefresh=document.querySelector('#printerRefresh');if(printerRefresh)printerRefresh.addEventListener('click',refreshPrinterStatus);
function officeView(){
 const epson=document.querySelector('#epsonView'),devices=document.querySelector('#officeDevicesView');if(!epson||!devices)return;
 const office=location.hash==='#devices';epson.hidden=office;devices.hidden=!office;
 document.querySelectorAll('.device-view-tabs a').forEach(a=>{const active=a.hash===(office?'#devices':'#epson');a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
}
officeView();window.addEventListener('hashchange',officeView);

refreshPrinterStatus();
if(location.protocol==="http:" || location.hostname.endsWith(".ts.net"))setInterval(refreshPrinterStatus,30000);

async function refreshPlaystationStatus(){
 const panel=document.querySelector("#playstationPanel"); if(!panel)return;
 const badge=document.querySelector("#playstationBadge"),title=document.querySelector("#playstationTitle");
 const meta=document.querySelector("#playstationMeta"),detail=document.querySelector("#playstationDetail");
 try{
  const r=await fetch("/api/playstation/status",{cache:"no-store"}),p=await r.json();
  badge.textContent=p.online?"AWAKE":"NO REPLY"; badge.classList.toggle("online",!!p.online);
  const type=p.host_type||"PlayStation";
  title.textContent=p.running_app_name||p.host_name||type;
  const bits=[type,p.ip||"10.0.0.48"];
  if(p.system_version)bits.push("System "+p.system_version);
  meta.textContent=bits.join(" · ");
  if(p.running_app_name){
   detail.textContent="Now running: "+p.running_app_name+(p.running_app_titleid?" · "+p.running_app_titleid:"");
  }else{
   detail.textContent=p.detail||"Console detected; no running app name was supplied.";
  }
 }catch(e){
  badge.textContent="UNAVAILABLE";
  title.textContent="PlayStation status unavailable";
  meta.textContent="10.0.0.48";
  detail.textContent="The local PlayStation probe could not be read.";
 }
}
refreshPlaystationStatus();
if(location.protocol==="http:" || location.hostname.endsWith(".ts.net"))setInterval(refreshPlaystationStatus,15000);



