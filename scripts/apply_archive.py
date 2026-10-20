#!/usr/bin/env python3
"""
Apply M1 archive verdicts to tools/*.py.

Reads scripts/tool_audit.json and, for every tool classified DEAD / ARCHIVE / STALE
(and not already archived), injects `ARCHIVED = True` + `ARCHIVED_REASON = "..."`
as the first statements of that tool's class body. Idempotent; skips classes that
already carry ARCHIVED. Run with --apply to write; default is a dry run.

Usage:
  python3 scripts/apply_archive.py            # dry run (shows diff plan)
  python3 scripts/apply_archive.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "scripts" / "tool_audit.json"
TARGET_VERDICTS = {"DEAD", "ARCHIVE", "STALE"}


def reason_for(rec: dict) -> str:
    v, pushed = rec["verdict"], (rec.get("pushed_at") or "")[:7]
    if v == "DEAD":
        if "blocked" in rec["reason"]:
            return "Upstream repo removed/blocked (DMCA or suspended)"
        return "Upstream repo deleted (404)"
    if v == "ARCHIVE":
        return f"Upstream repo archived by author{f' (last commit {pushed})' if pushed else ''}"
    return f"Unmaintained — no commits since {pushed}" if pushed else "Unmaintained upstream"


def apply_to_file(path: Path, targets: list[dict], write: bool) -> list[str]:
    """Insert ARCHIVED lines for each target class in this file. Returns log lines."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    log = []
    # Descend by class-line index so insertions don't shift later ones.
    plans = []
    for rec in targets:
        cname = rec["class"]
        idx = next((i for i, ln in enumerate(lines)
                    if re.match(rf"^class\s+{re.escape(cname)}\s*\(", ln)), None)
        if idx is None:
            log.append(f"  ?? {cname}: class not found in {path.name} — skipped")
            continue
        # Find class-body extent (until next top-level `class ` or EOF).
        end = next((j for j in range(idx + 1, len(lines))
                    if re.match(r"^class\s+\w+\s*\(", lines[j])), len(lines))
        block = "".join(lines[idx:end])
        if re.search(r"^\s+ARCHIVED\s*=\s*True", block, re.M):
            log.append(f"  == {cname}: already ARCHIVED — skipped")
            continue
        # Body indent = leading spaces of the first non-blank body line (default 4).
        indent = "    "
        for j in range(idx + 1, end):
            if lines[j].strip():
                indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                break
        reason = reason_for(rec).replace('"', "'")
        ins = f"{indent}ARCHIVED = True\n{indent}ARCHIVED_REASON = \"{reason}\"\n"
        plans.append((idx, cname, rec["verdict"], reason, ins))

    for idx, cname, verdict, reason, ins in sorted(plans, key=lambda p: p[0], reverse=True):
        lines.insert(idx + 1, ins)
        log.append(f"  ++ {cname} [{verdict}] → {reason}")

    if write and plans:
        path.write_text("".join(lines), encoding="utf-8")
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    records = json.loads(AUDIT.read_text())
    targets = [r for r in records
               if r["verdict"] in TARGET_VERDICTS and not r["already_archived"]]

    by_file: dict[str, list[dict]] = {}
    for r in targets:
        by_file.setdefault(r["file"], []).append(r)

    total = 0
    print(f"{'APPLYING' if args.apply else 'DRY RUN'} — {len(targets)} classes across {len(by_file)} files\n")
    for f in sorted(by_file):
        log = apply_to_file(ROOT / f, by_file[f], args.apply)
        applied = [l for l in log if l.strip().startswith("++")]
        total += len(applied)
        print(f"{f}  ({len(applied)} archived)")
        for l in log:
            print(l)
    print(f"\n{'Wrote' if args.apply else 'Would archive'} {total} classes."
          + ("" if args.apply else "  Re-run with --apply to write."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
