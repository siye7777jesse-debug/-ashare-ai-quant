const assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),ctx={};
vm.runInNewContext(fs.readFileSync("backtest.js","utf8"),ctx);
vm.runInNewContext(fs.readFileSync("validation.js","utf8"),ctx);
const core=ctx.AshareBacktest, validator=ctx.AshareValidation;
function generate(n=160){
 const origin=Date.parse("2023-01-01T00:00:00Z");
 return Array.from({length:n},(_,i)=>{
  const date=new Date(origin+i*86400000).toISOString().slice(0,10);
  const p=i<80?10+i*0.12:19.6-(i-80)*0.08;
  return {date,open:p,high:p+0.3,low:p-0.3,close:p+0.05,volume:10000};
 });
}
function closeTo(x,y,desc){assert.ok(Math.abs(x-y)<1e-9,desc+": "+x+" vs "+y)}
let checks=0, bars=generate(),opts={strategy:"ma",symbol:"600865",capital:100000,commission:0.0003};
const r=validator.split(bars,opts);
assert.equal(r.trainBars,112);assert.equal(r.testBars,48);
assert.equal(r.trainEnd,bars[111].date);assert.equal(r.testStart,bars[112].date);
assert.equal(r.inSample.equity.length,112);
assert.equal(r.outSample.equity.length,49);
assert.equal(r.outSample.firstTradeDate,bars[112].date);
assert.ok(r.outSample.records.every(t=>t.date>=r.testStart));checks++;
const manual=core.run(bars,{...opts,startIndex:112});
closeTo(r.outSample.returnRate,manual.returnRate,"manual holdout");
closeTo(r.outSample.benchmark,bars.at(-1).close/bars[111].close-1,"benchmark baseline");
closeTo(r.outSample.endingCash,manual.endingCash,"holdout cash");
assert.equal(r.outSample.records.length,manual.records.length);checks++;
const changed=bars.map((x,i)=>i>=150?{...x,open:x.open+10,high:x.high+10,low:x.low+10,close:x.close+10}:x);
const d=validator.split(changed,opts);
closeTo(d.inSample.returnRate,r.inSample.returnRate,"future did not change training");
assert.equal(d.inSample.records.length,r.inSample.records.length);
for(let i=0;i<=30;i++)closeTo(d.outSample.equity[i],r.outSample.equity[i],"future did not change early holdout equity "+i);
checks++;
const ratio=validator.split(bars,{...opts,trainRatio:.8});
assert.equal(ratio.trainBars,128);assert.equal(ratio.testBars,32);
assert.equal(ratio.outSample.equity.length,33);checks++;
assert.throws(()=>validator.split(bars,{trainRatio:.9}),/Train ratio/);
assert.throws(()=>validator.split(generate(85)),/样本不足/);checks++;
const poor=validator.split(bars,{...opts,capital:100});
assert.equal(poor.inSample.records.length,0);assert.equal(poor.outSample.records.length,0);checks++;
console.log("Holdout validation: "+checks+" groups passed");
