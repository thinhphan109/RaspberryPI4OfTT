// Exercise the actual dashboard script's timer lifecycle, without a browser.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},nodes=new Map(),timers=new Map();let sequence=0;
const metrics={temperature:40,cpu:null,ram:{total:100,used:30,percent:30},swap:{total:0,used:0},uptime:10,load:[0,0,0],disks:[],services:[],timestamp:1,network:[],guard:{}};
const network={signal:50,hotspot:{}};
function element(id){if(nodes.has(id))return nodes.get(id);const classes=new Set();const node={id,dataset:{},style:{},innerHTML:'',textContent:'',classList:{toggle(k,on){if(on)classes.add(k);else classes.delete(k)},contains(k){return classes.has(k)},remove(k){classes.delete(k)},add(k){classes.add(k)}},setAttribute(){},removeAttribute(){},replaceChildren(){},append(){},addEventListener(){},scrollIntoView(){},focus(){}};nodes.set(id,node);return node}
element('initial-metrics').textContent=JSON.stringify(metrics);element('initial-network').textContent=JSON.stringify(network);
const views=['overview','network','gpio','activity','storage'].map(element),tabs=views.map(v=>({...element('tab-'+v.id),dataset:{tab:v.id}}));
const document={hidden:false,getElementById:element,querySelectorAll:s=>s.includes('nav-item')?tabs:s.includes('view-section')?views:[],createElement:()=>element('generated-'+sequence++),addEventListener:(name,f)=>(listeners[name]??=[]).push(f)};
const window={addEventListener:document.addEventListener,dispatchEvent:e=>(listeners[e.type]||[]).forEach(f=>f(e))};
const context={document,window,location:{hash:'#overview'},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail}},setInterval:(f,ms)=>{const id=++sequence;timers.set(id,{f,ms});return id},clearInterval:id=>timers.delete(id),AbortSignal,fetch:async url=>({ok:true,redirected:false,json:async()=>({ok:true,data:url==='/api/status'?network:metrics})}),matchMedia:()=>({matches:false}),console};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/dashboard.js'),'utf8'),context);
assert.equal(timers.size,1,'Overview must have only one metrics timer');
document.hidden=true;(listeners.visibilitychange||[]).forEach(f=>f());assert.equal(timers.size,0,'Hidden page must clear all timers');
document.hidden=false;(listeners.visibilitychange||[]).forEach(f=>f());assert.equal(timers.size,1,'Resume must create exactly one timer');
context.location.hash='#network';(listeners.hashchange||[]).forEach(f=>f());assert.equal(timers.size,2,'Network view adds its network timer');
context.location.hash='#overview';(listeners.hashchange||[]).forEach(f=>f());assert.equal(timers.size,1,'Leaving network removes its timer');
console.log('Polling lifecycle: overview, hidden, resume, network, leave — passed');
