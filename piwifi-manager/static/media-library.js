(()=>{'use strict';
 const $=id=>document.getElementById(id);if(!$('catalog-form'))return;
 let timer,reading=false,revision=0,running=false,seen='';
 const visible=()=>!document.hidden&&$('media').classList.contains('active');
 const note=text=>$('catalog-note').textContent=text;
 async function api(payload){const r=await fetch('/api/media',{method:'POST',cache:'no-store',signal:AbortSignal.timeout(14000),headers:{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value},body:JSON.stringify(payload)});if(r.redirected)throw Error('Cần đăng nhập lại');const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Tìm kiếm chưa sẵn sàng');return d.data}
 function render(data){
  running=!!data.running;$('catalog-submit').disabled=running;note(data.message||'');
  const stamp=JSON.stringify(data.rows||[]);if(stamp===seen)return;seen=stamp;$('catalog-results').replaceChildren();
  for(const row of data.rows||[]){
   const li=document.createElement('li'),body=document.createElement('div'),title=document.createElement('strong'),sub=document.createElement('span'),buttons=document.createElement('div'),play=document.createElement('button'),pin=document.createElement('button');
   li.className='catalog-result';title.textContent=row.title;sub.textContent=row.subtitle===row.title?'':row.subtitle;body.append(title,sub);buttons.className='catalog-actions';play.type=pin.type='button';play.className='btn btn-primary btn-sm';pin.className='btn btn-outline btn-sm';play.textContent='Phát';pin.textContent='Ghim';
   play.onclick=()=>window.PiMedia?.command({action:'catalog_play',provider:row.provider,url:row.url});
   pin.onclick=()=>window.PiMedia?.command({action:'shortcut_save',provider:row.provider,url:row.url,label:row.title.slice(0,60)});
   buttons.append(play,pin);li.append(body,buttons);$('catalog-results').append(li);
  }
 }
 async function refresh(){if(!visible()||!running||reading)return;reading=true;const version=revision;try{const data=await api({action:'catalog_status'});if(version===revision)render(data)}catch(e){note(e.message);running=false}finally{reading=false;schedule(false)}}
 function schedule(immediate=true){clearTimeout(timer);if(visible()&&running){if(immediate)refresh();else timer=setTimeout(refresh,1000)}}
 $('catalog-form').onsubmit=async e=>{e.preventDefault();if(running)return;const version=++revision;running=true;$('catalog-submit').disabled=true;note('Đang tìm trên Pi…');try{const d=await api({action:'catalog_search',provider:$('catalog-provider').value,query:$('catalog-query').value});if(version===revision){render(d);schedule(false)}}catch(error){running=false;$('catalog-submit').disabled=false;note(error.message)}};
 window.addEventListener('pi:view',()=>schedule());document.addEventListener('visibilitychange',()=>schedule());window.addEventListener('pagehide',()=>clearTimeout(timer));
})();
