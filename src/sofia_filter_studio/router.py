"""Two-layer grid router (A* on a 0.635 mm grid, 45-degree moves, vias, rip-up and reroute).

Nets are routed one connection at a time, from the copper already laid for the net to the nearest
unconnected pad. Every grid node knows which net may use it: the clearance zones of pads, tracks and
vias are claimed as they are placed, and a second map says where a via of each net still fits. The
top layer is preferred; the bottom one is left mostly free for the ground plane.

When a connection does not fit, a relaxed search that may cross other nets' tracks names the nets in
the way; those are ripped up, the stuck connection is routed, and they go back to the queue.
"""

from __future__ import annotations

import heapq
import math
from collections import Counter, deque
from dataclasses import dataclass, field

from .geometry import Capsule, Shape, circle, point_distance

FREE, BLOCKED = -1, -2
DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
CROSSING_COST = 25.0  # relaxed search: price of crossing another net's track


@dataclass(frozen=True, slots=True)
class Rules:
    track: float = 0.3
    clearance: float = 0.25
    via_diameter: float = 0.8
    via_drill: float = 0.4
    edge: float = 0.5
    grid: float = 0.635


@dataclass(slots=True)
class Terminal:
    """A pad to connect: net, copper shape, layers (0 top, 1 bottom) and center."""

    key: tuple[str, str]
    net: str
    shape: Shape
    layers: tuple[int, ...]
    x: float
    y: float


@dataclass(slots=True)
class Track:
    layer: int
    x1: float
    y1: float
    x2: float
    y2: float
    net: str
    width: float


@dataclass(slots=True)
class Via:
    x: float
    y: float
    net: str
    diameter: float
    drill: float


@dataclass(slots=True)
class RouteResult:
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    unrouted: list[tuple[str, tuple[str, str], tuple[str, str]]] = field(default_factory=list)


class Router:
    def __init__(
        self,
        outline: tuple[float, float, float, float],
        terminals: list[Terminal],
        obstacles: list[Shape],
        rules: Rules,
        layer_cost: tuple[float, float] = (1.0, 2.2),
        via_cost: float = 12.0,
    ) -> None:
        self.rules = rules
        self.outline = outline
        self.terminals = terminals
        self.obstacles = obstacles
        self.layer_cost = layer_cost
        self.via_cost = via_cost
        x1, y1, x2, y2 = outline
        g = rules.grid
        self.x0, self.y0 = x1, y1
        self.nx = int((x2 - x1) / g) + 1
        self.ny = int((y2 - y1) / g) + 1
        self.nets = sorted({terminal.net for terminal in terminals})
        self.net_id = {net: index for index, net in enumerate(self.nets)}
        self.by_net: dict[str, list[Terminal]] = {}
        for terminal in terminals:
            self.by_net.setdefault(terminal.net, []).append(terminal)
        self._prepare()

    # Grid ----------------------------------------------------------------------------------------
    def _xy(self, index: int) -> tuple[float, float]:
        return self.x0 + (index % self.nx) * self.rules.grid, self.y0 + (index // self.nx) * self.rules.grid

    def _claim(self, layer: int, shape: Shape, owner: int, reach: float, net: str | None = None) -> list[int]:
        """Give the nodes within ``reach`` of ``shape`` to ``owner`` (or block them if contested).

        The same pass fills the via map: nodes closer than a via radius plus the clearance can only
        take a via of ``owner``. With ``net`` (tracks and vias) the claims are also recorded, so the
        relaxed search can tell which nets are in the way.
        """
        g = self.rules.grid
        via_reach = self.rules.via_diameter / 2 + self.rules.clearance
        far = max(reach, via_reach)
        x1, y1, x2, y2 = shape.bounds()
        i1 = max(0, math.floor((x1 - far - self.x0) / g))
        i2 = min(self.nx - 1, math.ceil((x2 + far - self.x0) / g))
        j1 = max(0, math.floor((y1 - far - self.y0) / g))
        j2 = min(self.ny - 1, math.ceil((y2 + far - self.y0) / g))
        cells = self.owner[layer]
        vias = self.via_owner[layer]
        inside = []
        for j in range(j1, j2 + 1):
            y = self.y0 + j * g
            for i in range(i1, i2 + 1):
                x = self.x0 + i * g
                gap = point_distance(x, y, shape)
                if gap >= far - 1e-9:
                    continue
                index = j * self.nx + i
                if gap < reach - 1e-9:
                    current = cells[index]
                    if current == FREE:
                        cells[index] = owner
                    elif current != owner:
                        cells[index] = BLOCKED
                    if gap <= 1e-9:
                        inside.append(index)
                    if net is not None:
                        self.claims.setdefault((layer, index, 0), set()).add(net)
                if gap < via_reach - 1e-9:
                    current = vias[index]
                    if current == FREE:
                        vias[index] = owner
                    elif current != owner:
                        vias[index] = BLOCKED
                    if net is not None:
                        self.claims.setdefault((layer, index, 1), set()).add(net)
        return inside

    def _prepare(self) -> None:
        """Board edge, holes and pads: the fixed part of the grid, kept as the base for replays."""
        r = self.rules
        size = self.nx * self.ny
        self.owner = [[FREE] * size, [FREE] * size]
        self.via_owner = [[FREE] * size, [FREE] * size]
        self.claims: dict[tuple[int, int, int], set[str]] = {}
        x1, y1, x2, y2 = self.outline
        keep = r.edge + r.track / 2
        via_keep = r.edge + r.via_diameter / 2
        for layer in (0, 1):
            cells, vias = self.owner[layer], self.via_owner[layer]
            for j in range(self.ny):
                y = self.y0 + j * r.grid
                for i in range(self.nx):
                    x = self.x0 + i * r.grid
                    edge = min(x - x1, x2 - x, y - y1, y2 - y)
                    if edge < keep:
                        cells[j * self.nx + i] = BLOCKED
                    if edge < via_keep:
                        vias[j * self.nx + i] = BLOCKED
        reach = r.clearance + r.track / 2
        for shape in self.obstacles:
            for layer in (0, 1):
                self._claim(layer, shape, BLOCKED, reach)
        self.pad_nodes: dict[tuple[str, str], set[tuple[int, int]]] = {}
        for terminal in self.terminals:
            net = self.net_id[terminal.net]
            nodes = set()
            for layer in terminal.layers:
                for index in self._claim(layer, terminal.shape, net, reach):
                    nodes.add((layer, index))
            self.pad_nodes[terminal.key] = nodes
        for terminal in self.terminals:
            net = self.net_id[terminal.net]
            nodes = {state for state in self.pad_nodes[terminal.key] if self.owner[state[0]][state[1]] == net}
            if not nodes:
                # Pad touched by no usable node: take the nearest free node of its net.
                i = round((terminal.x - self.x0) / r.grid)
                j = round((terminal.y - self.y0) / r.grid)
                for layer in terminal.layers:
                    if 0 <= i < self.nx and 0 <= j < self.ny and self.owner[layer][j * self.nx + i] in (FREE, net):
                        nodes.add((layer, j * self.nx + i))
            self.pad_nodes[terminal.key] = nodes
        self.base_owner = [list(layer) for layer in self.owner]
        self.base_via_owner = [list(layer) for layer in self.via_owner]

    def _replay(self) -> None:
        """Grid with the pads plus every path still committed."""
        self.owner = [list(layer) for layer in self.base_owner]
        self.via_owner = [list(layer) for layer in self.base_via_owner]
        self.claims = {}
        for net, entries in self.paths.items():
            for path, _, _ in entries:
                self._claim_path(net, path)

    # Paths ---------------------------------------------------------------------------------------
    def _geometry(self, path: list[tuple[int, int]]):
        """Straight segments per layer and the via positions of a path of grid states."""
        segments, vias = [], []
        start = 0
        for k in range(1, len(path) + 1):
            if k == len(path) or path[k][0] != path[start][0]:
                layer = path[start][0]
                nodes = [self._xy(index) for _, index in path[start:k]]
                corners = [nodes[0]]
                for a, b, c in zip(nodes, nodes[1:], nodes[2:]):
                    if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) != 0:
                        corners.append(b)
                if len(nodes) > 1:
                    corners.append(nodes[-1])
                segments += [(layer, a, b) for a, b in zip(corners, corners[1:])]
                if k < len(path):
                    vias.append(self._xy(path[k][1]))
                start = k
        return segments, vias

    def _claim_path(self, net: str, path: list[tuple[int, int]]) -> None:
        r = self.rules
        net_id = self.net_id[net]
        reach = r.clearance + r.track / 2
        segments, vias = self._geometry(path)
        for layer, (x1, y1), (x2, y2) in segments:
            self._claim(layer, Capsule(x1, y1, x2, y2, r.track / 2), net_id, reach, net)
        for x, y in vias:
            shape = circle(x, y, r.via_diameter / 2)
            for layer in (0, 1):
                self._claim(layer, shape, net_id, reach, net)

    # Search --------------------------------------------------------------------------------------
    def _search(self, net: str, sources, targets, goal: tuple[float, float], relaxed: bool = False):
        """A* from ``sources`` to ``targets``. ``relaxed`` may cross other nets' tracks at a price."""
        net_id = self.net_id[net]
        nx, ny, g = self.nx, self.ny, self.rules.grid
        owner, via_owner = self.owner, self.via_owner
        base, base_vias = self.base_owner, self.base_via_owner
        gx, gy = (goal[0] - self.x0) / g, (goal[1] - self.y0) / g
        layer_cost = self.layer_cost
        allowed = (FREE, net_id)

        def heuristic(index: int) -> float:
            dx, dy = abs(index % nx - gx), abs(index // nx - gy)
            return max(dx, dy) + 0.414 * min(dx, dy)

        def usable(layer: int, index: int) -> float | None:
            """Extra cost of entering a node, or None when it cannot be used."""
            if owner[layer][index] in allowed:
                return 0.0
            if relaxed and base[layer][index] in allowed:
                return CROSSING_COST
            return None

        best: dict[tuple[int, int], float] = {}
        came: dict[tuple[int, int], tuple[int, int] | None] = {}
        heap: list = []
        for state in sources:
            best[state] = 0.0
            came[state] = None
            heapq.heappush(heap, (heuristic(state[1]), 0.0, state, -1))
        while heap:
            _, cost, state, direction = heapq.heappop(heap)
            if cost > best.get(state, math.inf) + 1e-9:
                continue
            if state in targets:
                path = [state]
                while came[path[-1]] is not None:
                    path.append(came[path[-1]])
                return path[::-1]
            layer, index = state
            i, j = index % nx, index // nx
            for d, (di, dj) in enumerate(DIRECTIONS):
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < ny):
                    continue
                nindex = nj * nx + ni
                extra = usable(layer, nindex)
                if extra is None:
                    continue
                if di and dj:
                    side_a, side_b = usable(layer, j * nx + ni), usable(layer, nj * nx + i)
                    if side_a is None or side_b is None:
                        continue
                    extra += side_a + side_b
                step = (1.414 if di and dj else 1.0) * layer_cost[layer] + extra
                if direction not in (-1, d):
                    step += 0.3
                next_state = (layer, nindex)
                new_cost = cost + step
                if new_cost < best.get(next_state, math.inf) - 1e-9:
                    best[next_state] = new_cost
                    came[next_state] = state
                    heapq.heappush(heap, (new_cost + heuristic(nindex), new_cost, next_state, d))
            other = 1 - layer
            extra = usable(other, index)
            if extra is None:
                continue
            if via_owner[0][index] in allowed and via_owner[1][index] in allowed:
                via_extra = 0.0
            elif relaxed and base_vias[0][index] in allowed and base_vias[1][index] in allowed:
                via_extra = CROSSING_COST
            else:
                continue
            next_state = (other, index)
            new_cost = cost + self.via_cost + extra + via_extra
            if new_cost < best.get(next_state, math.inf) - 1e-9:
                best[next_state] = new_cost
                came[next_state] = state
                heapq.heappush(heap, (new_cost + heuristic(index), new_cost, next_state, -1))
        return None

    def _blockers(self, net: str, path: list[tuple[int, int]]) -> set[str]:
        """Nets whose tracks or vias a relaxed path runs over."""
        found: set[str] = set()
        for k, (layer, index) in enumerate(path):
            found |= self.claims.get((layer, index, 0), set())
            if k + 1 < len(path) and path[k + 1][1] == index:
                found |= self.claims.get((0, index, 1), set()) | self.claims.get((1, index, 1), set())
        found.discard(net)
        return found

    # Routing -------------------------------------------------------------------------------------
    def _route_net(self, net: str) -> list[tuple[tuple[str, str], tuple[str, str], list | None]]:
        """Route every connection of a net; returns the ones that failed with their relaxed path."""
        pads = self.by_net.get(net, [])
        self.paths[net] = []
        if len(pads) < 2:
            return []
        first = min(pads, key=lambda t: (t.x, t.y))
        connected = [first]
        tree = set(self.pad_nodes[first.key])
        pending = [pad for pad in pads if pad is not first]
        failures = []
        while pending:
            pad = min(pending, key=lambda p: min(math.hypot(p.x - c.x, p.y - c.y) for c in connected))
            pending.remove(pad)
            nearest = min(connected, key=lambda c: math.hypot(pad.x - c.x, pad.y - c.y))
            targets = self.pad_nodes[pad.key]
            path = self._search(net, tree, targets, (pad.x, pad.y)) if targets and tree else None
            if path is None:
                relaxed = self._search(net, tree, targets, (pad.x, pad.y), relaxed=True) if targets and tree else None
                failures.append((nearest.key, pad.key, relaxed))
                continue
            start_pad = next((t.key for t in connected if path[0] in self.pad_nodes[t.key]), None)
            self.paths[net].append((path, start_pad, pad.key))
            self._claim_path(net, path)
            tree.update(path)
            tree.update(self.pad_nodes[pad.key])
            connected.append(pad)
        return failures

    def route(self, order: list[str] | None = None, max_ripups: int = 3) -> RouteResult:
        self.paths: dict[str, list] = {}
        self._replay()
        queue = deque(net for net in (order or self.default_order()) if len(self.by_net.get(net, [])) > 1)
        ripped = Counter()
        failed: dict[str, list] = {}
        budget = 8 * len(queue) + 10
        while queue and budget > 0:
            budget -= 1
            net = queue.popleft()
            if self.paths.get(net):
                # Routed before (it was queued twice): start over from a clean grid.
                self.paths.pop(net)
                self._replay()
            failures = self._route_net(net)
            if not failures:
                failed.pop(net, None)
                continue
            failed[net] = failures
            blockers = set()
            for _, _, relaxed in failures:
                if relaxed is not None:
                    blockers |= self._blockers(net, relaxed)
            blockers = {other for other in blockers if ripped[other] < max_ripups}
            if not blockers:
                continue
            for other in blockers:
                self.paths.pop(other, None)
                ripped[other] += 1
                if other not in queue:
                    queue.append(other)
            self.paths.pop(net, None)
            self._replay()
            queue.appendleft(net)
        for net in queue:
            failed.setdefault(net, [(None, None, None)])
        return self._result(failed)

    def _result(self, failed: dict[str, list]) -> RouteResult:
        r = self.rules
        result = RouteResult()
        centers = {terminal.key: terminal for terminal in self.terminals}
        for net, entries in self.paths.items():
            for path, start_pad, end_pad in entries:
                segments, vias = self._geometry(path)
                result.tracks += [Track(layer, a[0], a[1], b[0], b[1], net, r.track) for layer, a, b in segments]
                result.vias += [Via(x, y, net, r.via_diameter, r.via_drill) for x, y in vias]
                # Short track from the grid node to the pad center, so the joint is solid copper.
                for state, key in ((path[0], start_pad), (path[-1], end_pad)):
                    if key is None:
                        continue
                    terminal = centers[key]
                    x, y = self._xy(state[1])
                    if math.hypot(x - terminal.x, y - terminal.y) > 1e-6:
                        layer = state[0] if state[0] in terminal.layers else terminal.layers[0]
                        result.tracks.append(Track(layer, x, y, terminal.x, terminal.y, net, r.track))
        for net, failures in failed.items():
            for a, b, _ in failures:
                if a is None:
                    pads = self.by_net[net]
                    a, b = pads[0].key, pads[1].key
                result.unrouted.append((net, a, b))
        return result

    def default_order(self) -> list[str]:
        """Short signal nets first, then the supplies (they reach every package)."""

        def span(net: str) -> float:
            pads = self.by_net[net]
            xs = [p.x for p in pads]
            ys = [p.y for p in pads]
            return (max(xs) - min(xs)) + (max(ys) - min(ys))

        supplies = [net for net in ("VREF", "VCC", "GND") if net in self.by_net]
        signals = sorted((net for net in self.by_net if net not in supplies), key=span)
        return signals + supplies
