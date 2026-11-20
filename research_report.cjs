// Reproducible, fixed-rule forward windows for the existing cache. Runs on a PC or Actions.
"use strict";
const fs = require("node:fs");
const crypto = require("node:crypto");
require("./backtest.js");

const capital = 100000;
const config = {capital, strategy:"ma", commission:.0003, slippage:.001, minCommission:5};
const symbols = ["000759","300308","600519","600838","600865","601138"];
const read = path => fs.readFileSync(path);
const hash = b => crypto.createHash("sha256").update(b).digest("hex");
function evaluate(dataset, actions) {
  if (dataset.symbol!==actions.symbol || dataset.adjustment!=="none") throw Error("行情与分配口径不一致");
  const bars = AshareBacktest.normalize(dataset.bars);
  if (bars[0].date<actions.start || bars.at(-1).date>actions.end) throw Error("分配记录覆盖不足");
  const windows = [];
  for (let year=Number(bars[0].date.slice(0,4))+1; year<=Number(bars.at(-1).date.slice(0,4)); year++) {
    const cutoff = year+"-01-01", end = year+"-12-31";
    const history = bars.filter(b=>b.date<=end);
    const startIndex = history.findIndex(b=>b.date>=cutoff);
    const window = {year, start:history[startIndex]?.date, end:history.at(-1)?.date,
      partial: actions.end<end, warmupBars:startIndex, testBars:startIndex<0?0:history.length-startIndex};
    try {
      if (startIndex<60 || window.testBars<30) throw Error("至少需要60条预热日线和30条样本外日线");
      const r = AshareBacktest.run(history,{...config,symbol:dataset.symbol,startIndex,
        actions:actions.events.filter(e=>e.date<=end)});
      Object.assign(window,{returnRate:r.returnRate, benchmark:r.benchmark, maxDrawdown:r.maxDrawdown,
        trades:r.records.length, dividends:r.dividends, fees:r.fees});
    } catch (e) { window.error=e.message; }
    windows.push(window);
  }
  return windows;
}
function build() {
  const stocks=symbols.map(symbol=>{
    const prices=read("data/"+symbol+".json"), events=read("data/actions/"+symbol+".json");
    const d=JSON.parse(prices), a=JSON.parse(events);
    if (d.symbol!==symbol || a.symbol!==symbol) throw Error("缓存股票代码不符："+symbol);
    return {symbol, priceSHA256:hash(prices), actionsSHA256:hash(events), asOf:d.bars.at(-1).date,
      windows:evaluate(d,a)};
  });
  return {config, method:"固定5/20日均线；逐自然年向前验证，各年独立空仓起步，不拼接年度收益。",stocks};
}
if (require.main===module) {
  const path="data/research.json", output=JSON.stringify(build())+"\n";
  if (process.argv.includes("--check")) {
    if (read(path).toString()!==output) throw Error("预计算报告与行情、分配或回测规则不一致");
  } else fs.writeFileSync(path,output);
}
module.exports={evaluate,build};
