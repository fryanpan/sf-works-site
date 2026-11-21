"""Speed camera rotation animation: mobile cameras that move to a new signed site each week, drawn each month by stratified sampling, covering the whole 2022 High Injury Network plus one site in every SF school's zone, with the coverage they build over a year, written to scratch/embeds/speed-camera-rotation/index.html.

Run from the repo root: python3 scripts/speed-camera-rotation.py. Needs node (for MAP_HEAD and to run the
simulation once for the printed figures). Writes one gitignored HTML file and prints the figures the post quotes.

INPUTS, all read-only:
- data/extract/access/hin-2022.json: SFMTA's 2022 High Injury Network, the layer the brief's 4% is measured on
  (fetched 2026-09-30 by scripts/access-inputs.py).
- data/extract/speed-cameras/camera-injuries.json: the 33 fixed camera locations, one point each.
- DataSF 7e7j-59qk, Schools (CDE's list, public and private): .cache/stop-destinations/schools.json, fetched
  from https://data.sfgov.org/resource/7e7j-59qk.json when the cache is missing. Active rows with coordinates.

METHOD.
- Distances in feet on a flat projection at SF's latitude, as scratch/runs/articles/speed-cameras-estimate.py
  does for the brief's "6.2 of 159.5 miles" (4%), which this script reproduces and asserts.
- The network is sampled every 25 ft or less. A site "covers" network within 300 ft of it, the brief's measure.
- HIN sites: candidates every 100 ft along each block, then a greedy set cover picks the fewest that put every
  sampled foot of the network within 300 ft of a site. "Hundreds of sites covering the whole High Injury Network"
  is the brief's ask; the cover is what "whole" takes at 300 ft.
- School sites: state law allows cameras in school zones, whose signs may stand up to 500 ft from school grounds
  (Veh. Code §22425(b)(1)(C), §22352(b)(2), per research/notes/speed-cameras-2026-10/2026-11-12-mobile-rotation-
  legal-check.md). A school with an HIN site within 300 ft of its point shares it; every other school gets its
  own site at its point. The camera stands on the nearest street, which this sketch doesn't place.
- Stratified sampling, redrawn each month (Bryan, 2026-11-16: "let's do stratified sampling every month"). The
  strata are supervisor district (site/data/supervisor-districts.json) crossed with network site or school-only
  site. Each month's K x (weeks starting in it) placements are split across strata in proportion to their sites (largest
  remainder). Within a stratum, sites come off a shuffled queue that refills when it runs out, so every site is
  visited before any repeats. The month's placements are then shuffled and dealt K a week, with no site twice in a week. A camera stays
  at its site all week (Bryan, 2026-11-16: "assume 100 mobile cameras that move every week").
  Seeded mulberry32, so every run and every browser shows the same days. No equity or speeding weighting yet:
  the brief leaves that tuning to the program, and the strata are where it would go.
- Months are calendar months from day 1 (31, 28, 31, ... days); the animation still steps a day at a time.
- State routes (19th Avenue and others) are on the network and are kept; the law bars cameras there today.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import heapq
import json
import math
import os
import subprocess
import sys
import urllib.request

ROOT = paths.ROOT
P = lambda *a: os.path.join(ROOT, *a)
sys.path.insert(0, paths.LIB)
from lib.stable import write_text  # noqa: E402

HIN = P("data/extract/access/hin-2022.json")
CAMS = P("data/extract/speed-cameras/camera-injuries.json")
SCHOOLS_CACHE = P(".cache/stop-destinations/schools.json")
SCHOOLS_URL = "https://data.sfgov.org/resource/7e7j-59qk.json?$limit=5000"
OUT = P("scratch/embeds/speed-camera-rotation/index.html")

R = 300.0          # feet: "within 300 feet", the brief's coverage measure
STEP = 25.0        # feet between network samples
CAND = 100.0       # feet between candidate sites
DAYS = 365
MONTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
SEED = 20270320    # the day mobile units become legal for SF, about 20 March 2027
K_DEFAULT = 100    # Bryan, 2026-11-16: "assume 100 mobile cameras". The slider runs to one camera per site.
FT = 364000.0
COS = math.cos(math.radians(37.76))


def xy(lon, lat):
    return (lon * FT * COS, lat * FT)


def check(ok, msg):
    if not ok:
        sys.exit(f"speed-camera-rotation: {msg}")


class Grid:
    def __init__(self, pts, cell=R):
        self.c, self.g = cell, {}
        for i, (x, y) in enumerate(pts):
            self.g.setdefault((int(x // cell), int(y // cell)), []).append(i)

    def near(self, x, y):
        cx, cy = int(x // self.c), int(y // self.c)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from self.g.get((cx + dx, cy + dy), ())


def schools():
    if not os.path.exists(SCHOOLS_CACHE):
        os.makedirs(os.path.dirname(SCHOOLS_CACHE), exist_ok=True)
        with urllib.request.urlopen(SCHOOLS_URL, timeout=60) as r:
            open(SCHOOLS_CACHE, "wb").write(r.read())
    out = []
    for r in json.load(open(SCHOOLS_CACHE)):
        if r.get("status") != "Active":
            continue
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            continue  # "Information Redacted"
        out.append({"name": r["school"].strip(), "public": bool(r.get("public_yesno")), "lon": lon, "lat": lat})
    out.sort(key=lambda s: (s["name"], s["lon"], s["lat"]))
    return out


# The simulation, shared by the page and by node for the printed figures. Deterministic for a given (K, seed).
SIM = r"""
function rng(a){return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function plan(D,K,days,seed){
 var N=D.siteCover.length,r=rng(seed+K),S=D.strata.length,queues=[],members=[],i,j,m,out=new Array(days),d0=0;
 for(i=0;i<S;i++){members.push([]);queues.push([])}
 for(i=0;i<N;i++)members[D.stratum[i]].push(i);
 function shuffle(a){for(var i=a.length-1;i>0;i--){var j=Math.floor(r()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
 function take(s){if(!queues[s].length)queues[s]=shuffle(members[s].slice());return queues[s].pop()}
 for(m=0;d0<days;m++){
  var len=Math.min(D.months[m%12],days-d0),wk=[];
  for(var w=Math.ceil(d0/7)*7;w<d0+len;w+=7)wk.push(w);
  var V=K*wk.length,quota=[],rem=[],used=0;
  for(i=0;i<S;i++){var q=V*members[i].length/N;quota.push(Math.floor(q));rem.push([q-Math.floor(q),i]);used+=Math.floor(q)}
  rem.sort(function(a,b){return b[0]-a[0]||a[1]-b[1]});for(i=0;used<V;i++,used++)quota[rem[i%S][1]]++;
  var month=[];for(i=0;i<S;i++)for(j=0;j<quota[i];j++)month.push(take(i));
  shuffle(month);
  for(var wi=0;wi<wk.length;wi++){
   var today=[],seen={};
   for(j=wi*K;j<(wi+1)*K&&j<month.length;j++){
    for(var k=j+1;seen[month[j]]&&k<month.length;k++){if(!seen[month[k]]){var t=month[j];month[j]=month[k];month[k]=t}}
    if(!seen[month[j]]){seen[month[j]]=1;today.push(month[j])}
   }
   today.sort(function(a,b){return a-b});
   for(var dd=wk[wi];dd<Math.min(wk[wi]+7,days);dd++)out[dd]=today;
  }
  d0+=len;
 }
 return out;
}
function simulate(D,K,days,seed){
 var N=D.siteCover.length,i,d,p,P=plan(D,K,days,seed);
 var c7=new Uint16Array(D.w.length),c30=new Uint16Array(D.w.length),ev=new Uint8Array(D.w.length),tot=0,l7=0,l30=0,lev=0;
 for(i=0;i<D.w.length;i++)tot+=D.w[i];
 var on=new Uint16Array(N),q10=[],q50=[],q90=[],last=new Int32Array(N).fill(-1e9),visits=[],h7=[],h30=[],hev=[],s7=[],s30=[],sev=[],sEver=new Uint8Array(D.schoolSite.length);
 function add(cnt,site,dlt){var cv=D.siteCover[site],q,s=0;for(q=0;q<cv.length;q++){p=cv[q];if(dlt>0){if(cnt[p]++===0)s+=D.w[p]}else{if(--cnt[p]===0)s-=D.w[p]}}return s}
 for(d=0;d<days;d++){
  var today=P[d];visits.push(today);
  for(i=0;i<today.length;i++)on[today[i]]++;
  var sh=Array.from(on).sort(function(a,b){return a-b});
  q10.push(sh[Math.floor(.1*(N-1))]/(d+1));q50.push(sh[Math.floor(.5*(N-1))]/(d+1));q90.push(sh[Math.floor(.9*(N-1))]/(d+1));
  today.forEach(function(s){l7+=add(c7,s,1);l30+=add(c30,s,1);last[s]=d;var cv=D.siteCover[s];for(var q=0;q<cv.length;q++){if(!ev[cv[q]]){ev[cv[q]]=1;lev+=D.w[cv[q]]}}});
  if(d>=7)visits[d-7].forEach(function(s){l7+=add(c7,s,-1)});
  if(d>=30)visits[d-30].forEach(function(s){l30+=add(c30,s,-1)});
  var n7=0,n30=0,nev=0;
  for(i=0;i<D.schoolSite.length;i++){var a=d-last[D.schoolSite[i]];if(a<7)n7++;if(a<30)n30++;if(a===0)sEver[i]=1;nev+=sEver[i]}
  h7.push(l7/tot);h30.push(l30/tot);hev.push(lev/tot);s7.push(n7/D.schoolSite.length);s30.push(n30/D.schoolSite.length);sev.push(nev/D.schoolSite.length);
 }
 return {visits:visits,on:on,q10:q10,q50:q50,q90:q90,h7:h7,h30:h30,hev:hev,s7:s7,s30:s30,sev:sev};
}
"""

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Speed cameras sent at random: how much of the High Injury Network they reach</title>
<!-- Written by tools/street-safety/speed-camera-rotation.py. Do not edit by hand. -->
<style>
:root{--ink:#15181c;--muted:#59626f;--line:#dde1e6;--cam:#4269d0;--fixed:#efb118;--pub:#3ca951;--priv:#a463f2;--w7:#1c3a85;--w30:#4269d0;--wev:#a9c0ee}
body{margin:0;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:#fff}
#wrap{padding:6px 10px 10px;max-width:1340px}
.stats{display:flex;flex-wrap:wrap;gap:4px 22px;align-items:baseline;margin:0 0 6px}
.stat b{font-size:22px;font-weight:700;margin-right:4px}
.stat span{color:var(--muted);font-size:13px}
.ctl{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin:0 0 6px;font-size:13px}
.ctl button{font:inherit;font-size:13px;padding:3px 12px;border:1px solid var(--ink);border-radius:14px;background:var(--ink);color:#fff;cursor:pointer;min-height:30px;min-width:74px}
.ctl label{display:flex;align-items:center;gap:6px}
.ctl input[type=range]{width:180px}
#day{color:var(--muted);font-variant-numeric:tabular-nums}
.row{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,1fr);gap:12px}
.glmap{height:560px;border:1px solid var(--line);border-radius:4px}
.key{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12px;color:var(--muted);margin:4px 0 0}
.key span{display:inline-flex;align-items:center;gap:4px}
.sw{display:inline-block;flex:none;border-radius:50%;width:10px;height:10px}
h3{margin:2px 0 0;font-size:13px}
.sub{color:var(--muted);font-size:12px;margin:0}
.chart svg{display:block;overflow:visible}
.maplibregl-popup-content{font-size:13px;padding:6px 9px;line-height:1.35}
@media (max-width:760px){.row{grid-template-columns:1fr}.glmap{height:300px}.stat b{font-size:19px}.ctl input[type=range]{width:130px}}
</style>
__HEAD__
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6"></script>
</head><body>
<div id="wrap">
 <div class="stats">
  <div class="stat"><b id="sH"></b><span>how often each site has a camera over the year, on average</span></div>
  <div class="stat"><b id="sS"></b><span>the least-covered site's share of days over the year (most: <span id="sM"></span>)</span></div>
  <div class="stat"><b id="sG"></b><span>cameras for 1 day in 10 at every site (<span id="sG5"></span> for 1 day in 5)</span></div>
 </div>
 <div class="ctl">
  <button id="play" type="button">Pause</button>
  <label for="k">Mobile cameras <input id="k" type="range" min="1" max="__KMAX__" step="1" value="__KDEF__"> <b id="kv"></b></label>
  <span id="day"></span>
 </div>
 <div class="row">
  <div><div class="glmap" id="m" role="application" aria-label="Map of camera sites on the High Injury Network and at schools"></div>
   <div class="key"><span><i class="sw" style="background:var(--cam)"></i>Mobile camera (fades over 30 days after it moves)</span><span><i class="sw" style="background:#fff;border:1.5px solid #9498a0;width:7px;height:7px"></i>Signed site</span><span><i class="sw" style="background:var(--fixed);border:1px solid var(--ink);border-radius:2px"></i>Fixed camera today</span><span><i class="sw" style="background:var(--pub)"></i>Public school</span><span><i class="sw" style="background:var(--priv)"></i>Private school</span></div></div>
  <div>
   <h3>How often each site has a camera over the year</h3><p class="sub">Sites by share of days with a mobile camera at the current setting. Dashed: 1 day in 10 and 1 day in 5</p><div class="chart" id="c1"></div>
   <p class="sub" id="note"></p>
  </div>
 </div>
</div>
<script>
const D=__DATA__;
__SIM__
const $=s=>document.querySelector(s);
const pct=v=>(100*v<10?(100*v).toFixed(1):Math.round(100*v))+"%";
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const N=D.siteCover.length;
$("#note").textContent=`${N.toLocaleString("en-US")} signed sites: ${D.nHin.toLocaleString("en-US")} cover every block of the network, ${D.nSchoolOnly} more stand at schools off it. ${D.nSchools} schools, ${D.nPublic} public and ${D.nSchools-D.nPublic} private. Each camera stays a week at its site. Each month, sites are drawn by stratified sampling: every supervisor district gets cameras in proportion to its sites, and no site repeats until its district's others have had a turn. The High Injury Network is the 2022 layer.`;
let K=+$("#k").value,S=simulate(D,K,D.days,D.seed),day=0,timer=null,map=null,shown=-1;
const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
function share(el){
 // Year-end share of days with a camera, one bar per 1% band. A site's running share jumps between 0 and a
 // spike until it has had several turns, so the chart shows the whole year rather than the share so far.
 const w=el.clientWidth||320,phone=w<420,H=phone?170:210;
 const yr=Array.from(S.on).map(v=>v/D.days),top=Math.max(.25,Math.ceil(Math.max(...yr)*20)/20);
 el.replaceChildren(Plot.plot({width:w,height:H,marginLeft:40,marginRight:12,marginTop:18,marginBottom:30,
  x:{domain:[0,top],tickFormat:v=>Math.round(v*100)+"%",label:"Share of days with a camera",labelAnchor:"center",labelArrow:"none"},
  y:{label:"Sites",grid:true,labelArrow:"none"},
  style:{fontSize:"11px",color:"#59626f"},
  marks:[Plot.rectY(yr,Plot.binX({y:"count"},{x:v=>v,thresholds:Array.from({length:Math.round(top*100)+1},(_,i)=>i/100),fill:"var(--w7)",inset:.5})),
   Plot.ruleY([0],{stroke:"#dde1e6"}),
   Plot.ruleX([.1,.2],{stroke:"#59626f",strokeDasharray:"4,3"}),
   Plot.text([{x:.1,t:"1 day in 10"},{x:.2,t:"1 day in 5"}],{x:"x",text:"t",frameAnchor:"top",dy:-12,fill:"#59626f",fontSize:11})]}));
}
function chart(el,lines,fixed){
 const w=el.clientWidth||320,phone=w<420;
 const data=[];lines.forEach(([k,label,col])=>{for(let d=0;d<=day;d++)data.push({d:d+1,v:S[k][d],k:label,col})});
 const H=phone?150:178,ppu=H-36,gap=13/ppu;
 // Line-end labels, nudged apart so equal values don't print on top of each other.
 const ends=lines.map(([k,label,col])=>({d:day+1,v:S[k][day],y:S[k][day],k:label,col})).sort((a,b)=>a.y-b.y);
 for(let i=1;i<ends.length;i++)if(ends[i].y-ends[i-1].y<gap)ends[i].y=ends[i-1].y+gap;
 const marks=[Plot.ruleY([0],{stroke:"#dde1e6"}),
  Plot.line(data,{x:"d",y:"v",z:"k",stroke:"col",strokeWidth:2}),
  Plot.text(ends,{x:"d",y:"y",text:d=>`${d.k} ${pct(d.v)}`,fill:"col",dx:6,textAnchor:"start",fontSize:11,fontWeight:600})];
 if(fixed!=null)marks.push(Plot.ruleY([fixed],{stroke:"#59626f",strokeDasharray:"4,3"}));
 el.replaceChildren(Plot.plot({width:w,height:H,marginLeft:36,marginRight:phone?92:98,marginTop:10,marginBottom:26,
  x:{domain:[1,D.days],label:"Month",ticks:D.monthStarts,tickFormat:d=>String(D.monthStarts.indexOf(d)+1)},y:{domain:[0,1],tickFormat:v=>Math.round(v*100)+"%",ticks:5,label:null,grid:true},
  style:{fontSize:"11px",color:"#59626f"},marks}));
}
function draw(){
 const yr=Array.from(S.on).map(v=>v/D.days),avg=K*7/(N*7),lo=Math.min(...yr),hi=Math.max(...yr);
 const inN=v=>v>0?`1 day in ${Math.round(1/v)}`:"never";
 $("#sH").textContent=inN(K/N);$("#sS").textContent=inN(lo);$("#sM").textContent=inN(hi);
 $("#sG").textContent=Math.ceil(N/10).toLocaleString("en-US");$("#sG5").textContent=Math.ceil(N/5).toLocaleString("en-US");
 $("#kv").textContent=K;{let m=0;while(m<11&&day+1>=D.monthStarts[m+1])m++;$("#day").textContent=`Month ${m+1}, day ${day+1-D.monthStarts[m]+1}`;}
 share($("#c1"));
 paintMap();
}
function paintMap(){
 if(!map||!map.getLayer("lit"))return;
 if(shown>day){for(let s=0;s<N;s++)map.removeFeatureState({source:"sites",id:s});shown=-1}
 for(let d=shown+1;d<=day;d++)S.visits[d].forEach(s=>map.setFeatureState({source:"sites",id:s},{last:d}));
 shown=day;
 const age=["-",day,["coalesce",["feature-state","last"],-1e6]];
 const op=["case",[">",age,29],0,["-",0.9,["*",0.025,age]]];
 map.setPaintProperty("lit","circle-opacity",op);map.setPaintProperty("lit","circle-stroke-opacity",op);
 map.setPaintProperty("today","circle-stroke-opacity",["case",["==",age,0],1,0]);
}
function stop(){clearInterval(timer);timer=null;$("#play").textContent=day>=D.days-1?"Replay":"Play"}
function play(){if(day>=D.days-1){day=0;}timer=setInterval(()=>{if(day>=D.days-1){stop();return}day++;draw()},80);$("#play").textContent="Pause";draw()}
$("#play").addEventListener("click",()=>timer?stop():play());
$("#k").addEventListener("input",()=>{K=+$("#k").value;S=simulate(D,K,D.days,D.seed);shown=1e9;paintMap();draw()});
const sites={type:"FeatureCollection",features:D.sites.map((p,i)=>({type:"Feature",id:i,properties:{i,school:p[2]},geometry:{type:"Point",coordinates:[p[0],p[1]]}}))};
const hin={type:"FeatureCollection",features:D.hin.map(c=>({type:"Feature",properties:{},geometry:{type:"LineString",coordinates:c}}))};
const sch={type:"FeatureCollection",features:D.schools.map(s=>({type:"Feature",properties:{name:s[2],pub:s[3]},geometry:{type:"Point",coordinates:[s[0],s[1]]}}))};
const fx={type:"FeatureCollection",features:D.fixed.map(c=>({type:"Feature",properties:{name:c[2]},geometry:{type:"Point",coordinates:[c[0],c[1]]}}))};
// 300 ft to scale from zoom 14 in; drawn larger below that so a visit shows at city scale.
const R300=["interpolate",["exponential",2],["zoom"],10,4,13,6.5,14,12,18,192];
// On a phone the map controls sit across the top, so the city starts below them.
const pad=()=>innerWidth<760?{top:44,bottom:18,left:8,right:8}:{top:12,bottom:12,left:12,right:12};
map=sfMap.create($("#m"),{bounds:D.bounds,padding:pad});
if(map)map.on("load",()=>{
 map.resize();map.fitBounds(D.bounds,{padding:pad(),duration:0});
 map.addSource("hin",{type:"geojson",data:hin});
 map.addSource("sites",{type:"geojson",data:sites});
 map.addSource("sch",{type:"geojson",data:sch});
 map.addSource("fx",{type:"geojson",data:fx});
 map.addLayer({id:"hin",type:"line",source:"hin",layout:{"line-cap":"round"},paint:{"line-color":"#59626f","line-width":["interpolate",["linear"],["zoom"],11,1,15,3],"line-opacity":0.55}});
 map.addLayer({id:"site",type:"circle",source:"sites",minzoom:13,paint:{"circle-radius":2.5,"circle-color":"#fff","circle-stroke-color":"#9498a0","circle-stroke-width":1}});
 map.addLayer({id:"lit",type:"circle",source:"sites",paint:{"circle-radius":R300,"circle-color":"#4269d0","circle-opacity":0,"circle-stroke-color":"#fff","circle-stroke-width":0.5,"circle-stroke-opacity":0}});
 map.addLayer({id:"today",type:"circle",source:"sites",paint:{"circle-radius":R300,"circle-color":"rgba(0,0,0,0)","circle-stroke-color":"#15181c","circle-stroke-width":1.5,"circle-stroke-opacity":0}});
 map.addLayer({id:"sch",type:"circle",source:"sch",paint:{"circle-radius":["interpolate",["linear"],["zoom"],11,2.6,15,5],"circle-color":["case",["get","pub"],"#3ca951","#a463f2"],"circle-stroke-color":"#fff","circle-stroke-width":0.8}});
 map.addLayer({id:"fx",type:"circle",source:"fx",paint:{"circle-radius":["interpolate",["linear"],["zoom"],11,2.8,15,5.5],"circle-color":"#efb118","circle-stroke-color":"#59626f","circle-stroke-width":0.8}});
 const pop=new maplibregl.Popup({focusAfterOpen:false,maxWidth:"240px"});
 map.on("click",e=>{const f=sfMap.near(map,e.point,["fx","sch","lit","site"])[0];if(!f){pop.remove();return}
  let h;if(f.layer.id==="fx")h=`<b>Fixed camera</b><br>${esc(f.properties.name)}`;
  else if(f.layer.id==="sch")h=`<b>${esc(f.properties.name)}</b><br>${f.properties.pub?"Public":"Private"} school`;
  else{const st=map.getFeatureState({source:"sites",id:f.id});h=`<b>Signed site${f.properties.school?" at a school":""}</b><br>${st.last!=null?`Last mobile camera: day ${st.last+1}`:"No mobile camera yet"}`}
  pop.setLngLat(e.lngLat).setHTML(h).addTo(map)});
 shown=-1;paintMap();
});
const qd=+new URLSearchParams(location.search).get("day");
if(qd>0){day=Math.min(qd,D.days)-1;draw();stop()}else if(reduce){day=D.days-1;draw();stop()}else play();
let lastH=0;
function height(){const h=Math.ceil($("#wrap").getBoundingClientRect().height)+10;if(Math.abs(h-lastH)<2)return;lastH=h;
 try{parent.postMessage({type:"sfworks:height",block:new URLSearchParams(location.search).get("block")||"speed-camera-rotation",height:h},"*")}catch(e){}}
height();addEventListener("load",height);new ResizeObserver(height).observe($("#wrap"));
addEventListener("resize",()=>draw());
</script></body></html>"""


def inside(x, y, ring):
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def strata_for(sites, n_hin):
    """Supervisor district x (network site, school-only site). A site in no district polygon (a pier, say) takes
    the district with the nearest vertex."""
    dd = json.load(open(P("site/data/supervisor-districts.json")))["districts"]
    check(len(dd) == 11, f"{len(dd)} districts, expected 11")
    polys = []
    for d in dd:
        c = d["coords"]
        rings = [poly[0] for poly in c] if isinstance(c[0][0][0], list) else [c[0]]
        polys.append((d["district"], rings))
    names, idx, out = [], {}, []
    for i, (lon, lat, _) in enumerate(sites):
        hit = next((dn for dn, rings in polys if any(inside(lon, lat, r) for r in rings)), None)
        if hit is None:
            hit = min(polys, key=lambda pr: min(math.dist((lon, lat), v) for r in pr[1] for v in r))[0]
        key = f"D{hit} {'network' if i < n_hin else 'school'}"
        if key not in idx:
            idx[key] = len(names); names.append(key)
        out.append(idx[key])
    order = sorted(range(len(names)), key=lambda k: (int(names[k].split()[0][1:]), names[k]))
    remap = {old: new for new, old in enumerate(order)}
    return [remap[x] for x in out], [names[k] for k in order]


def main():
    hin = json.load(open(HIN))["records"]
    check(len(hin) > 2000, f"only {len(hin)} HIN records")
    cams = json.load(open(CAMS))["rows"]
    check(len(cams) == 33, f"{len(cams)} fixed camera locations, expected 33")

    # Network samples and candidate sites.
    samp, w, cand, cand_ll, lines = [], [], [], [], []
    for rec in sorted(hin, key=lambda r: r["id"]):
        lines.append([[round(x, 5), round(y, 5)] for x, y in rec["pts"]])
        pts = [xy(*p) for p in rec["pts"]]
        run = 0.0
        for (a, la), (b, lb) in zip(zip(pts, rec["pts"]), zip(pts[1:], rec["pts"][1:])):
            L = math.dist(a, b)
            k = max(1, math.ceil(L / STEP))
            for i in range(k):
                t = (i + .5) / k
                samp.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                w.append(L / k)
            # candidates every CAND ft along the block, starting at its first vertex
            s = (CAND - run % CAND) % CAND if run else 0.0
            while s <= L:
                t = s / L if L else 0
                cand.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                cand_ll.append((la[0] + (lb[0] - la[0]) * t, la[1] + (lb[1] - la[1]) * t))
                s += CAND
            run += L
        cand.append(pts[-1]); cand_ll.append(tuple(rec["pts"][-1]))
    total = sum(w)
    sg = Grid(samp)

    def cover(x, y):
        return [i for i in sg.near(x, y) if math.dist(samp[i], (x, y)) <= R]

    # The brief's figure: 6.2 of 159.5 miles within 300 ft of today's 33 locations.
    fixed_pts = set()
    for c in cams:
        fixed_pts.update(cover(*xy(c["lon"], c["lat"])))
    fixed_share = sum(w[i] for i in fixed_pts) / total
    print(f"HIN {total/5280:.1f} mi; fixed cameras cover {sum(w[i] for i in fixed_pts)/5280:.1f} mi ({fixed_share:.1%})")
    check(abs(total / 5280 - 159.5) < 1.0 and abs(fixed_share - 0.039) < 0.004, "doesn't reproduce the brief's 6.2 of 159.5 miles")

    # Greedy set cover (lazy), ties to the lower candidate index so the result is stable.
    cov = [cover(*c) for c in cand]
    done = bytearray(len(samp))
    heap = [(-sum(w[i] for i in cv), j) for j, cv in enumerate(cov)]
    heapq.heapify(heap)
    chosen, left = [], total
    while heap and left > 1e-6:
        g, j = heapq.heappop(heap)
        gain = sum(w[i] for i in cov[j] if not done[i])
        if gain <= 1e-9:
            continue
        if heap and -heap[0][0] > gain + 1e-9:
            heapq.heappush(heap, (-gain, j))
            continue
        chosen.append(j)
        for i in cov[j]:
            if not done[i]:
                done[i] = 1
                left -= w[i]
    check(all(done), "network not fully covered")
    chosen.sort()
    sites = [[round(cand_ll[j][0], 5), round(cand_ll[j][1], 5), 0] for j in chosen]
    site_xy = [cand[j] for j in chosen]
    site_cover = [sorted(cov[j]) for j in chosen]
    n_hin = len(sites)

    # Schools: share an HIN site within 300 ft, or get their own.
    sch = schools()
    check(len(sch) >= 220, f"only {len(sch)} schools")
    hg = Grid(site_xy)
    school_site = []
    for s in sch:
        p = xy(s["lon"], s["lat"])
        best = min(((math.dist(site_xy[i], p), i) for i in hg.near(*p) if math.dist(site_xy[i], p) <= R), default=None)
        if best:
            school_site.append(best[1]); sites[best[1]][2] = 1
        else:
            school_site.append(len(sites))
            sites.append([round(s["lon"], 5), round(s["lat"], 5), 1])
            site_cover.append(cover(*p))
    n_school_only = len(sites) - n_hin
    n_pub = sum(s["public"] for s in sch)
    print(f"sites: {n_hin} on the network + {n_school_only} at schools off it = {len(sites)}; schools {len(sch)} ({n_pub} public, {len(sch)-n_pub} private)")

    stratum, strata = strata_for(sites, n_hin)
    print("strata:", ", ".join(f"{n} {sum(1 for x in stratum if x == i)}" for i, n in enumerate(strata)))

    allx = [p[0] for l in lines for p in l]; ally = [p[1] for l in lines for p in l]
    allx += [s["lon"] for s in sch]; ally += [s["lat"] for s in sch]
    data = {
        "days": DAYS, "seed": SEED, "fixedShare": round(fixed_share, 4),
        "months": MONTHS, "monthStarts": [1 + sum(MONTHS[:i]) for i in range(12)],
        "stratum": stratum, "strata": strata,
        "nHin": n_hin, "nSchoolOnly": n_school_only, "nSchools": len(sch), "nPublic": n_pub,
        "bounds": [[round(min(allx), 4), round(min(ally), 4)], [round(max(allx), 4), round(max(ally), 4)]],
        "w": [round(x, 1) for x in w], "siteCover": site_cover, "schoolSite": school_site, "sites": sites,
        "hin": lines,
        "schools": [[round(s["lon"], 5), round(s["lat"], 5), s["name"], s["public"]] for s in sch],
        "fixed": [[round(c["lon"], 5), round(c["lat"], 5), c["label"]] for c in cams],
    }
    js = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")

    # Figures for the post, from the same simulation the page runs.
    probe = SIM + "\nconst D=JSON.parse(require('fs').readFileSync(0,'utf8'));for(const K of [33,100,200]){const S=simulate(D,K,D.days,D.seed);" \
        "console.log(JSON.stringify({K,gap:Math.round(D.siteCover.length/K),lo:Math.min(...S.on)/D.days,hi:Math.max(...S.on)/D.days,avg:K/D.siteCover.length,hev_365:S.hev[364],sev_365:S.sev[364]}))}"
    res = subprocess.run(["node", "-e", probe], input=json.dumps(data), capture_output=True, text=True, check=True)
    for line in res.stdout.split("\n"):
        if line:
            r = json.loads(line)
            print("K=%(K)d: a site every %(gap)d weeks; share of days per site over the year: average %(avg).1f%%, least %(lo).1f%%, most %(hi).1f%%; "
                  "by day 365 the network ever reached %(hev_365).1f%%, schools %(sev_365).1f%%"
                  % {k: (v * 100 if k != "K" and k != "gap" else v) for k, v in r.items()})
    print(f"cameras for every site 1 day in 10: {math.ceil(len(sites)/10)}; 1 day in 5: {math.ceil(len(sites)/5)}")

    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_MAPS_KEY"}  # board frames refuse Google tiles
    head = subprocess.run(["node", "--input-type=module", "-e",
                           "import {MAP_HEAD} from './site/src/maplibre.mjs'; process.stdout.write(MAP_HEAD)"],
                          cwd=ROOT, capture_output=True, text=True, check=True, env=env).stdout
    html = (TEMPLATE.replace("__HEAD__", head).replace("__SIM__", SIM).replace("__KMAX__", str(len(sites)))
            .replace("__KDEF__", str(K_DEFAULT)).replace("__DATA__", js))
    write_text(OUT, html)
    print("wrote", os.path.relpath(OUT, ROOT), f"({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
