#!/usr/bin/env python3
"""Build a metadata-only JSON directory from the archived tool catalogue.

This script parses names, categories, tags, and explicitly published HTTPS links.
It never imports, executes, or reproduces any archived tool implementation.
"""
from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/TOOLS.md"
TOOL_SOURCE = ROOT / "src/hackingtool/tools"
OUTPUT = ROOT / "data/catalog.json"
ARCHIVED_METADATA = ROOT / "data/archived-tools.json"
ARCHIVE_CATALOG_URL = (
    "https://github.com/HumayunShariarHimu/HackingTools/blob/main/"
    "docs/TOOLS.md"
)

CATEGORY_DESCRIPTIONS = {
    "Anonymously Hiding Tools": "Resources related to network privacy, anonymity and tunnelling. Review the upstream project and applicable rules before use.",
    "Information gathering tools": "Resources for security inventory, public-source research and network discovery. Active assessments require written scope.",
    "Wordlist Generator": "Resources for password audits and wordlists. Use synthetic or explicitly authorized test data only.",
    "Wireless attack tools": "Resources related to Wi-Fi and wireless security. Test only equipment and radio environments you own or are authorized to assess.",
    "SQL Injection Tools": "Resources for learning about and assessing SQL injection in intentionally vulnerable labs or applications within an authorized scope.",
    "Phishing attack tools": "Resources for defensive awareness and authorized simulations. Never collect real credentials or target people without permission.",
    "Web Attack tools": "Resources related to web application security. Use only on applications you own or that are explicitly in scope.",
    "Post exploitation tools": "High-risk resources associated with post-compromise activity and privilege analysis. This directory is read-only; use an isolated, authorized lab.",
    "Forensic tools": "Resources for preserving, examining and understanding digital evidence. Follow evidence-handling and privacy requirements.",
    "Payload creation tools": "High-risk payload-related references. Do not deploy generated artifacts; use an isolated, disposable lab with written authorization.",
    "Exploit framework": "References for exploit development and validation. Stay within intentionally vulnerable labs or a documented authorized scope.",
    "Reverse engineering tools": "Resources for examining software, binaries and file formats. Respect ownership, privacy and applicable law.",
    "DDOS Attack Tools": "Denial-of-service resources are listed for defensive awareness only. Do not generate disruptive traffic or test public systems.",
    "Remote Administrator Tools (RAT)": "References related to remote administration and access. Verify the publisher, consent, authorization and endpoint controls.",
    "XSS Attack Tools": "Resources for learning about cross-site scripting and authorized application testing. Prefer designated training labs.",
    "Steganography Tools": "Resources for hiding, detecting or examining data in media. Handle files lawfully and preserve originals during investigations.",
    "Active Directory Tools": "Resources related to Windows identity and directory security. Use only in a lab or documented, explicitly authorized environment.",
    "Cloud Security Tools": "Cloud-security resources. Confirm account ownership, tenant boundaries, provider policies and written scope before assessment.",
    "Mobile Security Tools": "Resources for mobile application and device security. Use only your own or authorized test devices and applications.",
    "Other tools": "Additional security and learning resources. Verify the official source, purpose, permission and operating context before use.",
    "Password / Hash Cracking": "Resources for password audits and hash analysis. Work only with hashes and accounts you own or are explicitly authorized to assess.",
}

ARCHIVED_CATEGORY_BY_MODULE = {
    "ddos": "DDOS Attack Tools",
    "exploit_frameworks": "Exploit framework",
    "information_gathering": "Information gathering tools",
    "payload_creator": "Payload creation tools",
    "phishing_attack": "Phishing attack tools",
    "post_exploitation": "Post exploitation tools",
    "remote_administration": "Remote Administrator Tools (RAT)",
    "sql_injection": "SQL Injection Tools",
    "steganography": "Steganography Tools",
    "web_attack": "Web Attack tools",
    "wireless_attack": "Wireless attack tools",
    "wordlist_generator": "Wordlist Generator",
    "xss_attack": "XSS Attack Tools",
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


def archived_tool_records(existing: list[dict[str, object]]) -> list[dict[str, object]]:
    """Read only literal metadata from classes explicitly marked ARCHIVED=True."""
    if not TOOL_SOURCE.is_dir():
        if not ARCHIVED_METADATA.is_file():
            raise SystemExit(f"Missing archived metadata snapshot: {ARCHIVED_METADATA}")
        archived = json.loads(ARCHIVED_METADATA.read_text(encoding="utf-8"))
        if not isinstance(archived, list) or not all(
            isinstance(record, dict)
            and record.get("status") == "archived"
            and isinstance(record.get("id"), str)
            and isinstance(record.get("name"), str)
            for record in archived
        ):
            raise SystemExit(f"Invalid archived metadata snapshot: {ARCHIVED_METADATA}")
        return archived

    existing_keys = {
        (str(record["category"]), str(record["name"]).casefold())
        for record in existing
    }
    archived: list[dict[str, object]] = []
    for path in sorted(TOOL_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for class_node in tree.body:
            if not isinstance(class_node, ast.ClassDef):
                continue
            values: dict[str, object] = {}
            for statement in class_node.body:
                if isinstance(statement, ast.Assign):
                    targets = statement.targets
                elif isinstance(statement, ast.AnnAssign):
                    targets = [statement.target]
                else:
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in {
                        "ARCHIVED", "TITLE", "DESCRIPTION", "PROJECT_URL",
                        "ARCHIVED_REASON", "SUPPORTED_OS",
                    }:
                        value_node = statement.value
                        if value_node is None:
                            continue
                        try:
                            values[target.id] = ast.literal_eval(value_node)
                        except (ValueError, TypeError, SyntaxError):
                            continue
            if values.get("ARCHIVED") is not True:
                continue

            title = values.get("TITLE")
            if not isinstance(title, str) or not title.strip():
                title = class_node.name
            title = html.unescape(title.strip())
            category = (
                "Other tools" if path.parent.name == "others"
                else ARCHIVED_CATEGORY_BY_MODULE.get(path.stem)
            )
            if not category:
                raise SystemExit(f"No archived category mapping for {path.relative_to(TOOL_SOURCE)}")
            key = (category, title.casefold())
            if key in existing_keys:
                raise SystemExit(f"Archived tool duplicates a published catalog entry: {category} / {title}")
            existing_keys.add(key)

            candidate = values.get("PROJECT_URL")
            url_candidate = candidate.strip() if isinstance(candidate, str) else ""
            parsed = urlparse(url_candidate) if url_candidate else None
            source_url = (
                url_candidate
                if parsed and parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                else None
            )
            description = values.get("DESCRIPTION")
            if not isinstance(description, str) or not description.strip():
                description = CATEGORY_DESCRIPTIONS.get(category, "Archived resource from the original project source.")
            reason = values.get("ARCHIVED_REASON")
            if not isinstance(reason, str) or not reason.strip():
                reason = "Marked archived in the original project source."
            platform = values.get("SUPPORTED_OS")
            if isinstance(platform, (list, tuple)):
                platform = ", ".join(str(item) for item in platform)
            if not isinstance(platform, str):
                platform = "Not listed in the archived source"

            path_from_root = path.relative_to(ROOT).as_posix()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "resource"
            archived.append({
                "id": f"{len(existing) + len(archived) + 1:03d}-archived-{slug}",
                "name": title,
                "category": category,
                "tags": [],
                "type": "tool",
                "description": description.strip(),
                "sourceUrl": source_url,
                "archiveUrl": "https://github.com/HumayunShariarHimu/HackingTools/blob/main/" + quote(path_from_root, safe="/"),
                "platform": platform,
                "status": "archived",
                "statusReason": reason.strip(),
            })
    ARCHIVED_METADATA.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVED_METADATA.write_text(
        json.dumps(archived, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return archived


def build() -> list[dict[str, object]]:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing source catalogue: {SOURCE}")

    category = "Uncategorized"
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    pattern = re.compile(r"-\s+(.+?)\s+—\s+<sub>(.*?)</sub>\s*$")

    for raw_line in SOURCE.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("## "):
            category = re.sub(r"^[^\w]+", "", raw_line[3:].strip()).strip()
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
                "Security and learning resource. Verify the official source, purpose and authorized scope before use.",
            ),
            "sourceUrl": source_url,
            "archiveUrl": ARCHIVE_CATALOG_URL,
            "platform": "Not listed in the archived source",
            "status": "active",
            "statusReason": "",
        })

    if not records:
        raise SystemExit("No entries found in the archived Markdown catalogue")
    active_count = len(records)
    archived = archived_tool_records(records)
    records.extend(archived)
    archived_count = len(archived)
    https_source_count = sum(bool(record["sourceUrl"]) for record in records)
    category_count = len({str(record["category"]) for record in records})
    payload = {
        "generatedFrom": "docs/TOOLS.md",
        "generatedAt": "source-controlled",
        "count": len(records),
        "activeResourceCount": active_count,
        "archivedResourceCount": archived_count,
        "categoryCount": category_count,
        "httpsSourceCount": https_source_count,
        "noHttpsSourceCount": len(records) - https_source_count,
        "staleReadmeClaimCount": 219,
        "note": (
            f"This directory includes {active_count} published resources from docs/TOOLS.md and "
            f"{archived_count} additional Python tools marked archived in the source, across {category_count} categories. "
            f"{https_source_count} have HTTPS source links and "
            f"{len(records) - https_source_count} do not. Archived entries are labeled, retained for reference and never executed. "
            "The old README claim of 219 tools is stale: source evidence supports 217 active runtime leaves, "
            "including two built-in menu actions, rather than 219."
        ),
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    result = build()
    print(f"Built {len(result)} records at {OUTPUT.relative_to(ROOT)}")
