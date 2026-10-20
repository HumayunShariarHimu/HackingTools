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
SOURCE = ROOT / "docs/TOOLS.md"
OUTPUT = ROOT / "data/catalog.json"
ARCHIVE_CATALOG_URL = (
    "https://github.com/HumayunShariarHimu/HackingTools/blob/main/"
    "docs/TOOLS.md"
)

CATEGORY_DESCRIPTIONS = {
    "Anonymously Hiding Tools": "নেটওয়ার্ক গোপনীয়তা, anonymity ও tunnelling-সংক্রান্ত resource। ব্যবহারের আগে upstream প্রকল্প ও স্থানীয় নিয়ম যাচাই করুন।",
    "Information gathering tools": "নিরাপত্তা inventory, public-source research ও network discovery-র resource। সক্রিয় অনুরোধে লিখিত scope থাকতে হবে।",
    "Wordlist Generator": "Password audit ও wordlist-সংক্রান্ত resource। শুধু synthetic বা স্পষ্টভাবে অনুমোদিত test data ব্যবহার করুন।",
    "Wireless attack tools": "Wi-Fi ও wireless security-সংক্রান্ত resource। পরীক্ষা কেবল নিজের বা অনুমোদিত equipment ও radio environment-এ সীমাবদ্ধ রাখুন।",
    "SQL Injection Tools": "SQL injection বোঝা ও মূল্যায়নের resource; ইচ্ছাকৃতভাবে দুর্বল lab বা স্পষ্ট scope-যুক্ত application-এ ব্যবহার করুন।",
    "Phishing attack tools": "প্রতিরক্ষামূলক সচেতনতা ও অনুমোদিত simulation-সংক্রান্ত resource। বাস্তব credential সংগ্রহ বা অনুমতি ছাড়া কাউকে লক্ষ্য করবেন না।",
    "Web Attack tools": "Web application security-সংক্রান্ত resource। কেবল নিজের বা স্পষ্টভাবে scope-এ থাকা application-এ কাজ করুন।",
    "Post exploitation tools": "Compromise-পরবর্তী কার্যকলাপ ও privilege analysis-সংক্রান্ত উচ্চ-ঝুঁকির resource। এই directory এগুলো চালায় না; isolated lab ও লিখিত অনুমতি আবশ্যক।",
    "Forensic tools": "Digital evidence সংরক্ষণ, পরীক্ষা ও বোঝার resource। Evidence handling ও privacy নিয়ম অনুসরণ করুন।",
    "Payload creation tools": "উচ্চ-ঝুঁকির payload-সংক্রান্ত reference। তৈরি করা artifact deploy করবেন না; লিখিত অনুমতিসহ isolated disposable lab ব্যবহার করুন।",
    "Exploit framework": "Exploit development ও validation-সংক্রান্ত reference। ইচ্ছাকৃতভাবে দুর্বল lab বা অনুমোদিত scope-এর ভেতরে থাকুন।",
    "Reverse engineering tools": "Software, binary ও file format পরীক্ষা করার resource। মালিকানা, privacy ও প্রযোজ্য আইন মানুন।",
    "DDOS Attack Tools": "Denial-of-service-সংক্রান্ত resource কেবল defensive awareness-এর জন্য তালিকাভুক্ত। বিঘ্নকারী traffic তৈরি বা public system পরীক্ষা করবেন না।",
    "Remote Administrator Tools (RAT)": "Remote administration ও access-সংক্রান্ত reference। বিবেচনার আগে publisher, consent, authorization ও endpoint control যাচাই করুন।",
    "XSS Attack Tools": "Cross-site scripting শেখা ও অনুমোদিত application testing-এর resource। নির্দিষ্ট training lab অগ্রাধিকার দিন।",
    "Steganography Tools": "Media-তে data লুকানো, শনাক্ত বা পরীক্ষা করার resource। আইন মেনে file ব্যবহার করুন এবং তদন্তে original অক্ষত রাখুন।",
    "Active Directory Tools": "Windows identity ও directory security-সংক্রান্ত resource। কেবল lab বা নথিভুক্ত, স্পষ্টভাবে অনুমোদিত environment-এ ব্যবহার করুন।",
    "Cloud Security Tools": "Cloud security-সংক্রান্ত resource। পরীক্ষার আগে account ownership, tenant boundary, provider policy ও লিখিত scope নিশ্চিত করুন।",
    "Mobile Security Tools": "Mobile app ও device security-সংক্রান্ত resource। নিজের বা অনুমোদিত test device ও application ব্যবহার করুন।",
    "Other tools": "অতিরিক্ত security ও learning resource। ব্যবহারের আগে official documentation, permission ও operating context যাচাই করুন।",
    "Password / Hash Cracking": "Password audit ও hash analysis-এর resource। শুধু নিজের বা স্পষ্টভাবে অনুমোদিত hash ও account নিয়ে কাজ করুন।",
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
                "নিরাপত্তা ও শিক্ষামূলক resource। ব্যবহারের আগে official source, উদ্দেশ্য ও অনুমোদিত scope যাচাই করুন।",
            ),
            "sourceUrl": source_url,
            "archiveUrl": ARCHIVE_CATALOG_URL,
            "platform": "Archived catalog-এ উল্লেখ নেই",
        })

    if not records:
        raise SystemExit("No entries found in the archived Markdown catalogue")
    payload = {
        "generatedFrom": "docs/TOOLS.md",
        "generatedAt": "source-controlled",
        "count": len(records),
        "sourceClaimedCount": 219,
        "note": "Archived README-তে 219টি active tool-এর দাবি রয়েছে; প্রকাশিত docs/TOOLS.md-এ এই সংখ্যক entry পাওয়া গেছে। অনুপস্থিত entry বা source URL অনুমান করে যোগ করা হয়নি।",
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    result = build()
    print(f"Built {len(result)} records at {OUTPUT.relative_to(ROOT)}")
