"""Inline REPL front-end — a claude-cli-style command surface for hackingtool.

Slice 1 of the "AI Operator Console". A prompt_toolkit prompt sits at the top of
the loop; every nested menu (``show_options``, ``_pick_tool``) stays classic rich
``input()``. They compose because output prints *between* blocking prompts — no
full-screen ``Application``, so native terminal scrollback stays free.

Grammar (see ``_dispatch``):
  ``/`` = actions you run   (``/run`` ``/search`` ``/tags`` ``/ai`` ``/help`` ``/quit``)
  ``@`` = things you name    (``@<tool>`` opens a tool, ``@tag:<t>`` filters by tag)
  bare text                  = natural-language recommend (AI1)

Everything data-facing (tool list, tag index, AI) is reused from ``cli`` as-is;
this module is navigation only. ``_run_tool`` is the single seam a tmux ``/run``
pane slots into later (pillar B).
"""
from __future__ import annotations

# Commands offered by the completer / shown in the toolbar. Kept in one place so
# the completer and /help stay in sync.
_COMMANDS = {
    "/run": "open a tool (add ' &' to run in a background tmux pane)",
    "/search": "search tools by keyword",
    "/tags": "list every tag + count",
    "/ai": "recommend tools for a goal",
    "/goal": "AI-plan & run an objective (per-step confirm)",
    "/find": "find tools for a need (catalog + GitHub)",
    "/panes": "list background panes",
    "/attach": "attach to background panes (Ctrl-b d to return)",
    "/kill": "kill a background pane (/kill <label|all>)",
    "/config": "view or change settings",
    "/update": "update system packages or hackingtool",
    "/uninstall": "remove hackingtool + its installed tools",
    "/skill": "view the operator playbook",
    "/clear": "clear the screen",
    "/help": "show help",
    "/quit": "exit hackingtool (also /exit, Ctrl-C, Ctrl-D)",
}


def _last_fragment(text: str) -> str:
    """Return the whitespace-delimited token the cursor is sitting in."""
    cut = max(text.rfind(" "), text.rfind("\t"))
    return text[cut + 1:]


class HTCompleter:
    """prompt_toolkit Completer: ``/`` → commands, ``@`` → tools, ``@tag:`` → tags.

    A custom Completer (not NestedCompleter) because completion branches on the
    lead char (``/`` vs ``@``), not on whitespace-split words.
    """

    def __init__(self, tool_titles, tag_names):
        self._titles = sorted(tool_titles)
        self._tags = sorted(tag_names)

    def get_completions(self, document, complete_event):
        from prompt_toolkit.completion import Completion

        text = document.text_before_cursor

        # `/command` — only while still typing the first word. Insert a trailing
        # space so the completed word no longer matches (menu closes) and the
        # cursor sits ready for an argument; dispatch strips it for no-arg commands.
        if text.startswith("/") and " " not in text:
            for cmd, desc in _COMMANDS.items():
                if cmd.startswith(text):
                    yield Completion(cmd + " ", start_position=-len(text),
                                     display=cmd, display_meta=desc)
            return

        frag = _last_fragment(text)
        if frag.startswith("@tag:"):
            typed = frag[len("@tag:"):].lower()
            for tag in self._tags:
                if tag.lower().startswith(typed):
                    yield Completion("@tag:" + tag, start_position=-len(frag),
                                     display=tag, display_meta="tag")
        elif frag.startswith("@"):
            typed = frag[1:].lower()
            for title in self._titles:
                if typed in title.lower():
                    yield Completion("@" + title, start_position=-len(frag),
                                     display=title, display_meta="tool")


def _resolve(name, tools_by_title):
    """Exact title, then canonical binary name (SYSTEM_PKGS['which']), then fuzzy (difflib)."""
    import difflib

    name = name.strip()
    if not name:
        return None
    lower = {t.lower(): tool for t, tool in tools_by_title.items()}
    if name.lower() in lower:
        return lower[name.lower()]
    # canonical binary alias: `@nmap` → the tool whose `which` is nmap, before fuzzy
    # matching can mis-hit (e.g. nmap/sqlmap → "NoSqlMap"). Only when unambiguous.
    canon = [tool for tool in tools_by_title.values()
             if str((getattr(tool, "SYSTEM_PKGS", None) or {}).get("which") or "").lower() == name.lower()]
    if len(canon) == 1:
        return canon[0]
    hit = difflib.get_close_matches(name.lower(), lower.keys(), n=1, cutoff=0.6)
    return lower[hit[0]] if hit else None


def _run_tool(tool):
    """Open a tool's classic menu. The single seam tmux `/run` slots into later."""
    tool.show_options()


def _open_mention(raw, tag_index, tools_by_title):
    """Handle an ``@…`` token: ``@tag:<t>`` filters, ``@<tool>`` opens."""
    import hackingtool.cli as cli
    from hackingtool.core import console

    if raw.startswith("@tag:"):
        tag = raw[len("@tag:"):].strip().lower()
        matches = cli._tools_for_tags([tag], tag_index)
        if not matches:
            console.print(f"[dim]No tools tagged '{tag}'.[/dim]")
            return
        cli._tool_table(matches, f"Tools tagged '{tag}'")
        cli._pick_tool(matches)
        return

    name = raw[1:] if raw.startswith("@") else raw
    tool = _resolve(name, tools_by_title)
    if tool is None:
        console.print(f"[dim]No tool matches '{name}'. Try /search or /tags.[/dim]")
        return
    _run_tool(tool)


def show_all_tags(tag_index):
    """Print every tag with its tool count — the visibility fix (was `t`-gated)."""
    from rich import box
    from rich.panel import Panel
    from hackingtool.core import console

    if not tag_index:
        console.print("[dim]No tags found.[/dim]")
        return
    body = "  ".join(
        f"[bold cyan]{t}[/bold cyan]([dim]{len(tag_index[t])}[/dim])"
        for t in sorted(tag_index)
    )
    console.print(Panel(
        body, title="[bold magenta] Tags [/bold magenta]",
        subtitle="[dim]open with @tag:<name>[/dim]", subtitle_align="right",
        border_style="magenta", box=box.ROUNDED, padding=(0, 2),
    ))


def show_skill():
    """Print the operator playbook (human body of OPERATOR.md) + charter version."""
    from rich.markdown import Markdown
    from hackingtool import skill
    from hackingtool.core import console

    body = skill.playbook()
    if not body:
        console.print("[dim]Operator playbook unavailable.[/dim]")
        return
    console.print(f"[bold magenta]Operator Charter v{skill.version()}[/bold magenta]")
    console.print(Markdown(body))


def _dispatch(raw, tag_index=None, tools_by_title=None):
    """Back-compat shim: the grammar now lives in ``prompt.dispatch``. Kept so
    existing callers/tests (test_skill) keep working. Returns False to quit,
    True to keep looping; opens ``@…`` mentions in place."""
    from hackingtool import prompt

    sig = prompt.dispatch(raw, prompt.PromptCtx("home"))
    if sig is prompt.QUIT:
        return False
    if isinstance(sig, prompt.Open):
        prompt.open_mention(sig.mention)
    return True


def _use_repl(force_classic: bool) -> bool:
    """REPL only on an interactive TTY with prompt_toolkit importable."""
    import sys

    if force_classic:
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import prompt_toolkit  # noqa: F401
    except ImportError:
        return False
    return True


def run_repl():
    """Launch the inline REPL over the shared input surface (prompt.read_line +
    prompt.dispatch), so home and nested tool menus share ONE line editor,
    history, and grammar. Fallback selection is the caller's job (`_use_repl`)."""
    from hackingtool import prompt
    import hackingtool.cli as cli
    from hackingtool.core import console

    console.print(cli._build_header())
    console.print(
        "[dim]Type a goal, [cyan]/[/cyan] for commands, [cyan]@[/cyan] for tools "
        "· [cyan]/help[/cyan] · [cyan]/quit[/cyan][/dim]\n"
    )

    ctx = prompt.PromptCtx("home")
    while True:
        raw = prompt.read_line(ctx)   # EOF → SystemExit(0); Ctrl-C → "" (clears line)
        sig = prompt.dispatch(raw, ctx)
        if sig is prompt.QUIT:
            break
        if isinstance(sig, prompt.Open):
            prompt.open_mention(sig.mention)
        # CONTINUE / BACK at home → keep looping.

    console.print("[bold magenta]Exiting…[/bold magenta]")
