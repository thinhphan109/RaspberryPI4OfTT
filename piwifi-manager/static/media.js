(()=>{'use strict';
 const $=id=>document.getElementById(id);if(!$('media'))return;
 let busy=false,timer,loading=false,nonstop=false,settingsLoaded=false,repeatLoaded=false,lastWarning=false;
 const visible=()=>!document.hidden&&($('media').classList.contains('active')||$('overview').classList.contains('active'));
 let standby=false,connected=false;
 function powerControls(){
  document.querySelectorAll('[data-media-power]').forEach(b=>b.disabled=busy||(b.dataset.mediaPower==='off'?standby:!standby&&connected));
  $('media-start').disabled=busy;
  document.querySelectorAll('[data-media],#media-play,#media-dislike,#media-volume').forEach(b=>{if(!b.matches('[data-media="clear"],[data-media="remove"]'))b.disabled=busy||standby});
 }
 const clock=n=>{n=Math.max(0,Math.floor(n||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0')};
 async function api(payload){
  const r=await fetch('/api/media',{cache:'no-store',signal:AbortSignal.timeout(14000),...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value},body:JSON.stringify(payload)}:{})});
  if(r.redirected){location.href='/login';throw Error('Cần đăng nhập lại')}
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Media chưa sẵn sàng');return d.data;
 }
 function render(d){
  standby=!!d.standby;connected=!!d.connected;powerControls();
  $('resource-mode-state').textContent=standby?'Media đang nghỉ · trình duyệt đã đóng':connected?'Media đang mở · cho nghỉ khi không nghe nhạc':'Media chưa kết nối · bấm Bật Media để mở trình duyệt';
  const prefs=d.preferences;
  $('media-policy-note').textContent=d.policy_note||'';
  if(prefs){
   if(!repeatLoaded){$('media-repeat-enabled').checked=prefs.repeat.enabled;$('media-repeat-hours').value=prefs.repeat.hours;repeatLoaded=true}
   const sleep=prefs.sleep;
   $('media-sleep-cancel').hidden=!sleep.active;
   $('media-sleep-note').textContent=sleep.expired?'Đã hết giờ · nhạc đang dừng. Bấm Phát để nghe tiếp.':sleep.active?'Còn '+clock(sleep.remaining)+' · '+(sleep.remaining<=sleep.fade_seconds?'đang giảm âm lượng':'sẽ giảm âm lượng trước khi dừng'):'Chưa hẹn giờ.';
   $('media-disliked-count').textContent=prefs.disliked.length;$('media-disliked').replaceChildren();
   prefs.disliked.forEach(item=>{const li=document.createElement('li'),name=document.createElement('span'),button=document.createElement('button');name.textContent=item.title;button.textContent='Bỏ chặn';button.className='btn btn-outline';button.onclick=()=>command({action:'undislike',id:item.id});li.append(name,button);$('media-disliked').append(li)});
   if(!prefs.disliked.length){const li=document.createElement('li');li.textContent='Chưa có bài không thích.';$('media-disliked').append(li)}
  }
  nonstop=!!d.nonstop;$('media-nonstop').textContent=nonstop?'Nonstop đang bật · Tắt':'Bật Nonstop';$('media-nonstop').setAttribute('aria-pressed',String(nonstop));$('media-nonstop-note').textContent=d.nonstop_note||'';
  $('media-title').textContent=d.title||'Chưa có video';
  $('media-state').textContent=(standby?'Đang nghỉ':!d.connected?'Chưa kết nối':d.ad?'Đang quảng cáo':!d.has_video?'Chọn video để bắt đầu':d.paused?'Đã tạm dừng':'Đang phát')+(d.autoplay?' · YouTube tự đề xuất':'');
  $('media-state').className='badge '+(d.connected?'badge-success':'badge-warning');
  $('media-toggle').textContent=d.paused?'▶ Phát':'Ⅱ Tạm dừng';
  $('media-progress').max=d.duration||1;$('media-progress').value=d.position||0;
  $('media-time').textContent=clock(d.position)+' / '+(d.duration?clock(d.duration):'Trực tiếp / chưa rõ');
  if(document.activeElement!==$('media-volume'))$('media-volume').value=d.volume??50;
  $('media-volume-value').textContent=(d.volume??0)+'%';
  const policy=d.volume_schedule;
  if(policy){
   $('media-limit-note').textContent=policy.active?'Đang giới hạn tối đa '+policy.limit+'% · '+policy.start+'–'+policy.end+' (giờ Việt Nam)':policy.enabled?'Lịch giới hạn '+policy.start+'–'+policy.end+' · tối đa '+policy.limit+'% (giờ Việt Nam)':'Giới hạn theo giờ đang tắt';
   if(!settingsLoaded){$('media-limit-enabled').checked=policy.enabled;$('media-limit-start').value=policy.start;$('media-limit-end').value=policy.end;$('media-limit-value').value=policy.limit;settingsLoaded=true}
  }
  const upcoming=d.up_next,validNext=upcoming&&/^https:\/\/www\.youtube\.com\/watch\?v=[\w-]{11}$/.test(upcoming.url||'');
  $('media-next-link').hidden=!validNext;$('media-next-empty').hidden=!!validNext;$('media-next-empty').textContent='Chưa có đề xuất phù hợp sau khi lọc bài đã nghe và bài không thích.';
  $('media-next-source').textContent=validNext?upcoming.source:'';
  if(validNext){$('media-next-link').href=upcoming.url;$('media-next-link').textContent=upcoming.title||'Bài tiếp theo'}
  const match=(d.url||'').match(/^https:\/\/www\.youtube\.com\/watch\?v=([\w-]{11})$/);
  $('media-art').hidden=!match;$('media-art-empty').hidden=!!match;$('media-video-link').hidden=!match;
  if(match){const src='https://i.ytimg.com/vi/'+match[1]+'/hqdefault.jpg';if($('media-art').src!==src)$('media-art').src=src;$('media-video-link').href=d.url}
  $('media-count').textContent=(d.queue||[]).length;$('media-queue').replaceChildren();
  (d.queue||[]).forEach((url,index)=>{const li=document.createElement('li'),a=document.createElement('a'),b=document.createElement('button');a.textContent='Video '+(index+1)+' · '+url.split('v=')[1];a.href=url;a.target='_blank';a.rel='noopener';b.textContent='Bỏ';b.className='btn btn-outline';b.onclick=()=>command({action:'remove',index});li.append(a,b);$('media-queue').append(li)});
  if(!(d.queue||[]).length){const li=document.createElement('li');li.textContent='Chưa có video trong hàng đợi.';$('media-queue').append(li)}
  if(d.error||d.notice){$('media-result').textContent=d.error||d.notice;lastWarning=true}
  else if(lastWarning){$('media-result').textContent='';lastWarning=false}
 }
 async function refresh(){if(loading||busy||!visible())return;loading=true;try{render(await api())}catch(e){$('media-state').textContent='Mất kết nối';$('media-state').className='badge badge-warning';$('media-result').textContent=e.message}finally{loading=false}}
 async function command(payload){if(busy)return;busy=true;powerControls();const controls=$('media').querySelectorAll('button');controls.forEach(b=>b.disabled=true);try{render(await api(payload));$('media-result').textContent='Đã gửi thao tác · '+new Date().toLocaleTimeString('vi-VN')}catch(e){$('media-result').textContent=e.message;$('resource-mode-state').textContent=e.message}finally{busy=false;controls.forEach(b=>b.disabled=false);powerControls()}}
 document.querySelectorAll('[data-media-power]').forEach(b=>b.onclick=()=>command({action:'power',enabled:b.dataset.mediaPower==='on'}));
 $('media-start').onclick=()=>command({action:'start'});
 $('media-nonstop').onclick=()=>command({action:'nonstop',enabled:!nonstop});
 $('media-dislike').onclick=()=>command({action:'dislike'});
 $('media-sleep-cancel').onclick=()=>command({action:'sleep_cancel'});
 $('media-sleep-form').onsubmit=e=>{e.preventDefault();command({action:'sleep',minutes:Number($('media-sleep-minutes').value)})};
 $('media-repeat-form').onsubmit=e=>{e.preventDefault();command({action:'repeat',setting:{enabled:$('media-repeat-enabled').checked,hours:Number($('media-repeat-hours').value)}})};
 ['play','enqueue'].forEach(action=>$('media-'+action).onclick=()=>command({action,url:$('media-url').value.trim()}));
 document.querySelectorAll('[data-media]').forEach(b=>b.onclick=()=>command({action:b.dataset.media,...(b.dataset.value?{value:Number(b.dataset.value)}:{})}));
 $('media-volume').onchange=()=>command({action:'volume',value:Number($('media-volume').value)});
 $('media-limit-form').onsubmit=e=>{e.preventDefault();command({action:'volume_schedule',schedule:{enabled:$('media-limit-enabled').checked,start:$('media-limit-start').value,end:$('media-limit-end').value,limit:Number($('media-limit-value').value)}})};
 function schedule(){clearInterval(timer);if(visible()){refresh();timer=setInterval(refresh,$('media').classList.contains('active')?3000:10000)}}
 window.addEventListener('pi:view',schedule);document.addEventListener('visibilitychange',schedule);schedule();
})();
