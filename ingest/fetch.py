"""Download + extract the full Loghub BGL and OpenStack datasets into data/raw/ (skips what's already there)."""
from __future__ import annotations

import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
SOURCES = {
    "BGL.zip": "https://zenodo.org/records/8196385/files/BGL.zip?download=1",
    "OpenStack.tar.gz": "https://zenodo.org/records/8196385/files/OpenStack.tar.gz?download=1",
}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        archive = RAW / name
        if not archive.exists():
            print(f"downloading {name} ...")
            with urllib.request.urlopen(url, timeout=60) as r, open(archive.with_suffix(".part"), "wb") as f:
                shutil.copyfileobj(r, f)
            archive.with_suffix(".part").rename(archive)
        out = RAW / name.split(".")[0]
        if not out.exists():
            print(f"extracting {name} ...")
            if name.endswith(".zip"):
                with zipfile.ZipFile(archive) as z:
                    z.extractall(out)
            else:
                with tarfile.open(archive) as t:
                    t.extractall(out, filter="data")
    for p in sorted(RAW.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size / 1e6:9.1f} MB  {p.relative_to(RAW)}")


if __name__ == "__main__":
    main()
