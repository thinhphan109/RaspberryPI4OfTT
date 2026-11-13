const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../static/media.js'),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(initial,deferFirst=false){
 const nodes=new Map(),timers=new Map(),listeners={},calls=[],feedback=[];let seq=0,payload=initial,release;
 const deferred=new Promise(resolve=>{release=resolve});
 function node(id){if(nodes.has(id))return nodes.get(id);const n={id,value:'',textContent:'',dataset:{},hidden:false,disabled:false,children:[],classList:{contains:v=>v==='active'&&id==='media'},setAttribute(k,v){this[k]=v},matches:()=>false,querySelectorAll:()=>[],append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children}};Object.defineProperty(n,'innerHTML',{set(){throw Error('Unsafe HTML insertion')}});nodes.set(id,n);return n;}
 const sources=['youtube','spotify'].map(provider=>Object.assign(node(provider),{dataset:{mediaSource:provider}}));
 const controls=['toggle','next'].map(action=>Object.assign(node('media-'+action),{dataset:{media:action}}));
 const document={hidden:false,activeElement:null,getElementById:node,createElement:t=>node(t+seq++),addEventListener:(k,f)=>(listeners[k]??=[]).push(f),querySelectorAll:s=>s==='[data-media-source]'?sources:s==='[data-media]'?controls:[]};
 node('ops-csrf').value='csrf-extras';
 const context={CustomEvent:class{constructor(type){this.type=type}},document,window:{dispatchEvent:()=>{},addEventListener:document.addEventListener,PiUI:{feedback:(id,text,tone)=>feedback.push({text,tone})}},location:{},AbortSignal,
  setInterval:(f,ms)=>{const id=++seq;timers.set(id,{f,ms});return id},clearInterval:id=>timers.delete(id),
  fetch:async(url,options)=>{calls.push({url,options});const data=deferFirst&&calls.length===1?await deferred:payload;return {ok:true,redirected:false,json:async()=>({ok:true,data})}}};
 vm.runInNewContext(script,context);
 return {node,sources,timers,calls,feedback,set:value=>payload=value,release,document,listeners};
}
(async()=>{
 const state={provider:'spotify',connected:true,has_video:true,paused:false,can_toggle:true,can_volume:false,position_known:false,queue:[]};
 const h=harness(state);await flush();
 assert.equal(h.node('media-volume').disabled,true);assert.equal(h.node('media-volume-value').textContent,'—');assert.equal(h.node('media-progress').hidden,true);
 h.set({...state,command:{id:'one',state:'pending',message:'Checking'}});
 await h.node('media-toggle').onclick();
 assert.equal(h.feedback.at(-1).tone,'info','Sending a click is not a confirmed result');
 h.set({...state,paused:true,command:{id:'one',state:'confirmed',message:'Paused'}});
 await [...h.timers.values()][0].f();await flush();
 assert.equal(h.feedback.at(-1).tone,'success');assert.equal(h.node('media-toggle').textContent,'▶ Phát');
 h.set({...state,command:{id:'two',state:'unconfirmed',message:'Not confirmed'}});
 await [...h.timers.values()][0].f();await flush();assert.equal(h.feedback.at(-1).tone,'error');
 const label='<img src=x onerror=bad()>',item={id:'a'.repeat(16),provider:'spotify',url:'https://open.spotify.com/playlist/1234567890ABCDEFGHIJKL',label};
 h.node('media-url').value=item.url;h.node('media-shortcut-label').value=label;
 h.set({...state,shortcuts:[item],command:{id:'saved',state:'confirmed',message:'Saved'}});
 await h.node('media-shortcut-form').onsubmit({preventDefault(){}});
 const request=JSON.parse(h.calls.at(-1).options.body);assert.equal(request.action,'shortcut_save');assert.equal(request.label,label);assert.equal(request.provider,'spotify');assert.equal(h.calls.at(-1).options.headers['X-CSRF-Token'],'csrf-extras');
 const row=h.node('media-shortcuts').children[0];assert.equal(row.children[0].children[0].textContent,label);assert.equal(row.children[1]['aria-label'],'Bỏ ghim '+label);
 await row.children[0].onclick();assert.deepEqual(JSON.parse(h.calls.at(-1).options.body),{action:'shortcut_play',id:item.id});
 assert.equal(h.timers.size,1,'Extras do not add browser pollers');
 h.document.hidden=true;(h.listeners.visibilitychange||[]).forEach(f=>f());assert.equal(h.timers.size,0);
 const race=harness({provider:'youtube',title:'Old',queue:[]},true);
 race.set({...state,title:'New'});await race.sources[1].onclick();
 race.release({provider:'youtube',title:'Old',queue:[]});await flush();
 assert.equal(race.node('media-title').textContent,'New','An old status GET must not overwrite a newer command');
 assert.equal(race.sources[1]['aria-pressed'],'true');
 // Run the exact safety scripts: preserve pre-existing mute and block future play.
 const py=fs.readFileSync(path.join(__dirname,'../media_agent.py'),'utf8');
 const hold=py.match(/SAFETY_MUTE_JS="""([\s\S]*?)"""/)[1],restore=py.match(/SAFETY_RELEASE_JS="""([\s\S]*?)"""/)[1];
 class Media {constructor(muted=false){this.muted=muted;this.paused=false}pause(){this.paused=true}}
 const a=new Media(),b=new Media(true),events={},ctx={HTMLMediaElement:Media,window:{},document:{querySelectorAll:()=>[a,b],addEventListener:(k,f)=>events[k]=f}};
 vm.runInNewContext(hold,ctx);vm.runInNewContext(hold,ctx);assert(a.muted&&a.paused&&b.muted&&b.paused);
 a.paused=false;events.play({target:a});assert(a.paused,'Autoplay cannot bypass Bluetooth hold');
 vm.runInNewContext(restore,ctx);assert.equal(a.muted,false);assert.equal(b.muted,true,'Preserve manual mute');
 a.paused=false;events.play({target:a});assert.equal(a.paused,false,'Explicit release permits later play');
 console.log('Media extras: observed feedback, safe shortcut DOM/CSRF, stale GET guard, no extra polling and exact Bluetooth hold scripts PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
