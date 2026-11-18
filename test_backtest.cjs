const assert=require("node:assert/strict");const fs=require("node:fs");const vm=require("node:vm");const code=fs.readFileSync("backtest.js","utf8");const context={};vm.runInNewContext(code,context);const bt=context.AshareBacktest;
function bars(price=10){return Array.from({length:40},(_,i)=>({date:"2024-01-"+String(i+1).padStart(2,"0"),open:price+i*.2,high:price+i*.2+.3,low:price+i*.2-.3,close:price+i*.2+.1,volume:10000}))}
let b=bars(); // Use calendar-valid dates for date-based metrics
b=Array.from({length:45},(_,i)=>{const date=new Date(Date.UTC(2024,0,1+i)).toISOString().slice(0,10),p=10+i*.2;return {date,open:p,high:p+.3,low:p-.3,close:p+.1,volume:10000}});
const a=bt.run(b,{capital:100000,strategy:"ma",symbol:"600865",slippage:0});
assert.ok(a.records.length>0,"trending prices should produce trades");
assert.ok(a.endingCash>=-1e-6,"cash cannot go negative");
assert.ok(a.records.every(x=>x.shares%100===0));
assert.ok(a.returnRate!==0);
const noFunds=bt.run(b,{capital:100,strategy:"ma",symbol:"600865"});
assert.equal(noFunds.records.length,0);assert.ok(noFunds.stats.insufficientCash>0);
const flat=b.map(x=>({...x,open:10,high:10.1,low:9.9,close:10}));const noSignal=bt.run(flat,{strategy:"ma"});assert.equal(noSignal.records.length,0);assert.equal(noSignal.stats.signals,0);
assert.throws(()=>bt.run([...b].reverse()),/Invalid or unordered/);
const t1=bt.run(b,{strategy:"revert"});assert.ok(t1.records.every((r,i)=>i===0||r.side!==t1.records[i-1].side||r.side==="买入"));
console.log("Backtest core: 6 checks passed");
