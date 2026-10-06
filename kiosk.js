// Eldoret kiosk inactivity return: deeper screens go Home after 2 minutes without interaction.
(()=>{
  const HOME="/";
  const TIMEOUT=120000;
  let timer;
  const reset=()=>{
    clearTimeout(timer);
    timer=setTimeout(()=>{
      if(location.pathname!==HOME && !location.pathname.endsWith("/index.html")) location.href=HOME;
    },TIMEOUT);
  };
  ["pointerdown","pointermove","keydown","touchstart","wheel"].forEach(evt=>addEventListener(evt,reset,{passive:true}));
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)reset();});
  reset();
})();