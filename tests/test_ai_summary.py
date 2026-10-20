import hackingtool.ai_summary as ai_summary
import hackingtool.engagement as engagement
from hackingtool.findings import Finding, save_findings


def _root(tmp_path, monkeypatch):
    monkeypatch.setattr(engagement, "ENGAGEMENTS_ROOT", tmp_path)


def test_prompt_has_guardrail_and_real_findings():
    fs = [Finding("vulnerability", "https://a/.git/", "Exposed .git", "high",
                  "nuclei", {}, "raw-line", "T")]
    prompt = ai_summary._build_prompt(fs)
    assert "do not invent" in prompt.lower() or "not fabricate" in prompt.lower()
    assert "Exposed .git" in prompt


def test_summarize_returns_none_without_findings(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("empty")
    assert ai_summary.summarize(e) is None


def test_summarize_degrades_when_ollama_unreachable(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme")
    save_findings(e.findings_file, [Finding("service", "https://a", "a", "info",
                                            "httpx", {}, "", "T")])
    monkeypatch.setattr(ai_summary, "ask", lambda p: None)
    assert ai_summary.summarize(e) is None


def test_summarize_uses_generator(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme")
    save_findings(e.findings_file, [Finding("service", "https://a", "a", "info",
                                            "httpx", {}, "", "T")])
    monkeypatch.setattr(ai_summary, "ask", lambda p: "SUMMARY OK")
    assert ai_summary.summarize(e) == "SUMMARY OK"
