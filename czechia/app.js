const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const COL={"ANO":"#2a3f9e","ODS":"#1f6fd1","STAN":"#f28e2b","Piráti":"#4a4a4a","SPD":"#1aa3a3","TOP 09":"#7b3f98","KDU-ČSL":"#d4b800","Motoristé":"#c2185b","Stačilo":"#b71c1c","ČSSD":"#e64a19","KSČM":"#7f0000","Zelení":"#2e9c3d","Přísaha":"#00838f","Svobodní":"#c0ca33","Trikolora":"#8d6e63","Prague Together":"#5c6bc0","Praha Sobě":"#26a69a","Spojené síly pro Prahu":"#1565c0","Naše Praha":"#ab47bc"};
Object.assign(COL,{"Naše Česko":"#e91e63","Spolu pro Prahu":"#0d47a1"});
const col=s=>COL[s]||"#607d8b";
const num=v=>v.toFixed(1).replace(".",",");
let articles=[],parties={},allPromises=[],polls=[],pols={},sum={},info=[];
const TABS=["zpravy","strany","sliby","pruzkumy"];

Promise.all([
  fetch("articles_recent.json").then(r=>r.json()).catch(()=>[]),
  fetch("parties.json").then(r=>r.json()).catch(()=>({strany:{}})),
  fetch("polls.json").then(r=>r.json()).catch(()=>({pruzkumy:[]})),
  fetch("politicians.json").then(r=>r.json()).catch(()=>({politici:{}})),
  fetch("summary.json").then(r=>r.json()).catch(()=>({obdobi:{}})),
  fetch("pruzkumy_info.json").then(r=>r.json()).catch(()=>[])
]).then(([a,p,q,pl,sm,inf])=>{
  articles=a;parties=p.strany||{};polls=q.pruzkumy||[];pols=pl;sum=sm;info=inf||[];
  allPromises=Object.entries(parties).flatMap(([s,d])=>(d.sliby||[]).map(x=>({...x,strana:s})));
  $("upd").textContent=a.length?"Aktualizováno "+new Date(a[0].added+"Z").toLocaleString("cs-CZ",{day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"}):"Zatím bez dat";
  [...new Set(a.flatMap(x=>x.strany||[]))].sort().forEach(s=>$("strana").add(new Option(s,s)));
  Object.keys(parties).sort().forEach(s=>$("sstrana").add(new Option(s,s)));
  [...new Set(allPromises.map(x=>x.tema).filter(Boolean))].sort().forEach(t=>$("stema").add(new Option(t,t)));
  renderSum();renderNews();renderPols();renderParties();renderPromises();fillAgencies();
});

function tab(n){TABS.forEach(t=>{$("v-"+t).hidden=t!==n;$("t-"+t).classList.toggle("on",t===n)});scrollTo(0,0)}
TABS.forEach(t=>$("t-"+t).onclick=()=>tab(t));

function renderSum(){
  const s=(sum.obdobi||{})[$("sum-days").value];
  if(!s){$("sum-body").className="muted";$("sum-body").textContent="Shrnutí zatím není k dispozici.";$("sum-meta").textContent="";return}
  const ul=a=>a&&a.length?`<ul>${a.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:"";
  $("sum-body").className="";
  $("sum-body").innerHTML=`<p>${esc(s.uvod)}</p>
    ${s.praha&&s.praha.length?`<h4>Praha</h4>${ul(s.praha)}`:""}
    ${s.cr&&s.cr.length?`<h4>Celá ČR</h4>${ul(s.cr)}`:""}
    <div>${(s.temata||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join("")}</div>
    ${s.pozn?`<p class="meta">${esc(s.pozn)}</p>`:""}`;
  $("sum-meta").textContent=`Shrnuto ze ${s.pocet} zpráv. Vygenerováno AI, ověřte ve zdrojích.`;
}
$("sum-days").addEventListener("input",renderSum);

function renderNews(){
  const q=$("q").value.toLowerCase(),r=$("region").value,s=$("strana").value;
  const out=articles.filter(a=>(!r||a.region===r)&&(!s||(a.strany||[]).includes(s))&&(!q||(a.title+" "+(a.shrnuti||"")+" "+(a.politici||[]).map(p=>p.jmeno).join(" ")).toLowerCase().includes(q)));
  $("list").innerHTML=out.slice(0,100).map(a=>`<div class="card">
    <a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a>
    <div>${esc(a.shrnuti)}</div>
    <div class="meta">${esc(a.source)} · ${esc(a.published||a.added)}<br>
      <span class="tag">${esc(a.region)}</span>
      ${(a.strany||[]).map(x=>`<span class="tag"><i class="dot" style="background:${col(x)}"></i>${esc(x)}</span>`).join("")}
      <span class="tag">tón: ${esc(a.ton)}</span>
      ${a.overeni?`<span class="tag">ověřeno: ${esc(a.overeni)}</span>`:""}
    </div></div>`).join("")||"Nic nenalezeno.";
}
["q","region","strana"].forEach(id=>$(id).addEventListener("input",renderNews));

function renderPols(){
  const rows=(pols.politici||{})[$("pol-days").value]||[];
  if(!rows.length){$("pol-list").textContent="Zatím bez dat. Žebříček se objeví po dalším běhu.";return}
  const max=rows[0].pocet;
  $("pol-list").innerHTML=rows.map((r,i)=>{
    const t=r.tony||{},s=(t["pozitivní"]||0)+(t["neutrální"]||0)+(t["kritický"]||0)||1;
    const pc=k=>Math.round(100*(t[k]||0)/s);
    return `<div class="row rank">
      <b class="pos">${i+1}.</b>
      <div class="body">
        <div><a href="#" data-pol="${esc(r.jmeno)}">${esc(r.jmeno)}</a>
          ${r.strana?`<span class="tag"><i class="dot" style="background:${col(r.strana)}"></i>${esc(r.strana)}</span>`:""}</div>
        <div class="track"><div class="fill" style="width:${r.pocet/max*100}%;background:${col(r.strana)}"></div></div>
        <div class="legend">tón zpráv: pozitivní ${pc("pozitivní")} % · kritický ${pc("kritický")} %</div>
      </div>
      <b class="cnt">${r.pocet}×</b></div>`}).join("");
}
$("pol-days").addEventListener("input",renderPols);

function renderParties(){
  const list=Object.entries(parties).sort((a,b)=>b[1].pocet-a[1].pocet);
  if(!list.length){$("strany-list").textContent="Profily stran zatím nejsou k dispozici.";return}
  $("strany-list").innerHTML=list.map(([name,d])=>{
    const t=d.tony||{},s=(t["pozitivní"]||0)+(t["neutrální"]||0)+(t["kritický"]||0)||1;
    const pct=k=>Math.round(100*(t[k]||0)/s);
    const ov=Object.entries(d.overeni||{}).map(([k,v])=>`<span class="tag">${esc(k)}: ${v}</span>`).join("");
    return `<div class="card" style="border-left:5px solid ${col(name)}">
      <h2>${esc(name)}</h2>
      <div class="meta">${d.pocet} zpráv (z toho ${d.praha} o Praze) · ${(d.sliby||[]).length} slibů</div>
      ${d.profil?`<p>${esc(d.profil)}</p>`:""}
      ${d.kritika?`<p><b>Nejčastější výhrady:</b> ${esc(d.kritika)}</p>`:""}
      <div class="bar"><i class="p" style="width:${pct("pozitivní")}%"></i><i class="n" style="width:${pct("neutrální")}%"></i><i class="k" style="width:${pct("kritický")}%"></i></div>
      <div class="legend">Mediální tón: pozitivní ${pct("pozitivní")} % · neutrální ${pct("neutrální")} % · kritický ${pct("kritický")} %</div>
      <div>${(d.temata||[]).map(x=>`<span class="tag">${esc(x)}</span>`).join("")}</div>
      ${ov?`<div class="meta">Ověřené výroky: ${ov}</div>`:""}
      <div class="btns"><button data-go="news" data-s="${esc(name)}">Zprávy</button><button data-go="promises" data-s="${esc(name)}">Sliby</button></div>
    </div>`}).join("");
}

document.addEventListener("click",e=>{
  const p=e.target.closest("[data-pol]");
  if(p){e.preventDefault();$("q").value=p.dataset.pol;renderNews();$("list").scrollIntoView({behavior:"smooth"});return}
  const b=e.target.closest("[data-go]");if(!b)return;
  if(b.dataset.go==="news"){$("strana").value=b.dataset.s;renderNews();tab("zpravy")}
  else{$("sstrana").value=b.dataset.s;renderPromises();tab("sliby")}
});

function renderPromises(){
  const q=$("sq").value.toLowerCase(),s=$("sstrana").value,t=$("stema").value;
  const out=allPromises.filter(x=>(!s||x.strana===s)&&(!t||x.tema===t)&&(!q||x.slib.toLowerCase().includes(q)));
  $("sliby-list").innerHTML=out.map(x=>`<div class="card" style="border-left:5px solid ${col(x.strana)}">
    <span class="tag">${esc(x.strana)}</span>${x.tema?`<span class="tag">${esc(x.tema)}</span>`:""}
    <div>${esc(x.slib)}</div>
    <div class="meta"><a href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.zdroj)}</a> · ${esc(x.datum)}</div></div>`).join("")||"Zatím žádné sliby. Objeví se, jakmile je AI najde ve zprávách.";
}
["sq","sstrana","stema"].forEach(id=>$(id).addEventListener("input",renderPromises));

function fillAgencies(){
  const reg=$("preg").value,cur=$("pag").value;
  const ag=[...new Set(polls.filter(p=>p.region===reg).map(p=>p.agentura))].sort();
  $("pag").innerHTML='<option value="__avg">Průměr agentur (60 dní)</option>'+ag.map(a=>`<option>${esc(a)}</option>`).join("");
  if(ag.includes(cur))$("pag").value=cur;
  renderPolls();
}
$("preg").addEventListener("input",fillAgencies);
$("pag").addEventListener("input",renderPolls);

function latestByAgency(P){const m={};P.forEach(p=>{if(!m[p.agentura]||p.datum>m[p.agentura].datum)m[p.agentura]=p});return Object.values(m)}

function infoBlock(reg){
  const items=(info||[]).filter(x=>x.region===reg);
  if(!items.length)return"";
  return `<div class="legend" style="margin:6px 0 10px">DALŠÍ ZJIŠTĚNÍ</div>`+items.map(x=>`<div class="card">
    <b>${esc(x.nadpis)}</b>
    <div>${esc(x.text)}</div>
    <div class="meta"><a href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.zdroj)}</a>${x.datum?" · "+esc(x.datum):""}</div></div>`).join("")+`<div class="legend" style="margin:18px 0 10px">ZAZNAMENANÉ PRŮZKUMY</div>`;
}

function renderPolls(){
  const reg=$("preg").value,ag=$("pag").value;
  const P=polls.filter(p=>p.region===reg);
  $("p-title").textContent="Volební preference: "+(reg==="Praha"?"Praha":"celá ČR");
  if(!P.length){
    $("bars").innerHTML='<p class="muted">Zatím nejsou zachycené žádné průzkumy. Objeví se, jakmile je skript najde ve zprávách.</p>';
    $("trend").innerHTML="";$("poll-list").innerHTML=infoBlock(reg);return;
  }
  let base;
  if(ag==="__avg"){
    const newest=P.map(p=>p.datum).sort().pop();
    const lim=new Date(new Date(newest)-60*864e5).toISOString().slice(0,10);
    base=latestByAgency(P.filter(p=>p.datum>=lim));
  }else base=[P.filter(p=>p.agentura===ag).sort((a,b)=>b.datum.localeCompare(a.datum))[0]];
  const sm={},cnt={};
  base.forEach(p=>Object.entries(p.vysledky).forEach(([k,v])=>{sm[k]=(sm[k]||0)+v;cnt[k]=(cnt[k]||0)+1}));
  const rows=Object.keys(sm).map(k=>[k,sm[k]/cnt[k]]).sort((a,b)=>b[1]-a[1]);
  const max=Math.max(10,rows[0][1])*1.1;
  $("bars").innerHTML=rows.map(([k,v])=>`<div class="row"><span class="nm"><i class="dot" style="background:${col(k)}"></i>${esc(k)}</span>
    <div class="track"><div class="fill" style="width:${v/max*100}%;background:${col(k)}"></div><span class="thr" style="left:${5/max*100}%"></span></div><b>${num(v)} %</b></div>`).join("")
    +`<div class="meta">${ag==="__avg"?`Průměr z ${base.length} agentur (poslední průzkum každé)`:`${esc(base[0].agentura)} · ${esc(base[0].datum)}`}</div>`;
  const top=rows.slice(0,6).map(r=>r[0]);
  $("trend").innerHTML=lineChart(ag==="__avg"?P:P.filter(p=>p.agentura===ag),top);
  $("poll-list").innerHTML=infoBlock(reg)+P.slice(0,30).map(p=>`<div class="card">
    <b>${esc(p.agentura)}</b> · ${esc(p.datum)}
    <div class="meta">${Object.entries(p.vysledky).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${esc(k)} ${num(v)} %`).join(" · ")}</div>
    <div class="meta"><a href="${esc(p.link)}" target="_blank" rel="noopener">${esc(p.zdroj)}</a></div></div>`).join("");
}

function lineChart(P,ps){
  const ts=P.map(p=>+new Date(p.datum)),t0=Math.min(...ts),t1=Math.max(...ts);
  if(!(t1>t0))return '<p class="muted">Pro graf vývoje je zatím málo průzkumů z různých dnů.</p>';
  const pts=ps.map(s=>({s,d:P.filter(p=>p.vysledky[s]!=null).map(p=>({t:+new Date(p.datum),v:p.vysledky[s]})).sort((a,b)=>a.t-b.t)}));
  const W=640,H=260,L=34,R=12,T=12,B=26;
  const vmax=Math.ceil(Math.max(...pts.flatMap(x=>x.d.map(q=>q.v)))/5)*5+5;
  const X=t=>L+(t-t0)/(t1-t0)*(W-L-R),Y=v=>T+(1-v/vmax)*(H-T-B);
  let g="";
  for(let v=0;v<=vmax;v+=5)g+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${L-6}" y="${Y(v)+4}" text-anchor="end" class="ax">${v}</text>`;
  const f=t=>new Date(t).toLocaleDateString("cs-CZ",{day:"numeric",month:"numeric"});
  g+=`<text x="${L}" y="${H-6}" class="ax">${f(t0)}</text><text x="${W-R}" y="${H-6}" text-anchor="end" class="ax">${f(t1)}</text>`;
  pts.forEach(({s,d})=>{if(!d.length)return;
    g+=`<polyline fill="none" stroke="${col(s)}" stroke-width="2.5" stroke-linejoin="round" points="${d.map(q=>X(q.t)+","+Y(q.v)).join(" ")}"/>`+d.map(q=>`<circle cx="${X(q.t)}" cy="${Y(q.v)}" r="3.2" fill="${col(s)}"/>`).join("")});
  const leg=pts.map(x=>`<span class="lg"><i style="background:${col(x.s)}"></i>${esc(x.s)}</span>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart">${g}</svg><div>${leg}</div>`;
}
