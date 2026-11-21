const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const ctx={};
for(const file of ["backtest.js","validation.js","multistock.js"]){vm.runInNewContext(fs.readFileSync(file,"utf8"),ctx)}
const v=ctx.AshareValidation,m=ctx.AshareMultiStock;
function make(n,initial="2024-01-01",slope=.1,skip=0){
 const start=Date.parse(initial+"T00:00:00Z"),out=[];
 for(let i=0;i<n;i++){if(skip && i%skip===0)continue;
  const date=new Date(start+i*86400000).toISOString().slice(0,10),p=10+i*slope;
  out.push({date,open:p,high:p+.2,low:p-.2,close:p,volume:10000})}
 return out
}
const a=make(180),b=make(180,"2024-01-01",-.03),c=make(180,"2024-01-01",.07,9);
const cutoff="2024-05-01",cfg={cutoff,capital:100000,commission:.0003,strategy:"ma"};
const splitA=v.splitAtDate(a,cutoff,{...cfg,symbol:"600865"});
assert.ok(splitA.trainBars>=60 && splitA.testBars>=30);
assert.ok(splitA.trainEnd<cutoff && splitA.testStart>=cutoff);
assert.equal(splitA.outSample.firstTradeDate,splitA.testStart);
assert.ok(splitA.outSample.records.every(r=>r.date>=cutoff));
assert.equal(splitA.outSample.equity.length,splitA.testBars+1);
const mutated=a.map(x=>x.date>"2024-06-01"?{...x,open:x.open*1.1,high:x.high*1.1,low:x.low*1.1,close:x.close*1.1}:x);
const splitA2=v.splitAtDate(mutated,cutoff,{...cfg,symbol:"600865"});
assert.equal(splitA.inSample.returnRate,splitA2.inSample.returnRate);
assert.deepEqual(splitA.inSample.records.map(x=>x.date),splitA2.inSample.records.map(x=>x.date));
const r=m.compare([{symbol:"600865",name:"百大集团",bars:a},{symbol:"000759",name:"中百集团",bars:b},{symbol:"300308",name:"中际旭创",bars:c},{symbol:"601138",error:"Source unavailable"}],cfg);
assert.equal(r.summary.selected,4);assert.equal(r.summary.valid,3);assert.equal(r.summary.failed,1);
assert.equal(r.results[3].error,"Source unavailable");
for(const x of r.results.slice(0,3)){assert.ok(x.trainEnd<cutoff);assert.ok(x.testStart>=cutoff);assert.ok(x.outSample.records.every(t=>t.date>=cutoff))}
assert.equal(r.results[0].testStart,r.results[1].testStart);
assert.ok(r.results[2].testStart>=cutoff);
assert.equal(r.summary.medianOosReturn,null);
assert.equal(r.summary.comparable,false);
const full=m.compare([{symbol:"600865",bars:a},{symbol:"000759",bars:b}],cfg);
assert.equal(full.summary.comparable,true);
assert.equal(full.summary.medianOosReturn,full.results.reduce((sum,row)=>sum+row.outSample.returnRate,0)/2);
const missing=m.compare([{symbol:"600865",bars:a.filter((_,i)=>i!==145)},{symbol:"000759",bars:b.filter((_,i)=>i!==146)}],cfg);
assert.equal(missing.results[0].testBars,missing.results[1].testBars);
assert.equal(missing.summary.observedDays,splitA.testBars);
assert.equal(missing.summary.sharedDays,splitA.testBars-2);
assert.equal(missing.summary.sameObservedWindow,false);
assert.equal(missing.summary.medianOosDrawdown,null);
assert.equal(r.summary.positive,r.results.slice(0,3).filter(x=>x.outSample.returnRate>0).length);
assert.ok(r.notes.includes("不是组合收益"));
const poor=m.compare([{symbol:"600865",bars:a}],{...cfg,capital:100});
assert.equal(poor.summary.noTrades,1);assert.equal(poor.summary.comparable,false);
assert.equal(poor.results[0].outSample.records.length,0);
const invalid=m.compare([{symbol:"600865",bars:a.slice(140)},{symbol:"600865",bars:a},{symbol:"ABC",bars:a}],cfg);
assert.equal(invalid.summary.sharedStart,null);assert.equal(invalid.summary.sharedDays,0);
assert.equal(invalid.summary.valid,0);assert.equal(invalid.summary.failed,3);
assert.throws(()=>v.splitAtDate(a,"2024-02-30",cfg),/无效/);
assert.throws(()=>v.splitAtDate(make(70),cutoff,cfg),/至少/);
console.log("Cross-stock holdout tests: passed (date isolation, failure handling, medians and bounds)");
