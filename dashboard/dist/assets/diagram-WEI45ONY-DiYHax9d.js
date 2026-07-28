import{p as k}from"./chunk-JWPE2WC7-DXgiH_F6.js";import{aC as F,L as R,P as I,aF as D,M as E,aD as _,a as c,aB as P,n as z,m as y,N as C,F as G,ai as B,$ as W,w as V}from"./mermaid.core-BegXshz1.js";import{p as H}from"./cynefin-VYW2F7L2-NWNDdSla.js";import"./index-36UQyGQS.js";import"./Architecture-BerrLzyB.js";import"./crosshair-DgPqWi6E.js";import"./minimize-2-B1KcKQPS.js";import"./maximize-2-BRnvmGiJ.js";import"./square-terminal-D0w8_46j.js";import"./transform-C7htkucW.js";import"./string-CY7Nc7fS.js";import"./step-CWvwoXpJ.js";var x={showLegend:!0,ticks:5,max:null,min:0,graticule:"circle"},w={axes:[],curves:[],options:x},g=structuredClone(w),j=G.radar,N=c(()=>y({...j,...C().radar}),"getConfig"),b=c(()=>g.axes,"getAxes"),U=c(()=>g.curves,"getCurves"),X=c(()=>g.options,"getOptions"),Y=c(a=>{g.axes=a.map(t=>({name:t.name,label:t.label??t.name}))},"setAxes"),Z=c(a=>{g.curves=a.map(t=>({name:t.name,label:t.label??t.name,entries:q(t.entries)}))},"setCurves"),q=c(a=>{if(a[0].axis==null)return a.map(e=>e.value);const t=b();if(t.length===0)throw new Error("Axes must be populated before curves for reference entries");return t.map(e=>{const r=a.find(n=>{var s;return((s=n.axis)==null?void 0:s.$refText)===e.name});if(r===void 0)throw new Error("Missing entry for axis "+e.label);return r.value})},"computeCurveEntries"),J=c(a=>{var e,r,n,s,l;const t=a.reduce((o,i)=>(o[i.name]=i,o),{});g.options={showLegend:((e=t.showLegend)==null?void 0:e.value)??x.showLegend,ticks:((r=t.ticks)==null?void 0:r.value)??x.ticks,max:((n=t.max)==null?void 0:n.value)??x.max,min:((s=t.min)==null?void 0:s.value)??x.min,graticule:((l=t.graticule)==null?void 0:l.value)??x.graticule}},"setOptions"),K=c(()=>{z(),g=structuredClone(w)},"clear"),$={getAxes:b,getCurves:U,getOptions:X,setAxes:Y,setCurves:Z,setOptions:J,getConfig:N,clear:K,setAccTitle:_,getAccTitle:E,setDiagramTitle:D,getDiagramTitle:I,getAccDescription:R,setAccDescription:F},Q=c(a=>{k(a,$);const{axes:t,curves:e,options:r}=a;$.setAxes(t),$.setCurves(e),$.setOptions(r)},"populate"),tt={parse:c(async a=>{const t=await H("radar",a);B.debug(t),Q(t)},"parse")},et=c((a,t,e,r)=>{const n=r.db,s=n.getAxes(),l=n.getCurves(),o=n.getOptions(),i=n.getConfig(),d=n.getDiagramTitle(),u=P(t),p=at(u,i),m=o.max??Math.max(...l.map(f=>Math.max(...f.entries))),h=o.min,v=Math.min(i.width,i.height)/2;rt(p,s,v,o.ticks,o.graticule),nt(p,s,v,i),A(p,s,l,h,m,o.graticule,i),T(p,l,o.showLegend,i),p.append("text").attr("class","radarTitle").text(d).attr("x",0).attr("y",-i.height/2-i.marginTop)},"draw"),at=c((a,t)=>{const e=t.width+t.marginLeft+t.marginRight,r=t.height+t.marginTop+t.marginBottom,n={x:t.marginLeft+t.width/2,y:t.marginTop+t.height/2};return V(a,r,e,t.useMaxWidth??!0),a.attr("viewBox",`0 0 ${e} ${r}`).attr("overflow","visible"),a.append("g").attr("transform",`translate(${n.x}, ${n.y})`)},"drawFrame"),rt=c((a,t,e,r,n)=>{if(n==="circle")for(let s=0;s<r;s++){const l=e*(s+1)/r;a.append("circle").attr("r",l).attr("class","radarGraticule")}else if(n==="polygon"){const s=t.length;for(let l=0;l<r;l++){const o=e*(l+1)/r,i=t.map((d,u)=>{const p=2*u*Math.PI/s-Math.PI/2,m=o*Math.cos(p),h=o*Math.sin(p);return`${m},${h}`}).join(" ");a.append("polygon").attr("points",i).attr("class","radarGraticule")}}},"drawGraticule"),nt=c((a,t,e,r)=>{const n=t.length;for(let s=0;s<n;s++){const l=t[s].label,o=2*s*Math.PI/n-Math.PI/2,i=Math.cos(o),d=Math.sin(o);a.append("line").attr("x1",0).attr("y1",0).attr("x2",e*r.axisScaleFactor*i).attr("y2",e*r.axisScaleFactor*d).attr("class","radarAxisLine");const u=i>.01?"start":i<-.01?"end":"middle",p=d>.01?"hanging":d<-.01?"auto":"central",m=4;a.append("text").text(l).attr("x",e*r.axisLabelFactor*i+m*i).attr("y",e*r.axisLabelFactor*d+m*d).attr("text-anchor",u).attr("dominant-baseline",p).attr("class","radarAxisLabel")}},"drawAxes");function A(a,t,e,r,n,s,l){const o=t.length,i=Math.min(l.width,l.height)/2;e.forEach((d,u)=>{if(d.entries.length!==o)return;const p=d.entries.map((m,h)=>{const v=2*Math.PI*h/o-Math.PI/2,f=M(m,r,n,i),S=f*Math.cos(v),O=f*Math.sin(v);return{x:S,y:O}});s==="circle"?a.append("path").attr("d",L(p,l.curveTension)).attr("class",`radarCurve-${u}`):s==="polygon"&&a.append("polygon").attr("points",p.map(m=>`${m.x},${m.y}`).join(" ")).attr("class",`radarCurve-${u}`)})}c(A,"drawCurves");function M(a,t,e,r){const n=Math.min(Math.max(a,t),e);return r*(n-t)/(e-t)}c(M,"relativeRadius");function L(a,t){const e=a.length;let r=`M${a[0].x},${a[0].y}`;for(let n=0;n<e;n++){const s=a[(n-1+e)%e],l=a[n],o=a[(n+1)%e],i=a[(n+2)%e],d={x:l.x+(o.x-s.x)*t,y:l.y+(o.y-s.y)*t},u={x:o.x-(i.x-l.x)*t,y:o.y-(i.y-l.y)*t};r+=` C${d.x},${d.y} ${u.x},${u.y} ${o.x},${o.y}`}return`${r} Z`}c(L,"closedRoundCurve");function T(a,t,e,r){if(!e)return;const n=(r.width/2+r.marginRight)*3/4,s=-(r.height/2+r.marginTop)*3/4,l=20;t.forEach((o,i)=>{const d=a.append("g").attr("transform",`translate(${n}, ${s+i*l})`);d.append("rect").attr("width",12).attr("height",12).attr("class",`radarLegendBox-${i}`),d.append("text").attr("x",16).attr("y",0).attr("class","radarLegendText").text(o.label)})}c(T,"drawLegend");var st={draw:et},ot=c((a,t)=>{let e="";for(let r=0;r<a.THEME_COLOR_LIMIT;r++){const n=a[`cScale${r}`];e+=`
		.radarCurve-${r} {
			color: ${n};
			fill: ${n};
			fill-opacity: ${t.curveOpacity};
			stroke: ${n};
			stroke-width: ${t.curveStrokeWidth};
		}
		.radarLegendBox-${r} {
			fill: ${n};
			fill-opacity: ${t.curveOpacity};
			stroke: ${n};
		}
		`}return e},"genIndexStyles"),it=c(a=>{const t=W(),e=C(),r=y(t,e.themeVariables),n=y(r.radar,a);return{themeVariables:r,radarOptions:n}},"buildRadarStyleOptions"),lt=c(({radar:a}={})=>{const{themeVariables:t,radarOptions:e}=it(a);return`
	.radarTitle {
		font-size: ${t.fontSize};
		color: ${t.titleColor};
		dominant-baseline: hanging;
		text-anchor: middle;
	}
	.radarAxisLine {
		stroke: ${e.axisColor};
		stroke-width: ${e.axisStrokeWidth};
	}
	.radarAxisLabel {
		font-size: ${e.axisLabelFontSize}px;
		color: ${e.axisColor};
	}
	.radarGraticule {
		fill: ${e.graticuleColor};
		fill-opacity: ${e.graticuleOpacity};
		stroke: ${e.graticuleColor};
		stroke-width: ${e.graticuleStrokeWidth};
	}
	.radarLegendText {
		text-anchor: start;
		font-size: ${e.legendFontSize}px;
		dominant-baseline: hanging;
	}
	${ot(t,e)}
	`},"styles"),Ct={parser:tt,db:$,renderer:st,styles:lt};export{Ct as diagram};
