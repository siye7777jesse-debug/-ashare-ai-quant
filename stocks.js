/* Current publicly listed A-share names, independent of historical bar data. */
(function(root){
"use strict";
const MARKETS="m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048";
function normalize(input,min=1){
 const rows=Array.isArray(input)?input:input&&input.stocks;
 if(!Array.isArray(rows))throw Error("股票目录格式错误");
 const seen=new Map();
 for(const row of rows){
  const code=String(row?.code??"").trim(),name=String(row?.name??"").trim();
  if(/^\d{6}$/.test(code)&&name&&name!=="-"&&name.length<=40)seen.set(code,{code,name});
 }
 if(seen.size<min)throw Error("股票目录数量不足（"+seen.size+"），拒绝使用不完整的名单");
 return [...seen.values()].sort((a,b)=>a.code.localeCompare(b.code));
}
function matches(rows,query,max=15){
 const key=String(query??"").trim().toLowerCase();
 if(!key||!Array.isArray(rows))return [];
 const score=x=>{
  const n=x.name.toLowerCase(),c=x.code;
  if(c===key||n===key)return 0;
  if(c.startsWith(key))return 1;
  if(n.startsWith(key))return 2;
  if(c.includes(key))return 3;
  if(n.includes(key))return 4;
  return 99;
 };
 return rows.map(x=>({x,s:score(x)})).filter(v=>v.s<99).sort((a,b)=>a.s-b.s||a.x.code.localeCompare(b.x.code)).slice(0,max).map(v=>v.x);
}
async function fetchPublic(){
 const seen = new Map(), pz=100;
 let expected;
 for(let pn=1;pn<=150;pn++){
  const args=new URLSearchParams({pn:String(pn),pz:String(pz),po:"1",np:"1",fltt:"2",invt:"2",fid:"f12",fs:MARKETS,fields:"f12,f14"});
  const response=await fetch("https://push2.eastmoney.com/api/qt/clist/get?"+args,{signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error("公开股票目录 HTTP "+response.status);
  const {data}=await response.json();
  expected ??= Number(data?.total);
  if(!Number.isInteger(expected)||expected<3500||expected>15000||expected!==Number(data?.total))throw Error("股票目录数量无效或已变化");
  const page=Object.values(data.diff||{});
  if(!page.length)throw Error("公开目录分页不完整");
  for(const row of page){
   const [item]=normalize([{code:row.f12,name:row.f14}]);
   if(seen.has(item.code))throw Error("目录分页重复");
   seen.set(item.code,item);
  }
  if(seen.size===expected)return [...seen.values()];
  if(seen.size>expected)break;
 }
 throw Error("公开目录数量与返回总数不符");
}
let loading;
async function load(){
 if(!loading)loading=(async()=>{
  try{
   const response=await fetch("./data/stocks.json",{cache:"no-cache"});
   if(!response.ok)throw Error("网站股票目录暂未生成");
   const json=await response.json();
   return {stocks:normalize(json,3500),scope:json.scope,source:json.source||"网站公开目录",updated:json.fetched_at||""};
  }catch(localError){
   try{return {stocks:await fetchPublic(),scope:"currently-listed",source:"东方财富公开实时股票列表",updated:""}}
   catch(remoteError){throw Error("股票名称目录暂不可用（"+localError.message+"；"+remoteError.message+"）。仍可输入6位股票代码。")}
  }
 })().catch(err=>{loading=null;throw err});
 return loading;
}
root.AshareStocks={normalize,matches,fetchPublic,load};
})(typeof globalThis!=="undefined"?globalThis:this);
