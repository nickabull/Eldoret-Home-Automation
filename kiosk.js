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
