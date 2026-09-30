"""Graph-Layout (Sugiyama) für Flowcharts, Klassen-, Zustands- und ER-Diagramme – ohne Qt, ohne Graphviz.

Ablauf je Container (Wurzel oder Subgraph):
  1. Zyklen brechen (Rückwärtskanten umdrehen), 2. Ebenen per längstem Pfad (beschriftete Kanten überspringen eine
  Ebene, die Beschriftung bekommt dort einen Platzhalter), 3. Hilfsknoten für lange Kanten, 4. Reihenfolge per
  Baryzentrum mit Kreuzungszählung, 5. x-Koordinaten durch wiederholtes Ausrichten auf die Nachbarn unter
  Einhaltung der Abstände (Blockverschmelzung), 6. y je Ebene.
Subgraphen werden zuerst für sich angeordnet und dann im Eltern-Container wie ein großer Knoten behandelt –
dadurch überlappen Rahmen nie. Kanten zwischen verschiedenen Subgraphen laufen im gemeinsamen Eltern-Container.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

CLUSTER_PAD = 16.0
CLUSTER_LABEL_GAP = 6.0


@dataclass
class LNode:
    id: str
    w: float
    h: float
    shape: str = "rect"          # rect | round | diamond | circle | ellipse (für das Andocken der Kanten)


@dataclass
class LEdge:
    key: int
    src: str
    dst: str
    label_w: float = 0.0
    label_h: float = 0.0
    minlen: int = 1


@dataclass
class LCluster:
    id: str
    parent: str | None = None
    direction: str | None = None
    label_w: float = 0.0
    label_h: float = 0.0


@dataclass
class Layout:
    nodes: dict[str, tuple[float, float]] = field(default_factory=dict)         # Mittelpunkt
    edges: dict[int, list[tuple[float, float]]] = field(default_factory=dict)  # Punkte (bereits angedockt)
    labels: dict[int, tuple[float, float]] = field(default_factory=dict)       # Mittelpunkt der Beschriftung
    clusters: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)   # x, y, w, h
    width: float = 0.0
    height: float = 0.0


# ---- flaches Sugiyama ------------------------------------------------------------------------------------------------
@dataclass
class _Item:
    id: str
    w: float
    h: float
    dummy: bool = False


def _flat_layout(items: dict[str, tuple[float, float]], edges: list[tuple], direction: str, nodesep: float,
                 ranksep: float):
    """items: id → (w, h); edges: (key, a, b, lw, lh, minlen). Liefert (pos, routes, labelpos, w, h) in lokalen
    Koordinaten; routes[key] = Punkte von a nach b (Mittelpunkte, noch nicht angedockt)."""
    horizontal = direction in ("LR", "RL")
    sizes = {k: ((h, w) if horizontal else (w, h)) for k, (w, h) in items.items()}
    order_ids = list(items)

    loops = [e for e in edges if e[1] == e[2]]
    real = [e for e in edges if e[1] != e[2] and e[1] in items and e[2] in items]
    # Schleifen brauchen seitlich Platz
    for e in loops:
        w, h = sizes[e[1]]
        sizes[e[1]] = (w + 48, h)

    # 1) Zyklen brechen (DFS in Eingabereihenfolge)
    succ: dict[str, list] = {k: [] for k in items}
    for e in real:
        succ[e[1]].append(e)
    state: dict[str, int] = {}
    reversed_keys: set[int] = set()

    def dfs(start: str) -> None:
        stack = [(start, iter(succ[start]))]
        state[start] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                continue
            target = nxt[2]
            if state.get(target) == 1:
                reversed_keys.add(nxt[0])
            elif target not in state:
                state[target] = 1
                stack.append((target, iter(succ[target])))
    for k in order_ids:
        if k not in state:
            dfs(k)
    directed = []                                  # (key, von, nach, lw, lh, minlen, umgedreht)
    for e in real:
        if e[0] in reversed_keys:
            directed.append((e[0], e[2], e[1], e[3], e[4], e[5], True))
        else:
            directed.append((e[0], e[1], e[2], e[3], e[4], e[5], False))

    # 2) Ebenen: längster Pfad
    preds: dict[str, list] = {k: [] for k in items}
    outs: dict[str, list] = {k: [] for k in items}
    for d in directed:
        preds[d[2]].append(d)
        outs[d[1]].append(d)
    indeg = {k: len(preds[k]) for k in items}
    queue = [k for k in order_ids if indeg[k] == 0]
    topo = []
    while queue:
        node = queue.pop(0)
        topo.append(node)
        for d in outs[node]:
            indeg[d[2]] -= 1
            if indeg[d[2]] == 0:
                queue.append(d[2])
    for k in order_ids:                            # Sicherheitsnetz (sollte nach dem Brechen nicht nötig sein)
        if k not in topo:
            topo.append(k)
    rank: dict[str, int] = {}
    for node in topo:
        rank[node] = max((rank.get(d[1], 0) + d[5] for d in preds[node]), default=0)
    for node in reversed(topo):                    # Quellen dicht an ihre Nachfolger ziehen
        if not preds[node] and outs[node]:
            rank[node] = max(0, min(rank[d[2]] - d[5] for d in outs[node]))

    # 3) Hilfsknoten
    layers: dict[int, list[str]] = {}
    nodes: dict[str, _Item] = {k: _Item(k, *sizes[k]) for k in items}
    chains: dict[int, list[str]] = {}
    adj_up: dict[str, list[str]] = {k: [] for k in items}
    adj_down: dict[str, list[str]] = {k: [] for k in items}
    label_node: dict[int, str] = {}
    for d in directed:
        key, a, b, lw, lh = d[0], d[1], d[2], d[3], d[4]
        ra, rb = rank[a], rank[b]
        chain = [a]
        mid = (ra + rb) // 2 if rb - ra > 1 else None
        for r in range(ra + 1, rb):
            did = f"\x00d{key}_{r}"
            if lw and r == mid:
                size = (lh, lw) if horizontal else (lw, lh)
                nodes[did] = _Item(did, size[0] + 8, size[1] + 4, True)
                label_node[key] = did
            else:
                nodes[did] = _Item(did, 0.0, 0.0, True)
            rank[did] = r
            adj_up[did], adj_down[did] = [], []
            chain.append(did)
        chain.append(b)
        for u, v in zip(chain, chain[1:]):
            adj_down[u].append(v)
            adj_up[v].append(u)
        chains[key] = chain
    for node_id in [*order_ids, *[n for n in nodes if n not in items]]:
        layers.setdefault(rank[node_id], []).append(node_id)
    max_rank = max(layers) if layers else 0
    ordered = [layers.get(r, []) for r in range(max_rank + 1)]

    # 4) Reihenfolge: Baryzentrum, beste Variante nach Kreuzungen behalten
    def crossings(order) -> int:
        total = 0
        for r in range(len(order) - 1):
            pos = {n: i for i, n in enumerate(order[r + 1])}
            pairs = sorted((i, pos[v]) for i, u in enumerate(order[r]) for v in adj_down[u] if v in pos)
            ys = [p[1] for p in pairs]
            for i in range(len(ys)):                   # O(n²) genügt für Notiz-Diagramme
                for j in range(i + 1, len(ys)):
                    if ys[j] < ys[i]:
                        total += 1
        return total

    def sweep(order, down: bool) -> None:
        rng = range(1, len(order)) if down else range(len(order) - 2, -1, -1)
        for r in rng:
            ref = order[r - 1] if down else order[r + 1]
            pos = {n: i for i, n in enumerate(ref)}
            current = {n: i for i, n in enumerate(order[r])}

            def bary(n):
                neigh = adj_up[n] if down else adj_down[n]
                vals = [pos[m] for m in neigh if m in pos]
                return sum(vals) / len(vals) if vals else current[n]
            order[r] = sorted(order[r], key=lambda n: (bary(n), current[n]))

    best = [list(layer) for layer in ordered]
    best_cross = crossings(best)
    work = [list(layer) for layer in ordered]
    for i in range(10):
        sweep(work, down=(i % 2 == 0))
        c = crossings(work)
        if c < best_cross:
            best, best_cross = [list(layer) for layer in work], c
        if best_cross == 0:
            break
    ordered = best

    # 5) x-Koordinaten
    def gap(a: str, b: str) -> float:
        na, nb = nodes[a], nodes[b]
        sep = nodesep if not (na.dummy or nb.dummy) else nodesep * 0.5
        return na.w / 2 + nb.w / 2 + sep

    xs: dict[str, float] = {}
    for layer in ordered:
        x = 0.0
        for i, n in enumerate(layer):
            if i:
                x += gap(layer[i - 1], n)
            xs[n] = x

    def place(layer: list[str], desired: dict[str, float]) -> None:
        blocks: list[dict] = []
        for n in layer:
            blocks.append({"nodes": [n], "offs": [0.0], "x": desired[n]})
            while len(blocks) > 1:
                prev, cur = blocks[-2], blocks[-1]
                need = prev["x"] + prev["offs"][-1] + gap(prev["nodes"][-1], cur["nodes"][0])
                if cur["x"] >= need - 1e-6:
                    break
                shift = need - prev["x"]
                prev["nodes"] += cur["nodes"]
                prev["offs"] += [shift + o for o in cur["offs"]]
                prev["x"] = sum(desired[m] - o for m, o in zip(prev["nodes"], prev["offs"])) / len(prev["nodes"])
                blocks.pop()
        for b in blocks:
            for m, o in zip(b["nodes"], b["offs"]):
                xs[m] = b["x"] + o

    def weight(a: str, b: str) -> float:
        da, db = nodes[a].dummy, nodes[b].dummy
        return 8.0 if da and db else (2.0 if da or db else 1.0)

    for it in range(24):
        mode = it % 3                                  # von oben, von unten, beide
        rng = range(len(ordered)) if mode != 1 else range(len(ordered) - 1, -1, -1)
        for r in rng:
            layer = ordered[r]
            desired = {}
            for n in layer:
                neigh = (adj_up[n] if mode == 0 else adj_down[n] if mode == 1 else adj_up[n] + adj_down[n])
                if neigh:
                    tw = sum(weight(n, m) for m in neigh)
                    desired[n] = sum(xs[m] * weight(n, m) for m in neigh) / tw
                else:
                    desired[n] = xs[n]
            place(layer, desired)
    min_x = min((xs[n] - nodes[n].w / 2 for n in xs), default=0.0)
    for n in xs:
        xs[n] -= min_x
    width = max((xs[n] + nodes[n].w / 2 for n in xs), default=0.0)

    # 6) y je Ebene
    ys: dict[str, float] = {}
    y = 0.0
    for r, layer in enumerate(ordered):
        h = max((nodes[n].h for n in layer), default=0.0)
        for n in layer:
            ys[n] = y + h / 2
        y += h + (ranksep if r < len(ordered) - 1 else 0)
    height = y

    pos = {n: (xs[n], ys[n]) for n in items}
    routes: dict[int, list[tuple[float, float]]] = {}
    labels: dict[int, tuple[float, float]] = {}
    for d in directed:
        pts = [(xs[n], ys[n]) for n in chains[d[0]]]
        if d[6]:
            pts.reverse()
        routes[d[0]] = pts
        if d[0] in label_node:
            ln = label_node[d[0]]
            labels[d[0]] = (xs[ln], ys[ln])
        elif d[3]:                                  # Kante über genau eine Ebene: Beschriftung mittig
            labels[d[0]] = ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
    for e in loops:
        cx, cy = pos[e[1]]
        w, h = items[e[1]] if not horizontal else (items[e[1]][1], items[e[1]][0])
        x0 = cx + w / 2
        routes[e[0]] = [(x0, cy - h / 4), (x0 + 22, cy - h / 3), (x0 + 22, cy + h / 3), (x0, cy + h / 4)]
        if e[3]:
            labels[e[0]] = (x0 + 26 + e[3] / 2, cy)

    # zurück in die gewünschte Richtung
    def tf(p):
        x, y = p
        if direction == "LR":
            return (y, x)
        if direction == "RL":
            return (height - y, x)
        if direction == "BT":
            return (x, height - y)
        return (x, y)
    pos = {k: tf(v) for k, v in pos.items()}
    routes = {k: [tf(p) for p in v] for k, v in routes.items()}
    labels = {k: tf(v) for k, v in labels.items()}
    if horizontal:
        width, height = height, width
    return pos, routes, labels, width, height


# ---- Andocken an die Knotenform ---------------------------------------------------------------------------------------
def clip(center, w, h, shape, toward):
    cx, cy = center
    dx, dy = toward[0] - cx, toward[1] - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return center
    hw, hh = w / 2, h / 2
    if shape in ("circle", "ellipse"):
        t = 1 / math.sqrt((dx / hw) ** 2 + (dy / hh) ** 2) if hw and hh else 0
    elif shape == "diamond":
        t = 1 / (abs(dx) / hw + abs(dy) / hh) if hw and hh else 0
    else:
        tx = hw / abs(dx) if dx else math.inf
        ty = hh / abs(dy) if dy else math.inf
        t = min(tx, ty)
    t = min(t, 1.0)
    return (cx + dx * t, cy + dy * t)


# ---- Rekursives Layout mit Subgraphen --------------------------------------------------------------------------------
def layout(nodes: list[LNode], edges: list[LEdge], clusters: list[LCluster] | None = None,
           membership: dict[str, str] | None = None, direction: str = "TB", nodesep: float = 32.0,
           ranksep: float = 44.0) -> Layout:
    """membership: Knoten-ID → Subgraph-ID (direkter Eltern-Subgraph); Subgraphen nennen ihren Eltern selbst."""
    clusters = clusters or []
    membership = membership or {}
    by_node = {n.id: n for n in nodes}
    by_cluster = {c.id: c for c in clusters}

    def parent_of(item: str) -> str | None:
        if item in by_cluster:
            p = by_cluster[item].parent
            return p if p in by_cluster else None
        p = membership.get(item)
        return p if p in by_cluster else None

    # Kinder je Container in Reihenfolge des ersten Auftretens (Subgraph = sein frühester Knoten) – das bestimmt,
    # welche Kanten beim Zyklen-Brechen als „rückwärts“ gelten
    first_seen = {n.id: i for i, n in enumerate(nodes)}
    for c in clusters:
        first_seen.setdefault(c.id, len(first_seen) + len(clusters))
    for n in nodes:
        p = parent_of(n.id)
        while p is not None:
            first_seen[p] = min(first_seen[p], first_seen[n.id])
            p = parent_of(p)
    children: dict[str | None, list[str]] = {}
    for item in sorted([c.id for c in clusters] + [n.id for n in nodes], key=lambda k: first_seen[k]):
        children.setdefault(parent_of(item), []).append(item)

    def chain(item: str) -> list[str | None]:
        out: list[str | None] = []
        p = parent_of(item)
        while p is not None:
            out.append(p)
            p = parent_of(p)
        out.append(None)
        return out[::-1]                            # Wurzel … direkter Eltern

    def lift(node: str, container: str | None) -> str:
        """Direktes Kind von `container`, das `node` enthält."""
        item = node
        while parent_of(item) != container:
            item = parent_of(item)
        return item

    assigned: dict[str | None, list[tuple]] = {}
    known = set(by_node) | set(by_cluster)
    for e in edges:
        if e.src not in known or e.dst not in known:            # Endpunkte dürfen auch Subgraphen sein
            continue
        ca, cb = chain(e.src), chain(e.dst)
        common = None
        for x, y in zip(ca, cb):
            if x == y:
                common = x
            else:
                break
        a, b = lift(e.src, common), lift(e.dst, common)
        if a == b and e.src != e.dst:                           # Rahmen ↔ eigener Inhalt: nicht anordnen
            continue
        minlen = max(e.minlen, 2 if e.label_w else 1) if a != b else e.minlen
        assigned.setdefault(common, []).append((e.key, a, b, e.label_w, e.label_h, minlen))

    local: dict[str | None, tuple] = {}
    sizes: dict[str, tuple[float, float]] = {n.id: (n.w, n.h) for n in nodes}

    def solve(container: str | None) -> None:
        for child in children.get(container, []):
            if child in by_cluster:
                solve(child)
        members = children.get(container, [])
        items = {m: sizes[m] for m in members}
        c = by_cluster.get(container) if container else None
        d = (c.direction if c and c.direction else direction)
        result = _flat_layout(items, assigned.get(container, []), d, nodesep, ranksep)
        local[container] = result
        if c is not None:
            w, h = result[3], result[4]
            head = c.label_h + CLUSTER_LABEL_GAP if c.label_h else 0
            sizes[c.id] = (max(w, c.label_w) + 2 * CLUSTER_PAD, h + 2 * CLUSTER_PAD + head)

    solve(None)
    out = Layout()
    absolute: dict[str, tuple[float, float]] = {}

    def place(container: str | None, ox: float, oy: float) -> None:
        pos, routes, labels, w, h = local[container]
        for item, (x, y) in pos.items():
            absolute[item] = (ox + x, oy + y)
            if item in by_cluster:
                cw, ch = sizes[item]
                cx, cy = ox + x - cw / 2, oy + y - ch / 2
                out.clusters[item] = (cx, cy, cw, ch)
                c = by_cluster[item]
                inner_w = local[item][3]
                head = c.label_h + CLUSTER_LABEL_GAP if c.label_h else 0
                place(item, cx + (cw - inner_w) / 2, cy + CLUSTER_PAD + head)
        for key, pts in routes.items():
            out.edges[key] = [(ox + x, oy + y) for x, y in pts]
        for key, (x, y) in labels.items():
            out.labels[key] = (ox + x, oy + y)

    margin = 8.0
    place(None, margin, margin)
    for n in nodes:
        out.nodes[n.id] = absolute[n.id]
    # Kanten bis zu den echten Knoten verlängern und an deren Form andocken
    def anchor(item: str):
        if item in by_node:
            n = by_node[item]
            return out.nodes[item], n.w, n.h, n.shape
        x, y, w, h = out.clusters[item]
        return (x + w / 2, y + h / 2), w, h, "rect"
    for e in edges:
        if e.key not in out.edges or e.src == e.dst:
            continue
        pts = list(out.edges[e.key])
        (ca, wa, ha, sa), (cb, wb, hb, sb) = anchor(e.src), anchor(e.dst)
        pts[0], pts[-1] = ca, cb
        pts[0] = clip(ca, wa, ha, sa, pts[1])
        pts[-1] = clip(cb, wb, hb, sb, pts[-2])
        out.edges[e.key] = pts
    w, h = local[None][3], local[None][4]
    out.width, out.height = w + 2 * margin, h + 2 * margin
    return out
