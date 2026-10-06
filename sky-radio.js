const isLive=location.protocol==="http:" || location.hostname.endsWith(".ts.net");
const PAGE_SIZE=14;let stations=[],page=0;
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function clock(v){if(!v)return "";const d=new Date(v);return Number.isNaN(d.getTime())?"":d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}
function artwork(uuid){return uuid?"https://images.metadata.sky.com/pd-image/"+encodeURIComponent(uuid)+"/16-9":""}
function applyArtwork(el,uuid,cssVar,klass){
  if(!el||!uuid){if(el){el.classList.remove(klass);el.style.removeProperty(cssVar)}return}
  const url=artwork(uuid),probe=new Image();
  probe.onload=()=>{el.style.setProperty(cssVar,'url("'+url+'")');el.classList.add(klass)};
  probe.onerror=()=>{el.classList.remove(klass);el.style.removeProperty(cssVar)};
  probe.src=url;
}
async function tune(channel){if(!isLive)return;await fetch("/api/sky/channel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({channel:String(channel)})});setTimeout(refreshNow,1500)}
function render(){
  const pages=Math.max(1,Math.ceil(stations.length/PAGE_SIZE));page=Math.max(0,Math.min(page,pages-1));
  document.querySelector("#skyRadioPageLabel").textContent=(page+1)+" / "+pages;
  const grid=document.querySelector("#skyRadioGrid"),slice=stations.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
  grid.innerHTML=slice.map((x,i)=>'<button class="sport-channel sky-radio-station" data-index="'+i+'" data-channel="'+esc(x.tune)+'">'+
    (x.logo?'<img class="sport-channel-logo" src="'+esc(x.logo)+'" alt="">':'')+
    '<strong>'+esc(x.channel||"Radio")+'</strong><div class="sport-onair"><span>'+esc(x.channelno)+'</span><b>'+esc(x.programme||"Live radio")+'</b>'+
    (x.synopsis?'<p class="sport-synopsis">'+esc(x.synopsis)+'</p>':'')+
    (x.next&&x.next.programme?'<div class="sport-next"><span>Next'+(x.next.start?' · '+clock(x.next.start):'')+'</span><b>'+esc(x.next.programme)+'</b></div>':'')+
    '</div><small>'+esc(x.channelno)+'</small></button>').join("");
  grid.querySelectorAll("[data-channel]").forEach((b,i)=>{
    b.onclick=()=>tune(b.dataset.channel);
    const item=slice[i];
    if(item&&item.programmeuuid) applyArtwork(b,item.programmeuuid,"--radio-artwork","has-radio-artwork");
  });
}
async function load(){try{const r=await fetch("/api/sky/radio",{cache:"no-store"}),d=await r.json();stations=d.channels||[];render()}catch(e){document.querySelector("#skyRadioGrid").innerHTML='<div class="sky-search-hint">Sky radio unavailable</div>'}}
async function refreshNow(){
  const p=document.querySelector("#skyNowLive");if(!p)return;
  try{
    const r=await fetch("/api/sky/now",{cache:"no-store"}),d=await r.json();
    const kicker=p.querySelector(".sky-kicker");
    const radio=!!d.is_radio || /^0\d{3}$/.test(String(d.channelno||""));
    if(kicker)kicker.textContent=radio?"NOW LISTENING":"NOW WATCHING";
    p.querySelector(".sky-programme").textContent=d.programme||d.channel||(radio?"Live radio":"Live TV");
    p.querySelector(".sky-meta").textContent=[d.channelno,d.channel].filter(Boolean).join(" · ");
    p.querySelector(".sky-synopsis").textContent=d.synopsis||"";
    p.querySelector(".sky-state").textContent=d.live?(radio?"LIVE RADIO":"LIVE"):"PLAYBACK";
    const wrap=p.querySelector(".sky-logo-wrap");
    if(wrap&&d.logo){let img=wrap.querySelector("img");if(!img){img=document.createElement("img");wrap.innerHTML="";wrap.appendChild(img)}img.src=d.logo;img.alt=d.channel||"Sky channel";wrap.classList.add("now-channel-logo")}
    applyArtwork(p,d.programmeuuid,"--now-radio-artwork","has-now-radio-artwork");
  }catch(e){}
}
document.querySelector("#skyRadioPrev").onclick=()=>{if(page>0){page--;render()}};
document.querySelector("#skyRadioNext").onclick=()=>{if((page+1)*PAGE_SIZE<stations.length){page++;render()}};
refreshNow();load();if(isLive){setInterval(refreshNow,15000);setInterval(load,60000)}


async function sendRadioSkyKey(key,button){
  if(!isLive)return;
  if(button)button.classList.add("sending");
  try{
    const r=await fetch("/api/sky/key",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key})});
    if(!r.ok)throw new Error(await r.text());
    setTimeout(refreshNow,1200);
  }catch(e){
    if(button){button.classList.add("failed");setTimeout(()=>button.classList.remove("failed"),1000);}
  }finally{
    if(button)setTimeout(()=>button.classList.remove("sending"),180);
  }
}
document.querySelectorAll(".sport-now-controls [data-sky-key]").forEach(button=>{
  button.addEventListener("click",()=>sendRadioSkyKey(button.dataset.skyKey,button));
});

const channelPadOverlay=document.querySelector("#channelPadOverlay");
const channelPadOpen=document.querySelector("#channelPadOpen");
const channelPadClose=document.querySelector("#channelPadClose");
const channelPadDisplay=document.querySelector("#channelPadDisplay");
const channelPadGo=document.querySelector("#channelPadGo");
const channelPadClear=document.querySelector("#channelPadClear");
let channelPadValue="";
function renderChannelPad(){if(channelPadDisplay)channelPadDisplay.textContent=channelPadValue||"—";}
function openChannelPad(){channelPadValue="";renderChannelPad();channelPadOverlay.hidden=false;requestAnimationFrame(()=>channelPadOverlay.classList.add("open"));}
function closeChannelPad(){channelPadOverlay.classList.remove("open");setTimeout(()=>channelPadOverlay.hidden=true,120);}
function addChannelDigit(d){if(channelPadValue.length<4){channelPadValue+=d;renderChannelPad();}}
async function goChannelPad(){
  if(!channelPadValue)return;
  channelPadGo.classList.add("sending");
  try{
    const r=await fetch("/api/sky/channel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({channel:channelPadValue})});
    if(!r.ok)throw new Error(await r.text());
    closeChannelPad();
    setTimeout(refreshNow,1700);
  }catch(e){
    channelPadDisplay.textContent="Error";
    setTimeout(renderChannelPad,900);
  }finally{setTimeout(()=>channelPadGo.classList.remove("sending"),180);}
}
if(channelPadOpen)channelPadOpen.addEventListener("click",openChannelPad);
if(channelPadClose)channelPadClose.addEventListener("click",closeChannelPad);
if(channelPadClear)channelPadClear.addEventListener("click",()=>{channelPadValue="";renderChannelPad();});
if(channelPadGo)channelPadGo.addEventListener("click",goChannelPad);
document.querySelectorAll("[data-pad-digit]").forEach(b=>b.addEventListener("click",()=>addChannelDigit(b.dataset.padDigit)));
document.querySelectorAll("[data-pad-key]").forEach(b=>b.addEventListener("click",()=>sendRadioSkyKey(b.dataset.padKey,b)));
if(channelPadOverlay)channelPadOverlay.addEventListener("click",e=>{if(e.target===channelPadOverlay)closeChannelPad();});
document.addEventListener("keydown",e=>{
  if(!channelPadOverlay||channelPadOverlay.hidden)return;
  if(/^\d$/.test(e.key))addChannelDigit(e.key);
  else if(e.key==="Backspace"){channelPadValue=channelPadValue.slice(0,-1);renderChannelPad();}
  else if(e.key==="Enter")goChannelPad();
  else if(e.key==="Escape")closeChannelPad();
});
