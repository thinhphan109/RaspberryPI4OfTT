(()=>{'use strict';
 const $=id=>document.getElementById(id);if(!$('native-scan'))return;
 const buttons=[...document.querySelectorAll('[data-native]')];
 let selected=null,state=null,busy=false,reading=false,revision=0;
 const visible=()=>!document.hidden&&$('media').classList.contains('active');
 const note=text=>$('native-note').textContent=text;
 async function api(payload){
  const r=await fetch('/api/media',{method:'POST',cache:'no-store',signal:AbortSignal.timeout(12000),headers:{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value},body:JSON.stringify(payload)});
  if(r.redirected)throw Error('Cần đăng nhập lại');
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Ứng dụng chưa phản hồi');return d.data;
 }
 function controls(){
  $('native-scan').disabled=busy;$('native-select').disabled=busy;
  buttons.forEach(b=>b.disabled=busy||!state||!state['can_'+b.dataset.native]);
  $('native-volume').disabled=busy||!state?.can_volume;
 }
 function render(data){
  state=data;$('native-track-title').textContent=data.title||'Chưa có bài đang phát';$('native-track-artist').textContent=data.artist||'';
  $('native-state').textContent=({Playing:'Đang phát',Paused:'Tạm dừng',Stopped:'Đã dừng'})[data.playback]||'Chưa rõ trạng thái';
  if(document.activeElement!==$('native-volume'))$('native-volume').value=data.volume??0;
  $('native-volume-value').textContent=data.volume==null?'—':data.volume+'%';controls();
 }
 function invalidate(message){selected=null;state=null;revision++;controls();note(message)}
 async function refresh(){
  if(!selected||!visible()||busy||reading)return;reading=true;const version=revision,target=selected;
  try{const data=await api({action:'app_status',...target});if(version===revision&&visible())render(data)}
  catch(e){if(version===revision)invalidate(e.message)}finally{reading=false}
 }
 async function scan(){
  if(busy)return;busy=true;revision++;selected=null;state=null;controls();note('Đang tìm ứng dụng…');
  try{
   const data=await api({action:'apps'}),rows=data.players||[];$('native-select').replaceChildren();
   for(const row of rows){const option=document.createElement('option');option.value=row.id;option.textContent=row.label;option.dataset.owner=row.owner;$('native-select').append(option)}
   $('native-player').hidden=!rows.length;
   if(rows.length){selected={id:rows[0].id,owner:rows[0].owner};note('Chọn app để điều khiển.')}else note(data.message||'Chưa có ứng dụng đang mở.');
  }catch(e){invalidate(e.message)}finally{busy=false;controls()}
  await refresh();
 }
 async function change(command,value){
  if(busy||!selected||!state)return;busy=true;const version=++revision,target=selected;controls();note('Đang gửi lệnh…');
  try{const data=await api({action:'app_command',...target,command,...(value===undefined?{}:{value})});if(version===revision){render(data);note(data.receipt?.message||'Đã nhận phản hồi ứng dụng.')}}
  catch(e){if(version===revision)invalidate(e.message)}finally{busy=false;controls()}
 }
 $('native-scan').onclick=scan;
 $('native-select').onchange=()=>{revision++;state=null;const option=$('native-select').selectedOptions[0];selected=option?{id:option.value,owner:option.dataset.owner}:null;controls();refresh()};
 buttons.forEach(b=>b.onclick=()=>change(b.dataset.native,b.dataset.value===undefined?undefined:Number(b.dataset.value)));
 $('native-volume').oninput=()=>{$('native-volume-value').textContent=$('native-volume').value+'%'};
 $('native-volume').onchange=()=>change('volume',Number($('native-volume').value));
 // Reuse the visible Media refresh; no timer or request until an explicit scan.
 window.addEventListener('pi:media-state',refresh);
 window.addEventListener('pi:view',()=>{revision++;refresh()});
 document.addEventListener('visibilitychange',()=>{revision++;refresh()});
 window.addEventListener('pagehide',()=>{revision++});controls();
})();
