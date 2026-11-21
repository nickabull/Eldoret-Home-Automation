(()=>{'use strict';
const $=id=>document.getElementById(id), dims={wide:[1920,1080],ipad:[1024,768],pi:[800,480]};
let doc={version:1,page:'pioneer',preset:'wide',width:1920,height:1080,background:'#0c2430',elements:[]},selected=null,undo=[],redo=[],stageScale=1,dirty=false;
const fields=['name','label','src','x','y','w','h','size','radius','color','bg','opacity','locked','behaviour','font'];
const defaults={font:'Arial',bold:false,italic:false,underline:false,strike:false,align:'center'};
const hydrate=e=>{for(const [k,v] of Object.entries(defaults))if(e[k]===undefined)e[k]=v;return e};
const clone=x=>JSON.parse(JSON.stringify(x));
const notice=msg=>{$('status').textContent=msg};
const get=()=>doc.elements.find(e=>e.id===selected);
const cssRGB=(hex,opacity)=>{const v=parseInt(hex.slice(1),16);return 'rgba('+((v>>16)&255)+','+((v>>8)&255)+','+(v&255)+','+(opacity/100)+')'};
const format=()=>{let a=dims[doc.preset]||dims.wide;doc.width=a[0];doc.height=a[1];$('dimensions').textContent=a.join(' × ');};
function snapshot(){undo.push(clone(doc));if(undo.length>70)undo.shift();redo=[];dirty=true}
function resizeStage(){const w=$('stagewrap').clientWidth-46,h=$('stagewrap').clientHeight-46;stageScale=$('zoom').value==='fit'?Math.min(1,w/doc.width,h/doc.height):Number($('zoom').value);$('stage').style.width=doc.width+'px';$('stage').style.height=doc.height+'px';$('stage').style.transform='scale('+stageScale+')';$('stagewrap').style.alignItems='start';$('stagewrap').style.justifyItems='center';$('stagewrap').style.display='flex';$('stagewrap').style.justifyContent='center';$('stage').style.marginBottom=(doc.height*stageScale-doc.height)+'px';}
function render(){format();$('page').value=doc.page;$('preset').value=doc.preset;const stage=$('stage');stage.replaceChildren();stage.style.background=doc.background;
 doc.elements.forEach((e,index)=>{hydrate(e);const node=document.createElement('div');node.className='element'+(e.id===selected?' selected':'')+(e.locked?' locked':'');node.style.left=e.x+'px';node.style.top=e.y+'px';node.style.width=e.w+'px';node.style.height=e.h+'px';node.style.fontSize=e.size+'px';node.style.fontFamily=e.font;node.style.fontWeight=e.bold?'bold':'normal';node.style.fontStyle=e.italic?'italic':'normal';node.style.textDecoration=[e.underline?'underline':'',e.strike?'line-through':''].filter(Boolean).join(' ');node.style.justifyContent=e.align==='left'?'flex-start':e.align==='right'?'flex-end':'center';node.style.textAlign=e.align;node.style.color=e.color;node.style.background=cssRGB(e.bg,e.opacity);node.style.borderRadius=e.radius+'px';node.style.zIndex=index+1;node.dataset.id=e.id;
 if(e.type==='image'&&e.src){const image=document.createElement('img');image.src=e.src;image.alt=e.label||'Artwork';image.draggable=false;image.style.cssText='width:100%;height:100%;object-fit:contain;pointer-events:none';node.append(image)}else{node.textContent=e.label}
 node.addEventListener('pointerdown',evt=>startDrag(evt,e.id,false));node.addEventListener('click',evt=>{evt.stopPropagation();select(e.id)});
 if(e.id===selected&&!e.locked){const h=document.createElement('div');h.className='handle';h.addEventListener('pointerdown',evt=>startDrag(evt,e.id,true));node.append(h)}
 stage.append(node)});
 const layers=$('layers');layers.replaceChildren();[...doc.elements].reverse().forEach(e=>{const btn=document.createElement('button');btn.className='layer'+(e.id===selected?' current':'');const name=document.createElement('span');name.textContent=e.name;const kind=document.createElement('small');kind.textContent=e.locked?'🔒':e.type;btn.append(name,kind);btn.addEventListener('click',()=>select(e.id));layers.append(btn)});
 const e=get();$('empty').hidden=!!e;$('inspector').hidden=!e;if(e){fields.forEach(id=>{$(id).value=id==='locked'?String(e[id]):e[id]??''});$('sizeSlider').value=Math.max(8,Math.min(160,e.size));$('opacitySlider').value=e.opacity;
for(const [slider,field] of [['sizeSlider','size'],['opacitySlider','opacity']]){
 $(slider).addEventListener('input',()=>{const e=get();if(!e)return;const v=Number($(slider).value);e[field]=v;$(field).value=v;const node=document.querySelector('.element.selected');if(node){if(field==='size')node.style.fontSize=v+'px';else node.style.background=cssRGB(e.bg,v)}dirty=true;notice('Unsaved changes')});
 $(slider).addEventListener('change',()=>{render();notice('Unsaved changes')});
}
for(const [id,key] of [['boldToggle','bold'],['italicToggle','italic'],['underlineToggle','underline'],['strikeToggle','strike'],['textLeft','left'],['textCenter','center'],['textRight','right']]){$(id).classList.toggle('active',key==='left'||key==='center'||key==='right'?e.align===key:!!e[key]);}}resizeStage();
}
function select(id){selected=id;render()}
$('stage').addEventListener('click',()=>select(null));
function startDrag(event,id,resizing){if(event.button!==0&&event.pointerType!=='touch')return;event.preventDefault();event.stopPropagation();selected=id;const e=get();if(e.locked){render();return};snapshot();const sx=event.clientX,sy=event.clientY,initial={x:e.x,y:e.y,w:e.w,h:e.h};const node=event.currentTarget.closest('.element');node.setPointerCapture(event.pointerId);const move=ev=>{const dx=Math.round((ev.clientX-sx)/stageScale),dy=Math.round((ev.clientY-sy)/stageScale);if(resizing){e.w=Math.max(20,Math.min(doc.width-e.x,initial.w+dx));e.h=Math.max(20,Math.min(doc.height-e.y,initial.h+dy))}else{e.x=Math.max(0,Math.min(doc.width-e.w,initial.x+dx));e.y=Math.max(0,Math.min(doc.height-e.h,initial.y+dy))}node.style.left=e.x+'px';node.style.top=e.y+'px';node.style.width=e.w+'px';node.style.height=e.h+'px';};const stop=()=>{node.removeEventListener('pointermove',move);node.removeEventListener('pointerup',stop);node.removeEventListener('pointercancel',stop);render();notice('Unsaved changes')};node.addEventListener('pointermove',move);node.addEventListener('pointerup',stop);node.addEventListener('pointercancel',stop)}
const makeId=()=>globalThis.crypto&&crypto.randomUUID?crypto.randomUUID():'layer-'+Date.now()+'-'+Math.floor(Math.random()*1e6);
document.querySelectorAll('[data-add]').forEach(btn=>btn.addEventListener('click',()=>{snapshot();let type=btn.dataset.add;let e={id:makeId(),type,name:type+' '+(doc.elements.length+1),label:type==='button'?'New button':type==='text'?'Edit this text':type==='panel'?'New panel':'Artwork',src:'',x:Math.round(doc.width*.15),y:Math.round(doc.height*.2),w:type==='panel'?500:360,h:type==='panel'?240:100,size:type==='text'?48:28,radius:type==='button'?20:8,color:'#ffffff',bg:'#164858',opacity:type==='image'?0:80,locked:false,behaviour:'',font:'Arial',bold:false,italic:false,underline:false,strike:false,align:'center'};doc.elements.push(e);selected=e.id;render();notice('Unsaved changes')}));
fields.forEach(id=>$(id).addEventListener('change',()=>{const e=get();if(!e)return;snapshot();let v=$(id).value;if(['x','y','w','h','size','radius','opacity'].includes(id))v=Number(v)||0;if(id==='locked')v=v==='true';e[id]=v;if(id==='x')e.x=Math.max(0,Math.min(doc.width-e.w,v));if(id==='y')e.y=Math.max(0,Math.min(doc.height-e.h,v));if(id==='w')e.w=Math.max(20,Math.min(doc.width-e.x,v));if(id==='h')e.h=Math.max(20,Math.min(doc.height-e.y,v));if(id==='opacity')e.opacity=Math.min(100,Math.max(0,v));render();notice('Unsaved changes')}));

for(const [id,key] of [['boldToggle','bold'],['italicToggle','italic'],['underlineToggle','underline'],['strikeToggle','strike']]){
 $(id).addEventListener('click',()=>{const e=get();if(!e)return;snapshot();e[key]=!e[key];render();notice('Unsaved text formatting')});
}
for(const [id,val] of [['textLeft','left'],['textCenter','center'],['textRight','right']]){
 $(id).addEventListener('click',()=>{const e=get();if(!e)return;snapshot();e.align=val;render();notice('Unsaved alignment')});
}
$('zoom').addEventListener('change',resizeStage);
$('toggleLock').addEventListener('click',()=>{const e=get();if(!e)return;snapshot();e.locked=!e.locked;render();notice(e.locked?'Layer locked':'Layer unlocked')});
for(const [id,coord,position] of [['centerH','x',e=>Math.round((doc.width-e.w)/2)],['centerV','y',e=>Math.round((doc.height-e.h)/2)],['alignLeft','x',()=>0],['alignTop','y',()=>0]]){
 $(id).addEventListener('click',()=>{const e=get();if(!e||e.locked)return;snapshot();e[coord]=position(e);render();notice('Unsaved alignment')});
}
document.addEventListener('keydown',event=>{
 const tag=(document.activeElement?.tagName||'').toLowerCase();
 if(['input','select','textarea'].includes(tag)||document.activeElement?.isContentEditable)return;
 const e=get();if(!e)return;
 if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='d'){event.preventDefault();$('duplicate').click();return}
 if(e.locked)return;
 const dirs={ArrowLeft:['x',-1],ArrowRight:['x',1],ArrowUp:['y',-1],ArrowDown:['y',1]};
 if(dirs[event.key]){event.preventDefault();const [key,delta]=dirs[event.key],amt=delta*(event.shiftKey?10:1);snapshot();e[key]=Math.max(0,Math.min((key==='x'?doc.width-e.w:doc.height-e.h),e[key]+amt));render();notice('Unsaved position')}
 if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();$('remove').click()}
});
$('page').addEventListener('change',()=>{const v=$('page').value.trim().toLowerCase();if(!/^[a-z0-9][a-z0-9_-]{0,39}$/.test(v)){alert('Use letters, numbers, dashes and underscores (max 40 characters).');$('page').value=doc.page;return}doc.page=v;notice('Changed page name; load or save its draft')});
$('preset').addEventListener('change',async()=>{if(dirty&&!confirm('Switch layout? Save your current draft first.')){$('preset').value=doc.preset;return}doc.preset=$('preset').value;format();doc.elements=[];selected=null;dirty=false;await load()});
$('undo').addEventListener('click',()=>{if(undo.length){redo.push(clone(doc));doc=undo.pop();selected=null;dirty=true;render();notice('Unsaved changes')}});
$('redo').addEventListener('click',()=>{if(redo.length){undo.push(clone(doc));doc=redo.pop();selected=null;dirty=true;render();notice('Unsaved changes')}});
$('duplicate').addEventListener('click',()=>{const e=get();if(!e)return;snapshot();const copy=clone(e);copy.id=makeId();copy.name='Copy of '+e.name;copy.x=Math.min(doc.width-copy.w,copy.x+35);copy.y=Math.min(doc.height-copy.h,copy.y+35);copy.locked=false;doc.elements.push(copy);selected=copy.id;render();notice('Unsaved changes')});
$('remove').addEventListener('click',()=>{if(!get()||get().locked)return;snapshot();doc.elements=doc.elements.filter(e=>e.id!==selected);selected=null;render();notice('Unsaved changes')});
for(const [id,dir] of [['up',1],['down',-1]])$(id).addEventListener('click',()=>{const i=doc.elements.findIndex(e=>e.id===selected),j=i+dir;if(i<0||j<0||j>=doc.elements.length)return;snapshot();[doc.elements[i],doc.elements[j]]=[doc.elements[j],doc.elements[i]];render();notice('Unsaved changes')});
async function api(method,payload){const response=await fetch('/api/design-centre?name='+encodeURIComponent(doc.page)+'&preset='+encodeURIComponent(doc.preset),{method,headers:{'Content-Type':'application/json'},body:payload?JSON.stringify(payload):undefined,cache:'no-store'});const d=await response.json();if(!response.ok)throw Error(d.error||'HTTP '+response.status);return d}
async function load(){notice('Loading draft…');try{const d=await api('GET');if(d.design){doc=d.design;format();selected=null;dirty=false;undo=[];redo=[];render();notice('Draft loaded from Bulldog')}else{doc={version:1,page:doc.page,preset:doc.preset,width:dims[doc.preset][0],height:dims[doc.preset][1],background:'#0c2430',elements:[]};selected=null;dirty=false;undo=[];redo=[];render();notice('New blank draft — nothing published')}}catch(e){render();notice('Load failed: '+e.message)}}
$('load').addEventListener('click',load);
$('save').addEventListener('click',async()=>{notice('Saving to Bulldog…');$('save').disabled=true;try{const d=await api('POST',{design:doc});dirty=false;notice('Saved on Bulldog · '+(d.saved_at||''))}catch(e){notice('Save failed: '+e.message)}finally{$('save').disabled=false}});
$('export').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='eldoret-'+doc.page+'-'+doc.preset+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
$('import').addEventListener('click',()=>$('jsonfile').click());
$('jsonfile').addEventListener('change',async()=>{const file=$('jsonfile').files[0];if(!file)return;try{const j=JSON.parse(await file.text());if(!j||!Array.isArray(j.elements)||!dims[j.preset]||typeof j.page!=='string')throw Error('Invalid design JSON');snapshot();doc=j;selected=null;render();notice('Imported — save draft to Bulldog to persist')}catch(e){alert('Cannot import: '+e.message)}});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='Unsaved design changes'}});
new ResizeObserver(resizeStage).observe($('stagewrap'));render();load();
})();