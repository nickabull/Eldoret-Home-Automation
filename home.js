(()=>{
 'use strict';
 const $=id=>document.getElementById(id), health=new Map(), checks=new Map(), busy=new Set();
 const icons={router:'<rect x="3" y="11" width="18" height="9" rx="2"/><path d="M7 11V4m10 7V4M7 16h.1m4 0h.1m4 0h2"/>',lights:'<path d="M9 18h6m-5 3h4M8 13a6 6 0 1 1 8 0c-1 1-1 2-1 3H9c0-1 0-2-1-3Z"/>',tv:'<rect x="2" y="4" width="20" height="14" rx="2"/><path d="M8 22h8m-4-4v4"/>',game:'<path d="M7 7h10c4 0 6 12 3 13-2 1-5-4-6-4h-4c-1 0-4 5-6 4C1 19 3 7 7 7Z"/><path d="M6 11v5m-2-2h5m7-2h.1m3 3h.1"/>',wifi:'<path d="M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0m-11 4a6 6 0 0 1 8 0m-4 4h.1"/>',printer:'<path d="M6 8V2h12v6M6 18H2V8h20v10h-4M6 14h12v8H6zM18 11h.1"/>',dishwasher:'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M4 7h16M7 4.5h.1m3 0h.1"/><circle cx="12" cy="14" r="4"/>'};
 document.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[el.dataset.icon]+'</svg>';});
 function clock(){const now=new Date();$('homeTime').textContent=now.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});$('homeDate').textContent=now.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});}
 clock();setInterval(clock,1000);
 function overall(){
  const list=[...health.values()], good=list.filter(x=>x==='good').length, warn=list.filter(x=>x==='warning').length, missing=7-good-warn;
  $('homeSummary').textContent=(good+warn)?(good+warn)+' of 7 areas reporting in. '+(warn?'A few things are worth a look.':'A little peace of mind, all in one place.'):'Your home’s live details, together in one place.';
  $('homeHealthTitle').textContent=warn?warn+' thing'+(warn===1?'':'s')+' to look at':good===7?'Your world is OK.':good?'Home is checking in.':'Connecting the dots';
  $('homeHealthDetail').textContent=warn?'Amber cards have the details.':missing?missing+' area'+(missing===1?' is':'s are')+' waiting for a live reading or connection.':'All seven monitored areas are reporting normally.';
  $('homeHealthIcon').textContent=warn?'!':good===7?'✓':'⌁';
  document.querySelector('.home-health').classList.toggle('attention',warn>0);
 }
 function card(id,state,badge,title,detail){const el=$('vital-'+id);el.dataset.state=state;el.querySelector('.vital-state').textContent=badge;el.querySelector('.vital-title').textContent=title;el.querySelector('.vital-detail').textContent=detail;health.set(id,state);overall();}
 const number=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
 const setSpeed=(id,v)=>{const el=$(id);el.replaceChildren(document.createTextNode(number(v)?v.toFixed(2):'—'));const unit=document.createElement('span');unit.textContent=' Mbps';el.append(unit);};
 function plot(history){const rows=(history||[]).slice(-60),max=Math.max(1,...rows.flatMap(x=>[x.download,x.upload]).filter(number));for(const [key,id]of[['download','homeDownLine'],['upload','homeUpLine']]){let open=false,d='';rows.forEach((r,i)=>{if(!number(r[key])){open=false;return;}d+=(open?'L':'M')+(360-(rows.length-1-i)*360/59)+','+(43-r[key]*40/max)+' ';open=true;});$(id).setAttribute('d',d);}document.querySelector('.home-spark').setAttribute('aria-label',rows.some(r=>number(r.download)||number(r.upload))?'Recent download and upload traffic':'Waiting for live WAN2 traffic');}
 function router(p){
  const fresh=p.online===true&&p.checked_at&&Date.now()-Date.parse(p.checked_at)<25000;
  const linkDown=fresh&&p.link_up===false;
  card('router',!fresh?'unknown':linkDown?'warning':'good',!fresh?'WAITING':linkDown?'LINK DOWN':'CONNECTED',fresh?(linkDown?'WAN2 needs a look.':'Your router is connected.'):'Waiting for router readings',fresh?'Current WAN2 use · updates every 5 seconds':p.message||'Live speeds are not available yet.');
  setSpeed('homeDown',fresh?p.download_mbps:null);setSpeed('homeUp',fresh?p.upload_mbps:null);plot(fresh?p.history:[]);
 }
 function lights(p){
  const b=p.bridges||[];if(b.length!==2)throw Error('Missing bridge readings');
  const online=b.filter(x=>x.online),total=online.reduce((n,x)=>n+(x.total||0),0);
  card('lights',online.length===2?'good':'unknown',online.length===2?'CONNECTED':'WAITING',online.length===2?'Your Hue bridges are connected.':'Waiting for Hue bridge readings',online.length+' / 2 bridges responding · '+total+' lights in their groups');
  $('homeLightsMeta').textContent=online.length===2?'House + utility · tap for room controls':'House and utility status not fully available.';
 }
 function sky(p){
  if(p.available){const title=p.programme||(p.playback==='recording'?'Playing a recording':p.live?(p.channel||'Live television'):'Sky Q is playing');card('sky','good',p.live?'WATCHING':'PLAYING',title,p.channel?['Sky Q',p.channel,p.channelno].filter(Boolean).join(' · '):'Programme details are not supplied for this playback.');$('homeSkyMeta').textContent=p.start&&p.end?new Date(p.start).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})+' – '+new Date(p.end).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}):'Live from Sky Q.';}
  else{card('sky','unknown','NO READING','A quiet moment on the sofa.','No current programme reported · Sky Q may be in standby.');$('homeSkyMeta').textContent='Tap to open Sky Q.';}
 }
 function jesse(p){
  if(p.online&&p.running_app_name)card('jesse','good','PLAYING',p.running_app_name,'Jesse’s PS5 reports this game or app.');
  else if(p.online)card('jesse','good','CONNECTED','Jesse’s PlayStation is connected.','No game or app title is currently reported.');
  else card('jesse','unknown','NO REPLY','No word from the PlayStation.','It may be off or resting · no game is being reported.');
 }
 function devices(p){
  const aps=(p.devices||[]).filter(x=>/^UniFi\b/i.test(x.name||''));
  if(aps.length!==4)throw Error('Missing access point readings');
  const count=aps.filter(x=>x.online===true).length;
  card('wifi',count===4?'good':'unknown',count===4?'REACHABLE':'CHECKING',count===4?'Four access points, all reachable.':count+' / 4 access points reachable','Network replies only · detailed UniFi health comes with the controller.');
  $('homeAps').replaceChildren(...aps.map(ap=>{const span=document.createElement('span');span.className='ap-pill'+(ap.online?' reachable':'');span.textContent=(ap.name||'').replace(/^UniFi\s*/i,'');span.title=ap.name+': '+(ap.online?'responding':'no service reply');return span;}));
 }
 card('dishwasher','unknown','NOT LINKED','Dishwasher, waiting to connect.','Wash cycle and time remaining are not connected yet.');
 function printer(p){
  const ink=(p.ink||[]).filter(x=>number(x.percent)&&x.percent<=100),low=ink.filter(x=>x.percent<=15);
  card('printer',!p.online?'unknown':low.length?'warning':'good',!p.online?'NO REPLY':low.length?'LOW INK':'AVAILABLE',p.online?(p.state||'Printer is connected.').replace(/\.$/,''):'Printer is taking a quiet moment.',p.online?(low.length?low.map(x=>x.colour).join(' / ')+' ink is running low.':'Your Epson is connected and reporting in.'):'No current reply · check power or connection.');
  const colours=[['Black','#000'],['Cyan','#14c6ee'],['Magenta','#f63c9b'],['Yellow','#f3cf36']];
  $('homeInks').replaceChildren(...colours.map(([name,colour])=>{const v=p.online?ink.find(x=>x.colour===name)?.percent:null,known=number(v);const el=document.createElement('div');el.className='mini-ink';el.style.setProperty('--colour',colour);el.title=name+': '+(known?v+'%':'not reported');const label=document.createElement('span');label.textContent=(name==='Black'?'BK':name[0])+' '+(known?v+'%':'—');const track=document.createElement('div'),fill=document.createElement('i');fill.style.width=(known?v:0)+'%';track.append(fill);el.append(label,track);return el;}));
 }
 const jobs=[{key:'router',url:'/api/router/status',period:5000,render:router,ids:['router']},{key:'lights',url:'/api/hue/group',period:20000,render:lights,ids:['lights']},{key:'sky',url:'/api/sky/now',period:20000,render:sky,ids:['sky']},{key:'jesse',url:'/api/playstation/status',period:20000,render:jesse,ids:['jesse']},{key:'devices',url:'/api/network/status',period:30000,render:devices,ids:['wifi']},{key:'printer',url:'/api/printer/status',period:30000,render:printer,ids:['printer']}];
 async function refresh(job){if(busy.has(job.key)||document.hidden)return;busy.add(job.key);const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),20000);try{let p; if(job.key==='lights'){const bridges=await Promise.all(['house','utility'].map(async bridge=>{try{const r=await fetch('/api/hue/group?bridge='+bridge+'&group=0',{cache:'no-store',signal:abort.signal});if(!r.ok)throw Error();const g=await r.json();if(!g.state||!Array.isArray(g.lights))throw Error();return {online:true,total:g.lights.length};}catch(e){return {online:false};}}));p={bridges};}else{const r=await fetch(job.url,{cache:'no-store',signal:abort.signal});if(!r.ok)throw Error('No reading');p=await r.json();}job.render(p);checks.set(job.key,Date.now());$('homeChecked').textContent='Live checks · '+new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});}catch(e){for(const id of job.ids){const el=$('vital-'+id);card(id,'unknown','NO READING','Waiting for a fresh reading.', 'Tap to open the detailed view.');if(id==='router'){setSpeed('homeDown',null);setSpeed('homeUp',null);plot([]);}if(id==='printer')$('homeInks').replaceChildren();if(id==='wifi')$('homeAps').replaceChildren();const meta=el.querySelector('.vital-bottom');if(meta&&id!=='jesse')meta.textContent='Live status is unavailable.';}}finally{clearTimeout(timer);busy.delete(job.key);}}
 jobs.forEach(job=>{refresh(job);setInterval(()=>refresh(job),job.period);});
 $('homeRefresh').addEventListener('click',async()=>{const button=$('homeRefresh');button.disabled=true;await Promise.allSettled(jobs.map(refresh));button.disabled=false;});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)jobs.forEach(refresh);});
})();
