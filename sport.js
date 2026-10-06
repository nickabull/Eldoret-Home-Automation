const isLive=location.protocol==="http:";
function skyClock(value){if(!value)return "";const d=new Date(value);if(Number.isNaN(d.getTime()))return "";return d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});}
async function refreshNow(){
  const p=document.querySelector("#skyNowLive"); if(!p)return;
  const title=p.querySelector(".sky-programme"), meta=p.querySelector(".sky-meta"), syn=p.querySelector(".sky-synopsis"), badge=p.querySelector(".sky-state");
  try{
    const r=await fetch("/api/sky/now",{cache:"no-store"}); const d=await r.json();
    if(!d.available) throw new Error(d.error||"Unavailable");
    if(d.live){
      title.textContent=d.programme||d.channel||"Live TV";
      const b=[]; if(d.channelno)b.push(d.channelno); if(d.channel)b.push(d.channel);
      const s=skyClock(d.start),e=skyClock(d.end); if(s&&e)b.push(s+"–"+e);
      meta.textContent=b.join(" · "); syn.textContent=d.synopsis||""; badge.textContent="LIVE";
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
document.querySelectorAll(".sport-channel").forEach(b=>b.addEventListener("click",()=>tune(b)));
refreshNow(); if(isLive)setInterval(refreshNow,15000);

async function refreshSportGuide(){
  try{
    const r=await fetch("/api/sky/sport-guide",{cache:"no-store"});
    const data=await r.json();
    const byNo=new Map((data.channels||[]).map(x=>[String(x.channelno),x]));
    document.querySelectorAll(".sport-channel[data-channel]").forEach(button=>{
      const item=byNo.get(button.dataset.channel);
      const logo=button.querySelector(".sport-channel-logo");
      const onair=button.querySelector(".sport-onair");
      if(!item){
        if(onair) onair.innerHTML='<span>On now</span><b>Programme unavailable</b>';
        return;
      }
      if(logo && item.logo){logo.src=item.logo;logo.hidden=false;}
      if(onair){
        const nowTime=[skyClock(item.start),skyClock(item.end)].filter(Boolean).join("–");
        const nextTime=item.next&&item.next.start?skyClock(item.next.start):"";
        onair.innerHTML=
          '<span>On now'+(nowTime?' · '+nowTime:'')+'</span>'+
          '<b>'+(item.programme||"Programme unavailable")+'</b>'+
          (item.synopsis?'<p class="sport-synopsis">'+item.synopsis+'</p>':'')+
          (item.next&&item.next.programme?
            '<div class="sport-next"><span>Next'+(nextTime?' · '+nextTime:'')+'</span><b>'+item.next.programme+'</b></div>':'');
      }
      button.title=[item.channel,item.programme].filter(Boolean).join(" · ");
    });
  }catch(e){
    document.querySelectorAll(".sport-onair").forEach(x=>x.innerHTML='<span>Guide</span><b>Unavailable</b>');
  }
}
refreshSportGuide();
if(isLive)setInterval(refreshSportGuide,60000);

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
