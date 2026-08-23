#!/usr/bin/env python3
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed.json"


def haversine_m(a, b):
    r = 6_371_000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def analyze(data, radius=300, mode="all"):
    aeds = [a for a in data["aeds"] if mode == "all" or a["is24h"]]
    demand = data["demand"]
    statuses = []
    for d in demand:
        nearest = min(haversine_m(d, a) for a in aeds)
        statuses.append((d, nearest <= radius))

    total = sum(d["population"] for d, _ in statuses)
    covered = sum(d["population"] for d, ok in statuses if ok)
    total75 = sum(d["senior75"] for d, _ in statuses)
    covered75 = sum(d["senior75"] for d, ok in statuses if ok)

    best = None
    for c in data["candidates"]:
        gain = sum(d["population"] for d, ok in statuses if not ok and haversine_m(d, c) <= radius)
        gain75 = sum(d["senior75"] for d, ok in statuses if not ok and haversine_m(d, c) <= radius)
        if best is None or (gain, gain75) > (best["gain"], best["gain75"]):
            best = {**c, "gain": gain, "gain75": gain75}

    return {
        "mode": mode,
        "radiusM": radius,
        "coverageRate": covered / total * 100,
        "coveredPopulation": covered,
        "uncoveredPopulation": total - covered,
        "uncoveredSenior75": total75 - covered75,
        "best": best,
    }


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    results = [analyze(data, 300, "all"), analyze(data, 300, "24h")]

    assert data["summary"]["regionCount"] == 44
    assert data["summary"]["aedCount"] > 0
    assert data["summary"]["candidateCount"] > 0
    assert all(0 <= r["coverageRate"] <= 100 for r in results)
    assert all(r["best"] and r["best"]["gain"] >= 0 for r in results)
    assert results[0]["coverageRate"] >= results[1]["coverageRate"]

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("QA: PASS")


if __name__ == "__main__":
    main()
