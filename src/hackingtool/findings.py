"""Normalized findings schema + per-tool parsers. Stdlib only."""
import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Finding:
    kind: str          # subdomain | service | vulnerability
    target: str
    name: str
    severity: str      # info | low | medium | high | critical | unknown
    source_tool: str
    details: dict
    raw: str
    timestamp: str


def parse_subfinder(raw: str, ts: str) -> tuple[list[Finding], list[str]]:
    hosts = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    findings = [Finding("subdomain", h, h, "info", "subfinder", {}, h, ts) for h in hosts]
    return findings, hosts


def parse_httpx(raw: str, ts: str) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    urls: list[str] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue  # skip malformed line, keep going
        if not isinstance(obj, dict):          # valid JSON but not an object → skip
            continue
        url = obj.get("url") or obj.get("input") or ""
        if not isinstance(url, str) or not url:
            continue
        title = obj.get("title")
        title = title if isinstance(title, str) and title else url
        details = {
            "status_code": obj.get("status_code"),
            "title": obj.get("title"),
            "tech": obj.get("tech"),
            "webserver": obj.get("webserver"),
        }
        findings.append(Finding("service", url, title, "info", "httpx", details, ln, ts))
        urls.append(url)
    return findings, urls


def parse_nuclei(raw: str, ts: str) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):          # valid JSON but not an object → skip
            continue
        info = obj.get("info")
        if not isinstance(info, dict):
            info = {}
        target = obj.get("matched-at") or obj.get("host") or ""
        if not isinstance(target, str):
            target = ""
        tid = obj.get("template-id", "")
        tid = tid if isinstance(tid, str) else ""
        name = info.get("name") or tid
        name = name if isinstance(name, str) and name else tid
        sev = info.get("severity")
        sev = sev if isinstance(sev, str) and sev else "unknown"
        details = {"template_id": tid, "matched_at": obj.get("matched-at"),
                   "type": obj.get("type")}
        findings.append(Finding("vulnerability", target, name, sev, "nuclei",
                                details, ln, ts))
    return findings, []


PARSERS = {"subfinder": parse_subfinder, "httpx": parse_httpx, "nuclei": parse_nuclei}


def save_findings(path: Path, findings: list[Finding]) -> None:
    from hackingtool.storage import write_json
    write_json(path, [asdict(f) for f in findings], indent=2)


def load_findings(path: Path) -> list[Finding]:
    if not path.exists():
        return []
    return [Finding(**d) for d in json.loads(path.read_text(encoding="utf-8"))]
