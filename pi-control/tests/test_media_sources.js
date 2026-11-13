const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),listeners={},timers=new Map();let sequence=0,calls=[],payload={provider:'youtube',connected:true,has_video:true,paused:false,volume:30,queue:[]};
function node(id){if(nodes.has(id))return nodes.get(id);const n={id,value:'',textContent:'',dataset:{},hidden:false,disabled:false,children:[],classList:{contains:v=>v==='active'&&id==='media'},setAttribute(k,v){this[k]=v},matches:()=>false,querySelectorAll:()=>[],append(...n){this.children.push(...n)},replaceChildren(...n){this.children=n}};nodes.set(id,n);return n;}
const sources=['youtube','spotify'].map(p=>Object.assign(node(p),{dataset:{mediaSource:p}}));
const ytOnly=[node('queue-panel'),node('repeat-panel')];
const document={hidden:false,activeElement:null,getElementById:node,createElement:t=>node(t+sequence++),addEventListener:(k,v)=>(listeners[k]??=[]).push(v),querySelectorAll:s=>s==='[data-media-source]'?sources:s==='[data-youtube-only]'?ytOnly:[]};
node('ops-csrf').value='csrf-source-test';
const context={CustomEvent:class{constructor(type){this.type=type}},document,window:{dispatchEvent:()=>{},addEventListener:document.addEventListener},location:{},AbortSignal,
setInterval:(f,ms)=>{const id=++sequence;timers.set(id,{f,ms});return id},clearInterval:id=>timers.delete(id),
fetch:async(path,options)=>{calls.push({path,options});if(options.method){const command=JSON.parse(options.body);if(command.action==='source')payload={provider:'spotify',connected:true,login_required:true,queue:[],spotify_ad_filter:true};}return {ok:true,redirected:false,json:async()=>({ok:true,data:payload})}}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/media.js'),'utf8'),context);
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await flush();assert.equal(timers.size,1);
 await sources[1].onclick();assert.equal(sources[1]['aria-pressed'],'true');assert(ytOnly.every(n=>n.hidden));
 assert.equal(node('media-toggle').disabled,true);assert.equal(node('media-spotify-account').hidden,false);
 const command=JSON.parse(calls.at(-1).options.body);assert.equal(command.provider,'spotify');assert.equal(calls.at(-1).options.headers['X-CSRF-Token'],'csrf-source-test');
 await node('media-spotify-login').onclick();assert.deepEqual(JSON.parse(calls.at(-1).options.body),{action:'spotify_login'});
 assert.equal(timers.size,1,'Source changes do not add pollers');
 document.hidden=true;(listeners.visibilitychange||[]).forEach(f=>f());assert.equal(timers.size,0);
 console.log('Media source UI: Spotify selection, login action, capability controls, CSRF and unchanged polling PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
