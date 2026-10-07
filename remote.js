(()=> {
  const isRemote=location.hostname.endsWith("github.io");
  if(!isRemote) return;
  const TOPIC="https://ntfy.sh/eldoret-live-4f1c7a92d8e63b5a0f4d2c9b71e8a605/json?poll=1&since=10m";
  let cache=null,cacheAt=0;
  async function loadState(){
    const now=Date.now();
    if(cache && now-cacheAt<15000) return cache;
    const r=await window.__eldoretNativeFetch(TOPIC,{cache:"no-store"});
    const text=await r.text();
    const lines=text.trim().split(/\n+/).filter(Boolean);
    let state=null;
    for(let i=lines.length-1;i>=0;i--){
      try{
        const evt=JSON.parse(lines[i]);
        if(evt.event!=="message") continue;
        const msg=JSON.parse(evt.message||"{}");
        if(msg.generated_at){state=msg;break;}
      }catch(e){}
    }
    if(!state) throw new Error("No remote state");
    cache=state; cacheAt=now; return state;
  }
  function response(data,status=200){
    return new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json"}});
  }
  window.__eldoretNativeFetch=window.fetch.bind(window);
  window.fetch=async function(input,init={}){
    const url=typeof input==="string"?input:input.url;
    let u;
    try{u=new URL(url,location.href)}catch(e){return window.__eldoretNativeFetch(input,init)}
    if(!u.pathname.startsWith("/api/")) return window.__eldoretNativeFetch(input,init);
    if((init.method||"GET").toUpperCase()!=="GET"){
      return response({ok:false,remote:true,read_only:true,error:"Remote Eldoret is read-only."},403);
    }
    try{
      const s=await loadState();
      if(u.pathname==="/api/sky/now") return response(s.sky_now||{available:false,remote:true});
      if(u.pathname==="/api/printer/status") return response(s.printer||{online:false,remote:true});
      if(u.pathname==="/api/playstation/status") return response(s.playstation||{online:false,remote:true});
      if(u.pathname==="/api/hue/group"){
        const key=(u.searchParams.get("bridge")||"")+":"+(u.searchParams.get("group")||"");
        return response(s.hue&&s.hue[key]?s.hue[key]:{state:{any_on:false},action:{bri:null},remote:true});
      }
      if(u.pathname==="/api/remote/state") return response(s);
      if(u.pathname==="/api/network/status"){
        return response({devices:[],summary:s.summary||{},remote:true});
      }
      return response({remote:true,read_only:true,error:"This live endpoint is not mirrored remotely yet."},404);
    }catch(e){
      return response({remote:true,error:"Remote state unavailable"},503);
    }
  };

  const badge=document.createElement("div");
  badge.className="remote-live-badge";
  badge.innerHTML='<span></span>REMOTE LIVE · READ ONLY';
  document.addEventListener("DOMContentLoaded",()=>document.body.appendChild(badge));
})();