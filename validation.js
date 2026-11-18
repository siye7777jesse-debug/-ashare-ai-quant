/* Chronological holdout validation; never train or execute on future evaluation dates. */
(function(root){
"use strict";
function split(raw,opts={}){
 const core=root.AshareBacktest;
 if(!core||typeof core.run!=="function")throw Error("Backtest core is unavailable");
 const bars=core.normalize(raw);
 const trainRatio=opts.trainRatio===undefined?0.7:Number(opts.trainRatio);
 if(!(trainRatio>=0.5&&trainRatio<=0.85))throw Error("Train ratio must be between 50% and 85%");
 const trainCount=Math.floor(bars.length*trainRatio),testCount=bars.length-trainCount;
 if(trainCount<60||testCount<30)throw Error("样本不足：至少60条样本内日线和30条样本外日线");
 const cfg={...opts};
 delete cfg.trainRatio;
 delete cfg.startIndex;
 // Optimize nothing with test data. Strategy/fees/capital are fixed before comparing.
 const inside=core.run(bars.slice(0,trainCount),cfg);
 // The earlier history is visible only as indicator warmup; initial position is flat,
 // initial cash is restored to capital, and trading begins on the first holdout bar.
 const outside=core.run(bars,{...cfg,startIndex:trainCount});
 if(outside.records.some(r=>r.date<bars[trainCount].date))throw Error("Holdout leakage detected");
 return {
   inSample:inside,outSample:outside,
   trainBars:trainCount,testBars:testCount,
   trainStart:bars[0].date,trainEnd:bars[trainCount-1].date,
   testStart:bars[trainCount].date,testEnd:bars.at(-1).date,
   splitIndex:trainCount,
   warning:"仅按时间划分固定策略；如果曾用全区间选择参数或多次查看样本外结果后调参，这不属于独立样本外验证。"
 };
}
root.AshareValidation={split};
})(typeof globalThis!=="undefined"?globalThis:this);
