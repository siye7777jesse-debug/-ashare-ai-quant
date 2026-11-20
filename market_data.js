/* Shared by single-stock and batch research. Only closed, unadjusted bars can fill orders. */
(function(root){
"use strict";
const validDate = d => root.AshareBacktest.validDate(d);
function lastClosedDate(now = Date.now()) {
  const local = new Date(now + 8 * 3600000);
  if (local.getUTCHours() < 16) local.setUTCDate(local.getUTCDate() - 1);
  return local.toISOString().slice(0, 10);
}
async function json(url) {
  const r = await fetch(url, {cache:"no-cache", signal:AbortSignal.timeout(15000)});
  if (!r.ok) throw Error("HTTP " + r.status);
  return r.json();
}
async function withFallback(local, online) {
  try { return await local(); }
  catch (error) {
    try { return await online(); }
    catch (remote) { throw Error("缓存：" + error.message + "。公开接口：" + remote.message); }
  }
}
function numeric(field) {
  if (typeof field !== "string" || !field.trim() || !Number.isFinite(Number(field))) throw Error("日线数值无效");
  return Number(field);
}
function publicBars(data, code) {
  if (data?.code !== code || data.market !== (code.startsWith("6")?1:0) || !Array.isArray(data.klines)) throw Error("行情代码或格式错误");
  return data.klines.map(line => {
    const fields = line.split(",");
    if (fields.length !== 6) throw Error("日线字段数错误");
    const [open,close,high,low,volume] = fields.slice(1).map(numeric);
    return {date:fields[0], open, close, high, low, volume};
  });
}
function publicEvents(payload, code, begin, end) {
  const result = payload?.result;
  if (payload?.success !== true || result?.pages !== 1 || !result.data?.length) throw Error("分配记录不完整");
  const events = [];
  for (const r of result.data) {
    if (r.SECURITY_CODE !== code) throw Error("分配记录与代码不符");
    if (r.ASSIGN_PROGRESS !== "实施分配") continue;
    const date = r.EX_DIVIDEND_DATE?.slice(0,10);
    if (!validDate(date)) throw Error("缺少已实施分配的除权日期");
    if (date < begin || date > end) continue;
    const cashPerShare = Number(r.PRETAX_BONUS_RMB ?? 0)/10, bonusPerShare = Number(r.BONUS_IT_RATIO ?? 0)/10;
    if (![cashPerShare,bonusPerShare].every(x=>Number.isFinite(x)&&x>=0) || cashPerShare+bonusPerShare <= 0)
      throw Error("分配数量无效：" + date);
    events.push({date,cashPerShare,bonusPerShare});
  }
  return events;
}
async function load(code, begin, requestedEnd) {
  if (!root.AshareStocks.isStockCode(code) || !validDate(begin) || !validDate(requestedEnd)) throw Error("请输入支持的A股代码和有效日期");
  const end = [requestedEnd,lastClosedDate()].sort()[0];
  if (begin > end) throw Error("日期区间内没有已收盘日线");
  const history = await withFallback(async()=>{
    const data = await json("./data/" + code + ".json");
    if (data.symbol !== code || data.adjustment !== "none" || !Array.isArray(data.bars)) throw Error("行情代码或复权口径错误");
    const vintage = Date.parse(data.fetched_at);
    if (!Number.isFinite(vintage) || begin < "2018-01-01" || end > lastClosedDate(vintage))
      throw Error("缓存未覆盖查询区间");
    return {rows:root.AshareBacktest.normalize(data.bars), source:data.source, vintage:data.fetched_at};
  }, async()=>{
    const args = new URLSearchParams({secid:(code.startsWith("6")?"1.":"0.")+code,klt:"101",fqt:"0",
      beg:begin.replaceAll("-",""),end:end.replaceAll("-",""),fields1:"f1,f2,f3,f4,f5,f6",fields2:"f51,f52,f53,f54,f55,f56"});
    const p = await json("https://push2his.eastmoney.com/api/qt/stock/kline/get?"+args);
    const rows = root.AshareBacktest.normalize(publicBars(p.data,code));
    if (rows.some(b=>b.date<begin || b.date>end)) throw Error("返回行情超出已收盘日期区间");
    return {rows,source:"东方财富公开日线",vintage:new Date().toISOString()};
  });
  const rows = history.rows.filter(b=>b.date>=begin && b.date<=end);
  if (rows.length < 25) throw Error("所选区间不足25条有效日线");
  const first = rows[0].date, last = rows.at(-1).date;
  const actions = await withFallback(async()=>{
    const p = await json("./data/actions/"+code+".json");
    if (p.symbol!==code || !validDate(p.start) || !validDate(p.end) || p.start>first || p.end<last || !Array.isArray(p.events))
      throw Error("分配缓存未覆盖行情");
    return p.events.filter(e=>e.date>=first && e.date<=last);
  }, async()=>{
    const args = new URLSearchParams({reportName:"RPT_SHAREBONUS_DET",columns:"ALL",
      filter:'(SECURITY_CODE="'+code+'")',pageSize:"100",sortColumns:"EX_DIVIDEND_DATE",sortTypes:"-1"});
    return publicEvents(await json("https://datacenter-web.eastmoney.com/api/data/v1/get?"+args),code,first,last);
  });
  return {rows, actions, info: history.source+"，采集于 "+history.vintage.slice(0,10)+"；已实施分配 "+actions.length+" 条"};
}
root.AshareMarketData = {load, lastClosedDate, publicBars, publicEvents};
})(typeof globalThis !== "undefined" ? globalThis : this);
