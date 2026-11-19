/* Responsive, dependency-free canvas charts for A-share strategy comparisons. */
(function(root){
"use strict";
function seriesFor(entry,kind){
 if(kind==="return")return [
  {label:"样本外策略",value:entry.outSample.returnRate,color:"#6aa8ff"},
  {label:"同期买入持有",value:entry.outSample.benchmark,color:"#4bd1bd"}
 ];
 if(kind==="split")return [
  {label:"样本内策略",value:entry.inSample.returnRate,color:"#d3a5ff"},
  {label:"样本外策略",value:entry.outSample.returnRate,color:"#6aa8ff"}
 ];
 if(kind==="drawdown")return [
  {label:"样本外最大回撤",value:entry.outSample.maxDrawdown,color:"#f3a66d"}
 ];
 throw Error("Unknown chart type");
}
function build(entries,kind){
 const rows=entries.filter(x=>!x.error);
 const data=rows.map(x=>({name:x.name||x.symbol,code:x.symbol,series:seriesFor(x,kind)}));
 const values=data.flatMap(x=>x.series.map(s=>s.value));
 let min=Math.min(0,...values),max=Math.max(0,...values);
 if(max-min<.00001){min=Math.min(min,-.05);max=Math.max(max,.05)}
 const pad=(max-min)*.09;
 return {data,min:min-pad,max:max+pad,kind};
}
function draw(canvas,entries,kind){
 if(!canvas||typeof canvas.getContext!=="function")throw Error("Chart canvas unavailable");
 const report=build(entries,kind),width=Math.max(280,Math.round(canvas.parentElement?.clientWidth||canvas.clientWidth||350)),
 height=Math.max(146,report.data.length*67+85);
 const dpr=Math.min(2,root.devicePixelRatio||1);
 canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
 canvas.style.width="100%";canvas.style.height=height+"px";
 const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
 const left=width<400?99:135,right=44,top=60,plotWidth=width-left-right;
 const x=v=>left+(v-report.min)/(report.max-report.min)*plotWidth;
 ctx.font="12px system-ui";ctx.textBaseline="middle";
 if(!report.data.length){ctx.fillStyle="#a9b8cb";ctx.textAlign="center";ctx.fillText("暂无成功回测的股票，无法绘图",width/2,72);return report}
 const legend=report.data[0].series,legendWidth=width/legend.length;
 legend.forEach((item,i)=>{const lx=12+i*legendWidth;ctx.fillStyle=item.color;ctx.fillRect(lx,15,10,10);ctx.fillStyle="#d1dbeb";ctx.textAlign="left";ctx.fillText(item.label,lx+15,20)});
 for(let i=0;i<=4;i++){
  const tick=report.min+(report.max-report.min)*i/4,px=x(tick);
  ctx.strokeStyle="#304155";ctx.lineWidth=.8;ctx.beginPath();ctx.moveTo(px,top-5);ctx.lineTo(px,height-18);ctx.stroke();
  ctx.fillStyle="#a8bbd1";ctx.textAlign="center";ctx.font="10px system-ui";ctx.fillText((tick*100).toFixed(0)+"%",px,height-8)
 }
 ctx.strokeStyle="#c7d6e8";ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(x(0),top-5);ctx.lineTo(x(0),height-18);ctx.stroke();
 report.data.forEach((entry,i)=>{
  const y=top+i*67,label=entry.name.length>7?entry.name.slice(0,7)+"…":entry.name;
  ctx.fillStyle="#e5edf8";ctx.textAlign="left";ctx.font="12px system-ui";ctx.fillText(label,5,y+14);
  ctx.fillStyle="#a9b8cb";ctx.font="10px system-ui";ctx.fillText(entry.code,5,y+29);
  const n=entry.series.length,barHeight=n===1?17:12;
  entry.series.forEach((s,j)=>{
   const by=y+6+j*(barHeight+6),zero=x(0),tip=x(s.value);
   ctx.fillStyle=s.color;ctx.fillRect(Math.min(zero,tip),by,Math.max(1,Math.abs(tip-zero)),barHeight);
   ctx.font="10px system-ui";ctx.fillStyle="#eaf0f8";ctx.textAlign=s.value<0?"right":"left";
   let lx=s.value<0?tip-3:tip+3;
   lx=Math.min(width-2,Math.max(left-2,lx));
   ctx.fillText((s.value*100).toFixed(1)+"%",lx,by+barHeight/2)
  })
 });
 return report;
}
root.AshareCompareCharts={build,draw};
})(typeof globalThis!=="undefined"?globalThis:this);
