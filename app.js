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
  return '<div class="controls">'+
    '<div class="control-top"><button type="button" class="power-btn" data-power="toggle"><span class="power-dot"></span><span class="power-label">Power</span></button><span class="control-state">Preview</span></div>'+
    '<div class="control-block"><div class="range-head"><label for="dimRange">Brightness</label><output id="dimValue">70%</output></div><input id="dimRange" class="dim-range" type="range" min="1" max="100" value="70"></div>'+
    colours+
    '<div class="control-note">'+(isLive?'Local control mode detected.':'Controls are ready, but GitHub Pages cannot securely talk directly to the Hue bridges. A small local connector will make these live.')+'</div>'+
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
  if(p) p.addEventListener("click",()=>{p.classList.toggle("on");p.querySelector(".power-label").textContent=p.classList.contains("on")?"On":"Off";sendControl(r,{on:p.classList.contains("on")});});
  if(range){
    range.addEventListener("input",()=>out.textContent=range.value+"%");
    range.addEventListener("change",()=>sendControl(r,{brightness:Number(range.value)}));
  }
  dc.querySelectorAll(".colour-btn").forEach(btn=>btn.addEventListener("click",()=>{
    dc.querySelectorAll(".colour-btn").forEach(x=>x.classList.remove("selected"));
    btn.classList.add("selected");
    sendControl(r,{colour:btn.dataset.colour});
  }));
}

async function sendControl(r,command){
  const state=dc.querySelector(".control-state");
  if(!isLive){state.textContent="Preview";return;}
  state.textContent="Sending…";
  try{
    const res=await fetch("/api/hue/group",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bridge:r.b,group:r.g,...command})});
    if(!res.ok) throw new Error("Control failed");
    state.textContent="Live";
  }catch(e){state.textContent="Connector offline";}
}

document.querySelector(".close").addEventListener("click",()=>dlg.close());
dlg.addEventListener("click",e=>{if(e.target===dlg)dlg.close();});
render(window.ELDORET_FILTER||"all");
