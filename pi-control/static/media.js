(()=>{'use strict';
 const $=id=>document.getElementById(id);if(!$('media'))return;
 function feedback(text,tone='info'){if(window.PiUI)window.PiUI.feedback('media-result',text,tone);else $('media-result').textContent=text;}
 let busy=false,timer,loading=false,nonstop=false,settingsLoaded=false,repeatLoaded=false,lastWarning=false;
 const visible=()=>!document.hidden&&($('media').classList.contains('active')||$('overview').classList.contains('active'));
 let standby=false,connected=false,provider='youtube',spotifyState={};
 let revision=0,shortcutStamp='',receiptStamp='',lastReceipt=null;
 function powerControls(){
  $('media-nonstop').disabled=busy||provider==='spotify';
  document.querySelectorAll('[data-media-power]').forEach(b=>b.disabled=busy||(b.dataset.mediaPower==='off'?standby:!standby&&connected));
  $('media-start').disabled=busy;
  document.querySelectorAll('[data-media],#media-play,#media-dislike,#media-volume').forEach(b=>{if(!b.matches('[data-media="clear"],[data-media="remove"]'))b.disabled=busy||(standby&&b.id!=='media-play')});
  document.querySelectorAll('[data-media-source]').forEach(b=>{b.disabled=busy||standby;b.setAttribute('aria-pressed',String(b.dataset.mediaSource===provider))});
  $('media-spotify-login').disabled=busy||standby;$('media-spotify-filter').disabled=busy;
  const reload=$('media-spotify-reload');
  reload.hidden=provider!=='spotify'||standby||!connected||spotifyState.login_required||
   !(spotifyState.ad||spotifyState.notice||spotifyState.error||spotifyState.spotify_ad_recovery?.message)||spotifyState.content_unavailable;
  reload.disabled=busy||spotifyState.launch_pending||spotifyState.manual_pause||spotifyState.preferences?.sleep?.expired||spotifyState.bluetooth_guard?.paused;
  if(provider==='spotify'){
   document.querySelectorAll('[data-media="seek"]').forEach(b=>b.disabled=busy||standby||!spotifyState.can_seek);
   document.querySelectorAll('[data-media="next"]').forEach(b=>b.disabled=busy||standby||!spotifyState.can_next);
   $('media-toggle').disabled=busy||standby||!spotifyState.can_toggle;
   $('media-volume').disabled=busy||standby||spotifyState.can_volume===false||!spotifyState.has_video;
  }
  document.querySelectorAll('[data-shortcut-play],[data-shortcut-remove],#media-shortcut-save,#media-bt-guard').forEach(b=>b.disabled=busy);
 }
 function shortcuts(items){
  const rows=Array.isArray(items)?items:[],stamp=JSON.stringify(rows);if(stamp===shortcutStamp)return;shortcutStamp=stamp;
  $('media-shortcut-count').textContent=rows.length+'/24';$('media-shortcut-empty').hidden=rows.length>0;$('media-shortcuts').replaceChildren();
  for(const item of rows){
   const li=document.createElement('li'),play=document.createElement('button'),label=document.createElement('span'),source=document.createElement('span'),remove=document.createElement('button');
   li.className='media-shortcut-row';play.type='button';play.className='btn btn-outline media-shortcut-play';play.dataset.shortcutPlay=item.id;label.className='media-shortcut-label';label.textContent=item.label;source.className='media-shortcut-provider';source.textContent=item.provider==='spotify'?'Spotify':'YouTube';play.append(label,source);play.onclick=()=>command({action:'shortcut_play',id:item.id});
   remove.type='button';remove.className='btn btn-outline media-shortcut-remove';remove.dataset.shortcutRemove=item.id;remove.textContent='×';remove.setAttribute('aria-label','Bỏ ghim '+item.label);remove.onclick=()=>command({action:'shortcut_remove',id:item.id});li.append(play,remove);$('media-shortcuts').append(li);
  }
 }
 const clock=n=>{n=Math.max(0,Math.floor(n||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0')};
 async function api(payload){
  const r=await fetch('/api/media',{cache:'no-store',signal:AbortSignal.timeout(14000),...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':$('ops-csrf').value},body:JSON.stringify(payload)}:{})});
  if(r.redirected){location.href='/login';throw Error('Cần đăng nhập lại')}
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Media chưa sẵn sàng');return d.data;
 }
 function render(d){
  provider=d.provider==='spotify'?'spotify':'youtube';spotifyState=d;
  if($('media-quality')&&document.activeElement!==$('media-quality'))$('media-quality').value=d.youtube_quality||'240';
  if($('media-quality-note'))$('media-quality-note').textContent=d.video_height?'Đang giải mã '+d.video_height+'p · YouTube có thể tự điều chỉnh.':'Ưu tiên độ phân giải thấp khi nghe nhạc.';
  $('media').dataset.provider=provider;
  standby=!!d.standby;connected=!!d.connected;powerControls();
  shortcuts(d.shortcuts);powerControls();
  const guard=d.bluetooth_guard;
  if(guard){$('media-bt-guard').checked=!!guard.enabled;$('media-bt-guard-state').textContent=guard.message||(guard.enabled&&guard.watching?'Đang theo dõi loa Bluetooth đang dùng.':'');$('media-bt-guard-state').dataset.held=String(!!guard.paused)}
  $('media-shortcut-note').textContent=d.shortcut_error||'Dùng nguồn và link ở phía trên.';
  document.querySelectorAll('[data-youtube-only]').forEach(n=>n.hidden=provider==='spotify');
  $('media-spotify-account').hidden=provider!=='spotify';
  $('media-spotify-account-state').textContent=d.login_required?'Chờ đăng nhập trên Pi':d.has_video?'Đã nhận bộ phát':'Spotify Free · đăng nhập khi cần';
  $('media-spotify-filter').checked=d.spotify_ad_filter!==false;
  $('media-url-label').textContent='Link YouTube / Spotify · tự nhận nguồn';
  $('media-url').placeholder=provider==='spotify'?'https://open.spotify.com/playlist/…':'https://www.youtube.com/watch?v=…';
  $('media-search').href=provider==='spotify'?'https://open.spotify.com/':'https://www.youtube.com/';
  $('media-search').textContent=provider==='spotify'?'Tìm trên Spotify ↗':'Tìm video trên YouTube ↗';
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
  nonstop=!!(d.youtube_nonstop??d.nonstop);
  $('media-nonstop').textContent=nonstop?'Nonstop YouTube · Bật':'Bật Nonstop YouTube';
  $('media-nonstop').setAttribute('aria-pressed',String(nonstop));
  let nonstopNote='';
  if(provider==='spotify')nonstopNote='Chọn YouTube để dùng Nonstop.';
  else if(nonstop){
   if(standby)nonstopNote='Nonstop chờ bạn bật Media.';
   else if(guard?.paused)nonstopNote='Loa Bluetooth đã ngắt. Chọn đầu ra rồi bấm Phát.';
   else if(prefs?.sleep?.expired)nonstopNote='Đã hết hẹn giờ. Bấm Phát để nghe tiếp.';
   else if(d.manual_pause)nonstopNote='Đang chờ bạn bấm Phát.';
   else if(!['Đang theo dõi','Đã tắt','Đang giữ Autoplay và tiếp tục phát'].includes(d.nonstop_note))nonstopNote=d.nonstop_note||'';
  }
  $('media-nonstop-note').textContent=nonstopNote;
  $('media-title').textContent=(d.title||'Chưa có nội dung')+(provider==='spotify'&&d.artist?' · '+d.artist:'');
  $('media-state').textContent=(standby?'Đang nghỉ':!d.connected?'Chưa kết nối':d.login_required?'Chờ đăng nhập':d.ad?(d.ad_muted?'Đã tắt tiếng quảng cáo':'Đang quảng cáo'):!d.has_video?'Chọn nội dung để bắt đầu':d.paused?'Đã tạm dừng':'Đang phát')+(d.autoplay?' · Tự phát':'');
  $('media-state').className='badge '+(d.connected?'badge-success':'badge-warning');
  const phase={opening:'Đang mở Chromium…',loading:'Đang tải nội dung…',confirming:'Đang xác nhận phát…'}[d.playback_phase];
  if(phase||d.launch_pending){
   $('media-state').textContent=phase||'Đang tải nội dung…';
   $('media-state').className='badge badge-warning';
  }
  if(d.content_unavailable){$('media-state').textContent='Nội dung không khả dụng';$('media-state').className='badge badge-warning'}
  if(provider==='spotify'&&d.has_video&&!d.paused&&d.playback_observed===false){$('media-state').textContent='Player báo đang phát · chưa xác minh âm thanh';$('media-state').className='badge badge-warning'}
  if(guard?.paused){$('media-state').textContent='Tạm dừng · kiểm tra loa';$('media-state').className='badge badge-warning'}
  $('media-toggle').textContent=d.has_video&&d.paused===false?'Ⅱ Tạm dừng':'▶ Phát';
  $('media-progress').max=d.duration||1;$('media-progress').value=d.position||0;
  $('media-time').textContent=clock(d.position)+' / '+(d.duration?clock(d.duration):'Trực tiếp / chưa rõ');
  $('media-progress').hidden=provider==='spotify'&&d.position_known===false;
  if(provider==='spotify'&&d.position_known===false)$('media-time').textContent='Chưa đọc được tiến độ từ Spotify';
  if(document.activeElement!==$('media-volume'))$('media-volume').value=d.volume??50;
  $('media-volume-value').textContent=(d.volume??0)+'%';
  if(provider==='spotify'&&d.can_volume===false)$('media-volume-value').textContent='—';
  const policy=d.volume_schedule;
  if(policy){
   $('media-limit-note').textContent=policy.active?'Đang giới hạn tối đa '+policy.limit+'% · '+policy.start+'–'+policy.end+' (giờ Việt Nam)':policy.enabled?'Lịch giới hạn '+policy.start+'–'+policy.end+' · tối đa '+policy.limit+'% (giờ Việt Nam)':'';
   if(!settingsLoaded){$('media-limit-enabled').checked=policy.enabled;$('media-limit-start').value=policy.start;$('media-limit-end').value=policy.end;$('media-limit-value').value=policy.limit;settingsLoaded=true}
  }
  const upcoming=d.up_next,validNext=upcoming&&/^https:\/\/www\.youtube\.com\/watch\?v=[\w-]{11}$/.test(upcoming.url||'');
  $('media-next-link').hidden=!validNext;$('media-next-empty').hidden=!!validNext;$('media-next-empty').textContent='Chưa có đề xuất phù hợp sau khi lọc bài đã nghe và bài không thích.';
  $('media-next-source').textContent=validNext?upcoming.source:'';
  if(validNext){$('media-next-link').href=upcoming.url;$('media-next-link').textContent=upcoming.title||'Bài tiếp theo'}
  const match=(d.url||'').match(/^https:\/\/www\.youtube\.com\/watch\?v=([\w-]{11})$/);
  $('media-art').hidden=!match;$('media-art-empty').hidden=!!match;$('media-video-link').hidden=!match;
  if(match){const src='https://i.ytimg.com/vi/'+match[1]+'/hqdefault.jpg';if($('media-art').src!==src)$('media-art').src=src;$('media-video-link').href=d.url}
  if(provider==='spotify'){
   const safeArt=typeof d.artwork==='string'&&/^https:\/\/i\.scdn\.co\/image\/[a-f0-9]+$/i.test(d.artwork);
   $('media-art').hidden=!safeArt;$('media-art-empty').hidden=!!safeArt;if(safeArt)$('media-art').src=d.artwork;
   const safeLink=/^https:\/\/open\.spotify\.com\/(?:track|album|playlist|artist|episode|show)\/[A-Za-z0-9]{22}$/.test(d.url||'');
   $('media-video-link').hidden=!safeLink;if(safeLink)$('media-video-link').href=d.url;
   $('media-video-link').textContent='Mở trên Spotify ↗';
  }else $('media-video-link').textContent='Mở video này trên điện thoại ↗';
  $('media-count').textContent=(d.queue||[]).length;$('media-queue').replaceChildren();
  (d.queue||[]).forEach((url,index)=>{const li=document.createElement('li'),a=document.createElement('a'),b=document.createElement('button');a.textContent='Video '+(index+1)+' · '+url.split('v=')[1];a.href=url;a.target='_blank';a.rel='noopener';b.textContent='Bỏ';b.className='btn btn-outline';b.onclick=()=>command({action:'remove',index});li.append(a,b);$('media-queue').append(li)});
  if(!(d.queue||[]).length){const li=document.createElement('li');li.textContent='Chưa có video trong hàng đợi.';$('media-queue').append(li)}
  const receipt=d.command;lastReceipt=receipt;
  if(d.recovery_requested){feedback('Đã yêu cầu tải lại Spotify. Chờ trình phát phản hồi.');lastWarning=true}
  else if(d.error||d.notice||d.spotify_ad_recovery?.message){feedback(d.error||d.notice||d.spotify_ad_recovery.message,d.error||d.content_unavailable?'error':'info');lastWarning=true}
  else if(receipt){const stamp=receipt.id+':'+receipt.state;if(stamp!==receiptStamp){receiptStamp=stamp;feedback(receipt.message,receipt.state==='confirmed'?'success':receipt.state==='unconfirmed'?'error':'info')}lastWarning=false}
  else if(lastWarning){feedback('');lastWarning=false}
 }
 async function refresh(){if(loading||busy||!visible())return;loading=true;const version=revision;try{const d=await api();if(version===revision&&!busy&&visible()){render(d);window.dispatchEvent(new CustomEvent('pi:media-state'))}}catch(e){if(version===revision&&!busy){$('media-state').textContent='Mất kết nối';$('media-state').className='badge badge-warning';feedback(e.message,'error')}}finally{loading=false}}
 async function command(payload){if(busy){feedback('Đang xử lý thao tác trước; chờ một chút rồi thử lại.');return null}busy=true;revision++;powerControls();const controls=[...$('media').querySelectorAll('button')].filter(b=>!b.closest?.('.media-catalog,.media-native'));controls.forEach(b=>b.disabled=true);feedback('Đang gửi yêu cầu…');try{const result=await api(payload);render(result);if(!result.error&&!result.notice&&!result.command&&!result.recovery_requested)feedback('Đã nhận yêu cầu; đang chờ trạng thái player.');return result}catch(e){if(lastReceipt)receiptStamp=lastReceipt.id+':'+lastReceipt.state;feedback(e.message,'error');$('resource-mode-state').textContent=e.message;return null}finally{busy=false;controls.forEach(b=>b.disabled=false);powerControls()}}
 document.querySelectorAll('[data-media-power]').forEach(b=>b.onclick=()=>command({action:'power',enabled:b.dataset.mediaPower==='on'}));
 $('media-start').onclick=()=>command({action:'start'});
 document.querySelectorAll('[data-media-source]').forEach(b=>b.onclick=()=>command({action:'source',provider:b.dataset.mediaSource}));
 $('media-spotify-login').onclick=()=>command({action:'spotify_login'});
 $('media-spotify-reload').onclick=()=>command({action:'spotify_reload'});
 $('media-spotify-filter').onchange=()=>command({action:'spotify_filter',enabled:$('media-spotify-filter').checked});
 $('media-bt-guard').onchange=()=>command({action:'bluetooth_guard',enabled:$('media-bt-guard').checked});
 if($('media-quality'))$('media-quality').onchange=()=>command({action:'youtube_quality',value:$('media-quality').value});
 window.PiMedia={command};
 $('media-shortcut-form').onsubmit=async e=>{e.preventDefault();const result=await command({action:'shortcut_save',provider,url:$('media-url').value.trim(),label:$('media-shortcut-label').value.trim()});if(result)$('media-shortcut-label').value=''};
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
