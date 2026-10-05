const rooms=[
{n:"Living Room",b:"house",i:"🛋️",l:2,x:"Room",d:["2 colour bulbs","Living Room Hue dimmer · 79% battery"]},
{n:"Kitchen",b:"house",i:"🍳",l:16,x:"Room",d:["10 ceiling spots","Hue Lightstrip Plus","Table & corner lamps","2 filament bulbs","Hue Tap + dimmer switch","Smart plug · unreachable"]},
{n:"Dining Room",b:"house",i:"🍽️",l:6,x:"Room",d:["Colour spots","Fugato colour spots"]},
{n:"Dining Filaments",b:"house",i:"💡",l:2,x:"Room",d:["2 Hue filament bulbs"]},
{n:"Office Spots",b:"house",i:"💻",l:5,x:"Room",d:["5 Hue Ambiance spots","Office Hue Tap switch"]},
{n:"Office Rail",b:"house",i:"🎨",l:6,x:"Room",d:["White + colour GU10 spots"]},
{n:"Office Spots + Rail",b:"house",i:"🧑‍💻",l:11,x:"Zone",d:["Combined Office lighting zone"]},
{n:"Kitchen + Dining",b:"house",i:"🏠",l:24,x:"Zone",d:["Combined downstairs lighting zone"]},
{n:"Kitchen Music Area",b:"house",i:"🎵",l:2,x:"Entertainment",d:["Hue Entertainment area"]},
{n:"Xmas lights",b:"house",i:"🎄",l:0,x:"Room",d:["Currently empty"]},
{n:"Outside Lights",b:"utility",i:"🌙",l:6,x:"Room",d:["6 Hue white outdoor bulbs","Outdoor motion sensor · battery critical"]},
{n:"Outside Back Door",b:"utility",i:"🚪",l:4,x:"Zone",d:["Overlapping outside-light zone"]},
{n:"BBQ",b:"utility",i:"🔥",l:1,x:"Room",d:["Hue Discover outdoor wall light","BBQ switch · battery empty"]},
{n:"Utility",b:"utility",i:"🧺",l:8,x:"Room",d:["8 spots","Hue motion sensor · battery 100%","Motion · light · temperature"]},
{n:"Shower",b:"utility",i:"🚿",l:6,x:"Room",d:["6 Hue white spots","Hue Smart button · battery 100%","Spot 6 needs attention"]},
{n:"Hallway",b:"utility",i:"🚶",l:2,x:"Room",d:["2 Hue Ambiance spots","Motion sensor · battery critical"]},
{n:"Toilet",b:"utility",i:"🚻",l:2,x:"Room",d:["2 Hue white spots"]}
];
const grid=document.querySelector("#rooms"),dlg=document.querySelector("#detail"),dc=document.querySelector("#detailContent");
function render(f="all"){grid.innerHTML="";rooms.filter(r=>f==="all"||r.b===f).forEach(r=>{const b=document.createElement("button");b.className="card";b.innerHTML='<div><span class="icon">'+r.i+'</span><h3>'+r.n+'</h3><p>'+(r.b==="house"?"House":"Utility")+" bridge</p></div><div class=meta><span class=pill>"+r.x+"</span><span class=pill>"+r.l+" lights</span></div>';b.addEventListener("click",()=>openRoom(r));grid.appendChild(b)})}
function openRoom(r){dc.innerHTML="<p class=eyebrow>"+r.x.toUpperCase()+" · "+(r.b==="house"?"HOUSE":"UTILITY")+"</p><h2>"+r.i+" "+r.n+"</h2><p>"+r.l+" Hue light"+(r.l===1?"":"s")+"</p><div class=detail-list>"+r.d.map(x=>"<div>"+x+"</div>").join("")+"</div><p style='margin-top:20px;color:#9eacbe'>Scene controls will be added in the next control-enabled stage.</p>";dlg.showModal()}
document.querySelectorAll(".tabs button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".tabs button").forEach(x=>x.classList.remove("active"));b.classList.add("active");render(b.dataset.filter)}));
document.querySelector(".close").addEventListener("click",()=>dlg.close());dlg.addEventListener("click",e=>{if(e.target===dlg)dlg.close()});render();