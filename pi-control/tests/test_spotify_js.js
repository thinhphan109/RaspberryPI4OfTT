// Run the exact scripts shipped in spotify_player.py against a bounded fake DOM.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../spotify_player.py'),'utf8');
const state=source.match(/STATE_JS=r"""([\s\S]*?)"""/)[1];
const muteScripts=[...source.matchAll(/return evaluate\("([^"\n]+)"\)/g)].map(m=>m[1]);
assert.equal(muteScripts.length,2);
let audio={muted:false,paused:false,currentTime:12,duration:180,volume:.4};
let login=false,advert=false;
const button={getClientRects:()=>[1],getAttribute:()=> 'Pause'};
const document={querySelector:s=>s==='audio'?audio:s.includes('playpause')?button:null,
 querySelectorAll:s=>s.includes('login')?(login?[button]:[]):s.includes('ad-label')?(advert?[button]:[]):[]};
const context={document,window:{},navigator:{mediaSession:{metadata:{title:'Song',artist:'Artist',artwork:[]}}},location:{href:'https://open.spotify.com/'}};
let result=vm.runInNewContext(state,context);assert.equal(result.ad,false);assert.equal(result.position,12);
context.navigator.mediaSession.metadata.title='Advertisement';assert.equal(vm.runInNewContext(state,context).ad,false,'A song title alone is not an ad');
advert=true;result=vm.runInNewContext(state,context);assert.equal(result.ad,true);
vm.runInNewContext(muteScripts[0],context);assert.equal(audio.muted,true);
vm.runInNewContext(muteScripts[0],context);vm.runInNewContext(muteScripts[1],context);assert.equal(audio.muted,false,'Repeated ad samples must preserve pre-ad mute state');
audio.muted=true;vm.runInNewContext(muteScripts[0],context);vm.runInNewContext(muteScripts[1],context);assert.equal(audio.muted,true,'Do not unmute a manually muted player');
audio.muted=false;vm.runInNewContext(muteScripts[0],context);const old=audio;audio={muted:false};vm.runInNewContext(muteScripts[0],context);vm.runInNewContext(muteScripts[1],context);assert.equal(old.muted,false);assert.equal(audio.muted,false,'A replaced media element must not remain muted');
login=true;assert.equal(vm.runInNewContext(state,context).login_required,true);
// Spotify can expose a short, unrelated audio element alongside the actual
// track's UI timeline. Never show that element's duration as the song length.
const query=document.querySelector;
audio={muted:false,paused:false,currentTime:3,duration:6,volume:1};
document.querySelector=s=>s==='[data-testid="playback-position"]'?{textContent:'1:12'}:s==='[data-testid="playback-duration"]'?{textContent:'4:34'}:query(s);
result=vm.runInNewContext(state,context);assert.equal(result.position,72);assert.equal(result.duration,274);assert.equal(result.can_seek,false);assert.equal(result.can_volume,false);
console.log('Spotify exact scripts: explicit ad signals, mute restoration, manual mute preservation and login indicator PASS');
