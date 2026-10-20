"""sponsors: trust-filtered committed loader, tier-weighted pick, zero network by default. Never raises."""
import hackingtool.sponsors as sp
from hackingtool.sponsors import Sponsor


def _reset():
    sp._featured_memo = None


def test_load_shipped_empty_returns_empty(monkeypatch):
    _reset()
    monkeypatch.setattr(sp, "_sponsors_url", lambda: "")   # no remote, exercise shipped file
    assert sp.load() == []


def test_load_filters_untrusted_and_incomplete(monkeypatch, tmp_path):
    y = tmp_path / "sponsors.yaml"
    y.write_text(
        'sponsors:\n'
        '  - {name: "Good", url: "https://good.example", tier: "gold"}\n'
        '  - {name: "AlsoGood", url: "http://ok.example"}\n'
        '  - {name: "JS", url: "javascript:alert(1)"}\n'
        '  - {name: "File", url: "file:///etc/passwd"}\n'
        '  - {url: "https://noname.example"}\n'
        '  - {name: "NoUrl"}\n'
        '  - {name: "BadTier", url: "https://bt.example", tier: "platinum"}\n'
    )
    monkeypatch.setattr(sp, "_YAML", y)
    monkeypatch.setattr(sp, "_sponsors_url", lambda: "")
    out = sp.load()
    assert [s.url for s in out] == ["https://good.example", "http://ok.example", "https://bt.example"]
    assert out[0].tier == "gold"
    assert out[2].tier == "bronze"   # unknown tier -> default


def test_featured_deterministic_and_from_list(monkeypatch):
    _reset()
    pool = [Sponsor("A", "https://a.example"), Sponsor("B", "https://b.example")]
    monkeypatch.setattr(sp, "load", lambda: pool)
    r1 = sp.featured(1, seed=0)
    _reset()
    r2 = sp.featured(1, seed=0)
    assert len(r1) == 1 and r1[0] in pool
    assert r1[0].url == r2[0].url   # deterministic for a fixed seed


def test_featured_empty_list(monkeypatch):
    _reset()
    monkeypatch.setattr(sp, "load", lambda: [])
    assert sp.featured(1, seed=0) == []


def test_tier_weighting_favors_gold(monkeypatch):
    pool = [Sponsor("Gold", "https://g.example", "", "gold")] + [
        Sponsor(f"B{i}", f"https://b{i}.example", "", "bronze") for i in range(9)
    ]
    monkeypatch.setattr(sp, "load", lambda: pool)
    n = 300
    gold = 0
    for seed in range(n):
        _reset()
        picked = sp.featured(1, seed=seed)
        if picked and picked[0].name == "Gold":
            gold += 1
    # P(gold) = 3/(3+9) = 0.25 weighted vs 0.10 uniform -> weighting is clearly applied.
    assert gold > n * 0.15


def test_no_network_by_default(monkeypatch):
    _reset()
    monkeypatch.setattr(sp, "SPONSORS_URL", "")              # fixed-in-code feed is blank by default
    monkeypatch.delenv("HACKINGTOOL_NO_SPONSOR_FETCH", raising=False)

    def boom(*a, **k):
        raise AssertionError("network must not be touched when SPONSORS_URL is blank")

    monkeypatch.setattr(sp.urllib.request, "urlopen", boom)
    assert isinstance(sp.load(), list)   # no exception, no network


def test_sponsor_cta():
    assert sp.sponsor_cta() == "https://github.com/sponsors/Z4nzu"
