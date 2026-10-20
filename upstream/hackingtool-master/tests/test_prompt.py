"""Tests for the shared input surface (offline — no TTY, no model)."""
import types

from hackingtool import prompt
from hackingtool.prompt import PromptCtx, CONTINUE, QUIT, BACK, Open


def _fake_tool(title):
    t = types.SimpleNamespace(TITLE=title, opened=False, goal=None)
    t.show_options = lambda: setattr(t, "opened", True)
    t._ai_command = lambda goal=None: setattr(t, "goal", goal)
    return t


# ── dispatch: global commands ────────────────────────────────────────────────

def test_dispatch_quit():
    assert prompt.dispatch("/quit", PromptCtx("home")) is QUIT


def test_bare_quit_and_exit_quit():
    # Shell muscle-memory verbs exit without a slash.
    assert prompt.dispatch("quit", PromptCtx("home")) is QUIT
    assert prompt.dispatch("exit", PromptCtx("home")) is QUIT
    assert prompt.dispatch("/exit", PromptCtx("home")) is QUIT


def test_clear_slash_and_bare(monkeypatch):
    hits = []
    monkeypatch.setattr(prompt, "_clear", lambda ctx: hits.append(ctx.mode))
    assert prompt.dispatch("/clear", PromptCtx("home")) is CONTINUE
    assert prompt.dispatch("clear", PromptCtx("home")) is CONTINUE
    assert hits == ["home", "home"]


def test_uninstall_and_update_open_manager(monkeypatch):
    opened = []
    monkeypatch.setattr(prompt, "_open_manager", lambda which: opened.append(which))
    assert prompt.dispatch("/uninstall", PromptCtx("home")) is CONTINUE
    assert prompt.dispatch("/remove", PromptCtx("home")) is CONTINUE
    assert prompt.dispatch("/update", PromptCtx("home")) is CONTINUE
    assert opened == ["uninstall", "uninstall", "update"]


def test_dispatch_back():
    assert prompt.dispatch("/back", PromptCtx("tool", _fake_tool("Nmap"))) is BACK


def test_dispatch_empty_is_continue():
    assert prompt.dispatch("   ", PromptCtx("home")) is CONTINUE


def test_dispatch_tags_lists_and_continues(monkeypatch):
    called = {}
    monkeypatch.setattr(prompt, "show_all_tags", lambda idx: called.setdefault("hit", True))
    assert prompt.dispatch("/tags", PromptCtx("home")) is CONTINUE
    assert called["hit"] is True


# ── dispatch: mentions → Open(raw) ───────────────────────────────────────────

def test_dispatch_tool_mention_returns_open():
    assert prompt.dispatch("@nmap", PromptCtx("home")) == Open("@nmap")


def test_dispatch_tag_mention_returns_open():
    assert prompt.dispatch("@tag:web", PromptCtx("home")) == Open("@tag:web")


# ── dispatch: bare text is context-aware ─────────────────────────────────────

def test_bare_text_home_calls_ai1(monkeypatch):
    seen = {}
    import hackingtool.cli as cli
    monkeypatch.setattr(cli, "recommend_tools", lambda intent=None: seen.setdefault("i", intent))
    assert prompt.dispatch("crack a wifi handshake", PromptCtx("home")) is CONTINUE
    assert seen["i"] == "crack a wifi handshake"


def test_bare_text_in_tool_calls_ai2():
    tool = _fake_tool("Nmap")
    assert prompt.dispatch("scan for open ports", PromptCtx("tool", tool)) is CONTINUE
    assert tool.goal == "scan for open ports"


# ── open_mention: injectable, actually opens ─────────────────────────────────

def test_open_mention_opens_injected_tool():
    tool = _fake_tool("Nmap")
    prompt.open_mention("@nmap", tools_by_title={"Nmap": tool}, tag_index={})
    assert tool.opened is True


# ── status line ──────────────────────────────────────────────────────────────

def test_status_home_has_breadcrumb_and_counts():
    s = prompt.status(PromptCtx("home"))
    assert "home" in s and "tools" in s and "tags" in s


def test_status_tool_uses_tool_title():
    s = prompt.status(PromptCtx("tool", _fake_tool("Nmap")))
    assert "Nmap" in s


# ── simple: readline fallback, no escape leak ────────────────────────────────

def test_simple_reads_line(monkeypatch):
    monkeypatch.setattr(prompt, "FORCE_CLASSIC", True)
    monkeypatch.setattr("builtins.input", lambda *_: "hello")
    assert prompt.simple("q: ") == "hello"


def test_simple_eof_exits(monkeypatch):
    monkeypatch.setattr(prompt, "FORCE_CLASSIC", True)
    def _eof(*_):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)
    try:
        prompt.simple("q: ")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


# ── /run &, /panes, /attach, /kill, /config, live status ────────────────────

class _FakeTool:
    TITLE = "Nmap"
    USAGE = []
    def _get_tool_dir(self):
        return "/tools/nmap"


def test_run_background_when_enabled(monkeypatch):
    from hackingtool import prompt, session, repl
    rec = {}
    monkeypatch.setattr(session, "enabled", lambda: True)

    def fake_run(label, cwd, command=None, banner=None):
        rec["args"] = (label, cwd, command)
        return label

    monkeypatch.setattr(session, "run", fake_run)
    monkeypatch.setattr(prompt, "_catalog", lambda: ({"Nmap": _FakeTool()}, {}))
    monkeypatch.setattr(repl, "_resolve", lambda name, tbt: _FakeTool())
    sig = prompt.dispatch("/run nmap -sV h &", prompt.PromptCtx("home"))
    assert sig is prompt.CONTINUE
    assert rec["args"] == ("nmap", "/tools/nmap", "nmap -sV h")


def test_run_bare_tool_background_no_command(monkeypatch):
    from hackingtool import prompt, session, repl
    rec = {}
    monkeypatch.setattr(session, "enabled", lambda: True)
    monkeypatch.setattr(session, "run",
                        lambda label, cwd, command=None, banner=None:
                        rec.setdefault("cmd", command) or label)
    monkeypatch.setattr(prompt, "_catalog", lambda: ({"Nmap": _FakeTool()}, {}))
    monkeypatch.setattr(repl, "_resolve", lambda name, tbt: _FakeTool())
    prompt.dispatch("/run nmap &", prompt.PromptCtx("home"))
    assert rec["cmd"] is None


def test_run_background_falls_back_when_disabled(monkeypatch):
    from hackingtool import prompt, session
    monkeypatch.setattr(session, "enabled", lambda: False)
    assert prompt.dispatch("/run nmap &", prompt.PromptCtx("home")) == prompt.Open("@nmap")


def test_run_background_with_args_falls_back_to_tool_token(monkeypatch):
    from hackingtool import prompt, session
    monkeypatch.setattr(session, "enabled", lambda: False)
    sig = prompt.dispatch("/run nmap -sV host &", prompt.PromptCtx("home"))
    assert sig == prompt.Open("@nmap")     # tool token only, not the full arg string


def test_panes_routes(monkeypatch):
    from hackingtool import prompt, session
    called = {}
    monkeypatch.setattr(session, "windows", lambda: called.setdefault("w", True) and [])
    assert prompt.dispatch("/panes", prompt.PromptCtx("home")) is prompt.CONTINUE
    assert called["w"]


def test_attach_routes(monkeypatch):
    from hackingtool import prompt, session
    called = {}
    monkeypatch.setattr(session, "attach", lambda: called.setdefault("a", True))
    prompt.dispatch("/attach", prompt.PromptCtx("home"))
    assert called["a"]


def test_kill_routes(monkeypatch):
    from hackingtool import prompt, session
    killed = {}
    monkeypatch.setattr(session, "kill", lambda t: killed.setdefault("t", t))
    prompt.dispatch("/kill nmap", prompt.PromptCtx("home"))
    assert killed["t"] == "nmap"


def test_config_routes(monkeypatch):
    from hackingtool import prompt
    import hackingtool.cli as cli
    got = {}
    monkeypatch.setattr(cli, "config_command", lambda arg="": got.setdefault("arg", arg))
    prompt.dispatch("/config background_runner off", prompt.PromptCtx("home"))
    assert got["arg"] == "background_runner off"


def test_status_shows_running(monkeypatch):
    from hackingtool import prompt, session
    monkeypatch.setattr(session, "enabled", lambda: True)
    monkeypatch.setattr(session, "count", lambda: 3)
    prompt._RUNNING_CACHE["at"] = 0.0     # bust the TTL cache
    assert "▶ 3 running" in prompt.status(prompt.PromptCtx("home"))
