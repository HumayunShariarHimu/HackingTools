"""Data-driven tool catalog loader.

Reads ``catalog/*.yaml`` and turns each entry into a ``HackingTool`` instance so
that **adding a tool is one YAML entry, not edits across the codebase**. Two
shapes are supported per catalog file:

    category:
      title: "Password / Hash Cracking"   # collection title
      icon:  "🔓"
      menu_label: "Hash Cracking"
      description: "..."
      merge_into: null        # null -> new top-level category
                              # "Information gathering tools" -> merge into that
    tools:
      - title: ...
        kind: install|resource
        tags: [...]                       # must be a subset of tags.TAXONOMY
        description: ...
        system_pkgs: {which: nmap, apt: nmap, brew: nmap}
        install: {apt: nmap}              # or git/pip/pipx/go/commands/url(+sha256)
        run: ["nmap"]
        usage: [["ping-sweep a subnet", "nmap -sn 10.10.10.0/24"], ...]
        lab_safe_notes: "..."
        url: "https://crackstation.net/"  # required when kind == resource

Install-via-URL is declared here now; the safe-fetch executor lands in M4, so a
url-only install prints a "not yet" notice instead of blindly piping to a shell.
"""
import webbrowser
from pathlib import Path

import yaml

from hackingtool.core import HackingTool, HackingToolsCollection

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"


def _install_commands(install: dict) -> list[str]:
    """Derive concrete install commands from a declarative install spec.

    ``commands`` is a verbatim escape hatch for multi-step installs. Otherwise a
    single package-manager key is translated. ``url`` is intentionally NOT turned
    into a command here (no blind ``curl | bash``) — the safe-fetch path is M4.
    """
    if not install:
        return []
    if install.get("commands"):
        return list(install["commands"])
    cmds: list[str] = []
    if "git" in install:
        cmds.append(f"git clone {install['git']}")
    if "apt" in install:
        cmds.append(f"sudo apt-get install -y {install['apt']}")
    if "brew" in install:
        cmds.append(f"brew install {install['brew']}")
    if "pipx" in install:
        cmds.append(f"pipx install {install['pipx']}")
    if "pip" in install:
        cmds.append(f"pip install --user {install['pip']}")
    if "go" in install:
        cmds.append(f"go install -v {install['go']}")
    return cmds


class CatalogTool(HackingTool):
    """A HackingTool built from a single YAML catalog entry."""

    def __init__(self, entry: dict):
        self.TITLE = entry["title"]
        self.DESCRIPTION = entry.get("description", "")
        self.KIND = entry.get("kind", "install")
        self.TAGS = list(entry.get("tags", []))
        self.USAGE = [tuple(u) for u in entry.get("usage", [])]
        self.SYSTEM_PKGS = entry.get("system_pkgs", {}) or {}
        self.LAB_SAFE_NOTES = entry.get("lab_safe_notes", "")
        self.PROJECT_URL = entry.get("project_url", "") or entry.get("url", "")

        install = entry.get("install", {}) or {}
        self.INSTALL_COMMANDS = _install_commands(install)
        self.INSTALL_URL = install.get("url", "")
        self.INSTALL_SHA256 = install.get("sha256", "")
        self.RUN_COMMANDS = list(entry.get("run", []) or [])

        if self.KIND == "resource":
            url = entry["url"]  # required; schema test enforces
            super().__init__(
                [("Open link", lambda u=url: webbrowser.open_new_tab(u))],
                installable=False, runnable=False,
            )
        else:
            installable = bool(self.INSTALL_COMMANDS or self.INSTALL_URL or self.SYSTEM_PKGS)
            super().__init__(installable=installable, runnable=bool(self.RUN_COMMANDS))

def _apply_overlay(tool, o: dict) -> None:
    """Set guidance fields on an existing tool instance from an overlay entry."""
    if "usage" in o:
        tool.USAGE = [tuple(u) for u in o["usage"]]
    if "tags" in o:
        tool.TAGS = list(dict.fromkeys(list(tool.TAGS or []) + list(o["tags"])))
    if "lab_safe_notes" in o:
        tool.LAB_SAFE_NOTES = o["lab_safe_notes"]
    if "system_pkgs" in o:
        tool.SYSTEM_PKGS = {**(tool.SYSTEM_PKGS or {}), **o["system_pkgs"]}


class Category:
    """One catalog file's category header + its built tools."""

    def __init__(self, header: dict, tools: list[CatalogTool]):
        self.title = header["title"]
        self.icon = header.get("icon", "•")
        self.menu_label = header.get("menu_label", self.title)
        self.description = header.get("description", "")
        self.merge_into = header.get("merge_into")  # None or an existing collection title
        self.tools = tools

    def as_collection(self) -> HackingToolsCollection:
        coll = HackingToolsCollection()
        coll.TITLE = self.title
        coll.DESCRIPTION = self.description
        coll.TOOLS = self.tools
        return coll

    @property
    def definition(self) -> tuple:
        return (self.title, self.icon, self.menu_label)


class Registry:
    def __init__(self, categories: list[Category], overlays: dict | None = None):
        self.categories = categories
        # title -> {usage, tags, lab_safe_notes, system_pkgs} for EXISTING tools
        self.overlays = overlays or {}

    def apply_overlays(self, tool_pairs) -> list[str]:
        """Enrich already-built tools (Python or catalog) by title. Returns titles hit."""
        applied = []
        for tool, _cat in tool_pairs:
            o = self.overlays.get(tool.TITLE)
            if o:
                _apply_overlay(tool, o)
                applied.append(tool.TITLE)
        return applied

    # --- new top-level categories (merge_into is None) ---
    @property
    def new_collections(self) -> list[HackingToolsCollection]:
        return [c.as_collection() for c in self.categories if not c.merge_into]

    @property
    def new_definitions(self) -> list[tuple]:
        return [c.definition for c in self.categories if not c.merge_into]

    def merge_tools_for(self, collection_title: str) -> list[CatalogTool]:
        """Tools to append into an existing (Python-defined) collection."""
        out: list[CatalogTool] = []
        for c in self.categories:
            if c.merge_into == collection_title:
                out.extend(c.tools)
        return out


# Keys that make a catalog entry executable or actionable. Stripped from
# user-dir catalogs at load: /find writes inert entries, but the loader must
# not trust that the file on disk is still what /find wrote. Enforced on the
# read side so the invariant ("GitHub-derived metadata never becomes a
# runnable command") holds end-to-end rather than depending on the writer
# alone. ``kind``/``url`` are included: a tampered {"kind": "resource", "url":
# ...} would otherwise still build an "Open link" option around an
# attacker-controlled URL.
_EXECUTABLE_KEYS = ("install", "run", "system_pkgs", "kind", "url")


def _load_file(path: Path, inert: bool = False):
    """Return (Category | None, overlays list). A file may add new tools, overlay
    existing ones by title, or both. ``inert`` strips executable keys (see
    _EXECUTABLE_KEYS) — used for user-supplied catalogs."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    header = data.get("category")
    entries = [e for e in (data.get("tools") or []) if isinstance(e, dict)]
    if inert:
        entries = [{k: v for k, v in e.items() if k not in _EXECUTABLE_KEYS}
                   for e in entries]
    tools = [CatalogTool(e) for e in entries]
    category = None
    if header or tools:
        category = Category(header or {"title": path.stem}, tools)
    overlays = data.get("overlay") or []
    return category, overlays


def load(catalog_dir: Path = CATALOG_DIR, user_dir: Path | None = None) -> Registry:
    """Load the shipped catalog, plus an optional user catalog (e.g. found.yaml).

    ``user_dir`` defaults to None (opt-in), not the live ``~/.hackingtool`` dir:
    a caller that wants it must pass it explicitly, so tests that only override
    ``catalog_dir`` stay isolated from whatever a developer has discovered
    locally with ``/find``.
    """
    if not catalog_dir.is_dir():
        return Registry([])
    cats: list[Category] = []
    overlays: dict[str, dict] = {}
    for p in sorted(catalog_dir.glob("*.yaml")):
        category, file_overlays = _load_file(p)
        if category:
            cats.append(category)
        for o in file_overlays:
            title = o["title"]
            overlays.setdefault(title, {}).update(
                {k: v for k, v in o.items() if k != "title"}
            )
    if user_dir and user_dir.is_dir():
        for p in sorted(user_dir.glob("*.yaml")):
            try:
                category, _file_overlays = _load_file(p, inert=True)
            except Exception:
                continue                  # a broken user file must never break the catalog
            if category:
                cats.append(category)
    return Registry(cats, overlays)


if __name__ == "__main__":
    reg = load()
    total = sum(len(c.tools) for c in reg.categories)
    print(f"catalog: {len(reg.categories)} files, {total} tools, "
          f"{len(reg.new_collections)} new categories")
    for c in reg.categories:
        tgt = f"-> {c.merge_into}" if c.merge_into else "(new category)"
        print(f"  {c.title} {tgt}: {len(c.tools)} tools")
