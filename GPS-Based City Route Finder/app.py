from flask import Flask, render_template_string, request, jsonify, send_file
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
@app.route("/")
def index():
    return send_file('main.html')

@app.route("/script.js")
def script():
    return send_file('script.js')

@app.route("/style.css")
def style():
    return send_file('style.css')

if __name__ == "__main__":
    print("\n🚀  A* NYC Pathfinder  →  http://127.0.0.1:5050\n")
    app.run(debug=False, port=5050)