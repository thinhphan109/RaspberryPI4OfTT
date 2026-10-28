// Shared help/feedback behavior, with API and background polling forbidden.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),events={},timers=new Map();let next=0;
function node(id){if(nodes.has(id))return nodes.get(id);const value={id,dataset:{},hidden:false,open:false,textContent:'',children:[],handlers:{},isConnected:true,classList:{add(){}},setAttribute(name,value){this[name]=value},replaceChildren(...items){this.children=items},focus(){this.focused=true},addEventListener(name,fn){this.handlers[name]=fn},showModal(){this.open=true},close(){this.open=false;this.handlers.close?.()},querySelector(selector){return selector==='.help-drawer-body'?node('body'):null},querySelectorAll(){return topics}};nodes.set(id,value);return value;}
const topics=['camera','network','media'].map(name=>Object.assign(node('topic-'+name),{dataset:{helpTopic:name},hidden:true}));
const buttons=['camera','network','media'].map(name=>Object.assign(node('help-'+name),{dataset:{helpPage:name}}));
node('camera').querySelector=()=>({textContent:'Camera & timelapse'});node('network').querySelector=()=>({textContent:'Kết nối mạng'});
const document={getElementById:node,createElement:tag=>node(tag+'-'+ ++next),querySelectorAll:selector=>selector==='[data-help-page]'?buttons:[]};
const window={addEventListener:(name,fn)=>events[name]=fn};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/interface.js'),'utf8'),{document,window,setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),fetch:()=>{throw Error('UI help must not fetch')},setInterval:()=>{throw Error('UI help must not poll')}});
buttons[0].handlers.click();assert(node('ui-help').open);assert.equal(node('ui-help-title').textContent,'Camera & timelapse');assert.deepEqual(topics.map(t=>t.hidden),[false,true,true]);
node('ui-help-close').onclick();assert(!node('ui-help').open);assert(buttons[0].focused);
buttons[1].handlers.click();events['pi:view']();assert(!node('ui-help').open);
window.PiUI.feedback('result','Không đọc được ổ lưu','error');assert.equal(node('result').role,'alert');assert.equal(timers.size,0);assert.equal(node('result').hidden,false);
window.PiUI.feedback('result','Đã lưu','success');assert.equal(timers.size,1);assert.equal([...timers.values()][0].ms,5000);
window.PiUI.feedback('result','Đã lưu','success');assert.equal(timers.size,1,'Same render must not reset timeout');
[...timers.values()][0].fn();assert(node('result').hidden);assert.equal(timers.size,0);
window.PiUI.feedback('result','<img src=x onerror=alert(1)>','error');assert.equal(node('result').children[0].textContent,'<img src=x onerror=alert(1)>');assert.equal(node('result').children.length,2);
node('result').children[1].onclick();assert(node('result').hidden);
window.PiUI.feedback('result','Đã cập nhật','success');buttons[2].handlers.click();events.pagehide();assert.equal(timers.size,0);assert(!node('ui-help').open);
console.log('Context help, focus return, persistent errors, deduplicated 5s success, safe text and no polling PASS');
