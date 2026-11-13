const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const flush=()=>new Promise(r=>setImmediate(r));
function harness(){
 const nodes=new Map(),listeners={},calls=[];let count=0,next,deferred;
 const state={title:'<img onerror=bad()>',artist:'Artist',playback:'Paused',volume:20,can_play:true,can_pause:true,can_next:false,can_previous:false,can_seek:true,can_volume:true};
 function node(id){if(nodes.has(id))return nodes.get(id);const n={id,value:'',textContent:'',disabled:false,hidden:false,dataset:{},children:[],classList:{contains:()=>true},append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children}};Object.defineProperty(n,'innerHTML',{set(){throw Error('Unsafe HTML')}});nodes.set(id,n);return n}
 const buttons=['play','pause','next','previous','seek'].map(action=>Object.assign(node(action),{dataset:{native:action,...(action==='seek'?{value:'10'}:{})}}));
 node('ops-csrf').value='native-csrf';
 const document={hidden:false,activeElement:null,getElementById:node,createElement:()=>node('new'+count++),querySelectorAll:()=>buttons,addEventListener:(k,f)=>(listeners[k]??=[]).push(f)};
 const context={document,window:{addEventListener:document.addEventListener},AbortSignal,fetch:async(url,options)=>{
  const payload=JSON.parse(options.body);calls.push({url,options,payload});let data;
  if(deferred){const wait=deferred;deferred=null;data=await wait}else if(next instanceof Error){const error=next;next=null;throw error}else {data=next||(payload.action==='apps'?{players:[{id:'org.mpris.MediaPlayer2.vlc',owner:':1.123',label:'VLC'}]}:state);next=null}
  return {ok:true,json:async()=>({ok:true,data})};
 }};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/native-player.js'),'utf8'),context);
 return {node,buttons,calls,listeners,document,state,set:x=>next=x,defer(){let release;deferred=new Promise(r=>release=r);return release},event(k){for(const f of listeners[k]||[])f()}};
}
(async()=>{
 const h=harness();await flush();assert.equal(h.calls.length,0,'No startup scan or timer');h.event('pi:media-state');await flush();assert.equal(h.calls.length,0,'No reads until explicit scan');
 await h.node('native-scan').onclick();assert.equal(h.calls.length,2);assert.equal(h.node('native-track-title').textContent,'<img onerror=bad()>');assert.equal(h.buttons[2].disabled,true);
 assert.equal(h.calls[1].payload.owner,':1.123');assert.equal(h.calls[1].options.headers['X-CSRF-Token'],'native-csrf');
 h.node('native-volume').value='35';h.node('native-volume').oninput();assert.equal(h.calls.length,2,'Dragging does not write');
 h.set({...h.state,volume:35,receipt:{message:'Confirmed'}});await h.node('native-volume').onchange();assert.equal(h.calls.at(-1).payload.command,'volume');assert.equal(h.calls.at(-1).payload.value,35);
 h.document.hidden=true;h.event('visibilitychange');h.event('pi:media-state');await flush();assert.equal(h.calls.length,3,'Hidden tab never reads');
 h.document.hidden=false;h.event('visibilitychange');await flush();
 const release=h.defer();h.event('pi:media-state');await flush();h.set({...h.state,playback:'Playing',receipt:{message:'Confirmed'}});await h.buttons[0].onclick();release({...h.state,title:'stale'});await flush();assert.notEqual(h.node('native-track-title').textContent,'stale','Old status cannot replace command result');
 h.set(Error('App restarted; rescan'));h.event('pi:media-state');await flush();assert(h.buttons.every(b=>b.disabled));const before=h.calls.length;h.event('pi:media-state');await flush();assert.equal(h.calls.length,before,'Owner failure clears selected app, preventing retry loop');
 console.log('Native app UI: explicit scan, no idle reads/timers, capabilities, unique owner, CSRF, safe text, commit-on-change, visibility and stale response protection PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
