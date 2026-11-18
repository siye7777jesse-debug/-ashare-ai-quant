/* Educational A-share backtest core. Prices are unadjusted; no intraday order book. */
(function(root){
"use strict";
function average(bars,end,n){if(end<n-1)return NaN;let s=0;for(let k=end-n+1;k<=end;k++)s+=bars[k].close;return s/n}
function desired(bars,i,type){if(type==="ma")return average(bars,i,5)>average(bars,i,20);if(type==="break")return i>=20&&bars[i].close>Math.max(...bars.slice(i-20,i).map(x=>x.high));if(type==="revert")return i>=5&&bars[i].close/bars[i-5].close-1<-.08;throw Error("Unknown strategy")}
function normalize(bars){if(!Array.isArray(bars))throw Error("Invalid bars");let prev="";return bars.map(b=>{const date=String(b.date);let x={date,open:Number(b.open),high:Number(b.high),low:Number(b.low),close:Number(b.close),volume:Number(b.volume)};if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date))||new Date(date+"T00:00:00Z").toISOString().slice(0,10)!==date||date<=prev||![x.open,x.high,x.low,x.close,x.volume].every(Number.isFinite)||Math.min(x.open,x.high,x.low,x.close)<=0||x.volume<0||x.high<Math.max(x.open,x.close,x.low)||x.low>Math.min(x.open,x.close,x.high))throw Error("Invalid or unordered OHLCV: "+date);prev=date;return x})}
function run(raw,opts={}){
const bars=normalize(raw),capital=Number(opts.capital??100000),commission=Number(opts.commission??.0003),slippage=Number(opts.slippage??.001),minCommission=Number(opts.minCommission??5),type=opts.strategy??"ma",symbol=String(opts.symbol??"");
if(bars.length<25)throw Error("At least 25 bars required");
const startIndex=opts.startIndex===undefined?1:Number(opts.startIndex);
if(!Number.isInteger(startIndex)||startIndex<1||startIndex>=bars.length)throw Error("Invalid evaluation start index");
if(bars.length-startIndex<20)throw Error("Evaluation period must include at least 20 bars");
if(!["ma","break","revert"].includes(type))throw Error("Unknown strategy");
if(!(capital>0&&commission>=0&&commission<.1&&slippage>=0&&slippage<.1&&minCommission>=0))throw Error("Invalid parameters");
let cash=capital,shares=0,entry=-1,peak=capital,maxdd=0,records=[],equity=[capital],stats={signals:0,insufficientCash:0,zeroVolume:0,limitBlocked:0},fees=0;
const mainBoard=/^(60|00)/.test(symbol); // ST and special treatment not detectable from OHLCV.
for(let i=startIndex;i<bars.length;i++){
const b=bars[i],prev=bars[i-1],want=desired(bars,i-1,type),sell=shares>0&&(type==="revert"?i-entry>=5:!want);
const limitUp=mainBoard&&b.open>=prev.close*1.099-1e-8&&b.high<=b.open+1e-8;
const limitDown=mainBoard&&b.open<=prev.close*.901+1e-8&&b.low>=b.open-1e-8;
if(sell){
 if(b.volume<=0)stats.zeroVolume++;
 else if(limitDown)stats.limitBlocked++;
 else if(i>entry){let price=b.open*(1-slippage),gross=shares*price,stamp=b.date<"2023-08-28"?.001:.0005,cost=Math.max(minCommission,gross*commission)+gross*stamp;cash+=gross-cost;fees+=cost;records.push({date:b.date,side:"卖出",price,shares,fees:cost});shares=0;entry=-1}
}
if(!shares&&want&&!sell){
stats.signals++;
if(b.volume<=0)stats.zeroVolume++;
else if(limitUp)stats.limitBlocked++;
else{
const price=b.open*(1+slippage);let qty=Math.floor(cash/(price*(1+commission))/100)*100;
while(qty>0){const gross=qty*price,cost=Math.max(minCommission,gross*commission);if(gross+cost<=cash+1e-8)break;qty-=100}
if(qty<=0)stats.insufficientCash++;
else{const gross=qty*price,cost=Math.max(minCommission,gross*commission);cash-=gross+cost;fees+=cost;shares=qty;entry=i;records.push({date:b.date,side:"买入",price,shares:qty,fees:cost})}
}}
if(cash < -1e-7 || shares<0 || shares%100!==0 || !Number.isFinite(cash))throw Error("Portfolio accounting invariant violated on "+b.date);
const value=cash+shares*b.close;if(!Number.isFinite(value)||value<0)throw Error("Invalid portfolio equity on "+b.date);peak=Math.max(peak,value);maxdd=Math.min(maxdd,value/peak-1);equity.push(value)
}
const last=equity[equity.length-1],years=(Date.parse(bars.at(-1).date)-Date.parse(bars[startIndex-1].date))/86400000/365.25;
const daily=equity.slice(1).map((v,i)=>v/equity[i]-1),avg=daily.reduce((a,b)=>a+b,0)/daily.length,variance=daily.reduce((a,b)=>a+(b-avg)**2,0)/Math.max(1,daily.length-1),vol=Math.sqrt(variance);
return {returnRate:last/capital-1,benchmark:bars.at(-1).close/bars[startIndex-1].close-1,maxDrawdown:maxdd,annualized:years>0?Math.pow(last/capital,1/years)-1:null,sharpe:vol>0?avg/vol*Math.sqrt(252):null,records,equity,stats,fees,endingCash:cash,endingShares:shares,endingEquity:last,firstTradeDate:bars[startIndex].date,baselineDate:bars[startIndex-1].date,evaluationBars:bars.length-startIndex,assumptions:"未复权日线；收盘信号次日开盘模拟；主板近似一字涨跌停限制；T+1；固定滑点；佣金最低5元；印花税按2023-08-28分段；未建模ST、完整停牌与除权分红。"}
}
root.AshareBacktest={run,normalize,desired};
})(typeof globalThis!=="undefined"?globalThis:this);
