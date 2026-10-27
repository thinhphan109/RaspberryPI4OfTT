(()=>{'use strict';
const $=id=>document.getElementById(id),root=$('camera');if(!root)return;
let state={},active=false,busy=false,previewBusy=false,previewTimer,statusTimer,libraryTimer,watchTimer,watchBusy=false;
const viewer=Array.from(crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('');let watching=false;
let frozen=false,selection=0,rois=[],drag=null,blobURL=null,lastVideo='',calibrationDirty=false;
const libraryCards=[];
const gallery=$('camera-gallery');let gallerySession=null,galleryIndices=[],galleryPosition=0,galleryRequest=null,galleryURL=null,galleryEpoch=0,galleryDebounce,pageLeaving=false;
const img=$('camera-image'),canvas=$('camera-regions'),context=canvas.getContext('2d');
const message=(text,error=false)=>{if(window.PiUI)window.PiUI.feedback('camera-message',text,error?'error':'success');else{$('camera-message').textContent=text;$('camera-message').style.color=error?'var(--danger)':'';}};
async function api(payload){const response=await fetch('/api/camera',{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value}:{},body:payload?JSON.stringify(payload):undefined,cache:'no-store',signal:AbortSignal.timeout(10000)});if(response.redirected)throw Error('Phiên đăng nhập đã hết hạn');const result=await response.json();if(!result.ok)throw Error(result.error);return result.data;}
function visible(){return active&&!document.hidden&&!gallery.open&&!pageLeaving;}
function labelDuration(seconds){return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;}
function modeNote(){const position=$('camera-mode').value==='position';$('camera-interval-field').hidden=position;for(const id of ['camera-position-actions','camera-position-settings','camera-calibration-note'])$(id).hidden=!position;$('camera-mode-note').textContent=position?'Cần lưu mẫu vị trí trước khi ghi.':'Chụp đều theo chu kỳ đã chọn.';if(!position&&frozen)$('camera-live').click();}
function storageNote(){$('camera-storage-note').textContent=$('camera-storage').value==='missing'?'SSD chưa kết nối. Gắn lại ổ để ghi.':$('camera-storage').value==='ram'?'Bản thử RAM · 10 phút / 64 MiB · mất khi reboot.':'SSD đã được ghi nhớ · dữ liệu giữ qua reboot.';}
function updateLibraryCard(entry){
 const {row,note,retry,remove}=entry;
 const matches=job=>job?.id===row.id&&job.storage===row.storage;
 const live=matches(state.session)?{...state.session,state:'recording'}:matches(state.render_session)?{...state.render_session,state:'rendering'}:matches(state.last_result)?state.last_result:null;
 const current=live?{...row,...live}:row;
 const labels={ready:'Đã ghép',recording:'Đang ghi',rendering:'Đang ghép',interrupted:'Bị gián đoạn',incomplete:'Chưa ghép'};
 note.textContent=`${Number.isInteger(current.frames)?`${current.frames} ảnh`:'Chưa kiểm đếm ảnh'} · ${row.storage==='ram'?'RAM':row.storage} · ${labels[current.state]||'Chưa ghép'}`;
 retry.hidden=['recording','rendering'].includes(current.state);
 retry.disabled=remove.disabled=Boolean(state.recording||state.rendering);
}
function render(data){state=data;const enabled=data.enabled,recording=data.recording;
 if(recording&&data.session?.mode&&$('camera-mode').value!==data.session.mode){$('camera-mode').value=data.session.mode;modeNote();}
 $('camera-automatic').checked=data.automatic!==false;
 $('camera-power').disabled=recording;
 $('camera-power-note').textContent=recording?'Đang ghi · tiếp tục khi đóng trang.':data.manual_paused?'Đã tắt thủ công.':data.automatic?`${data.viewers||0} người xem · tự nghỉ khi không dùng.`:'Điều khiển bằng nút Bật / Tắt.';
 $('camera-power').textContent=enabled?'Tắt camera':'Bật camera';$('camera-live-state').textContent=data.available?'Đang có hình':enabled?'Đang kết nối…':'Đã tắt';
 $('camera-record-state').textContent=recording?'Đang ghi':data.rendering?'Đang ghép…':'Sẵn sàng';
 $('camera-record').disabled=!data.available||recording||data.rendering;$('camera-stop').disabled=!recording;
 for(const id of ['camera-mode','camera-interval','camera-storage'])$(id).disabled=recording||data.rendering;
 for(const id of ['camera-threshold','camera-settle','camera-roi-head','camera-roi-bed'])$(id).disabled=recording||data.rendering;
 if(recording||data.rendering)calibrationDirty=false;
 if(recording||data.rendering||(!calibrationDirty&&!frozen)){$('camera-threshold').value=data.threshold??6;$('camera-settle').value=data.settle??.2;}
 $('camera-freeze').disabled=!data.available||recording||data.rendering;$('camera-calibrate').disabled=!frozen||recording||data.rendering;
 $('camera-count').textContent=data.session?.frames??data.render_session?.frames??data.last_result?.frames??0;$('camera-elapsed').textContent=labelDuration(data.session?.duration??data.render_session?.duration??data.last_result?.duration??0);
 $('camera-session-note').textContent=data.error||data.session?.note||data.render_session?.note||data.last_result?.note||'Chưa có phiên ghi.';
 const tracking=data.tracking;
 $('camera-tracking').hidden=!tracking;
 $('camera-tracking').textContent=tracking?`Khớp mẫu ≤ ${tracking.threshold}% · Rời mẫu > ${tracking.departure_threshold}%${tracking.recent_max?` · Cao nhất 30 giây: ${tracking.recent_max.join(' / ')}%`:''}`:'';
 $('camera-calibration-warning').hidden=!data.calibration_warning||frozen||$('camera-mode').value!=='position';
 $('camera-calibration-warning').textContent=data.calibration_warning||'';
 $('camera-match').textContent=data.scores?`Sai lệch đầu / bàn: ${data.scores.join(' / ')}%`:data.calibrated?'Đã lưu vị trí mẫu':'Chưa có mẫu vị trí';
 const mounts=data.mounts||[],selected=data.storage_default??(data.storage_uuid?'missing':'ram'),key=JSON.stringify([mounts,selected]);
 if($('camera-storage').dataset.mounts!==key){$('camera-storage').dataset.mounts=key;const options=[new Option('RAM · Thử tối đa 10 phút','ram'),...mounts.map(m=>new Option(`SSD · ${m.path}`,m.path))];if(selected==='missing')options.push(new Option('SSD đã lưu · Chưa kết nối','missing'));$('camera-storage').replaceChildren(...options);$('camera-storage').value=selected;storageNote();}
 if(selected==='missing')$('camera-record').disabled=true;
 if(!data.available&&!frozen){img.hidden=true;$('camera-empty').hidden=false;}
 libraryCards.forEach(updateLibraryCard);
 const resultId=data.last_result?.id||'';
 if(resultId!==lastVideo){lastVideo=resultId;library();}
}
async function refresh(){if(!visible()||busy)return;try{render(await api());}catch(error){message(error.message,true);}}
async function command(payload){if(busy)return;busy=true;try{const data=await api(payload);if(payload.action!=='freeze')render(data);message('Đã cập nhật.');return data;}catch(error){message(error.message,true);}finally{busy=false;}}
async function preview(){if(!visible()||frozen||!state.enabled||previewBusy)return;previewBusy=true;try{const response=await fetch(`/api/camera/frame?t=${Date.now()}`,{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!response.ok||response.redirected)throw Error('Chưa có hình');const blob=await response.blob();if(!visible()||frozen)return;const next=URL.createObjectURL(blob),previous=blobURL;blobURL=next;img.src=next;img.hidden=false;$('camera-empty').hidden=true;if(previous)URL.revokeObjectURL(previous);}catch(_){/* Status endpoint gives the actionable device error. */}finally{previewBusy=false;}}
function draw(){context.clearRect(0,0,canvas.width,canvas.height);rois.forEach((roi,i)=>{if(!roi)return;context.strokeStyle=i?'#fb923c':'#60a5fa';context.fillStyle=i?'#fb923c22':'#60a5fa22';context.lineWidth=4;const [x,y,w,h]=roi.map((v,j)=>v*(j%2?canvas.height:canvas.width));context.fillRect(x,y,w,h);context.strokeRect(x,y,w,h);context.fillStyle=i?'#fb923c':'#60a5fa';context.font='bold 22px sans-serif';context.fillText(i?'Bàn in':'Đầu in',x+6,Math.max(24,y+24));});}
function point(event){const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))];}
canvas.addEventListener('pointerdown',event=>{if(!frozen)return;drag=point(event);canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{if(!drag)return;const p=point(event);rois[selection]=[Math.min(drag[0],p[0]),Math.min(drag[1],p[1]),Math.abs(p[0]-drag[0]),Math.abs(p[1]-drag[1])];draw();});
for(const name of ['pointerup','pointercancel'])canvas.addEventListener(name,()=>drag=null);
canvas.addEventListener('keydown',event=>{
 if(!frozen||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
 event.preventDefault();const r=rois[selection]||(selection?[.55,.55,.2,.2]:[.1,.1,.2,.2]),horizontal=['ArrowLeft','ArrowRight'].includes(event.key);
 const axis=horizontal?0:1,index=event.shiftKey?axis+2:axis,delta=['ArrowLeft','ArrowUp'].includes(event.key)?-.01:.01;
 r[index]=Math.max(event.shiftKey?.04:0,Math.min(1,r[index]+delta));
 r[0]=Math.min(r[0],1-r[2]);r[1]=Math.min(r[1],1-r[3]);rois[selection]=r;draw();
});
$('camera-roi-head').onclick=()=>{selection=0;message('Kéo một vùng chứa chi tiết đầu in trên ảnh mẫu.');};
$('camera-roi-bed').onclick=()=>{selection=1;message('Kéo một vùng chứa chi tiết bàn in; tránh vật thể đang in.');};
$('camera-freeze').onclick=async()=>{const data=await command({action:'freeze'});if(!data)return;frozen=true;img.src=`data:image/jpeg;base64,${data.jpeg}`;img.hidden=false;$('camera-empty').hidden=true;canvas.hidden=false;$('camera-live').hidden=false;$('camera-source').textContent='Ảnh mẫu đang giữ · Chọn hai vùng';rois=state.regions?.length===2?state.regions.map(r=>r.slice()):[];draw();render(state);message('Chọn đầu in và bàn in đúng vị trí chụp, rồi lưu mẫu.');};
$('camera-live').onclick=()=>{frozen=false;canvas.hidden=true;$('camera-live').hidden=true;$('camera-source').textContent='720p · Xem trực tiếp tối đa 4 ảnh/giây';render(state);preview();};
for(const id of ['camera-threshold','camera-settle'])$(id).addEventListener('input',()=>{calibrationDirty=true;});
$('camera-calibrate').onclick=async()=>{if(rois.length!==2||!rois[0]||!rois[1])return message('Chọn đủ hai vùng trước.',true);const data=await command({action:'calibrate',regions:rois,threshold:Number($('camera-threshold').value),settle:Number($('camera-settle').value)});if(data)calibrationDirty=false;};
$('camera-power').onclick=()=>command({action:'power',enabled:!state.enabled});
$('camera-automatic').onchange=()=>command({action:'automatic',enabled:$('camera-automatic').checked});
$('camera-record').onclick=async()=>{await command({action:'start',mode:$('camera-mode').value,interval:Number($('camera-interval').value)});if(state.recording&&frozen)$('camera-live').click();};
$('camera-stop').onclick=()=>command({action:'stop'});
$('camera-mode').onchange=modeNote;$('camera-storage').onchange=async()=>{await command({action:'storage',storage:$('camera-storage').value});$('camera-storage').dataset.mounts='';render(state);};
async function library(){if(!visible())return;try{const rows=await api({action:'list'});if(!visible())return;$('camera-library').replaceChildren();libraryCards.length=0;if(!rows.length){const p=document.createElement('p');p.className='text-muted text-sm';p.textContent='Chưa có phiên. Ảnh và video xuất hiện ở đây khi bắt đầu ghi.';$('camera-library').append(p);}
for(const row of rows){
 const card=document.createElement('div');card.className='camera-recording';
 const title=document.createElement('strong');title.textContent=row.id;
 const note=document.createElement('p');note.className='text-muted text-sm';
 const actions=document.createElement('div');actions.className='hub-actions';
 const photos=document.createElement('button');photos.type='button';photos.className='btn btn-outline';photos.textContent='Xem ảnh';photos.onclick=()=>openGallery(row);actions.append(photos);
 if(row.video){const a=document.createElement('a');a.className='btn btn-outline';a.textContent='Tải MP4';a.href=`/api/camera/video/${encodeURIComponent(row.id)}?storage=${encodeURIComponent(row.storage)}`;actions.append(a);}
 const retry=document.createElement('button');retry.type='button';retry.className='btn btn-outline';retry.textContent='Ghép ảnh gốc';retry.onclick=async()=>{await command({action:'render',id:row.id,storage:row.storage});library();};if(!row.video)actions.append(retry);
 const remove=document.createElement('button');remove.type='button';remove.className='btn btn-ghost';remove.textContent='Xóa phiên';remove.disabled=state.recording||state.rendering;remove.onclick=async()=>{if(confirm('Xóa video và toàn bộ ảnh gốc của phiên này?')){await command({action:'delete',id:row.id,storage:row.storage});library();}};
 actions.append(remove);card.append(title,note,actions);$('camera-library').append(card);const entry={row,note,retry,remove};libraryCards.push(entry);updateLibraryCard(entry);
}}
catch(error){message(error.message,true);}}
$('camera-library-refresh').onclick=library;
function galleryPath(index){return `/api/camera/photo/${encodeURIComponent(gallerySession.id)}/${index}?storage=${encodeURIComponent(gallerySession.storage)}`;}
function galleryMessage(text){$('camera-gallery-message').textContent=text;$('camera-gallery-message').hidden=false;}
function resetGallery(){
 ++galleryEpoch;clearTimeout(galleryDebounce);galleryRequest?.abort();galleryRequest=null;
 if(galleryURL)URL.revokeObjectURL(galleryURL);galleryURL=null;galleryIndices=[];gallerySession=null;
 $('camera-gallery-image').removeAttribute('src');$('camera-gallery-image').hidden=true;$('camera-gallery-download').hidden=true;
}
async function galleryFetch(url,json=false){
 galleryRequest?.abort();const controller=new AbortController();galleryRequest=controller;
 const timeout=setTimeout(()=>controller.abort(),10000);
 try{const response=await fetch(url,{cache:'no-store',signal:controller.signal});if(response.redirected)throw Error('Phiên đăng nhập đã hết hạn.');if(!response.ok)throw Error('Không đọc được ảnh. Kiểm tra ổ lưu còn kết nối và phiên chưa bị xóa.');return json?await response.json():await response.blob();}
 finally{clearTimeout(timeout);}
}
function galleryControls(){
 const total=galleryIndices.length,position=galleryPosition+1,index=galleryIndices[galleryPosition];
 $('camera-gallery-count').textContent=total?`Ảnh ${position} / ${total}`:'Chưa có ảnh';
 $('camera-gallery-file').textContent=total?`frame-${String(index).padStart(6,'0')}.jpg`:'';
 for(const id of ['camera-gallery-range','camera-gallery-jump']){$(id).max=Math.max(1,total);$(id).value=position;$(id).disabled=!total;}
 $('camera-gallery-prev').disabled=!total||galleryPosition===0;$('camera-gallery-next').disabled=!total||galleryPosition===total-1;
}
async function showPhoto(position){
 clearTimeout(galleryDebounce);if(!gallery.open||!galleryIndices.length||document.hidden)return;
 galleryPosition=Math.max(0,Math.min(galleryIndices.length-1,position));galleryControls();
 const ticket=++galleryEpoch,url=galleryPath(galleryIndices[galleryPosition]);
 $('camera-gallery-image').hidden=true;$('camera-gallery-download').hidden=true;galleryMessage('Đang tải ảnh…');
 try{const blob=await galleryFetch(url);if(ticket!==galleryEpoch||!gallery.open||document.hidden)return;
  const next=URL.createObjectURL(blob);if(galleryURL)URL.revokeObjectURL(galleryURL);galleryURL=next;
  $('camera-gallery-image').src=next;$('camera-gallery-image').alt=`Ảnh ${galleryPosition+1} của phiên ${gallerySession.id}`;$('camera-gallery-image').hidden=false;
  $('camera-gallery-message').hidden=true;$('camera-gallery-download').href=url+'&download=1';$('camera-gallery-download').hidden=false;
 }catch(error){if(ticket===galleryEpoch&&gallery.open)galleryMessage(error.name==='AbortError'?'Tải ảnh quá lâu. Bấm Trước hoặc Sau để thử lại.':error.message);}
}
async function openGallery(row){
 resetGallery();gallerySession=row;galleryPosition=0;galleryControls();$('camera-gallery-session').textContent=`${row.id} · ${row.storage==='ram'?'RAM':'SSD'}`;
 galleryMessage('Đang tải danh sách ảnh…');gallery.showModal();clearTimers();release();
 const ticket=++galleryEpoch;
 try{const result=await galleryFetch(`/api/camera/photos/${encodeURIComponent(row.id)}?storage=${encodeURIComponent(row.storage)}`,true);
  if(ticket!==galleryEpoch||!gallery.open)return;if(!result.ok)throw Error(result.error||'Không đọc được phiên.');
  galleryIndices=result.data.indices;galleryControls();if(galleryIndices.length)showPhoto(0);else galleryMessage('Phiên này chưa có ảnh đã lưu. Đóng rồi mở lại sau khi chụp.');
 }catch(error){if(ticket===galleryEpoch&&gallery.open)galleryMessage(error.name==='AbortError'?'Tải danh sách quá lâu. Đóng rồi mở lại phiên để thử lại.':error.message);}
}
$('camera-gallery-close').onclick=()=>gallery.close();gallery.addEventListener('close',()=>{resetGallery();schedule();});
$('camera-gallery-prev').onclick=()=>showPhoto(galleryPosition-1);$('camera-gallery-next').onclick=()=>showPhoto(galleryPosition+1);
$('camera-gallery-range').oninput=()=>{clearTimeout(galleryDebounce);const position=Number($('camera-gallery-range').value)-1;galleryDebounce=setTimeout(()=>showPhoto(position),150);};
function jumpPhoto(){const value=Number($('camera-gallery-jump').value);if(Number.isInteger(value)&&value>=1)showPhoto(value-1);else galleryControls();}
$('camera-gallery-jump').onchange=jumpPhoto;
$('camera-gallery-jump').oninput=()=>{clearTimeout(galleryDebounce);galleryDebounce=setTimeout(jumpPhoto,300);};
$('camera-gallery-jump').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();jumpPhoto();}});
gallery.addEventListener('keydown',event=>{if(event.target.tagName==='INPUT')return;if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();showPhoto(galleryPosition+(event.key==='ArrowLeft'?-1:1));}});
async function heartbeat(){
 if(!visible()||watchBusy)return;watching=true;watchBusy=true;
 try{const data=await api({action:'watch',viewer,watching:true});if(visible())render(data);}
 catch(error){if(visible())message(error.message,true);}
 finally{watchBusy=false;}
}
function release(){
 if(!watching)return;watching=false;
 const payload=JSON.stringify({action:'watch',viewer,watching:false,csrf:$('ops-csrf').value});
 const body=new Blob([payload],{type:'application/json'});
 if(!navigator.sendBeacon||!navigator.sendBeacon('/api/camera',body))fetch('/api/camera',{method:'POST',body:payload,headers:{'Content-Type':'application/json'},keepalive:true}).catch(()=>{});
}
function clearTimers(){clearInterval(previewTimer);clearInterval(statusTimer);clearInterval(libraryTimer);clearInterval(watchTimer);}
function schedule(){clearTimers();if(!visible()){release();return;}heartbeat();refresh();preview();library();watchTimer=setInterval(heartbeat,4000);previewTimer=setInterval(preview,250);statusTimer=setInterval(refresh,2000);libraryTimer=setInterval(library,15000);}
window.addEventListener('pi:view',event=>{active=event.detail==='camera';if(!active&&gallery.open)gallery.close();schedule();});document.addEventListener('visibilitychange',()=>{if(document.hidden)galleryRequest?.abort();else if(gallery.open&&galleryIndices.length)showPhoto(galleryPosition);schedule();});
window.addEventListener('pagehide',()=>{pageLeaving=true;clearTimers();release();if(gallery.open)gallery.close();});window.addEventListener('pageshow',()=>{pageLeaving=false;schedule();});
active=root.classList.contains('active');modeNote();schedule();
})();
