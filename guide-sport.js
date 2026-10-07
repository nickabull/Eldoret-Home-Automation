
let eldoretPending=null,eldoretPendingTimer=null;
function clearEldoretPending(){
  if(eldoretPending&&eldoretPending.el)eldoretPending.el.classList.remove("eldoret-pending");
  eldoretPending=null; clearTimeout(eldoretPendingTimer);
  const box=document.querySelector("#eldoretConfirm"); if(box)box.remove();
}
function stageEldoretAction(label,run,el){
  clearEldoretPending(); if(el)el.classList.add("eldoret-pending");
  eldoretPending={run,el};
  const box=document.createElement("div"); box.id="eldoretConfirm"; box.className="eldoret-confirm";
  box.innerHTML='<span>'+label+'</span><button type="button">CONFIRM</button>';
  box.querySelector("button").onclick=async()=>{const p=eldoretPending;clearEldoretPending();if(p)await p.run();};
  document.body.appendChild(box);
  eldoretPendingTimer=setTimeout(clearEldoretPending,10000);
}
const isLive=location.protocol==="http:" || location.hostname.endsWith(".ts.net");
function skyClock(value){if(!value)return "";const d=new Date(value);if(Number.isNaN(d.getTime()))return "";return d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});}
async function refreshNow(){
  const p=document.querySelector("#skyNowLive"); if(!p)return;
  const title=p.querySelector(".sky-programme"), meta=p.querySelector(".sky-meta"), syn=p.querySelector(".sky-synopsis"), badge=p.querySelector(".sky-state"), kicker=p.querySelector(".sky-kicker");
  try{
    const r=await fetch("/api/sky/now",{cache:"no-store"}); const d=await r.json();
    if(!d.available) throw new Error(d.error||"Unavailable");
    if(d.live){
      const radio=!!d.is_radio || /^0\d{3}$/.test(String(d.channelno||""));
      if(kicker)kicker.textContent=radio?"NOW LISTENING":"NOW WATCHING";
      title.textContent=d.programme||d.channel||(radio?"Live radio":"Live TV");
      const b=[]; if(d.channelno)b.push(d.channelno); if(d.channel)b.push(d.channel);
      const s=skyClock(d.start),e=skyClock(d.end); if(s&&e)b.push(s+"–"+e);
      meta.textContent=b.join(" · "); syn.textContent=d.synopsis||""; badge.textContent=radio?"LIVE RADIO":"LIVE";
      if(d.programmeuuid){
        p.style.setProperty("--now-artwork",'url("'+programmeArtworkUrl(d.programmeuuid)+'")');
        p.classList.add("has-now-artwork");
      }else{p.classList.remove("has-now-artwork");p.style.removeProperty("--now-artwork");}
    }else{title.textContent="Sky Q playback";meta.textContent="Non-live playback";syn.textContent="";badge.textContent="PLAYBACK";}
  }catch(e){title.textContent="Sky Q unavailable";meta.textContent="Control may still work.";syn.textContent="";badge.textContent="UNKNOWN";}
}
async function tune(button){
  if(!isLive)return;
  const channel=button.dataset.channel;
  button.classList.add("sending");
  try{
    const r=await fetch("/api/sky/channel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({channel})});
    if(!r.ok)throw new Error(await r.text());
    document.querySelectorAll(".sport-channel").forEach(x=>x.classList.remove("selected"));
    button.classList.add("selected");
    setTimeout(refreshNow,1800);
  }catch(e){button.classList.add("failed");setTimeout(()=>button.classList.remove("failed"),1200);}
  finally{setTimeout(()=>button.classList.remove("sending"),180);}
}

refreshNow(); if(isLive)setInterval(refreshNow,15000);

function programmeArtworkUrl(uuid){
  return uuid ? "https://images.metadata.sky.com/pd-image/"+encodeURIComponent(uuid)+"/16-9" : "";
}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function renderGuideCard(item){
  const no=String(item.channelno||"");
  const b=document.createElement("button"); b.className="sport-channel"; b.dataset.channel=no;
  b.innerHTML='<img class="sport-channel-logo" alt=""><strong>'+esc(item.channel||item.requested||"Channel")+'</strong><div class="sport-onair"><span>On now</span><b>'+esc(item.programme||"Programme unavailable")+'</b></div><small>'+esc(no)+'</small>';
  const logo=b.querySelector(".sport-channel-logo"); if(item.logo){logo.src=item.logo}else logo.hidden=true;
  if(item.programmeuuid){
    const art=programmeArtworkUrl(item.programmeuuid), probe=new Image();
    probe.onload=()=>{b.style.setProperty("--programme-artwork",'url("'+art+'")');b.classList.add("has-programme-artwork");};
    probe.src=art;
  }
  const onair=b.querySelector(".sport-onair"),nowTime=[skyClock(item.start),skyClock(item.end)].filter(Boolean).join("–"),nextTime=item.next&&item.next.start?skyClock(item.next.start):"";
  onair.innerHTML='<span>On now'+(nowTime?' · '+nowTime:'')+'</span><b>'+esc(item.programme||"Programme unavailable")+'</b>'+(item.synopsis?'<p class="sport-synopsis">'+esc(item.synopsis)+'</p>':'')+(item.next&&item.next.programme?'<div class="sport-next"><span>Next'+(nextTime?' · '+nextTime:'')+'</span><b>'+esc(item.next.programme)+'</b></div>':'');
  b.addEventListener("click",()=>stageEldoretAction("Channel "+no,()=>tune(b),b)); return b;
}
let guidePage=0;
async function refreshGuide(){
 const group=document.body.dataset.guideGroup,grid=document.querySelector("#guideChannelGrid"); if(!group||!grid)return;
 const start=document.body.dataset.guideStart,end=document.body.dataset.guideEnd||"399";
 try{
   const topPicks=document.body.dataset.guideTopPicks==="1";
   const url=topPicks
     ? "/api/sky/top-picks?page="+guidePage+"&size=14"
     : start
       ? "/api/sky/guide-range?start="+encodeURIComponent(start)+"&end="+encodeURIComponent(end)+"&page="+guidePage+"&size=14"
       : "/api/sky/guide?group="+encodeURIComponent(group);
   const r=await fetch(url,{cache:"no-store"}),data=await r.json();
   grid.replaceChildren(...(data.channels||[]).filter(x=>x.channelno).map(renderGuideCard));
   const label=document.querySelector("#guidePageLabel"),prev=document.querySelector("#guidePrev"),next=document.querySelector("#guideNext");
   if(label)label.textContent=((data.page??0)+1)+" / "+(data.pages||1);
   if(prev)prev.disabled=(data.page??0)<=0;
   if(next)next.disabled=(data.page??0)>=(data.pages||1)-1;
 } catch(e){grid.innerHTML='<div class="guide-empty">Guide unavailable</div>';}
}
const gp=document.querySelector("#guidePrev"),gn=document.querySelector("#guideNext");
if(gp)gp.addEventListener("click",()=>{if(guidePage>0){guidePage--;refreshGuide()}});
if(gn)gn.addEventListener("click",()=>{guidePage++;refreshGuide()});
refreshGuide(); if(isLive)setInterval(refreshGuide,60000);

async function sendSportSkyKey(key,button){
  if(!isLive)return;
  button.classList.add("sending");
  try{
    const r=await fetch("/api/sky/key",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key})});
    if(!r.ok)throw new Error(await r.text());
    setTimeout(refreshNow,1200);
  }catch(e){button.classList.add("failed");setTimeout(()=>button.classList.remove("failed"),1000);}
  finally{setTimeout(()=>button.classList.remove("sending"),180);}
}
document.querySelectorAll(".sport-now-controls [data-sky-key]").forEach(button=>{
  button.addEventListener("click",()=>sendSportSkyKey(button.dataset.skyKey,button));
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
if(channelPadGo)channelPadGo.addEventListener("click",()=>{if(channelPadValue)stageEldoretAction("Channel "+channelPadValue,goChannelPad,channelPadGo);});
document.querySelectorAll("[data-pad-digit]").forEach(b=>b.addEventListener("click",()=>addChannelDigit(b.dataset.padDigit)));
document.querySelectorAll("[data-pad-key]").forEach(b=>b.addEventListener("click",()=>sendSportSkyKey(b.dataset.padKey,b)));
if(channelPadOverlay)channelPadOverlay.addEventListener("click",e=>{if(e.target===channelPadOverlay)closeChannelPad();});
document.addEventListener("keydown",e=>{
  if(!channelPadOverlay||channelPadOverlay.hidden)return;
  if(/^\d$/.test(e.key))addChannelDigit(e.key);
  else if(e.key==="Backspace"){channelPadValue=channelPadValue.slice(0,-1);renderChannelPad();}
  else if(e.key==="Enter")goChannelPad();
  else if(e.key==="Escape")closeChannelPad();
});
