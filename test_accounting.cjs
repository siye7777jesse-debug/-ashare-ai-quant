const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ctx = {};
vm.runInNewContext(fs.readFileSync("backtest.js","utf8"),ctx);
const bt = ctx.AshareBacktest;
function make(start="2023-08-01",length=65,fn=i=>10+i*.12){
  const begin=Date.parse(start+"T00:00:00Z");
  return Array.from({length},(_,i)=>{
    const p=fn(i),date=new Date(begin+i*86400000).toISOString().slice(0,10);
    return {date,open:p,high:p+.2,low:p-.2,close:p,volume:10000};
  });
}
function approx(actual,expected,label){assert.ok(Math.abs(actual-expected)<1e-6,label+": "+actual+" != "+expected)}
let tests=0;
const trend=make("2023-08-01",65,i=>i<34?10+i*.2:16.8-(i-34)*.22);
const res=bt.run(trend,{strategy:"ma",symbol:"600865",capital:100000,slippage:0,commission:.0003});
assert.ok(res.records.some(x=>x.side==="买入"));assert.ok(res.records.some(x=>x.side==="卖出"));
let cash=100000,shares=0,buyDay="";
for(const r of res.records){
  const gross=r.price*r.shares;
  assert.equal(r.shares%100,0);
  if(r.side==="买入"){
    assert.equal(shares,0,"must not buy while holding");
    cash-=gross+r.fees;shares=r.shares;buyDay=r.date;
  }else{
    assert.ok(shares>0);assert.equal(r.shares,shares);
    assert.ok(r.date>buyDay,"T+1");
    cash+=gross-r.fees;shares=0;
  }
  assert.ok(cash>=-1e-6,"cash nonnegative");
}
approx(cash,res.endingCash,"cash ledger");
assert.equal(shares,res.endingShares);
approx(cash+shares*trend.at(-1).close,res.endingEquity,"ending equity");
approx(res.endingEquity/100000-1,res.returnRate,"return rate");
assert.equal(res.equity.length,trend.length);tests++;
// One-lot affordability: cash exactly sufficient after minimum commission.
const oneLot=bt.run(make("2024-01-01",35,i=>10+i*.1),{capital:1100,strategy:"ma",slippage:0,commission:0,minCommission:5});
assert.ok(oneLot.records.some(x=>x.side==="买入"));tests++;
// Explicit 2023-08-28 stamp tax cut: sale tax differs for same notional.
const before=make("2023-07-01",65,i=>i<34?10+i*.2:16.8-(i-34)*.22);
const after=make("2023-09-01",65,i=>i<34?10+i*.2:16.8-(i-34)*.22);
const rBefore=bt.run(before,{capital:100000,slippage:0,strategy:"ma"});
const rAfter=bt.run(after,{capital:100000,slippage:0,strategy:"ma"});
const saleBefore=rBefore.records.find(x=>x.side==="卖出");
const saleAfter=rAfter.records.find(x=>x.side==="卖出");
assert.ok(saleBefore&&saleAfter);
const grossBefore=saleBefore.price*saleBefore.shares;
const grossAfter=saleAfter.price*saleAfter.shares;
approx(saleBefore.fees,Math.max(5,grossBefore*.0003)+grossBefore*.001,"old stamp tax");
approx(saleAfter.fees,Math.max(5,grossAfter*.0003)+grossAfter*.0005,"new stamp tax");tests++;
// Invalid dates, duplicated days and malformed candles are rejected.
assert.throws(()=>bt.normalize([{date:"2024-02-30",open:10,high:11,low:9,close:10,volume:100}]),/Invalid/);
assert.throws(()=>bt.normalize([trend[0],trend[0]]),/Invalid/);
assert.throws(()=>bt.normalize([{...trend[0],volume:-1}]),/Invalid/);tests++;
// 100-share lots, insufficient cash and no signal.
const poor=bt.run(make("2024-01-01",40,i=>10+i*.1),{capital:100,strategy:"ma"});
assert.equal(poor.records.length,0);assert.ok(poor.stats.insufficientCash>0);tests++;
console.log("Accounting and execution regression tests passed:",tests);
