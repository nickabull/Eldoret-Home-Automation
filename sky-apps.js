const isLive=location.protocol==="http:"||location.hostname.endsWith(".ts.net");
const demoApps=[
 ["Netflix","https://www.netflix.com/","N"],["YouTube","https://www.youtube.com/","Y"],["BBC iPlayer","https://www.bbc.co.uk/iplayer","BBC"],["ITVX","https://www.itv.com/","ITV"],
 ["Disney+","https://www.disneyplus.com/","D+"],["Prime Video","https://www.primevideo.com/","P"],["Spotify","https://open.spotify.com/","S"],["STV Player","https://player.stv.tv/","STV"],
 ["Channel 4","https://www.channel4.com/","4"],["My5","https://www.channel5.com/","5"],["Sky Store","https://www.skystore.com/","SKY"],["Paramount+","https://www.paramountplus.com/","P+"]
];
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function demo(){
 const g=document.querySelector("#skyAppsGrid"),n=document.querySelector("#skyAppsCount");
 n.textContent="PREVIEW · "+demoApps.length+" apps";
 g.innerHTML=demoApps.map(([title,url,abbr])=>'<a class="sport-channel sky-app-card" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer" aria-label="Open '+esc(title)+' website"><div class="sky-app-fallback">'+esc(abbr)+'</div><strong>'+esc(title)+'</strong><div class="sport-onair"><span>Preview only</span><b>Visit website ↗</b></div></a>').join("");
 const now=document.querySelector("#skyNowLive");
 if(now){now.querySelector(".sky-programme").textContent="Sky Q offline preview";now.querySelector(".sky-meta").textContent="Connect to the home Eldoret service for live status.";now.querySelector(".sky-state").textContent="DEMO"}
 document.querySelectorAll("[data-sky-key],#channelPadOpen").forEach(b=>{b.disabled=true;b.title="Available when connected to the private Eldoret home service"});
 const status=document.querySelector("header .status");if(status)status.textContent="Preview mode · no Sky Q connection";
}
async function load(){
 if(!isLive){demo();return}
 const g=document.querySelector("#skyAppsGrid"),n=document.querySelector("#skyAppsCount");
 try{
  const r=await fetch("/api/sky/apps",{cache:"no-store"});if(!r.ok)throw new Error("Apps API unavailable");
  const d=await r.json(),a=d.apps||[];if(!a.length)throw new Error("No apps returned");
  n.textContent=a.length+" apps";
  g.innerHTML=a.slice(0,30).map(x=>'<button class="sport-channel sky-app-card" data-appid="'+esc(x.appid)+'">'+(x.icon?'<img class="sky-app-icon" src="'+esc(x.icon)+'" alt="">':'<div class="sky-app-fallback">'+esc((x.title||"APP").slice(0,2).toUpperCase())+'</div>')+'<strong>'+esc(x.title)+'</strong><div class="sport-onair"><span>Sky Q app</span><b>Tap to open</b></div></button>').join("");
  g.querySelectorAll("[data-appid]").forEach(b=>b.onclick=()=>launch(b));
 }catch(e){demo()}
}
async function launch(b){
 if(!isLive)return;
 b.classList.add("sending");
 try{const r=await fetch("/api/sky/app/launch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({appid:b.dataset.appid})});if(!r.ok)throw Error("Launch failed")}
 catch(e){b.classList.add("failed");setTimeout(()=>b.classList.remove("failed"),1000)}
 finally{setTimeout(()=>b.classList.remove("sending"),1800)}
}
load();
