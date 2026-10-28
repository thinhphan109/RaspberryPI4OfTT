// Real Media/Audio scripts: a successful HTTP response can still contain an error.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
function run(file,initial){
 const elements=new Map(),messages=[],timers=[];let result=initial,throwPost=false;
 const element=id=>{if(elements.has(id))return elements.get(id);const e={value:'',dataset:{},classList:{contains:()=>true},querySelectorAll:()=>[],contains:()=>false,replaceChildren(){},append(){},setAttribute(){},matches:()=>false};elements.set(id,e);return e;};
 const document={hidden:false,activeElement:null,getElementById:element,querySelectorAll:()=>[],createElement:()=>element('new-'+elements.size),addEventListener(){}};
 const window={addEventListener(){},PiUI:{feedback:(id,text,tone)=>messages.push({id,text,tone})}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),{document,window,location:{},AbortSignal,console,setInterval:fn=>{timers.push(fn);return timers.length},clearInterval(){},fetch:async(url,opts)=>{if(opts?.method==='POST'&&throwPost)throw Error('Thao tác không hợp lệ');return{ok:true,redirected:false,json:async()=>({ok:true,data:result})}}});
 return{element,messages,timers,set:value=>result=value,failPost:value=>throwPost=value};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const media=run('media.js',{connected:true,error:'Không mở được video',queue:[]});await flush();media.messages.length=0;
 await media.element('media-play').onclick();assert.equal(media.messages.at(-1).tone,'error');assert.equal(media.messages.at(-1).text,'Không mở được video');
 assert(!media.messages.some(m=>m.tone==='success'),'Media error must not be overwritten by success');
 media.set({connected:true,notice:'Đang chờ trình duyệt',queue:[]});await media.element('media-play').onclick();assert.equal(media.messages.at(-1).tone,'info');
 media.set({connected:true,queue:[]});await media.element('media-play').onclick();assert.equal(media.messages.at(-1).tone,'info','HTTP success alone does not confirm playback');
 media.set({connected:true,queue:[],command:{id:'verified',state:'confirmed',message:'Confirmed'}});await media.element('media-play').onclick();assert.equal(media.messages.at(-1).tone,'success');
 const audioState={devices:[],defaults:{},bluetooth:{powered:false,available:true,devices:[]},job:{message:''},errors:[]};
 const audio=run('audio.js',audioState);await flush();audio.messages.length=0;audio.set({...audioState,errors:['Không kết nối được loa']});
 await audio.element('audio-bt-power').onclick();assert.equal(audio.messages.at(-1).tone,'error');assert(!audio.messages.some(m=>m.tone==='success'));
 audio.set(audioState);await audio.timers[0]();await flush();audio.messages.length=0;audio.failPost(true);
 await audio.element('audio-bt-power').onclick();assert.equal(audio.messages.at(-1).tone,'error');const count=audio.messages.length;
 await audio.timers[0]();await flush();assert.equal(audio.messages.length,count,'A successful poll must not dismiss action errors');
 audio.failPost(false);await audio.element('audio-bt-power').onclick();assert.equal(audio.messages.at(-1).tone,'success');
 console.log('Media/Audio errors survive successful HTTP/polling and only real success shows confirmation PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
