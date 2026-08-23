from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

NON_WALKABLE_HIGHWAYS = {
    "motorway", "motorway_link", "construction", "proposed", "raceway",
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.asin(math.sqrt(value))


def mesh100m_center(meshcode: str) -> tuple[float, float]:
    """Return the centre of a Japanese 10-digit 100 m mesh cell."""
    code = str(meshcode).strip()
    if len(code) != 10 or not code.isdigit():
        raise ValueError(f"expected 10-digit mesh code, got {meshcode!r}")
    lat = int(code[0:2]) * 2.0 / 3.0
    lon = int(code[2:4]) + 100.0
    lat += int(code[4]) / 12.0
    lon += int(code[5]) / 8.0
    lat += int(code[6]) / 120.0
    lon += int(code[7]) / 80.0
    lat_step = 1.0 / 1200.0
    lon_step = 1.0 / 800.0
    lat += int(code[8]) * lat_step + lat_step / 2.0
    lon += int(code[9]) * lon_step + lon_step / 2.0
    return lat, lon


def _node_key(lat: float, lon: float) -> str:
    return f"w:{lat:.7f}:{lon:.7f}"


@dataclass
class WalkingGraph:
    adjacency: dict[str, list[tuple[str, float]]]
    coordinates: dict[str, tuple[float, float]]
    edge_count: int

    @property
    def nodes(self) -> set[str]:
        return set(self.coordinates)


def walking_graph_from_overpass(data: dict[str, Any]) -> WalkingGraph:
    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    coordinates: dict[str, tuple[float, float]] = {}
    seen: set[tuple[str, str, int, int]] = set()
    edge_count = 0

    for element in data.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        highway = str(tags.get("highway", ""))
        if not highway or highway in NON_WALKABLE_HIGHWAYS:
            continue
        if str(tags.get("area", "")).lower() == "yes":
            continue
        if str(tags.get("access", "")).lower() in {"no", "private"}:
            continue
        if str(tags.get("foot", "")).lower() == "no":
            continue
        geometry = element.get("geometry") or []
        way_id = int(element.get("id") or 0)
        for idx, (first, second) in enumerate(zip(geometry, geometry[1:])):
            a = (float(first["lat"]), float(first["lon"]))
            b = (float(second["lat"]), float(second["lon"]))
            u, v = _node_key(*a), _node_key(*b)
            coordinates[u] = a
            coordinates[v] = b
            metres = max(haversine_m(*a, *b), 0.1)
            # Pedestrian routing is deliberately bidirectional. Most road one-way
            # restrictions do not prohibit pedestrians; foot=no is respected above.
            for source, target in ((u, v), (v, u)):
                key = (source, target, way_id, idx)
                if key in seen:
                    continue
                seen.add(key)
                adjacency[source].append((target, metres))
                edge_count += 1
    return WalkingGraph(dict(adjacency), coordinates, edge_count)


@dataclass
class CoordinateIndex:
    coordinates: dict[str, tuple[float, float]]
    cell_degrees: float = 0.004

    def __post_init__(self) -> None:
        self._buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
        for node, (lat, lon) in self.coordinates.items():
            self._buckets[self._bucket(lat, lon)].append(node)

    def _bucket(self, lat: float, lon: float) -> tuple[int, int]:
        return math.floor(lat / self.cell_degrees), math.floor(lon / self.cell_degrees)

    def nearest(self, lat: float, lon: float, *, max_search_m: float = 500.0) -> tuple[str | None, float]:
        if not self.coordinates:
            return None, math.inf
        base_i, base_j = self._bucket(lat, lon)
        ring_limit = max(2, int(math.ceil(max_search_m / (self.cell_degrees * 90_000))) + 2)
        candidates: list[str] = []
        for ring in range(ring_limit + 1):
            for di in range(-ring, ring + 1):
                for dj in range(-ring, ring + 1):
                    if ring and max(abs(di), abs(dj)) != ring:
                        continue
                    candidates.extend(self._buckets.get((base_i + di, base_j + dj), []))
            if candidates and ring >= 1:
                break
        if not candidates:
            return None, math.inf
        best = min(candidates, key=lambda node: haversine_m(lat, lon, *self.coordinates[node]))
        best_lat, best_lon = self.coordinates[best]
        distance = haversine_m(lat, lon, best_lat, best_lon)
        if distance > max_search_m:
            return None, distance
        return best, distance


def multisource_distances(
    graph: WalkingGraph,
    seeds: Iterable[tuple[str, float]],
    *,
    cutoff_m: float,
) -> dict[str, float]:
    dist: dict[str, float] = {}
    heap: list[tuple[float, str]] = []
    for node, initial in seeds:
        if node not in graph.coordinates:
            continue
        if initial < dist.get(node, math.inf):
            dist[node] = initial
            heapq.heappush(heap, (initial, node))
    while heap:
        value, node = heapq.heappop(heap)
        if value != dist.get(node):
            continue
        if value > cutoff_m:
            continue
        for nxt, weight in graph.adjacency.get(node, []):
            candidate = value + weight
            if candidate > cutoff_m or candidate >= dist.get(nxt, math.inf):
                continue
            dist[nxt] = candidate
            heapq.heappush(heap, (candidate, nxt))
    return dist


def truncated_distances(graph: WalkingGraph, source: str, *, cutoff_m: float) -> dict[str, float]:
    return multisource_distances(graph, [(source, 0.0)], cutoff_m=cutoff_m)
