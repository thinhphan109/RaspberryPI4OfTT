(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  if(!$('hub-apps'))return;
  let currentIP='', busy=false, timer, checkBusy=false, checkedNetwork=null, autoChecked=false;
  const visible=()=>!document.hidden&&$('apps').classList.contains('active');
  async function api(path,options={}) {
    const r=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(15000),...options});
    if(r.redirected){location.href='/login';throw Error('Cần đăng nhập lại');}
    const j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||'Chưa đọc được dữ liệu');return j.data;
  }
  async function copy(value){
    if(!value)throw Error('Chưa có IP');
    try{await navigator.clipboard.writeText(value);}catch(_){
      const input=document.createElement('textarea');input.value=value;document.body.append(input);input.select();
      const ok=document.execCommand('copy');input.remove();if(!ok)throw Error('Không sao chép được; chọn địa chỉ IP hiển thị để sao chép thủ công.');
    }
    $('hub-status').textContent='Đã sao chép '+value;
  }
  function link(parent,label,url){const a=document.createElement('a');a.className='btn btn-outline';a.textContent=label;a.href=url;a.target='_blank';a.rel='noopener';parent.append(a);}
  async function refresh(){
    if(busy)return;busy=true;$('hub-refresh').disabled=true;
    try{
      const d=await api('/api/hub');currentIP=d.ip||'';
      const networkKey=JSON.stringify([currentIP,d.ssid]);
      if(checkedNetwork!==null&&checkedNetwork!==networkKey){
        $('hub-dns-state').textContent='Mạng của Pi đã đổi — cần kiểm tra lại';
        $('hub-dns-state').className='badge badge-warning';
        $('hub-dns-result').textContent='Cập nhật DNS theo IP mới nếu cần rồi bấm kiểm tra lại.';
      }
      checkedNetwork=networkKey;
      $('hub-ip').textContent=currentIP||'Chưa có IP LAN';$('hub-copy-ip').disabled=!currentIP;
      $('hub-network').textContent=(d.ssid||'Chưa kết nối')+' · '+d.hostname;
      $('hub-updated').textContent='Đọc từ Pi lúc '+new Date(d.updated*1000).toLocaleTimeString('vi-VN')+' · tự làm mới khi mục này đang mở';
      $('hub-apps').replaceChildren();
      d.apps.forEach(item=>{
        const card=document.createElement('article');card.className='card hub-app';
        const state=document.createElement('span');state.className='badge '+(item.state==='active'?'badge-success':'badge-warning');state.textContent=({'active':'Đang chạy','inactive':'Đã dừng','unknown':'Chưa đọc được','deactivating':'Đang dừng','activating':'Đang khởi động','failed':'Lỗi'})[item.state]||item.state;
        const title=document.createElement('h2');title.textContent=item.name;
        const desc=document.createElement('p');desc.className='text-muted text-sm';desc.textContent=item.description;
        const actions=document.createElement('div');actions.className='hub-actions';
        if(item.lan_url)link(actions,'Mở trong LAN',item.lan_url);
        if(item.public_url)link(actions,'Mở qua tên miền',item.public_url);
        if(item.loopback){const note=document.createElement('p');note.className='text-sm';note.textContent='Mở qua nút Camera trên Pi Control của Windows.';actions.append(note);}
        card.append(state,title,desc,actions);$('hub-apps').append(card);
      });$('hub-status').textContent='Đã cập nhật kết nối. Tên miền dashboard vẫn dùng được khi IP LAN thay đổi và Pi có Internet.';
    }catch(e){currentIP='';$('hub-copy-ip').disabled=true;$('hub-status').textContent='Dữ liệu có thể đã cũ: '+e.message;}
    finally{busy=false;$('hub-refresh').disabled=false;}
  }
  $('hub-refresh').onclick=refresh;
  $('hub-copy-ip').onclick=()=>copy(currentIP).catch(e=>$('hub-status').textContent=e.message);
  async function checkDNS(){
    if(checkBusy)return;checkBusy=true;$('hub-dns-check').disabled=true;
    $('hub-dns-result').textContent='Đang gửi truy vấn thử…';
    $('hub-dns-state').textContent='Đang kiểm tra thiết bị này…';
    $('hub-dns-state').className='badge badge-warning';
    let image;
    try{
      const d=await api('/api/dns-check',{method:'POST',headers:{'X-CSRF-Token':$('ops-csrf').value}});
      image=new Image();image.referrerPolicy='no-referrer';image.src='https://'+d.domain+'/pixel.png';
      let result;
      for(let i=0;i<4;i++){
        await new Promise(resolve=>setTimeout(resolve,2000));
        result=await api('/api/dns-check');if(result.seen)break;
      }
      const labels={verified:'Đã xác nhận dùng AdGuard và chặn được mẫu thử',filter_error:'Đã qua AdGuard — mẫu thử chưa được chặn',unconfirmed:'Chưa xác nhận thiết bị đang dùng AdGuard'};
      $('hub-dns-state').textContent=labels[result.status]||labels.unconfirmed;
      $('hub-dns-state').className='badge '+(result.status==='verified'?'badge-success':'badge-warning');
      $('hub-dns-result').textContent=result.message+' '+(result.filtering?'Bộ lọc trên Pi hoạt động.':'Bộ lọc trên Pi chưa chặn tên miền kiểm tra.')+' Kiểm tra lúc '+new Date(result.checked_at*1000).toLocaleTimeString('vi-VN');
    }catch(e){$('hub-dns-result').textContent=e.message;$('hub-dns-state').textContent='Chưa kiểm tra được';$('hub-dns-state').className='badge badge-warning';}
    finally{if(image)image.src='';checkBusy=false;$('hub-dns-check').disabled=false;}
  }
  $('hub-dns-check').onclick=checkDNS;
  window.addEventListener('online',()=>{if(visible()&&!checkBusy)checkDNS();});
  if(navigator.connection)navigator.connection.addEventListener('change',()=>{
    $('hub-dns-state').textContent='Kết nối thiết bị đã đổi — cần kiểm tra lại';
    $('hub-dns-state').className='badge badge-warning';
  });
  function schedule(){clearInterval(timer);if(visible()){refresh();if(!autoChecked){autoChecked=true;checkDNS();}timer=setInterval(refresh,30000);}}
  window.addEventListener('pi:view',schedule);document.addEventListener('visibilitychange',schedule);schedule();
})();
