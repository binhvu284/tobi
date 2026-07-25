import{p as rt}from"./chunk-JWPE2WC7-B8UJKNXz.js";import{L as nt,aC as it,M as ot,aD as st,P as lt,aF as ct,a as d,ai as G,O as ut,m as gt,aB as dt,ap as pt,w as ht,n as ft,F as mt}from"./mermaid.core-plhEZER9.js";import{p as vt}from"./cynefin-VYW2F7L2-B-uvPj5p.js";import"./transform-C7htkucW.js";import{d as J}from"./arc-DtxbFlka.js";import{o as xt}from"./ordinal-BQ3KlzSu.js";import{h as T,E as B,c as St}from"./step-CWvwoXpJ.js";import"./index-BOEpdMOI.js";import"./Architecture-DyWdn8Na.js";import"./crosshair-Vy-Aen49.js";import"./minimize-2-BmO5JTRZ.js";import"./maximize-2-CAWbYK3j.js";import"./square-terminal-_Etjq1qW.js";import"./string-CY7Nc7fS.js";import"./init-BFKUnIhM.js";function yt(t,n){return n<t?-1:n>t?1:n>=t?0:NaN}function wt(t){return t}function At(){var t=wt,n=yt,y=null,b=T(0),l=T(B),p=T(0);function i(e){var r,s=(e=St(e)).length,h,w,$=0,f=new Array(s),o=new Array(s),D=+b.apply(this,arguments),M=Math.min(B,Math.max(-B,l.apply(this,arguments)-D)),k,L=Math.min(Math.abs(M)/s,p.apply(this,arguments)),u=L*(M<0?-1:1),A;for(r=0;r<s;++r)(A=o[f[r]=r]=+t(e[r],r,e))>0&&($+=A);for(n!=null?f.sort(function(z,m){return n(o[z],o[m])}):y!=null&&f.sort(function(z,m){return y(e[z],e[m])}),r=0,w=$?(M-s*u)/$:0;r<s;++r,D=k)h=f[r],A=o[h],k=D+(A>0?A*w:0)+u,o[h]={data:e[h],index:r,value:A,startAngle:D,endAngle:k,padAngle:L};return o}return i.value=function(e){return arguments.length?(t=typeof e=="function"?e:T(+e),i):t},i.sortValues=function(e){return arguments.length?(n=e,y=null,i):n},i.sort=function(e){return arguments.length?(y=e,n=null,i):y},i.startAngle=function(e){return arguments.length?(b=typeof e=="function"?e:T(+e),i):b},i.endAngle=function(e){return arguments.length?(l=typeof e=="function"?e:T(+e),i):l},i.padAngle=function(e){return arguments.length?(p=typeof e=="function"?e:T(+e),i):p},i}var Ct=mt.pie,I={sections:new Map,showData:!1},P=I.sections,V=I.showData,$t=structuredClone(Ct),Dt=d(()=>structuredClone($t),"getConfig"),Tt=d(()=>{P=new Map,V=I.showData,ft()},"clear"),bt=d(({label:t,value:n})=>{if(n<0)throw new Error(`"${t}" has invalid value: ${n}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);P.has(t)||(P.set(t,n),G.debug(`added new section: ${t}, with value: ${n}`))},"addSection"),kt=d(()=>P,"getSections"),Et=d(t=>{V=t},"setShowData"),Mt=d(()=>V,"getShowData"),K={getConfig:Dt,clear:Tt,setDiagramTitle:ct,getDiagramTitle:lt,setAccTitle:st,getAccTitle:ot,setAccDescription:it,getAccDescription:nt,addSection:bt,getSections:kt,setShowData:Et,getShowData:Mt},zt=d((t,n)=>{rt(t,n),n.setShowData(t.showData),t.sections.map(n.addSection)},"populateDb"),Ft={parse:d(async t=>{const n=await vt("pie",t);G.debug(n),zt(n,K)},"parse")},Lt=d(t=>`
  .pieCircle{
    stroke: ${t.pieStrokeColor};
    stroke-width : ${t.pieStrokeWidth};
    opacity : ${t.pieOpacity};
  }
  .pieCircle.highlighted{
    scale: 1.05;
    opacity: 1;
  }
  .pieCircle.highlightedOnHover:hover{
    transition-duration: 250ms;
    scale: 1.05;
    opacity: 1;
  }
  .pieOuterCircle{
    stroke: ${t.pieOuterStrokeColor};
    stroke-width: ${t.pieOuterStrokeWidth};
    fill: none;
  }
  .pieTitleText {
    text-anchor: middle;
    font-size: ${t.pieTitleTextSize};
    fill: ${t.pieTitleTextColor};
    font-family: ${t.fontFamily};
  }
  .slice {
    font-family: ${t.fontFamily};
    fill: ${t.pieSectionTextColor};
    font-size:${t.pieSectionTextSize};
    // fill: white;
  }
  .legend text {
    fill: ${t.pieLegendTextColor};
    font-family: ${t.fontFamily};
    font-size: ${t.pieLegendTextSize};
  }
`,"getStyles"),Rt=Lt,Ot=d(t=>{const n=[...t.values()].reduce((l,p)=>l+p,0),y=[...t.entries()].map(([l,p])=>({label:l,value:p})).filter(l=>l.value/n*100>=1);return At().value(l=>l.value).sort(null)(y)},"createPieArcs"),Pt=d((t,n,y,b)=>{var q;G.debug(`rendering pie chart
`+t);const l=b.db,p=ut(),i=gt(l.getConfig(),p.pie),e=40,r=18,s=4,h=450,w=h,$=dt(n),f=$.append("g");f.attr("transform","translate("+w/2+","+h/2+")");const{themeVariables:o}=p;let[D]=pt(o.pieOuterStrokeWidth);D??(D=2);const M=i.legendPosition,k=i.textPosition,L=i.donutHole>0&&i.donutHole<=.9?i.donutHole:0,u=Math.min(w,h)/2-e,A=J().innerRadius(L*u).outerRadius(u),z=J().innerRadius(u*k).outerRadius(u*k),m=f.append("g");m.append("circle").attr("cx",0).attr("cy",0).attr("r",u+D/2).attr("class","pieOuterCircle");const R=l.getSections(),Q=Ot(R),Y=[o.pie1,o.pie2,o.pie3,o.pie4,o.pie5,o.pie6,o.pie7,o.pie8,o.pie9,o.pie10,o.pie11,o.pie12];let W=0;R.forEach(a=>{W+=a});const U=Q.filter(a=>(a.data.value/W*100).toFixed(0)!=="0"),H=xt(Y).domain([...R.keys()]);m.selectAll("mySlices").data(U).enter().append("path").attr("d",A).attr("fill",a=>H(a.data.label)).attr("class",a=>{let c="pieCircle";return i.highlightSlice==="hover"?c+=" highlightedOnHover":i.highlightSlice===a.data.label&&(c+=" highlighted"),c}),m.selectAll("mySlices").data(U).enter().append("text").text(a=>(a.data.value/W*100).toFixed(0)+"%").attr("transform",a=>"translate("+z.centroid(a)+")").style("text-anchor","middle").attr("class","slice");const tt=f.append("text").text(l.getDiagramTitle()).attr("x",0).attr("y",-400/2).attr("class","pieTitleText"),F=[...R.entries()].map(([a,c])=>({label:a,value:c})),C=f.selectAll(".legend").data(F).enter().append("g").attr("class","legend");C.append("rect").attr("width",r).attr("height",r).style("fill",a=>H(a.label)).style("stroke",a=>H(a.label)),C.append("text").attr("x",r+s).attr("y",r-s).text(a=>l.getShowData()?`${a.label} [${a.value}]`:a.label);const E=Math.max(...C.selectAll("text").nodes().map(a=>(a==null?void 0:a.getBoundingClientRect().width)??0));let O=h,N=w+e;const g=r+s,_=F.length*g;switch(M){case"center":C.attr("transform",(a,c)=>{const v=g*F.length/2,x=-E/2-(r+s),S=c*g-v;return"translate("+x+","+S+")"});break;case"top":O+=_,C.attr("transform",(a,c)=>{const v=u,x=-E/2-(r+s),S=c*g-v;return`translate(${x}, ${S})`}),m.attr("transform",()=>`translate(0, ${_+g})`);break;case"bottom":O+=_,C.attr("transform",(a,c)=>{const v=-u-g,x=-E/2-(r+s),S=c*g-v;return"translate("+x+","+S+")"});break;case"left":N+=r+s+E,C.attr("transform",(a,c)=>{const v=g*F.length/2,x=-u-(r+s),S=c*g-v;return"translate("+x+","+S+")"}),m.attr("transform",()=>`translate(${E+r+s}, 0)`);break;case"right":default:N+=r+s+E,C.attr("transform",(a,c)=>{const v=g*F.length/2,x=12*r,S=c*g-v;return"translate("+x+","+S+")"});break}const j=((q=tt.node())==null?void 0:q.getBoundingClientRect().width)??0,et=w/2-j/2,at=w/2+j/2,X=Math.min(0,et),Z=Math.max(N,at)-X;$.attr("viewBox",`${X} 0 ${Z} ${O}`),ht($,O,Z,i.useMaxWidth)},"draw"),Wt={draw:Pt},te={parser:Ft,db:K,renderer:Wt,styles:Rt};export{te as diagram};
