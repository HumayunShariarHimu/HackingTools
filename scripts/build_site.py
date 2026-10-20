#!/usr/bin/env python3
"""Copy the static app to dist/ for static hosting and managed publication."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist"


def main() -> None:
    required = [ROOT / "index.html", ROOT / "assets/styles.css", ROOT / "assets/app.js", ROOT / "data/catalog.json"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Required static files are missing: " + ", ".join(missing))
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    shutil.copy2(ROOT / "index.html", OUTPUT / "index.html")
    shutil.copy2(ROOT / "manus-routes.json", OUTPUT / "manus-routes.json")
    for directory in ("assets", "data"):
        shutil.copytree(ROOT / directory, OUTPUT / directory)
    print(f"Static site built at {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
