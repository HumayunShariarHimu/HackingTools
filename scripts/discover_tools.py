#!/usr/bin/env python3
"""Discovery leg — mine curated lists / GitHub for NEW candidate tools.

The M1 `audit_tools.py` looks *inward* (are the tools we already ship still
maintained?). This looks *outward*: given a curated "awesome list" repo (default
`A-poc/RedTeam-Tools`), pull every GitHub project it links, drop the ones we
already ship, then for each remaining candidate fetch its GitHub metadata — what
it does, stars, last push, license, language, topics — so a human can quickly
understand *what the tool provides* and decide whether to add it.

Output (both written to `scripts/`, both gitignored drafts):
  - `discovered_tools.md`   — readable report, ranked by stars, one row per candidate
  - `discovered_candidates.yaml` — draft catalog stubs (project_url + SUGGESTED
    taxonomy tags + an install *hint*) ready to hand-curate into `catalog/`.

Guardrails (same posture as the rest of the project):
  - It NEVER writes to `catalog/` and NEVER fabricates `usage` commands or
    `lab_safe_notes` — those are left blank in the stub for a human to fill from
    the tool's real docs. Tags are only *suggested* (mapped from repo topics onto
    the closed `tags.TAXONOMY`); a human confirms them.
  - Read-only against GitHub; results cached so reruns are cheap.

Auth: a GitHub token lifts the 60 req/hr anon cap. Provide via env
  GITHUB_TOKEN / GH_TOKEN, or the gitignored file `scripts/.github_token`
  (a plain no-scope token is enough — everything queried is public).

Usage:
  python3 scripts/discover_tools.py                              # mine RedTeam-Tools
  python3 scripts/discover_tools.py --source A-poc/RedTeam-Tools --source 0x90n/InfoSec-Black-Friday
  python3 scripts/discover_tools.py --search "kerberoast" --search "adcs"   # GitHub repo search
  python3 scripts/discover_tools.py --min-stars 200 --max 50
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Reuse the auditor's battle-tested helpers rather than re-implementing them.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_tools import ROOT, gh_repo, load_token, parse_tools  # noqa: E402

sys.path.insert(0, str(ROOT))
from hackingtool.tags import TAXONOMY  # noqa: E402

CATALOG_DIR = ROOT / "catalog"
CACHE_FILE = ROOT / "scripts" / ".discover_cache.json"
REPORT_MD = ROOT / "scripts" / "discovered_tools.md"
STUBS_YAML = ROOT / "scripts" / "discovered_candidates.yaml"

GH_LINK_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
# Owners that are platforms/orgs, not tools — links to these are noise in a list.
SKIP_OWNERS = {"sponsors", "topics", "search", "about", "features", "marketplace",
               "collections", "orgs", "settings", "notifications"}

# repo topic / keyword -> canonical taxonomy tag (only mappings we're confident of).
TOPIC_MAP = {
    "osint": "osint", "recon": "recon", "reconnaissance": "recon",
    "scanner": "scanner", "vulnerability-scanner": "vuln-scan", "vulnerability": "vuln-scan",
    "port-scanner": "port-scan", "subdomain": "subdomain-enum", "subdomain-enumeration": "subdomain-enum",
    "enumeration": "enumeration", "fingerprinting": "fingerprint", "crawler": "crawler",
    "exploit": "exploitation", "exploitation": "exploitation",
    "post-exploitation": "post-exploitation", "privilege-escalation": "privesc", "privesc": "privesc",
    "lateral-movement": "lateral-movement", "persistence": "persistence",
    "active-directory": "active-directory", "kerberos": "active-directory", "ldap": "active-directory",
    "web": "web", "web-security": "web", "api": "api", "dns": "dns", "email": "email",
    "network": "network", "wireless": "wireless", "wifi": "wireless", "iot": "iot",
    "cloud": "cloud", "aws": "cloud", "azure": "cloud", "gcp": "cloud", "kubernetes": "cloud",
    "mobile": "mobile", "android": "mobile", "ios": "mobile", "apk": "apk",
    "bruteforce": "bruteforce", "brute-force": "bruteforce", "password": "password-attack",
    "password-cracking": "hash-crack", "hashcat": "hash-crack", "credentials": "credentials",
    "phishing": "phishing", "social-engineering": "social-engineering",
    "payload": "payload", "shellcode": "payload", "c2": "c2", "command-and-control": "c2",
    "reverse-shell": "reverse-shell", "mitm": "mitm", "sniffer": "sniffing", "sniffing": "sniffing",
    "ddos": "ddos", "fuzzing": "fuzzing", "fuzzer": "fuzzing",
    "sql-injection": "sql-injection", "sqli": "sql-injection", "xss": "xss",
    "steganography": "steganography", "reverse-engineering": "reversing", "disassembler": "reversing",
    "forensics": "forensics", "dfir": "forensics", "malware": "malware-analysis",
    "malware-analysis": "malware-analysis", "wordlist": "wordlist", "anonymity": "anonymity",
    "tor": "anonymity", "tunneling": "tunneling", "exfiltration": "exfiltration",
}
# Language -> a rough install hint (NOT a real install spec — a human verifies).
INSTALL_HINT = {
    "Go": "go install <module>@latest", "Python": "pipx install <pkg>  # or git+pip",
    "Rust": "cargo install <crate>", "Ruby": "gem install <gem>  # or git",
    "C": "apt/build from source", "C++": "apt/build from source",
    "Shell": "git clone", "PowerShell": "git clone (Windows)", "Java": "download release jar",
}


def _get(url: str, token: str | None) -> tuple[int, object]:
    """GET a GitHub API URL. Returns (status, parsed-json-or-None). Never raises."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "hackingtool-discover"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, None


def known_repos() -> set[str]:
    """Every owner/repo we already ship — from tools/*.py and catalog/*.yaml."""
    known: set[str] = set()
    for rec in parse_tools():
        for k in (rec.get("project_repo"), rec.get("clone_repo")):
            if k:
                known.add(k)
    for path in CATALOG_DIR.glob("*.yaml"):
        for m in GH_LINK_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            r = gh_repo("https://github.com/" + m.group(1))
            if r:
                known.add(r)
    return known


def repos_from_list(source: str, token: str) -> list[str]:
    """Every github owner/repo linked from a curated list's README."""
    status, data = _get(f"https://api.github.com/repos/{source}/readme", token)
    if status != 200 or not isinstance(data, dict) or data.get("encoding") != "base64":
        print(f"  ! could not read README for {source} (status {status})")
        return []
    text = base64.b64decode(data["content"]).decode("utf-8", "replace")
    out: list[str] = []
    for m in GH_LINK_RE.finditer(text):
        repo = gh_repo("https://github.com/" + m.group(1))
        if repo and repo.split("/")[0] not in SKIP_OWNERS and repo != source.lower():
            out.append(repo)
    return list(dict.fromkeys(out))  # dedup, keep order


def repos_from_search(term: str, token: str, per: int = 15) -> list[str]:
    """Top repos for a GitHub search term (sorted by stars)."""
    q = urllib.parse.quote(term)
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={per}"
    status, data = _get(url, token)
    if status != 200 or not isinstance(data, dict):
        print(f"  ! search failed for {term!r} (status {status})")
        return []
    return [gh_repo(it["html_url"]) for it in data.get("items", []) if it.get("html_url")]


def fetch_meta(repo: str, token: str) -> dict:
    """GitHub metadata for one candidate repo (what it does + maintenance signals)."""
    status, d = _get(f"https://api.github.com/repos/{repo}", token)
    if status != 200 or not isinstance(d, dict):
        return {"status": status}
    lic = (d.get("license") or {}).get("spdx_id") or ""
    return {
        "status": 200, "full_name": d.get("full_name"),
        "description": (d.get("description") or "").strip(),
        "stars": d.get("stargazers_count", 0), "pushed_at": d.get("pushed_at"),
        "archived": bool(d.get("archived")), "language": d.get("language") or "",
        "license": "" if lic in ("NOASSERTION", "") else lic,
        "topics": d.get("topics") or [], "html_url": d.get("html_url"),
    }


def suggest_tags(meta: dict) -> list[str]:
    """Map repo topics onto the closed taxonomy (suggestion only; human confirms)."""
    hay = set(meta.get("topics") or [])
    # also mine hyphen/space tokens out of the description
    hay |= set(re.findall(r"[a-z][a-z0-9-]+", (meta.get("description") or "").lower()))
    tags = {TOPIC_MAP[t] for t in hay if t in TOPIC_MAP}
    tags |= {t for t in hay if t in TAXONOMY}  # topic already a canonical tag
    return sorted(tags)


def _age(pushed: str | None) -> tuple[int, str]:
    if not pushed:
        return 10**6, "unknown"
    days = (datetime.now(timezone.utc)
            - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
    return days, pushed[:10]


def _stub(meta: dict, tags: list[str]) -> str:
    """A draft catalog entry — project_url + suggested tags; usage left for a human."""
    hint = INSTALL_HINT.get(meta["language"], "TODO")
    title = meta["full_name"].split("/")[-1]
    desc = (meta["description"] or "TODO — describe what it does").replace('"', "'")
    tagline = ", ".join(tags) if tags else "TODO"
    return (
        f'  - title: "{title}"\n'
        f'    kind: install\n'
        f'    tags: [{tagline}]              # SUGGESTED from repo topics — confirm against tags.TAXONOMY\n'
        f'    description: "{desc}"\n'
        f'    # install: {hint}   # VERIFY the real, pinned install method\n'
        f'    project_url: "{meta["html_url"]}"\n'
        f'    usage: []          # TODO — fill 3-6 REAL canonical commands from the tool\'s docs (no fabrication)\n'
        f'    lab_safe_notes: "" # TODO\n'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", default=[],
                    help="curated-list repo (owner/repo) to mine; repeatable")
    ap.add_argument("--search", action="append", default=[],
                    help="GitHub repo-search term; repeatable")
    ap.add_argument("--min-stars", type=int, default=100)
    ap.add_argument("--stale-years", type=int, default=3, help="flag repos idle longer than this")
    ap.add_argument("--max", type=int, default=60, help="max candidates in the report")
    args = ap.parse_args()

    sources = args.source or (["A-poc/RedTeam-Tools"] if not args.search else [])
    token = load_token()
    print(f"GitHub token: {'yes' if token else 'NO (anon 60/hr — expect rate limits)'}")

    # 1) gather candidate repos from lists + searches
    candidates: list[str] = []
    for src in sources:
        got = repos_from_list(src, token)
        print(f"  list {src}: {len(got)} linked repos")
        candidates += got
    for term in args.search:
        got = repos_from_search(term, token)
        print(f"  search {term!r}: {len(got)} repos")
        candidates += got
    candidates = list(dict.fromkeys(r for r in candidates if r))

    # 2) drop the ones we already ship
    known = known_repos()
    fresh = [r for r in candidates if r not in known]
    print(f"{len(candidates)} unique candidates; {len(candidates) - len(fresh)} already in catalog; "
          f"{len(fresh)} new to look at.")

    # 3) fetch metadata (cached)
    cache: dict = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    for i, repo in enumerate(fresh, 1):
        if repo not in cache:
            cache[repo] = fetch_meta(repo, token)
            if cache[repo].get("status") != 200:
                print(f"  [{i}/{len(fresh)}] {repo}: status {cache[repo].get('status')}")
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))

    # 4) keep live, maintained, popular-enough; rank by stars
    rows = []
    for repo in fresh:
        m = cache.get(repo, {})
        if m.get("status") != 200 or m.get("archived"):
            continue
        if m.get("stars", 0) < args.min_stars:
            continue
        days, last = _age(m.get("pushed_at"))
        rows.append({**m, "repo": repo, "age_days": days, "last": last,
                     "stale": days > args.stale_years * 365, "sugg": suggest_tags(m)})
    rows.sort(key=lambda r: -r["stars"])
    rows = rows[:args.max]
    print(f"{len(rows)} candidates pass filters (>= {args.min_stars}★, not archived).")

    # 5) write the report + draft stubs
    md = [f"# Discovered tool candidates — {datetime.now().strftime('%Y-%m-%d')}", "",
          f"Sources: {', '.join(sources) or '—'}"
          + (f" · searches: {', '.join(repr(s) for s in args.search)}" if args.search else ""), "",
          f"{len(rows)} candidates not already in our catalog (>= {args.min_stars}★, live). "
          "Stubs for hand-curation are in `discovered_candidates.yaml`.", "",
          "| ★ | Last push | Repo | Lang | License | Suggested tags | What it does |",
          "|---:|---|---|---|---|---|---|"]
    for r in rows:
        flag = " ⚠stale" if r["stale"] else ""
        desc = (r["description"] or "").replace("|", "\\|")[:110]
        md.append(f"| {r['stars']} | {r['last']}{flag} | [{r['repo']}]({r['html_url']}) | "
                  f"{r['language']} | {r['license'] or '—'} | {', '.join(r['sugg']) or '—'} | {desc} |")
    md += ["", "## Notes", "",
           "- Tags are **suggested** (mapped from repo topics onto `tags.TAXONOMY`) — confirm before use.",
           "- `usage`/`lab_safe_notes` are intentionally blank in the stubs: fill them with **real**",
           "  commands from each tool's docs. Do not fabricate flags.",
           "- ⚠stale = no push in "
           f"{args.stale_years}y+; weigh before adding.", ""]
    REPORT_MD.write_text("\n".join(md))

    stubs = ["# DRAFT candidate catalog entries from scripts/discover_tools.py — NOT loaded.",
             "# Hand-curate the ones worth adding into the right catalog/<category>.yaml:",
             "# pick a category (set merge_into or a new category), confirm tags, and fill in",
             "# usage/lab_safe_notes/install with REAL values from the tool's docs.", "",
             "tools:"]
    for r in rows:
        stubs.append(_stub(r, r["sugg"]))
    STUBS_YAML.write_text("\n".join(stubs))

    print(f"\nReport → {REPORT_MD.relative_to(ROOT)}")
    print(f"Draft stubs → {STUBS_YAML.relative_to(ROOT)}  ({len(rows)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
