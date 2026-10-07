(()=> {
  const isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent);
  document.documentElement.classList.toggle("ios-device",isIOS);
  if("serviceWorker" in navigator && location.protocol==="https:"){
    navigator.serviceWorker.register("/sw.js").catch(()=>{});
  }
  const tabs=document.querySelector(".tabs");
  if(tabs && !document.querySelector(".mobile-dock")){
    const wanted=[
      ["index.html","Home","⌂"],
      ["lights.html","Lights","◉"],
      ["sky.html","Sky","▣"],
      ["av.html","AV","▶"],
      ["network.html","Network","⌁"]
    ];
    const dock=document.createElement("nav");
    dock.className="mobile-dock";
    dock.setAttribute("aria-label","Primary");
    const path=(location.pathname.split("/").pop()||"index.html");
    dock.innerHTML=wanted.map(([href,label,icon])=>'<a href="'+href+'" class="'+(path===href?"active":"")+'"><span>'+icon+'</span><small>'+label+'</small></a>').join("");
    document.body.appendChild(dock);
  }
})();