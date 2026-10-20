import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Callable
from functools import lru_cache
from platform import system

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.traceback import install

from hackingtool.constants import (
    THEME_PRIMARY, THEME_BORDER, THEME_ACCENT,
    THEME_SUCCESS, THEME_ERROR, THEME_WARNING,
    THEME_DIM, THEME_ARCHIVED, THEME_URL,
)

# Enable rich tracebacks globally
install()

_theme = Theme({
    "purple":   "#7B61FF",
    "success":  THEME_SUCCESS,
    "error":    THEME_ERROR,
    "warning":  THEME_WARNING,
    "archived": THEME_ARCHIVED,
    "url":      THEME_URL,
    "dim":      THEME_DIM,
})

# Single shared console — all tool files do: from core import console
console = Console(theme=_theme)


def clear_screen():
    os.system("cls" if system() == "Windows" else "clear")


def validate_input(ip, val_range: list) -> int | None:
    """Return the integer if it is in val_range, else None."""
    if not val_range:
        return None
    try:
        ip = int(ip)
        if ip in val_range:
            return ip
    except (TypeError, ValueError):
        pass
    return None


def ask(prompt: str, default: str = "") -> str:
    """Prompt wrapper → the shared input surface. EOF (piped/closed stdin, Ctrl-D)
    or Ctrl-C cleanly quit (SystemExit) instead of crashing the menu loop, and the
    readline-backed reader kills the arrow-key escape-leak on nested menus."""
    from hackingtool import prompt as _prompt
    return _prompt.simple(prompt, default)


@lru_cache(maxsize=1)
def _cmd_logger() -> logging.Logger:
    """Append-only log of every executed command + its exit code.

    Lazy (built on first command) so importing core has no filesystem side
    effects. Path follows OS convention via platformdirs — ~/.local/state on
    Linux, ~/Library/Logs on macOS — so it ships correctly once packaged.
    """
    from pathlib import Path

    from platformdirs import user_log_dir

    log_dir = Path(user_log_dir("hackingtool"))
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hackingtool.commands")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # don't leak into root/console
    if not logger.handlers:
        handler = logging.FileHandler(log_dir / "commands.log")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
    return logger


def _run_shell(cmd: str) -> int:
    """Run a catalog/tool shell one-liner and return its real exit code.

    Catalog commands are user-chosen shell strings (with &&, pipes, redirects),
    so they legitimately need a shell — unlike code we build from untrusted input.
    Using subprocess.run captures the exit code that os.system silently dropped,
    so success/failure is reported honestly instead of always printing "✔".
    ponytail: shell=True is intentional — opt-in commands the user selected, not
    attacker input.
    """
    try:
        rc = subprocess.run(cmd, shell=True).returncode
    except KeyboardInterrupt:
        console.print("\n[warning]⚠ Interrupted.[/warning]")
        rc = 130
    _cmd_logger().info("exit=%s :: %s", rc, cmd)
    return rc


def _show_inline_help():
    """Quick help available from any menu level."""
    console.print(Panel(
        Text.assemble(
            ("  Navigation\n", "bold white"),
            ("  ─────────────────────────────────\n", "dim"),
            ("  1–N    ", "bold cyan"), ("select item\n", "white"),
            ("  97     ", "bold cyan"), ("install all (in category)\n", "white"),
            ("\n  Tool menu: Install, Run, Update, Open Folder\n", "dim"),
            ("  99     ", "bold cyan"), ("go back\n", "white"),
            ("  98     ", "bold cyan"), ("open project page / archived\n", "white"),
            ("  ?      ", "bold cyan"), ("show this help\n", "white"),
            ("  q      ", "bold cyan"), ("quit hackingtool\n", "white"),
        ),
        title="[bold magenta] ? Quick Help [/bold magenta]",
        border_style="magenta",
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    ask("[dim]Press Enter to return[/dim]", default="")


class HackingTool:
    TITLE: str              = ""
    DESCRIPTION: str        = ""
    INSTALL_COMMANDS: list[str]  = []
    UNINSTALL_COMMANDS: list[str] = []
    RUN_COMMANDS: list[str]      = []
    # Safe-fetch install (the vetted curl|bash replacement): download INSTALL_URL,
    # require + verify INSTALL_SHA256, then run INSTALL_COMMANDS with {file} → the
    # verified download. See _url_install().
    INSTALL_URL: str        = ""
    INSTALL_SHA256: str     = ""
    OPTIONS: list[tuple[str, Callable]] = []
    PROJECT_URL: str        = ""

    # OS / capability metadata
    SUPPORTED_OS: list[str] = ["linux", "macos"]
    REQUIRES_ROOT: bool     = False
    REQUIRES_WIFI: bool     = False
    REQUIRES_GO: bool       = False
    REQUIRES_RUBY: bool     = False
    REQUIRES_JAVA: bool     = False
    REQUIRES_DOCKER: bool   = False

    # Tags for search/filter (e.g. ["osint", "web", "recon", "scanner"])
    TAGS: list[str]         = []

    # Guided-operations metadata (set by the YAML catalog loader; see registry.py)
    KIND: str               = "install"        # "install" | "resource"
    USAGE: list[tuple[str, str]] = []          # [(task, command)] cheatsheet
    SYSTEM_PKGS: dict       = {}               # {which, apt, brew, ...} reuse-first hints
    LAB_SAFE_NOTES: str     = ""               # THM/CTF-safe usage guidance

    # Archived tool flags
    ARCHIVED: bool          = False
    ARCHIVED_REASON: str    = ""

    def __init__(self, options=None, installable=True, runnable=True):
        options = options or []
        if not isinstance(options, list):
            raise TypeError("options must be a list of (option_name, option_fn) tuples")
        self.OPTIONS = []
        if installable:
            self.OPTIONS.append(("Install", self.install))
        if runnable:
            self.OPTIONS.append(("Run", self.run))
        # Maintenance actions only make sense for something installed/run locally —
        # a pure resource (installable=runnable=False) collapses to its own options.
        if installable or runnable:
            self.OPTIONS.append(("Update", self.update))
            self.OPTIONS.append(("Open Folder", self.open_folder))
        self.OPTIONS.extend(options)

    @property
    def is_installed(self) -> bool:
        """Check if the tool's binary is on PATH or its clone dir exists."""
        # Resources (sites/services) are never "installed" — don't nag or count them.
        if self.KIND == "resource":
            return True
        # Reuse-first: if the catalog declares a system binary, trust PATH.
        which = (self.SYSTEM_PKGS or {}).get("which")
        if which and shutil.which(which):
            return True
        if self.RUN_COMMANDS:
            cmd = self.RUN_COMMANDS[0]
            # Handle "cd foo && binary --help" pattern
            if "&&" in cmd:
                cmd = cmd.split("&&")[-1].strip()
            if cmd.startswith("sudo "):
                cmd = cmd[5:].strip()
            binary = cmd.split()[0] if cmd else ""
            if binary and binary not in (".", "echo", "cd"):
                if shutil.which(binary):
                    return True
        # Check if git clone target dir exists
        if self.INSTALL_COMMANDS:
            for ic in self.INSTALL_COMMANDS:
                if "git clone" in ic:
                    parts = ic.split()
                    repo_url = [p for p in parts if p.startswith("http")]
                    if repo_url:
                        dirname = repo_url[0].rstrip("/").rsplit("/", 1)[-1].replace(".git", "")
                        if os.path.isdir(dirname):
                            return True
        return False

    def show_info(self):
        desc = f"[cyan]{self.DESCRIPTION}[/cyan]"
        if self.PROJECT_URL:
            desc += f"\n[url]🔗 {self.PROJECT_URL}[/url]"
        if self.ARCHIVED:
            desc += f"\n[archived]⚠ ARCHIVED: {self.ARCHIVED_REASON}[/archived]"
        console.print(Panel(
            desc,
            title=f"[{THEME_PRIMARY}]{self.TITLE}[/{THEME_PRIMARY}]",
            border_style="purple",
            box=box.DOUBLE,
        ))

        # Guided-ops: top real commands so a junior can act without reading --help.
        if self.USAGE:
            cheat = Table(title="Top commands", box=box.SIMPLE_HEAD, show_lines=False)
            cheat.add_column("What you want", style="bold yellow", no_wrap=False)
            cheat.add_column("Command", style="bold white", overflow="fold")
            for task, cmd in self.USAGE:
                cheat.add_row(task, cmd)
            console.print(cheat)

        if self.LAB_SAFE_NOTES:
            console.print(Panel(
                f"[warning]🧪 Lab-safe:[/warning] {self.LAB_SAFE_NOTES}",
                border_style="warning", box=box.ROUNDED, padding=(0, 1),
            ))

    def _ai_command(self, goal=None):
        """AI2: turn a free-text goal into a command for this tool (display only).
        ``goal`` may be pre-supplied (bare text typed at the menu → dispatch)."""
        import hackingtool.ai_command as ai_command
        if goal is None:
            goal = ask("[bold cyan]What do you want to do?[/bold cyan]",
                              default="").strip()
        else:
            goal = goal.strip()
        if not goal:
            return
        result = ai_command.build_command(self.TITLE, self.USAGE, goal)
        if result is None:
            console.print(Panel(
                "No curated command matched. See [bold]Top commands[/bold] above, "
                "or run the tool with [bold]--help[/bold]. "
                "[dim](AI leg needs HACKINGTOOL_AI_* env or a local Ollama.)[/dim]",
                border_style="warning", box=box.ROUNDED, padding=(0, 1),
            ))
            return
        source, command = result
        if source == "curated":
            console.print(Panel(f"[bold white]{command}[/bold white]",
                                title="[success]✔ Curated command[/success]",
                                border_style="success", box=box.ROUNDED))
        else:
            console.print(Panel(
                f"[bold white]{command}[/bold white]\n"
                "[warning]⚠ AI-generated — unverified. Confirm with --help before running.[/warning]",
                title="[warning]🤖 AI-generated command[/warning]",
                border_style="warning", box=box.ROUNDED))

    def show_options(self, parent=None):
        """Iterative menu loop — no recursion, no stack growth."""
        while True:
            clear_screen()
            self.show_info()

            table = Table(title="Options", box=box.SIMPLE_HEAVY)
            table.add_column("No.", style="bold cyan", justify="center")
            table.add_column("Action", style="bold yellow")

            for index, option in enumerate(self.OPTIONS):
                table.add_row(str(index + 1), option[0])

            if self.PROJECT_URL:
                table.add_row("98", "Open Project Page")
            table.add_row("99", f"Back to {parent.TITLE if parent else 'Main Menu'}")
            console.print(table)
            cmd_hint = "[dim cyan]c[/dim cyan][dim]md  " if self.USAGE else ""
            console.print(
                f"  {cmd_hint}[dim cyan]?[/dim cyan][dim]help  "
                "[/dim][dim cyan]q[/dim cyan][dim]uit  "
                "[/dim][dim cyan]99[/dim cyan][dim] back[/dim]"
            )

            from hackingtool import prompt
            ctx = prompt.PromptCtx("tool", self)
            raw = prompt.read_line(ctx).strip()
            if not raw:
                continue
            low = raw.lower()
            if low in ("?", "help"):
                _show_inline_help()
                continue
            if low in ("q", "quit", "exit"):
                raise SystemExit(0)
            if low in ("c", "cmd") and self.USAGE:
                self._ai_command()
                ask("[dim]Press Enter to continue[/dim]", default="")
                continue

            try:
                choice = int(raw)
            except ValueError:
                # Non-numeric → the shared grammar (/cmds, @tool/@tag:, bare text).
                sig = prompt.dispatch(raw, ctx)
                if sig is prompt.QUIT:
                    raise SystemExit(0)
                if sig is prompt.BACK:
                    return
                if isinstance(sig, prompt.Open):
                    # ponytail: a nested open returns here and walks back up the
                    # menu stack (shallow). True flat-jump is a Layer-2 refinement,
                    # not built now.
                    prompt.open_mention(sig.mention)
                continue

            if choice == 99:
                return
            elif choice == 98 and self.PROJECT_URL:
                self.show_project_page()
            elif 1 <= choice <= len(self.OPTIONS):
                try:
                    self.OPTIONS[choice - 1][1]()
                except Exception:
                    console.print_exception(show_locals=True)
                ask("[dim]Press Enter to continue[/dim]", default="")
            else:
                console.print("[error]⚠ Invalid option.[/error]")

    def _already_present(self) -> bool:
        """Strict reuse-first signal for skipping install: trust an explicit
        system binary (system_pkgs.which) or an existing clone dir, but NOT the
        RUN_COMMANDS interpreter heuristic (which false-positives on python3/go)."""
        which = (self.SYSTEM_PKGS or {}).get("which")
        if which and shutil.which(which):
            return True
        for ic in (self.INSTALL_COMMANDS or []):
            if "git clone" in ic:
                repo = [p for p in ic.split() if p.startswith("http")]
                if repo:
                    d = repo[0].rstrip("/").rsplit("/", 1)[-1].replace(".git", "")
                    if os.path.isdir(d):
                        return True
        return False

    def before_install(self): pass

    def _url_install(self):
        """Safe-fetch installer — the vetted curl|bash replacement.

        Download INSTALL_URL, REQUIRE a pinned INSTALL_SHA256 and verify it
        (abort on mismatch or if unpinned), then run INSTALL_COMMANDS with
        ``{file}`` substituted for the verified download. Nothing executes until
        the checksum matches, so a tampered/hijacked download can't run.
        """
        import hashlib
        import tempfile
        import urllib.request

        if not self.INSTALL_SHA256:
            console.print(
                f"[error]✘ Refusing url install for {self.TITLE}: no sha256 pinned. "
                f"Add INSTALL_SHA256 to run this safely.[/error]"
            )
            return
        console.print(f"[warning]↓ fetching {self.INSTALL_URL}[/warning]")
        try:
            with urllib.request.urlopen(self.INSTALL_URL) as resp:
                data = resp.read()
        except Exception as e:  # network / HTTP / TLS errors
            console.print(f"[error]✘ Download failed: {e}[/error]")
            return
        digest = hashlib.sha256(data).hexdigest()
        if digest.lower() != self.INSTALL_SHA256.strip().lower():
            console.print(
                "[error]✘ sha256 MISMATCH — refusing to run.[/error]\n"
                f"[dim]expected {self.INSTALL_SHA256}\n     got {digest}[/dim]"
            )
            return
        console.print(f"[success]✔ sha256 verified ({digest[:16]}…)[/success]")

        fd, path = tempfile.mkstemp(prefix="hackingtool-")
        ok = True
        try:
            os.write(fd, data)
            os.close(fd)
            os.chmod(path, 0o755)
            for cmd in (self.INSTALL_COMMANDS or ["chmod +x {file}"]):
                real = cmd.replace("{file}", path)
                console.print(f"[warning]→ {real}[/warning]")
                if _run_shell(real) != 0:
                    console.print(f"[error]✘ Command failed (exit ≠ 0): {real}[/error]")
                    ok = False
                    break
        finally:
            if os.path.exists(path):
                os.remove(path)
        console.print("[success]✔ Successfully installed![/success]" if ok else
                      "[error]✘ Install did not complete — see the error above.[/error]")

    def install(self):
        # Reuse-first: don't re-run installs (and re-clone into an existing dir)
        # when the tool is already present.
        if self._already_present():
            console.print(f"[success]✔ {self.TITLE} already present — skipping install.[/success]")
            return
        # Safe-fetch path (url + pinned sha256) takes priority over raw commands.
        if self.INSTALL_URL:
            return self._url_install()
        self.before_install()
        ok = True
        if isinstance(self.INSTALL_COMMANDS, (list, tuple)):
            for cmd in self.INSTALL_COMMANDS:
                console.print(f"[warning]→ {cmd}[/warning]")
                if _run_shell(cmd) != 0:
                    console.print(f"[error]✘ Command failed (exit ≠ 0): {cmd}[/error]")
                    ok = False
                    break  # stop the chain — later steps usually depend on this one
        if ok:
            self.after_install()
        else:
            console.print("[error]✘ Install did not complete — fix the error above and retry.[/error]")

    def after_install(self):
        console.print("[success]✔ Successfully installed![/success]")

    def before_uninstall(self) -> bool:
        return True

    def uninstall(self):
        if self.before_uninstall():
            if isinstance(self.UNINSTALL_COMMANDS, (list, tuple)):
                for cmd in self.UNINSTALL_COMMANDS:
                    console.print(f"[warning]→ {cmd}[/warning]")
                    _run_shell(cmd)
        self.after_uninstall()

    def after_uninstall(self): pass

    def update(self):
        """Smart update — detects install method and runs the right update command."""
        if not self.is_installed:
            console.print("[warning]Tool is not installed yet. Install it first.[/warning]")
            return

        updated = False
        failed = False
        for ic in (self.INSTALL_COMMANDS or []):
            if "git clone" in ic:
                # Extract repo dir name from clone command
                parts = ic.split()
                repo_urls = [p for p in parts if p.startswith("http")]
                if repo_urls:
                    dirname = repo_urls[0].rstrip("/").rsplit("/", 1)[-1].replace(".git", "")
                    if os.path.isdir(dirname):
                        console.print(f"[cyan]→ git -C {dirname} pull[/cyan]")
                        failed |= _run_shell(f"git -C {dirname} pull") != 0
                        updated = True
            elif "pip install" in ic:
                # Re-run pip install (--upgrade)
                upgrade_cmd = ic.replace("pip install", "pip install --upgrade")
                console.print(f"[cyan]→ {upgrade_cmd}[/cyan]")
                failed |= _run_shell(upgrade_cmd) != 0
                updated = True
            elif "go install" in ic:
                # Re-run go install (fetches latest)
                console.print(f"[cyan]→ {ic}[/cyan]")
                failed |= _run_shell(ic) != 0
                updated = True
            elif "gem install" in ic:
                upgrade_cmd = ic.replace("gem install", "gem update")
                console.print(f"[cyan]→ {upgrade_cmd}[/cyan]")
                failed |= _run_shell(upgrade_cmd) != 0
                updated = True

        if updated and not failed:
            console.print("[success]✔ Update complete![/success]")
        elif updated:
            console.print("[error]✘ Update ran but a command failed — see above.[/error]")
        else:
            console.print("[dim]No automatic update method available for this tool.[/dim]")

    def _get_tool_dir(self) -> str | None:
        """Find the tool's local directory — clone target, pip location, or binary path."""
        # 1. Check git clone target dir
        for ic in (self.INSTALL_COMMANDS or []):
            if "git clone" in ic:
                parts = ic.split()
                # If last arg is not a URL, it's a custom dir name
                repo_urls = [p for p in parts if p.startswith("http")]
                if repo_urls:
                    dirname = repo_urls[0].rstrip("/").rsplit("/", 1)[-1].replace(".git", "")
                    # Check custom target dir (arg after URL)
                    url_idx = parts.index(repo_urls[0])
                    if url_idx + 1 < len(parts):
                        dirname = parts[url_idx + 1]
                    if os.path.isdir(dirname):
                        return os.path.abspath(dirname)

        # 2. Check binary location via which
        if self.RUN_COMMANDS:
            cmd = self.RUN_COMMANDS[0]
            if "&&" in cmd:
                # "cd foo && bar" → check "foo"
                cd_part = cmd.split("&&")[0].strip()
                if cd_part.startswith("cd "):
                    d = cd_part[3:].strip()
                    if os.path.isdir(d):
                        return os.path.abspath(d)
            binary = cmd.split()[0] if cmd else ""
            if binary.startswith("sudo"):
                binary = cmd.split()[1] if len(cmd.split()) > 1 else ""
            path = shutil.which(binary) if binary else None
            if path:
                return os.path.dirname(os.path.realpath(path))

        return None

    def open_folder(self):
        """Open the tool's directory in a new shell so the user can work manually."""
        tool_dir = self._get_tool_dir()
        if tool_dir:
            console.print(f"[success]Opening folder: {tool_dir}[/success]")
            console.print("[dim]Type 'exit' to return to hackingtool.[/dim]")
            os.system(f'cd "{tool_dir}" && $SHELL')
        else:
            console.print("[warning]Tool directory not found.[/warning]")
            if self.PROJECT_URL:
                console.print(f"[dim]You can clone it manually:[/dim]")
                console.print(f"[cyan]  git clone {self.PROJECT_URL}.git[/cyan]")

    def before_run(self): pass

    def run(self):
        self.before_run()
        if isinstance(self.RUN_COMMANDS, (list, tuple)):
            for cmd in self.RUN_COMMANDS:
                console.print(f"[cyan]⚙ Running:[/cyan] [bold]{cmd}[/bold]")
                rc = _run_shell(cmd)
                # A non-zero exit is informational for run (tools often exit ≠ 0
                # on --help or when the user quits) — surface it, don't cry failure.
                if rc != 0:
                    console.print(f"[dim]↳ exited with code {rc}[/dim]")
        self.after_run()

    def after_run(self): pass

    def show_project_page(self):
        # Only http(s) reaches the browser. PROJECT_URL used to come solely from
        # the vetted catalog, but /find also writes it into ~/.hackingtool/found.yaml
        # from GitHub data — so a hand-edited file must not be able to hand
        # webbrowser a javascript:/file:/data: URL.
        url = (self.PROJECT_URL or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            console.print("[warning]Refusing to open a non-http(s) link.[/warning]")
            console.print(f"  {url}", markup=False)
            return
        console.print(f"[url]🌐 Opening: {url}[/url]")
        webbrowser.open_new_tab(url)


class HackingToolsCollection:
    TITLE: str       = ""
    DESCRIPTION: str = ""
    TOOLS: list      = []

    def __init__(self):
        pass

    def show_info(self):
        console.rule(f"[{THEME_PRIMARY}]{self.TITLE}[/{THEME_PRIMARY}]", style="purple")
        if self.DESCRIPTION:
            console.print(f"[italic cyan]{self.DESCRIPTION}[/italic cyan]\n")

    def _active_tools(self) -> list:
        """Return tools that are not archived and are OS-compatible."""
        from hackingtool.os_detect import CURRENT_OS
        return [
            t for t in self.TOOLS
            if not getattr(t, "ARCHIVED", False)
            and CURRENT_OS.system in getattr(t, "SUPPORTED_OS", ["linux", "macos"])
        ]

    def _archived_tools(self) -> list:
        return [t for t in self.TOOLS if getattr(t, "ARCHIVED", False)]

    def _incompatible_tools(self) -> list:
        from hackingtool.os_detect import CURRENT_OS
        return [
            t for t in self.TOOLS
            if not getattr(t, "ARCHIVED", False)
            and CURRENT_OS.system not in getattr(t, "SUPPORTED_OS", ["linux", "macos"])
        ]

    def _show_archived_tools(self):
        """Show archived tools sub-menu (option 98)."""
        archived = self._archived_tools()
        if not archived:
            console.print("[dim]No archived tools in this category.[/dim]")
            ask("[dim]Press Enter to return[/dim]", default="")
            return

        while True:
            clear_screen()
            console.rule(f"[archived]Archived Tools — {self.TITLE}[/archived]", style="yellow")

            table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_lines=True)
            table.add_column("No.", justify="center", style="bold yellow")
            table.add_column("Tool", style="dim yellow")
            table.add_column("Reason", style="dim white")

            for i, tool in enumerate(archived):
                reason = getattr(tool, "ARCHIVED_REASON", "No reason given")
                table.add_row(str(i + 1), tool.TITLE, reason)

            table.add_row("99", "Back", "")
            console.print(table)

            raw = ask("[bold yellow][?] Select[/bold yellow]", default="99")
            try:
                choice = int(raw)
            except ValueError:
                continue

            if choice == 99:
                return
            elif 1 <= choice <= len(archived):
                archived[choice - 1].show_options(parent=self)

    def show_options(self, parent=None):
        """Iterative menu loop — no recursion, no stack growth."""
        while True:
            clear_screen()
            self.show_info()

            active = self._active_tools()
            incompatible = self._incompatible_tools()
            archived = self._archived_tools()

            table = Table(title="Available Tools", box=box.SIMPLE_HEAD, show_lines=True)
            table.add_column("No.", justify="center", style="bold cyan", width=6)
            table.add_column("", width=2)  # installed indicator
            table.add_column("Tool", style="bold yellow", min_width=24)
            table.add_column("Description", style="white", overflow="fold")

            for index, tool in enumerate(active, start=1):
                desc = getattr(tool, "DESCRIPTION", "") or "—"
                desc = desc.splitlines()[0] if desc != "—" else "—"
                has_status = hasattr(tool, "is_installed")
                status = ("[green]✔[/green]" if tool.is_installed else "[dim]✘[/dim]") if has_status else ""
                table.add_row(str(index), status, tool.TITLE, desc)

            # Count not-installed tools for "Install All" label (skip sub-collections)
            not_installed = [t for t in active if hasattr(t, "is_installed") and not t.is_installed]
            if not_installed:
                table.add_row(
                    "[bold green]97[/bold green]", "",
                    f"[bold green]Install all ({len(not_installed)} not installed)[/bold green]", "",
                )
            if archived:
                table.add_row("[dim]98[/dim]", "", f"[archived]Archived tools ({len(archived)})[/archived]", "")
            if incompatible:
                console.print(f"[dim]({len(incompatible)} tools hidden — not supported on current OS)[/dim]")

            table.add_row("99", "", f"Back to {parent.TITLE if parent else 'Main Menu'}", "")
            console.print(table)
            console.print(
                "  [dim cyan]?[/dim cyan][dim]help  "
                "[/dim][dim cyan]q[/dim cyan][dim]uit  "
                "[/dim][dim cyan]99[/dim cyan][dim] back[/dim]"
            )

            raw = ask("[bold cyan]╰─>[/bold cyan]", default="").strip().lower()
            if not raw:
                continue
            if raw in ("?", "help"):
                _show_inline_help()
                continue
            if raw in ("q", "quit", "exit"):
                raise SystemExit(0)

            try:
                choice = int(raw)
            except ValueError:
                console.print("[error]⚠ Enter a number, ? for help, or q to quit.[/error]")
                continue

            if choice == 99:
                return
            elif choice == 97 and not_installed:
                console.print(Panel(
                    f"[bold]Installing {len(not_installed)} tools...[/bold]",
                    border_style="green", box=box.ROUNDED,
                ))
                for i, tool in enumerate(not_installed, start=1):
                    console.print(f"\n[bold cyan]({i}/{len(not_installed)})[/bold cyan] {tool.TITLE}")
                    try:
                        tool.install()
                    except Exception:
                        console.print(f"[error]✘ Failed: {tool.TITLE}[/error]")
                ask("\n[dim]Press Enter to continue[/dim]", default="")
            elif choice == 98 and archived:
                self._show_archived_tools()
            elif 1 <= choice <= len(active):
                try:
                    active[choice - 1].show_options(parent=self)
                except Exception:
                    console.print_exception(show_locals=True)
                    ask("[dim]Press Enter to continue[/dim]", default="")
            else:
                console.print("[error]⚠ Invalid option.[/error]")
