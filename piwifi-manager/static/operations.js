(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const csrf = $('ops-csrf')?.value;
  const date = t => new Date(t * 1000).toLocaleString('vi-VN');
  const stages = {unknown:'Chưa xác định kết quả · tác vụ quá thời hạn',queued:'Đã tiếp nhận yêu cầu', connecting:'Đang kết nối Wi-Fi', address:'Đã nhận địa chỉ IP', 'awaiting-browser':'Đã nhận IP · chờ trình duyệt kết nối lại', confirmed:'Đã kết nối lại dashboard', failed:'Kết nối thất bại · chờ kiểm tra phục hồi', recovered:'Đã phục hồi mạng trước'};
  async function get(path) {
    const r = await fetch(path, {cache:'no-store', signal:AbortSignal.timeout(12000)});
    if (r.redirected) { location.href='/login'; throw Error('Cần đăng nhập lại'); }
    const j = await r.json();
    if (!r.ok || !j.ok) throw Error(j.error || 'Không đọc được dữ liệu');
    return j.data;
  }
  function row(parent, name, value, state) {
    const element = document.createElement('div'); element.className='ops-row';
    const label = document.createElement('span'); label.textContent=name;
    const detail = document.createElement('span'); detail.textContent=value;
    if(state) detail.className=state==='ok'?'good':state==='failed'?'bad':'text-muted';
    element.append(label,detail); parent.append(element);
  }
  let operation = $('initial-operation') ? JSON.parse($('initial-operation').textContent) : null;
  let confirming = false;
  let hideTimer, lastStage, operationPoll;
  const visible=id=>!document.hidden && $(id)?.classList.contains('active');
  function showOperation(current) {
    const target=$('operation-progress');
    if(!target) return;
    clearTimeout(hideTimer);
    lastStage=current.stage;
    const terminal=['confirmed','recovered'].includes(current.stage);
    const remaining=15000-Math.max(0,(current.server_time||current.updated||current.timestamp||0)-(current.updated||current.timestamp||0))*1000;
    target.hidden=!current.id || (!operation && terminal && remaining<=0);
    target.textContent=(stages[current.stage]||'Đang kiểm tra thao tác mạng')+
      (['address','awaiting-browser'].includes(current.stage)&&current.ip?' · '+current.ip:'');
    if(!operation && terminal && remaining>0) hideTimer=setTimeout(()=>{target.hidden=true},remaining);
  }
  async function progress() {
    if(document.hidden || (!operation && !visible('network'))) return;
    try {
      const current = await get('/api/operation');
      if(operation && current.id !== operation.id) {
        $('operation-progress').textContent='Thao tác đã được thay thế. Mở dashboard để xem trạng thái mới.'; return;
      }
      if(!current.id) {if($('operation-progress')) $('operation-progress').hidden=true; return;}
      const target = $('operation-progress');
      showOperation(current);
      if(operation && ['confirmed','recovered'].includes(current.stage)) clearInterval(operationPoll);
      const steps=$('operation-steps');
      if(steps) {
        steps.replaceChildren();
        (current.steps||[]).forEach(s=>{const li=document.createElement('li');li.textContent=(stages[s.stage]||s.stage)+' · '+new Date(s.timestamp*1000).toLocaleTimeString('vi-VN');steps.append(li)});
      }
      if(current.stage==='awaiting-browser' && !confirming) {
        confirming=true;
        try {
          const r=await fetch('/api/operation/ack',{method:'POST',body:new URLSearchParams({csrf,id:current.id}),signal:AbortSignal.timeout(12000)});
          const j=await r.json(); if(j.ok) {showOperation({...current,stage:'confirmed',updated:current.server_time});if(operation) clearInterval(operationPoll);}
        } finally {confirming=false;}
      }
    } catch(e) {
      if($('operation-progress') && (operation || ['queued','connecting','address','awaiting-browser'].includes(lastStage))) {
        $('operation-progress').hidden=false;
        $('operation-progress').textContent='Đang chờ kết nối lại Pi. Hãy chuyển thiết bị sang mạng đích; nếu IP đổi, mở raspberrypi.local:18765. Chưa thể xác định kết quả.';
      }
    }
  }
  if(operation) {const resume=()=>{clearInterval(operationPoll);if(!document.hidden){progress();operationPoll=setInterval(progress,3000)}};resume();document.addEventListener('visibilitychange',resume);return;}
  let busy=false;
  function paintMetrics(m) {
      const power=m.power||{};
      const currentFlags=power.available?[power.undervoltage?'Nguồn đang yếu':null,power.frequency_capped?'Xung đang bị giới hạn':null,power.throttled?'Đang giảm hiệu năng':null,power.soft_temp_limit?'Đạt giới hạn nhiệt mềm':null].filter(Boolean):[];
      const pastFlags=[power.undervoltage_occurred?'Từng thiếu nguồn':null,power.throttled_occurred?'Từng giảm hiệu năng':null,power.frequency_capped_occurred?'Từng giới hạn xung':null,power.soft_temp_limit_occurred?'Từng đạt giới hạn nhiệt mềm':null].filter(Boolean);
      $('power-status').textContent=(power.available?(currentFlags.join(' · ')||'Nguồn & giảm xung: chưa có cảnh báo hiện tại'):'Chưa đọc được trạng thái nguồn / giảm xung')+' · Xung CPU: '+(m.frequency_mhz??'—')+' MHz'+(pastFlags.length?' · Từ lúc khởi động: '+pastFlags.join(', '):'');
      $('power-status').classList.toggle('bad',!!currentFlags.length);
      $('network-rates').replaceChildren();
      (m.network||[]).forEach(n=>row($('network-rates'),n.name,`↓ ${n.rx_rate===null?'—':(n.rx_rate/1024).toFixed(1)} KiB/s · ↑ ${n.tx_rate===null?'—':(n.tx_rate/1024).toFixed(1)} KiB/s · Tổng ↓ ${(n.rx/1048576).toFixed(1)} MiB / ↑ ${(n.tx/1048576).toFixed(1)} MiB`));
      $('top-processes').replaceChildren();
      (m.processes||[]).forEach(p=>{const tr=document.createElement('tr');[`${p.pid} / ${p.name}`,p.cpu===null?'—':p.cpu+'%',(p.rss/1048576).toFixed(1)+' MiB'].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td)});$('top-processes').append(tr)});
      const d=m.diagnostics||{};
      $('network-diagnostics').replaceChildren();
      const labels={ok:'Đạt',failed:'Thất bại',unknown:'Chưa kết luận',na:'Không áp dụng'};
      (d.layers||[]).forEach(l=>row($('network-diagnostics'),l.name,`${labels[l.state]} · ${l.detail}`,l.state));
      $('diagnostics-age').textContent=d.timestamp?'Kiểm tra lúc '+date(d.timestamp):'Đang chờ kiểm tra';
      if(d.error) row($('network-diagnostics'),'Trạng thái',d.error,'unknown');
      $('ops-updated').textContent=(m.stale?'Dữ liệu cũ · ':'Cập nhật · ')+date(m.timestamp);
  }
  async function refresh() {
    if(busy || !visible('activity')) return; busy=true;
    try {
      const items=await get('/api/events');$('event-list').replaceChildren();
      if(!items.length) row($('event-list'),'Chưa có sự kiện','Lịch sử bắt đầu từ bản cập nhật này');
      items.forEach(e=>row($('event-list'),date(e.timestamp),e.message,e.level==='warning'?'failed':null));
    } catch(e) { $('ops-updated').textContent='Dữ liệu cũ · '+e.message; }
    finally {busy=false;}
  }
  let chartPoints=[];
  function drawHistory(){
    const svg=$('history-chart');if(!svg||!svg.getBoundingClientRect().width)return;
    const end=chartPoints.at(-1)?.timestamp||Date.now()/1000,start=chartPoints[0]?.timestamp??end-3600;
    const steps=chartPoints.slice(1).map((p,i)=>p.timestamp-chartPoints[i].timestamp).filter(n=>n>0).sort((a,b)=>a-b),step=steps.length?steps[Math.floor(steps.length/2)]:60;
    const plot=PiCharts.frame(svg,{max:100,start:Math.min(start,end-60),end,unit:'CPU / RAM (%)',rightUnit:'Nhiệt độ (°C)'});
    for(const [id,key]of [['history-cpu','cpu'],['history-ram','ram'],['history-temp','temperature']])PiCharts.draw($(id),chartPoints,key,plot,Math.max(90,step*1.8));
    PiCharts.inspect(svg,{rows:chartPoints,plot,maxDistance:Math.max(90,step*1.8)/2,series:[{key:'cpu',label:'CPU',unit:'%',color:'var(--chart-cpu)'},{key:'ram',label:'RAM',unit:'%',color:'var(--chart-ram)'},{key:'temperature',label:'Nhiệt độ',unit:'°C',color:'var(--chart-temp)'}]});
  }
  PiCharts.observe($('history-chart'),drawHistory);
  async function chart() {
    if(!visible('activity')) return;
    try {
      const points=await get('/api/history?hours='+$('history-range').value);
      chartPoints=points;drawHistory();
      $('history-summary').textContent=points.length?`${date(points[0].timestamp)} → ${date(points.at(-1).timestamp)} · ${points.length} điểm hiển thị`:'Chưa đủ mẫu; lịch sử RAM lấy một mẫu mỗi phút và mất khi bộ giám sát khởi động lại.';
    } catch(e) {$('history-summary').textContent=e.message;}
  }
  async function releases() {
    if(!visible('storage')) return;
    try {
      const d=await get('/api/deployments');$('deployment-info').replaceChildren();
      row($('deployment-info'),'Bản đang chạy',d.current.version||'Chưa có metadata');
      row($('deployment-info'),'Triển khai lúc',d.current.timestamp?date(d.current.timestamp):'—');
      row($('deployment-info'),'Mã nguồn SHA-256',d.current.source_hash||'—');
      (d.snapshots||[]).forEach(s=>row($('deployment-info'),s.id,(s.bytes/1048576).toFixed(1)+' MiB'+(s.id===d.rollback?' · bản phục hồi kế tiếp':'')));
      $('rollback-button').disabled=!d.rollback;
    } catch(e){$('deployment-info').textContent=e.message;}
  }
  $('history-range').onchange=chart;
  let lastMetrics=JSON.parse($('initial-metrics').textContent);
  window.addEventListener('pi:metrics',e=>{lastMetrics=e.detail;if(visible('activity'))paintMetrics(lastMetrics)});
  const updateView=()=>{if(visible('activity'))paintMetrics(lastMetrics);refresh();chart();releases();progress()};
  
  let timers=[];
  function schedule(){timers.forEach(clearInterval);timers=[];if(document.hidden)return;updateView();
    if(visible('activity'))timers.push(setInterval(refresh,30000),setInterval(chart,60000));
    if(visible('storage'))timers.push(setInterval(releases,60000));
    if(visible('network')){let last=0;timers.push(setInterval(()=>{const wait=['queued','connecting','address','awaiting-browser'].includes(lastStage)?3000:30000;if(performance.now()-last>=wait){last=performance.now();progress()}},3000))}
  }
  window.addEventListener('pi:view',schedule);document.addEventListener('visibilitychange',schedule);schedule();
})();
