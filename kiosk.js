// Return detailed views to Home after two minutes without interaction.
(()=>{
 const HOME=new URL('index.html',location.href).href,TIMEOUT=120000;
 if(location.pathname==='/'||location.pathname.endsWith('/index.html'))return;
 let last=Date.now();
 const active=()=>{last=Date.now();};
 ['pointerdown','pointermove','keydown','touchstart','wheel','input'].forEach(name=>addEventListener(name,active,{passive:true}));
 setInterval(()=>{
  // Let an active radio player continue; navigation would stop its audio.
  if([...document.querySelectorAll('audio,video')].some(media=>!media.paused&&!media.ended)){active();return;}
  if(!document.hidden&&Date.now()-last>=TIMEOUT)location.assign(HOME);
 },1000);
})();


// Eldoret network fault strip v1. Read-only client monitor.
// Uses existing /api/network/status TCP/service probes. A missing response is
// not evidence of failure until a device was previously healthy and fails
// three consecutive polls; sleeping/unchecked devices remain unclassified.
(()=>{
  const KEY='eldoret-health-alerts-v1';
  const WATCH=new Set(['10.0.0.1','10.0.0.2','10.0.0.4','10.0.0.6','10.0.0.7','10.0.0.8','10.0.0.9','10.0.0.18','10.0.0.22']);
  const PERIOD=30000,FAILURES=3;
  let records={};
  try{records=JSON.parse(sessionStorage.getItem(KEY)||'{}')||{};}catch(_){records={};}
  if(typeof records!=='object'||Array.isArray(records)) records={};
  // Never persist unchecked/unknown devices as false failures.
  function store(){try{sessionStorage.setItem(KEY,JSON.stringify(records));}catch(_){}}
  const css=document.createElement('style');
  css.textContent=`
#eldoret-health-alert{position:fixed;left:12px;bottom:12px;z-index:2147483000;max-width:min(650px,calc(100vw - 24px));box-sizing:border-box;background:#321c21;color:#fff;border:1px solid #e7877a;border-radius:13px;box-shadow:0 8px 30px #0009;padding:9px 12px;font:13px/1.35 system-ui,-apple-system,sans-serif;display:none}
#eldoret-health-alert[data-active="true"]{display:block}
#eldoret-health-alert .eha-row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
#eldoret-health-alert .eha-heart{font-size:21px;color:#ff857c;line-height:1}
#eldoret-health-alert .eha-heading{font-weight:700;flex:1;min-width:160px}
#eldoret-health-alert .eha-detail{font-size:11px;color:#f4c6c0;flex-basis:100%}
#eldoret-health-alert button,#eldoret-health-alert a{color:#fff;background:#61333b;border:1px solid #a85f62;border-radius:7px;font:inherit;padding:6px 9px;text-decoration:none;cursor:pointer;min-height:30px}
#eldoret-health-alert button:focus-visible,#eldoret-health-alert a:focus-visible{outline:2px solid #fff;outline-offset:2px}
#eldoret-health-alert[data-ack="true"]{background:#372a1c;border-color:#d6ae72}
#eldoret-health-alert[data-ack="true"] .eha-heart{color:#e3b976}
@media(max-width:550px){#eldoret-health-alert{font-size:12px;bottom:64px;left:8px;right:8px;max-width:none;padding:7px 9px}#eldoret-health-alert .eha-detail{display:none}}
@media(prefers-reduced-motion:no-preference){#eldoret-health-alert[data-ack="false"] .eha-heart{animation:eha-beat 1.4s ease-in-out infinite}@keyframes eha-beat{0%,100%{transform:scale(1)}20%,44%{transform:scale(1.18)}31%{transform:scale(.93)}}}
`;
  document.head.appendChild(css);
  const strip=document.createElement('aside');strip.id='eldoret-health-alert';strip.setAttribute('role','status');strip.setAttribute('aria-live','polite');
  const line=document.createElement('div');line.className='eha-row';
  const heart=document.createElement('span');heart.className='eha-heart';heart.textContent='♥';heart.setAttribute('aria-hidden','true');
  const heading=document.createElement('span');heading.className='eha-heading';
  const ack=document.createElement('button');ack.type='button';ack.textContent='Acknowledge';
  const investigate=document.createElement('a');investigate.href='network.html';investigate.textContent='Investigate';
  const detail=document.createElement('span');detail.className='eha-detail';
  line.append(heart,heading,ack,investigate,detail);strip.append(line);
  document.body.appendChild(strip);
  const stamp=t=>t?new Date(t).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}):'not recorded';
  function render(){
    const faults=Object.entries(records).filter(([,r])=>r&&r.failed&&WATCH.has(r.ip));
    strip.dataset.active=String(faults.length>0);
    if(!faults.length)return;
    const unacked=faults.filter(([,r])=>!r.ack);
    strip.dataset.ack=String(unacked.length===0);
    const names=faults.map(([,r])=>r.name||r.ip);
    heading.textContent=unacked.length?names.slice(0,2).join(', ')+(faults.length>2?' +'+(faults.length-2):'')+' — unreachable':faults.length+' network fault'+(faults.length===1?'':'s')+' acknowledged';
    detail.textContent='Read-only service checks · Last successful: '+faults.map(([,r])=>(r.name||r.ip)+' '+stamp(r.lastGood)).slice(0,2).join(' · ');
    ack.hidden=unacked.length===0;
    investigate.textContent='Investigate ('+faults.length+')';
  }
  ack.addEventListener('click',()=>{for(const r of Object.values(records)){if(r&&r.failed)r.ack=true;}store();render();});
  let busy=false;
  async function refresh(){
    if(busy)return;busy=true;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch('/api/network/status',{cache:'no-store',signal:controller.signal,credentials:'same-origin'});
      if(!response.ok)throw Error('network status unavailable');
      const payload=await response.json();
      if(!Array.isArray(payload.devices)||payload.error)throw Error('invalid network status');
      const now=Date.now();
      for(const device of payload.devices){
        if(!device||!WATCH.has(device.ip)||typeof device.online!=='boolean')continue;
        const r=records[device.ip]||{ip:device.ip,failCount:0,failed:false,ack:false,lastGood:null};
        r.name=device.name||r.name||device.ip;
        r.lastChecked=now;
        if(device.online){
          r.lastGood=now;r.hadSuccess=true;r.failCount=0;r.failed=false;r.ack=false;
        }else if(r.hadSuccess){
          r.failCount=Math.min(FAILURES,Number(r.failCount||0)+1);
          if(r.failCount>=FAILURES)r.failed=true;
        }
        records[device.ip]=r;
      }
      store();render();
    }catch(_){
      // Connector outage is not proof that every monitored device failed.
      // Keep any already-open incident visible, but do not create new ones.
      render();
    }finally{clearTimeout(timer);busy=false;}
  }
  render();refresh();setInterval(refresh,PERIOD);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
