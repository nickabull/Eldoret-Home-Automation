const deviceGroups={"network":[["Main Router","10.0.0.1","DrayTek","Router","🌐"],["House Hue Bridge","10.0.0.2","Philips Hue","Bridge","💡"],["Utility Hue Bridge","10.0.0.4","Philips Hue","Bridge","💡"],["Old Raspberry Pi","10.0.0.5","Raspberry Pi","Legacy host","🥧"],["UniFi Office/Kitchen","10.0.0.6","Ubiquiti","Access point","📶"],["UniFi Utility","10.0.0.7","Ubiquiti","Access point","📶"],["UniFi Garden","10.0.0.8","Ubiquiti","Access point","📶"],["UniFi Landing","10.0.0.9","Ubiquiti","Access point","📶"],["BBC Aruba","10.0.0.20","HPE Aruba","Network device","📡"],["Eldoret Chromebook","10.0.0.27","Intel / ChromeOS","Current host","🫏"]],"av":[["Sky Q","10.0.0.18","Sky","Set-top box","📺"],["LG webOS TV","10.0.0.33","LG Electronics","webOS TV","📺"],["LG device","10.0.0.43","LG Innotek","Needs identification","📺"],["LG device","10.0.0.47","LG Electronics","Needs identification","📺"],
 ["LG webOS TV","10.0.0.51","LG Electronics","Newly discovered · room to identify","📺"],["Android-2","10.0.0.25","Allwinner","Android device","▶️"],["Android-3","10.0.0.31","Amazon","Android / Fire device","▶️"],["PlayStation","10.0.0.48","Sony","Games console","🎮"]],"appliances":[["Extractor Hood","10.0.0.12","BSH / Home Connect","Kitchen","🍳"],["Hob","10.0.0.13","BSH / Home Connect","Kitchen","🔥"],["Dishwasher","10.0.0.14","BSH / Home Connect","Kitchen","🫧"],["Left Oven","10.0.0.16","BSH / Home Connect","Kitchen","♨️"],["Right Oven","10.0.0.17","BSH / Home Connect","Kitchen","♨️"],["VELUX Gateway","10.0.0.22","Netatmo / VELUX","Windows & blinds","🪟"],["Tuya device","10.0.0.10","Tuya","Needs identification","🔌"],["Smart device","10.0.0.19","Espressif","Needs identification","🔌"],["Smart device","10.0.0.21","Texas Instruments","Needs identification","🔌"]],"office":[["Epson printer","10.0.0.3","Epson","Printer","🖨️"],["MacBook Pro","10.0.0.26","Apple","Computer","💻"],["Apple device","10.0.0.23","Apple","Needs identification","🍎"],["Apple device","10.0.0.39","Apple","Needs identification","🍎"],["Amazon device","10.0.0.24","Amazon","Needs identification","🔊"],["Amazon device","10.0.0.28","Amazon","Needs identification","🔊"],["Amazon device","10.0.0.35","Amazon","Needs identification","🔊"],["Amazon device","10.0.0.38","Amazon","Needs identification","🔊"]]};
function renderDevices(group){
 const grid=document.querySelector("#deviceGrid"); if(!grid)return;
 grid.innerHTML=(deviceGroups[group]||[]).map(function(d){
  return '<article class="device-card" data-ip="'+d[1]+'"><div class="device-icon">'+d[4]+'</div><div><h3>'+d[0]+'</h3><p>'+d[2]+' · '+d[3]+'</p><code>'+d[1]+'</code></div><span class="device-state">Checking</span></article>';
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
async function refreshPrinterStatus(){
 const panel=document.querySelector("#printerPanel"); if(!panel)return;
 const badge=document.querySelector("#printerBadge"),name=document.querySelector("#printerName"),detail=document.querySelector("#printerDetail");
 const live=document.querySelector("#printerLive"),protocols=document.querySelector("#printerProtocols"),identity=document.querySelector("#printerIdentity");
 try{
  const r=await fetch("/api/printer/status",{cache:"no-store"}),p=await r.json();
  badge.textContent=p.online?"ONLINE":"NO RESPONSE"; badge.classList.toggle("online",!!p.online);
  name.textContent=p.model||p.title||"Epson printer";
  identity.textContent=(p.model||p.title||"Epson network printer")+" · "+(p.ip||"10.0.0.3");
  live.textContent=p.online?"Printer is reachable from Eldoret.":"Printer did not answer the current probes.";
  const bits=[]; if(p.http)bits.push("Web"); if(p.https)bits.push("HTTPS"); if(p.ipp)bits.push("IPP"); if(p.raw_print)bits.push("Raw print");
  protocols.textContent=bits.length?bits.join(" · "):"No known printer services detected.";
  detail.textContent=p.detail||"Read-only probe complete.";
 }catch(e){
  badge.textContent="UNAVAILABLE"; detail.textContent="Printer status probe unavailable.";
 }
}
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
