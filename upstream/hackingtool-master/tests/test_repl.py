"""Tests for the inline REPL front-end (navigation only — no tool side effects)."""
import types

from hackingtool import repl


# ── Fakes ────────────────────────────────────────────────────────────────────

def _fake_tool(title):
    t = types.SimpleNamespace(TITLE=title, opened=False)
    t.show_options = lambda: setattr(t, "opened", True)
    return t


class _Doc:
    """Minimal stand-in for a prompt_toolkit Document."""
    def __init__(self, text):
        self.text_before_cursor = text


# ── Completer ────────────────────────────────────────────────────────────────

def _complete(text, titles, tags):
    comp = repl.HTCompleter(titles, tags)
    return [c.text for c in comp.get_completions(_Doc(text), None)]


def test_completer_commands():
    # Trailing space so completing closes the menu + readies the cursor for an arg.
    out = _complete("/ta", ["Nmap"], ["web"])
    assert out == ["/tags "]


def test_history_persists_to_file(tmp_path, monkeypatch):
    """↑↓ history is backed by a FileHistory at ~/.hackingtool/history."""
    from prompt_toolkit.history import FileHistory
    from hackingtool import prompt, constants
    hist = tmp_path / "history"
    monkeypatch.setattr(constants, "USER_HISTORY_FILE", hist)
    prompt._session.cache_clear()
    try:
        session = prompt._session()
        assert isinstance(session.history, FileHistory)
        assert session.history.filename == str(hist)
    finally:
        prompt._session.cache_clear()   # don't leak the tmp-bound session


def test_completer_tool_mention():
    out = _complete("@nm", ["Nmap", "Nikto"], ["web"])
    assert "@Nmap" in out and "@Nikto" not in out


def test_completer_tag_mention():
    out = _complete("@tag:w", ["Nmap"], ["web", "wifi", "osint"])
    assert set(out) == {"@tag:web", "@tag:wifi"}


def test_completer_no_completion_after_space():
    # A bare goal ("scan the ...") must not trigger tool/command completion.
    assert _complete("scan the ", ["Nmap"], ["web"]) == []


# ── _resolve ─────────────────────────────────────────────────────────────────

def test_resolve_case_insensitive():
    tools = {"Nmap": _fake_tool("Nmap")}
    assert repl._resolve("nmap", tools) is tools["Nmap"]


def test_resolve_fuzzy():
    tools = {"Nmap": _fake_tool("Nmap")}
    assert repl._resolve("nmpa", tools) is tools["Nmap"]   # typo within 0.6 cutoff


def test_resolve_miss():
    assert repl._resolve("wireshark", {"Nmap": _fake_tool("Nmap")}) is None


# ── dispatch (via the shared surface) ────────────────────────────────────────

def test_dispatch_quit_returns_false():
    # Back-compat shim still used by test_skill; grammar now lives in prompt.
    assert repl._dispatch("/quit") is False


def test_open_mention_opens_tool():
    from hackingtool import prompt
    tool = _fake_tool("Nmap")
    prompt.open_mention("@nmap", tools_by_title={"Nmap": tool}, tag_index={})
    assert tool.opened is True


def test_run_command_opens_tool():
    from hackingtool import prompt
    tool = _fake_tool("Nmap")
    sig = prompt.dispatch("/run nmap", prompt.PromptCtx("home"))
    assert sig == prompt.Open("@nmap")
    prompt.open_mention(sig.mention, tools_by_title={"Nmap": tool}, tag_index={})
    assert tool.opened is True


def test_dispatch_free_text_recommends(monkeypatch):
    from hackingtool import prompt
    seen = {}
    import hackingtool.cli as cli
    monkeypatch.setattr(cli, "recommend_tools", lambda intent=None: seen.setdefault("intent", intent))
    prompt.dispatch("crack a wifi handshake", prompt.PromptCtx("home"))
    assert seen["intent"] == "crack a wifi handshake"


def test_dispatch_tags_lists(monkeypatch):
    from hackingtool import prompt
    called = {}
    monkeypatch.setattr(prompt, "show_all_tags", lambda idx: called.setdefault("hit", True))
    prompt.dispatch("/tags", prompt.PromptCtx("home"))
    assert called["hit"] is True


def test_find_is_completable_and_documented():
    assert "/find" in repl._COMMANDS


def test_dispatch_find_routes_to_discover_run(monkeypatch):
    from hackingtool import prompt
    import hackingtool.discover as discover
    seen = {}
    monkeypatch.setattr(discover, "run", lambda need, ctx=None: seen.setdefault("need", need))
    ctx = prompt.PromptCtx("home")
    prompt.dispatch("/find crack a hash", ctx)
    assert seen["need"] == "crack a hash"
