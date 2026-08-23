#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_data import (
    AED_FILE,
    FAC_FILE,
    OSM_FILE,
    POP_MESH_FILE,
    RAW,
    SOURCE_META,
    parse_aeds,
    parse_population,
    read_csv,
    read_population_mesh,
)

FILES = {
    "aed": AED_FILE,
    "population_mesh": POP_MESH_FILE,
    "public_facility": FAC_FILE,
}
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
TILE_DEGREES = 0.10
TILE_BUFFER_DEGREES = 0.015


def request_bytes(url: str, *, data: bytes | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "ehime-aed-rescue-map/0.2 (+https://github.com/ryotamatsuki/ehime-aed-rescue-map)",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def download(url: str, path: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            content = request_bytes(url, timeout=90)
            if len(content) < 100:
                raise RuntimeError(f"downloaded file is unexpectedly small: {url}")
            path.write_bytes(content)
            print(f"updated {path.name}: {len(content):,} bytes")
            return
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to download {url}: {last_error}")


def tile_bboxes(points: list[tuple[float, float]]) -> list[tuple[float, float, float, float]]:
    cells = {(math.floor(lat / TILE_DEGREES), math.floor(lon / TILE_DEGREES)) for lat, lon in points}
    result = []
    for i, j in sorted(cells):
        south = i * TILE_DEGREES - TILE_BUFFER_DEGREES
        west = j * TILE_DEGREES - TILE_BUFFER_DEGREES
        north = (i + 1) * TILE_DEGREES + TILE_BUFFER_DEGREES
        east = (j + 1) * TILE_DEGREES + TILE_BUFFER_DEGREES
        result.append((south, west, north, east))
    return result


def overpass_tile(bbox: tuple[float, float, float, float]) -> dict:
    south, west, north, east = bbox
    box = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    query = f'[out:json][timeout:90];way["highway"]({box});out tags geom;'
    encoded = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(3):
            try:
                payload = request_bytes(endpoint, data=encoded, timeout=150)
                result = json.loads(payload.decode("utf-8"))
                if not isinstance(result.get("elements"), list):
                    raise RuntimeError("Overpass response has no elements")
                return result
            except Exception as exc:
                errors.append(f"{endpoint} attempt {attempt + 1}: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
    raise RuntimeError("Overpass tile failed: " + " | ".join(errors[-6:]))


def build_osm_snapshot(raw_dir: Path) -> None:
    population = parse_population(read_population_mesh(raw_dir / POP_MESH_FILE))
    aeds = parse_aeds(read_csv(raw_dir / AED_FILE))
    points = [(float(d["lat"]), float(d["lon"])) for d in population]
    points.extend((float(a["lat"]), float(a["lon"])) for a in aeds)
    bboxes = tile_bboxes(points)
    print(f"Overpass walking-network tiles: {len(bboxes)}")

    merged: dict[tuple[str, int], dict] = {}
    for index, bbox in enumerate(bboxes, 1):
        tile = overpass_tile(bbox)
        print(f"  tile {index}/{len(bboxes)}: {len(tile.get('elements', [])):,} highway ways")
        for element in tile.get("elements", []):
            key = (str(element.get("type")), int(element.get("id") or 0))
            previous = merged.get(key)
            if previous is None or len(element.get("geometry") or []) > len(previous.get("geometry") or []):
                merged[key] = element
        if index < len(bboxes):
            time.sleep(0.25)

    snapshot = {
        "version": 0.6,
        "generator": "ehime-aed-rescue-map tiled Overpass fetch",
        "elements": list(merged.values()),
        "_meta": {
            "tileCount": len(bboxes),
            "tileDegrees": TILE_DEGREES,
            "tileBufferDegrees": TILE_BUFFER_DEGREES,
            "source": "OpenStreetMap via Overpass API",
        },
    }
    path = raw_dir / OSM_FILE
    path.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"updated {path.name}: {path.stat().st_size:,} bytes / {len(merged):,} unique ways")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for key, filename in FILES.items():
        download(SOURCE_META[key]["url"], RAW / filename)
    build_osm_snapshot(RAW)
    from build_data import main as build_main
    old_argv = sys.argv[:]
    try:
        sys.argv = ["build_data.py"]
        build_main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
