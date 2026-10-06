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
   "#wmap{cursor:zoom-in}#wmap.wm-full{position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:0!important;width:100%!important;height:100vh!important;height:100dvh!important;z-index:100000!important;border:0!important;border-radius:0!important;cursor:grab}"+
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

  /* Vestavěný seznam míst: [název, lat, lon, [hledané výrazy]]. Výraz končící "$" musí být celé slovo. */
  var GAZ=[
   ["Washington, D.C.",38.9,-77.04,["washington dc","washington, d.c.","white house","pentagon","capitol hill","federal reserve"]],
   ["New York",40.71,-74.0,["new york","wall street","nasdaq","nyse","manhattan"]],
   ["Los Angeles",34.05,-118.24,["los angeles","hollywood"]],
   ["San Francisco",37.77,-122.42,["san francisco","silicon valley"]],
   ["Kalifornie",36.8,-119.4,["california"]],
   ["Chicago",41.88,-87.63,["chicago"]],
   ["Texas",31.0,-99.0,["texas","houston","dallas","austin"]],
   ["Florida",27.8,-81.7,["florida","miami"]],
   ["Seattle",47.6,-122.33,["seattle"]],
   ["Boston",42.36,-71.06,["boston"]],
   ["Detroit",42.33,-83.05,["detroit"]],
   ["Atlanta",33.75,-84.39,["atlanta"]],
   ["Arizona",34.2,-111.7,["arizona","phoenix"]],
   ["Las Vegas",36.17,-115.14,["las vegas","nevada"]],
   ["Minneapolis",44.98,-93.27,["minneapolis","minnesota"]],
   ["Philadelphia",39.95,-75.17,["philadelphia","pennsylvania"]],
   ["Aljaška",64.2,-149.5,["alaska"]],
   ["Havaj",20.8,-156.3,["hawaii"]],
   ["Portoriko",18.2,-66.5,["puerto rico"]],
   ["Kanada",56.1,-106.3,["canada","canadian","ottawa","toronto"]],
   ["Mexiko",23.6,-102.5,["mexico","mexican"]],
   ["Kuba",21.5,-79.0,["cuba$","havana"]],
   ["Venezuela",7.0,-66.0,["venezuela","caracas"]],
   ["Brazílie",-14.2,-51.9,["brazil"]],
   ["Argentina",-34.0,-64.0,["argentin","buenos aires"]],
   ["Ukrajina",50.45,30.52,["ukrain$","ukraine","kyiv","kiev"]],
   ["Rusko",55.75,37.62,["russia","moscow","kremlin"]],
   ["Izrael",31.5,34.8,["israel","tel aviv","jerusalem"]],
   ["Gaza",31.4,34.4,["gaza"]],
   ["Írán",32.4,53.7,["iran$","iranian","tehran"]],
   ["Sýrie",34.8,38.9,["syria","damascus"]],
   ["Libanon",33.9,35.9,["lebanon","beirut","hezbollah"]],
   ["Turecko",39.0,35.0,["turkey$","türkiye","turkish","ankara","istanbul"]],
   ["Egypt",26.8,30.8,["egypt","cairo","suez"]],
   ["SAE",24.3,54.4,["uae$","emirates","dubai","abu dhabi"]],
   ["Katar",25.3,51.2,["qatar","doha"]],
   ["Čína",35.9,104.2,["china","chinese","beijing","shanghai"]],
   ["Tchaj-wan",23.7,121.0,["taiwan","taipei"]],
   ["Hongkong",22.3,114.2,["hong kong"]],
   ["Japonsko",36.2,138.3,["japan","tokyo","yen$"]],
   ["Jižní Korea",36.5,127.9,["south korea","seoul"]],
   ["Severní Korea",40.0,127.0,["north korea","pyongyang"]],
   ["Indie",20.6,79.0,["india$","indian$","new delhi","mumbai"]],
   ["Pákistán",30.4,69.3,["pakistan","islamabad"]],
   ["Afghánistán",33.9,67.7,["afghanistan","kabul"]],
   ["Indonésie",-2.5,118.0,["indonesia","borneo","sumatra","jakarta"]],
   ["Singapur",1.35,103.8,["singapore"]],
   ["Austrálie",-25.3,133.8,["australia","sydney","canberra"]],
   ["Londýn",51.5,-0.12,["london","britain","british","uk$","england"]],
   ["Berlín",52.52,13.4,["germany","german$","berlin"]],
   ["Paříž",48.86,2.35,["france","french$","paris$"]],
   ["Řím",41.9,12.5,["italy","italian$","rome$"]],
   ["Madrid",40.4,-3.7,["spain","spanish$","madrid"]],
   ["Varšava",52.23,21.0,["poland","polish$","warsaw"]],
   ["Praha",50.08,14.43,["prague","czech"]],
   ["Brusel",50.85,4.35,["brussels","european commission","european union","eu$"]],
   ["Etiopie",9.1,40.5,["ethiopia","addis ababa","tigray"]],
   ["Súdán",15.5,32.5,["sudan$","khartoum"]],
   ["Somálsko",5.2,46.2,["somalia","mogadishu","somaliland"]],
   ["Eritrea",15.2,39.8,["eritrea","asmara"]],
   ["Džibutsko",11.6,43.1,["djibouti"]],
   ["Jihoafrická republika",-30.6,22.9,["south africa","johannesburg"]],
   ["Nigérie",9.1,8.7,["nigeria","lagos"]]
  ];
  GAZ.forEach(function(g){
    g.re=g[3].map(function(t){
      var ex=/\$$/.test(t);t=t.replace(/\$$/,"").replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
      return new RegExp("(^|[^a-z])"+t+(ex?"([^a-z]|$)":""));
    });
  });

  var mons=M.filter(function(m){return m.type==="t"});
  Promise.all(mons.map(function(m){
    return fetch(BASE+m.data,{cache:"no-store"}).then(function(r){return r.json()}).catch(function(){return null});
  })).then(function(res){
    var pts={},nEv=0,nMon=0;
    res.forEach(function(d,i){
      if(!d)return;
      var m=mons[i],lv=lvlKey(d),arts=d.articles||[],locs=(d.locations||[]).filter(function(l){return typeof l.lat==="number"&&typeof l.lon==="number"});
      var hay=arts.map(function(a){return{a:a,t:(a.title+" "+plain(a.summary)).toLowerCase()}});
      var used=false;
      function add(name,lat,lon,hits){
        if(!hits.length)return;
        var id=lat.toFixed(1)+","+lon.toFixed(1);
        var p=pts[id]||(pts[id]={lat:lat,lon:lon,name:name,items:[],seen:{},lv:"",mons:{}});
        p.mons[m.name]=1;used=true;
        if(!p.lv||(RANK[lv]||0)>(RANK[p.lv]||0))p.lv=lv;
        hits.forEach(function(a){
          if(p.seen[a.link])return;p.seen[a.link]=1;
          p.items.push({t:a.title,l:a.link,s:a.source,d:new Date(a.published),m:m.name});
        });
      }
      locs.forEach(function(l){
        var terms=[l.key,l.name_en].filter(Boolean).map(function(x){return String(x).toLowerCase()});
        add(l.name_cs||l.key,l.lat,l.lon,hay.filter(function(h){return terms.some(function(t){return h.t.indexOf(t)>-1})}).map(function(h){return h.a}));
      });
      GAZ.forEach(function(g){
        if(locs.some(function(l){return Math.abs(l.lat-g[1])<2.5&&Math.abs(l.lon-g[2])<2.5}))return;
        add(g[0],g[1],g[2],hay.filter(function(h){return g.re.some(function(r){return r.test(h.t)})}).map(function(h){return h.a}));
      });
      if(used)nMon++;
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
        L.circleMarker([p.lat,p.lon],{radius:r,color:c,weight:2,fillColor:c,fillOpacity:.45,bubblingMouseEvents:false}).addTo(map).bindPopup(h);
        b.push([p.lat,p.lon]);
      });
      function fit(){
        if(b.length>1)map.fitBounds(b,{padding:[30,30],maxZoom:4});
        else if(b.length)map.setView(b[0],4);
      }
      fit();
      var big=false,el=document.getElementById("wmap"),btn=document.createElement("button");
      btn.textContent="\u2715 Zavřít";
      btn.style.cssText="display:none;position:fixed;top:12px;left:12px;z-index:100001;font:600 13px 'IBM Plex Mono',monospace;padding:10px 14px;background:#142c3a;color:#e7e0cd;border:1px solid #b8863b;border-radius:2px;cursor:pointer";
      document.body.appendChild(btn);
      function setBig(v){
        big=v;el.classList.toggle("wm-full",v);btn.style.display=v?"block":"none";
        document.body.style.overflow=v?"hidden":"";
        if(v)map.scrollWheelZoom.enable();else{map.scrollWheelZoom.disable();map.closePopup()}
        setTimeout(function(){map.invalidateSize();fit()},60);
      }
      map.on("click",function(){if(!big)setBig(true)});
      btn.onclick=function(){setBig(false)};
      document.addEventListener("keydown",function(e){if(e.key==="Escape"&&big)setBig(false)});
      document.getElementById("wmnote").innerHTML=list.length+" míst · "+nEv+" článků z "+nMon+
        " monitorů. Klepnutím na mapu ji zvětšíte. Velikost značky = počet článků, barva = nejvyšší úroveň hrozby. Lokalita se páruje podle názvu v titulku a shrnutí zprávy (heuristika, ověřte ve zdroji).";
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
