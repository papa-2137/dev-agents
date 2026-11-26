/* Skrypt przewodnika dev-agents - przeniesiony z zaakceptowanej makiety dev_log/guide_mockup.html: router zakładek,
   podpowiedzi (drzewo plików, diagram, terminy ze słowniczka), przyciski „Kopiuj”, diagram przepływu, wiersze
   „krok po kroku” i graf zależności. Renderer wstawia ten plik do <script> w guide.html; dane diagramu i grafu
   (flow-data, deps-data) są opcjonalne. */
{
 const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
 /* ---------- router zakładek ---------- */
 const tabs=[...document.querySelectorAll('.tab')];
 const links=[...document.querySelectorAll('#nav > a')];
 const route=()=>{
  const id=decodeURIComponent(location.hash.slice(1))||'przeglad';
  let el=document.getElementById(id),tab=null,target=null;
  if(el&&el.classList.contains('tab'))tab=el;else if(el){tab=el.closest('.tab');target=el}
  if(!tab)tab=tabs[0];
  tabs.forEach(t=>{t.hidden=t!==tab});
  links.forEach(a=>{if(a.getAttribute('href')==='#'+tab.id)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});
  hideTip(true);
  requestAnimationFrame(()=>{drawFlow();drawDeps();if(target)target.scrollIntoView({block:'start'});else window.scrollTo(0,0)});
 };
 /* ---------- podpowiedzi ---------- */
 const tip=document.getElementById('tip');let pinned=null,pinShow=null;
 const place=el=>{tip.hidden=false;const r=el.getBoundingClientRect(),tw=tip.offsetWidth,th=tip.offsetHeight;let x=r.left,y=r.bottom+8;if(x+tw>innerWidth-12)x=innerWidth-tw-12;if(x<12)x=12;if(y+th>innerHeight-12)y=r.top-th-8;if(y<12)y=12;tip.style.left=x+'px';tip.style.top=y+'px'};
 function hideTip(force){if(pinned&&!force)return;if(pinned)pinned.classList.remove('on');pinned=null;pinShow=null;tip.classList.remove('pin');tip.hidden=true}
 const showItem=el=>{const n=el.cloneNode(true);n.querySelectorAll('i').forEach(i=>i.remove());tip.innerHTML='<b>'+esc(n.textContent.trim())+'</b><p><span>Czym jest</span>'+esc(el.dataset.w)+'</p><p><span>Rola w projekcie</span>'+esc(el.dataset.r)+'</p>';place(el)};
 /* termin ze słowniczka w tekście: span.tm z data-t (termin) i data-d (definicja), oba z renderera */
 const showTerm=el=>{tip.innerHTML='<b>'+esc(el.dataset.t)+'</b><p><span>Pojęcie</span>'+esc(el.dataset.d)+'</p>';place(el)};
 const bindTip=(el,show)=>{
  el.addEventListener('mouseenter',()=>{if(!pinned)show(el)});
  el.addEventListener('mouseleave',()=>{if(!pinned)hideTip()});
  el.addEventListener('focus',()=>{if(!pinned)show(el)});
  el.addEventListener('blur',()=>{if(!pinned)hideTip()});
  el.addEventListener('click',ev=>{ev.stopPropagation();if(pinned===el){hideTip(true);return}if(pinned)pinned.classList.remove('on');pinned=el;pinShow=show;el.classList.add('on');show(el);tip.classList.add('pin')});
  if(el.tagName!=='BUTTON')el.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();el.click()}});
 };
 document.querySelectorAll('.it[data-w]').forEach(el=>bindTip(el,showItem));
 document.querySelectorAll('.tm').forEach(el=>bindTip(el,showTerm));
 document.addEventListener('click',ev=>{if(pinned&&!tip.contains(ev.target))hideTip(true)});
 document.addEventListener('keydown',ev=>{if(ev.key==='Escape')hideTip(true)});
 window.addEventListener('scroll',()=>{if(pinned&&pinShow)pinShow(pinned);else hideTip()},{passive:true});
 /* ---------- przyciski kopiowania ---------- */
 document.querySelectorAll('.cb').forEach(box=>{const b=document.createElement('button');b.className='cp';b.type='button';b.textContent='Kopiuj';
  b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(box.querySelector('pre').textContent);b.textContent='Skopiowano'}catch(e){b.textContent='Zaznacz i skopiuj'}setTimeout(()=>{b.textContent='Kopiuj'},1600)});box.appendChild(b)});
 /* ---------- dane przepływu ---------- */
 /* dane diagramu wstawia renderer (diagram i wiersze „krok po kroku” z tych samych danych); bez nich nic się nie rysuje */
 const flowEl=document.getElementById('flow-data');
 const flow=flowEl?JSON.parse(flowEl.textContent):{nodes:[],edges:[],layout:{}};
 const byId={};flow.nodes.forEach((n,i)=>{n.num=i+1;byId[n.id]=n});
 const kindName={term:'start / koniec',step:'czynność robota',sys:'kontakt z systemem zewnętrznym',dec:'decyzja'};
 const showFlow=g=>{const n=byId[g.dataset.go];if(!n)return;
  const mf=[n.module,n.funcs.join(', ')].filter(Boolean).map(t=>'<code>'+esc(t)+'</code>').join(' · ');
  tip.innerHTML='<b>'+n.num+'. '+esc(n.label)+(n.unc?' <span class="unc">wywnioskowane</span>':'')+'</b><p class="tk">'+esc(kindName[n.kind])+'</p>'+(n.desc?'<p>'+esc(n.desc)+'</p>':'')+(mf?'<p><span>Moduł i funkcja</span>'+mf+'</p>':'')+(n.reads.length?'<p><span>Czyta</span>'+n.reads.map(r=>esc(r.name)).join(', ')+'</p>':'')+(n.writes.length?'<p><span>Zapisuje / zwraca</span>'+n.writes.map(r=>esc(r.name)).join(', ')+'</p>':'')+'<p class="tk">Kliknij, aby przejść do szczegółów kroku.</p>';place(g)};
 /* ---------- diagram przepływu (SVG) ---------- */
 const svg=document.getElementById('flow')||document.createElementNS('http://www.w3.org/2000/svg','svg');
 const defs='<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#111"/></marker><marker id="ahr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#e4002b"/></marker></defs>';
 function drawFlow(){
  if(!flow.nodes.length||svg.closest('.tab').hidden)return;
  const W=svg.clientWidth||svg.parentNode.clientWidth;if(!W)return;
  const rowH=78,top=26,rows=Math.max(...Object.values(flow.layout).map(p=>p[0]))+1,H=top*2+(rows-1)*rowH+40;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.style.height=H+'px';
  const narrow=W<640,bw=narrow?W*.44:Math.min(300,W*.4),bh=44,colX=narrow?[W*.29,W*.76]:[W*.36,W*.74];
  const P=id=>{const [r,c]=flow.layout[id];return{x:colX[c],y:top+20+r*rowH}};
  let e='',n='';
  const bottom=(id)=>{const p=P(id),k=byId[id].kind;return{x:p.x,y:p.y+(k==='dec'?bh/2+6:bh/2)}};
  const topOf=(id)=>{const p=P(id),k=byId[id].kind;return{x:p.x,y:p.y-(k==='dec'?bh/2+6:bh/2)}};
  flow.edges.forEach(ed=>{
   const a=P(ed.from),b=P(ed.to),kind=ed.kind||'normal';
   if(kind==='loop'){
    const x0=a.x+bw/2,x1=b.x+bw/2+(byId[ed.to].kind==='dec'?-bw/2+bw*.3:0),off=Math.min(70,W*.08),xr=Math.max(x0,x1)+off;
    e+=`<path class="lp" marker-end="url(#ahr)" d="M${x0},${a.y}C${xr},${a.y} ${xr},${b.y} ${x1+6},${b.y}"/>`;
    if(ed.label)e+=`<text class="lblr" x="${x0+10}" y="${a.y+bh/2+12}" style="text-anchor:start">${esc(ed.label)}</text>`;
   }else if(a.x!==b.x){
    const s=byId[ed.from].kind==='dec'?{x:a.x+bw*.36,y:a.y}:{x:a.x+(b.x>a.x?bw/2:-bw/2),y:a.y};
    const t=b.y>a.y?topOf(ed.to):{x:b.x,y:b.y};
    if(b.x>a.x){e+=`<path class="edge" marker-end="url(#ah)" d="M${s.x},${s.y}H${t.x}V${t.y}"/>`;if(ed.label)e+=`<text class="lbl" x="${s.x+10}" y="${s.y-12}" style="text-anchor:start">${esc(ed.label)}</text>`}
    else{const tt=topOf(ed.to);const tx=tt.x+bw*.25;e+=`<path class="edge" marker-end="url(#ah)" d="M${a.x},${bottom(ed.from).y}V${tt.y-14}H${tx}V${tt.y}"/>`}
   }else{
    const s=bottom(ed.from),t=topOf(ed.to),ra=flow.layout[ed.from][0],rb=flow.layout[ed.to][0],cc=flow.layout[ed.from][1];
    const blocked=Object.entries(flow.layout).some(([id,q])=>q[1]===cc&&q[0]>Math.min(ra,rb)&&q[0]<Math.max(ra,rb));
    if(blocked){const xb=a.x-bw/2-26;e+=`<path class="edge" marker-end="url(#ah)" d="M${a.x-bw*.36},${a.y}H${xb}V${t.y-12}H${b.x-bw*.25}V${t.y}"/>`;if(ed.label)e+=`<text class="lbl" x="${xb-2}" y="${(a.y+t.y)/2}" style="text-anchor:end">${esc(ed.label)}</text>`}
    else{e+=`<path class="edge" marker-end="url(#ah)" d="M${s.x},${s.y}V${t.y}"/>`;if(ed.label)e+=`<text class="lbl" x="${s.x+16}" y="${(s.y+t.y)/2}" style="text-anchor:start">${esc(ed.label)}</text>`}
   }
  });
  const lines=(t,maxW,fs)=>{const per=Math.max(6,Math.floor(maxW/(fs*.56)));if(t.length<=per)return[t];const w=t.split(' ');let a='',b='';for(const x of w){if(!b&&(a+' '+x).trim().length<=per)a=(a+' '+x).trim();else b=(b+' '+x).trim()}return b?[a,b]:[a]};
  flow.nodes.forEach(nd=>{const p=P(nd.id),fs=narrow?12:14;let shape,cls;
   if(nd.kind==='dec'){const hw=bw*.42,hh=bh/2+6;shape=`<polygon class="n-dec" points="${p.x},${p.y-hh} ${p.x+hw},${p.y} ${p.x},${p.y+hh} ${p.x-hw},${p.y}"/>`;cls='t-dec'}
   else{const rx=nd.kind==='term'?22:3;shape=`<rect x="${p.x-bw/2}" y="${p.y-bh/2}" width="${bw}" height="${bh}" rx="${rx}" class="${nd.kind==='sys'?'n-sys':nd.kind==='term'?'n-term':'n-step'}"/>`;cls=nd.kind==='sys'?'t-sys':'t-step'}
   const numCls=nd.kind==='sys'?'t-numw':'t-num';
   n+=`<g data-go="${esc(nd.id)}" tabindex="0" role="button" aria-label="${esc(nd.num+'. '+nd.label)}: szczegóły">${shape}${lines(nd.label,nd.kind==='dec'?bw*.62:bw-30,fs).map((t,k,a)=>`<text x="${nd.kind==='dec'?p.x:p.x+9}" y="${p.y+(k-(a.length-1)/2)*(fs+2)}" class="${cls}" font-size="${fs}">${esc(t)}</text>`).join('')}${nd.kind!=='dec'?`<text x="${p.x-bw/2+12}" y="${p.y}" class="${numCls}">${nd.num}</text>`:''}</g>`});
  svg.innerHTML=defs+e+n;
 }
 const goRow=id=>{hideTip(true);const r=document.getElementById('row-'+id);if(!r)return;document.querySelectorAll('.row.hl').forEach(x=>x.classList.remove('hl'));r.classList.add('hl');r.scrollIntoView({behavior:reduce?'auto':'smooth',block:'center'})};
 svg.addEventListener('click',ev=>{const g=ev.target.closest('[data-go]');if(g){ev.stopPropagation();goRow(g.dataset.go)}});
 svg.addEventListener('mouseover',ev=>{const g=ev.target.closest('[data-go]');if(g&&!pinned)showFlow(g)});
 svg.addEventListener('mouseout',ev=>{const g=ev.target.closest('[data-go]');if(g&&!g.contains(ev.relatedTarget)&&!pinned)hideTip()});
 svg.addEventListener('focusin',ev=>{const g=ev.target.closest('[data-go]');if(g&&!pinned)showFlow(g)});
 svg.addEventListener('focusout',()=>{if(!pinned)hideTip()});
 svg.addEventListener('keydown',ev=>{const g=ev.target.closest('[data-go]');if(g&&(ev.key==='Enter'||ev.key===' ')){ev.preventDefault();goRow(g.dataset.go)}});
 /* ---------- krok po kroku (z tych samych danych) ---------- */
 const chip=r=>`<div class="c ${r.kind}">${esc(r.name)}</div>`;
 const rowsHtml=flow.nodes.map((nd,i)=>{
  const ins=nd.reads.map(chip).join(''),outs=nd.writes.map(chip).join('');
  const out=flow.edges.filter(e=>e.from===nd.id);
  const decOut=nd.kind==='dec'?'<div class="dec-out">'+out.map(e=>`<span>${esc(e.label||'')} → ${byId[e.to].num}</span>`).join('')+'</div>':'';
  const loop=out.find(e=>e.kind==='loop');
  const nextTxt=loop?`<div class="down"><div class="v loop">${esc(loop.label)} → krok ${byId[loop.to].num}</div></div>`:(i<flow.nodes.length-1?'<div class="down"><div class="v"></div></div>':'');
  const unc=nd.unc?' <span class="unc">wywnioskowane</span>':'';
  const mod=nd.module?`<code>${esc(nd.module)}</code>`:'';
  const desc=nd.desc?`<p>${esc(nd.desc)}</p>`:'';
  const calls=nd.funcs.length?'<ol class="calls">'+nd.funcs.map(f=>`<li>${esc(f)}</li>`).join('')+'</ol>':'';
  return `<div class="row" id="row-${esc(nd.id)}"><div class="ins">${ins}</div><div class="ar${ins?'':' none'}"></div><div class="node ${nd.kind==='sys'?'sys':nd.kind==='dec'?'dec':''}"><div class="nh"><span class="num">${nd.num}</span><b>${esc(nd.label)}</b>${unc}${mod}</div>${desc}${calls}${decOut}</div><div class="ar${outs?'':' none'}"></div><div class="outs">${outs}</div></div>${nextTxt}`;
 }).join('');
 const flowRows=document.getElementById('flowrows');if(flowRows)flowRows.innerHTML=rowsHtml;
 /* ---------- graf zależności ---------- */
 /* dane grafu (węzły i krawędzie liczone z importów) wstawia renderer; bez nich graf się nie rysuje */
 const depsEl=document.getElementById('deps-data');
 const deps=depsEl?JSON.parse(depsEl.textContent):{nodes:[],edges:[]};
 const dsvg=document.getElementById('deps')||document.createElementNS('http://www.w3.org/2000/svg','svg');
 function drawDeps(){
  if(!deps.nodes.length||dsvg.closest('.tab').hidden)return;
  const W=dsvg.clientWidth||dsvg.parentNode.clientWidth;if(!W)return;
  /* warstwy: punkty wejścia i moduły, których nikt nie importuje, w warstwie 0; reszta wg najdłuższej ścieżki */
  const depth={},fixed={},hasIn={};
  deps.edges.forEach(([a,b])=>{hasIn[b]=true});
  deps.nodes.forEach(n=>{if(n.entry||!hasIn[n.id]){depth[n.id]=0;fixed[n.id]=true}});
  for(let k=0;k<deps.nodes.length;k++)deps.edges.forEach(([a,b])=>{if(!fixed[b]&&depth[a]!=null&&(depth[b]==null||depth[b]<depth[a]+1)&&depth[a]+1<deps.nodes.length)depth[b]=depth[a]+1});
  deps.nodes.forEach(n=>{if(depth[n.id]==null)depth[n.id]=1});
  const layers={};deps.nodes.forEach(n=>{(layers[depth[n.id]]=layers[depth[n.id]]||[]).push(n)});
  const L=Object.keys(layers).length,maxN=Math.max(...Object.values(layers).map(l=>l.length));
  const rowH=40,H=Math.max(120,maxN*rowH+30);dsvg.setAttribute('viewBox',`0 0 ${W} ${H}`);dsvg.style.height=H+'px';
  const longest=Math.max(...deps.nodes.map(n=>n.id.split('/').pop().length)),bw=Math.max(70,Math.min(longest*8+20,(W-20)/L-36)),bh=28,pos={};
  const maxCh=Math.max(4,Math.floor((bw-10)/7.8));
  Object.entries(layers).forEach(([d,l])=>{l.forEach((n,i)=>{pos[n.id]={x:10+bw/2+d*((W-20-bw)/Math.max(1,L-1)),y:(H-(l.length-1)*rowH)/2+i*rowH}})});
  let e='',s='';
  deps.edges.forEach(([a,b])=>{const p=pos[a],q=pos[b];if(!p||!q)return;const mx=(p.x+q.x)/2;e+=`<path class="edge" marker-end="url(#ah2)" d="M${p.x+bw/2},${p.y}C${mx},${p.y} ${mx},${q.y} ${q.x-bw/2-2},${q.y}"/>`});
  /* nazwa pliku w prostokącie (skrócona, gdy się nie mieści); pełna ścieżka w <title> po najechaniu */
  deps.nodes.forEach(n=>{const p=pos[n.id],base=n.id.split('/').pop(),label=base.length>maxCh?base.slice(0,maxCh-1)+'…':base;s+=`<g><title>${esc(n.id)}</title><rect x="${p.x-bw/2}" y="${p.y-bh/2}" width="${bw}" height="${bh}" rx="2" class="${n.entry?'n-entry':'n-mod'}"/><text x="${p.x}" y="${p.y}" class="${n.entry?'t-entry':'t-mod'}">${esc(label)}</text></g>`});
  dsvg.innerHTML='<defs><marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="#111"/></marker></defs>'+e+s;
 }
 new ResizeObserver(()=>{drawFlow();drawDeps()}).observe(document.querySelector('main'));
 window.addEventListener('hashchange',route);
 route();
}
