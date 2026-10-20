"""Regenerate src/hackingtool/catalog_owners.py from tools we already ship.

The owners of tools we curated are a free, self-maintaining trusted-author
signal for /find: nothing in GitHub metadata separates a professional tool
from a malware toy, so we lean on who wrote the tools we already vetted.

Run: uv run python scripts/gen_catalog_owners.py
A test asserts the committed file matches a fresh run, so it cannot rot.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "hackingtool"
OUT = SRC / "catalog_owners.py"
# (?<!api\.) drops api.github.com/... URLs entirely (e.g. .../repos/mozilla/...,
# .../search/repositories) rather than misreading their path segments as owners.
_URL = re.compile(r"(?<!api\.)github\.com/([A-Za-z0-9._-]+)/[A-Za-z0-9._-]+")
# Path segments that land right after github.com/ in non-owner URLs (placeholder
# docs, API paths that slipped past the api. filter) — never real owners.
_NOT_OWNERS = {"search", "repos", "orgs", "org", "sponsors"}

HEADER = '''"""GitHub owners of tools we already ship — GENERATED, do not edit.

Regenerate with: uv run python scripts/gen_catalog_owners.py
"""

CATALOG_OWNERS: frozenset[str] = frozenset({
'''


def collect() -> list[str]:
    owners = set()
    for p in sorted(SRC.rglob("*")):
        if p.suffix in (".yaml", ".py") and p.is_file() and p.name != OUT.name:
            found = _URL.findall(p.read_text(errors="ignore"))
            owners.update(o for o in found if o.lower() not in _NOT_OWNERS)
    return sorted(owners, key=str.lower)


def render(owners: list[str]) -> str:
    body = "".join(f'    "{o}",\n' for o in owners)
    return HEADER + body + "})\n"


if __name__ == "__main__":
    owners = collect()
    OUT.write_text(render(owners))
    print(f"wrote {OUT} — {len(owners)} owners")
