import{L as Pe,aC as Ve,P as ze,aF as Re,M as He,aD as Be,a as l,O as ht,w as Ge,B as q,ai as lt,s as Xe,aA as je,n as Ue,aU as qe}from"./mermaid.core-Cq4IpQQN.js";import{b5 as It,bm as Yt}from"./index-BRLRNnvK.js";import{s as bt}from"./transform-C7htkucW.js";import{t as Ze,b as re,h as ne,j as Qe,i as Ke,d as Je,k as ti,o as ei,l as ii,g as ri,a as se,e as ae,f as oe,s as ce,m as le}from"./time-BsEOgm3j.js";import{a as ni,m as si}from"./min-C8X95urT.js";import{l as ai}from"./linear-COmVcJR4.js";import{R as me,r as oi,d as ke,e as ye,C as ge,n as $t,h as ci}from"./string-CY7Nc7fS.js";import"./Architecture-CifDPdqD.js";import"./crosshair-Cj2AxCVl.js";import"./minimize-2-B0Yx8RSY.js";import"./maximize-2-BGgUBpnk.js";import"./square-terminal-FldFgcnQ.js";import"./step-CWvwoXpJ.js";import"./init-BFKUnIhM.js";import"./defaultLocale-CrowFXzY.js";const li=Math.PI/180,ui=180/Math.PI,Ct=18,pe=.96422,ve=1,xe=.82521,Te=4/29,mt=6/29,be=3*mt*mt,di=mt*mt*mt;function we(t){if(t instanceof it)return new it(t.l,t.a,t.b,t.opacity);if(t instanceof nt)return _e(t);t instanceof me||(t=oi(t));var e=Wt(t.r),i=Wt(t.g),r=Wt(t.b),s=Ft((.2225045*e+.7168786*i+.0606169*r)/ve),m,f;return e===i&&i===r?m=f=s:(m=Ft((.4360747*e+.3850649*i+.1430804*r)/pe),f=Ft((.0139322*e+.0971045*i+.7141733*r)/xe)),new it(116*s-16,500*(m-s),200*(s-f),t.opacity)}function fi(t,e,i,r){return arguments.length===1?we(t):new it(t,e,i,r??1)}function it(t,e,i,r){this.l=+t,this.a=+e,this.b=+i,this.opacity=+r}ke(it,fi,ye(ge,{brighter(t){return new it(this.l+Ct*(t??1),this.a,this.b,this.opacity)},darker(t){return new it(this.l-Ct*(t??1),this.a,this.b,this.opacity)},rgb(){var t=(this.l+16)/116,e=isNaN(this.a)?t:t+this.a/500,i=isNaN(this.b)?t:t-this.b/200;return e=pe*Lt(e),t=ve*Lt(t),i=xe*Lt(i),new me(Ot(3.1338561*e-1.6168667*t-.4906146*i),Ot(-.9787684*e+1.9161415*t+.033454*i),Ot(.0719453*e-.2289914*t+1.4052427*i),this.opacity)}}));function Ft(t){return t>di?Math.pow(t,1/3):t/be+Te}function Lt(t){return t>mt?t*t*t:be*(t-Te)}function Ot(t){return 255*(t<=.0031308?12.92*t:1.055*Math.pow(t,1/2.4)-.055)}function Wt(t){return(t/=255)<=.04045?t/12.92:Math.pow((t+.055)/1.055,2.4)}function hi(t){if(t instanceof nt)return new nt(t.h,t.c,t.l,t.opacity);if(t instanceof it||(t=we(t)),t.a===0&&t.b===0)return new nt(NaN,0<t.l&&t.l<100?0:NaN,t.l,t.opacity);var e=Math.atan2(t.b,t.a)*ui;return new nt(e<0?e+360:e,Math.sqrt(t.a*t.a+t.b*t.b),t.l,t.opacity)}function Vt(t,e,i,r){return arguments.length===1?hi(t):new nt(t,e,i,r??1)}function nt(t,e,i,r){this.h=+t,this.c=+e,this.l=+i,this.opacity=+r}function _e(t){if(isNaN(t.h))return new it(t.l,0,0,t.opacity);var e=t.h*li;return new it(t.l,Math.cos(e)*t.c,Math.sin(e)*t.c,t.opacity)}ke(nt,Vt,ye(ge,{brighter(t){return new nt(this.h,this.c,this.l+Ct*(t??1),this.opacity)},darker(t){return new nt(this.h,this.c,this.l-Ct*(t??1),this.opacity)},rgb(){return _e(this).rgb()}}));function mi(t){return function(e,i){var r=t((e=Vt(e)).h,(i=Vt(i)).h),s=$t(e.c,i.c),m=$t(e.l,i.l),f=$t(e.opacity,i.opacity);return function(b){return e.h=r(b),e.c=s(b),e.l=m(b),e.opacity=f(b),e+""}}}const ki=mi(ci);function yi(t){return t}var _t=1,Nt=2,zt=3,wt=4,ue=1e-6;function gi(t){return"translate("+t+",0)"}function pi(t){return"translate(0,"+t+")"}function vi(t){return e=>+t(e)}function xi(t,e){return e=Math.max(0,t.bandwidth()-e*2)/2,t.round()&&(e=Math.round(e)),i=>+t(i)+e}function Ti(){return!this.__axis}function De(t,e){var i=[],r=null,s=null,m=6,f=6,b=3,C=typeof window<"u"&&window.devicePixelRatio>1?0:.5,L=t===_t||t===wt?-1:1,w=t===wt||t===Nt?"x":"y",N=t===_t||t===zt?gi:pi;function _(D){var X=r??(e.ticks?e.ticks.apply(e,i):e.domain()),R=s??(e.tickFormat?e.tickFormat.apply(e,i):yi),g=Math.max(m,0)+b,M=e.range(),W=+M[0]+C,O=+M[M.length-1]+C,H=(e.bandwidth?xi:vi)(e.copy(),C),z=D.selection?D.selection():D,I=z.selectAll(".domain").data([null]),x=z.selectAll(".tick").data(X,e).order(),k=x.exit(),E=x.enter().append("g").attr("class","tick"),h=x.select("line"),T=x.select("text");I=I.merge(I.enter().insert("path",".tick").attr("class","domain").attr("stroke","currentColor")),x=x.merge(E),h=h.merge(E.append("line").attr("stroke","currentColor").attr(w+"2",L*m)),T=T.merge(E.append("text").attr("fill","currentColor").attr(w,L*g).attr("dy",t===_t?"0em":t===zt?"0.71em":"0.32em")),D!==z&&(I=I.transition(D),x=x.transition(D),h=h.transition(D),T=T.transition(D),k=k.transition(D).attr("opacity",ue).attr("transform",function(v){return isFinite(v=H(v))?N(v+C):this.getAttribute("transform")}),E.attr("opacity",ue).attr("transform",function(v){var p=this.parentNode.__axis;return N((p&&isFinite(p=p(v))?p:H(v))+C)})),k.remove(),I.attr("d",t===wt||t===Nt?f?"M"+L*f+","+W+"H"+C+"V"+O+"H"+L*f:"M"+C+","+W+"V"+O:f?"M"+W+","+L*f+"V"+C+"H"+O+"V"+L*f:"M"+W+","+C+"H"+O),x.attr("opacity",1).attr("transform",function(v){return N(H(v)+C)}),h.attr(w+"2",L*m),T.attr(w,L*g).text(R),z.filter(Ti).attr("fill","none").attr("font-size",10).attr("font-family","sans-serif").attr("text-anchor",t===Nt?"start":t===wt?"end":"middle"),z.each(function(){this.__axis=H})}return _.scale=function(D){return arguments.length?(e=D,_):e},_.ticks=function(){return i=Array.from(arguments),_},_.tickArguments=function(D){return arguments.length?(i=D==null?[]:Array.from(D),_):i.slice()},_.tickValues=function(D){return arguments.length?(r=D==null?null:Array.from(D),_):r&&r.slice()},_.tickFormat=function(D){return arguments.length?(s=D,_):s},_.tickSize=function(D){return arguments.length?(m=f=+D,_):m},_.tickSizeInner=function(D){return arguments.length?(m=+D,_):m},_.tickSizeOuter=function(D){return arguments.length?(f=+D,_):f},_.tickPadding=function(D){return arguments.length?(b=+D,_):b},_.offset=function(D){return arguments.length?(C=+D,_):C},_}function bi(t){return De(_t,t)}function wi(t){return De(zt,t)}var Se={exports:{}};(function(t,e){(function(i,r){t.exports=r()})(It,function(){var i="day";return function(r,s,m){var f=function(L){return L.add(4-L.isoWeekday(),i)},b=s.prototype;b.isoWeekYear=function(){return f(this).year()},b.isoWeek=function(L){if(!this.$utils().u(L))return this.add(7*(L-this.isoWeek()),i);var w,N,_,D,X=f(this),R=(w=this.isoWeekYear(),N=this.$u,_=(N?m.utc:m)().year(w).startOf("year"),D=4-_.isoWeekday(),_.isoWeekday()>4&&(D+=7),_.add(D,i));return X.diff(R,"week")+1},b.isoWeekday=function(L){return this.$utils().u(L)?this.day()||7:this.day(this.day()%7?L:L-7)};var C=b.startOf;b.startOf=function(L,w){var N=this.$utils(),_=!!N.u(w)||w;return N.p(L)==="isoweek"?_?this.date(this.date()-(this.isoWeekday()-1)).startOf("day"):this.date(this.date()-1-(this.isoWeekday()-1)+7).endOf("day"):C.bind(this)(L,w)}}})})(Se);var _i=Se.exports;const Di=Yt(_i);var Ce={exports:{}};(function(t,e){(function(i,r){t.exports=r()})(It,function(){var i={LTS:"h:mm:ss A",LT:"h:mm A",L:"MM/DD/YYYY",LL:"MMMM D, YYYY",LLL:"MMMM D, YYYY h:mm A",LLLL:"dddd, MMMM D, YYYY h:mm A"},r=/(\[[^[]*\])|([-_:/.,()\s]+)|(A|a|Q|YYYY|YY?|ww?|MM?M?M?|Do|DD?|hh?|HH?|mm?|ss?|S{1,3}|z|ZZ?)/g,s=/\d/,m=/\d\d/,f=/\d\d?/,b=/\d*[^-_:/,()\s\d]+/,C={},L=function(g){return(g=+g)+(g>68?1900:2e3)},w=function(g){return function(M){this[g]=+M}},N=[/[+-]\d\d:?(\d\d)?|Z/,function(g){(this.zone||(this.zone={})).offset=function(M){if(!M||M==="Z")return 0;var W=M.match(/([+-]|\d\d)/g),O=60*W[1]+(+W[2]||0);return O===0?0:W[0]==="+"?-O:O}(g)}],_=function(g){var M=C[g];return M&&(M.indexOf?M:M.s.concat(M.f))},D=function(g,M){var W,O=C.meridiem;if(O){for(var H=1;H<=24;H+=1)if(g.indexOf(O(H,0,M))>-1){W=H>12;break}}else W=g===(M?"pm":"PM");return W},X={A:[b,function(g){this.afternoon=D(g,!1)}],a:[b,function(g){this.afternoon=D(g,!0)}],Q:[s,function(g){this.month=3*(g-1)+1}],S:[s,function(g){this.milliseconds=100*+g}],SS:[m,function(g){this.milliseconds=10*+g}],SSS:[/\d{3}/,function(g){this.milliseconds=+g}],s:[f,w("seconds")],ss:[f,w("seconds")],m:[f,w("minutes")],mm:[f,w("minutes")],H:[f,w("hours")],h:[f,w("hours")],HH:[f,w("hours")],hh:[f,w("hours")],D:[f,w("day")],DD:[m,w("day")],Do:[b,function(g){var M=C.ordinal,W=g.match(/\d+/);if(this.day=W[0],M)for(var O=1;O<=31;O+=1)M(O).replace(/\[|\]/g,"")===g&&(this.day=O)}],w:[f,w("week")],ww:[m,w("week")],M:[f,w("month")],MM:[m,w("month")],MMM:[b,function(g){var M=_("months"),W=(_("monthsShort")||M.map(function(O){return O.slice(0,3)})).indexOf(g)+1;if(W<1)throw new Error;this.month=W%12||W}],MMMM:[b,function(g){var M=_("months").indexOf(g)+1;if(M<1)throw new Error;this.month=M%12||M}],Y:[/[+-]?\d+/,w("year")],YY:[m,function(g){this.year=L(g)}],YYYY:[/\d{4}/,w("year")],Z:N,ZZ:N};function R(g){var M,W;M=g,W=C&&C.formats;for(var O=(g=M.replace(/(\[[^\]]+])|(LTS?|l{1,4}|L{1,4})/g,function(h,T,v){var p=v&&v.toUpperCase();return T||W[v]||i[v]||W[p].replace(/(\[[^\]]+])|(MMMM|MM|DD|dddd)/g,function(a,d,y){return d||y.slice(1)})})).match(r),H=O.length,z=0;z<H;z+=1){var I=O[z],x=X[I],k=x&&x[0],E=x&&x[1];O[z]=E?{regex:k,parser:E}:I.replace(/^\[|\]$/g,"")}return function(h){for(var T={},v=0,p=0;v<H;v+=1){var a=O[v];if(typeof a=="string")p+=a.length;else{var d=a.regex,y=a.parser,u=h.slice(p),S=d.exec(u)[0];y.call(T,S),h=h.replace(S,"")}}return function(n){var Y=n.afternoon;if(Y!==void 0){var o=n.hours;Y?o<12&&(n.hours+=12):o===12&&(n.hours=0),delete n.afternoon}}(T),T}}return function(g,M,W){W.p.customParseFormat=!0,g&&g.parseTwoDigitYear&&(L=g.parseTwoDigitYear);var O=M.prototype,H=O.parse;O.parse=function(z){var I=z.date,x=z.utc,k=z.args;this.$u=x;var E=k[1];if(typeof E=="string"){var h=k[2]===!0,T=k[3]===!0,v=h||T,p=k[2];T&&(p=k[2]),C=this.$locale(),!h&&p&&(C=W.Ls[p]),this.$d=function(u,S,n,Y){try{if(["x","X"].indexOf(S)>-1)return new Date((S==="X"?1e3:1)*u);var o=R(S)(u),G=o.year,c=o.month,A=o.day,$=o.hours,V=o.minutes,F=o.seconds,B=o.milliseconds,P=o.zone,st=o.week,ot=new Date,vt=A||(G||c?1:ot.getDate()),dt=G||ot.getFullYear(),j=0;G&&!c||(j=c>0?c-1:ot.getMonth());var K,Z=$||0,ct=V||0,J=F||0,at=B||0;return P?new Date(Date.UTC(dt,j,vt,Z,ct,J,at+60*P.offset*1e3)):n?new Date(Date.UTC(dt,j,vt,Z,ct,J,at)):(K=new Date(dt,j,vt,Z,ct,J,at),st&&(K=Y(K).week(st).toDate()),K)}catch{return new Date("")}}(I,E,x,W),this.init(),p&&p!==!0&&(this.$L=this.locale(p).$L),v&&I!=this.format(E)&&(this.$d=new Date("")),C={}}else if(E instanceof Array)for(var a=E.length,d=1;d<=a;d+=1){k[1]=E[d-1];var y=W.apply(this,k);if(y.isValid()){this.$d=y.$d,this.$L=y.$L,this.init();break}d===a&&(this.$d=new Date(""))}else H.call(this,z)}}})})(Ce);var Si=Ce.exports;const Ci=Yt(Si);var Me={exports:{}};(function(t,e){(function(i,r){t.exports=r()})(It,function(){return function(i,r){var s=r.prototype,m=s.format;s.format=function(f){var b=this,C=this.$locale();if(!this.isValid())return m.bind(this)(f);var L=this.$utils(),w=(f||"YYYY-MM-DDTHH:mm:ssZ").replace(/\[([^\]]+)]|Q|wo|ww|w|WW|W|zzz|z|gggg|GGGG|Do|X|x|k{1,2}|S/g,function(N){switch(N){case"Q":return Math.ceil((b.$M+1)/3);case"Do":return C.ordinal(b.$D);case"gggg":return b.weekYear();case"GGGG":return b.isoWeekYear();case"wo":return C.ordinal(b.week(),"W");case"w":case"ww":return L.s(b.week(),N==="w"?1:2,"0");case"W":case"WW":return L.s(b.isoWeek(),N==="W"?1:2,"0");case"k":case"kk":return L.s(String(b.$H===0?24:b.$H),N==="k"?1:2,"0");case"X":return Math.floor(b.$d.getTime()/1e3);case"x":return b.$d.getTime();case"z":return"["+b.offsetName()+"]";case"zzz":return"["+b.offsetName("long")+"]";default:return N}});return m.bind(this)(w)}}})})(Me);var Mi=Me.exports;const Ei=Yt(Mi);var Ee={exports:{}};(function(t,e){(function(i,r){t.exports=r()})(It,function(){var i,r,s=1e3,m=6e4,f=36e5,b=864e5,C=31536e6,L=2628e6,w=/^(-|\+)?P(?:([-+]?[0-9,.]*)Y)?(?:([-+]?[0-9,.]*)M)?(?:([-+]?[0-9,.]*)W)?(?:([-+]?[0-9,.]*)D)?(?:T(?:([-+]?[0-9,.]*)H)?(?:([-+]?[0-9,.]*)M)?(?:([-+]?[0-9,.]*)S)?)?$/,N=/\[([^\]]+)]|YYYY|YY|Y|M{1,2}|D{1,2}|H{1,2}|m{1,2}|s{1,2}|SSS/g,_={years:C,months:L,days:b,hours:f,minutes:m,seconds:s,milliseconds:1,weeks:6048e5},D=function(I){return I instanceof H},X=function(I,x,k){return new H(I,k,x.$l)},R=function(I){return r.p(I)+"s"},g=function(I){return I<0},M=function(I){return g(I)?Math.ceil(I):Math.floor(I)},W=function(I){return Math.abs(I)},O=function(I,x){return I?g(I)?{negative:!0,format:""+W(I)+x}:{negative:!1,format:""+I+x}:{negative:!1,format:""}},H=function(){function I(k,E,h){var T=this;if(this.$d={},this.$l=h,k===void 0&&(this.$ms=0,this.parseFromMilliseconds()),E)return X(k*_[R(E)],this);if(typeof k=="number")return this.$ms=k,this.parseFromMilliseconds(),this;if(typeof k=="object")return Object.keys(k).forEach(function(a){T.$d[R(a)]=k[a]}),this.calMilliseconds(),this;if(typeof k=="string"){var v=k.match(w);if(v){var p=v.slice(2).map(function(a){return a!=null?Number(a):0});return this.$d.years=p[0],this.$d.months=p[1],this.$d.weeks=p[2],this.$d.days=p[3],this.$d.hours=p[4],this.$d.minutes=p[5],this.$d.seconds=p[6],this.calMilliseconds(),this}}return this}var x=I.prototype;return x.calMilliseconds=function(){var k=this;this.$ms=Object.keys(this.$d).reduce(function(E,h){return E+(k.$d[h]||0)*_[h]},0)},x.parseFromMilliseconds=function(){var k=this.$ms;this.$d.years=M(k/C),k%=C,this.$d.months=M(k/L),k%=L,this.$d.days=M(k/b),k%=b,this.$d.hours=M(k/f),k%=f,this.$d.minutes=M(k/m),k%=m,this.$d.seconds=M(k/s),k%=s,this.$d.milliseconds=k},x.toISOString=function(){var k=O(this.$d.years,"Y"),E=O(this.$d.months,"M"),h=+this.$d.days||0;this.$d.weeks&&(h+=7*this.$d.weeks);var T=O(h,"D"),v=O(this.$d.hours,"H"),p=O(this.$d.minutes,"M"),a=this.$d.seconds||0;this.$d.milliseconds&&(a+=this.$d.milliseconds/1e3,a=Math.round(1e3*a)/1e3);var d=O(a,"S"),y=k.negative||E.negative||T.negative||v.negative||p.negative||d.negative,u=v.format||p.format||d.format?"T":"",S=(y?"-":"")+"P"+k.format+E.format+T.format+u+v.format+p.format+d.format;return S==="P"||S==="-P"?"P0D":S},x.toJSON=function(){return this.toISOString()},x.format=function(k){var E=k||"YYYY-MM-DDTHH:mm:ss",h={Y:this.$d.years,YY:r.s(this.$d.years,2,"0"),YYYY:r.s(this.$d.years,4,"0"),M:this.$d.months,MM:r.s(this.$d.months,2,"0"),D:this.$d.days,DD:r.s(this.$d.days,2,"0"),H:this.$d.hours,HH:r.s(this.$d.hours,2,"0"),m:this.$d.minutes,mm:r.s(this.$d.minutes,2,"0"),s:this.$d.seconds,ss:r.s(this.$d.seconds,2,"0"),SSS:r.s(this.$d.milliseconds,3,"0")};return E.replace(N,function(T,v){return v||String(h[T])})},x.as=function(k){return this.$ms/_[R(k)]},x.get=function(k){var E=this.$ms,h=R(k);return h==="milliseconds"?E%=1e3:E=h==="weeks"?M(E/_[h]):this.$d[h],E||0},x.add=function(k,E,h){var T;return T=E?k*_[R(E)]:D(k)?k.$ms:X(k,this).$ms,X(this.$ms+T*(h?-1:1),this)},x.subtract=function(k,E){return this.add(k,E,!0)},x.locale=function(k){var E=this.clone();return E.$l=k,E},x.clone=function(){return X(this.$ms,this)},x.humanize=function(k){return i().add(this.$ms,"ms").locale(this.$l).fromNow(!k)},x.valueOf=function(){return this.asMilliseconds()},x.milliseconds=function(){return this.get("milliseconds")},x.asMilliseconds=function(){return this.as("milliseconds")},x.seconds=function(){return this.get("seconds")},x.asSeconds=function(){return this.as("seconds")},x.minutes=function(){return this.get("minutes")},x.asMinutes=function(){return this.as("minutes")},x.hours=function(){return this.get("hours")},x.asHours=function(){return this.as("hours")},x.days=function(){return this.get("days")},x.asDays=function(){return this.as("days")},x.weeks=function(){return this.get("weeks")},x.asWeeks=function(){return this.as("weeks")},x.months=function(){return this.get("months")},x.asMonths=function(){return this.as("months")},x.years=function(){return this.get("years")},x.asYears=function(){return this.as("years")},I}(),z=function(I,x,k){return I.add(x.years()*k,"y").add(x.months()*k,"M").add(x.days()*k,"d").add(x.hours()*k,"h").add(x.minutes()*k,"m").add(x.seconds()*k,"s").add(x.milliseconds()*k,"ms")};return function(I,x,k){i=k,r=k().$utils(),k.duration=function(T,v){var p=k.locale();return X(T,{$l:p},v)},k.isDuration=D;var E=x.prototype.add,h=x.prototype.subtract;x.prototype.add=function(T,v){return D(T)?z(this,T,1):E.bind(this)(T,v)},x.prototype.subtract=function(T,v){return D(T)?z(this,T,-1):h.bind(this)(T,v)}}})})(Ee);var Ii=Ee.exports;const Yi=Yt(Ii);var Rt=function(){var t=l(function(p,a,d,y){for(d=d||{},y=p.length;y--;d[p[y]]=a);return d},"o"),e=[6,8,10,12,13,14,15,16,17,18,20,21,22,23,24,25,26,27,28,29,30,31,33,35,36,38,40],i=[1,26],r=[1,27],s=[1,28],m=[1,29],f=[1,30],b=[1,31],C=[1,32],L=[1,33],w=[1,34],N=[1,9],_=[1,10],D=[1,11],X=[1,12],R=[1,13],g=[1,14],M=[1,15],W=[1,16],O=[1,19],H=[1,20],z=[1,21],I=[1,22],x=[1,23],k=[1,25],E=[1,35],h={trace:l(function(){},"trace"),yy:{},symbols_:{error:2,start:3,gantt:4,document:5,EOF:6,line:7,SPACE:8,statement:9,NL:10,weekday:11,weekday_monday:12,weekday_tuesday:13,weekday_wednesday:14,weekday_thursday:15,weekday_friday:16,weekday_saturday:17,weekday_sunday:18,weekend:19,weekend_friday:20,weekend_saturday:21,dateFormat:22,inclusiveEndDates:23,topAxis:24,axisFormat:25,tickInterval:26,excludes:27,includes:28,todayMarker:29,title:30,acc_title:31,acc_title_value:32,acc_descr:33,acc_descr_value:34,acc_descr_multiline_value:35,section:36,clickStatement:37,taskTxt:38,taskData:39,click:40,callbackname:41,callbackargs:42,href:43,clickStatementDebug:44,$accept:0,$end:1},terminals_:{2:"error",4:"gantt",6:"EOF",8:"SPACE",10:"NL",12:"weekday_monday",13:"weekday_tuesday",14:"weekday_wednesday",15:"weekday_thursday",16:"weekday_friday",17:"weekday_saturday",18:"weekday_sunday",20:"weekend_friday",21:"weekend_saturday",22:"dateFormat",23:"inclusiveEndDates",24:"topAxis",25:"axisFormat",26:"tickInterval",27:"excludes",28:"includes",29:"todayMarker",30:"title",31:"acc_title",32:"acc_title_value",33:"acc_descr",34:"acc_descr_value",35:"acc_descr_multiline_value",36:"section",38:"taskTxt",39:"taskData",40:"click",41:"callbackname",42:"callbackargs",43:"href"},productions_:[0,[3,3],[5,0],[5,2],[7,2],[7,1],[7,1],[7,1],[11,1],[11,1],[11,1],[11,1],[11,1],[11,1],[11,1],[19,1],[19,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,1],[9,2],[9,2],[9,1],[9,1],[9,1],[9,2],[37,2],[37,3],[37,3],[37,4],[37,3],[37,4],[37,2],[44,2],[44,3],[44,3],[44,4],[44,3],[44,4],[44,2]],performAction:l(function(a,d,y,u,S,n,Y){var o=n.length-1;switch(S){case 1:return n[o-1];case 2:this.$=[];break;case 3:n[o-1].push(n[o]),this.$=n[o-1];break;case 4:case 5:this.$=n[o];break;case 6:case 7:this.$=[];break;case 8:u.setWeekday("monday");break;case 9:u.setWeekday("tuesday");break;case 10:u.setWeekday("wednesday");break;case 11:u.setWeekday("thursday");break;case 12:u.setWeekday("friday");break;case 13:u.setWeekday("saturday");break;case 14:u.setWeekday("sunday");break;case 15:u.setWeekend("friday");break;case 16:u.setWeekend("saturday");break;case 17:u.setDateFormat(n[o].substr(11)),this.$=n[o].substr(11);break;case 18:u.enableInclusiveEndDates(),this.$=n[o].substr(18);break;case 19:u.TopAxis(),this.$=n[o].substr(8);break;case 20:u.setAxisFormat(n[o].substr(11)),this.$=n[o].substr(11);break;case 21:u.setTickInterval(n[o].substr(13)),this.$=n[o].substr(13);break;case 22:u.setExcludes(n[o].substr(9)),this.$=n[o].substr(9);break;case 23:u.setIncludes(n[o].substr(9)),this.$=n[o].substr(9);break;case 24:u.setTodayMarker(n[o].substr(12)),this.$=n[o].substr(12);break;case 27:u.setDiagramTitle(n[o].substr(6)),this.$=n[o].substr(6);break;case 28:this.$=n[o].trim(),u.setAccTitle(this.$);break;case 29:case 30:this.$=n[o].trim(),u.setAccDescription(this.$);break;case 31:u.addSection(n[o].substr(8)),this.$=n[o].substr(8);break;case 33:u.addTask(n[o-1],n[o]),this.$="task";break;case 34:this.$=n[o-1],u.setClickEvent(n[o-1],n[o],null);break;case 35:this.$=n[o-2],u.setClickEvent(n[o-2],n[o-1],n[o]);break;case 36:this.$=n[o-2],u.setClickEvent(n[o-2],n[o-1],null),u.setLink(n[o-2],n[o]);break;case 37:this.$=n[o-3],u.setClickEvent(n[o-3],n[o-2],n[o-1]),u.setLink(n[o-3],n[o]);break;case 38:this.$=n[o-2],u.setClickEvent(n[o-2],n[o],null),u.setLink(n[o-2],n[o-1]);break;case 39:this.$=n[o-3],u.setClickEvent(n[o-3],n[o-1],n[o]),u.setLink(n[o-3],n[o-2]);break;case 40:this.$=n[o-1],u.setLink(n[o-1],n[o]);break;case 41:case 47:this.$=n[o-1]+" "+n[o];break;case 42:case 43:case 45:this.$=n[o-2]+" "+n[o-1]+" "+n[o];break;case 44:case 46:this.$=n[o-3]+" "+n[o-2]+" "+n[o-1]+" "+n[o];break}},"anonymous"),table:[{3:1,4:[1,2]},{1:[3]},t(e,[2,2],{5:3}),{6:[1,4],7:5,8:[1,6],9:7,10:[1,8],11:17,12:i,13:r,14:s,15:m,16:f,17:b,18:C,19:18,20:L,21:w,22:N,23:_,24:D,25:X,26:R,27:g,28:M,29:W,30:O,31:H,33:z,35:I,36:x,37:24,38:k,40:E},t(e,[2,7],{1:[2,1]}),t(e,[2,3]),{9:36,11:17,12:i,13:r,14:s,15:m,16:f,17:b,18:C,19:18,20:L,21:w,22:N,23:_,24:D,25:X,26:R,27:g,28:M,29:W,30:O,31:H,33:z,35:I,36:x,37:24,38:k,40:E},t(e,[2,5]),t(e,[2,6]),t(e,[2,17]),t(e,[2,18]),t(e,[2,19]),t(e,[2,20]),t(e,[2,21]),t(e,[2,22]),t(e,[2,23]),t(e,[2,24]),t(e,[2,25]),t(e,[2,26]),t(e,[2,27]),{32:[1,37]},{34:[1,38]},t(e,[2,30]),t(e,[2,31]),t(e,[2,32]),{39:[1,39]},t(e,[2,8]),t(e,[2,9]),t(e,[2,10]),t(e,[2,11]),t(e,[2,12]),t(e,[2,13]),t(e,[2,14]),t(e,[2,15]),t(e,[2,16]),{41:[1,40],43:[1,41]},t(e,[2,4]),t(e,[2,28]),t(e,[2,29]),t(e,[2,33]),t(e,[2,34],{42:[1,42],43:[1,43]}),t(e,[2,40],{41:[1,44]}),t(e,[2,35],{43:[1,45]}),t(e,[2,36]),t(e,[2,38],{42:[1,46]}),t(e,[2,37]),t(e,[2,39])],defaultActions:{},parseError:l(function(a,d){if(d.recoverable)this.trace(a);else{var y=new Error(a);throw y.hash=d,y}},"parseError"),parse:l(function(a){var d=this,y=[0],u=[],S=[null],n=[],Y=this.table,o="",G=0,c=0,A=2,$=1,V=n.slice.call(arguments,1),F=Object.create(this.lexer),B={yy:{}};for(var P in this.yy)Object.prototype.hasOwnProperty.call(this.yy,P)&&(B.yy[P]=this.yy[P]);F.setInput(a,B.yy),B.yy.lexer=F,B.yy.parser=this,typeof F.yylloc>"u"&&(F.yylloc={});var st=F.yylloc;n.push(st);var ot=F.options&&F.options.ranges;typeof B.yy.parseError=="function"?this.parseError=B.yy.parseError:this.parseError=Object.getPrototypeOf(this).parseError;function vt(Q){y.length=y.length-2*Q,S.length=S.length-Q,n.length=n.length-Q}l(vt,"popStack");function dt(){var Q;return Q=u.pop()||F.lex()||$,typeof Q!="number"&&(Q instanceof Array&&(u=Q,Q=u.pop()),Q=d.symbols_[Q]||Q),Q}l(dt,"lex");for(var j,K,Z,ct,J={},at,tt,ie,Tt;;){if(K=y[y.length-1],this.defaultActions[K]?Z=this.defaultActions[K]:((j===null||typeof j>"u")&&(j=dt()),Z=Y[K]&&Y[K][j]),typeof Z>"u"||!Z.length||!Z[0]){var At="";Tt=[];for(at in Y[K])this.terminals_[at]&&at>A&&Tt.push("'"+this.terminals_[at]+"'");F.showPosition?At="Parse error on line "+(G+1)+`:
`+F.showPosition()+`
Expecting `+Tt.join(", ")+", got '"+(this.terminals_[j]||j)+"'":At="Parse error on line "+(G+1)+": Unexpected "+(j==$?"end of input":"'"+(this.terminals_[j]||j)+"'"),this.parseError(At,{text:F.match,token:this.terminals_[j]||j,line:F.yylineno,loc:st,expected:Tt})}if(Z[0]instanceof Array&&Z.length>1)throw new Error("Parse Error: multiple actions possible at state: "+K+", token: "+j);switch(Z[0]){case 1:y.push(j),S.push(F.yytext),n.push(F.yylloc),y.push(Z[1]),j=null,c=F.yyleng,o=F.yytext,G=F.yylineno,st=F.yylloc;break;case 2:if(tt=this.productions_[Z[1]][1],J.$=S[S.length-tt],J._$={first_line:n[n.length-(tt||1)].first_line,last_line:n[n.length-1].last_line,first_column:n[n.length-(tt||1)].first_column,last_column:n[n.length-1].last_column},ot&&(J._$.range=[n[n.length-(tt||1)].range[0],n[n.length-1].range[1]]),ct=this.performAction.apply(J,[o,c,G,B.yy,Z[1],S,n].concat(V)),typeof ct<"u")return ct;tt&&(y=y.slice(0,-1*tt*2),S=S.slice(0,-1*tt),n=n.slice(0,-1*tt)),y.push(this.productions_[Z[1]][0]),S.push(J.$),n.push(J._$),ie=Y[y[y.length-2]][y[y.length-1]],y.push(ie);break;case 3:return!0}}return!0},"parse")},T=function(){var p={EOF:1,parseError:l(function(d,y){if(this.yy.parser)this.yy.parser.parseError(d,y);else throw new Error(d)},"parseError"),setInput:l(function(a,d){return this.yy=d||this.yy||{},this._input=a,this._more=this._backtrack=this.done=!1,this.yylineno=this.yyleng=0,this.yytext=this.matched=this.match="",this.conditionStack=["INITIAL"],this.yylloc={first_line:1,first_column:0,last_line:1,last_column:0},this.options.ranges&&(this.yylloc.range=[0,0]),this.offset=0,this},"setInput"),input:l(function(){var a=this._input[0];this.yytext+=a,this.yyleng++,this.offset++,this.match+=a,this.matched+=a;var d=a.match(/(?:\r\n?|\n).*/g);return d?(this.yylineno++,this.yylloc.last_line++):this.yylloc.last_column++,this.options.ranges&&this.yylloc.range[1]++,this._input=this._input.slice(1),a},"input"),unput:l(function(a){var d=a.length,y=a.split(/(?:\r\n?|\n)/g);this._input=a+this._input,this.yytext=this.yytext.substr(0,this.yytext.length-d),this.offset-=d;var u=this.match.split(/(?:\r\n?|\n)/g);this.match=this.match.substr(0,this.match.length-1),this.matched=this.matched.substr(0,this.matched.length-1),y.length-1&&(this.yylineno-=y.length-1);var S=this.yylloc.range;return this.yylloc={first_line:this.yylloc.first_line,last_line:this.yylineno+1,first_column:this.yylloc.first_column,last_column:y?(y.length===u.length?this.yylloc.first_column:0)+u[u.length-y.length].length-y[0].length:this.yylloc.first_column-d},this.options.ranges&&(this.yylloc.range=[S[0],S[0]+this.yyleng-d]),this.yyleng=this.yytext.length,this},"unput"),more:l(function(){return this._more=!0,this},"more"),reject:l(function(){if(this.options.backtrack_lexer)this._backtrack=!0;else return this.parseError("Lexical error on line "+(this.yylineno+1)+`. You can only invoke reject() in the lexer when the lexer is of the backtracking persuasion (options.backtrack_lexer = true).
`+this.showPosition(),{text:"",token:null,line:this.yylineno});return this},"reject"),less:l(function(a){this.unput(this.match.slice(a))},"less"),pastInput:l(function(){var a=this.matched.substr(0,this.matched.length-this.match.length);return(a.length>20?"...":"")+a.substr(-20).replace(/\n/g,"")},"pastInput"),upcomingInput:l(function(){var a=this.match;return a.length<20&&(a+=this._input.substr(0,20-a.length)),(a.substr(0,20)+(a.length>20?"...":"")).replace(/\n/g,"")},"upcomingInput"),showPosition:l(function(){var a=this.pastInput(),d=new Array(a.length+1).join("-");return a+this.upcomingInput()+`
`+d+"^"},"showPosition"),test_match:l(function(a,d){var y,u,S;if(this.options.backtrack_lexer&&(S={yylineno:this.yylineno,yylloc:{first_line:this.yylloc.first_line,last_line:this.last_line,first_column:this.yylloc.first_column,last_column:this.yylloc.last_column},yytext:this.yytext,match:this.match,matches:this.matches,matched:this.matched,yyleng:this.yyleng,offset:this.offset,_more:this._more,_input:this._input,yy:this.yy,conditionStack:this.conditionStack.slice(0),done:this.done},this.options.ranges&&(S.yylloc.range=this.yylloc.range.slice(0))),u=a[0].match(/(?:\r\n?|\n).*/g),u&&(this.yylineno+=u.length),this.yylloc={first_line:this.yylloc.last_line,last_line:this.yylineno+1,first_column:this.yylloc.last_column,last_column:u?u[u.length-1].length-u[u.length-1].match(/\r?\n?/)[0].length:this.yylloc.last_column+a[0].length},this.yytext+=a[0],this.match+=a[0],this.matches=a,this.yyleng=this.yytext.length,this.options.ranges&&(this.yylloc.range=[this.offset,this.offset+=this.yyleng]),this._more=!1,this._backtrack=!1,this._input=this._input.slice(a[0].length),this.matched+=a[0],y=this.performAction.call(this,this.yy,this,d,this.conditionStack[this.conditionStack.length-1]),this.done&&this._input&&(this.done=!1),y)return y;if(this._backtrack){for(var n in S)this[n]=S[n];return!1}return!1},"test_match"),next:l(function(){if(this.done)return this.EOF;this._input||(this.done=!0);var a,d,y,u;this._more||(this.yytext="",this.match="");for(var S=this._currentRules(),n=0;n<S.length;n++)if(y=this._input.match(this.rules[S[n]]),y&&(!d||y[0].length>d[0].length)){if(d=y,u=n,this.options.backtrack_lexer){if(a=this.test_match(y,S[n]),a!==!1)return a;if(this._backtrack){d=!1;continue}else return!1}else if(!this.options.flex)break}return d?(a=this.test_match(d,S[u]),a!==!1?a:!1):this._input===""?this.EOF:this.parseError("Lexical error on line "+(this.yylineno+1)+`. Unrecognized text.
`+this.showPosition(),{text:"",token:null,line:this.yylineno})},"next"),lex:l(function(){var d=this.next();return d||this.lex()},"lex"),begin:l(function(d){this.conditionStack.push(d)},"begin"),popState:l(function(){var d=this.conditionStack.length-1;return d>0?this.conditionStack.pop():this.conditionStack[0]},"popState"),_currentRules:l(function(){return this.conditionStack.length&&this.conditionStack[this.conditionStack.length-1]?this.conditions[this.conditionStack[this.conditionStack.length-1]].rules:this.conditions.INITIAL.rules},"_currentRules"),topState:l(function(d){return d=this.conditionStack.length-1-Math.abs(d||0),d>=0?this.conditionStack[d]:"INITIAL"},"topState"),pushState:l(function(d){this.begin(d)},"pushState"),stateStackSize:l(function(){return this.conditionStack.length},"stateStackSize"),options:{"case-insensitive":!0},performAction:l(function(d,y,u,S){switch(u){case 0:return this.begin("open_directive"),"open_directive";case 1:return this.begin("acc_title"),31;case 2:return this.popState(),"acc_title_value";case 3:return this.begin("acc_descr"),33;case 4:return this.popState(),"acc_descr_value";case 5:this.begin("acc_descr_multiline");break;case 6:this.popState();break;case 7:return"acc_descr_multiline_value";case 8:break;case 9:break;case 10:break;case 11:return 10;case 12:break;case 13:break;case 14:this.begin("href");break;case 15:this.popState();break;case 16:return 43;case 17:this.begin("callbackname");break;case 18:this.popState();break;case 19:this.popState(),this.begin("callbackargs");break;case 20:return 41;case 21:this.popState();break;case 22:return 42;case 23:this.begin("click");break;case 24:this.popState();break;case 25:return 40;case 26:return 4;case 27:return 22;case 28:return 23;case 29:return 24;case 30:return 25;case 31:return 26;case 32:return 28;case 33:return 27;case 34:return 29;case 35:return 12;case 36:return 13;case 37:return 14;case 38:return 15;case 39:return 16;case 40:return 17;case 41:return 18;case 42:return 20;case 43:return 21;case 44:return"date";case 45:return 30;case 46:return"accDescription";case 47:return 36;case 48:return 38;case 49:return 39;case 50:return":";case 51:return 6;case 52:return"INVALID"}},"anonymous"),rules:[/^(?:%%\{)/i,/^(?:accTitle\s*:\s*)/i,/^(?:(?!\n||)*[^\n]*)/i,/^(?:accDescr\s*:\s*)/i,/^(?:(?!\n||)*[^\n]*)/i,/^(?:accDescr\s*\{\s*)/i,/^(?:[\}])/i,/^(?:[^\}]*)/i,/^(?:%%(?!\{)*[^\n]*)/i,/^(?:[^\}]%%*[^\n]*)/i,/^(?:%%*[^\n]*[\n]*)/i,/^(?:[\n]+)/i,/^(?:\s+)/i,/^(?:%[^\n]*)/i,/^(?:href[\s]+["])/i,/^(?:["])/i,/^(?:[^"]*)/i,/^(?:call[\s]+)/i,/^(?:\([\s]*\))/i,/^(?:\()/i,/^(?:[^(]*)/i,/^(?:\))/i,/^(?:[^)]*)/i,/^(?:click[\s]+)/i,/^(?:[\s\n])/i,/^(?:[^\s\n]*)/i,/^(?:gantt\b)/i,/^(?:dateFormat\s[^#\n;]+)/i,/^(?:inclusiveEndDates\b)/i,/^(?:topAxis\b)/i,/^(?:axisFormat\s[^#\n;]+)/i,/^(?:tickInterval\s[^#\n;]+)/i,/^(?:includes\s[^#\n;]+)/i,/^(?:excludes\s[^#\n;]+)/i,/^(?:todayMarker\s[^\n;]+)/i,/^(?:weekday\s+monday\b)/i,/^(?:weekday\s+tuesday\b)/i,/^(?:weekday\s+wednesday\b)/i,/^(?:weekday\s+thursday\b)/i,/^(?:weekday\s+friday\b)/i,/^(?:weekday\s+saturday\b)/i,/^(?:weekday\s+sunday\b)/i,/^(?:weekend\s+friday\b)/i,/^(?:weekend\s+saturday\b)/i,/^(?:\d\d\d\d-\d\d-\d\d\b)/i,/^(?:title\s[^\n]+)/i,/^(?:accDescription\s[^#\n;]+)/i,/^(?:section\s[^\n]+)/i,/^(?:[^:\n]+)/i,/^(?::[^#\n;]+)/i,/^(?::)/i,/^(?:$)/i,/^(?:.)/i],conditions:{acc_descr_multiline:{rules:[6,7],inclusive:!1},acc_descr:{rules:[4],inclusive:!1},acc_title:{rules:[2],inclusive:!1},callbackargs:{rules:[21,22],inclusive:!1},callbackname:{rules:[18,19,20],inclusive:!1},href:{rules:[15,16],inclusive:!1},click:{rules:[24,25],inclusive:!1},INITIAL:{rules:[0,1,3,5,8,9,10,11,12,13,14,17,23,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52],inclusive:!0}}};return p}();h.lexer=T;function v(){this.yy={}}return l(v,"Parser"),v.prototype=h,h.Parser=v,new v}();Rt.parser=Rt;var Ai=Rt;q.extend(Di);q.extend(Ci);q.extend(Ei);var de={friday:5,saturday:6},et="",Xt="",jt=void 0,Ut="",yt=[],gt=[],qt=new Map,Zt=[],Mt=[],pt="",Qt="",Ie=["active","done","crit","milestone","vert"],Kt=[],ft="",xt=!1,Jt=!1,te="sunday",Et="saturday",Ht=0,$i=l(function(){Zt=[],Mt=[],pt="",Kt=[],Dt=0,Gt=void 0,St=void 0,U=[],et="",Xt="",Qt="",jt=void 0,Ut="",yt=[],gt=[],xt=!1,Jt=!1,Ht=0,qt=new Map,ft="",Ue(),te="sunday",Et="saturday"},"clear"),Fi=l(function(t){ft=t},"setDiagramId"),Li=l(function(t){Xt=t},"setAxisFormat"),Oi=l(function(){return Xt},"getAxisFormat"),Wi=l(function(t){jt=t},"setTickInterval"),Ni=l(function(){return jt},"getTickInterval"),Pi=l(function(t){Ut=t},"setTodayMarker"),Vi=l(function(){return Ut},"getTodayMarker"),zi=l(function(t){et=t},"setDateFormat"),Ri=l(function(){xt=!0},"enableInclusiveEndDates"),Hi=l(function(){return xt},"endDatesAreInclusive"),Bi=l(function(){Jt=!0},"enableTopAxis"),Gi=l(function(){return Jt},"topAxisEnabled"),Xi=l(function(t){Qt=t},"setDisplayMode"),ji=l(function(){return Qt},"getDisplayMode"),Ui=l(function(){return et},"getDateFormat"),Ye=l((t,e)=>{const i=e.toLowerCase().split(/[\s,]+/).filter(r=>r!=="");return[...new Set([...t,...i])]},"mergeTokens"),qi=l(function(t){yt=Ye(yt,t)},"setIncludes"),Zi=l(function(){return yt},"getIncludes"),Qi=l(function(t){gt=Ye(gt,t)},"setExcludes"),Ki=l(function(){return gt},"getExcludes"),Ji=l(function(){return qt},"getLinks"),tr=l(function(t){pt=t,Zt.push(t)},"addSection"),er=l(function(){return Zt},"getSections"),ir=l(function(){let t=fe();const e=10;let i=0;for(;!t&&i<e;)t=fe(),i++;return Mt=U,Mt},"getTasks"),Ae=l(function(t,e,i,r){const s=t.format(e.trim()),m=t.format("YYYY-MM-DD");return r.includes(s)||r.includes(m)?!1:i.includes("weekends")&&(t.isoWeekday()===de[Et]||t.isoWeekday()===de[Et]+1)||i.includes(t.format("dddd").toLowerCase())?!0:i.includes(s)||i.includes(m)},"isInvalidDate"),rr=l(function(t){te=t},"setWeekday"),nr=l(function(){return te},"getWeekday"),sr=l(function(t){Et=t},"setWeekend"),$e=l(function(t,e,i,r){if(!i.length||t.manualEndTime)return;let s;t.startTime instanceof Date?s=q(t.startTime):s=q(t.startTime,e,!0),s=s.add(1,"d");let m;t.endTime instanceof Date?m=q(t.endTime):m=q(t.endTime,e,!0);const[f,b]=ar(s,m,e,i,r);t.endTime=f.toDate(),t.renderEndTime=b},"checkTaskDates"),ar=l(function(t,e,i,r,s){let m=!1,f=null;const b=e.add(1e4,"d");for(;t<=e;){if(m||(f=e.toDate()),m=Ae(t,i,r,s),m&&(e=e.add(1,"d"),e>b))throw new Error("Failed to find a valid date that was not excluded by `excludes` after 10,000 iterations.");t=t.add(1,"d")}return[e,f]},"fixTaskDates"),Bt=l(function(t,e,i){if(i=i.trim(),l(b=>{const C=b.trim();return C==="x"||C==="X"},"isTimestampFormat")(e)&&/^\d+$/.test(i))return new Date(Number(i));const m=/^after\s+(?<ids>[\d\w- ]+)/.exec(i);if(m!==null){let b=null;for(const L of m.groups.ids.split(" ")){let w=ut(L);w!==void 0&&(!b||w.endTime>b.endTime)&&(b=w)}if(b)return b.endTime;const C=new Date;return C.setHours(0,0,0,0),C}let f=q(i,e.trim(),!0);if(f.isValid())return f.toDate();{lt.debug("Invalid date:"+i),lt.debug("With date format:"+e.trim());const b=new Date(i);if(b===void 0||isNaN(b.getTime())||b.getFullYear()<-1e4||b.getFullYear()>1e4)throw new Error("Invalid date:"+i);return b}},"getStartDate"),Fe=l(function(t){const e=/^(\d+(?:\.\d+)?)([Mdhmswy]|ms)$/.exec(t.trim());return e!==null?[Number.parseFloat(e[1]),e[2]]:[NaN,"ms"]},"parseDuration"),Le=l(function(t,e,i,r=!1){i=i.trim();const m=/^until\s+(?<ids>[\d\w- ]+)/.exec(i);if(m!==null){let w=null;for(const _ of m.groups.ids.split(" ")){let D=ut(_);D!==void 0&&(!w||D.startTime<w.startTime)&&(w=D)}if(w)return w.startTime;const N=new Date;return N.setHours(0,0,0,0),N}let f=q(i,e.trim(),!0);if(f.isValid())return r&&(f=f.add(1,"d")),f.toDate();let b=q(t);const[C,L]=Fe(i);if(!Number.isNaN(C)){const w=b.add(C,L);w.isValid()&&(b=w)}return b.toDate()},"getEndDate"),Dt=0,kt=l(function(t){return t===void 0?(Dt=Dt+1,"task"+Dt):t},"parseId"),or=l(function(t,e){let i;e.substr(0,1)===":"?i=e.substr(1,e.length):i=e;const r=i.split(","),s={};ee(r,s,Ie);for(let f=0;f<r.length;f++)r[f]=r[f].trim();let m="";switch(r.length){case 1:s.id=kt(),s.startTime=t.endTime,m=r[0];break;case 2:s.id=kt(),s.startTime=Bt(void 0,et,r[0]),m=r[1];break;case 3:s.id=kt(r[0]),s.startTime=Bt(void 0,et,r[1]),m=r[2];break}return m&&(s.endTime=Le(s.startTime,et,m,xt),s.manualEndTime=q(m,"YYYY-MM-DD",!0).isValid(),$e(s,et,gt,yt)),s},"compileData"),cr=l(function(t,e){let i;e.substr(0,1)===":"?i=e.substr(1,e.length):i=e;const r=i.split(","),s={};ee(r,s,Ie);for(let m=0;m<r.length;m++)r[m]=r[m].trim();switch(r.length){case 1:s.id=kt(),s.startTime={type:"prevTaskEnd",id:t},s.endTime={data:r[0]};break;case 2:s.id=kt(),s.startTime={type:"getStartDate",startData:r[0]},s.endTime={data:r[1]};break;case 3:s.id=kt(r[0]),s.startTime={type:"getStartDate",startData:r[1]},s.endTime={data:r[2]};break}return s},"parseData"),Gt,St,U=[],Oe={},lr=l(function(t,e){const i={section:pt,type:pt,processed:!1,manualEndTime:!1,renderEndTime:null,raw:{data:e},task:t,classes:[]},r=cr(St,e);i.raw.startTime=r.startTime,i.raw.endTime=r.endTime,i.id=r.id,i.prevTaskId=St,i.active=r.active,i.done=r.done,i.crit=r.crit,i.milestone=r.milestone,i.vert=r.vert,i.vert?i.order=-1:(i.order=Ht,Ht++);const s=U.push(i);St=i.id,Oe[i.id]=s-1},"addTask"),ut=l(function(t){const e=Oe[t];return U[e]},"findTaskById"),ur=l(function(t,e){const i={section:pt,type:pt,description:t,task:t,classes:[]},r=or(Gt,e);i.startTime=r.startTime,i.endTime=r.endTime,i.id=r.id,i.active=r.active,i.done=r.done,i.crit=r.crit,i.milestone=r.milestone,i.vert=r.vert,Gt=i,Mt.push(i)},"addTaskOrg"),fe=l(function(){const t=l(function(i){const r=U[i];let s="";switch(U[i].raw.startTime.type){case"prevTaskEnd":{const m=ut(r.prevTaskId);r.startTime=m.endTime;break}case"getStartDate":s=Bt(void 0,et,U[i].raw.startTime.startData),s&&(U[i].startTime=s);break}return U[i].startTime&&(U[i].endTime=Le(U[i].startTime,et,U[i].raw.endTime.data,xt),U[i].endTime&&(U[i].processed=!0,U[i].manualEndTime=q(U[i].raw.endTime.data,"YYYY-MM-DD",!0).isValid(),$e(U[i],et,gt,yt))),U[i].processed},"compileTask");let e=!0;for(const[i,r]of U.entries())t(i),e=e&&r.processed;return e},"compileTasks"),dr=l(function(t,e){let i=e;ht().securityLevel!=="loose"&&(i=je(e)),t.split(",").forEach(function(r){ut(r)!==void 0&&(Ne(r,()=>{window.open(i,"_self")}),qt.set(r,i))}),We(t,"clickable")},"setLink"),We=l(function(t,e){t.split(",").forEach(function(i){let r=ut(i);r!==void 0&&r.classes.push(e)})},"setClass"),fr=l(function(t,e,i){if(ht().securityLevel!=="loose"||e===void 0)return;let r=[];if(typeof i=="string"){r=i.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);for(let m=0;m<r.length;m++){let f=r[m].trim();f.startsWith('"')&&f.endsWith('"')&&(f=f.substr(1,f.length-2)),r[m]=f}}r.length===0&&r.push(t),ut(t)!==void 0&&Ne(t,()=>{qe.runFunc(e,...r)})},"setClickFun"),Ne=l(function(t,e){Kt.push(function(){const i=ft?`${ft}-${t}`:t,r=document.querySelector(`[id="${i}"]`);r!==null&&r.addEventListener("click",function(){e()})},function(){const i=ft?`${ft}-${t}`:t,r=document.querySelector(`[id="${i}-text"]`);r!==null&&r.addEventListener("click",function(){e()})})},"pushFun"),hr=l(function(t,e,i){t.split(",").forEach(function(r){fr(r,e,i)}),We(t,"clickable")},"setClickEvent"),mr=l(function(t){Kt.forEach(function(e){e(t)})},"bindFunctions"),kr={getConfig:l(()=>ht().gantt,"getConfig"),clear:$i,setDateFormat:zi,getDateFormat:Ui,enableInclusiveEndDates:Ri,endDatesAreInclusive:Hi,enableTopAxis:Bi,topAxisEnabled:Gi,setAxisFormat:Li,getAxisFormat:Oi,setTickInterval:Wi,getTickInterval:Ni,setTodayMarker:Pi,getTodayMarker:Vi,setAccTitle:Be,getAccTitle:He,setDiagramTitle:Re,getDiagramTitle:ze,setDiagramId:Fi,setDisplayMode:Xi,getDisplayMode:ji,setAccDescription:Ve,getAccDescription:Pe,addSection:tr,getSections:er,getTasks:ir,addTask:lr,findTaskById:ut,addTaskOrg:ur,setIncludes:qi,getIncludes:Zi,setExcludes:Qi,getExcludes:Ki,setClickEvent:hr,setLink:dr,getLinks:Ji,bindFunctions:mr,parseDuration:Fe,isInvalidDate:Ae,setWeekday:rr,getWeekday:nr,setWeekend:sr};function ee(t,e,i){let r=!0;for(;r;)r=!1,i.forEach(function(s){const m="^\\s*"+s+"\\s*$",f=new RegExp(m);t[0].match(f)&&(e[s]=!0,t.shift(1),r=!0)})}l(ee,"getTaskTags");q.extend(Yi);var yr=l(function(){lt.debug("Something is calling, setConf, remove the call")},"setConf"),he={monday:ri,tuesday:ii,wednesday:ei,thursday:ti,friday:Je,saturday:Ke,sunday:Qe},gr=l((t,e)=>{let i=[...t].map(()=>-1/0),r=[...t].sort((m,f)=>m.startTime-f.startTime||m.order-f.order),s=0;for(const m of r)for(let f=0;f<i.length;f++)if(m.startTime>=i[f]){i[f]=m.endTime,m.order=f+e,f>s&&(s=f);break}return s},"getMaxIntersections"),rt,Pt=1e4,pr=l(function(t,e,i,r){const s=ht().gantt;r.db.setDiagramId(e);const m=ht().securityLevel;let f;m==="sandbox"&&(f=bt("#i"+e));const b=m==="sandbox"?bt(f.nodes()[0].contentDocument.body):bt("body"),C=m==="sandbox"?f.nodes()[0].contentDocument:document,L=C.getElementById(e);rt=L.parentElement.offsetWidth,rt===void 0&&(rt=1200),s.useWidth!==void 0&&(rt=s.useWidth);const w=r.db.getTasks(),N=w.filter(h=>!h.vert);let _=[];for(const h of N)_.push(h.type);_=E(_);const D={};let X=2*s.topPadding;if(r.db.getDisplayMode()==="compact"||s.displayMode==="compact"){const h={};for(const v of N)h[v.section]===void 0?h[v.section]=[v]:h[v.section].push(v);let T=0;for(const v of Object.keys(h)){const p=gr(h[v],T)+1;T+=p,X+=p*(s.barHeight+s.barGap),D[v]=p}}else{X+=N.length*(s.barHeight+s.barGap);for(const h of _)D[h]=N.filter(T=>T.type===h).length}L.setAttribute("viewBox","0 0 "+rt+" "+X);const R=b.select(`[id="${e}"]`),g=Ze().domain([ni(w,function(h){return h.startTime}),si(w,function(h){return h.endTime})]).rangeRound([0,rt-s.leftPadding-s.rightPadding]);function M(h,T){const v=h.startTime,p=T.startTime;let a=0;return v>p?a=1:v<p&&(a=-1),a}l(M,"taskCompare"),w.sort(M),W(w,rt,X),Ge(R,X,rt,s.useMaxWidth),R.append("text").text(r.db.getDiagramTitle()).attr("x",rt/2).attr("y",s.titleTopMargin).attr("class","titleText");function W(h,T,v){const p=s.barHeight,a=p+s.barGap,d=s.topPadding,y=s.leftPadding,u=ai().domain([0,_.length]).range(["#00B9FA","#F95002"]).interpolate(ki);H(a,d,y,T,v,h,r.db.getExcludes(),r.db.getIncludes()),I(y,d,T,v),O(h,a,d,y,p,u,T),x(a,d),k(y,d,T,v)}l(W,"makeGantt");function O(h,T,v,p,a,d,y){h.sort((c,A)=>c.vert===A.vert?0:c.vert?1:-1);const u=h.filter(c=>!c.vert),n=[...new Set(u.map(c=>c.order))].map(c=>u.find(A=>A.order===c));R.append("g").selectAll("rect").data(n).enter().append("rect").attr("x",0).attr("y",function(c,A){return A=c.order,A*T+v-2}).attr("width",function(){return y-s.rightPadding/2}).attr("height",T).attr("class",function(c){for(const[A,$]of _.entries())if(c.type===$)return"section section"+A%s.numberSectionStyles;return"section section0"}).enter();const Y=R.append("g").selectAll("rect").data(h).enter(),o=r.db.getLinks();if(Y.append("rect").attr("id",function(c){return e+"-"+c.id}).attr("rx",3).attr("ry",3).attr("x",function(c){return c.milestone?g(c.startTime)+p+.5*(g(c.endTime)-g(c.startTime))-.5*a:g(c.startTime)+p}).attr("y",function(c,A){return A=c.order,c.vert?s.gridLineStartPadding:A*T+v}).attr("width",function(c){return c.milestone?a:c.vert?.08*a:g(c.renderEndTime||c.endTime)-g(c.startTime)}).attr("height",function(c){return c.vert?u.length*(s.barHeight+s.barGap)+s.barHeight*2:a}).attr("transform-origin",function(c,A){return A=c.order,(g(c.startTime)+p+.5*(g(c.endTime)-g(c.startTime))).toString()+"px "+(A*T+v+.5*a).toString()+"px"}).attr("class",function(c){const A="task";let $="";c.classes.length>0&&($=c.classes.join(" "));let V=0;for(const[B,P]of _.entries())c.type===P&&(V=B%s.numberSectionStyles);let F="";return c.active?c.crit?F+=" activeCrit":F=" active":c.done?c.crit?F=" doneCrit":F=" done":c.crit&&(F+=" crit"),F.length===0&&(F=" task"),c.milestone&&(F=" milestone "+F),c.vert&&(F=" vert "+F),F+=V,F+=" "+$,A+F}),Y.append("text").attr("id",function(c){return e+"-"+c.id+"-text"}).text(function(c){return c.task}).attr("font-size",s.fontSize).attr("x",function(c){let A=g(c.startTime),$=g(c.renderEndTime||c.endTime);if(c.milestone&&(A+=.5*(g(c.endTime)-g(c.startTime))-.5*a,$=A+a),c.vert)return g(c.startTime)+p;const V=this.getBBox().width;return V>$-A?$+V+1.5*s.leftPadding>y?A+p-5:$+p+5:($-A)/2+A+p}).attr("y",function(c,A){return c.vert?s.gridLineStartPadding+u.length*(s.barHeight+s.barGap)+60:(A=c.order,A*T+s.barHeight/2+(s.fontSize/2-2)+v)}).attr("text-height",a).attr("class",function(c){const A=g(c.startTime);let $=g(c.endTime);c.milestone&&($=A+a);const V=this.getBBox().width;let F="";c.classes.length>0&&(F=c.classes.join(" "));let B=0;for(const[st,ot]of _.entries())c.type===ot&&(B=st%s.numberSectionStyles);let P="";return c.active&&(c.crit?P="activeCritText"+B:P="activeText"+B),c.done?c.crit?P=P+" doneCritText"+B:P=P+" doneText"+B:c.crit&&(P=P+" critText"+B),c.milestone&&(P+=" milestoneText"),c.vert&&(P+=" vertText"),V>$-A?$+V+1.5*s.leftPadding>y?F+" taskTextOutsideLeft taskTextOutside"+B+" "+P:F+" taskTextOutsideRight taskTextOutside"+B+" "+P+" width-"+V:F+" taskText taskText"+B+" "+P+" width-"+V}),ht().securityLevel==="sandbox"){let c;c=bt("#i"+e);const A=c.nodes()[0].contentDocument;Y.filter(function($){return o.has($.id)}).each(function($){var V=A.querySelector("#"+CSS.escape(e+"-"+$.id)),F=A.querySelector("#"+CSS.escape(e+"-"+$.id+"-text"));const B=V.parentNode;var P=A.createElement("a");P.setAttribute("xlink:href",o.get($.id)),P.setAttribute("target","_top"),B.appendChild(P),P.appendChild(V),P.appendChild(F)})}}l(O,"drawRects");function H(h,T,v,p,a,d,y,u){if(y.length===0&&u.length===0)return;let S,n;for(const{startTime:$,endTime:V}of d)(S===void 0||$<S)&&(S=$),(n===void 0||V>n)&&(n=V);if(!S||!n)return;if(q(n).diff(q(S),"year")>5){lt.warn("The difference between the min and max time is more than 5 years. This will cause performance issues. Skipping drawing exclude days.");return}const Y=r.db.getDateFormat(),o=[];let G=null,c=q(S);for(;c.valueOf()<=n;)r.db.isInvalidDate(c,Y,y,u)?G?G.end=c:G={start:c,end:c}:G&&(o.push(G),G=null),c=c.add(1,"d");R.append("g").selectAll("rect").data(o).enter().append("rect").attr("id",$=>e+"-exclude-"+$.start.format("YYYY-MM-DD")).attr("x",$=>g($.start.startOf("day"))+v).attr("y",s.gridLineStartPadding).attr("width",$=>g($.end.endOf("day"))-g($.start.startOf("day"))).attr("height",a-T-s.gridLineStartPadding).attr("transform-origin",function($,V){return(g($.start)+v+.5*(g($.end)-g($.start))).toString()+"px "+(V*h+.5*a).toString()+"px"}).attr("class","exclude-range")}l(H,"drawExcludeDays");function z(h,T,v,p){if(v<=0||h>T)return 1/0;const a=T-h,d=q.duration({[p??"day"]:v}).asMilliseconds();return d<=0?1/0:Math.ceil(a/d)}l(z,"getEstimatedTickCount");function I(h,T,v,p){const a=r.db.getDateFormat(),d=r.db.getAxisFormat();let y;d?y=d:a==="D"?y="%d":y=s.axisFormat??"%Y-%m-%d";let u=wi(g).tickSize(-p+T+s.gridLineStartPadding).tickFormat(re(y));const n=/^([1-9]\d*)(millisecond|second|minute|hour|day|week|month)$/.exec(r.db.getTickInterval()||s.tickInterval);if(n!==null){const Y=parseInt(n[1],10);if(isNaN(Y)||Y<=0)lt.warn(`Invalid tick interval value: "${n[1]}". Skipping custom tick interval.`);else{const o=n[2],G=r.db.getWeekday()||s.weekday,c=g.domain(),A=c[0],$=c[1],V=z(A,$,Y,o);if(V>Pt)lt.warn(`The tick interval "${Y}${o}" would generate ${V} ticks, which exceeds the maximum allowed (${Pt}). This may indicate an invalid date or time range. Skipping custom tick interval.`);else switch(o){case"millisecond":u.ticks(le.every(Y));break;case"second":u.ticks(ce.every(Y));break;case"minute":u.ticks(oe.every(Y));break;case"hour":u.ticks(ae.every(Y));break;case"day":u.ticks(se.every(Y));break;case"week":u.ticks(he[G].every(Y));break;case"month":u.ticks(ne.every(Y));break}}}if(R.append("g").attr("class","grid").attr("transform","translate("+h+", "+(p-50)+")").call(u).selectAll("text").style("text-anchor","middle").attr("fill","#000").attr("stroke","none").attr("font-size",10).attr("dy","1em"),r.db.topAxisEnabled()||s.topAxis){let Y=bi(g).tickSize(-p+T+s.gridLineStartPadding).tickFormat(re(y));if(n!==null){const o=parseInt(n[1],10);if(isNaN(o)||o<=0)lt.warn(`Invalid tick interval value: "${n[1]}". Skipping custom tick interval.`);else{const G=n[2],c=r.db.getWeekday()||s.weekday,A=g.domain(),$=A[0],V=A[1];if(z($,V,o,G)<=Pt)switch(G){case"millisecond":Y.ticks(le.every(o));break;case"second":Y.ticks(ce.every(o));break;case"minute":Y.ticks(oe.every(o));break;case"hour":Y.ticks(ae.every(o));break;case"day":Y.ticks(se.every(o));break;case"week":Y.ticks(he[c].every(o));break;case"month":Y.ticks(ne.every(o));break}}}R.append("g").attr("class","grid").attr("transform","translate("+h+", "+T+")").call(Y).selectAll("text").style("text-anchor","middle").attr("fill","#000").attr("stroke","none").attr("font-size",10)}}l(I,"makeGrid");function x(h,T){let v=0;const p=Object.keys(D).map(a=>[a,D[a]]);R.append("g").selectAll("text").data(p).enter().append(function(a){const d=a[0].split(Xe.lineBreakRegex),y=-(d.length-1)/2,u=C.createElementNS("http://www.w3.org/2000/svg","text");u.setAttribute("dy",y+"em");for(const[S,n]of d.entries()){const Y=C.createElementNS("http://www.w3.org/2000/svg","tspan");Y.setAttribute("alignment-baseline","central"),Y.setAttribute("x","10"),S>0&&Y.setAttribute("dy","1em"),Y.textContent=n,u.appendChild(Y)}return u}).attr("x",10).attr("y",function(a,d){if(d>0)for(let y=0;y<d;y++)return v+=p[d-1][1],a[1]*h/2+v*h+T;else return a[1]*h/2+T}).attr("font-size",s.sectionFontSize).attr("class",function(a){for(const[d,y]of _.entries())if(a[0]===y)return"sectionTitle sectionTitle"+d%s.numberSectionStyles;return"sectionTitle"})}l(x,"vertLabels");function k(h,T,v,p){const a=r.db.getTodayMarker();if(a==="off")return;const d=R.append("g").attr("class","today"),y=new Date,u=d.append("line");u.attr("x1",g(y)+h).attr("x2",g(y)+h).attr("y1",s.titleTopMargin).attr("y2",p-s.titleTopMargin).attr("class","today"),a!==""&&u.attr("style",a.replace(/,/g,";"))}l(k,"drawToday");function E(h){const T={},v=[];for(let p=0,a=h.length;p<a;++p)Object.prototype.hasOwnProperty.call(T,h[p])||(T[h[p]]=!0,v.push(h[p]));return v}l(E,"checkUnique")},"draw"),vr={setConf:yr,draw:pr},xr=l(t=>`
  .mermaid-main-font {
        font-family: ${t.fontFamily};
  }

  .exclude-range {
    fill: ${t.excludeBkgColor};
  }

  .section {
    stroke: none;
    opacity: 0.2;
  }

  .section0 {
    fill: ${t.sectionBkgColor};
  }

  .section2 {
    fill: ${t.sectionBkgColor2};
  }

  .section1,
  .section3 {
    fill: ${t.altSectionBkgColor};
    opacity: 0.2;
  }

  .sectionTitle0 {
    fill: ${t.titleColor};
  }

  .sectionTitle1 {
    fill: ${t.titleColor};
  }

  .sectionTitle2 {
    fill: ${t.titleColor};
  }

  .sectionTitle3 {
    fill: ${t.titleColor};
  }

  .sectionTitle {
    text-anchor: start;
    font-family: ${t.fontFamily};
  }


  /* Grid and axis */

  .grid .tick {
    stroke: ${t.gridColor};
    opacity: 0.8;
    shape-rendering: crispEdges;
  }

  .grid .tick text {
    font-family: ${t.fontFamily};
    fill: ${t.textColor};
  }

  .grid path {
    stroke-width: 0;
  }


  /* Today line */

  .today {
    fill: none;
    stroke: ${t.todayLineColor};
    stroke-width: 2px;
  }


  /* Task styling */

  /* Default task */

  .task {
    stroke-width: 2;
  }

  .taskText {
    text-anchor: middle;
    font-family: ${t.fontFamily};
  }

  .taskTextOutsideRight {
    fill: ${t.taskTextDarkColor};
    text-anchor: start;
    font-family: ${t.fontFamily};
  }

  .taskTextOutsideLeft {
    fill: ${t.taskTextDarkColor};
    text-anchor: end;
  }


  /* Special case clickable */

  .task.clickable {
    cursor: pointer;
  }

  .taskText.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }

  .taskTextOutsideLeft.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }

  .taskTextOutsideRight.clickable {
    cursor: pointer;
    fill: ${t.taskTextClickableColor} !important;
    font-weight: bold;
  }


  /* Specific task settings for the sections*/

  .taskText0,
  .taskText1,
  .taskText2,
  .taskText3 {
    fill: ${t.taskTextColor};
  }

  .task0,
  .task1,
  .task2,
  .task3 {
    fill: ${t.taskBkgColor};
    stroke: ${t.taskBorderColor};
  }

  .taskTextOutside0,
  .taskTextOutside2
  {
    fill: ${t.taskTextOutsideColor};
  }

  .taskTextOutside1,
  .taskTextOutside3 {
    fill: ${t.taskTextOutsideColor};
  }


  /* Active task */

  .active0,
  .active1,
  .active2,
  .active3 {
    fill: ${t.activeTaskBkgColor};
    stroke: ${t.activeTaskBorderColor};
  }

  .activeText0,
  .activeText1,
  .activeText2,
  .activeText3 {
    fill: ${t.taskTextDarkColor} !important;
  }


  /* Completed task */

  .done0,
  .done1,
  .done2,
  .done3 {
    stroke: ${t.doneTaskBorderColor};
    fill: ${t.doneTaskBkgColor};
    stroke-width: 2;
  }

  .doneText0,
  .doneText1,
  .doneText2,
  .doneText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  /* Done task text displayed outside the bar sits against the diagram background,
     not against the done-task bar, so it must use the outside/contrast color. */
  .doneText0.taskTextOutsideLeft,
  .doneText0.taskTextOutsideRight,
  .doneText1.taskTextOutsideLeft,
  .doneText1.taskTextOutsideRight,
  .doneText2.taskTextOutsideLeft,
  .doneText2.taskTextOutsideRight,
  .doneText3.taskTextOutsideLeft,
  .doneText3.taskTextOutsideRight {
    fill: ${t.taskTextOutsideColor} !important;
  }


  /* Tasks on the critical line */

  .crit0,
  .crit1,
  .crit2,
  .crit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.critBkgColor};
    stroke-width: 2;
  }

  .activeCrit0,
  .activeCrit1,
  .activeCrit2,
  .activeCrit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.activeTaskBkgColor};
    stroke-width: 2;
  }

  .doneCrit0,
  .doneCrit1,
  .doneCrit2,
  .doneCrit3 {
    stroke: ${t.critBorderColor};
    fill: ${t.doneTaskBkgColor};
    stroke-width: 2;
    cursor: pointer;
    shape-rendering: crispEdges;
  }

  .milestone {
    transform: rotate(45deg) scale(0.8,0.8);
  }

  .milestoneText {
    font-style: italic;
  }
  .doneCritText0,
  .doneCritText1,
  .doneCritText2,
  .doneCritText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  /* Done-crit task text outside the bar — same reasoning as doneText above. */
  .doneCritText0.taskTextOutsideLeft,
  .doneCritText0.taskTextOutsideRight,
  .doneCritText1.taskTextOutsideLeft,
  .doneCritText1.taskTextOutsideRight,
  .doneCritText2.taskTextOutsideLeft,
  .doneCritText2.taskTextOutsideRight,
  .doneCritText3.taskTextOutsideLeft,
  .doneCritText3.taskTextOutsideRight {
    fill: ${t.taskTextOutsideColor} !important;
  }

  .vert {
    stroke: ${t.vertLineColor};
  }

  .vertText {
    font-size: 15px;
    text-anchor: middle;
    fill: ${t.vertLineColor} !important;
  }

  .activeCritText0,
  .activeCritText1,
  .activeCritText2,
  .activeCritText3 {
    fill: ${t.taskTextDarkColor} !important;
  }

  .titleText {
    text-anchor: middle;
    font-size: 18px;
    fill: ${t.titleColor||t.textColor};
    font-family: ${t.fontFamily};
  }
`,"getStyles"),Tr=xr,Wr={parser:Ai,db:kr,renderer:vr,styles:Tr};export{Wr as diagram};
