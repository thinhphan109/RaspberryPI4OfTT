/* SVG axes in real CSS pixels; no chart dependency or extra polling. */
(()=>{'use strict';
 const NS='http://www.w3.org/2000/svg';
 function layout(width,max,start,end,right=false,height=240){
  width=Math.max(220,width||800);height=Math.max(180,height||240);
  return {width,height,left:62,right:width-(right?48:16),top:26,bottom:height-41,max:Math.max(1,max),start,end:Math.max(start+1,end)};
 }
 function path(rows,key,p,gap=Infinity){
  let d='',previous=null;
  for(const row of rows){
   const t=row.t??row.timestamp,v=row[key];
   if(!Number.isFinite(t)||!Number.isFinite(v)||v<0||t<p.start||t>p.end){previous=null;continue}
   const x=p.left+(t-p.start)/(p.end-p.start)*(p.right-p.left),y=p.bottom-Math.min(p.max,v)/p.max*(p.bottom-p.top);
   d+=(previous!==null&&t-previous<=gap?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)+' ';previous=t;
  }
  return d.trim();
 }
 function ceiling(value){if(!(value>0))return 1;const power=10**Math.floor(Math.log10(value));return [1,2,4,5,8,10].find(n=>n*power>=value)*power}
 function nearest(rows,t,maxDistance=Infinity){
  let chosen=null,distance=Infinity;
  for(const row of rows){const at=row.t??row.timestamp;if(!Number.isFinite(at))continue;const d=Math.abs(at-t);if(d<distance){distance=d;chosen=row}}
  return distance<=maxDistance?chosen:null;
 }
 function frame(svg,options){
  const bounds=svg.getBoundingClientRect(),p=layout(bounds.width,options.max,options.start,options.end,!!options.rightUnit,bounds.height);
  svg.setAttribute('viewBox',`0 0 ${p.width} ${p.height}`);
  let group=svg.querySelector('.chart-axes');if(!group){group=document.createElementNS(NS,'g');group.setAttribute('class','chart-axes');svg.prepend(group)}group.replaceChildren();
  function add(tag,attrs,text){const node=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))node.setAttribute(k,String(v));if(text!==undefined)node.textContent=text;group.append(node)}
  const number=n=>n===0?'0':n>=100?n.toFixed(0):Number(n.toPrecision(3)).toString();
  for(let i=0;i<=4;i++){
   const y=p.bottom-(p.bottom-p.top)*i/4,value=p.max*i/4;
   add('line',{x1:p.left,y1:y,x2:p.right,y2:y,class:'chart-grid'});
   add('text',{x:p.left-10,y:y+3,'text-anchor':'end'},number(value));
   if(options.rightUnit)add('text',{x:p.right+8,y:y+3,'text-anchor':'start'},number(value));
  }
  const count=p.width<320||p.width<500&&p.end-p.start>=86400?2:p.width<500?3:5;
  for(let i=0;i<count;i++){
   const x=p.left+(p.right-p.left)*i/(count-1),t=p.start+(p.end-p.start)*i/(count-1);
   add('line',{x1:x,y1:p.top,x2:x,y2:p.bottom,class:'chart-grid chart-grid-vertical'});
   const span=p.end-p.start,format={hour:'2-digit',minute:'2-digit',...(span<3600?{second:'2-digit'}:{}),...(span>=86400?{day:'2-digit',month:'2-digit'}:{})};
   add('text',{x,y:p.bottom+21,'text-anchor':i===0?'start':i===count-1?'end':'middle'},new Date(t*1000).toLocaleString('vi-VN',format));
  }
  add('text',{x:p.left,y:13,class:'chart-unit'},p.width<420&&options.rightUnit?'CPU/RAM %':options.unit);
  if(options.rightUnit)add('text',{x:p.right,y:13,'text-anchor':'end',class:'chart-unit'},p.width<420?'°C':options.rightUnit);
  add('text',{x:p.right,y:p.height-3,'text-anchor':'end',class:'chart-unit'},'Thời gian');
  return p;
 }
 function observe(svg,draw){if(!svg||typeof ResizeObserver==='undefined')return;let width=0,height=0;new ResizeObserver(entries=>{const next=entries[0].contentRect;if(next.width>0&&(Math.abs(next.width-width)>1||Math.abs(next.height-height)>1)){width=next.width;height=next.height;requestAnimationFrame(draw)}}).observe(svg)}
 function draw(el,rows,key,p,gap){
  el.setAttribute('d',path(rows,key,p,gap));
  let dot=el.parentNode.querySelector('#'+el.id+'-dot');
  if(!dot){dot=document.createElementNS(NS,'circle');dot.id=el.id+'-dot';dot.setAttribute('class','chart-dot '+el.id);dot.setAttribute('r','3');el.parentNode.append(dot)}
  const row=rows.at(-1),t=row?.t??row?.timestamp,v=row?.[key];
  const valid=Number.isFinite(t)&&Number.isFinite(v)&&v>=0&&t>=p.start&&t<=p.end;
  dot.setAttribute('visibility',valid?'visible':'hidden');
  if(valid){dot.setAttribute('cx',p.left+(t-p.start)/(p.end-p.start)*(p.right-p.left));dot.setAttribute('cy',p.bottom-Math.min(p.max,v)/p.max*(p.bottom-p.top))}
 }
 const inspectors=new Map();
 function inspect(svg,model){
  let state=inspectors.get(svg);
  if(!state){
   const tip=document.createElement('div');tip.className='chart-tooltip';tip.id='chart-tooltip-'+(inspectors.size+1);tip.hidden=true;tip.setAttribute('role','tooltip');document.body.append(tip);svg.setAttribute('aria-describedby',tip.id);
   const cursor=document.createElementNS(NS,'g');cursor.setAttribute('class','chart-inspector');cursor.setAttribute('visibility','hidden');svg.append(cursor);
   state={tip,cursor,model,active:false,x:0,y:0};inspectors.set(svg,state);
   svg.setAttribute('tabindex','0');svg.classList.add('chart-interactive');
   function hide(){state.active=false;tip.hidden=true;cursor.setAttribute('visibility','hidden')}
   state.hide=hide;
   function show(x,y,index){
    const box=svg.getBoundingClientRect(),m=state.model,p=m.plot;if(!box.width||!box.height){hide();return}
    const localX=(x-box.left)/box.width*p.width,localY=(y-box.top)/box.height*p.height;
    if(index==null&&(localX<p.left||localX>p.right||localY<p.top||localY>p.bottom)){hide();return}
    const t=p.start+(localX-p.left)/(p.right-p.left)*(p.end-p.start);
    const row=index==null?nearest(m.rows,t,m.maxDistance):m.rows[index];
    if(!row){hide();return}
    state.active=true;state.x=x;state.y=y;state.index=m.rows.indexOf(row);
    const at=row.t??row.timestamp,cx=p.left+(at-p.start)/(p.end-p.start)*(p.right-p.left);
    tip.replaceChildren();cursor.replaceChildren();
    const heading=document.createElement('div');heading.className='chart-tooltip-time';heading.textContent=(m.prefix||'')+new Date(at*1000).toLocaleString('vi-VN');tip.append(heading);
    const line=document.createElementNS(NS,'line');for(const[k,v]of Object.entries({x1:cx,x2:cx,y1:p.top,y2:p.bottom}))line.setAttribute(k,String(v));cursor.append(line);
    for(const series of m.series){
     const value=row[series.key],valid=Number.isFinite(value)&&value>=0;
     const item=document.createElement('div');item.className='chart-tooltip-row';
     const label=document.createElement('span'),number=document.createElement('strong');label.textContent=series.label;label.style.color=series.color;
     number.textContent=valid?(series.format?series.format(value):value.toLocaleString('vi-VN',{maximumFractionDigits:2})+' '+(series.unit||'')):'Không có mẫu';item.append(label,number);tip.append(item);
     if(valid&&series.marker!==false){const dot=document.createElementNS(NS,'circle');dot.setAttribute('cx',String(cx));dot.setAttribute('cy',String(p.bottom-Math.min(p.max,value)/p.max*(p.bottom-p.top)));dot.setAttribute('r','4');dot.style.fill=series.color;cursor.append(dot)}
    }
    cursor.setAttribute('visibility','visible');tip.hidden=false;
    const bounds=tip.getBoundingClientRect(),width=document.documentElement.clientWidth,height=window.innerHeight;
    tip.style.left=Math.max(8,Math.min(x+14,width-bounds.width-8))+'px';
    tip.style.top=Math.max(8,Math.min(y-bounds.height-12<8?y+16:y-bounds.height-12,height-bounds.height-8))+'px';
   }
   state.show=show;
   svg.addEventListener('pointermove',e=>show(e.clientX,e.clientY));
   svg.addEventListener('pointerdown',e=>{show(e.clientX,e.clientY);if(e.pointerType==='touch')svg.setPointerCapture(e.pointerId)});
   svg.addEventListener('pointerleave',e=>{if(e.pointerType!=='touch')hide()});
   svg.addEventListener('pointercancel',hide);svg.addEventListener('blur',hide);
   svg.addEventListener('keydown',e=>{
    if(e.key==='Escape'){hide();return}if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)||!state.model.rows.length)return;
    e.preventDefault();const rows=state.model.rows,i=e.key==='Home'?0:e.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,(state.index??rows.length-1)+(e.key==='ArrowLeft'?-1:1)));
    const box=svg.getBoundingClientRect(),p=state.model.plot,at=rows[i].t??rows[i].timestamp;
    show(box.left+(p.left+(at-p.start)/(p.end-p.start)*(p.right-p.left))/p.width*box.width,box.top+35,i);
   });
   if(inspectors.size===1){
    const hideAll=()=>inspectors.forEach(s=>s.hide());
    document.addEventListener('visibilitychange',hideAll);window.addEventListener('pi:view',hideAll);
    window.addEventListener('scroll',hideAll,{passive:true});window.addEventListener('resize',hideAll);
    document.addEventListener('pointerdown',e=>{for(const[node,s]of inspectors)if(!node.contains(e.target))s.hide()});
   }
  }
  state.model=model;
  if(state.active)state.show(state.x,state.y);
 }
 const api={layout,path,ceiling,frame,observe,draw,nearest,inspect};
 if(typeof window!=='undefined')window.PiCharts=api;
 if(typeof module!=='undefined')module.exports=api;
})();
