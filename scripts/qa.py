#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed.json"


def analyze(data: dict, radius: float, mode: str) -> dict:
    nearest_key = "nearest24hM" if mode == "24h" else "nearestAllM"
    demand = data["demand"]
    covered = [d.get(nearest_key) is not None and float(d[nearest_key]) <= radius for d in demand]
    total = sum(float(d["population"]) for d in demand)
    covered_pop = sum(float(d["population"]) for d, ok in zip(demand, covered, strict=True) if ok)
    total75 = sum(float(d["senior75"]) for d in demand)
    covered75 = sum(float(d["senior75"]) for d, ok in zip(demand, covered, strict=True) if ok)

    best = None
    for c in data["candidates"]:
        gain = 0.0
        gain75 = 0.0
        for demand_index, distance in c["reach"]:
            if float(distance) > radius or covered[int(demand_index)]:
                continue
            d = demand[int(demand_index)]
            gain += float(d["population"])
            gain75 += float(d["senior75"])
        if best is None or (gain, gain75) > (best["gain"], best["gain75"]):
            best = {**c, "gain": gain, "gain75": gain75}

    return {
        "mode": mode,
        "radiusM": radius,
        "coverageRate": covered_pop / total * 100 if total else 0.0,
        "coveredPopulation": covered_pop,
        "uncoveredPopulation": total - covered_pop,
        "uncoveredSenior75": total75 - covered75,
        "best": None if best is None else {k: v for k, v in best.items() if k != "reach"},
    }


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    radius = float(data["meta"]["defaultRadiusM"])
    results = [analyze(data, radius, "all"), analyze(data, radius, "24h")]

    summary = data["summary"]
    assert data["meta"]["distanceModel"] == "osm-walking-shortest-path"
    assert "100m" in data["meta"]["populationModel"]
    assert summary["aedCount"] > 0
    assert summary["aedNetworkSnappedCount"] > 0
    assert summary["aed24hNetworkSnappedCount"] > 0
    assert summary["demandPointCount"] > 1000
    assert summary["demandNetworkSnappedCount"] > 1000
    assert summary["candidateCount"] > 0
    assert summary["networkNodeCount"] > 1000
    assert summary["networkDirectedEdgeCount"] > 1000
    assert summary["unsnappedPopulation"] / summary["population"] < 0.10
    assert all(0 <= r["coverageRate"] <= 100 for r in results)
    assert all(r["best"] and r["best"]["gain"] >= 0 for r in results)
    assert results[0]["coverageRate"] >= results[1]["coverageRate"]

    print(json.dumps({"summary": summary, "defaultAnalysis": results}, ensure_ascii=False, indent=2))
    print("QA: PASS")


if __name__ == "__main__":
    main()
