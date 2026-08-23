#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from network import CoordinateIndex, haversine_m, mesh100m_center, multisource_distances, truncated_distances, walking_graph_from_overpass

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed.json"

AED_FILE = "382019_aed.csv"
FAC_FILE = "382019_public_facility.csv"
POP_MESH_FILE = "100m_mesh_pop2020_38201.zip"
OSM_FILE = "osm_walk_matsuyama.json"

MAX_RADIUS_M = 640
DEFAULT_RADIUS_M = 320
DEMAND_MAX_SNAP_M = 300
AED_MAX_SNAP_M = 200
CANDIDATE_MAX_SNAP_M = 200
CANDIDATE_EXCLUSION_M = 50

SOURCE_META = {
    "aed": {
        "url": "https://www.city.matsuyama.ehime.jp/shisei/opendata/metadata/aeditiran.files/382019_aed.csv",
        "catalog": "https://www.pref.ehime.jp/opendata-catalog/dataset/3411.html",
        "data_date": "2025-03-01",
        "license": "CC BY",
    },
    "population_mesh": {
        "url": "https://gtfs-gis.jp/data/100m_pop2020/38/100m_mesh_pop2020_38201.zip",
        "catalog": "https://gtfs-gis.jp/teikyo/",
        "data_date": "2020 Census based",
        "license": "CC BY",
        "note": "2020 Census 250m population allocated to simplified 100m meshes using building-area and land-use information.",
    },
    "public_facility": {
        "url": "https://www.city.matsuyama.ehime.jp/shisei/opendata/metadata/shisetsu.files/382019_public_facility.csv",
        "catalog": "https://www.pref.ehime.jp/opendata-catalog/dataset/3638.html",
        "data_date": "2024-02-20",
        "license": "CC BY",
    },
    "walking_network": {
        "url": "https://www.openstreetmap.org/copyright",
        "catalog": "https://www.openstreetmap.org/copyright",
        "data_date": "build-time Overpass snapshot",
        "license": "ODbL 1.0",
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("unsupported population mesh encoding")


def read_population_mesh(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        csv_names = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
        if not csv_names:
            raise ValueError("population mesh archive has no CSV")
        return list(csv.DictReader(io.StringIO(decode_text(archive.read(csv_names[0])))))


def fnum(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_24h(row: dict[str, str]) -> bool:
    note = (row.get("利用可能日時特記事項") or "").strip()
    days = (row.get("利用可能曜日") or "").strip()
    start = (row.get("開始時間") or "").strip()
    end = (row.get("終了時間") or "").strip()
    explicit = "いつでも使用可" in note and "施設開錠時のみ" not in note
    all_days = all(day in days for day in "月火水木金土日")
    zero_clock = start in {"0:00", "00:00"} and end in {"0:00", "00:00"}
    return explicit or (all_days and zero_clock)


def parse_aeds(rows: list[dict[str, str]]) -> list[dict]:
    required = {"名称", "緯度", "経度", "所在地_連結表記"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"AED schema mismatch: {sorted(required - (set(rows[0]) if rows else set()))}")
    result = []
    for row in rows:
        lat, lon = fnum(row.get("緯度")), fnum(row.get("経度"))
        if lat is None or lon is None:
            continue
        result.append({
            "id": (row.get("ID") or f"AED{len(result)+1:04d}").strip(),
            "name": (row.get("名称") or "AED").strip(),
            "address": (row.get("所在地_連結表記") or "").strip(),
            "lat": lat,
            "lon": lon,
            "location": (row.get("設置位置") or "").strip(),
            "days": (row.get("利用可能曜日") or "").strip(),
            "start": (row.get("開始時間") or "").strip(),
            "end": (row.get("終了時間") or "").strip(),
            "notes": (row.get("利用可能日時特記事項") or "").strip(),
            "is24h": is_24h(row),
        })
    return result


def parse_population(rows: list[dict[str, str]]) -> list[dict]:
    required = {"Meshcode", "PopT", "Pop75over"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"population mesh schema mismatch: {sorted(required - (set(rows[0]) if rows else set()))}")
    demand = []
    for row in rows:
        population = float(row.get("PopT") or 0)
        if population <= 0:
            continue
        meshcode = str(row["Meshcode"]).strip()
        lat, lon = mesh100m_center(meshcode)
        demand.append({
            "id": meshcode,
            "meshcode": meshcode,
            "name": f"100mメッシュ {meshcode}",
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "population": round(population, 3),
            "senior65": round(float(row.get("Pop65over") or 0), 3),
            "senior75": round(float(row.get("Pop75over") or 0), 3),
            "senior85": round(float(row.get("Pop85over") or 0), 3),
        })
    return demand


def parse_candidates(rows: list[dict[str, str]]) -> list[dict]:
    required = {"名称", "緯度", "経度", "所在地_連結表記"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"public facility schema mismatch: {sorted(required - (set(rows[0]) if rows else set()))}")
    result = []
    seen: set[tuple[float, float]] = set()
    for row in rows:
        lat, lon = fnum(row.get("緯度")), fnum(row.get("経度"))
        if lat is None or lon is None:
            continue
        key = (round(lat, 6), round(lon, 6))
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "name": (row.get("名称") or "公共施設").strip(),
            "address": (row.get("所在地_連結表記") or "").strip(),
            "lat": lat,
            "lon": lon,
            "candidateType": "松山市公共施設",
        })
    return result


def snap_items(items: list[dict], index: CoordinateIndex, *, max_snap_m: float) -> None:
    for item in items:
        node, snap_m = index.nearest(float(item["lat"]), float(item["lon"]), max_search_m=max_snap_m)
        item["node"] = node
        item["snapM"] = round(snap_m, 1) if math.isfinite(snap_m) else None
        item["networkSnapped"] = node is not None


def rounded_or_none(value: float) -> float | None:
    return round(value, 1) if math.isfinite(value) else None


def _nearest_total(demand: dict, network_dist: dict[str, float]) -> float:
    node = demand.get("node")
    if not node:
        return math.inf
    base = network_dist.get(str(node), math.inf)
    if not math.isfinite(base):
        return math.inf
    return base + float(demand.get("snapM") or 0.0)


def build_payload(raw_dir: Path = RAW) -> dict:
    aeds = parse_aeds(read_csv(raw_dir / AED_FILE))
    candidates_raw = parse_candidates(read_csv(raw_dir / FAC_FILE))
    demand = parse_population(read_population_mesh(raw_dir / POP_MESH_FILE))
    osm = json.loads((raw_dir / OSM_FILE).read_text(encoding="utf-8"))
    graph = walking_graph_from_overpass(osm)
    if len(graph.coordinates) < 1000 or graph.edge_count < 1000:
        raise ValueError("OSM walking graph is unexpectedly small")
    index = CoordinateIndex(graph.coordinates)

    snap_items(aeds, index, max_snap_m=AED_MAX_SNAP_M)
    snap_items(demand, index, max_snap_m=DEMAND_MAX_SNAP_M)
    snap_items(candidates_raw, index, max_snap_m=CANDIDATE_MAX_SNAP_M)

    snapped_all = [a for a in aeds if a["networkSnapped"]]
    snapped_24h = [a for a in snapped_all if a["is24h"]]
    if not snapped_all or not snapped_24h:
        raise ValueError("AED snapping produced an empty all/24h set")

    cutoff = MAX_RADIUS_M + DEMAND_MAX_SNAP_M + AED_MAX_SNAP_M
    dist_all = multisource_distances(
        graph,
        [(str(a["node"]), float(a["snapM"] or 0.0)) for a in snapped_all],
        cutoff_m=cutoff,
    )
    dist_24h = multisource_distances(
        graph,
        [(str(a["node"]), float(a["snapM"] or 0.0)) for a in snapped_24h],
        cutoff_m=cutoff,
    )

    demand_by_node: dict[str, list[int]] = defaultdict(list)
    for i, item in enumerate(demand):
        node = item.get("node")
        if node:
            demand_by_node[str(node)].append(i)
        item["nearestAllM"] = rounded_or_none(_nearest_total(item, dist_all))
        item["nearest24hM"] = rounded_or_none(_nearest_total(item, dist_24h))
        item.pop("node", None)

    candidates = []
    seen_nodes: set[str] = set()
    for raw in candidates_raw:
        node = raw.get("node")
        if not node or str(node) in seen_nodes:
            continue
        straight_min = min(haversine_m(raw["lat"], raw["lon"], a["lat"], a["lon"]) for a in aeds)
        existing_network = dist_all.get(str(node), math.inf) + float(raw.get("snapM") or 0.0)
        if straight_min < CANDIDATE_EXCLUSION_M or existing_network < CANDIDATE_EXCLUSION_M:
            continue
        seen_nodes.add(str(node))
        local = truncated_distances(
            graph,
            str(node),
            cutoff_m=MAX_RADIUS_M + DEMAND_MAX_SNAP_M,
        )
        reach: list[list[float | int]] = []
        for demand_node, network_m in local.items():
            indexes = demand_by_node.get(demand_node, [])
            for demand_index in indexes:
                d = demand[demand_index]
                total = float(raw.get("snapM") or 0.0) + network_m + float(d.get("snapM") or 0.0)
                if total <= MAX_RADIUS_M:
                    reach.append([demand_index, round(total, 1)])
        if not reach:
            continue
        reach.sort(key=lambda pair: (pair[1], pair[0]))
        candidates.append({
            "id": f"C{len(candidates)+1:04d}",
            "name": raw["name"],
            "address": raw["address"],
            "lat": raw["lat"],
            "lon": raw["lon"],
            "candidateType": raw["candidateType"],
            "snapM": raw["snapM"],
            "nearestAedNetworkM": rounded_or_none(existing_network),
            "reach": reach,
        })

    for a in aeds:
        a.pop("node", None)
    for d in demand:
        d["snapM"] = d.get("snapM") if d.get("networkSnapped") else None

    total_pop = sum(float(d["population"]) for d in demand)
    total_75 = sum(float(d["senior75"]) for d in demand)
    unsnapped_pop = sum(float(d["population"]) for d in demand if not d["networkSnapped"])

    return {
        "meta": {
            "title": "AED 4分圏カバレッジ＆次の1台最適配置",
            "area": "愛媛県松山市",
            "defaultRadiusM": DEFAULT_RADIUS_M,
            "maxRadiusM": MAX_RADIUS_M,
            "walkSpeedKmh": 4.8,
            "defaultWalkMinutes": 4,
            "candidateExclusionRadiusM": CANDIDATE_EXCLUSION_M,
            "distanceModel": "osm-walking-shortest-path",
            "populationModel": "2020 Census 250m population distributed to simplified 100m mesh; no 2026 spatial rescaling",
            "model": "100m人口メッシュ中心とAED/候補をOSM歩行ネットワークへsnapし、snap距離を含む最短経路距離で評価。",
            "sources": SOURCE_META,
        },
        "summary": {
            "aedCount": len(aeds),
            "aedNetworkSnappedCount": len(snapped_all),
            "aed24hCount": sum(1 for a in aeds if a["is24h"]),
            "aed24hNetworkSnappedCount": len(snapped_24h),
            "population": round(total_pop, 3),
            "senior75": round(total_75, 3),
            "demandPointCount": len(demand),
            "demandNetworkSnappedCount": sum(1 for d in demand if d["networkSnapped"]),
            "unsnappedPopulation": round(unsnapped_pop, 3),
            "candidateCount": len(candidates),
            "networkNodeCount": len(graph.coordinates),
            "networkDirectedEdgeCount": graph.edge_count,
            "overpassTileCount": int(osm.get("_meta", {}).get("tileCount", 0)),
        },
        "aeds": aeds,
        "demand": demand,
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    payload = build_payload(args.raw_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
