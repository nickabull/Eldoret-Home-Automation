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
