// Exercise real Activity UI: safe text, filters, details and unchanged polling.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),listeners={},timers=new Map();let next=0,calls=[];
function element(id){if(nodes.has(id))return nodes.get(id);const node={id,dataset:{},value:'',hidden:false,open:false,children:[],handlers:{},style:{},textContent:'',classList:{contains:()=>id==='activity',toggle(){}},addEventListener(n,f){(this.handlers[n]??=[]).push(f)},append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children}};nodes.set(id,node);return node;}
const document={hidden:false,getElementById:element,createElement:()=>element('new-'+next++),addEventListener:(n,f)=>(listeners[n]??=[]).push(f)};
const window={addEventListener:document.addEventListener};
element('initial-operation').textContent='null';
element('initial-metrics').textContent=JSON.stringify({temperature:40,power:{},disks:[],network:[],processes:[],diagnostics:{layers:[]}});
const rows=[{id:'a',timestamp:10,kind:'storage',level:'error',message:'Ổ lưu cần kiểm tra',detail:'<img src=x onerror=evil()> token=[ẩn]',origin:'journal',count:5,first_timestamp:1},
 {id:'b',timestamp:9,kind:'camera',level:'info',message:'Ghép video hoàn tất',count:1,origin:'observed'},
 {id:'c',timestamp:8,kind:'usb',level:'warning',message:'Thiết bị USB mất kết nối',count:1}];
const context={document,window,location:{},AbortSignal,console,performance,setTimeout,clearTimeout,
 PiCharts:{observe(){},frame(){},draw(){},inspect(){}},
 setInterval:(fn,ms)=>{const id=++next;timers.set(id,{fn,ms});return id},clearInterval:id=>timers.delete(id),
 fetch:async url=>{calls.push(url);return {ok:true,redirected:false,json:async()=>({ok:true,data:url.startsWith('/api/events')?{events:rows,meta:{available:true,retention_days:30}}:[]})}}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/operations.js'),'utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await flush();assert.equal(timers.size,2);assert(calls.includes('/api/events?summary=1'));
 const list=element('event-list');assert.equal(list.children.length,3);
 assert.equal(list.children[0].children[1].children[0].textContent,rows[0].detail,'Technical details are text, never HTML');
 assert.equal(list.children[0].children[0].children[3].textContent,'×5');
 const before=calls.length;
 element('event-source').value='storage';element('event-source').onchange();assert.equal(list.children.length,2,'Storage filter includes USB');
 element('event-level').value='error';element('event-level').onchange();assert.equal(list.children.length,1);
 element('event-search').value='kiem tra';element('event-search').handlers.input[0]();assert.equal(list.children.length,1,'Vietnamese accents do not block search');
 assert.equal(calls.length,before,'Filters do not poll the API');
 element('event-search').value='';element('event-search').handlers.input[0]();
 list.children[0].open=true;await element('event-refresh').onclick();await flush();assert.equal(list.children[0].open,true,'Refresh preserves opened details');
 element('event-source').value='all';element('event-level').value='info';element('event-level').onchange();assert.equal(list.children.length,1);assert.match(list.children[0].children[0].children[2].textContent,/Ghép/);
 document.hidden=true;for(const fn of listeners.visibilitychange||[])fn();assert.equal(timers.size,0);
 const hiddenCalls=calls.length;await element('event-refresh').onclick();assert.equal(calls.length,hiddenCalls);
 document.hidden=false;for(const fn of listeners.visibilitychange||[])fn();await flush();assert.equal(timers.size,2);
 console.log('Activity journal filters, Vietnamese search, safe details, repeat count and visible-only polling PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
