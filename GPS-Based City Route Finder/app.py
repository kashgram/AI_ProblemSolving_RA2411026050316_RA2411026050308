from flask import Flask, render_template_string, request, jsonify
import heapq, math, json, urllib.request, urllib.parse

app = Flask(__name__)

# ── Haversine distance (metres) ─────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p = math.pi / 180
    a = 0.5 - math.cos((lat2-lat1)*p)/2 + \
        math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2
    return 2 * R * math.asin(math.sqrt(a))

# ── Overpass road fetch ──────────────────────────────────────────────────────
def fetch_graph(lat, lon, radius=2200):
    cos_lat = math.cos(math.radians(lat))
    dlat = radius / 111000
    dlon = radius / (111000 * cos_lat)
    bbox = f"{lat-dlat},{lon-dlon},{lat+dlat},{lon+dlon}"
    query = f"""[out:json][timeout:90];
(
  way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|road"](bbox:{bbox});
);
out body; >; out skel qt;"""
    url  = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": query}).encode()
    req  = urllib.request.Request(url, data=data)
    req.add_header("User-Agent", "AStarPathfinderNYC/1.0")
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())

def build_graph(osm_data):
    nodes = {}
    for el in osm_data["elements"]:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
    adj       = {}
    way_names = {}
    for el in osm_data["elements"]:
        if el["type"] != "way":
            continue
        nds    = el.get("nodes", [])
        tags   = el.get("tags", {})
        oneway = tags.get("oneway", "no")
        name   = tags.get("name","") or tags.get("ref","") or "unnamed road"
        for i in range(len(nds)-1):
            a, b = nds[i], nds[i+1]
            if a not in nodes or b not in nodes:
                continue
            d = haversine(*nodes[a], *nodes[b])
            adj.setdefault(a,[]).append((b, d, name))
            if oneway not in ("yes","1","true"):
                adj.setdefault(b,[]).append((a, d, name))
            way_names.setdefault(a, name)
            way_names.setdefault(b, name)
    return nodes, adj, way_names

def nearest_node(nodes, lat, lon):
    best, best_d = None, float("inf")
    for nid,(nlat,nlon) in nodes.items():
        d = haversine(lat, lon, nlat, nlon)
        if d < best_d:
            best_d = d; best = nid
    return best

# ── A* ───────────────────────────────────────────────────────────────────────
def astar(nodes, adj, start, goal):
    glat, glon = nodes[goal]
    open_set   = [(0.0, start)]
    came_from  = {}
    g_score    = {start: 0.0}
    visited    = []
    closed     = set()
    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur in closed:
            continue
        closed.add(cur)
        visited.append(cur)
        if cur == goal:
            path = []
            while cur in came_from:
                path.append(cur); cur = came_from[cur]
            path.append(start); path.reverse()
            return path, visited
        for nb, cost, _ in adj.get(cur, []):
            tg = g_score[cur] + cost
            if tg < g_score.get(nb, float("inf")):
                came_from[nb] = cur
                g_score[nb]   = tg
                h = haversine(*nodes[nb], glat, glon)
                heapq.heappush(open_set, (tg + h, nb))
    return None, visited

# ── Bearing & turn helpers ───────────────────────────────────────────────────
def bearing(lat1,lon1,lat2,lon2):
    p = math.pi/180
    y = math.sin((lon2-lon1)*p)*math.cos(lat2*p)
    x = math.cos(lat1*p)*math.sin(lat2*p) - math.sin(lat1*p)*math.cos(lat2*p)*math.cos((lon2-lon1)*p)
    return (math.degrees(math.atan2(y,x))+360)%360

def compass(b):
    return ["north","northeast","east","southeast","south","southwest","west","northwest"][round(b/45)%8]

def turn_word(prev_b,cur_b):
    diff=(cur_b-prev_b+360)%360
    if diff<20 or diff>340: return "continue straight"
    if diff<90:             return "turn right"
    if diff<180:            return "turn slight right"
    if diff<270:            return "turn left"
    return "turn slight left"

# ── Manhattan landmarks ───────────────────────────────────────────────────────
LANDMARKS=[
    {"name":"Times Square",          "lat":40.7580,"lon":-73.9855,"radius":260},
    {"name":"Central Park",          "lat":40.7851,"lon":-73.9683,"radius":750},
    {"name":"Empire State Building", "lat":40.7484,"lon":-73.9857,"radius":220},
    {"name":"Rockefeller Center",    "lat":40.7587,"lon":-73.9787,"radius":230},
    {"name":"Grand Central Terminal","lat":40.7527,"lon":-73.9772,"radius":230},
    {"name":"Penn Station",          "lat":40.7506,"lon":-73.9971,"radius":230},
    {"name":"Bryant Park",           "lat":40.7536,"lon":-73.9832,"radius":210},
    {"name":"Columbus Circle",       "lat":40.7681,"lon":-73.9819,"radius":210},
    {"name":"Lincoln Center",        "lat":40.7725,"lon":-73.9835,"radius":230},
    {"name":"Washington Square Park","lat":40.7308,"lon":-73.9973,"radius":230},
    {"name":"Union Square",          "lat":40.7359,"lon":-73.9911,"radius":210},
    {"name":"Madison Square Garden", "lat":40.7505,"lon":-73.9934,"radius":210},
    {"name":"Flatiron Building",     "lat":40.7411,"lon":-73.9897,"radius":160},
    {"name":"Herald Square",         "lat":40.7498,"lon":-73.9880,"radius":180},
]

def nearby_landmark(lat,lon):
    for lm in LANDMARKS:
        if haversine(lat,lon,lm["lat"],lm["lon"])<lm["radius"]:
            return lm["name"]
    return None

# ── Direction generation ─────────────────────────────────────────────────────
def generate_directions(path, nodes, way_names, src_name, dst_name):
    if len(path)<2:
        return [f"You are already at {dst_name}."]
    steps=[]
    prev_name = way_names.get(path[0],"the road")
    prev_b    = None
    seg_dist  = 0.0
    passed_lm = set()
    first_b   = bearing(*nodes[path[0]], *nodes[path[1]])
    steps.append(f"🚦 Start at <strong>{src_name}</strong>. Head {compass(first_b)} on <strong>{prev_name}</strong>.")
    for i in range(1,len(path)-1):
        cur  = path[i]
        nxt  = path[i+1]
        cur_b = bearing(*nodes[cur],*nodes[nxt])
        seg_dist += haversine(*nodes[path[i-1]],*nodes[cur])
        lm=nearby_landmark(*nodes[cur])
        if lm and lm not in passed_lm:
            steps.append(f"📍 Pass near <strong>{lm}</strong>.")
            passed_lm.add(lm)
        cur_name=way_names.get(cur,"the road")
        if cur_name!=prev_name and cur_name and cur_name!="unnamed road":
            turn=turn_word(prev_b,cur_b) if prev_b is not None else "continue"
            ds=f"{int(seg_dist)}m" if seg_dist<1000 else f"{seg_dist/1000:.1f}km"
            steps.append(
                f"↪ After <strong>{ds}</strong> on <strong>{prev_name}</strong>, "
                f"<em>{turn}</em> onto <strong>{cur_name}</strong>."
            )
            seg_dist=0.0; prev_name=cur_name
        prev_b=cur_b
    seg_dist+=haversine(*nodes[path[-2]],*nodes[path[-1]])
    ds=f"{int(seg_dist)}m" if seg_dist<1000 else f"{seg_dist/1000:.1f}km"
    steps.append(f"🏁 Continue <strong>{ds}</strong> — arrive at <strong>{dst_name}</strong>.")
    return steps

# ── API endpoint ─────────────────────────────────────────────────────────────
@app.route("/api/search", methods=["POST"])
def api_search():
    try:
        body     = request.json
        src_lat  = float(body["src_lat"]);  src_lon = float(body["src_lon"])
        dst_lat  = float(body["dst_lat"]);  dst_lon = float(body["dst_lon"])
        src_name = body.get("src_name","Source")
        dst_name = body.get("dst_name","Destination")
        mid_lat  = (src_lat+dst_lat)/2;    mid_lon = (src_lon+dst_lon)/2
        span     = haversine(src_lat,src_lon,dst_lat,dst_lon)
        radius   = max(1400, min(span*0.85, 3200))
        osm              = fetch_graph(mid_lat,mid_lon,radius)
        nodes,adj,wn     = build_graph(osm)
        if not nodes:
            return jsonify({"error":"No road data. Try a different pair."}),400
        sn = nearest_node(nodes,src_lat,src_lon)
        dn = nearest_node(nodes,dst_lat,dst_lon)
        path,visited = astar(nodes,adj,sn,dn)
        if not path:
            return jsonify({"error":"No path found between these locations."}),400
        # Build explored edges: for each visited node, emit segments to its neighbours
        # that were also visited (i.e. roads A* actually traversed), capped for perf.
        visited_set = set(visited)
        edges_seen  = set()
        explored_edges = []
        for n in visited:
            for nb, _, _ in adj.get(n, []):
                if nb in visited_set:
                    key = (min(n,nb), max(n,nb))
                    if key not in edges_seen:
                        edges_seen.add(key)
                        a, b = nodes[n], nodes[nb]
                        explored_edges.append([[a[0],a[1]],[b[0],b[1]]])
            if len(explored_edges) > 2000:   # cap so payload stays reasonable
                break
        path_coords   = [[nodes[n][0],nodes[n][1]] for n in path]
        total_dist    = sum(
            haversine(path_coords[i][0],path_coords[i][1],
                      path_coords[i+1][0],path_coords[i+1][1])
            for i in range(len(path_coords)-1)
        )
        directions = generate_directions(path,nodes,wn,src_name,dst_name)
        return jsonify({
            "visited":     explored_edges,
            "path":        path_coords,
            "directions":  directions,
            "stats":{
                "nodes_explored": len(visited),
                "path_nodes":     len(path),
                "distance_m":     round(total_dist),
                "distance_km":    round(total_dist/1000,2),
            }
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error":str(e)}),500

# ── Frontend ──────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>A* NYC Pathfinder</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
:root{
  --bg:#080d12;--sur:#0f1820;--s2:#17232f;--bdr:#243040;
  --acc:#00d4ff;--grn:#2dea7a;--red:#ff4560;--amb:#ffa827;
  --pur:#a78bfa;--ylw:#f5c518;--txt:#ddeeff;--mut:#5a7a99;
  --mono:"JetBrains Mono",monospace;--sans:"DM Sans",sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100vh;overflow:hidden;background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:14px;}

.topbar{height:50px;background:var(--sur);border-bottom:1px solid var(--bdr);
  display:flex;align-items:center;justify-content:space-between;
  padding:0 20px;z-index:1000;position:relative;}
.logo{font-family:var(--mono);font-weight:700;font-size:13px;color:var(--acc);letter-spacing:.06em;}
.logo span{color:var(--mut);font-weight:400;}
.badges{display:flex;gap:7px;}
.badge{font-family:var(--mono);font-size:10px;border:1px solid var(--bdr);
  border-radius:3px;padding:3px 10px;color:var(--mut);transition:all .3s;white-space:nowrap;}
.badge.lit{border-color:var(--acc);color:var(--acc);}
.badge.ok{border-color:var(--grn);color:var(--grn);}
.badge.err{border-color:var(--red);color:var(--red);}

.layout{display:grid;grid-template-columns:310px 1fr;height:calc(100vh - 50px);}

.sidebar{background:var(--sur);border-right:1px solid var(--bdr);display:flex;flex-direction:column;overflow:hidden;}
.sb-head{padding:12px 16px;border-bottom:1px solid var(--bdr);
  font-family:var(--mono);font-size:9px;color:var(--acc);font-weight:700;letter-spacing:.12em;text-transform:uppercase;}
.sb-body{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:12px;}

.sec-title{font-family:var(--mono);font-size:9px;color:var(--mut);
  letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;}

/* Location grid */
.loc-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;}
.loc-btn{background:var(--s2);border:1px solid var(--bdr);border-radius:5px;
  padding:9px 6px;cursor:pointer;text-align:center;transition:all .18s;
  color:var(--txt);font-family:var(--mono);font-size:10px;line-height:1.4;
  position:relative;}
.loc-btn:hover{border-color:var(--acc);background:#0d1e2e;}
.loc-btn.sel-src{border-color:var(--grn);background:#0a2018;color:var(--grn);}
.loc-btn.sel-dst{border-color:var(--red);background:#200a12;color:var(--red);}
.loc-btn .lbl{font-weight:700;font-size:15px;display:block;line-height:1.2;}
.loc-btn .name{font-size:8px;color:var(--mut);margin-top:2px;line-height:1.3;}
.loc-btn.sel-src .name{color:#2dea7a88;}
.loc-btn.sel-dst .name{color:#ff456088;}

/* Selected pair */
.pair-row{display:flex;align-items:center;gap:8px;}
.pair-tag{font-family:var(--mono);font-size:9px;text-transform:uppercase;
  letter-spacing:.07em;padding:2px 8px;border-radius:3px;flex-shrink:0;}
.pair-tag.src{background:#0a2018;color:var(--grn);border:1px solid var(--grn);}
.pair-tag.dst{background:#200a12;color:var(--red);border:1px solid var(--red);}
.pair-val{font-family:var(--mono);font-size:11px;flex:1;color:var(--txt);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pair-val.empty{color:var(--mut);}
.swap-btn{background:none;border:1px solid var(--bdr);color:var(--mut);
  padding:4px 8px;border-radius:4px;cursor:pointer;font-size:13px;transition:all .2s;flex-shrink:0;}
.swap-btn:hover{border-color:var(--acc);color:var(--acc);}

.run-btn{background:var(--acc);border:none;color:#000;
  font-family:var(--mono);font-size:12px;font-weight:700;
  padding:11px;border-radius:5px;cursor:pointer;width:100%;
  transition:all .2s;letter-spacing:.04em;}
.run-btn:hover:not(:disabled){background:#33ddff;}
.run-btn:disabled{background:var(--bdr);color:var(--mut);cursor:not-allowed;}
.run-btn.loading{background:var(--amb);color:#000;animation:pulse 1s ease infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.55;}}

.prog-bar{height:2px;background:var(--bdr);border-radius:1px;overflow:hidden;}
.prog-fill{height:100%;background:var(--acc);width:0%;transition:width .4s;}

.err-box{background:#200a12;border:1px solid var(--red);border-radius:5px;
  padding:9px 12px;font-size:11px;color:var(--red);font-family:var(--mono);display:none;line-height:1.5;}

/* Stats */
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;}
.stat-card{background:var(--bg);border:1px solid var(--bdr);border-radius:5px;padding:9px 10px;}
.stat-val{font-family:var(--mono);font-size:18px;font-weight:700;color:var(--acc);}
.stat-lbl{font-family:var(--mono);font-size:8px;color:var(--mut);margin-top:3px;line-height:1.4;}

/* Directions */
.dir-list{display:flex;flex-direction:column;gap:5px;}
.dir-step{background:var(--bg);border-left:2px solid var(--bdr);
  padding:8px 10px;font-size:11px;line-height:1.65;color:var(--txt);}
.dir-step:first-child{border-left-color:var(--grn);}
.dir-step:last-child{border-left-color:var(--red);}
.dir-step strong{color:var(--acc);}
.dir-step em{color:var(--amb);font-style:normal;font-weight:600;}

/* Legend */
.legend{display:flex;flex-direction:column;gap:5px;}
.leg-row{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:10px;color:var(--mut);}
.leg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}

.reset-btn{background:none;border:1px solid var(--bdr);color:var(--mut);
  font-family:var(--mono);font-size:10px;padding:8px;border-radius:5px;
  cursor:pointer;width:100%;transition:all .2s;}
.reset-btn:hover{border-color:var(--red);color:var(--red);}

.map-wrap{position:relative;}
#map{width:100%;height:100%;}
.map-hint{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);
  background:#080d12cc;border:1px solid var(--bdr);
  font-family:var(--mono);font-size:10px;color:var(--mut);
  padding:6px 18px;border-radius:20px;z-index:900;
  pointer-events:none;backdrop-filter:blur(4px);transition:opacity .4s;}

::-webkit-scrollbar{width:4px;}
::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:2px;}

.leaflet-popup-content-wrapper{background:var(--sur)!important;border:1px solid var(--acc)!important;
  border-radius:0!important;box-shadow:0 4px 24px #000c!important;}
.leaflet-popup-content{color:var(--txt)!important;font-family:var(--mono);font-size:11px;margin:10px 14px!important;}
.leaflet-popup-tip{background:var(--sur)!important;}
.leaflet-popup-close-button{color:var(--mut)!important;}
.leaflet-control-zoom{display:none;}
.leaflet-control-attribution{background:#080d12bb!important;color:var(--mut)!important;font-size:9px!important;}
.leaflet-control-attribution a{color:var(--mut)!important;}
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">A<span>*</span> <span>/ NYC Manhattan Pathfinder</span></div>
  <div class="badges">
    <div class="badge lit">A* ALGORITHM</div>
    <div class="badge" id="b-explored">— nodes</div>
    <div class="badge" id="b-status">IDLE</div>
    <div class="badge" id="b-dist">— km</div>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="sb-head">⬡ Manhattan Pathfinder</div>
    <div class="sb-body">

      <div>
        <div class="sec-title">Select Locations A – F</div>
        <div style="font-size:10px;color:var(--mut);margin-bottom:8px;line-height:1.5;">
          1st click → <span style="color:var(--grn)">● Source</span> &nbsp; 2nd click → <span style="color:var(--red)">● Destination</span>
        </div>
        <div class="loc-grid" id="loc-grid"></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:6px;">
        <div class="pair-row">
          <div class="pair-tag src">FROM</div>
          <div class="pair-val empty" id="src-label">— not selected —</div>
        </div>
        <div class="pair-row">
          <div class="pair-tag dst">TO</div>
          <div class="pair-val empty" id="dst-label">— not selected —</div>
          <button class="swap-btn" onclick="swapLocations()" title="Swap source & destination">⇄</button>
        </div>
      </div>

      <button class="run-btn" id="run-btn" onclick="runSearch()" disabled>▶ RUN A* SEARCH</button>
      <div class="prog-bar"><div class="prog-fill" id="prog-fill"></div></div>
      <div class="err-box" id="err-box"></div>

      <div id="stats-section" style="display:none;">
        <div class="sec-title" style="margin-bottom:6px;">Search Results</div>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-val" id="s-explored">—</div>
            <div class="stat-lbl">NODES<br>EXPLORED</div>
          </div>
          <div class="stat-card">
            <div class="stat-val" id="s-path">—</div>
            <div class="stat-lbl">PATH<br>NODES</div>
          </div>
          <div class="stat-card">
            <div class="stat-val" id="s-dist">—</div>
            <div class="stat-lbl">TOTAL COST<br>(METRES)</div>
          </div>
          <div class="stat-card">
            <div class="stat-val" id="s-km">—</div>
            <div class="stat-lbl">TOTAL COST<br>(KM)</div>
          </div>
        </div>
      </div>

      <div id="dir-section" style="display:none;">
        <div class="sec-title" style="margin-bottom:6px;">↪ Route Directions</div>
        <div class="dir-list" id="dir-list"></div>
      </div>

      <div class="legend">
        <div class="leg-row"><div style="width:18px;height:3px;background:#00d4ff;opacity:.7;border-radius:2px;flex-shrink:0"></div>Explored roads (A* frontier)</div>
        <div class="leg-row"><div style="width:18px;height:3px;background:#f5c518;border-radius:2px;flex-shrink:0"></div>Optimal shortest path</div>
        <div class="leg-row"><div class="leg-dot" style="background:#2dea7a"></div>Source location</div>
        <div class="leg-row"><div class="leg-dot" style="background:#ff4560"></div>Destination location</div>
      </div>

      <button class="reset-btn" onclick="resetAll()">↺ RESET</button>
    </div>
  </div>

  <div class="map-wrap">
    <div id="map"></div>
    <div class="map-hint" id="map-hint">Select Source and Destination from the panel</div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
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
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    print("\n🚀  A* NYC Pathfinder  →  http://127.0.0.1:5050\n")
    app.run(debug=False, port=5050)