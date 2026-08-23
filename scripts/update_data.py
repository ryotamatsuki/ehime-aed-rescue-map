#!/usr/bin/env python3
from pathlib import Path
from urllib.request import Request, urlopen
import subprocess
import sys

from build_data import RAW, SOURCE_META, AED_FILE, POP_FILE, FAC_FILE

FILES = {
    "aed": AED_FILE,
    "population": POP_FILE,
    "public_facility": FAC_FILE,
}


def download(url: str, path: Path) -> None:
    req = Request(url, headers={"User-Agent": "ehime-aed-rescue-map/0.1 (+open-data-poc)"})
    with urlopen(req, timeout=30) as response:
        content = response.read()
    if len(content) < 100:
        raise RuntimeError(f"downloaded file is unexpectedly small: {url}")
    path.write_bytes(content)
    print(f"updated {path.name}: {len(content):,} bytes")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for key, filename in FILES.items():
        download(SOURCE_META[key]["url"], RAW / filename)
    subprocess.run([sys.executable, str(Path(__file__).with_name("build_data.py"))], check=True)


if __name__ == "__main__":
    main()
