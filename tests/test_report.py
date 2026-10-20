import hackingtool.engagement as engagement
import hackingtool.report as report
from hackingtool.findings import Finding, save_findings

def _root(tmp_path, monkeypatch):
    monkeypatch.setattr(engagement, "ENGAGEMENTS_ROOT", tmp_path)

def test_generate_report(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", targets=["example.com"])
    save_findings(e.findings_file, [
        Finding("subdomain", "a.example.com", "a.example.com", "info", "subfinder", {}, "", "T"),
        Finding("vulnerability", "https://a.example.com/.git/", "Exposed .git", "high",
                "nuclei", {"template_id": "exposed-git"}, "", "T"),
    ])
    path = report.generate_report(e)
    text = path.read_text()
    assert path == e.report_file
    assert "# Engagement: acme" in text
    assert "Exposed .git" in text
    assert "high" in text
    assert "a.example.com" in text

def test_generate_report_empty(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("empty")
    text = report.generate_report(e).read_text()
    assert "No findings" in text
