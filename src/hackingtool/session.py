"""tmux background-execution wrapper — Layer 2 of the operator console.

Every ``/run <tool> &`` opens a labeled window in ONE dedicated detached tmux
session (``hackingtool``), running a live shell in the tool's dir. All tmux
calls are list-form ``subprocess`` (never ``shell=True``); read/kill paths
tolerate a missing server, so the console never crashes when tmux is absent or
the session is already gone.
"""
from __future__ import annotations

import shutil
import subprocess

SESSION = "hackingtool"


def available() -> bool:
    """True if the tmux binary is on PATH."""
    return shutil.which("tmux") is not None


def enabled() -> bool:
    """True if background execution is on AND tmux is present.

    Config key ``background_runner``: ``"auto"`` → on iff tmux installed;
    ``"off"`` → always off.
    """
    from hackingtool import config
    mode = config.load().get("background_runner", "auto")
    return available() if mode == "auto" else False


def _run(args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    """Run ``tmux <args>``; never raises on non-zero rc OR a missing tmux binary."""
    try:
        return subprocess.run(
            ["tmux", *args], capture_output=capture, text=True, check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(["tmux", *args], 1, "", "tmux executable not found")


class SessionError(RuntimeError):
    """A background tmux window/session could not be created or fed its command."""


def _has_session() -> bool:
    return _run(["has-session", "-t", SESSION]).returncode == 0


def windows() -> list[tuple[int, str]]:
    """``[(index, name), …]`` for our session's windows; ``[]`` if no server/session."""
    if not available():
        return []
    res = _run(["list-windows", "-t", SESSION,
                "-F", "#{window_index}:#{window_name}"], capture=True)
    if res.returncode != 0:
        return []
    out: list[tuple[int, str]] = []
    for line in res.stdout.splitlines():
        idx, _, name = line.partition(":")
        if idx.strip().isdigit():
            out.append((int(idx), name))
    return out


def count() -> int:
    return len(windows())


def _unique_label(label: str) -> str:
    """Suffix ``-2``, ``-3``, … if a window with this name already exists."""
    taken = {name for _, name in windows()}
    if label not in taken:
        return label
    n = 2
    while f"{label}-{n}" in taken:
        n += 1
    return f"{label}-{n}"


def run(label: str, cwd: str, command: str | None = None,
        banner: str | None = None) -> str:
    """Open a labeled window running a live shell cd'd into ``cwd``.

    Creates the detached session on first use, else adds a window. Optionally
    types a one-line ``banner`` (as a ``# comment``) then ``command`` into the
    pane's shell. Returns the resolved (deduplicated) window label.
    """
    label = _unique_label(label)
    if _has_session():
        res = _run(["new-window", "-t", SESSION, "-n", label, "-c", cwd], capture=True)
    else:
        res = _run(["new-session", "-d", "-s", SESSION, "-n", label, "-c", cwd], capture=True)
    if res.returncode != 0:
        raise SessionError((res.stderr or "").strip() or "tmux could not create the window")
    target = f"{SESSION}:{label}"
    if banner:
        _run(["send-keys", "-t", target, f"# {banner}", "Enter"])
    if command:
        res = _run(["send-keys", "-t", target, command, "Enter"], capture=True)
        if res.returncode != 0:
            raise SessionError((res.stderr or "").strip() or "tmux could not deliver the command")
    return label


def attach() -> None:
    """Attach to the session (blocking); returns to the caller on detach (Ctrl-b d)."""
    if not _has_session():
        from hackingtool.core import console
        console.print("[dim]No background panes.[/dim]")
        return
    subprocess.run(["tmux", "attach", "-t", SESSION], check=False)


def kill(target: str) -> None:
    """``kill("all")`` → the whole session; else kill window ``target``. Ignore missing."""
    if target == "all":
        _run(["kill-session", "-t", SESSION])
    else:
        _run(["kill-window", "-t", f"{SESSION}:{target}"])
