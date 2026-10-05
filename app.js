const rooms=[
{n:"Living Room",b:"house",g:"1",i:"🛋️",l:2,x:"Room",color:true,d:["2 colour bulbs","Living Room Hue dimmer · 79% battery"]},
{n:"Kitchen",b:"house",g:"2",i:"🍳",l:16,x:"Room",color:true,d:["10 ceiling spots","Hue Lightstrip Plus","Table & corner lamps","2 filament bulbs","Hue Tap + dimmer switch","Smart plug · unreachable"]},
{n:"Dining Room",b:"house",g:"3",i:"🍽️",l:6,x:"Room",color:true,d:["Colour spots","Fugato colour spots"]},
{n:"Dining Filaments",b:"house",g:"9",i:"💡",l:2,x:"Room",color:false,d:["2 Hue filament bulbs"]},
{n:"Office Spots",b:"house",g:"4",i:"💻",l:5,x:"Room",color:false,d:["5 Hue Ambiance spots","Office Hue Tap switch"]},
{n:"Office Rail",b:"house",g:"6",i:"🎨",l:6,x:"Room",color:true,d:["White + colour GU10 spots"]},
{n:"Office Spots + Rail",b:"house",g:"7",i:"🧑‍💻",l:11,x:"Zone",color:true,d:["Combined Office lighting zone"]},
{n:"Kitchen + Dining",b:"house",g:"10",i:"🏠",l:24,x:"Zone",color:true,d:["Combined downstairs lighting zone"]},
{n:"Kitchen Music Area",b:"house",g:"5",i:"🎵",l:2,x:"Entertainment",color:true,d:["Hue Entertainment area"]},
{n:"Xmas lights",b:"house",g:"8",i:"🎄",l:0,x:"Room",color:false,d:["Currently empty"]},
{n:"Outside Lights",b:"utility",g:"1",i:"🌙",l:6,x:"Room",color:false,d:["6 Hue white outdoor bulbs","Outdoor motion sensor · battery critical"]},
{n:"Outside Back Door",b:"utility",g:"85",i:"🚪",l:4,x:"Zone",color:false,d:["Overlapping outside-light zone"]},
{n:"BBQ",b:"utility",g:"84",i:"🔥",l:1,x:"Room",color:true,d:["Hue Discover outdoor wall light","BBQ switch · battery empty"]},
{n:"Utility",b:"utility",g:"5",i:"🧺",l:8,x:"Room",color:false,d:["8 spots","Hue motion sensor · battery 100%","Motion · light · temperature"]},
{n:"Shower",b:"utility",g:"4",i:"🚿",l:6,x:"Room",color:false,d:["6 Hue white spots","Hue Smart button · battery 100%","Spot 6 needs attention"]},
{n:"Hallway",b:"utility",g:"3",i:"🚶",l:2,x:"Room",color:false,d:["2 Hue Ambiance spots","Motion sensor · battery critical"]},
{n:"Toilet",b:"utility",g:"2",i:"🚻",l:2,x:"Room",color:false,d:["2 Hue white spots"]}
];

const scenes={
  "house:1":[
    ["Relax","mAMhLI5w246Jb3F"],["Read","4ZHRjRkG68-2Lgu"],["Concentrate","0teOVWVSxbrU1PA"],
    ["Energize","nEbdYT6HPjZzlpy"],["Bright","4lXui9okasttMhR"],["Dimmed","hTlcfO3RlBG63TI"],
    ["Nightlight","249kGtSrbmlG6uE"],["Hamilton 1","R9HNBqvmFqKUk-v"],["Hamilton 2","xlhSwlYHdEloKGk"],
    ["Hamilton 3","XrGEpMxX6EP8UQe"],["NFL","OY8EaVSlokAvxPL"],["Xmas","ZKhdjq5TX6U7QnM"],
    ["Sofa match","ovUyp2QHnvxN-4kL"]
  ],
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

const grid=document.querySelector("#rooms");
const dlg=document.querySelector("#detail");
const dc=document.querySelector("#detailContent");
const isLive=location.protocol==="http:";

function render(filter="all"){
  grid.innerHTML="";
  rooms.filter(r=>filter==="all"||r.b===filter).forEach(r=>{
    const button=document.createElement("button");
    button.type="button";
    button.className="card";
    button.innerHTML='<div><span class="icon">'+r.i+'</span><h3>'+r.n+'</h3><p>'+(r.b==="house"?"House":"Utility")+' bridge</p></div><div class="meta"><span class="pill">'+r.x+'</span><span class="pill">'+r.l+' lights</span></div>';
    button.addEventListener("click",()=>openRoom(r));
    grid.appendChild(button);
  });
}

function controlMarkup(r){
  if(r.l===0) return '<div class="control-note">No lights are currently assigned to this room.</div>';
  const colours=r.color?'<div class="control-block"><label>Colour</label><div class="colour-row">'+[
    ["#ffb36b","Warm"],["#ffffff","White"],["#6bb8ff","Blue"],["#d77bff","Purple"],["#ff6f91","Pink"],["#70e0a0","Green"]
  ].map(c=>'<button type="button" class="colour-btn" data-colour="'+c[0]+'" aria-label="'+c[1]+'" title="'+c[1]+'" style="--swatch:'+c[0]+'"></button>').join("")+'</div></div>':'';
  const roomScenes=scenes[r.b+":"+r.g]||[];
  const sceneMarkup=roomScenes.length?'<div class="control-block"><label>Scenes</label><div class="scene-grid">'+roomScenes.map(s=>'<button type="button" class="scene-btn" data-scene="'+s[1]+'">'+s[0]+'</button>').join("")+'</div></div>':'';
  return '<div class="controls">'+
    '<div class="control-top"><button type="button" class="power-btn" data-power="toggle"><span class="power-dot"></span><span class="power-label">Power</span></button><span class="control-state">Connecting…</span></div>'+
    '<div class="live-readout"><span class="live-dot"></span><span class="live-text">Reading Hue state…</span></div>'+
    '<div class="control-block"><div class="range-head"><label for="dimRange">Brightness</label><output id="dimValue">—</output></div><input id="dimRange" class="dim-range" type="range" min="1" max="100" value="70"></div>'+
    colours+sceneMarkup+
    '<div class="control-note">'+(isLive?'Live through the Eldoret connector.':'Open Eldoret through the local Chromebook connector to use live controls.')+'</div>'+
  '</div>';
}
function openRoom(r){
  dc.innerHTML='<p class="eyebrow">'+r.x.toUpperCase()+' · '+(r.b==="house"?"HOUSE":"UTILITY")+'</p><h2>'+r.i+' '+r.n+'</h2><p>'+r.l+' Hue light'+(r.l===1?"":"s")+'</p>'+
    controlMarkup(r)+
    '<div class="detail-list">'+r.d.map(x=>'<div>'+x+'</div>').join("")+'</div>';
  wireControls(r);
  if(typeof dlg.showModal==="function") dlg.showModal(); else dlg.setAttribute("open","");
}

function wireControls(r){
  const p=dc.querySelector(".power-btn");
  const range=dc.querySelector(".dim-range");
  const out=dc.querySelector("#dimValue");
  if(p) p.addEventListener("click",()=>{const next=!p.classList.contains("on");setPowerUI(next);sendControl(r,{on:next});});
  if(range){
    range.addEventListener("input",()=>out.textContent=range.value+"%");
    range.addEventListener("change",()=>sendControl(r,{brightness:Number(range.value)}));
  }
  dc.querySelectorAll(".colour-btn").forEach(btn=>btn.addEventListener("click",()=>{
    dc.querySelectorAll(".colour-btn").forEach(x=>x.classList.remove("selected"));
    btn.classList.add("selected");
    sendControl(r,{colour:btn.dataset.colour});
  }));
  dc.querySelectorAll(".scene-btn").forEach(btn=>btn.addEventListener("click",()=>activateScene(r,btn.dataset.scene,btn)));
  refreshState(r);
}

function setPowerUI(on){
  const p=dc.querySelector(".power-btn");
  if(!p)return;
  p.classList.toggle("on",!!on);
  p.querySelector(".power-label").textContent=on?"On":"Off";
}

async function refreshState(r){
  if(!isLive)return;
  const state=dc.querySelector(".control-state");
  const live=dc.querySelector(".live-text");
  const dot=dc.querySelector(".live-dot");
  try{
    const res=await fetch("/api/hue/group?bridge="+encodeURIComponent(r.b)+"&group="+encodeURIComponent(r.g),{cache:"no-store"});
    if(!res.ok)throw new Error("state");
    const data=await res.json();
    const on=!!(data.state&&data.state.any_on);
    const bri=(data.action&&typeof data.action.bri==="number")?Math.max(1,Math.round(data.action.bri*100/254)):null;
    setPowerUI(on);
    const range=dc.querySelector(".dim-range"),out=dc.querySelector("#dimValue");
    if(bri!==null&&range){range.value=bri;out.textContent=bri+"%";}
    state.textContent="Live";
    if(live)live.textContent=(on?"On":"Off")+(bri!==null?" · "+bri+"%":"");
    if(dot)dot.classList.add("ok");
  }catch(e){
    state.textContent="Connector offline";
    if(live)live.textContent="Unable to read Hue state";
    if(dot)dot.classList.remove("ok");
  }
}

async function sendControl(r,command){
  const state=dc.querySelector(".control-state");
  if(!isLive){state.textContent="Preview";return;}
  state.textContent="Sending…";
  try{
    const res=await fetch("/api/hue/group",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bridge:r.b,group:r.g,...command})});
    if(!res.ok) throw new Error("Control failed");
    state.textContent="Live";
    setTimeout(()=>refreshState(r),180);
  }catch(e){state.textContent="Connector offline";}
}

async function activateScene(r,scene,button){
  if(!isLive)return;
  const state=dc.querySelector(".control-state");
  state.textContent="Scene…";
  dc.querySelectorAll(".scene-btn").forEach(x=>x.classList.remove("selected"));
  try{
    const res=await fetch("/api/hue/scene",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bridge:r.b,group:r.g,scene})});
    if(!res.ok)throw new Error("Scene failed");
    button.classList.add("selected");
    state.textContent="Live";
    setTimeout(()=>refreshState(r),250);
  }catch(e){state.textContent="Connector offline";}
}

document.querySelector(".close").addEventListener("click",()=>dlg.close());
dlg.addEventListener("click",e=>{if(e.target===dlg)dlg.close();});
render(window.ELDORET_FILTER||"all");
