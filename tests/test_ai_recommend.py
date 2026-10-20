"""AI1 recommend: taxonomy guardrail, keyword fallback, transport degrade."""
import hackingtool.ai_recommend as ai_recommend
import hackingtool.tags as tags


def test_parse_drops_fabricated_tags():
    # Only tags that actually exist in the taxonomy survive.
    out = ai_recommend._parse_tags('noise ["hash-crack", "totally-made-up"] tail')
    assert out == ["hash-crack"]


def test_parse_handles_junk():
    assert ai_recommend._parse_tags("no array here") == []
    assert ai_recommend._parse_tags(None) == []
    assert ai_recommend._parse_tags("[not, json]") == []


def test_keyword_match_offline():
    assert "hash-crack" in ai_recommend.keyword_match("crack a hash", tags.TAXONOMY)
    # extraction ~ extract via difflib close-match
    assert "pdf-extraction" in ai_recommend.keyword_match(
        "extract text from a pdf", tags.TAXONOMY)
    assert ai_recommend.keyword_match("", tags.TAXONOMY) == []


def test_suggest_tags_none_when_unreachable(monkeypatch):
    monkeypatch.setattr(ai_recommend, "_byo_key", lambda p: None)
    monkeypatch.setattr(ai_recommend, "_ollama", lambda p: None)
    assert ai_recommend.suggest_tags("crack a hash") is None


def test_suggest_tags_filters_model_reply(monkeypatch):
    monkeypatch.setattr(ai_recommend, "_byo_key", lambda p: None)
    monkeypatch.setattr(ai_recommend, "_ollama",
                        lambda p: '["hash-crack", "invented-tag"]')
    assert ai_recommend.suggest_tags("x") == ["hash-crack"]


def test_resolve_falls_back_to_keywords(monkeypatch):
    monkeypatch.setattr(ai_recommend, "suggest_tags", lambda i: None)
    assert "hash-crack" in ai_recommend.resolve("crack a hash", tags.TAXONOMY)


def test_resolve_prefers_ai_when_present(monkeypatch):
    monkeypatch.setattr(ai_recommend, "suggest_tags", lambda i: ["osint"])
    assert ai_recommend.resolve("anything", tags.TAXONOMY) == ["osint"]


# ── /config test connection probe ────────────────────────────────────────────

class _FakeResp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


def test_test_connection_byo_ok(monkeypatch):
    from hackingtool import config
    monkeypatch.setattr(config, "ai_provider", lambda: "openai-compat")
    monkeypatch.setattr(config, "ai_base_url", lambda: "https://api.anthropic.com/v1")
    monkeypatch.setattr(config, "ai_key", lambda: "sk-test")
    monkeypatch.setattr(config, "ai_model", lambda: "claude-haiku")
    body = b'{"choices":[{"message":{"content":"connected"}}]}'
    monkeypatch.setattr(ai_recommend.urllib.request, "urlopen",
                        lambda req, timeout=30: _FakeResp(body))
    ok, detail = ai_recommend.test_connection()
    assert ok and "connected" in detail


def test_test_connection_reports_missing_key(monkeypatch):
    from hackingtool import config
    monkeypatch.setattr(config, "ai_provider", lambda: "openai-compat")
    monkeypatch.setattr(config, "ai_base_url", lambda: "https://x/v1")
    monkeypatch.setattr(config, "ai_key", lambda: "")
    ok, detail = ai_recommend.test_connection()
    assert not ok and "HACKINGTOOL_AI_KEY" in detail


def test_test_connection_surfaces_http_error(monkeypatch):
    import urllib.error
    from hackingtool import config
    monkeypatch.setattr(config, "ai_provider", lambda: "openai-compat")
    monkeypatch.setattr(config, "ai_base_url", lambda: "https://x/v1")
    monkeypatch.setattr(config, "ai_key", lambda: "sk-bad")
    monkeypatch.setattr(config, "ai_model", lambda: "m")

    def _raise(req, timeout=30):
        import io
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"bad key"))
    monkeypatch.setattr(ai_recommend.urllib.request, "urlopen", _raise)
    ok, detail = ai_recommend.test_connection()
    assert not ok and "401" in detail
