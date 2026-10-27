/* Shared help and action feedback. No API calls, observers, or polling. */
(()=>{'use strict';
 const $=id=>document.getElementById(id),drawer=$('ui-help'),timers=new Map();let returnFocus=null;
 function clear(id){clearTimeout(timers.get(id));timers.delete(id);const node=$(id);if(node){node.replaceChildren();node.hidden=true;delete node.dataset.message;}}
 function feedback(id,text,kind='info'){
  const node=$(id);if(!node)return;if(!text){clear(id);return;}
  if(node.dataset.message===text&&node.dataset.tone===kind&&!node.hidden)return;
  clearTimeout(timers.get(id));node.dataset.message=text;node.dataset.tone=kind;
  node.classList.add('ui-feedback');node.hidden=false;node.setAttribute('role',kind==='error'?'alert':'status');
  const content=document.createElement('span');content.textContent=text;
  const close=document.createElement('button');close.type='button';close.className='ui-feedback-dismiss';close.textContent='×';close.setAttribute('aria-label','Đóng thông báo');close.onclick=()=>clear(id);
  node.replaceChildren(content,close);
  if(kind==='success')timers.set(id,setTimeout(()=>clear(id),5000));
 }
 window.PiUI={feedback,clear};
 $('ui-skip')?.addEventListener('click',event=>{event.preventDefault();$('main-content').focus({preventScroll:true});$('main-content').scrollIntoView({block:'start'});});
 document.querySelectorAll('[data-flash]').forEach(node=>feedback(node.id,node.textContent.trim(),node.dataset.tone));
 if(!drawer)return;
 document.querySelectorAll('[data-help-page]').forEach(button=>button.addEventListener('click',()=>{
  returnFocus=button;const page=button.dataset.helpPage;
  drawer.querySelectorAll('[data-help-topic]').forEach(topic=>topic.hidden=topic.dataset.helpTopic!==page);
  const title=document.getElementById(page)?.querySelector('.page-title')?.textContent||'Pi Control';
  $('ui-help-title').textContent=title;drawer.showModal();drawer.querySelector('.help-drawer-body').scrollTop=0;
 }));
 $('ui-help-close').onclick=()=>drawer.close();
 drawer.addEventListener('close',()=>{if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});returnFocus=null;});
 window.addEventListener('pi:view',()=>{if(drawer.open)drawer.close();});
 window.addEventListener('pagehide',()=>{[...timers.keys()].forEach(clear);if(drawer.open)drawer.close();});
})();
