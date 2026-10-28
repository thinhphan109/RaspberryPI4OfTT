(()=>{'use strict';
 let invoker=null,opened=null;
 const close=()=>{if(opened?.open)opened.close()};
 document.querySelectorAll('[data-service-help]').forEach(button=>button.addEventListener('click',()=>{
  const id=button.dataset.serviceHelp;if(!/^[a-z-]+$/.test(id))return;
  const dialog=document.getElementById('service-help-'+id);if(!dialog)return;
  close();invoker=button;opened=dialog;dialog.showModal();
 }));
 document.querySelectorAll('.service-help-dialog').forEach(dialog=>{
  dialog.querySelector('[data-service-close]')?.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{if(opened===dialog){opened=null;invoker?.focus();invoker=null}});
 });
 window.addEventListener('pi:view',close);window.addEventListener('pagehide',close);
})();
