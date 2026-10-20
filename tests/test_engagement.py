import hackingtool.engagement as engagement
from hackingtool.engagement import Engagement


def _root(tmp_path, monkeypatch):
    monkeypatch.setattr(engagement, "ENGAGEMENTS_ROOT", tmp_path)


def test_create_and_load_roundtrip(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", targets=["example.com"], scope_in=["*.example.com"])
    e.save()
    assert (tmp_path / "acme" / "engagement.json").exists()
    loaded = engagement.load("acme")
    assert loaded.name == "acme"
    assert loaded.targets == ["example.com"]
    assert loaded.scope_in == ["*.example.com"]


def test_scope_matching(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", scope_in=["*.example.com"], scope_out=["admin.example.com"])
    assert e.in_scope("dev.example.com") is True
    assert e.in_scope("admin.example.com") is False
    assert e.in_scope("evil.test") is False


def test_scope_defaults_to_targets(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme", targets=["example.com"])
    assert e.in_scope("example.com") is True


def test_get_or_create_is_idempotent(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    a = engagement.get_or_create("acme", targets=["example.com"])
    b = engagement.get_or_create("acme")
    assert b.targets == ["example.com"]


def test_log_appends(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    e = engagement.create("acme")
    e.log("hello")
    assert "hello" in e.log_file.read_text()
