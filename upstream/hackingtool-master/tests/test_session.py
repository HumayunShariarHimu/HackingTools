import subprocess

import pytest

from hackingtool import session


class _Rec:
    """Records tmux argv; returns a scripted CompletedProcess."""
    def __init__(self):
        self.calls = []
        self.returncode = 0
        self.stdout = ""

    def __call__(self, args, capture_output=False, text=True, check=False):
        args_list = list(args)
        # Record just the tmux argv (strip "tmux" prefix)
        if args_list and args_list[0] == "tmux":
            args_list = args_list[1:]
        self.calls.append(args_list)
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


@pytest.fixture
def rec(monkeypatch):
    r = _Rec()
    monkeypatch.setattr(session.subprocess, "run", r)
    return r


def test_available_true(monkeypatch):
    monkeypatch.setattr(session.shutil, "which", lambda _: "/usr/bin/tmux")
    assert session.available() is True


def test_available_false(monkeypatch):
    monkeypatch.setattr(session.shutil, "which", lambda _: None)
    assert session.available() is False


def test_enabled_auto_present(monkeypatch):
    from hackingtool import config
    monkeypatch.setattr(session, "available", lambda: True)
    monkeypatch.setattr(config, "load", lambda: {"background_runner": "auto"})
    assert session.enabled() is True


def test_enabled_auto_absent(monkeypatch):
    from hackingtool import config
    monkeypatch.setattr(session, "available", lambda: False)
    monkeypatch.setattr(config, "load", lambda: {"background_runner": "auto"})
    assert session.enabled() is False


def test_enabled_off(monkeypatch):
    from hackingtool import config
    monkeypatch.setattr(session, "available", lambda: True)
    monkeypatch.setattr(config, "load", lambda: {"background_runner": "off"})
    assert session.enabled() is False


def test_run_creates_session_when_absent(rec, monkeypatch):
    monkeypatch.setattr(session, "_has_session", lambda: False)
    monkeypatch.setattr(session, "windows", lambda: [])
    label = session.run("nmap", "/tools/nmap", command="nmap -sV h", banner="scan")
    assert label == "nmap"
    assert ["new-session", "-d", "-s", "hackingtool", "-n", "nmap",
            "-c", "/tools/nmap"] in rec.calls
    assert ["send-keys", "-t", "hackingtool:nmap", "# scan", "Enter"] in rec.calls
    assert ["send-keys", "-t", "hackingtool:nmap", "nmap -sV h", "Enter"] in rec.calls


def test_run_adds_window_when_present(rec, monkeypatch):
    monkeypatch.setattr(session, "_has_session", lambda: True)
    monkeypatch.setattr(session, "windows", lambda: [])
    session.run("nuclei", "/tools/nuclei")
    assert ["new-window", "-t", "hackingtool", "-n", "nuclei",
            "-c", "/tools/nuclei"] in rec.calls
    # bare tool (no command) → no command send-keys
    assert not any(c[:1] == ["send-keys"] and c[-2] == "nuclei" for c in rec.calls)


def test_run_dedups_label(rec, monkeypatch):
    monkeypatch.setattr(session, "_has_session", lambda: True)
    monkeypatch.setattr(session, "windows", lambda: [(0, "nmap")])
    assert session.run("nmap", "/tools/nmap") == "nmap-2"


def test_windows_parses(monkeypatch):
    monkeypatch.setattr(session, "available", lambda: True)

    def fake_run(args, capture_output=False, text=True, check=False):
        return subprocess.CompletedProcess(args, 0, "0:nmap\n1:nuclei\n", "")

    monkeypatch.setattr(session.subprocess, "run", fake_run)
    assert session.windows() == [(0, "nmap"), (1, "nuclei")]


def test_windows_no_server(monkeypatch):
    monkeypatch.setattr(session, "available", lambda: True)

    def fake_run(args, capture_output=False, text=True, check=False):
        return subprocess.CompletedProcess(args, 1, "", "no server running")

    monkeypatch.setattr(session.subprocess, "run", fake_run)
    assert session.windows() == []


def test_windows_absent_tmux(monkeypatch):
    monkeypatch.setattr(session, "available", lambda: False)
    assert session.windows() == []


def test_kill_all(rec):
    session.kill("all")
    assert ["kill-session", "-t", "hackingtool"] in rec.calls


def test_kill_window(rec):
    session.kill("nmap")
    assert ["kill-window", "-t", "hackingtool:nmap"] in rec.calls


def test_no_crash_when_tmux_binary_missing(monkeypatch):
    """Verify session functions degrade gracefully when tmux binary is absent."""
    import pytest
    def boom(*a, **k):
        raise FileNotFoundError("tmux")
    monkeypatch.setattr(session.subprocess, "run", boom)
    monkeypatch.setattr(session, "windows", lambda: [])
    # cleanup helpers still degrade silently
    session.kill("nmap")
    session.kill("all")
    # run() now SIGNALS the failure (caller reports it) instead of pretending it started
    with pytest.raises(session.SessionError):
        session.run("x", "/tmp")
