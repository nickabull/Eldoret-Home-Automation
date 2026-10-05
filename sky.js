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
