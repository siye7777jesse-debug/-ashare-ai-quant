/* Fixed daily-bar strategies. A signal uses only observations through yesterday. */
(function(root){
"use strict";

function average(bars, end, n) {
  if (end < n - 1) return NaN;
  let sum = 0;
  for (let i = end - n + 1; i <= end; i++) sum += bars[i].close;
  return sum / n;
}
function desired(bars, i, strategy) {
  if (strategy === "ma") return average(bars, i, 5) > average(bars, i, 20);
  if (strategy === "break") return i >= 20 && bars[i].close > Math.max(...bars.slice(i - 20, i).map(b => b.high));
  return i >= 5 && bars[i].close / bars[i - 5].close - 1 < -.08;
}
function validDate(date) {
  return typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date)
    && Number.isFinite(Date.parse(date)) && new Date(date).toISOString().slice(0, 10) === date;
}
function normalize(bars) {
  if (!Array.isArray(bars)) throw Error("Invalid bars");
  let prev = "";
  return bars.map(b => {
    const {date, open, high, low, close, volume} = b;
    if (!validDate(date) || date <= prev || ![open, high, low, close, volume].every(Number.isFinite)
      || low <= 0 || low > Math.min(open, close) || high < Math.max(open, close) || volume < 0)
      throw Error("Invalid or unordered OHLCV: " + date);
    prev = date;
    return {date, open, high, low, close, volume};
  });
}
function distributions(actions, bars) {
  const byDay = new Map(), dates = new Set(bars.map(b => b.date));
  for (const e of actions) {
    if (!validDate(e.date) || ![e.cashPerShare, e.bonusPerShare].every(x => Number.isFinite(x) && x >= 0))
      throw Error("分配记录格式错误");
    if (e.date < bars[0].date || e.date > bars.at(-1).date) continue;
    if (byDay.has(e.date) || !dates.has(e.date)) throw Error("分配日期重复或缺失日线：" + e.date);
    byDay.set(e.date, e);
  }
  return byDay;
}
function marketRules(symbol, date) {
  if (/^68/.test(symbol)) return {limit: .20, minimum: 200, step: 1};
  if (/^(4|8|92)/.test(symbol)) return {limit: .30, minimum: 100, step: 1};
  const growth = /^30/.test(symbol) && date >= "2020-08-24";
  return {limit: growth ? .20 : .10, minimum: 100, step: 100};
}
function charge(account, gross, options, selling, date) {
  const commission = Math.max(options.minCommission, gross * options.commission);
  const stamp = selling ? gross * (date < "2023-08-28" ? .001 : .0005) : 0;
  const cost = commission + stamp + gross * options.slippage;
  account.fees += cost;
  return cost;
}
function buy(account, bar, rules, options) {
  const {cash} = account, price = bar.open;
  // Both the minimum and the proportional commission must fit in available cash.
  const budget = Math.min((cash - options.minCommission) / (1 + options.slippage),
                          cash / (1 + options.slippage + options.commission));
  const qty = Math.floor((budget / price + 1e-10) / rules.step) * rules.step;
  if (qty < rules.minimum) return null;
  const gross = qty * price, fees = charge(account, gross, options, false, bar.date);
  account.cash -= gross + fees;
  account.shares = qty;
  return {date: bar.date, side: "买入", price, shares: qty, fees};
}
function sell(account, bar, options, qty) {
  const gross = qty * bar.open;
  const fees = charge(account, gross, options, true, bar.date);
  account.cash += gross - fees;
  account.shares -= qty;
  return {date: bar.date, side: "卖出", price: bar.open, shares: qty, fees};
}
function credit(account, event) {
  if (!event || !account.shares) return;

  // Gross cash entitlements are kept separately and never fund new purchases.
  account.dividends += account.shares * event.cashPerShare;
  if (!event.bonusPerShare) return;
  if (!validDate(event.listingDate) || event.listingDate < event.date)
    throw Error(event.date + " 送转股份上市日未经核实，本区间无法结算");
  const exact = account.shares * event.bonusPerShare, qty = Math.round(exact);
  if (Math.abs(exact-qty)>1e-8) throw Error(event.date + " 零碎送股分配结果未知");
  account.shares += qty;
  account.locked.push({qty, until:event.listingDate});
}
function netValue(account, close) {
  const value = account.cash + account.shares * close + account.dividends;
  if (account.cash < -1e-6 || !Number.isFinite(value) || value < 0)
    throw Error("Portfolio accounting invariant violated");
  return value;
}
function run(raw, opts={}) {
  const bars = normalize(raw);
  const capital = Number(opts.capital ?? 100000);
  const options = {commission: Number(opts.commission ?? .0003), slippage: Number(opts.slippage ?? .001),
                   minCommission: Number(opts.minCommission ?? 5)};
  const strategy = opts.strategy ?? "ma", symbol = String(opts.symbol ?? "");
  const start = opts.startIndex ?? 1;
  if (bars.length < 25 || !Number.isInteger(start) || start < 1 || bars.length - start < 20)
    throw Error("Invalid evaluation period (at least 25 bars, 20 evaluation bars)");
  if (!["ma","break","revert"].includes(strategy)) throw Error("Unknown strategy");
  if (![capital,...Object.values(options)].every(Number.isFinite) || capital <= 0 ||
      options.commission < 0 || options.commission >= .1 || options.slippage < 0 ||
      options.slippage >= .1 || options.minCommission < 0) throw Error("Invalid parameters");

  const events = distributions(opts.actions ?? [], bars);
  const fresh = () => ({cash: capital, shares: 0, dividends: 0, fees: 0, locked: []});
  const account = fresh(), benchmark = fresh(), signals = [], equity = [capital], records = [];
  const stats = {signals: 0, insufficientCash: 0, zeroVolume: 0, limitBlocked: 0};
  let entry = -1, peak = capital, maxdd = 0, scale = 1;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i], event = events.get(b.date);
    const prev = i ? bars[i-1].close : b.open;
    const reference = event && i ? (prev - event.cashPerShare) / (1 + event.bonusPerShare) : prev;
    if (reference <= 0) throw Error("无效除权参考价：" + b.date);
    if (event && i) scale *= prev / reference;
    if (i >= start) {
      credit(account, event);
      credit(benchmark, event);
      const rules = marketRules(symbol, b.date);
      const tick = x => Math.round((x + 1e-9) * 100);
      const atUp = tick(b.open) >= tick(reference * (1 + rules.limit));
      const atDown = tick(b.open) <= tick(reference * (1 - rules.limit));
      const want = desired(signals, i-1, strategy);
      // Whole-day volume is used solely to identify a no-trade session.
      if (!benchmark.shares && b.volume > 0 && !atUp) buy(benchmark, b, rules, options);
      if (account.shares && (strategy === "revert" ? i-entry >= 5 : !want)) {
        if (!b.volume) stats.zeroVolume++;
        else if (atDown) stats.limitBlocked++;
        else if (i > entry) {
          account.locked = account.locked.filter(lot => lot.until > b.date);
          const available = account.shares - account.locked.reduce((n,lot)=>n+lot.qty,0);
          if (available) records.push(sell(account, b, options, available));
        }
      } else if (!account.shares && want) {
        stats.signals++;
        if (!b.volume) stats.zeroVolume++;
        else if (atUp) stats.limitBlocked++;
        else {
          const trade = buy(account, b, rules, options);
          if (trade) { records.push(trade); entry = i; }
          else stats.insufficientCash++;
        }
      }
      const value = netValue(account, b.close);
      equity.push(value);
      peak = Math.max(peak, value);
      maxdd = Math.min(maxdd, value / peak - 1);
    }
    signals.push({close: b.close * scale, high: b.high * scale});
  }
  const last = equity.at(-1);
  const years = (Date.parse(bars.at(-1).date) - Date.parse(bars[start-1].date)) / 86400000 / 365.25;
  const daily = equity.slice(1).map((v, i) => v / equity[i] - 1);
  const mean = daily.reduce((a, b) => a + b, 0) / daily.length;
  const variance = daily.reduce((a, b) => a + (b - mean)**2, 0) / (daily.length - 1);
  return {returnRate: last/capital-1, benchmark: netValue(benchmark, bars.at(-1).close)/capital-1,
    maxDrawdown: maxdd, annualized: last === 0 ? -1 : (last/capital)**(1/years)-1,
    sharpe: variance > 0 ? mean/Math.sqrt(variance)*Math.sqrt(252) : null, records, equity, stats,
    fees: account.fees, dividends: account.dividends, endingCash: account.cash, endingShares: account.shares,
    endingEquity: last, firstTradeDate: bars[start].date, baselineDate: bars[start-1].date,
    evaluationBars: bars.length-start,
    assumptions: "未复权开盘价成交，滑点计入成本；普通板块限价近似，开盘触限按无法排队成交处理。现金分配税前单列、不复投；未覆盖历史ST、特殊限价及配股。"};
}
root.AshareBacktest = {run, normalize, validDate};
})(typeof globalThis !== "undefined" ? globalThis : this);
