"""Sponsor list for the banner: committed baseline + optional cached-daily remote merge. Never raises."""
import json
import os
import random
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from .constants import REPO_NAME, SPONSORS_URL, USER_CONFIG_DIR, VERSION

_YAML = Path(__file__).resolve().parent / "sponsors.yaml"
_CACHE = USER_CONFIG_DIR / "sponsors_cache.json"
_TTL = 86400   # refresh remote at most once/day; otherwise serve the cache
_TIERS = {"gold", "silver", "bronze"}
_WEIGHTS = {"gold": 3, "silver": 2, "bronze": 1}
_CTA = "https://github.com/sponsors/Z4nzu"

_featured_memo: list["Sponsor"] | None = None   # pick once per process; banner re-renders a lot


@dataclass
class Sponsor:
    name: str
    url: str
    tagline: str = ""
    tier: str = "bronze"


def _coerce(entry: dict) -> Sponsor | None:
    """One raw yaml/json entry -> Sponsor, or None if untrusted/incomplete. Never raises."""
    try:
        name, url = entry.get("name"), entry.get("url")
        if not name or not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return None
        tier = entry.get("tier", "bronze")
        return Sponsor(str(name), url,
                       str(entry.get("tagline") or ""),
                       tier if tier in _TIERS else "bronze")
    except Exception:
        return None


def _committed() -> list[Sponsor]:
    try:
        raw = (yaml.safe_load(_YAML.read_text()) or {}).get("sponsors") or []
        return [s for s in (_coerce(e) for e in raw) if s]
    except Exception:
        return []


def _sponsors_url() -> str:
    return SPONSORS_URL or ""      # fixed in code (constants.SPONSORS_URL), not user-editable


def _fetch(url: str, timeout: float) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": f"{REPO_NAME}/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (operator-configured URL)
        return json.load(r).get("sponsors") or []


def _cached_remote(url: str, timeout: float) -> list:
    """Fresh cache -> serve it; else fetch and rewrite; offline/error -> stale cache for this url, else []."""
    cached: list = []
    try:
        data = json.loads(_CACHE.read_text())
        if data.get("url") == url:
            cached = data.get("sponsors") or []
            if time.time() - data.get("ts", 0) < _TTL:
                return cached
    except Exception:
        cached = []
    try:
        sponsors = _fetch(url, timeout)
    except Exception:
        return cached
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({"ts": time.time(), "url": url, "sponsors": sponsors}))
    except Exception:
        pass
    return sponsors


def _remote() -> list[Sponsor]:
    """Remote entries, or [] when opted out / no sponsors_url (the default -> ZERO network). Never raises."""
    if os.environ.get("HACKINGTOOL_NO_SPONSOR_FETCH"):
        return []
    url = _sponsors_url()
    if not url:
        return []
    try:
        raw = _cached_remote(url, 2.0)
    except Exception:
        return []
    return [s for s in (_coerce(e) for e in raw) if s]


def load() -> list[Sponsor]:
    """Committed sponsors, then any remote ones (deduped by url). Never raises -> committed-only, else []."""
    committed = _committed()
    try:
        seen = {s.url for s in committed}
        return committed + [s for s in _remote() if s.url not in seen]
    except Exception:
        return committed


def featured(n: int = 1, seed: int | None = None) -> list[Sponsor]:
    """Up to n sponsors, tier-weighted, sampled without replacement. Memoized per process (seed=None); seed is for tests."""
    global _featured_memo
    if seed is None and _featured_memo is not None:
        return _featured_memo
    pool = list(load())   # copy: sampling pops from it
    rng = random.Random(seed)
    weights = [_WEIGHTS.get(s.tier, 1) for s in pool]
    picked: list[Sponsor] = []
    for _ in range(min(n, len(pool))):
        i = rng.choices(range(len(pool)), weights=weights, k=1)[0]
        picked.append(pool.pop(i))
        weights.pop(i)
    if seed is None:
        _featured_memo = picked
    return picked


def sponsor_cta() -> str:
    """The 'become a sponsor' URL."""
    return _CTA
