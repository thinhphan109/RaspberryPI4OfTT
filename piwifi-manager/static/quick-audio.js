(()=>{'use strict';
 const $=id=>document.getElementById(id),dialog=$('quick-audio');if(!dialog)return;
 let output=null,timer,busy=false,reading=false,revision=0;
 const visible=()=>dialog.open&&!document.hidden;
 const note=text=>$('quick-audio-note').textContent=text;
 async function api(payload){
  const response=await fetch('/api/audio',{method:'POST',cache:'no-store',signal:AbortSignal.timeout(12000),headers:{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value},body:JSON.stringify(payload)});
  if(response.redirected)throw Error('Cần đăng nhập lại');
  const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Chưa đọc được loa');return result.data;
 }
 function render(data){
  output=data.output||null;$('quick-audio-name').textContent=output?.label||'Chưa chọn loa';
  $('quick-audio-volume').disabled=busy||!output;$('quick-audio-mute').disabled=busy||!output;
  if(document.activeElement!==$('quick-audio-volume'))$('quick-audio-volume').value=Math.min(100,output?.volume||0);
  $('quick-audio-value').textContent=output?output.volume+'%':'—';
  $('quick-audio-mute').textContent=output?.muted?'Bật tiếng':'Tắt tiếng';$('quick-audio-mute').setAttribute('aria-pressed',String(!!output?.muted));note(data.message||'');
 }
 async function refresh(){if(!visible()||busy||reading)return;reading=true;const version=revision;try{const data=await api({action:'output_status'});if(version===revision&&visible())render(data)}catch(e){if(version===revision){output=null;render({message:e.message})}}finally{reading=false}}
 async function change(action,extra){
  if(busy||!output)return;busy=true;revision++;const selected=output;render({output:selected});
  try{render(await api({action,id:selected.id,name:selected.name,...extra}))}catch(e){note(e.message);output=null;$('quick-audio-volume').disabled=true;$('quick-audio-mute').disabled=true}finally{busy=false;if(output){$('quick-audio-volume').disabled=false;$('quick-audio-mute').disabled=false}}
 }
 function schedule(){clearInterval(timer);if(visible()){refresh();timer=setInterval(refresh,5000)}}
 $('quick-audio-open').onclick=()=>{dialog.showModal();schedule()};$('quick-audio-close').onclick=()=>dialog.close();
 $('quick-audio-settings').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{revision++;clearInterval(timer);$('quick-audio-open').focus()});
 dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close()}});
 $('quick-audio-volume').oninput=()=>{$('quick-audio-value').textContent=$('quick-audio-volume').value+'%'};
 $('quick-audio-volume').onchange=()=>change('output_volume',{value:Number($('quick-audio-volume').value)});
 $('quick-audio-mute').onclick=()=>change('output_mute',{muted:!output?.muted});
 document.addEventListener('visibilitychange',schedule);window.addEventListener('pagehide',()=>clearInterval(timer));
})();
