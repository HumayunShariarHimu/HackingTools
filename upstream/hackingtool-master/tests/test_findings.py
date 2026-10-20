import json
from pathlib import Path
import hackingtool.findings as findings
from hackingtool.findings import Finding, parse_subfinder, parse_httpx, parse_nuclei, save_findings, load_findings

TS = "2026-07-05T00:00:00+00:00"

def test_parse_subfinder():
    raw = "a.example.com\nb.example.com\n\n"
    fs, forward = parse_subfinder(raw, TS)
    assert forward == ["a.example.com", "b.example.com"]
    assert [f.kind for f in fs] == ["subdomain", "subdomain"]
    assert fs[0].target == "a.example.com"
    assert fs[0].source_tool == "subfinder"
    assert fs[0].severity == "info"

def test_parse_httpx_forwards_bare_urls():
    raw = (
        json.dumps({"url": "https://a.example.com", "status_code": 200,
                    "title": "Home", "tech": ["nginx"]}) + "\n"
        + "not-json-skip-me\n"
        + json.dumps({"url": "https://b.example.com", "status_code": 403}) + "\n"
    )
    fs, forward = parse_httpx(raw, TS)
    assert forward == ["https://a.example.com", "https://b.example.com"]
    assert fs[0].kind == "service"
    assert fs[0].details["status_code"] == 200
    assert fs[0].details["tech"] == ["nginx"]

def test_parse_nuclei():
    raw = json.dumps({
        "template-id": "exposed-git",
        "info": {"name": "Exposed .git", "severity": "high"},
        "matched-at": "https://a.example.com/.git/",
        "type": "http",
    }) + "\n"
    fs, forward = parse_nuclei(raw, TS)
    assert forward == []
    assert fs[0].kind == "vulnerability"
    assert fs[0].severity == "high"
    assert fs[0].name == "Exposed .git"
    assert fs[0].target == "https://a.example.com/.git/"
    assert fs[0].details["template_id"] == "exposed-git"

def test_save_and_load_roundtrip(tmp_path: Path):
    fs = [Finding("subdomain", "a.example.com", "a.example.com", "info",
                  "subfinder", {}, "a.example.com", TS)]
    p = tmp_path / "findings.json"
    save_findings(p, fs)
    loaded = load_findings(p)
    assert loaded == fs
