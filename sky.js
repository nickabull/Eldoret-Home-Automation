const statusEl=document.querySelector("#skyRemoteStatus");
const keys=document.querySelectorAll("[data-sky-key]");
const isLive=location.protocol==="http:" || location.hostname.endsWith(".ts.net");
async function sendSkyKey(key,button){
  if(!isLive){statusEl.textContent="Open through the local Chromebook connector to control Sky Q.";return;}
  statusEl.textContent="Sending "+key+"…";
  button.classList.add("sending");
  try{
    const res=await fetch("/api/sky/key",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key})});
    if(!res.ok)throw new Error(await res.text());
    statusEl.textContent="Sent: "+key;
  }catch(e){statusEl.textContent="Sky Q control failed";}
  finally{setTimeout(()=>button.classList.remove("sending"),180);}
}
keys.forEach(button=>button.addEventListener("click",()=>sendSkyKey(button.dataset.skyKey,button)));

const viewTabs=document.querySelectorAll("[data-sky-view]");
const remoteView=document.querySelector("#skyRemote");
const channelView=document.querySelector("#skyChannels");
viewTabs.forEach(tab=>tab.addEventListener("click",()=>{
  viewTabs.forEach(x=>x.classList.remove("active"));
  tab.classList.add("active");
  const channels=tab.dataset.skyView==="channels";
  remoteView.hidden=channels;
  channelView.hidden=!channels;
}));
document.querySelectorAll("[data-channel]").forEach(button=>button.addEventListener("click",async()=>{
  if(!isLive){statusEl.textContent="Open through the local Chromebook connector to change channel.";return;}
  const channel=button.dataset.channel;
  button.classList.add("sending");
  try{
    const res=await fetch("/api/sky/channel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({channel})});
    if(!res.ok)throw new Error(await res.text());
    button.classList.add("selected");
    setTimeout(()=>button.classList.remove("selected"),900);
  }catch(e){
    statusEl.textContent="Channel change failed";
  }finally{
    setTimeout(()=>button.classList.remove("sending"),180);
  }
}));

function skyClock(value){
  if(!value)return "";
  const d=new Date(value);
  if(Number.isNaN(d.getTime()))return "";
  return d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
}
async function refreshSkyLive(){
  const panel=document.querySelector("#skyNowLive");
  if(!panel)return;
  const title=panel.querySelector(".sky-programme");
  const meta=panel.querySelector(".sky-meta");
  const synopsis=panel.querySelector(".sky-synopsis");
  const badge=panel.querySelector(".sky-state");
  const kicker=panel.querySelector(".sky-kicker");
  if(!isLive){
    title.textContent="Local connection required";
    meta.textContent="Open Eldoret through the Chromebook/Pi connector.";
    badge.textContent="LOCAL";
    return;
  }
  try{
    const res=await fetch("/api/sky/now",{cache:"no-store"});
    const data=await res.json();
    if(!data.available){
      title.textContent="Sky Q media unavailable";
      meta.textContent=data.error||"Unable to read current media.";
      synopsis.textContent="";
      badge.textContent="UNKNOWN";
      return;
    }
    if(data.live){
      const radio=!!data.is_radio || /^0\d{3}$/.test(String(data.channelno||""));
      if(kicker)kicker.textContent=radio?"NOW LISTENING":"NOW WATCHING";
      title.textContent=data.programme||data.channel||(radio?"Live radio":"Live TV");
      const bits=[];
      if(data.channelno)bits.push(data.channelno);
      if(data.channel)bits.push(data.channel);
      const st=skyClock(data.start), en=skyClock(data.end);
      if(st&&en)bits.push(st+"–"+en);
      if(!data.channel && data.sid)bits.push("Sky service "+data.sid);
      meta.textContent=bits.join(" · ");
      synopsis.textContent=data.synopsis||"";
      badge.textContent=radio?"LIVE RADIO":"LIVE";
    }else{
      title.textContent=data.playback==="recording"?"Recording playback":"Sky Q active";
      meta.textContent="Non-live playback";
      synopsis.textContent="";
      badge.textContent="PLAYBACK";
    }
  }catch(e){
    title.textContent="Unable to read Sky Q";
    meta.textContent="Remote control can still work even if now-playing readback fails.";
    synopsis.textContent="";
    badge.textContent="UNKNOWN";
  }
}
refreshSkyLive();
if(isLive)setInterval(refreshSkyLive,15000);

const searchInput=document.querySelector("#skyChannelSearch");
const searchResults=document.querySelector("#skySearchResults");
let searchTimer=null;
async function searchSkyChannels(q){
  if(!searchResults)return;
  const query=(q||"").trim();
  if(query.length<2){searchResults.innerHTML="";return;}
  searchResults.innerHTML='<div class="search-note">Searching…</div>';
  try{
    const r=await fetch("/api/sky/search?q="+encodeURIComponent(query),{cache:"no-store"});
    const data=await r.json();
    const items=(data.results||[]).slice(0,12);
    if(!items.length){searchResults.innerHTML='<div class="search-note">No matching channels</div>';return;}
    searchResults.innerHTML=items.map(item=>
      '<button type="button" class="sky-search-result" data-channel="'+item.channelno+'">'+
      (item.logo?'<img src="'+item.logo+'" alt="">':'')+
      '<span><strong>'+item.channel+'</strong><small>'+item.channelno+(item.programme?' · '+item.programme:'')+'</small></span></button>'
    ).join("");
    searchResults.querySelectorAll("[data-channel]").forEach(button=>button.addEventListener("click",async()=>{
      button.classList.add("sending");
      try{
        const r=await fetch("/api/sky/channel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({channel:button.dataset.channel})});
        if(!r.ok)throw new Error(await r.text());
        statusEl.textContent="Tuned to "+button.dataset.channel;
        setTimeout(refreshSkyLive,1600);
      }catch(e){statusEl.textContent="Channel change failed";}
      finally{setTimeout(()=>button.classList.remove("sending"),180);}
    }));
  }catch(e){searchResults.innerHTML='<div class="search-note">Search unavailable</div>';}
}
if(searchInput)searchInput.addEventListener("input",()=>{
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>searchSkyChannels(searchInput.value),220);
});
