/* Mapa světa s událostmi - přehled monitorů. Načítá data.json monitorů (typ "t"). */
(function(){
  var grid=document.getElementById("grid");
  if(!grid||typeof M==="undefined")return;
  var BASE="/Redsea-monitor/";
  var COL={STABLE:"#6a9b6e",MEDIUM:"#b8863b",HIGH:"#c07a3a",CRITICAL:"#a13d2b"};
  var RANK={STABLE:0,MEDIUM:1,HIGH:2,CRITICAL:3};
  var LBL={STABLE:"stabilní",MEDIUM:"střední",HIGH:"vysoká",CRITICAL:"kritická"};

  var st=document.createElement("style");
  st.textContent="#wm{margin-top:34px}#wm h2{font-size:1.25em;margin:0 0 10px}"+
   "#wmap{height:420px;border:1px solid var(--rule);border-radius:2px;background:var(--ink2)}"+
   "#wmnote{margin-top:8px;font-family:'IBM Plex Mono',monospace;font-size:.7em;color:var(--text-dim);line-height:1.6}"+
   ".wmpop{font-family:'Spectral',Georgia,serif;font-size:13px;line-height:1.4;max-width:260px}"+
   ".wmpop b{font-size:14px}.wmpop .m{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#666;margin-top:6px}"+
   ".wmpop a{color:#7a5412;text-decoration:none;display:block;margin:2px 0}.wmpop a:hover{text-decoration:underline}"+
   ".wm-dark .leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.85) contrast(.9) saturate(.5)}"+
   "@media (max-width:600px){#wmap{height:340px}}";
  document.head.appendChild(st);

  var sec=document.createElement("section");
  sec.id="wm";
  sec.innerHTML='<h2>Mapa událostí</h2><div id="wmap"></div><div id="wmnote">Načítání mapy…</div>';
  grid.parentNode.insertBefore(sec,grid.nextSibling);

  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
  function plain(s){return String(s||"").replace(/<[^>]*>/g," ")}
  function lvlKey(d){
    return String((d.assessment&&d.assessment.threat_level)||"").split(" ")[0].split("/")[0].trim().toUpperCase();
  }

  var mons=M.filter(function(m){return m.type==="t"});
  Promise.all(mons.map(function(m){
    return fetch(BASE+m.data,{cache:"no-store"}).then(function(r){return r.json()}).catch(function(){return null});
  })).then(function(res){
    var pts={},nEv=0,nMon=0;
    res.forEach(function(d,i){
      if(!d||!d.locations||!d.locations.length)return;
      nMon++;
      var m=mons[i],lv=lvlKey(d),arts=d.articles||[];
      var hay=arts.map(function(a){return{a:a,t:(a.title+" "+plain(a.summary)).toLowerCase()}});
      d.locations.forEach(function(l){
        if(typeof l.lat!=="number"||typeof l.lon!=="number")return;
        var terms=[l.key,l.name_en].filter(Boolean).map(function(x){return String(x).toLowerCase()});
        var hits=hay.filter(function(h){return terms.some(function(t){return h.t.indexOf(t)>-1})}).map(function(h){return h.a});
        var id=l.lat.toFixed(1)+","+l.lon.toFixed(1);
        var p=pts[id]||(pts[id]={lat:l.lat,lon:l.lon,name:l.name_cs||l.key,items:[],seen:{},lv:"",mons:{}});
        if(hits.length){p.mons[m.name]=1;if(!p.lv||(RANK[lv]||0)>(RANK[p.lv]||0))p.lv=lv}
        hits.forEach(function(a){
          if(p.seen[a.link])return;p.seen[a.link]=1;
          p.items.push({t:a.title,l:a.link,s:a.source,d:new Date(a.published),m:m.name});
        });
      });
    });
    var list=Object.keys(pts).map(function(k){return pts[k]}).filter(function(p){return p.items.length});
    if(!list.length){document.getElementById("wmnote").textContent="Mapu se nepodařilo sestavit - monitory neobsahují lokality s událostmi.";return}
    list.forEach(function(p){
      p.items.sort(function(a,b){return (b.d||0)-(a.d||0)});nEv+=p.items.length;
    });

    function init(){
      var light=document.body.classList.contains("light");
      var map=L.map("wmap",{minZoom:2,worldCopyJump:true,scrollWheelZoom:false}).setView([25,30],2);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{
        attribution:"&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>",maxZoom:8}).addTo(map);
      if(!light)document.getElementById("wmap").classList.add("wm-dark");
      var b=[];
      list.forEach(function(p){
        var c=COL[p.lv]||"#b8863b";
        var r=7+Math.min(14,3*Math.sqrt(p.items.length));
        var h='<div class="wmpop"><b>'+esc(p.name)+'</b><div class="m">'+p.items.length+' článků · '+
          Object.keys(p.mons).map(esc).join(", ")+(p.lv?' · hrozba: '+LBL[p.lv]:'')+'</div>';
        p.items.slice(0,4).forEach(function(it){
          if(!/^https?:\/\//.test(it.l))return;
          h+='<a href="'+esc(it.l)+'" target="_blank" rel="noopener">'+esc(it.t)+'</a>';
        });
        h+='</div>';
        L.circleMarker([p.lat,p.lon],{radius:r,color:c,weight:2,fillColor:c,fillOpacity:.45}).addTo(map).bindPopup(h);
        b.push([p.lat,p.lon]);
      });
      if(b.length>1)map.fitBounds(b,{padding:[30,30],maxZoom:4});
      else if(b.length)map.setView(b[0],4);
      document.getElementById("wmnote").innerHTML=list.length+" míst · "+nEv+" článků z "+nMon+
        " monitorů. Velikost značky = počet článků, barva = nejvyšší úroveň hrozby. Lokalita se páruje podle názvu v titulku a shrnutí zprávy (heuristika, ověřte ve zdroji).";
      setTimeout(function(){map.invalidateSize()},300);
    }
    var css=document.createElement("link");css.rel="stylesheet";
    css.href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";document.head.appendChild(css);
    var js=document.createElement("script");
    js.src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
    js.onload=init;
    js.onerror=function(){document.getElementById("wmnote").textContent="Knihovnu mapy se nepodařilo načíst."};
    document.head.appendChild(js);
  });
})();
