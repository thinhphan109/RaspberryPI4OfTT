(()=>{'use strict';
 const $=id=>document.getElementById(id);if(!$('sd-write-rate'))return;
 let timer,version=0,data=null;
 const visible=()=>!document.hidden&&$('storage').classList.contains('active');
 const date=t=>t?new Date(t*1000).toLocaleString('vi-VN'):'chưa lưu';
 function unit(value){let scale=1,name='B';for(const next of ['KiB','MiB','GiB','TiB']){if(value/scale<1024)break;scale*=1024;name=next}return {scale,name}}
 function bytes(value){if(!Number.isFinite(value))return '—';const u=unit(value);return (value/u.scale).toLocaleString('vi-VN',{maximumFractionDigits:2})+' '+u.name}
 function draw(){
  if(!data?.available||!visible())return;
  const rates=data.rate_history||[],daily=data.daily_history||[],now=data.timestamp;
  const speedUnit=unit(Math.max(0,...rates.map(r=>r.rate||0))),volumeUnit=unit(Math.max(0,...daily.map(r=>r.written||0)));
  const points=rates.map(r=>({...r,value:r.rate==null?null:r.rate/speedUnit.scale}));
  const first=points[0]?.timestamp??now-3600,last=points.at(-1)?.timestamp??now;
  const speed=PiCharts.frame($('sd-rate-chart'),{max:PiCharts.ceiling(Math.max(0,...points.map(p=>p.value||0))),start:Math.min(first,last-60),end:last,unit:speedUnit.name+'/s'});
  const steps=points.slice(1).map((p,i)=>p.timestamp-points[i].timestamp).filter(n=>n>0).sort((a,b)=>a-b),step=steps[Math.floor(steps.length/2)]||60;
  PiCharts.draw($('sd-rate-path'),points,'value',speed,step*1.8);
  PiCharts.inspect($('sd-rate-chart'),{rows:points,plot:speed,maxDistance:step*.9,series:[{key:'value',label:'Tốc độ ghi',color:'var(--chart-tx)',format:v=>bytes(v*speedUnit.scale)+'/s'}]});
  const start=(daily[0]?.timestamp??now)-43200,end=(daily.at(-1)?.timestamp??now)+43200;
  const p=PiCharts.frame($('sd-daily-chart'),{max:PiCharts.ceiling(Math.max(0,...daily.map(r=>r.written/volumeUnit.scale))),start,end,unit:volumeUnit.name});
  const bars=$('sd-daily-bars');bars.replaceChildren();
  const barWidth=Math.max(1,Math.min(32,(p.right-p.left)/Math.max(1,daily.length)*.65));
  daily.forEach(r=>{const node=document.createElementNS('http://www.w3.org/2000/svg','rect'),x=p.left+(r.timestamp-p.start)/(p.end-p.start)*(p.right-p.left),height=r.written/volumeUnit.scale/p.max*(p.bottom-p.top);for(const[k,v]of Object.entries({x:x-barWidth/2,y:p.bottom-height,width:barWidth,height}))node.setAttribute(k,String(v));const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=date(r.timestamp)+' · '+bytes(r.written);node.append(title);bars.append(node)});
  PiCharts.inspect($('sd-daily-chart'),{rows:daily,plot:p,prefix:data.daily_grouped?'Nhóm ngày · mốc cuối: ':'',series:[{key:'written',label:data.daily_grouped?'Ghi trong nhóm ngày':'Ghi trong ngày',color:'var(--chart-rx)',format:bytes,marker:false}]});
 }
 function paint(d){
  data=d;
  if(!d.available){$('sd-write-status').textContent=d.error||'Chưa có dữ liệu';return}
  $('sd-write-device').textContent=d.name+' · '+d.model+' · Bắt đầu '+date(d.started);
  $('sd-write-rate').textContent=d.rate==null?'Chờ mẫu kế tiếp':bytes(d.rate)+'/s';
  $('sd-write-boot').textContent=bytes(d.boot_bytes);$('sd-write-total').textContent=bytes(d.total_bytes);
  $('sd-write-status').textContent=(d.stale?'Dữ liệu cũ · ':'')+'Cập nhật '+date(d.timestamp)+' · Đã lưu '+date(d.saved_at)+(d.error?' · '+d.error:'');
  $('sd-rate-note').textContent=(d.rate_history?.length?'Trung bình từng khoảng; ':'Đang thu thập mẫu; ')+'chi tiết giữ 7 ngày, tổng theo giờ giữ 90 ngày.';
  $('sd-daily-note').textContent=(d.daily_grouped?'Các ngày được gộp theo khoảng để vừa đồ thị. ':'Ngày 00:00–24:00, giờ Việt Nam; chốt ở lượt lấy mẫu đầu sau 00:00. ')+'Lịch sử lưu lâu dài, lưu gộp 5 phút/lần. Mất điện có thể thiếu phần chưa lưu của lần chạy trước.';
  draw();
 }
 async function refresh(){
  if(!visible())return;const request=++version;
  try{const r=await fetch('/api/storage-writes?hours='+$('sd-write-hours').value+'&days='+$('sd-write-days').value,{cache:'no-store',signal:AbortSignal.timeout(8000)});if(r.redirected){location.href='/login';return}const j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||'Không đọc được lượng ghi');if(request===version)paint(j.data)}catch(e){if(request===version)$('sd-write-status').textContent='Dữ liệu cũ · '+e.message}
 }
 function schedule(){clearInterval(timer);version++;if(visible()){refresh();timer=setInterval(refresh,10000)}}
 $('sd-write-hours').onchange=refresh;$('sd-write-days').onchange=refresh;
 PiCharts.observe($('sd-rate-chart'),draw);PiCharts.observe($('sd-daily-chart'),draw);
 window.addEventListener('pi:view',schedule);document.addEventListener('visibilitychange',schedule);schedule();
})();
