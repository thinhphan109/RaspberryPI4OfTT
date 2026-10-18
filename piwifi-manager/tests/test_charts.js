const assert=require('node:assert/strict');
const c=require('../static/charts.js');
const p=c.layout(800,100,1000,1100);
const path=c.path([{t:1000,v:0},{t:1050,v:50},{t:1100,v:100}],'v',p,60);
assert.match(path,/^M62.00 199.00 L423.00 112.50 L784.00 26.00$/);
assert.equal((c.path([{t:1000,v:0},{t:1010,v:null},{t:1020,v:10}],'v',p,25).match(/M/g)||[]).length,2,'null must break a series');
assert.equal((c.path([{t:1000,v:0},{t:1090,v:10}],'v',p,25).match(/M/g)||[]).length,2,'outage must break a series');
assert.equal(c.path([{t:999,v:50},{t:1050,v:NaN},{t:1101,v:10}],'v',p),'');
for(const value of [0,.1,1,3,8,18,100,1025])assert.ok(c.ceiling(value)>=Math.max(1,value)||value>0&&c.ceiling(value)>=value);
const phone=c.layout(320,100,1000,1100,true);assert.ok(phone.right>phone.left);assert.equal(phone.height,240);
for(const [width,height]of [[240,220],[390,220],[768,260],[1024,180],[1366,300],[2560,300]]){
 const plot=c.layout(width,100,1000,1100,true,height);
 assert.ok(plot.right>plot.left&&plot.bottom<plot.height-20,'labels must have their own space');
 const line=c.path([{t:1000,v:0},{t:1100,v:100}],'v',plot,200);
 assert.ok(line.startsWith(`M${plot.left.toFixed(2)} ${plot.bottom.toFixed(2)}`));
 assert.ok(line.endsWith(`${plot.right.toFixed(2)} ${plot.top.toFixed(2)}`));
}
console.log('Chart scale, actual-time spacing, null/outage gaps, invalid values and phone layout PASS');
const samples=[{timestamp:10,v:0},{timestamp:20,v:null},{timestamp:30,v:4}];
assert.equal(c.nearest(samples,11).v,0,'Zero is a real value');
assert.equal(c.nearest(samples,20).v,null,'Missing values must not become zero');
assert.equal(c.nearest(samples,26).timestamp,30);
assert.equal(c.nearest(samples,25,2),null,'No sample selected inside a gap');
assert.equal(c.nearest([],10),null);
assert.equal(c.nearest([{t:12}],12).t,12);
console.log('Tooltip nearest sample, zero/missing values and gap selection PASS');
