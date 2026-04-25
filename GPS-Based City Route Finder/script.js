
const LOCATIONS = [
  { id:"A", name:"Times Square",           short:"Times Sq.",   lat:40.7580, lon:-73.9855 },
  { id:"B", name:"Central Park South",     short:"Central Park",lat:40.7671, lon:-73.9712 },
  { id:"C", name:"Empire State Building",  short:"Empire St.",  lat:40.7484, lon:-73.9857 },
  { id:"D", name:"Grand Central Terminal", short:"Grand Cent.", lat:40.7527, lon:-73.9772 },
  { id:"E", name:"Rockefeller Center",     short:"Rock. Ctr.",  lat:40.7587, lon:-73.9787 },
  { id:"F", name:"Washington Sq. Park",    short:"Wash. Sq.",   lat:40.7308, lon:-73.9973 },
];

// MAP
const map = L.map('map',{center:[40.755,-73.984],zoom:14,zoomControl:false,attributionControl:true});
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png',{
  attribution:'&copy; OpenStreetMap &copy; CARTO',subdomains:'abcd',maxZoom:19
}).addTo(map);

// Custom zoom
const zc=L.control({position:'topright'});
zc.onAdd=()=>{
  const d=L.DomUtil.create('div');
  d.style.cssText='display:flex;flex-direction:column;gap:2px;margin:10px 10px 0 0';
  ['＋','−'].forEach((sym,i)=>{
    const b=document.createElement('button');
    b.textContent=sym;
    b.style.cssText='width:28px;height:28px;background:#0f1820;color:#ddeeff;border:1px solid #243040;cursor:pointer;font-size:15px;border-radius:0;display:flex;align-items:center;justify-content:center;';
    b.onclick=()=>i===0?map.zoomIn():map.zoomOut();
    d.appendChild(b);
  });
  L.DomEvent.disableClickPropagation(d);
  return d;
};
zc.addTo(map);

// STATE
let srcLoc=null,dstLoc=null;
let srcMarker=null,dstMarker=null;
let locMarkers={};
let exploredLayer=null,pathLayer=null;

const mkPin=(color,label)=>L.divIcon({
  className:'',
  html:`<div style="width:20px;height:20px;border-radius:50%;background:${color};border:2px solid rgba(255,255,255,0.8);box-shadow:0 0 14px ${color};display:flex;align-items:center;justify-content:center;font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;color:#000;">${label}</div>`,
  iconAnchor:[10,10],
});

// Place dim pins for all 6 locations
LOCATIONS.forEach(loc=>{
  const m=L.marker([loc.lat,loc.lon],{icon:mkPin('#3a5570',loc.id)})
    .addTo(map)
    .bindPopup(`<strong>${loc.id} — ${loc.name}</strong><br><span style="color:#5a7a99;font-size:10px">${loc.lat.toFixed(4)}, ${loc.lon.toFixed(4)}</span>`);
  locMarkers[loc.id]=m;
});

// Build sidebar buttons
const grid=document.getElementById('loc-grid');
LOCATIONS.forEach(loc=>{
  const btn=document.createElement('button');
  btn.className='loc-btn';
  btn.id=`lb-${loc.id}`;
  btn.innerHTML=`<span class="lbl">${loc.id}</span><span class="name">${loc.short}</span>`;
  btn.onclick=()=>selectLoc(loc);
  grid.appendChild(btn);
});

function selectLoc(loc){
  if(!srcLoc){
    srcLoc=loc;
    document.getElementById('src-label').textContent=`${loc.id} — ${loc.name}`;
    document.getElementById('src-label').classList.remove('empty');
    placePin('src',loc);
    map.panTo([loc.lat,loc.lon]);
    refreshBtns();
  } else if(!dstLoc && loc.id!==srcLoc.id){
    dstLoc=loc;
    document.getElementById('dst-label').textContent=`${loc.id} — ${loc.name}`;
    document.getElementById('dst-label').classList.remove('empty');
    placePin('dst',loc);
    document.getElementById('run-btn').disabled=false;
    document.getElementById('map-hint').style.opacity='0';
    map.fitBounds([[srcLoc.lat,srcLoc.lon],[dstLoc.lat,dstLoc.lon]],{padding:[70,70]});
    refreshBtns();
  }
}

function placePin(type,loc){
  if(type==='src'){ if(srcMarker)map.removeLayer(srcMarker); srcMarker=L.marker([loc.lat,loc.lon],{icon:mkPin('#2dea7a',loc.id),zIndexOffset:2000}).addTo(map); }
  else            { if(dstMarker)map.removeLayer(dstMarker); dstMarker=L.marker([loc.lat,loc.lon],{icon:mkPin('#ff4560',loc.id),zIndexOffset:2000}).addTo(map); }
}

function refreshBtns(){
  LOCATIONS.forEach(loc=>{
    const btn=document.getElementById(`lb-${loc.id}`);
    btn.classList.remove('sel-src','sel-dst');
    if(srcLoc&&loc.id===srcLoc.id) btn.classList.add('sel-src');
    if(dstLoc&&loc.id===dstLoc.id) btn.classList.add('sel-dst');
    let col='#3a5570';
    if(srcLoc&&loc.id===srcLoc.id) col='#2dea7a';
    if(dstLoc&&loc.id===dstLoc.id) col='#ff4560';
    locMarkers[loc.id].setIcon(mkPin(col,loc.id));
  });
}

function swapLocations(){
  if(!srcLoc||!dstLoc) return;
  [srcLoc,dstLoc]=[dstLoc,srcLoc];
  document.getElementById('src-label').textContent=`${srcLoc.id} — ${srcLoc.name}`;
  document.getElementById('dst-label').textContent=`${dstLoc.id} — ${dstLoc.name}`;
  placePin('src',srcLoc); placePin('dst',dstLoc);
  refreshBtns(); clearResults();
}

async function runSearch(){
  if(!srcLoc||!dstLoc) return;
  clearResults();
  const btn=document.getElementById('run-btn');
  btn.disabled=true; btn.classList.add('loading'); btn.textContent='⟳ FETCHING ROAD DATA…';
  document.getElementById('err-box').style.display='none';
  setBadge('b-status','LOADING','lit');
  document.getElementById('prog-fill').style.width='15%';

  try{
    const res=await fetch('/api/search',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        src_lat:srcLoc.lat,src_lon:srcLoc.lon,
        dst_lat:dstLoc.lat,dst_lon:dstLoc.lon,
        src_name:srcLoc.name,dst_name:dstLoc.name,
      })
    });
    const data=await res.json();
    if(!res.ok||data.error) throw new Error(data.error||'Server error');
    document.getElementById('prog-fill').style.width='65%';
    btn.textContent='⬡ RENDERING MAP…';
    await renderResult(data);
  } catch(err){
    document.getElementById('err-box').textContent='⚠ '+err.message;
    document.getElementById('err-box').style.display='block';
    setBadge('b-status','ERROR','err');
    btn.classList.remove('loading'); btn.textContent='▶ RUN A* SEARCH'; btn.disabled=false;
  }
}

async function renderResult(data){
  const {visited,path,directions,stats}=data;
  const btn=document.getElementById('run-btn');

  // ── Phase 1: animate explored road segments (A* frontier spreading street by street) ──
  btn.textContent='⬡ EXPLORING ROADS…';
  setBadge('b-status','EXPLORING','lit');

  const vg=L.layerGroup();
  vg.addTo(map); exploredLayer=vg;

  // Fit map to full exploration area before animating
  if(visited.length>0){
    const allPts=visited.flat().concat(path.map(p=>[p[0],p[1]]));
    map.fitBounds(L.latLngBounds(allPts),{padding:[60,60],animate:false});
  }

  // Medium speed: ~35ms per frame, 1 segment per frame → clearly visible street-by-street spread
  const FRAME_MS = 35;
  // But if there are tons of edges, batch a few per frame so total time stays ~8-12s
  const TOTAL_ANIM_MS = 9000;
  const BATCH = Math.max(1, Math.ceil(visited.length / (TOTAL_ANIM_MS / FRAME_MS)));

  await new Promise(resolve=>{
    let i=0;
    function step(){
      const end=Math.min(i+BATCH, visited.length);
      for(;i<end;i++){
        const [a,b]=visited[i];
        L.polyline([a,b],{
          color:'#00d4ff',weight:2,opacity:0.55,interactive:false,smoothFactor:0
        }).addTo(vg);
      }
      // Progress bar 65% → 85%
      document.getElementById('prog-fill').style.width=(65+Math.round((i/visited.length)*20))+'%';
      if(i<visited.length) setTimeout(step,FRAME_MS);
      else resolve();
    }
    step();
  });

  // Pause so user sees the full explored frontier before the optimal path appears
  await new Promise(r=>setTimeout(r,400));

  // ── Phase 2: animate optimal path drawing segment by segment ─────────────────
  btn.textContent='⬡ DRAWING OPTIMAL PATH…';
  setBadge('b-status','DRAWING','lit');
  document.getElementById('prog-fill').style.width='87%';

  const pathCoords=path.map(p=>[p[0],p[1]]);
  const SEG_BATCH=Math.max(1,Math.floor(pathCoords.length/60));
  const SEG_MS=22;
  await new Promise(resolve=>{
    let j=2;
    pathLayer=L.polyline(pathCoords.slice(0,2),{
      color:'#f5c518',weight:5,opacity:.95,smoothFactor:1
    }).addTo(map);
    if(srcMarker) srcMarker.setZIndexOffset(3000);
    if(dstMarker) dstMarker.setZIndexOffset(3000);
    function drawSeg(){
      const end=Math.min(j+SEG_BATCH, pathCoords.length);
      pathLayer.setLatLngs(pathCoords.slice(0,end));
      j=end;
      if(j<pathCoords.length) setTimeout(drawSeg,SEG_MS);
      else resolve();
    }
    setTimeout(drawSeg,SEG_MS);
  });

  map.fitBounds(pathLayer.getBounds(),{padding:[55,55]});
  await new Promise(r=>setTimeout(r,200));

  // ── Phase 3: reveal stats & optimal-path directions only ─────────────────────
  document.getElementById('s-explored').textContent=stats.nodes_explored.toLocaleString();
  document.getElementById('s-path').textContent    =stats.path_nodes.toLocaleString();
  document.getElementById('s-dist').textContent    =stats.distance_m.toLocaleString();
  document.getElementById('s-km').textContent      =stats.distance_km;
  document.getElementById('stats-section').style.display='block';

  // directions[] comes from generate_directions(path, ...) on the server —
  // it is strictly the optimal route, never the explored nodes
  const dl=document.getElementById('dir-list');
  dl.innerHTML='';
  directions.forEach(step=>{
    const div=document.createElement('div');
    div.className='dir-step'; div.innerHTML=step;
    dl.appendChild(div);
  });
  document.getElementById('dir-section').style.display='block';
  document.getElementById('dir-section').scrollIntoView({behavior:'smooth',block:'nearest'});

  document.getElementById('b-explored').textContent=stats.nodes_explored.toLocaleString()+' nodes';
  document.getElementById('b-dist').textContent=stats.distance_km+' km';
  setBadge('b-dist','','ok'); document.getElementById('b-dist').textContent=stats.distance_km+' km';
  setBadge('b-status','DONE','ok');
  document.getElementById('prog-fill').style.width='100%';
  btn.classList.remove('loading'); btn.textContent='▶ RUN AGAIN'; btn.disabled=false;
}

function clearResults(){
  if(exploredLayer){map.removeLayer(exploredLayer);exploredLayer=null;}
  if(pathLayer){map.removeLayer(pathLayer);pathLayer=null;}
  document.getElementById('stats-section').style.display='none';
  document.getElementById('dir-section').style.display='none';
  document.getElementById('dir-list').innerHTML='';
  document.getElementById('prog-fill').style.width='0%';
  document.getElementById('b-dist').textContent='— km';
  document.getElementById('b-dist').className='badge';
  document.getElementById('b-explored').textContent='— nodes';
  setBadge('b-status','IDLE','');
}

function resetAll(){
  clearResults();
  if(srcMarker){map.removeLayer(srcMarker);srcMarker=null;}
  if(dstMarker){map.removeLayer(dstMarker);dstMarker=null;}
  srcLoc=null; dstLoc=null;
  document.getElementById('src-label').textContent='— not selected —';
  document.getElementById('src-label').classList.add('empty');
  document.getElementById('dst-label').textContent='— not selected —';
  document.getElementById('dst-label').classList.add('empty');
  document.getElementById('run-btn').disabled=true;
  document.getElementById('run-btn').classList.remove('loading');
  document.getElementById('run-btn').textContent='▶ RUN A* SEARCH';
  document.getElementById('err-box').style.display='none';
  document.getElementById('map-hint').style.opacity='1';
  LOCATIONS.forEach(loc=>locMarkers[loc.id].setIcon(mkPin('#3a5570',loc.id)));
  refreshBtns();
  map.setView([40.755,-73.984],14);
}

function setBadge(id,text,cls){
  const el=document.getElementById(id);
  el.className='badge'+(cls?' '+cls:'');
  if(text) el.textContent=text;
}
