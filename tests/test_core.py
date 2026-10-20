"""Engine-honesty checks for core.py (M4): exit-code capture, reuse-first skip,
honest success/failure, and EOF-safe prompting."""
import pytest

import hackingtool.core as core


def _tool(cmds):
    t = core.HackingTool(installable=True, runnable=False)
    t.TITLE = "T"
    t.INSTALL_COMMANDS = cmds
    t.SYSTEM_PKGS = {}
    return t


def test_install_stops_on_failure_and_is_honest(monkeypatch):
    run = []
    codes = {"a": 0, "b": 1, "c": 0}
    monkeypatch.setattr(core, "_run_shell", lambda c: run.append(c) or codes[c])
    t = _tool(["a", "b", "c"])
    after = []
    monkeypatch.setattr(t, "after_install", lambda: after.append(1))
    t.install()
    assert run == ["a", "b"]      # stopped at the first failing command
    assert after == []            # did NOT claim success on failure


def test_install_success_calls_after(monkeypatch):
    run = []
    monkeypatch.setattr(core, "_run_shell", lambda c: run.append(c) or 0)
    t = _tool(["a", "b"])
    after = []
    monkeypatch.setattr(t, "after_install", lambda: after.append(1))
    t.install()
    assert run == ["a", "b"]
    assert after == [1]


def test_reuse_first_skips_install(monkeypatch):
    ran = []
    monkeypatch.setattr(core, "_run_shell", lambda c: ran.append(c) or 0)
    t = _tool(["git clone https://x/y.git"])
    monkeypatch.setattr(t, "_already_present", lambda: True)
    t.install()
    assert ran == []             # already present → nothing executed


def test_already_present_uses_which_not_interpreter(monkeypatch):
    # A python3-launched tool must NOT read as present just because python3 is on PATH.
    t = _tool(["git clone https://x/notcloned.git"])
    t.RUN_COMMANDS = ["python3 main.py"]
    monkeypatch.setattr(core.shutil, "which", lambda b: "/usr/bin/python3")
    assert t._already_present() is False
    # But an explicit system binary is trusted.
    t.SYSTEM_PKGS = {"which": "nmap"}
    assert t._already_present() is True


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._d


def _url_tool(sha, cmds=None):
    t = core.HackingTool(installable=True, runnable=False)
    t.TITLE = "U"
    t.INSTALL_URL = "https://x/bin"
    t.INSTALL_SHA256 = sha
    t.INSTALL_COMMANDS = cmds if cmds is not None else []
    t.SYSTEM_PKGS = {}
    return t


def test_url_install_refuses_when_unpinned(monkeypatch):
    ran = []
    monkeypatch.setattr(core, "_run_shell", lambda c: ran.append(c) or 0)
    monkeypatch.setattr("urllib.request.urlopen", lambda u: _FakeResp(b"data"))
    _url_tool("").install()
    assert ran == []             # no sha256 → nothing runs


def test_url_install_refuses_on_mismatch(monkeypatch):
    ran = []
    monkeypatch.setattr(core, "_run_shell", lambda c: ran.append(c) or 0)
    monkeypatch.setattr("urllib.request.urlopen", lambda u: _FakeResp(b"data"))
    _url_tool("deadbeef" * 8).install()   # 64-hex but wrong
    assert ran == []             # checksum mismatch → nothing runs


def test_url_install_runs_on_match_with_substitution(monkeypatch):
    import hashlib
    data = b"payload"
    good = hashlib.sha256(data).hexdigest()
    ran = []
    monkeypatch.setattr(core, "_run_shell", lambda c: ran.append(c) or 0)
    monkeypatch.setattr("urllib.request.urlopen", lambda u: _FakeResp(data))
    _url_tool(good, ["chmod +x {file}", "mv {file} /dest"]).install()
    assert len(ran) == 2
    assert all("{file}" not in c for c in ran)          # placeholder substituted
    assert ran[0].startswith("chmod +x /") and ran[1].endswith("/dest")


def test_run_shell_logs_command_and_exit_code(monkeypatch):
    logged = []
    fake = type("L", (), {"info": lambda self, m, *a: logged.append(m % a)})()
    monkeypatch.setattr(core, "_cmd_logger", lambda: fake)
    assert core._run_shell("exit 3") == 3
    assert logged == ["exit=3 :: exit 3"]


def test_ask_quits_on_eof(monkeypatch):
    # ask now delegates to prompt.simple, which reads via input(); EOF still
    # cleanly quits (SystemExit) instead of crashing the menu loop.
    def boom(*a, **k):
        raise EOFError()
    monkeypatch.setattr("builtins.input", boom)
    with pytest.raises(SystemExit):
        core.ask("prompt")


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "file:///etc/passwd", "data:text/html,<script>",
    "ftp://example.com", "  javascript:alert(1)",
])
def test_project_page_refuses_non_http_urls(monkeypatch, url):
    """PROJECT_URL used to come only from the vetted catalog; /find now also
    writes it into ~/.hackingtool/found.yaml from GitHub data, so a hand-edited
    file must not be able to hand webbrowser a javascript:/file:/data: URL."""
    opened = []
    monkeypatch.setattr(core.webbrowser, "open_new_tab", opened.append)
    t = core.HackingTool(installable=False, runnable=False)
    t.TITLE = "T"
    t.PROJECT_URL = url
    t.show_project_page()
    assert opened == [], f"{url!r} must never reach the browser"


def test_project_page_still_opens_normal_links(monkeypatch):
    opened = []
    monkeypatch.setattr(core.webbrowser, "open_new_tab", opened.append)
    t = core.HackingTool(installable=False, runnable=False)
    t.TITLE = "T"
    t.PROJECT_URL = "https://github.com/ffuf/ffuf"
    t.show_project_page()
    assert opened == ["https://github.com/ffuf/ffuf"]
