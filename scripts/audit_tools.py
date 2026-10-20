#!/usr/bin/env python3
"""
M1 — Tool-list curation audit.

Statically parses every HackingTool subclass in tools/, extracts its PROJECT_URL
(and the git-clone URL from INSTALL_COMMANDS), then queries the GitHub API for
each unique repo's maintenance signals (last push, archived flag, stars, 404).
Classifies each tool KEEP / STALE / DEAD / REFRESH-URL / ARCHIVED / MANUAL and
writes a Markdown + JSON report.

Read-only: it does NOT modify tools/. Applying verdicts is a separate step.

Auth: needs a GitHub token to cover all repos in one pass (anon = 60 req/hr).
  Provide via env GITHUB_TOKEN / GH_TOKEN, or a gitignored file scripts/.github_token.
  A plain token with NO scopes is enough (all repos are public).

Results are cached in scripts/.audit_cache.json, so reruns only fetch what's new.

Usage:
  python3 scripts/audit_tools.py                # audit, using cache
  python3 scripts/audit_tools.py --refresh      # ignore cache, re-fetch all
  python3 scripts/audit_tools.py --stale-years 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
CACHE_FILE = ROOT / "scripts" / ".audit_cache.json"
REPORT_MD = ROOT / "scripts" / "tool_audit_report.md"
REPORT_JSON = ROOT / "scripts" / "tool_audit.json"

CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(", re.M)
TITLE_RE = re.compile(r'TITLE\s*=\s*["\'](.+?)["\']')
PROJECT_URL_RE = re.compile(r'PROJECT_URL\s*=\s*["\'](https?://[^"\']+)["\']')
ARCHIVED_RE = re.compile(r"ARCHIVED\s*=\s*True")
ARCHIVED_REASON_RE = re.compile(r'ARCHIVED_REASON\s*=\s*["\'](.+?)["\']')
GH_CLONE_RE = re.compile(r"git\s+clone\s+(?:--\S+\s+)*(https?://github\.com/[^\s\"']+)")
GH_REPO_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s#?\"']+)")


def gh_repo(url: str) -> str | None:
    """Normalize a GitHub URL to 'owner/repo' (lowercased), or None."""
    m = GH_REPO_RE.search(url or "")
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    # Cut at the first char that can't be in a repo name (handles ".git", ";cmd", etc.)
    repo = re.split(r"[^\w.\-]", repo)[0].removesuffix(".git")
    return f"{owner}/{repo}".lower()


def parse_tools() -> list[dict]:
    """Extract one record per HackingTool-ish class that declares a PROJECT_URL."""
    records = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        category = path.stem.replace("_", " ").title()
        # Split file into per-class blocks.
        starts = [(m.start(), m.group(1)) for m in CLASS_RE.finditer(text)]
        for i, (pos, cname) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            block = text[pos:end]
            purl_m = PROJECT_URL_RE.search(block)
            if not purl_m:
                continue  # no project URL → nothing to check
            title_m = TITLE_RE.search(block)
            clone_m = GH_CLONE_RE.search(block)
            records.append({
                "class": cname,
                "title": (title_m.group(1) if title_m else cname),
                "category": category,
                "file": str(path.relative_to(ROOT)),
                "project_url": purl_m.group(1).strip(),
                "project_repo": gh_repo(purl_m.group(1)),
                "clone_repo": gh_repo(clone_m.group(1)) if clone_m else None,
                "already_archived": bool(ARCHIVED_RE.search(block)),
                "archived_reason": (ARCHIVED_REASON_RE.search(block).group(1)
                                    if ARCHIVED_REASON_RE.search(block) else ""),
            })
    return records


def load_token() -> str | None:
    import os
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    tok_file = ROOT / "scripts" / ".github_token"
    if tok_file.exists():
        return tok_file.read_text().strip() or None
    return None


def fetch_repo(repo: str, token: str | None) -> dict:
    """Query the GitHub API for one repo. Returns a status dict (never raises)."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "hackingtool-audit"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        return {
            "status": 200,
            "pushed_at": d.get("pushed_at"),
            "archived": d.get("archived", False),
            "stars": d.get("stargazers_count", 0),
            "fork": d.get("fork", False),
            "full_name": d.get("full_name"),
        }
    except urllib.error.HTTPError as e:
        # Rate limiting: 429, or 403 whose body mentions "rate limit". Unify on 429
        # so a *persistent* 403 (DMCA/suspended/blocked repo) stays distinct and cacheable.
        if e.code == 429:
            return {"status": 429}
        if e.code == 403 and "rate limit" in (e.read().decode("utf-8", "ignore").lower()):
            return {"status": 429}
        return {"status": e.code}  # incl. persistent 403 = blocked
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {"status": 0, "error": str(e)}


def classify(rec: dict, api: dict, stale_years: int) -> tuple[str, str]:
    """Return (verdict, reason)."""
    if rec["already_archived"]:
        return "ALREADY-ARCHIVED", rec["archived_reason"] or "flagged in code"
    if not rec["project_repo"]:
        return "MANUAL", "non-GitHub host — check by hand"
    st = api.get("status")
    if st is None:
        return "PENDING", "not fetched yet — add token and rerun"
    if st == 404:
        return "DEAD", "repo 404 (deleted/renamed)"
    if st == 403:
        return "DEAD", "repo blocked (DMCA / suspended / private)"
    if st == 429:
        return "PENDING", "rate-limited — needs token to finish"
    if st != 200:
        return "MANUAL", f"API status {st}"
    if api.get("archived"):
        return "ARCHIVE", "upstream repo archived"
    pushed = api.get("pushed_at")
    if pushed:
        age_days = (datetime.now(timezone.utc)
                    - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
        if age_days > stale_years * 365:
            return "STALE", f"no push in {age_days // 365}y {(age_days % 365) // 30}m"
    # URL points at a different repo than we clone → drift
    if rec["clone_repo"] and rec["project_repo"] and rec["clone_repo"] != rec["project_repo"]:
        return "REFRESH-URL", f"PROJECT_URL={rec['project_repo']} but clones {rec['clone_repo']}"
    yrs = ""
    if pushed:
        yrs = f", last push {pushed[:10]}"
    return "KEEP", f"{api.get('stars', 0)}★{yrs}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore cache")
    ap.add_argument("--stale-years", type=int, default=2)
    args = ap.parse_args()

    records = parse_tools()
    repos = sorted({r["project_repo"] for r in records if r["project_repo"]})
    print(f"Parsed {len(records)} tools with a PROJECT_URL; {len(repos)} unique GitHub repos.")

    cache: dict = {}
    if CACHE_FILE.exists() and not args.refresh:
        cache = json.loads(CACHE_FILE.read_text())
        # Drop any rate-limit misses that were cached by older buggy runs.
        poisoned = [k for k, v in cache.items() if v.get("status") in (403, 429)]
        for k in poisoned:
            del cache[k]
        if poisoned:
            print(f"Purged {len(poisoned)} stale rate-limit entries from cache.")

    token = load_token()
    print(f"GitHub token: {'yes' if token else 'NO (anon 60/hr limit)'}")

    fetched = rate_limited = 0
    for repo in repos:
        if repo in cache and not args.refresh:
            continue
        api = fetch_repo(repo, token)
        if api.get("status") == 429:
            rate_limited += 1
            if rate_limited == 1:
                print("  ! hit rate limit — caching what we have; add a token to finish.")
            continue  # don't cache a rate-limit miss
        cache[repo] = api
        fetched += 1
        if not token:
            time.sleep(0.3)  # be polite when anon
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))
    print(f"Fetched {fetched} new; {len(cache)} cached; {len(repos) - len(cache)} still unfetched.")

    # Classify + assemble
    results = []
    for rec in records:
        api = cache.get(rec["project_repo"], {}) if rec["project_repo"] else {}
        verdict, reason = classify(rec, api, args.stale_years)
        results.append({**rec, "verdict": verdict, "reason": reason,
                        "stars": api.get("stars"), "pushed_at": api.get("pushed_at")})

    order = ["DEAD", "ARCHIVE", "STALE", "REFRESH-URL", "MANUAL", "PENDING",
             "ALREADY-ARCHIVED", "KEEP"]
    results.sort(key=lambda r: (order.index(r["verdict"]) if r["verdict"] in order else 99,
                                r["category"], r["title"]))

    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    REPORT_JSON.write_text(json.dumps(results, indent=2))

    lines = [f"# Tool-List Curation Audit — {datetime.now().strftime('%Y-%m-%d')}", "",
             f"Parsed **{len(records)}** tools with a PROJECT_URL across "
             f"**{len(repos)}** unique GitHub repos.", "",
             "## Summary", "", "| Verdict | Count | Meaning |", "|---|---:|---|"]
    meaning = {
        "DEAD": "repo 404 → archive/remove",
        "ARCHIVE": "upstream archived → move to Archived",
        "STALE": f"no commits in {args.stale_years}y+ → archive candidate",
        "REFRESH-URL": "PROJECT_URL ≠ cloned repo → fix link",
        "MANUAL": "non-GitHub / API error → check by hand",
        "PENDING": "not yet fetched (needs token)",
        "ALREADY-ARCHIVED": "already flagged in code",
        "KEEP": "maintained → keep",
    }
    for v in order:
        if counts.get(v):
            lines.append(f"| {v} | {counts[v]} | {meaning.get(v,'')} |")

    lines += ["", "## Action list (non-KEEP, non-already-archived)", "",
              "| Verdict | Tool | Category | Repo | Reason | File |",
              "|---|---|---|---|---|---|"]
    for r in results:
        if r["verdict"] in ("KEEP", "ALREADY-ARCHIVED"):
            continue
        lines.append(f"| {r['verdict']} | {r['title']} | {r['category']} | "
                     f"{r['project_repo'] or r['project_url']} | {r['reason']} | {r['file']} |")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines))

    print("\n" + " · ".join(f"{v}:{counts[v]}" for v in order if counts.get(v)))
    print(f"Report → {REPORT_MD.relative_to(ROOT)}  |  {REPORT_JSON.relative_to(ROOT)}")
    if counts.get("PENDING"):
        print(f"\n⚠ {counts['PENDING']} tools PENDING — add a GitHub token and rerun to finish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
