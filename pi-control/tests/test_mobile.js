// Exercise mobile/desktop transitions against the actual composition script.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const events={},nodes=new Map();
class Node {
 constructor(id){this.id=id;this.children=[];this.attrs={};this.listeners={};this.open=false;this.classes=new Set();this.classList={toggle:(k,on)=>on?this.classes.add(k):this.classes.delete(k),remove:k=>this.classes.delete(k),contains:k=>this.classes.has(k)};if(id)nodes.set(id,this);}
 append(n){this.insertBefore(n,null);}
 insertBefore(n,before){if(n.parent)n.parent.children.splice(n.parent.children.indexOf(n),1);const i=before?this.children.indexOf(before):this.children.length;this.children.splice(i,0,n);n.parent=this;}
 before(n){this.parent.insertBefore(n,this);}
 replaceWith(n){const parent=this.parent;parent.insertBefore(n,this);parent.children.splice(parent.children.indexOf(this),1);this.parent=null;}
 closest(){return this;}
 querySelector(selector){if(selector==='.page-title')return {textContent:this.id==='audio'?'Âm thanh':this.id};return selector==='.media-player'?player:null;}
 addEventListener(name,f){(this.listeners[name]??=[]).push(f);}
 fire(name,data={}){for(const f of this.listeners[name]||[])f(data);}
 setAttribute(k,v){this.attrs[k]=v;}
 removeAttribute(k){delete this.attrs[k];}
 showModal(){this.open=true;}
 close(){this.open=false;this.fire('close');}
}
const body=new Node('body'),media=new Node('media'),layout=new Node('layout'),player=new Node('player'),catalog=new Node('catalog'),speaker=new Node('quick-audio-open'),footer=new Node('footer'),header=new Node('mobile-header-actions'),menu=new Node('mobile-menu'),opener=new Node('mobile-menu-open');
new Node('mobile-menu-close');new Node('audio');new Node('overview');
nodes.set('catalog-form',{closest:()=>catalog});media.append(catalog);media.append(layout);layout.append(player);footer.append(speaker);
const screen={matches:true,addEventListener:(name,f)=>screen.change=f};
const viewport={height:844,addEventListener:(name,f)=>viewport.resize=f};
const document={body,activeElement:{tagName:'BODY'},getElementById:id=>nodes.get(id),createComment:()=>new Node(),querySelector:()=>media,addEventListener:(name,f)=>(events[name]??=[]).push(f)};
const window={innerHeight:844,scrollY:0,visualViewport:viewport,scrollTo:({top})=>{window.scrollY=top},addEventListener:document.addEventListener};
const dispatch=(name,detail)=>{for(const f of events[name]||[])f({detail})};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/mobile.js'),'utf8'),{document,window,matchMedia:()=>screen,fetch:()=>{throw Error('Mobile shell must not call APIs')},setInterval:()=>{throw Error('Mobile shell must not poll')},setTimeout:()=>{throw Error('Mobile shell must not add timers')}});
assert.equal(player.parent,media);assert(media.children.indexOf(player)<media.children.indexOf(catalog));assert.equal(speaker.parent,header);
opener.fire('click');assert(menu.open);assert.equal(opener.attrs['aria-expanded'],'true');
window.scrollY=300;dispatch('pi:view','audio');assert(!menu.open);assert(opener.classList.contains('active'));assert.equal(opener.attrs['aria-current'],'page');assert.equal(window.scrollY,0);
window.scrollY=200;dispatch('pi:view','media');assert.equal(window.scrollY,300);assert(!opener.classList.contains('active'));
document.activeElement={tagName:'INPUT',type:'search'};viewport.height=440;dispatch('focusin');assert(body.classList.contains('mobile-keyboard'));
document.activeElement={tagName:'BODY'};dispatch('focusout');assert(!body.classList.contains('mobile-keyboard'));
opener.fire('click');menu.fire('keydown',{key:'Escape',preventDefault(){}});assert(!menu.open);assert.equal(opener.attrs['aria-expanded'],'false','Escape resets expanded state');
screen.matches=false;screen.change();assert.equal(player.parent,layout);assert.equal(speaker.parent,footer);assert(!menu.open);
for(let i=0;i<3;i++){screen.matches=true;screen.change();screen.matches=false;screen.change();}
assert.deepEqual(layout.children,[player]);assert.deepEqual(footer.children,[speaker]);assert.deepEqual(media.children,[catalog,layout],'Resize restores exact DOM order without duplicate controllers');
console.log('Mobile composition: single controls, menu lifecycle, view scroll, keyboard and repeated desktop restoration PASS');
