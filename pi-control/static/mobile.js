/* Mobile composition only. Existing controllers own all APIs and playback. */
(()=>{'use strict';
 const $=id=>document.getElementById(id),menu=$('mobile-menu'),open=$('mobile-menu-open');
 if(!menu||!open)return;
 const screen=matchMedia('(max-width: 760px)'),saved=[],positions=new Map();let current='',active=false;
 function move(node,parent,before=null){if(!node||!parent)return;const marker=document.createComment('mobile-origin');node.before(marker);saved.push({node,marker});parent.insertBefore(node,before);}
 function restore(){for(const {node,marker} of saved.reverse()){marker.replaceWith(node);}saved.length=0;}
 function close(){if(menu.open)menu.close();open.setAttribute('aria-expanded','false');}
 function keyboard(){
  const tag=document.activeElement?.tagName,type=document.activeElement?.type;
  const editing=(tag==='INPUT'&&!['checkbox','radio','range','button','submit'].includes(type))||tag==='TEXTAREA';
  document.body.classList.toggle('mobile-keyboard',active&&editing&&!!window.visualViewport&&window.innerHeight-window.visualViewport.height>150);
 }
 function view(id,scroll=true){
  if(!active)return;
  if(scroll&&current&&current!==id)positions.set(current,window.scrollY);
  const secondary=!['overview','media','camera','network'].includes(id);
  open.classList.toggle('active',secondary);open.setAttribute('aria-label',secondary?'Các mục khác · '+($(id)?.querySelector('.page-title')?.textContent||id):'Mở các mục khác');
  if(secondary)open.setAttribute('aria-current','page');else open.removeAttribute('aria-current');
  close();if(scroll&&current&&current!==id)window.scrollTo({top:positions.get(id)||0,behavior:'instant'});current=id;
 }
 function compose(){
  active=screen.matches;close();
  if(active){
   const media=$('media'),catalog=$('catalog-form')?.closest('.media-catalog');
   move(media?.querySelector('.media-player'),media,catalog);
   move($('quick-audio-open'),$('mobile-header-actions'));
   view(document.querySelector('.view-section.active')?.id||'overview',false);
  }else{restore();document.body.classList.remove('mobile-keyboard');current='';}
  keyboard();
 }
 open.addEventListener('click',()=>{if(!active)return;menu.showModal();open.setAttribute('aria-expanded','true');});
 $('mobile-menu-close').addEventListener('click',close);
 menu.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}});
 menu.addEventListener('close',()=>{open.setAttribute('aria-expanded','false');});
 menu.addEventListener('click',event=>{if(event.target===menu){const r=menu.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}});
 screen.addEventListener('change',compose);
 window.addEventListener('pi:view',event=>view(event.detail));
 window.visualViewport?.addEventListener('resize',keyboard);
 document.addEventListener('focusin',keyboard);document.addEventListener('focusout',keyboard);
 window.addEventListener('pagehide',close);
 compose();
})();
