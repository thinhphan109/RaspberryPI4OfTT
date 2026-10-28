const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync('pi-control/static/service-help.js','utf8');
const handlers={},listeners={},buttons={},dialogs={};
for(const id of ['dashboard','camera']){
 const events={};const close={addEventListener:(type,fn)=>events[type]=fn};
 buttons[id]={dataset:{serviceHelp:id},addEventListener:(type,fn)=>handlers[id]=fn,focus:()=>buttons[id].focused=true};
 dialogs['service-help-'+id]={open:false,showModal(){this.open=true},close(){this.open=false;this.events.close()},events:{},addEventListener(type,fn){this.events[type]=fn},querySelector:()=>close,closeButton:events};
}
const context={document:{querySelectorAll:selector=>selector==='[data-service-help]'?Object.values(buttons):Object.values(dialogs),getElementById:id=>dialogs[id]},window:{addEventListener:(type,fn)=>listeners[type]=fn},fetch:()=>assert.fail('Help must not fetch'),setInterval:()=>assert.fail('Help must not poll')};
vm.runInNewContext(code,context);
handlers.dashboard();assert(dialogs['service-help-dashboard'].open);
handlers.camera();assert(!dialogs['service-help-dashboard'].open);assert(dialogs['service-help-camera'].open);
dialogs['service-help-camera'].closeButton.click();assert(buttons.camera.focused);
handlers.dashboard();listeners['pi:view']();assert(!dialogs['service-help-dashboard'].open);
handlers.camera();listeners.pagehide();assert(!dialogs['service-help-camera'].open);
buttons.camera.dataset.serviceHelp='../unsafe';handlers.camera();assert(!dialogs['service-help-camera'].open);
console.log('Per-service Help modal, focus return, navigation cleanup and no polling PASS');
