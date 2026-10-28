const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const flush=()=>new Promise(r=>setImmediate(r));
function harness(file){
 const nodes=new Map(),listeners={},timers=new Map(),calls=[];let counter=0,data={output:{id:42,name:'bluez_output.test',label:'Speaker',volume:35,muted:false}};
 function node(id){if(nodes.has(id))return nodes.get(id);const events={},n={id,value:'',dataset:{},disabled:false,open:false,textContent:'',children:[],classList:{contains:x=>x==='active'},setAttribute(k,v){this[k]=v},addEventListener(k,f){events[k]=f},events,append(...args){this.children.push(...args)},replaceChildren(...args){this.children=args},focus(){},showModal(){this.open=true},close(){this.open=false;events.close?.()},getBoundingClientRect:()=>({left:0,right:340,top:0,bottom:200})};Object.defineProperty(n,'innerHTML',{set(){throw Error('unsafe HTML')}});nodes.set(id,n);return n}
 node('ops-csrf').value='test-csrf';
 const document={hidden:false,activeElement:null,getElementById:node,createElement:t=>node(t+counter++),addEventListener:(k,f)=>(listeners[k]??=[]).push(f)};
 const context={document,window:{addEventListener:document.addEventListener,PiMedia:{command:async p=>calls.push({play:p})}},AbortSignal,
 fetch:async(url,options)=>{calls.push({url,payload:JSON.parse(options.body),options});if(data instanceof Error)throw data;return {ok:true,json:async()=>({ok:true,data})}},
 setInterval:(f,ms)=>{let id=++counter;timers.set(id,{f,ms});return id},clearInterval:id=>timers.delete(id),
 setTimeout:(f,ms)=>{let id=++counter;timers.set(id,{f,ms});return id},clearTimeout:id=>timers.delete(id)};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/'+file),'utf8'),context);
 return {node,document,timers,calls,listeners,set:d=>data=d};
}
(async()=>{
 const a=harness('quick-audio.js');await flush();assert.equal(a.calls.length,0,'Closed speaker popover never polls');
 a.node('quick-audio-open').onclick();await flush();assert.equal(a.calls[0].payload.action,'output_status');assert.equal(a.timers.size,1);
 a.node('quick-audio-volume').value='45';a.node('quick-audio-volume').oninput();assert.equal(a.calls.length,1,'Dragging only updates the local label');
 await a.node('quick-audio-volume').onchange();assert.equal(a.calls.at(-1).payload.name,'bluez_output.test');assert.equal(a.calls.at(-1).payload.value,45);assert.equal(a.calls.at(-1).options.headers['X-CSRF-Token'],'test-csrf');
 a.node('quick-audio-close').onclick();assert.equal(a.timers.size,0);a.node('quick-audio-open').onclick();await flush();a.document.hidden=true;a.listeners.visibilitychange.forEach(f=>f());assert.equal(a.timers.size,0);
 const b=harness('media-library.js');assert.equal(b.calls.length,0,'Search has no startup request');
 b.node('catalog-provider').value='spotify';b.node('catalog-kind').value='tracks';b.node('catalog-query').value='music';b.set({running:true,rows:[],message:'Searching'});
 await b.node('catalog-form').onsubmit({preventDefault(){}});assert.equal(b.calls[0].payload.query,'music');assert.equal(b.timers.size,1);
 b.document.hidden=true;b.listeners.visibilitychange.forEach(f=>f());assert.equal(b.timers.size,0,'Hidden search stops polling');
 b.set({running:false,message:'Done',rows:[{provider:'spotify',title:'<img onerror=bad()>',subtitle:'Artist',url:'https://open.spotify.com/track/'+'A'.repeat(22)}]});b.document.hidden=false;b.listeners.visibilitychange.forEach(f=>f());await flush();assert.equal(b.timers.size,0,'Completed search stops polling');
 const row=b.node('catalog-results').children[0];assert.equal(row.children[0].children[0].textContent,'<img onerror=bad()>');await row.children[1].children[0].onclick();assert.equal(b.calls.at(-1).play.action,'catalog_play');
 b.set({running:true,rows:[],message:'Searching'});await b.node('catalog-form').onsubmit({preventDefault(){}});assert.equal(b.calls.at(-1).payload.kind,'tracks');
 b.set(Error('offline'));await [...b.timers.values()].at(-1).f();await flush();assert.equal(b.node('catalog-submit').disabled,false,'Poll errors must unlock retry');
 console.log('Quick speaker and media search: explicit requests, CSRF, safe text, default identity, drag commits and visible-only lifecycle PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
