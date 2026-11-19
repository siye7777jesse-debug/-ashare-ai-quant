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
 for(const item of items){
  const symbol=String(item.symbol||""),name=String(item.name||symbol);
  if(!/^\d{6}$/.test(symbol)){results.push({symbol,name,error:"无效的股票代码"});continue}
  if(seen.has(symbol)){results.push({symbol,name,error:"重复股票代码"});continue}
  seen.add(symbol);
  if(item.error){results.push({symbol,name,error:String(item.error)});continue}
  try{
   const result=validation.splitAtDate(item.bars,opts.cutoff,{capital:opts.capital,commission:opts.commission,strategy:opts.strategy,symbol});
   results.push({symbol,name,...result});
  }catch(err){results.push({symbol,name,error:String(err.message||err)})}
 }
 const ok=results.filter(x=>!x.error),failed=results.length-ok.length;
 return {cutoff:opts.cutoff,results,summary:{
  selected:results.length,valid:ok.length,failed,
  positive:ok.filter(x=>x.outSample.returnRate>0).length,
  beatBenchmark:ok.filter(x=>x.outSample.returnRate>x.outSample.benchmark).length,
  medianOosReturn:median(ok.map(x=>x.outSample.returnRate)),
  medianOosDrawdown:median(ok.map(x=>x.outSample.maxDrawdown))
 },notes:"按同一日期分界，每股独立初始资金及空仓起步；汇总仅为横截面中位数，不是组合收益。失效或缺失股票不能视为零收益，未包含退市股票和完整历史股票池。"};
}
root.AshareMultiStock={compare};
})(typeof globalThis!=="undefined"?globalThis:this);
