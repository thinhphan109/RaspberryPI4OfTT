(()=>{'use strict';
 const $=id=>document.getElementById(id);if(!$('audio'))return;
 function feedback(text,tone='info'){if(window.PiUI)window.PiUI.feedback('audio-result',text,tone);else $('audio-result').textContent=text;}
 let busy=false,loading=false,timer,powered=false,pollError=false;
 const visible=()=>!document.hidden&&$('audio').classList.contains('active');
 async function api(payload){
  const r=await fetch('/api/audio',{cache:'no-store',signal:AbortSignal.timeout(15000),...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value},body:JSON.stringify(payload)}:{})});
  if(r.redirected){location.href='/login';throw Error('Cần đăng nhập lại')}
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Chưa đọc được âm thanh');return d.data;
 }
 function button(text,payload){const b=document.createElement('button');b.type='button';b.className='btn btn-outline';b.textContent=text;b.disabled=busy;b.onclick=()=>command(payload);return b}
 function render(d){
  for(const kind of ['output','input']){
   const list=$(kind==='output'?'audio-outputs':'audio-inputs');list.replaceChildren();
   const devices=d.devices.filter(n=>n.kind===kind);
   for(const n of devices){
    const row=document.createElement('div');row.className='audio-device';
    const name=document.createElement('strong');name.textContent=n.label;
    const note=document.createElement('span');note.className='text-sm text-muted';note.textContent=d.defaults[kind]===n.name?'Đang dùng':'Có thể chọn';
    const controls=document.createElement('div');controls.className='hub-actions';
    const volume=document.createElement('input');volume.type='range';volume.min=0;volume.max=100;volume.value=Math.min(100,n.volume);volume.setAttribute('aria-label','Âm lượng '+n.label);volume.onchange=()=>command({action:'volume',id:n.id,kind,value:Number(volume.value)});
    const value=document.createElement('span');value.textContent=n.volume+'%';value.className='text-mono';
    controls.append(button('Dùng thiết bị này',{action:'default',id:n.id,kind}),button(n.muted?'Bật tiếng':'Tắt tiếng',{action:'mute',id:n.id,kind,muted:!n.muted}));
    row.append(name,note,volume,value,controls);list.append(row);
   }
   if(!devices.length){const p=document.createElement('p');p.className='text-muted';p.textContent=kind==='input'?'Chưa có micro vật lý. Kết nối micro USB hoặc tai nghe có micro tương thích.':'Chưa có đầu ra. Kết nối thiết bị rồi làm mới.';list.append(p)}
  }
  const bt=d.bluetooth;powered=bt.powered;$('audio-bt-state').textContent=bt.available?(powered?'Bluetooth đang bật':'Bluetooth đang tắt'):bt.error||'Không có Bluetooth';$('audio-bt-power').textContent=powered?'Tắt Bluetooth':'Bật Bluetooth';
  $('audio-bt-job').textContent=d.job.message||'';$('audio-bt-devices').replaceChildren();
  for(const n of bt.devices){const row=document.createElement('div'),name=document.createElement('div'),title=document.createElement('strong'),note=document.createElement('p'),controls=document.createElement('div');row.className='audio-bt-row';title.textContent=n.label;note.className='text-muted text-sm';note.textContent=n.address+' · '+(n.connected?'Đã kết nối':n.paired?'Đã ghép nối':'Chưa ghép nối');name.append(title,note);controls.className='hub-actions';if(!n.paired)controls.append(button('Ghép nối',{action:'pair',address:n.address}));controls.append(button(n.connected?'Ngắt kết nối':'Kết nối',{action:n.connected?'disconnect':'connect',address:n.address}));row.append(name,controls);$('audio-bt-devices').append(row)}
  if(!bt.devices.length)$('audio-bt-devices').textContent='Chưa có thiết bị. Bật chế độ ghép nối trên thiết bị rồi Quét.';
  if(d.errors.length){pollError=true;feedback(d.errors.join(' · '),'error');}else if(pollError){pollError=false;feedback('');}
 }
 async function refresh(){if(busy||loading||!visible()||$('audio').contains(document.activeElement)&&document.activeElement.type==='range')return;loading=true;try{render(await api())}catch(e){pollError=true;feedback(e.message,'error')}finally{loading=false}}
 async function command(payload){if(busy)return;busy=true;pollError=false;try{const result=await api(payload);render(result);if(!result.errors.length)feedback('Đã cập nhật thiết bị.','success')}catch(e){feedback(e.message,'error')}finally{busy=false;$('audio').querySelectorAll('button').forEach(b=>b.disabled=false)}}
 $('audio-refresh').onclick=()=>refresh();$('audio-bt-power').onclick=()=>command({action:'power',enabled:!powered});$('audio-bt-scan').onclick=()=>command({action:'scan'});
 function schedule(){clearInterval(timer);if(visible()){refresh();timer=setInterval(refresh,8000)}}
 window.addEventListener('pi:view',schedule);document.addEventListener('visibilitychange',schedule);schedule();
})();
