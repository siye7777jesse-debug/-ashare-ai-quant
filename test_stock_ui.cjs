const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const ctx={devicePixelRatio:2};
vm.runInNewContext(fs.readFileSync("stocks.js","utf8"),ctx);
vm.runInNewContext(fs.readFileSync("compare_charts.js","utf8"),ctx);
const stocks=ctx.AshareStocks,charts=ctx.AshareCompareCharts;
const records=Array.from({length:1250},(_,i)=>({code:String(i).padStart(6,"0"),name:"测试股票"+i}));
records[8]={code:"600838",name:"上海九百"};
records[9]={code:"000759",name:"中百集团"};
records[10]={code:"300308",name:"中际旭创"};
const rows=stocks.normalize({stocks:records},1000);
assert.equal(rows.length,1249); // Duplicate code 000759 must be de-duplicated
assert.equal(stocks.matches(rows,"上海九百")[0].code,"600838");
assert.equal(stocks.matches(rows,"九百")[0].name,"上海九百");
assert.equal(stocks.matches(rows,"300308")[0].name,"中际旭创");
assert.equal(stocks.matches(rows,"不存在").length,0);
assert.throws(()=>stocks.normalize(records.slice(0,2),1000),/数量不足/);
const valid=[
 {name:"上海九百",symbol:"600838",inSample:{returnRate:.32},outSample:{returnRate:-.11,benchmark:.12,maxDrawdown:-.28}},
 {name:"中际旭创",symbol:"300308",inSample:{returnRate:-.12},outSample:{returnRate:.34,benchmark:.23,maxDrawdown:-.15}},
 {name:"中百集团",symbol:"000759",inSample:{returnRate:.06},outSample:{returnRate:0,benchmark:-.05,maxDrawdown:0}},
 {name:"其他",symbol:"601138",error:"数据接口不可用"}
];
const c=charts.build(valid,"return");
assert.equal(c.data.length,3);
assert.ok(c.min<0);assert.ok(c.max>.34);
assert.equal(c.data[0].series[0].value,-.11);
assert.equal(charts.build(valid,"split").data[1].series[0].value,-.12);
assert.equal(charts.build(valid,"drawdown").data[0].series[0].value,-.28);
const draws=[];
const context={setTransform(){},clearRect(){},fillRect(...p){draws.push(p)},fillText(...p){draws.push(p)},beginPath(){},moveTo(){},lineTo(){},stroke(){}};
const canvas={parentElement:{clientWidth:380},style:{},getContext(){return context},width:0,height:0};
for(const kind of ["return","split","drawdown"]){const chart=charts.draw(canvas,valid,kind);assert.equal(chart.data.length,3);assert.ok(canvas.height>=2*(3*67+85))}
assert.ok(draws.length>5);
const empty=charts.draw(canvas,valid.filter(x=>x.error),"return");assert.equal(empty.data.length,0);
console.log("Stock name search and comparison-chart regressions passed");
