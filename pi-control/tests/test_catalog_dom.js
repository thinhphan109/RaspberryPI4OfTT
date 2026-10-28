const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path'),cp=require('node:child_process');
const source=fs.readFileSync(path.join(__dirname,'../media_catalog.py'),'utf8');
const script=source.match(/SPOTIFY_JS = r"""([\s\S]*?)"""/)[1];
function fixture(loading){
 const footer={href:'https://open.spotify.com/playlist/'+'F'.repeat(22),textContent:'Top Song Lyrics',getClientRects:()=>[{}],closest:()=>({}),getAttribute:()=>null};
 const track={href:'https://open.spotify.com/track/'+'A'.repeat(22),textContent:'Song matching query',getClientRects:()=>[{}],closest:selector=>selector.startsWith('footer')?null:{innerText:'Song · Artist'},getAttribute:()=>null};
 const list={querySelectorAll:()=>[footer,track]};
 const main={querySelector:s=>s.includes('track-list')?list:null,querySelectorAll:s=>s.includes('loading')?(loading?[{getClientRects:()=>[{}]}]:[]):[footer,track]};
 return {document:{querySelector:()=>main},location:{pathname:'/search/music/tracks'}};
}
let data=vm.runInNewContext(script,fixture(true));assert.equal(data.ready,false);assert.equal(data.rows.some(row=>row.title==='Top Song Lyrics'),false,'Footer must never appear as search result');
data=vm.runInNewContext(script,fixture(false));assert.equal(data.ready,true);assert.equal(data.query,'music');assert.equal(data.kind,'tracks');assert.equal(data.rows.length,1);assert(data.rows[0].url.includes('/track/'));
const py=fs.readFileSync(path.join(__dirname,'../spotify_player.py'),'utf8'),stateScript=py.match(/STATE_JS=r"""([\s\S]*?)"""/)[1];
const link={href:'https://open.spotify.com/track/'+'A'.repeat(22),textContent:'Current song'},widget={querySelector:s=>s.includes('a[')?link:null},button={getClientRects:()=>[{}],getAttribute:()=> 'Pause',disabled:false};
const context={navigator:{mediaSession:{metadata:{title:'Old metadata'}}},window:{},location:{href:'https://open.spotify.com/playlist/'+'B'.repeat(22)},document:{querySelector:s=>s.includes('now-playing-widget')?widget:s.includes('control-button-playpause')?button:s==='main'?{innerText:'This playlist is not available. The owner of this playlist has made it private or removed it from Spotify.'}:null,querySelectorAll:()=>[]}};
data=vm.runInNewContext(stateScript,context);assert.equal(data.title,'Current song');assert.equal(data.track_url,link.href);assert.equal(data.content_unavailable,true);
// Current Spotify uses an album link in widget-v2. A track page alone must not
// confirm playback while the old song or a different artist is still playing.
const albumLink={textContent:'Previous song'},wanted={href:link.href,textContent:'Requested song'},artist={textContent:'Artist'};
const matchingRow={querySelectorAll:s=>s.includes('/artist/')?[artist]:[wanted]};
const v2={querySelector:s=>s==='a[href*="/album/"]'?albumLink:null};
const songContext={window:{},location:{href:link.href},navigator:{mediaSession:{metadata:{title:'Previous song',artist:'Artist'}}},document:{querySelector:s=>s.includes('now-playing-widget')?v2:s.includes('control-button-playpause')?button:s==='main'?{innerText:''}:null,querySelectorAll:s=>s.startsWith('main ')?[matchingRow]:[]}};
assert.equal(vm.runInNewContext(stateScript,songContext).track_matches,false);
albumLink.textContent='Requested song';assert.equal(vm.runInNewContext(stateScript,songContext).track_matches,true);
songContext.navigator.mediaSession.metadata.artist='Other';assert.equal(vm.runInNewContext(stateScript,songContext).track_matches,false);
songContext.location.href='https://open.spotify.com/album/'+'B'.repeat(22)+'?highlight=spotify%3Atrack%3A'+'A'.repeat(22);
songContext.PI_EXPECTED={url:link.href,title:'Requested song',art:''};songContext.document.querySelectorAll=()=>[];
data=vm.runInNewContext(stateScript,songContext);assert.equal(data.track_matches,true);assert.equal(data.track_url,link.href,'Album redirect retains the verified track identity');
songContext.PI_EXPECTED.art='32a7d87248d1b75463483df5';songContext.navigator.mediaSession.metadata.artwork=[{src:'https://i.scdn.co/image/ab67616d0000b27332a7d87248d1b75463483df5'}];
const widgetAlbum={href:'https://open.spotify.com/album/'+'B'.repeat(22),textContent:'Requested song'};
v2.querySelector=s=>s.includes('a[')?widgetAlbum:null;
data=vm.runInNewContext(stateScript,songContext);assert.equal(data.track_matches,true,'640px and 300px image variants share artwork identity');assert.equal(data.track_url,link.href,'Verified track takes precedence over album context link');
widgetAlbum.textContent='Wrong song';
albumLink.textContent='Wrong song';assert.equal(vm.runInNewContext(stateScript,songContext).track_matches,false);
const target='https://open.spotify.com/track/'+'A'.repeat(22);
const activate=JSON.parse(cp.execFileSync('python',['-c',"import sys,json;sys.path.insert(0,sys.argv[1]);import spotify_player as s;print(json.dumps(s.activate(lambda script:script,sys.argv[2])))",path.join(__dirname,'..'),target],{encoding:'utf8'}));
let clicked=0,generic=0;const row={querySelectorAll:()=>[{href:target}],querySelector:()=>({disabled:false,getAttribute:()=> 'Play current song',click:()=>clicked++})};
const activation={URL,document:{querySelector:()=>({querySelectorAll:()=>[row],querySelector:()=>{generic++;return null}})}};
assert.equal(vm.runInNewContext(activate,activation),true);assert.equal(clicked,1);assert.equal(generic,0,'Play the matched track, not another recommended card');
console.log('Catalog DOM: loading/footer rejection, track-only results, Spotify widget-v2, unavailable content and exact-row activation PASS');
