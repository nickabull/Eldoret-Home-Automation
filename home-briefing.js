(()=>{
'use strict';
const $=id=>document.getElementById(id);
async function json(url){
 const control=new AbortController(),timer=setTimeout(()=>control.abort(),12000);
 try{const r=await fetch(url,{cache:'no-store',signal:control.signal});if(!r.ok)throw Error();const data=await r.json();if(data.error)throw Error();return data;}finally{clearTimeout(timer);}
}
async function news(){try{const p=await json('/api/home/news');if(!p.available||!p.title)throw Error();const u=new URL(p.url);if(u.protocol!=='https:'||!['bbc.co.uk','www.bbc.co.uk','bbc.com','www.bbc.com'].includes(u.hostname))throw Error();$('news-headline').textContent=p.title;$('news-headline').href=u.href;const date=new Date(p.published_at);$('news-time').textContent='BBC News · '+(Number.isNaN(date.getTime())?'Top story':date.toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}));}catch{$('news-headline').textContent='Headlines unavailable — open BBC News';$('news-headline').href='https://www.bbc.co.uk/news';$('news-time').textContent='Waiting for a fresh headline.';}}
news();setInterval(()=>{if(!document.hidden)news();},300000);
let location=null;try{location=JSON.parse(localStorage.getItem('eldoret-weather-location')||'null');}catch{}
function conditions(code){if(code===0)return 'Clear';if(code<=2)return 'Partly cloudy';if(code===3)return 'Overcast';if(code<=48)return 'Fog';if(code<=57)return 'Drizzle';if(code<=67)return 'Rain';if(code<=77)return 'Snow';if(code<=82)return 'Showers';if(code<=86)return 'Snow showers';if(code>=95)return 'Thunderstorms';return 'Weather';}
let weatherVersion=0;
async function weather(){if(!location)return;const version=++weatherVersion;const place=location;try{const p=await json('/api/home/weather?lat='+encodeURIComponent(place.latitude)+'&lon='+encodeURIComponent(place.longitude));if(version!==weatherVersion)return;if(!p.available||!Number.isFinite(p.temperature))throw Error();$('weather-line').textContent=place.name+' · '+Math.round(p.temperature)+'°C · '+conditions(p.weather_code)+(Number.isFinite(p.high)?' · high '+Math.round(p.high)+'°':'')+(Number.isFinite(p.rain_chance)?' · rain '+p.rain_chance+'%':'');$('weather-settings').textContent='Change';}catch{if(version===weatherVersion)$('weather-line').textContent=place.name+' · weather temporarily unavailable.';}}
$('weather-settings').onclick=()=>$('weather-dialog').showModal();$('weather-close').onclick=()=>$('weather-dialog').close();
$('weather-search').onsubmit=async event=>{event.preventDefault();const status=$('weather-search-status'),results=$('weather-results');results.replaceChildren();status.textContent='Finding your location…';try{const p=await json('/api/home/locations?q='+encodeURIComponent($('weather-town').value.trim()));const choices=p.results||[];status.textContent=choices.length?'Choose your location:':'No matching UK place found. Try a nearby town.';for(const place of choices){const button=document.createElement('button');button.type='button';button.textContent=[place.name,place.admin2||place.admin1].filter(Boolean).join(' · ');button.onclick=()=>{location=place;try{localStorage.setItem('eldoret-weather-location',JSON.stringify(place));}catch{}$('weather-dialog').close();$('weather-line').textContent='Reading weather for '+place.name+'…';weather();};results.append(button);}}catch{status.textContent='Location search is unavailable. Please try again.';}};
weather();setInterval(()=>{if(!document.hidden)weather();},900000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){news();weather();}});
})();
