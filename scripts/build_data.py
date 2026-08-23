#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed.json"

AED_FILE = "382019_aed.csv"
POP_FILE = "382019_population_20260401.csv"
FAC_FILE = "382019_public_facility.csv"

SOURCE_META = {
    "aed": {
        "url": "https://www.city.matsuyama.ehime.jp/shisei/opendata/metadata/aeditiran.files/382019_aed.csv",
        "catalog": "https://www.pref.ehime.jp/opendata-catalog/dataset/3411.html",
        "data_date": "2025-03-01",
        "license": "CC BY",
    },
    "population": {
        "url": "https://www.city.matsuyama.ehime.jp/shisei/opendata/metadata/population_0401.files/382019_population_20260401.csv",
        "catalog": "https://www.pref.ehime.jp/opendata-catalog/dataset/3636.html",
        "data_date": "2026-04-01",
        "license": "CC BY",
    },
    "public_facility": {
        "url": "https://www.city.matsuyama.ehime.jp/shisei/opendata/metadata/shisetsu.files/382019_public_facility.csv",
        "catalog": "https://www.pref.ehime.jp/opendata-catalog/dataset/3638.html",
        "data_date": "2024-02-20",
        "license": "CC BY",
    },
}

MATS_BOUNDS = {"min_lat": 33.55, "max_lat": 34.20, "min_lon": 132.45, "max_lon": 132.98}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: str | None) -> float | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def in_bounds(lat: float | None, lon: float | None) -> bool:
    return (
        lat is not None
        and lon is not None
        and MATS_BOUNDS["min_lat"] <= lat <= MATS_BOUNDS["max_lat"]
        and MATS_BOUNDS["min_lon"] <= lon <= MATS_BOUNDS["max_lon"]
    )


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def senior75(row: dict[str, str]) -> int:
    cols = [
        "75-79歳の男性", "75-79歳の女性",
        "80-84歳の男性", "80-84歳の女性",
        "85歳以上の男性", "85歳以上の女性",
    ]
    return sum(int(float(row.get(c) or 0)) for c in cols)


def is_24h(row: dict[str, str]) -> bool:
    note = (row.get("利用可能日時特記事項") or "").strip()
    days = (row.get("利用可能曜日") or "").strip()
    start = (row.get("開始時間") or "").strip()
    end = (row.get("終了時間") or "").strip()
    explicit = "いつでも使用可" in note and "施設開錠時のみ" not in note
    all_days = all(day in days for day in "月火水木金土日")
    zero_clock = start in {"0:00", "00:00"} and end in {"0:00", "00:00"}
    return explicit or (all_days and zero_clock)


def mean_point(rows: list[dict[str, str]]) -> tuple[float, float]:
    points = []
    for row in rows:
        lat, lon = fnum(row.get("緯度")), fnum(row.get("経度"))
        if in_bounds(lat, lon):
            points.append((lat, lon))
    if not points:
        raise ValueError("No valid points available for derived region representative")
    return mean(p[0] for p in points), mean(p[1] for p in points)


def build_region_representatives(pop_rows, aed_rows, fac_rows) -> dict[str, tuple[float, float]]:
    reps: dict[str, tuple[float, float]] = {}
    island_regions = {"睦野", "東中島", "西中島", "神和"}

    for row in pop_rows:
        region = row["地域名"].strip()
        if region in island_regions:
            continue
        target = f"{region}公民館"
        exact = [r for r in aed_rows if (r.get("名称") or "").strip() == target]
        if not exact:
            exact = [r for r in aed_rows if (r.get("名称") or "").strip().startswith(target)]
        valid = [r for r in exact if in_bounds(fnum(r.get("緯度")), fnum(r.get("経度")))]
        if not valid:
            raise ValueError(f"Missing representative AED/public hall for region: {region}")
        reps[region] = (fnum(valid[0]["緯度"]), fnum(valid[0]["経度"]))  # type: ignore[arg-type]

    def address_matches(keys: tuple[str, ...]) -> list[dict[str, str]]:
        out = []
        for r in fac_rows:
            text = (r.get("所在地_連結表記") or "") + " " + (r.get("名称") or "")
            if any(k in text for k in keys):
                out.append(r)
        return out

    reps["睦野"] = mean_point(address_matches(("睦月", "野忽那")))
    reps["東中島"] = mean_point(address_matches(("中島大浦", "小浜", "長師", "宮野", "神浦")))
    reps["西中島"] = mean_point(address_matches(("宇和間", "熊田", "吉木", "饒", "畑里")))
    reps["神和"] = mean_point(address_matches(("上怒和", "元怒和", "津和地", "二神")))
    return reps


def nearest_region(lat: float, lon: float, reps: dict[str, tuple[float, float]]) -> str:
    return min(reps, key=lambda r: haversine_m(lat, lon, reps[r][0], reps[r][1]))


def build_payload(raw_dir: Path = RAW) -> dict:
    aed_rows = read_csv(raw_dir / AED_FILE)
    pop_rows = read_csv(raw_dir / POP_FILE)
    fac_rows = read_csv(raw_dir / FAC_FILE)

    required_aed = {"名称", "緯度", "経度", "所在地_連結表記"}
    required_pop = {"地域名", "総人口", "75-79歳の男性", "85歳以上の女性"}
    required_fac = {"名称", "緯度", "経度", "所在地_連結表記"}
    for rows, required, label in [
        (aed_rows, required_aed, "AED"),
        (pop_rows, required_pop, "population"),
        (fac_rows, required_fac, "public facility"),
    ]:
        if not rows or not required.issubset(rows[0].keys()):
            missing = required - (set(rows[0].keys()) if rows else set())
            raise ValueError(f"{label} schema mismatch. Missing: {sorted(missing)}")

    reps = build_region_representatives(pop_rows, aed_rows, fac_rows)
    pop_by_region = {
        r["地域名"].strip(): {
            "population": int(float(r["総人口"])),
            "senior75": senior75(r),
        }
        for r in pop_rows
    }

    anchors_by_region: dict[str, list[dict]] = defaultdict(list)
    for r in fac_rows:
        lat, lon = fnum(r.get("緯度")), fnum(r.get("経度"))
        if not in_bounds(lat, lon):
            continue
        region = nearest_region(lat, lon, reps)  # type: ignore[arg-type]
        anchors_by_region[region].append({
            "name": (r.get("名称") or "公共施設").strip(),
            "address": (r.get("所在地_連結表記") or "").strip(),
            "lat": lat,
            "lon": lon,
        })

    demand_raw = []
    for region, totals in pop_by_region.items():
        anchors = anchors_by_region.get(region, [])
        if not anchors:
            lat, lon = reps[region]
            anchors = [{"name": f"{region}地域代表点", "address": "", "lat": lat, "lon": lon}]
        per_pop = totals["population"] / len(anchors)
        per_75 = totals["senior75"] / len(anchors)
        for a in anchors:
            demand_raw.append({
                **a,
                "region": region,
                "population": per_pop,
                "senior75": per_75,
            })

    agg: dict[tuple[str, float, float], dict] = {}
    for d in demand_raw:
        key = (d["region"], round(d["lat"], 5), round(d["lon"], 5))
        if key not in agg:
            agg[key] = {**d, "lat": key[1], "lon": key[2], "names": [d["name"]]}
        else:
            agg[key]["population"] += d["population"]
            agg[key]["senior75"] += d["senior75"]
            if len(agg[key]["names"]) < 3 and d["name"] not in agg[key]["names"]:
                agg[key]["names"].append(d["name"])
    demand = []
    for i, d in enumerate(agg.values()):
        d["id"] = f"D{i+1:04d}"
        d["population"] = round(d["population"], 3)
        d["senior75"] = round(d["senior75"], 3)
        d["name"] = " / ".join(d.pop("names"))
        demand.append(d)

    aeds = []
    for r in aed_rows:
        lat, lon = fnum(r.get("緯度")), fnum(r.get("経度"))
        if not in_bounds(lat, lon):
            continue
        aeds.append({
            "id": (r.get("ID") or f"AED{len(aeds)+1:04d}").strip(),
            "name": (r.get("名称") or "AED").strip(),
            "address": (r.get("所在地_連結表記") or "").strip(),
            "lat": lat,
            "lon": lon,
            "location": (r.get("設置位置") or "").strip(),
            "days": (r.get("利用可能曜日") or "").strip(),
            "start": (r.get("開始時間") or "").strip(),
            "end": (r.get("終了時間") or "").strip(),
            "notes": (r.get("利用可能日時特記事項") or "").strip(),
            "is24h": is_24h(r),
        })

    candidates = []
    seen = set()
    for r in fac_rows:
        lat, lon = fnum(r.get("緯度")), fnum(r.get("経度"))
        if not in_bounds(lat, lon):
            continue
        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        nearest_aed = min(haversine_m(lat, lon, a["lat"], a["lon"]) for a in aeds) if aeds else float("inf")
        if nearest_aed < 50:
            continue
        candidates.append({
            "id": f"C{len(candidates)+1:04d}",
            "name": (r.get("名称") or "公共施設").strip(),
            "address": (r.get("所在地_連結表記") or "").strip(),
            "lat": lat,
            "lon": lon,
            "region": nearest_region(lat, lon, reps),
            "nearestAedM": round(nearest_aed, 1),
        })

    regions = []
    for r, point in reps.items():
        regions.append({
            "region": r,
            "lat": point[0],
            "lon": point[1],
            **pop_by_region[r],
            "anchorCount": len(anchors_by_region.get(r, [])),
        })

    return {
        "meta": {
            "title": "AED 4分圏カバレッジ＆次の1台最適配置 PoC",
            "area": "愛媛県松山市",
            "defaultRadiusM": 300,
            "candidateExclusionRadiusM": 50,
            "model": "地域人口を公共施設位置へ均等配分したPoC需要点プロキシ。距離は直線距離。",
            "sources": SOURCE_META,
        },
        "summary": {
            "aedCount": len(aeds),
            "aed24hCount": sum(1 for a in aeds if a["is24h"]),
            "population": sum(v["population"] for v in pop_by_region.values()),
            "senior75": sum(v["senior75"] for v in pop_by_region.values()),
            "demandPointCount": len(demand),
            "candidateCount": len(candidates),
            "regionCount": len(regions),
        },
        "aeds": aeds,
        "demand": demand,
        "candidates": candidates,
        "regions": regions,
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
