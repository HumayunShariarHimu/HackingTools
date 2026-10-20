"""Catalog / registry conformance tests.

These are CI guardrails so a bad YAML entry goes red instead of shipping:
tags stay within the taxonomy, resources are well-formed, install exemplars
carry usage cheatsheets, and the menu wiring stays consistent.
"""
import textwrap

import pytest

import hackingtool.registry as registry
import hackingtool.tags as tags


# --- real catalog (the shipped YAML files) ----------------------------------

@pytest.fixture(scope="module")
def reg():
    return registry.load()


@pytest.fixture(scope="module")
def all_catalog_tools(reg):
    return [t for c in reg.categories for t in c.tools]


def test_catalog_loads_something(all_catalog_tools):
    assert all_catalog_tools, "no catalog entries loaded — check catalog/*.yaml"


def test_all_tags_within_taxonomy(all_catalog_tools):
    offenders = {
        t.TITLE: tags.unknown_tags(t.TAGS)
        for t in all_catalog_tools
        if tags.unknown_tags(t.TAGS)
    }
    assert not offenders, f"tags outside tags.TAXONOMY: {offenders}"


def test_every_tool_has_tags(all_catalog_tools):
    missing = [t.TITLE for t in all_catalog_tools if not t.TAGS]
    assert not missing, f"catalog entries with no tags: {missing}"


def test_resources_are_well_formed(all_catalog_tools):
    resources = [t for t in all_catalog_tools if t.KIND == "resource"]
    assert resources, "expected at least one resource entry"
    for r in resources:
        assert r.PROJECT_URL, f"{r.TITLE}: resource must have a url"
        assert not r.INSTALL_COMMANDS, f"{r.TITLE}: resource must not install"
        assert not r.RUN_COMMANDS, f"{r.TITLE}: resource must not run"
        assert [o[0] for o in r.OPTIONS] == ["Open link"], f"{r.TITLE}: resource collapses to Open link"
        assert r.is_installed is True, f"{r.TITLE}: resource should never read as not-installed"


def test_install_tools_have_usage(all_catalog_tools):
    """Guided-ops promise: an install entry ships a top-commands cheatsheet."""
    bare = [t.TITLE for t in all_catalog_tools if t.KIND == "install" and not t.USAGE]
    assert not bare, f"install entries missing a usage cheatsheet: {bare}"


def test_install_tools_have_an_install_method(all_catalog_tools):
    for t in all_catalog_tools:
        if t.KIND == "install":
            has = t.INSTALL_COMMANDS or t.INSTALL_URL or t.SYSTEM_PKGS
            assert has, f"{t.TITLE}: install entry declares no install method"


def test_new_category_wiring_is_consistent(reg):
    assert len(reg.new_definitions) == len(reg.new_collections)
    for (title, icon, label), coll in zip(reg.new_definitions, reg.new_collections):
        assert title == coll.TITLE
        assert coll.TOOLS, f"{title}: new category has no tools"


def test_known_entries_round_trip(all_catalog_tools):
    by_title = {t.TITLE: t for t in all_catalog_tools}
    crack = next(t for t in all_catalog_tools if "CrackStation" in t.TITLE)
    assert crack.KIND == "resource" and crack.PROJECT_URL.startswith("https://")
    hashcat = next(t for t in all_catalog_tools if "hashcat" in t.TITLE)
    assert hashcat.SYSTEM_PKGS.get("which") == "hashcat"
    assert hashcat.USAGE, "hashcat should carry a cheatsheet"


# --- install-command derivation ---------------------------------------------

def test_install_command_derivation():
    assert registry._install_commands({"apt": "nmap"}) == ["sudo apt-get install -y nmap"]
    assert registry._install_commands({"pip": "spiderfoot"}) == ["pip install --user spiderfoot"]
    assert registry._install_commands({"go": "x/y@latest"}) == ["go install -v x/y@latest"]
    assert registry._install_commands({"git": "https://h/r.git"}) == ["git clone https://h/r.git"]
    # verbatim escape hatch wins
    assert registry._install_commands({"commands": ["a", "b"]}) == ["a", "b"]
    # url is NOT turned into a blind pipe
    assert registry._install_commands({"url": "https://x/i.sh", "sha256": "abc"}) == []


# --- requirement A: adding a tool is one YAML entry, no code edits -----------

def test_overlay_enriches_existing_tool_by_title(tmp_path):
    (tmp_path / "ov.yaml").write_text(textwrap.dedent("""
        overlay:
          - title: "Existing Tool"
            tags: [recon, web]
            system_pkgs: {which: xyz}
            usage: [["scan", "xyz -a"]]
            lab_safe_notes: "be gentle"
    """))
    reg = registry.load(tmp_path)

    class _Fake:
        TITLE = "Existing Tool"
        TAGS = ["preexisting"]
        USAGE = []
        SYSTEM_PKGS = {}
        LAB_SAFE_NOTES = ""

    t = _Fake()
    applied = reg.apply_overlays([(t, "cat")])
    assert applied == ["Existing Tool"]
    assert t.USAGE == [("scan", "xyz -a")]
    assert "preexisting" in t.TAGS and "recon" in t.TAGS   # merged, not clobbered
    assert t.SYSTEM_PKGS["which"] == "xyz"
    assert t.LAB_SAFE_NOTES == "be gentle"
    # overlay-only file adds no category
    assert reg.new_definitions == []


def test_shipped_nmap_overlay_applies():
    """The real catalog overlay reaches the Python-defined NMAP tool."""
    import hackingtool.cli as h
    nmap = next(t for t, _ in h._collect_all_tools() if t.TITLE == "Network Map (nmap)")
    assert nmap.USAGE, "nmap should get a usage cheatsheet from the overlay"
    assert nmap.SYSTEM_PKGS.get("which") == "nmap"
    assert "port-scan" in nmap.TAGS


def test_adding_a_tool_is_one_yaml_entry(tmp_path):
    (tmp_path / "demo.yaml").write_text(textwrap.dedent("""
        category:
          title: "Demo Cat"
          merge_into: null
        tools:
          - title: "Brand New Tool"
            kind: install
            tags: [recon]
            description: "Added with nothing but this YAML."
            system_pkgs: {which: newtool}
            run: ["newtool --help"]
            usage: [["do the thing", "newtool --go"]]
    """))
    reg = registry.load(tmp_path)
    titles = [t.TITLE for c in reg.categories for t in c.tools]
    assert "Brand New Tool" in titles
    assert reg.new_definitions[0][0] == "Demo Cat"
