
let eldoretPending=null,eldoretPendingTimer=null;
function clearEldoretPending(){
 if(eldoretPending&&eldoretPending.el)eldoretPending.el.classList.remove("eldoret-pending");
 eldoretPending=null;clearTimeout(eldoretPendingTimer);
 const box=document.querySelector("#eldoretConfirm");if(box)box.remove();
}
function stageEldoretAction(label,run,el){
 clearEldoretPending();if(el)el.classList.add("eldoret-pending");eldoretPending={run,el};
 const box=document.createElement("div");box.id="eldoretConfirm";box.className="eldoret-confirm";
 box.innerHTML='<span>'+label+'</span><button type="button">CONFIRM</button>';
 box.querySelector("button").onclick=async()=>{const p=eldoretPending;clearEldoretPending();if(p)await p.run();};
 document.body.appendChild(box);eldoretPendingTimer=setTimeout(clearEldoretPending,10000);
}
const isLive=location.protocol==="http:" || location.hostname.endsWith(".ts.net");

const LIGHT_ROOMS=[
 {n:"Living Room",b:"house",g:"1",l:2,x:"Room",img:"https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1000&q=82"},
 {n:"Kitchen",b:"house",g:"2",l:16,x:"Room",img:"https://images.unsplash.com/photo-1556912167-f556f1f39fdf?auto=format&fit=crop&w=1000&q=82"},
 {n:"Dining Room",b:"house",g:"3",l:6,x:"Room",img:"https://images.unsplash.com/photo-1617806118233-18e1de247200?auto=format&fit=crop&w=1000&q=82"},
 {n:"Dining Filaments",b:"house",g:"9",l:2,x:"Room",img:"https://images.unsplash.com/photo-1540932239986-30128078f3c5?auto=format&fit=crop&w=1000&q=82"},
 {n:"Office Spots",b:"house",g:"4",l:5,x:"Room",img:"https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1000&q=82"},
 {n:"Office Rail",b:"house",g:"6",l:6,x:"Room",img:"https://images.unsplash.com/photo-1497215842964-222b430dc094?auto=format&fit=crop&w=1000&q=82"},
 {n:"Office Spots + Rail",b:"house",g:"7",l:11,x:"Zone",img:"https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1000&q=82"},
 {n:"Kitchen + Dining",b:"house",g:"10",l:24,x:"Zone",img:"https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1000&q=82"},
 {n:"Kitchen Music Area",b:"house",g:"5",l:2,x:"Entertainment",img:"https://images.unsplash.com/photo-1506157786151-b8491531f063?auto=format&fit=crop&w=1000&q=82"},
 {n:"Outside Lights",b:"utility",g:"1",l:6,x:"Room",img:"https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=82"},
 {n:"Outside Back Door",b:"utility",g:"85",l:4,x:"Zone",img:"https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=82"},
 {n:"BBQ",b:"utility",g:"84",l:1,x:"Room",img:"https://images.unsplash.com/photo-1550547660-d9450f859349?auto=format&fit=crop&w=1000&q=82"},
 {n:"Utility",b:"utility",g:"5",l:8,x:"Room",img:"https://images.unsplash.com/photo-1626806787461-102c1bfaaea1?auto=format&fit=crop&w=1000&q=82"},
 {n:"Shower",b:"utility",g:"4",l:6,x:"Room",img:"https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=1000&q=82"},
 {n:"Hallway",b:"utility",g:"3",l:2,x:"Room",img:"https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?auto=format&fit=crop&w=1000&q=82"},
 {n:"Toilet",b:"utility",g:"2",l:2,x:"Room",img:"https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=1000&q=82"}
];

const LIGHT_SCENES={
 "house:1":[["Relax","mAMhLI5w246Jb3F"],["Read","4ZHRjRkG68-2Lgu"],["Concentrate","0teOVWVSxbrU1PA"],["Energize","nEbdYT6HPjZzlpy"],["Bright","4lXui9okasttMhR"],["Dimmed","hTlcfO3RlBG63TI"],["Nightlight","249kGtSrbmlG6uE"],["Hamilton 1","R9HNBqvmFqKUk-v"],["Hamilton 2","xlhSwlYHdEloKGk"],["Hamilton 3","XrGEpMxX6EP8UQe"],["NFL","OY8EaVSlokAvxPL"],["Xmas","ZKhdjq5TX6U7QnM"],["Sofa match","ovUyp2QHnvxN-4kL"]],
 "house:3":[["Relax","uxoEgFVtSrNzfx4"],["Bright","yV-ouqODcFl6SwI"],["Dimmed","tfUe4Mo7DMSIzpk"],["Nightlight","amOkIr374v0wK2U"],["Dada","U5RiqK62ooaiDIA"],["Eben :)","23evjjtinlbxfXy"]],
 "house:7":[["Office Bright","mauInies7FdR5AN"],["Office Dimmed","YH89dxjgGd7EMFy"],["Office Night","vV8CSKvd0vmtmON"],["Bright","ESscQoDspmSoQwl"],["Dimmed","hkWGbIYW0o2HgRB"],["Nice Colours Night","Y5fJULvQDCz-Zxu"],["Nice Colours Dimmed","LDuiuphvok3m0di"],["Nice Colours Bright","EmvbzuG3Z8YBENt"],["Just Nice Colours","fM6M7KUce8VO1yU"],["NFL 2026","nUNbRbDQDrKdYs3Z"],["Xmas","r9t0ptKIQaRCXizt"],["Neth/Eng Footy","4DFHQbPQw0iHe5Wr"],["Spain/Eng Footy","SbHM2nsz0egLWWGW"]],
 "house:10":[["Cook","fu1UnoAfef43Y52"],["Relax","IST2oo3GXy2DhlZ"],["Night","XabJ8eHAMa-0smi"],["Osaka","3sas67ih-vFdmJq"],["Galaxy","3WJXdyzs-ZHpPc0"],["Xmas","AIqAQKPhhk0vcOO"],["Bright","wFJXxD-7wO2LqRk"],["Dimmed","XexsIDQ1BwdtNvY"],["Nightlight","X0o4VIWGL038T4P"]],
 "utility:1":[["Bright","Uq7bUd0JObHb2Fx"],["Dimmed","aepnytsDnt271hp"],["Nightlight","fM0oLNnpav2dOhT"],["Energise","RrhWol7pVQ2LpAWy"],["Concentrate","edrTyU-A0RDnd5N8"],["Read","uD0JHTc9ChplGvhT"],["Relax","NxAkGVentaIX6XgH"]],
 "utility:2":[["Bright","IlMmYNNvY5ItzAG"],["Dimmed","erEuWDrXFuxBcNl"],["Nightlight","Aqxe4pr8v-lLB-c"]],
 "utility:3":[["Bright","vHo3Bu8yrquQa33"],["Dimmed","8EtcV3n8cmBEgpG"],["Nightlight","pwJfUQwbyK7CWAh"]],
 "utility:4":[["Bright","QklFHNpwfV7AqRU"],["Dimmed","uk8ICeXud6zJE7J"],["Nightlight","fDARlnbrSRI5Y1t"]],
 "utility:5":[["Bright","8fKZxYEXlDzy1jB"],["Dimmed","6RBogGJrfiQkM-D"],["Nightlight","j-rJ37JmxYUAUCc"]],
 "utility:85":[["Bright","Qy26e7sR-keGpT1y"],["Dimmed","WdyKc04jAEcDkJ1k"]]
};

const SCENE_LOOKS=[
 "linear-gradient(135deg,#f0cf85,#76563d)",
 "linear-gradient(135deg,#dcecff,#5d78a6)",
 "linear-gradient(135deg,#ffb47b,#693f69)",
 "linear-gradient(135deg,#7ed6d0,#244b72)",
 "linear-gradient(135deg,#d2a6ff,#6b3c8d)",
 "linear-gradient(135deg,#ffd7aa,#8a5b42)",
 "linear-gradient(135deg,#9db3ff,#263b65)",
 "linear-gradient(135deg,#f5ead8,#675b4c)"
];

let roomPage=0,scenePage=0,selected=LIGHT_ROOMS[0];
const roomsPerPage=4,scenesPerPage=6;
const roomGrid=document.querySelector("#lightRoomGrid"),sceneGrid=document.querySelector("#lightSceneGrid");

function roomKey(r){return r.b+":"+r.g}
function pageCount(items,n){return Math.max(1,Math.ceil(items.length/n))}
function setPager(label,prev,next,page,pages){
 label.textContent=(page+1)+" / "+pages; prev.disabled=page<=0; next.disabled=page>=pages-1;
}
function roomIcon(){
 return '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M9 51V27L32 10l23 17v24H38V36H26v15H9Z"/></svg>';
}
function renderRooms(){
 const pages=pageCount(LIGHT_ROOMS,roomsPerPage); roomPage=Math.min(roomPage,pages-1);
 const chunk=LIGHT_ROOMS.slice(roomPage*roomsPerPage,(roomPage+1)*roomsPerPage);
 roomGrid.innerHTML=chunk.map(r=>'<button class="light-room-card'+(roomKey(r)===roomKey(selected)?' selected':'')+'" data-key="'+roomKey(r)+'" style="--room-image:url(&quot;'+r.img+'&quot;)">'+
   '<div class="light-room-shade"></div><div class="light-room-content"><div class="light-room-top"><span class="light-room-icon">'+roomIcon()+'</span><span class="light-room-state" data-state-for="'+roomKey(r)+'">Checking</span></div>'+
   '<div><p>'+(r.b==="house"?"HOUSE":"UTILITY")+' · '+r.x.toUpperCase()+'</p><h3>'+r.n+'</h3><small>'+r.l+' light'+(r.l===1?'':'s')+'</small></div></div></button>').join("");
 roomGrid.querySelectorAll(".light-room-card").forEach(b=>b.addEventListener("click",()=>selectRoom(b.dataset.key)));
 setPager(document.querySelector("#roomPageLabel"),document.querySelector("#roomPrev"),document.querySelector("#roomNext"),roomPage,pages);
 chunk.forEach(refreshRoomState);
}
function selectRoom(key){
 selected=LIGHT_ROOMS.find(r=>roomKey(r)===key)||selected;scenePage=0;
 document.querySelector("#sceneRoomTitle").textContent=selected.n;
 renderRooms();renderQuickControl();renderScenes();
}
function renderScenes(){
 const list=LIGHT_SCENES[roomKey(selected)]||[];
 if(!list.length){
   sceneGrid.innerHTML='<div class="lights-empty">No saved scenes for this room yet.</div>';
   document.querySelector("#scenePageLabel").textContent="—";
   document.querySelector("#scenePrev").disabled=true;document.querySelector("#sceneNext").disabled=true;return;
 }
 const pages=pageCount(list,scenesPerPage);scenePage=Math.min(scenePage,pages-1);
 const chunk=list.slice(scenePage*scenesPerPage,(scenePage+1)*scenesPerPage);
 sceneGrid.innerHTML=chunk.map((s,i)=>'<button class="light-scene-card" data-scene="'+s[1]+'" style="--scene-look:'+SCENE_LOOKS[(scenePage*scenesPerPage+i)%SCENE_LOOKS.length]+'">'+
   '<span class="scene-glow"></span><div><p>SCENE</p><h3>'+s[0]+'</h3><small>Tap to activate</small></div></button>').join("");
 sceneGrid.querySelectorAll(".light-scene-card").forEach(b=>b.addEventListener("click",()=>stageEldoretAction(selected.n+" · "+b.querySelector("h3").textContent,()=>activateScene(b),b)));
 setPager(document.querySelector("#scenePageLabel"),document.querySelector("#scenePrev"),document.querySelector("#sceneNext"),scenePage,pages);
}
function renderQuickControl(){
 const host=document.querySelector("#lightQuickControl"); if(!host)return;
 host.innerHTML='<button type="button" data-light-power="on">On</button><button type="button" data-light-power="off">Off</button><div class="dimmer-wrap"><span>Dimmer</span><input id="lightDimmer" type="range" min="1" max="100" value="70"><output id="lightDimmerValue">70%</output></div>';
 host.querySelectorAll("[data-light-power]").forEach(btn=>btn.addEventListener("click",()=>stageEldoretAction(selected.n+" · "+btn.textContent,()=>setRoomPower(btn.dataset.lightPower==="on"),btn)));
 const dim=host.querySelector("#lightDimmer"),out=host.querySelector("#lightDimmerValue");
 dim.addEventListener("input",()=>out.textContent=dim.value+"%");
 dim.addEventListener("change",()=>stageEldoretAction(selected.n+" · "+dim.value+"%",()=>setRoomBrightness(Number(dim.value)),dim));
 refreshSelectedControl();
}
async function setRoomPower(on){
 if(!isLive)return;
 try{
  const res=await fetch("/api/hue/group",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bridge:selected.b,group:selected.g,on})});
  if(!res.ok)throw new Error();
  setTimeout(()=>{refreshRoomState(selected);refreshSelectedControl();},220);
 }catch(e){}
}
async function setRoomBrightness(brightness){
 if(!isLive)return;
 try{
  const res=await fetch("/api/hue/group",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bridge:selected.b,group:selected.g,brightness})});
  if(!res.ok)throw new Error();
  setTimeout(()=>{refreshRoomState(selected);refreshSelectedControl();},220);
 }catch(e){}
}
async function refreshSelectedControl(){
 if(!isLive)return;
 const host=document.querySelector("#lightQuickControl"); if(!host)return;
 try{
  const res=await fetch("/api/hue/group?bridge="+encodeURIComponent(selected.b)+"&group="+encodeURIComponent(selected.g),{cache:"no-store"});
  if(!res.ok)throw new Error();
  const d=await res.json(); const on=!!(d.state&&d.state.any_on);
  const bri=(d.action&&typeof d.action.bri==="number")?Math.max(1,Math.round(d.action.bri*100/254)):70;
  host.querySelectorAll("[data-light-power]").forEach(b=>b.classList.toggle("active",b.dataset.lightPower===(on?"on":"off")));
  const dim=host.querySelector("#lightDimmer"),out=host.querySelector("#lightDimmerValue"); if(dim){dim.value=bri;out.textContent=bri+"%";}
 }catch(e){}
}
async function refreshRoomState(r){
 if(!isLive)return;
 const tag=document.querySelector('[data-state-for="'+roomKey(r)+'"]');if(!tag)return;
 try{
  const res=await fetch("/api/hue/group?bridge="+encodeURIComponent(r.b)+"&group="+encodeURIComponent(r.g),{cache:"no-store"});
  if(!res.ok)throw new Error();
  const d=await res.json();const on=!!(d.state&&d.state.any_on);
  const bri=(d.action&&typeof d.action.bri==="number")?Math.max(1,Math.round(d.action.bri*100/254)):null;
  tag.textContent=on?("ON"+(bri!==null?" · "+bri+"%":"")):"OFF";tag.classList.toggle("on",on);
 }catch(e){tag.textContent="—";}
}
async function activateScene(button){
 if(!isLive)return;
 button.classList.add("sending");
 try{
  const res=await fetch("/api/hue/scene",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bridge:selected.b,group:selected.g,scene:button.dataset.scene})});
  if(!res.ok)throw new Error();
  document.querySelectorAll(".light-scene-card").forEach(x=>x.classList.remove("active"));
  button.classList.add("active");setTimeout(()=>refreshRoomState(selected),500);
 }catch(e){button.classList.add("failed");setTimeout(()=>button.classList.remove("failed"),1200)}
 finally{setTimeout(()=>button.classList.remove("sending"),180)}
}
document.querySelector("#roomPrev").onclick=()=>{if(roomPage>0){roomPage--;renderRooms()}};
document.querySelector("#roomNext").onclick=()=>{if(roomPage<pageCount(LIGHT_ROOMS,roomsPerPage)-1){roomPage++;renderRooms()}};
document.querySelector("#scenePrev").onclick=()=>{if(scenePage>0){scenePage--;renderScenes()}};
document.querySelector("#sceneNext").onclick=()=>{const list=LIGHT_SCENES[roomKey(selected)]||[];if(scenePage<pageCount(list,scenesPerPage)-1){scenePage++;renderScenes()}};

document.querySelector("#sceneRoomTitle").textContent=selected.n;renderRooms();renderQuickControl();renderScenes();
if(isLive)setInterval(()=>LIGHT_ROOMS.slice(roomPage*roomsPerPage,(roomPage+1)*roomsPerPage).forEach(refreshRoomState),15000);


// Read-only Hue sensor view, sharing the existing bridge connection.
(()=>{
 const host=document.querySelector('#hueSensorsView'),grid=document.querySelector('#hueSensorGrid');if(!host||!grid)return;
 let sensors=[],page=0,busy=false;
 const valid=v=>typeof v==='number'&&Number.isFinite(v);
 function render(){
  const pages=Math.max(1,Math.ceil(sensors.length/6));page=Math.min(page,pages-1);grid.replaceChildren();
  for(const sensor of sensors.slice(page*6,page*6+6)){
   const card=document.createElement('article');card.className='sensor-card';
   const offline=sensor.reachable===false;
   card.innerHTML='<div class="sensor-card-top"><p class="eyebrow"></p><span class="sensor-badge"></span></div><h3></h3><div class="sensor-values"></div><p class="sensor-age"></p>';
   card.querySelector('.eyebrow').textContent=sensor.bridge==='house'?'HOUSE':'UTILITY';card.querySelector('h3').textContent=sensor.name||'Hue sensor';
   const badge=card.querySelector('.sensor-badge');badge.textContent=offline?'NO RESPONSE':valid(sensor.battery)&&sensor.battery<=15?'LOW BATTERY':sensor.reachable===true?'CONNECTED':'UNKNOWN';badge.classList.toggle('warn',offline||valid(sensor.battery)&&sensor.battery<=15);
   const values=[['Temperature',!offline&&valid(sensor.temperature)?sensor.temperature.toFixed(1)+'°C':'—'],['Light level',!offline&&valid(sensor.lux)?Math.round(sensor.lux).toLocaleString()+' lux':'—'],['Motion',offline?'—':sensor.motion===true?'Detected':sensor.motion===false?'Clear':'—'],['Battery',valid(sensor.battery)?sensor.battery+'%':'—']];
   const list=card.querySelector('.sensor-values');for(const [label,value] of values){const item=document.createElement('div'),l=document.createElement('span'),v=document.createElement('strong');l.textContent=label;v.textContent=value;item.append(l,v);list.appendChild(item);}
   const stamp=new Date(sensor.updated_at);card.querySelector('.sensor-age').textContent=sensor.updated_at&&!Number.isNaN(stamp.getTime())?'Last reported '+stamp.toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'No report time supplied';grid.appendChild(card);
  }
  document.querySelector('#sensorPageLabel').textContent=(page+1)+' / '+pages;document.querySelector('#sensorPrev').disabled=page<=0;document.querySelector('#sensorNext').disabled=page>=pages-1;
 }
 async function load(){
  if(busy||host.hidden)return;busy=true;
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),15000);
  try{
   const r=await fetch('/api/hue/sensors',{cache:'no-store',signal:abort.signal});if(!r.ok)throw new Error('Sensor feed unavailable');const data=await r.json();if(!Array.isArray(data.devices))throw new Error('Invalid sensor feed');sensors=data.devices;render();
   const low=sensors.filter(x=>valid(x.battery)&&x.battery<=15).length;
   document.querySelector('#sensorSummary').textContent=sensors.length+' devices'+(low?' · '+low+' low batter'+(low===1?'y':'ies'):'')+(data.errors?.length?' · One or more bridges unavailable':'');
   if(!sensors.length)grid.innerHTML='<div class="lights-empty">'+(data.errors?.length?'The Hue bridges could not be read.':'No supported sensors were reported by the bridges.')+'</div>';
   const time=new Date(data.checked_at);document.querySelector('#sensorChecked').textContent='Read-only sensor readings'+(!Number.isNaN(time.getTime())?' · Checked '+time.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'')+'. Motion reports are not a guarantee that a room is occupied.';
  }catch(e){sensors=[];render();document.querySelector('#sensorSummary').textContent='Live readings unavailable';grid.innerHTML='<div class="lights-empty">The Hue sensor feed is not available yet. Donkey may need to load the updated connector.</div>';document.querySelector('#sensorChecked').textContent='No live readings available.';}
  finally{clearTimeout(timeout);busy=false;}
 }
 function view(){const active=location.hash==='#sensors';document.body.classList.toggle('hue-sensors-active',active);const title=document.querySelector('.lights-hero h2'),copy=document.querySelector('.lights-hero>div:last-child>p:last-child');if(title)title.textContent=active?'Sensors & batteries':'Lights';if(copy)copy.textContent=active?'Motion, room conditions and battery health from your Hue bridges.':'Set the mood. Choose a room, adjust the lights or select a scene.';host.hidden=!active;document.querySelectorAll('.lights-control-view').forEach(x=>x.hidden=active);document.querySelectorAll('.device-view-tabs a').forEach(a=>{const selected=a.hash===(active?'#sensors':'#lights');a.classList.toggle('active',selected);if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});if(active)load();}
 document.querySelector('#sensorPrev').onclick=()=>{if(page>0){page--;render();}};document.querySelector('#sensorNext').onclick=()=>{if(page<Math.ceil(sensors.length/6)-1){page++;render();}};
 window.addEventListener('hashchange',view);view();setInterval(load,30000);
})();
