#!/usr/bin/env python3
"""Build a metadata-only JSON directory from the archived tool catalogue.

This script parses names, categories, tags, and explicitly published HTTPS links.
It never imports, executes, or reproduces any archived tool implementation.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "upstream/hackingtool-master/docs/TOOLS.md"
OUTPUT = ROOT / "data/catalog.json"
ARCHIVE_CATALOG_URL = (
    "https://github.com/HumayunShariarHimu/HackingTools/blob/main/"
    "upstream/hackingtool-master/docs/TOOLS.md"
)

CATEGORY_DESCRIPTIONS = {
    "Anonymously Hiding Tools": "Resources about network privacy, anonymity and tunnelling. Review the upstream project and local rules before use.",
    "Information gathering tools": "Resources for security inventory, public-source research and network discovery. Active requests require a written scope.",
    "Wordlist Generator": "Resources related to password-audit data and wordlists. Use only synthetic or explicitly authorized test data.",
    "Wireless attack tools": "Wi-Fi and wireless-security resources. Restrict any testing to equipment and radio environments you own or are authorized to assess.",
    "SQL Injection Tools": "Resources for understanding and assessing SQL injection in deliberately vulnerable labs or explicitly scoped applications.",
    "Phishing attack tools": "Phishing-related references and simulation resources for defensive awareness. Never collect real credentials or target people without explicit approval.",
    "Web Attack tools": "Web application security resources. Interact only with applications that are yours or explicitly in scope.",
    "Post exploitation tools": "High-risk post-compromise and privilege-analysis resources. This directory does not run them; use isolated labs and explicit written authorization only.",
    "Forensic tools": "Resources for preserving, examining and explaining digital evidence. Follow evidence-handling and privacy requirements.",
    "Payload creation tools": "Payload-related references with elevated risk. Do not deploy generated artifacts; use isolated, disposable labs under written authorization.",
    "Exploit framework": "Exploit-development and validation references. Keep activity inside intentionally vulnerable labs or signed-off scope.",
    "Reverse engineering tools": "Resources for examining software, binaries and file formats. Respect ownership, privacy and applicable legal restrictions.",
    "DDOS Attack Tools": "Denial-of-service-related resources are listed for defensive awareness only. Do not generate disruptive traffic or test public systems.",
    "Remote Administrator Tools (RAT)": "Remote administration and remote-access references. Verify publisher, consent, authorization and endpoint controls before considering use.",
    "XSS Attack Tools": "Cross-site scripting resources for safe education and authorized application testing. Prefer dedicated training labs.",
    "Steganography Tools": "Resources for hiding, detecting or inspecting data embedded in media. Handle files lawfully and preserve originals when investigating.",
    "Active Directory Tools": "Windows identity and directory-security resources. Use only in a lab or a documented, explicitly authorized environment.",
    "Cloud Security Tools": "Cloud security resources. Confirm account ownership, tenant boundaries, provider policies and written scope before testing.",
    "Mobile Security Tools": "Mobile application and device-security resources. Use test devices and applications you own or are authorized to assess.",
    "Other tools": "Additional security and learning resources. Check the official project documentation, permissions and operating context before use.",
    "Password / Hash Cracking": "Password-audit and hash-analysis resources. Work only on hashes and accounts you own or are explicitly authorized to audit.",
}


def entry_type(tags: list[str]) -> str:
    tagset = set(tags)
    if "online-service" in tagset:
        return "service"
    if tagset & {"learning", "reference", "cheatsheet"}:
        return "reference"
    return "tool"


def parse_link(markdown_title: str) -> tuple[str, str | None]:
    match = re.match(r"\[([^\]]+)\]\((https://[^)]+)\)", markdown_title)
    if match:
        title = html.unescape(match.group(1)).strip()
        candidate = html.unescape(match.group(2)).strip()
        parsed = urlparse(candidate)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return title, candidate
    title = re.sub(r"<[^>]+>", "", markdown_title).strip()
    return html.unescape(title), None


def build() -> list[dict[str, object]]:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing source catalogue: {SOURCE}")

    category = "Uncategorized"
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    pattern = re.compile(r"-\s+(.+?)\s+—\s+<sub>(.*?)</sub>\s*$")

    for raw_line in SOURCE.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("## "):
            category = raw_line[3:].strip()
            continue
        match = pattern.match(raw_line.strip())
        if not match:
            continue
        markdown_title, raw_tags = match.groups()
        title, source_url = parse_link(markdown_title)
        tags = [tag.strip().lower() for tag in raw_tags.split(",") if tag.strip()]
        if not title:
            continue
        dedupe_key = (category, title.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "resource"
        record_id = f"{len(records) + 1:03d}-{slug}"
        records.append({
            "id": record_id,
            "name": title,
            "category": category,
            "tags": tags,
            "type": entry_type(tags),
            "description": CATEGORY_DESCRIPTIONS.get(
                category,
                "Curated security resource. Check the official source, intended use and authorization scope before use.",
            ),
            "sourceUrl": source_url,
            "archiveUrl": ARCHIVE_CATALOG_URL,
            "platform": "Not specified in the archived catalog",
        })

    if not records:
        raise SystemExit("No entries found in the archived Markdown catalogue")
    payload = {
        "generatedFrom": "upstream/hackingtool-master/docs/TOOLS.md",
        "generatedAt": "source-controlled",
        "count": len(records),
        "sourceClaimedCount": 219,
        "note": "The archived README claims 219 active tools; the published docs/TOOLS.md contains the records counted here. No missing entries or source URLs are invented.",
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    result = build()
    print(f"Built {len(result)} records at {OUTPUT.relative_to(ROOT)}")
