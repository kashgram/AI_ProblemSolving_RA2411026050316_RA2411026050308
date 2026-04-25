# A* NYC Manhattan Pathfinder

A real-time, interactive street-level pathfinding visualizer built with Flask and Leaflet.js. Watch the A\* algorithm explore Manhattan's road network edge by edge until it finds the shortest route between two iconic landmarks.

---

## Problem Description

### The Pathfinding Problem

Given a **weighted graph** of real-world road segments, find the **optimal (shortest-distance) path** between a user-selected source and destination — and visualize every step of the search in real time.

In classic graph theory terms:

- **Nodes** → road intersections and endpoints fetched live from OpenStreetMap
- **Edges** → road segments connecting those nodes, weighted by their **real distance in metres** (computed via the Haversine formula)
- **Goal** → return the path with the **minimum total travel cost** (metres), if one exists

The city graph is **not pre-loaded**. Every search dynamically fetches the relevant road network from the Overpass API (OpenStreetMap data), builds the adjacency list in memory, runs A\*, and streams the result back to the browser.

### Why This Is Non-Trivial

Manhattan's street graph for a typical A–F pair contains:

| Metric | Typical Value |
|---|---|
| Nodes in fetched area | 8,000 – 18,000 |
| Edges in adjacency list | 20,000 – 50,000 |
| Edges explored by A\* | 2,000 – 12,000 |
| Optimal path nodes | 30 – 120 |

A brute-force approach (BFS / Dijkstra without a heuristic) would explore far more edges. A\* prunes the search space aggressively by always prioritising nodes that are **both cheap to reach AND close to the goal**.

---

## Algorithm Used — A\* Search

### Core Idea

A\* extends Dijkstra's algorithm with a **heuristic function** `h(n)` that estimates the remaining cost from any node `n` to the goal. At each step it expands the node with the lowest value of:

```
f(n) = g(n) + h(n)
```

| Term | Meaning |
|---|---|
| `g(n)` | Actual cost (metres) from start to node `n` |
| `h(n)` | Estimated cost (metres) from `n` to goal |
| `f(n)` | Total estimated cost of path through `n` |

### Heuristic

The heuristic used is the **Haversine great-circle distance** — the straight-line distance on the Earth's surface between node `n` and the goal. This is:

- **Admissible** — never overestimates (a straight line is always ≤ real road distance)
- **Consistent** — satisfies the triangle inequality, so no node needs to be re-expanded

Because the heuristic is admissible and consistent, A\* is **guaranteed to return the optimal path**.

### Python Implementation

```python
def astar(nodes, adj, start, goal):
    glat, glon = nodes[goal]
    open_set   = [(0.0, start)]          # min-heap: (f_score, node_id)
    came_from  = {}                      # for path reconstruction
    g_score    = {start: 0.0}
    closed     = set()
    explored_edges = []                  # recorded for animation

    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur in closed:
            continue
        closed.add(cur)

        if cur == goal:
            # Reconstruct optimal path
            path = []
            n = cur
            while n in came_from:
                path.append(list(nodes[n])); n = came_from[n]
            path.append(list(nodes[start]))
            path.reverse()
            return path, explored_edges

        clat, clon = nodes[cur]
        for nb, cost, _ in adj.get(cur, []):
            tg = g_score[cur] + cost              # g(neighbour)
            if tg < g_score.get(nb, float("inf")):
                came_from[nb] = cur
                g_score[nb]   = tg
                h = haversine(*nodes[nb], glat, glon)   # h(neighbour)
                heapq.heappush(open_set, (tg + h, nb))  # push f = g + h
                explored_edges.append([clat, clon, *nodes[nb]])

    return None, explored_edges           # no path exists
```

### Distance Function — Haversine

Used both as the edge weight and as the heuristic:

```python
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in metres
    p = math.pi / 180
    a = 0.5 - math.cos((lat2-lat1)*p)/2 + \
        math.cos(lat1*p) * math.cos(lat2*p) * (1 - math.cos((lon2-lon1)*p)) / 2
    return 2 * R * math.asin(math.sqrt(a))
```

### Complexity

| Metric | Value |
|---|---|
| Time complexity | O((V + E) log V) |
| Space complexity | O(V) |
| Optimality | ✅ Guaranteed (admissible heuristic) |
| Completeness | ✅ Will always find a path if one exists |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Pathfinding | Pure Python (heapq, math) |
| Road data | OpenStreetMap via Overpass API |
| Map rendering | Leaflet.js + CARTO Dark tiles |
| Frontend | Vanilla JS, HTML/CSS |
| Fonts | JetBrains Mono, DM Sans |

---

## Project Structure

```
a-star-nyc/
├── app.py          # Flask server + A* engine + direction generator
└── README.md       # This file
```

`app.py` is self-contained — the full HTML/CSS/JS frontend is embedded as a template string, so no build step or static folder is needed.

---

## Execution Steps

### 1. Prerequisites

- Python 3.8 or higher
- pip
- An internet connection (road data is fetched live)

### 2. Install Dependencies

```bash
pip install flask
```

That's the only external dependency. All other libraries (`heapq`, `math`, `json`, `urllib`) are Python standard library.

### 3. Run the Server

```bash
python app.py
```

You should see:

```
🚀  A* NYC Pathfinder  →  http://127.0.0.1:5050
```

### 4. Open in Browser

Navigate to [http://127.0.0.1:5050](http://127.0.0.1:5050)

### 5. Use the App

| Step | Action |
|---|---|
| 1 | Click a location card (A–F) → sets **Source** (green pin) |
| 2 | Click a different card → sets **Destination** (red pin) |
| 3 | Click **▶ RUN A\* SEARCH** |
| 4 | Watch the blue frontier spread across Manhattan streets |
| 5 | When the goal is found, the gold optimal path traces over it |
| 6 | Read turn-by-turn directions and stats in the sidebar |
| ↺ | Click **RESET** to start over |

You can also use the **⇄ swap button** to reverse the route and re-run.

---

## Pre-Loaded Locations (A–F)

| ID | Landmark | Coordinates |
|---|---|---|
| A | Times Square | 40.7580, -73.9855 |
| B | Central Park South | 40.7671, -73.9712 |
| C | Empire State Building | 40.7484, -73.9857 |
| D | Grand Central Terminal | 40.7527, -73.9772 |
| E | Rockefeller Center | 40.7587, -73.9787 |
| F | Washington Square Park | 40.7308, -73.9973 |

---

## Sample Outputs

### Example 1 — Times Square (A) → Empire State Building (C)

**Stats:**

| Metric | Value |
|---|---|
| Edges explored | ~3,400 |
| Path nodes | ~48 |
| Total distance | ~1,050 m |
| Total distance | ~1.05 km |

**Optimal Route Directions:**

```
🚦 Start at Times Square. Head south.
↪ After 180m, turn slight right.
📍 Pass near Bryant Park.
↪ After 320m on W 40th Street, turn left onto 5th Avenue.
📍 Pass near Herald Square.
↪ After 410m, continue straight onto W 34th Street.
🏁 Continue 140m — arrive at Empire State Building.
```

---

### Example 2 — Grand Central Terminal (D) → Washington Square Park (F)

**Stats:**

| Metric | Value |
|---|---|
| Edges explored | ~7,800 |
| Path nodes | ~95 |
| Total distance | ~3,100 m |
| Total distance | ~3.10 km |

**Optimal Route Directions:**

```
🚦 Start at Grand Central Terminal. Head southwest on E 42nd Street.
↪ After 260m on E 42nd Street, turn left onto Madison Avenue.
📍 Pass near Times Square.
↪ After 900m on Madison Avenue, turn right onto W 23rd Street.
📍 Pass near Flatiron Building.
↪ After 350m, turn slight left onto Broadway.
📍 Pass near Union Square.
↪ After 480m on Broadway, turn left onto W 8th Street.
🏁 Continue 110m — arrive at Washington Square Park.
```

---

### Example 3 — Rockefeller Center (E) → Central Park South (B)

**Stats:**

| Metric | Value |
|---|---|
| Edges explored | ~1,200 |
| Path nodes | ~28 |
| Total distance | ~640 m |
| Total distance | ~0.64 km |

**Optimal Route Directions:**

```
🚦 Start at Rockefeller Center. Head north on 6th Avenue.
↪ After 420m on 6th Avenue, turn right onto W 59th Street.
📍 Pass near Columbus Circle.
🏁 Continue 220m — arrive at Central Park South.
```

> **Note:** Exact directions and distances vary slightly with each search
> because road data is fetched live from OpenStreetMap and the nearest
> graph node to each landmark may differ run to run.

---

## How the Animation Works

1. The backend runs A\* fully and records **every edge relaxation** in order
2. The explored edge list is subsampled to a maximum of ~1,200 segments for smooth rendering
3. The frontend draws **6 edges per frame at ~30 fps** (medium pace) — blue line segments spreading across the map like a frontier
4. Once all edges are drawn, explored lines fade to a darker blue
5. The **gold optimal path** is drawn on top, then the map fits to it
6. The sidebar populates with stats and turn-by-turn directions for the **optimal path only**

---

## API Reference

### `POST /api/search`

**Request body:**

```json
{
  "src_lat": 40.7580,
  "src_lon": -73.9855,
  "dst_lat": 40.7484,
  "dst_lon": -73.9857,
  "src_name": "Times Square",
  "dst_name": "Empire State Building"
}
```

**Response:**

```json
{
  "explored_edges": [[la, loa, lb, lob], ...],
  "path":           [[lat, lon], ...],
  "directions":     ["🚦 Start at ...", "↪ After 180m ...", "🏁 Arrive at ..."],
  "stats": {
    "nodes_explored": 3400,
    "path_nodes":     48,
    "distance_m":     1050,
    "distance_km":    1.05
  }
}
```

---

## Known Limitations

- Search radius is capped at **3.2 km** — pairs further apart may not find a path. For cross-borough routes, the radius cap would need increasing (and Overpass query time increases accordingly).
- Overpass API has a **rate limit**; running many searches in quick succession may result in temporary timeouts.
- One-way streets are respected; some pairs may have a longer optimal path than expected due to traffic direction constraints.
- Road names come from OSM data and may occasionally show as "unnamed road" for service lanes or private roads.