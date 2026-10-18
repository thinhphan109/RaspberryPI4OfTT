(() => {
  'use strict';
  const $=id=>document.getElementById(id), put=(id,v)=>{if($(id))$(id).textContent=v;};
  let timer,busy=false,lastKey='',points=[],lastTimestamp=0,filter='Tất cả',selected=11,pins=[];
  const labels={undervoltage:'Thiếu áp',frequency_capped:'Giới hạn xung',throttled:'Giảm hiệu năng',soft_temp_limit:'Giới hạn nhiệt mềm'};
  const rate=v=>v==null?'—':v<1024?v.toFixed(0)+' B/s':v<1048576?(v/1024).toFixed(1)+' KiB/s':(v/1048576).toFixed(1)+' MiB/s';
  function drawTraffic(){
    const svg=document.querySelector('.traffic-chart');if(!svg||!svg.getBoundingClientRect().width||!points.length)return;
    const maximum=Math.max(1,...points.flatMap(p=>[p.rx||0,p.tx||0]));
    const divisor=maximum>=1048576?1048576:maximum>=1024?1024:1,unit=divisor===1048576?'MiB/s':divisor===1024?'KiB/s':'B/s';
    const end=points.at(-1).t,rows=points.map(p=>({...p,rx:p.rx===null?null:p.rx/divisor,tx:p.tx===null?null:p.tx/divisor}));
    const plot=PiCharts.frame(svg,{max:PiCharts.ceiling(maximum/divisor),start:end-290,end,unit});
    for(const [id,key]of [['traffic-rx','rx'],['traffic-tx','tx']])PiCharts.draw($(id),rows,key,plot,25);
    PiCharts.inspect(svg,{rows,plot,maxDistance:12.5,series:[{key:'rx',label:'Nhận (RX)',color:'var(--chart-rx)',format:v=>rate(v*divisor)},{key:'tx',label:'Gửi (TX)',color:'var(--chart-tx)',format:v=>rate(v*divisor)}]});
  }
  function paint(m){
    const p=m.power||{},now=Object.keys(labels).filter(k=>p[k]),past=Object.keys(labels).filter(k=>p[k+'_occurred']);
    put('power-badge',!p.available?'Nguồn: chưa có dữ liệu':now.length?now.map(k=>labels[k]).join(' · '):past.length?'Có cảnh báo từ lần boot':'Nguồn ổn định');
    $('power-badge').className='badge '+(m.stale?'':p.status==='danger'?'badge-danger':p.status==='warning'?'badge-warning':p.status==='healthy'?'badge-success':'');
    put('power-detail',(m.stale?'Dữ liệu cũ · ':'')+'Hiện tại: '+(now.map(k=>labels[k]).join(', ')||(!p.available?'Không rõ':'Không có cờ cảnh báo'))+' · Từ boot: '+(past.map(k=>labels[k]).join(', ')||(!p.available?'Không rõ':'Không có cờ cảnh báo'))+' · '+(p.raw||'—')+' · CPU '+(m.frequency_mhz??'—')+' MHz');
    const n=(m.network||[]).find(n=>n.name===m.primary_interface)||(m.network||[]).find(n=>n.name==='wlan0')||(m.network||[])[0];
    if(n){
      const key=(m.boot_id||'unknown')+':'+n.name;
      if(key!==lastKey){lastKey=key;points=[];lastTimestamp=0;try{const saved=JSON.parse(sessionStorage.getItem('pi:traffic')||'null');if(saved?.key===key&&Array.isArray(saved.points))points=saved.points.filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.rx)&&Number.isFinite(p.tx)).slice(-30)}catch(e){}}
      if(m.timestamp!==lastTimestamp){lastTimestamp=m.timestamp;points.push({t:m.timestamp,rx:n.rx_rate,tx:n.tx_rate});points=points.slice(-30);try{sessionStorage.setItem('pi:traffic',JSON.stringify({key,points}))}catch(e){}}
      put('traffic-current','↓ '+rate(n.rx_rate)+'   ↑ '+rate(n.tx_rate));put('traffic-mini','↓ '+rate(n.rx_rate)+' · ↑ '+rate(n.tx_rate));
      put('traffic-caption',n.name+' · Tổng bộ đếm interface: nhận '+(n.rx/1073741824).toFixed(2)+' GiB · gửi '+(n.tx/1073741824).toFixed(2)+' GiB');
      drawTraffic();
    }
    const s=m.ssh_security||{};
    put('ssh-summary',s.active_connections_count==null?'SSH: chưa đọc được kết nối':'SSH: '+s.active_connections_count+' kết nối TCP'+(s.active_ips?.length?' · '+s.active_ips.join(', '):'')+' — không đồng nghĩa đã xác thực');
    put('ssh-coverage',(s.failed_observed_count==null?'Chưa biết số lỗi':s.failed_observed_count+' lần xác thực thất bại đã quan sát')+' · '+(s.reason||'Chưa có dữ liệu')+(s.top_failed_ip?' · IP nhiều lỗi: '+s.top_failed_ip:''));
    $('ssh-logins').replaceChildren();
    (s.last_logins||[]).forEach(r=>{const tr=document.createElement('tr');[r.user,r.ip,new Date(r.timestamp*1000).toLocaleString('vi-VN'),r.method].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td)});$('ssh-logins').append(tr)});
    if(!s.last_logins?.length)put('ssh-empty','Chưa có đăng nhập trong dữ liệu quan sát được');else put('ssh-empty','');
  }
  function drawPins(){
    const focused=document.activeElement?.closest?.('#gpio-board .pin')?.dataset.physical;
    $('gpio-board').replaceChildren();
    pins.forEach(p=>{
      const button=document.createElement('button');button.type='button';
      button.className='pin '+(p.bcm==null?'pin-power':'pin-gpio')+(p.level===1?' high':'')+(selected===p.physical?' selected':'');
      button.dataset.physical=String(p.physical);button.dataset.group=p.bcm==null?p.name:p.groups[0];button.dataset.dim=filter!=='Tất cả'&&!p.groups.includes(filter);
      button.style.gridColumn=String(21-Math.ceil(p.physical/2));button.style.gridRow=p.physical%2?'1':'2';
      const label=document.createElement('span'),number=document.createElement('span'),contact=document.createElement('span');
      label.className='pin-label';
      const name=document.createElement('span'),alternative=document.createElement('span');name.className='pin-bcm';name.textContent=p.name;
      alternative.className='pin-alternative';const functions=p.function.split(' / ');alternative.textContent=p.bcm==null?(p.name==='GND'?'Đất':'Nguồn'):p.function==='GPIO đa năng'?'GPIO':functions.find(f=>f.startsWith(p.groups[0]))||functions[0];label.append(name,alternative);
      number.className='pin-number';number.textContent=p.physical;
      contact.className='pin-contact';contact.setAttribute('aria-hidden','true');
      button.append(label,number,contact);button.setAttribute('aria-label','Chân vật lý '+p.physical+', '+p.name+', '+p.function);button.title='Chân '+p.physical+' · '+p.name+' · '+p.function;button.setAttribute('aria-pressed',selected===p.physical);
      button.onclick=()=>{selected=p.physical;drawPins();$('gpio-board').querySelector('[data-physical="'+selected+'"]').focus({preventScroll:true})};
      $('gpio-board').append(button);
    });
    if(focused)$('gpio-board').querySelector('[data-physical="'+focused+'"]')?.focus({preventScroll:true});
    const p=pins.find(p=>p.physical===selected);if(!p)return;
    $('pin-name').closest('.pin-inspector').dataset.group=p.bcm==null?p.name:p.groups[0];
    put('pin-name','Chân '+p.physical+' / '+p.name);put('pin-function',p.function+' · '+p.groups.join(', '));
    put('pin-state',p.bcm==null?'Chân nguồn/đất — không có giá trị GPIO để đọc':(p.func||'Không rõ')+' · '+(p.level==null?'Chưa đọc được mức logic':p.level?'HIGH':'LOW')+' · Pull '+(p.pull||'—'));
    put('pin-help',p.bcm==null?'Không thể đóng/ngắt chân nguồn bằng phần mềm.':p.bcm<2?'Dành cho nhận diện HAT; khóa điều khiển.':'GPIO là tín hiệu 3,3 V, không chịu 5 V. Tải như relay, quạt, servo cần mạch/nguồn phù hợp. Trạng thái quan sát không xác nhận chân đang trống.');
  }
  async function refresh(){if(document.hidden||!$('gpio').classList.contains('active')||busy)return;busy=true;try{const r=await fetch('/api/gpio/status',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(r.redirected){location.href='/login';return}const j=await r.json();if(!r.ok||!j.ok)throw Error('Không đọc được GPIO');pins=j.data.pins;put('gpio-status',j.data.model+' · '+j.data.reason+' · '+new Date(j.data.timestamp*1000).toLocaleTimeString('vi-VN'));drawPins()}catch(e){put('gpio-status','Dữ liệu cũ · '+e.message)}finally{busy=false}}
  function schedule(){clearInterval(timer);if(!document.hidden&&$('gpio').classList.contains('active')){refresh();timer=setInterval(refresh,10000)}}
  $('gpio-filters').querySelectorAll('button').forEach(b=>b.onclick=()=>{filter=b.textContent;$('gpio-filters').querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));drawPins()});
  window.addEventListener('pi:metrics',e=>paint(e.detail));window.addEventListener('pi:view',schedule);document.addEventListener('visibilitychange',schedule);
  PiCharts.observe(document.querySelector('.traffic-chart'),drawTraffic);window.addEventListener('pi:view',drawTraffic);
  paint(JSON.parse($('initial-metrics').textContent));schedule();
})();
