const statusEl=document.querySelector("#skyRemoteStatus");
const keys=document.querySelectorAll("[data-sky-key]");
const isLive=location.protocol==="http:";
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
      title.textContent=data.programme||data.channel||"Live TV";
      const bits=[];
      if(data.channelno)bits.push(data.channelno);
      if(data.channel)bits.push(data.channel);
      const st=skyClock(data.start), en=skyClock(data.end);
      if(st&&en)bits.push(st+"–"+en);
      if(!data.channel && data.sid)bits.push("Sky service "+data.sid);
      meta.textContent=bits.join(" · ");
      synopsis.textContent=data.synopsis||"";
      badge.textContent="LIVE";
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
