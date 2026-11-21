/* Fixed-rule cross-stock diagnostic; each symbol is a separate hypothetical account. */
(function(root){
"use strict";
const median=arr=>{if(!arr.length)return null;const a=[...arr].sort((x,y)=>x-y),m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2};
function compare(items,opts={}){
 const validation=root.AshareValidation;
 if(!validation||typeof validation.splitAtDate!=="function")throw Error("Date validation unavailable");
 if(!Array.isArray(items)||items.length<1||items.length>10)throw Error("一次最多比较10只股票");
 if(typeof opts.cutoff!=="string")throw Error("必须选择统一的样本外开始日期");
 const seen=new Set(),results=[];
 const observations=new Map();
 for(const item of items){
  const symbol=String(item.symbol||""),name=String(item.name||symbol);
  if(!/^\d{6}$/.test(symbol)){results.push({symbol,name,error:"无效的股票代码"});continue}
  if(seen.has(symbol)){results.push({symbol,name,error:"重复股票代码"});continue}
  seen.add(symbol);
  if(item.error){results.push({symbol,name,error:String(item.error)});continue}
  try{
   const result=validation.splitAtDate(item.bars,opts.cutoff,{...opts, actions:item.actions, symbol});
   for(const bar of item.bars.slice(-result.testBars)){
    observations.set(bar.date,(observations.get(bar.date)||0)+1);
   }
   results.push({symbol,name,...result});
  }catch(err){results.push({symbol,name,error:String(err.message||err)})}
 }
 const ok=results.filter(x=>!x.error),failed=results.length-ok.length;
 const sharedDates=[...observations].filter(([,count])=>count===ok.length).map(([date])=>date).sort();
 const sameDates=ok.length>0 && sharedDates.length===observations.size;
 const comparable=ok.length>=2 && !failed && sameDates;
 return {cutoff:opts.cutoff,results,summary:{
  comparable,sameObservedWindow:sameDates,
  observedDays:observations.size,sharedDays:sharedDates.length,
  sharedStart:sharedDates[0]??null,sharedEnd:sharedDates.at(-1)??null,
  noTrades:ok.filter(x=>!x.outSample.records.length).length,
  selected:results.length,valid:ok.length,failed,
  positive:ok.filter(x=>x.outSample.returnRate>0).length,
  beatBenchmark:ok.filter(x=>x.outSample.returnRate>x.outSample.benchmark).length,
  medianOosReturn:comparable?median(ok.map(x=>x.outSample.returnRate)):null,
  medianOosDrawdown:comparable?median(ok.map(x=>x.outSample.maxDrawdown)):null
 },notes:"每股独立建账，逐股统计不是组合收益。"};

}
root.AshareMultiStock={compare};
})(typeof globalThis!=="undefined"?globalThis:this);
