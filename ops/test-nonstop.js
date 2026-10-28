const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../pi-control/media_agent.py'),'utf8');
const js=source.match(/NONSTOP_JS="""([\s\S]*?)"""/)[1];
function run(text){
 let toggles=0,plays=0,confirms=0;
 const button={offsetParent:{},textContent:'Continue',click(){confirms++}};
 const dialog={textContent:text,querySelectorAll(){return [button]}};
 const doc={querySelector(s){return s==='video'?{paused:true,ended:false,play(){plays++;return Promise.resolve()}}:{getAttribute(){return 'false'},click(){toggles++}}},querySelectorAll(){return [dialog]}};
 vm.runInNewContext(js,{document:doc});return {toggles,plays,confirms};
}
assert.deepEqual(run('Video paused. Continue watching?'),{toggles:1,plays:1,confirms:1});
assert.equal(run('Video đã tạm dừng. Tiếp tục xem?').confirms,1);
assert.equal(run('Sign in to continue watching').confirms,0);
assert.equal(run('Nhập mật khẩu để tiếp tục xem').confirms,0);
assert.equal(run('Accept terms of service').confirms,0);
console.log('Nonstop browser script: 5 prompt/resume safety scenarios PASS');
