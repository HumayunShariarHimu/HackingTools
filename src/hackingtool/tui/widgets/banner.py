"""Compact header for the MAIN screen: boxed wordmark + product line + sponsor/CTA."""
from rich.text import Text
from textual import work
from textual.containers import Vertical
from textual.widgets import Static

from hackingtool import sponsors, update_check
from hackingtool.constants import REPO_WEB_URL, VERSION_DISPLAY
from hackingtool.tui import glyphs

# Big block wordmark (ANSI Shadow, pyfiglet) — "HACKINGTOOL" on one row of letters.
# The box is a CSS border (#ht-logo), not chars. Twin of cli._BANNER_ART (which stacks it).
_LOGO = "\n".join([
    "██╗  ██╗ █████╗  ██████╗██╗  ██╗██╗███╗   ██╗ ██████╗████████╗ ██████╗  ██████╗ ██╗",
    "██║  ██║██╔══██╗██╔════╝██║ ██╔╝██║████╗  ██║██╔════╝╚══██╔══╝██╔═══██╗██╔═══██╗██║",
    "███████║███████║██║     █████╔╝ ██║██╔██╗ ██║██║  ███╗  ██║   ██║   ██║██║   ██║██║",
    "██╔══██║██╔══██║██║     ██╔═██╗ ██║██║╚██╗██║██║   ██║  ██║   ██║   ██║██║   ██║██║",
    "██║  ██║██║  ██║╚██████╗██║  ██╗██║██║ ╚████║╚██████╔╝  ██║   ╚██████╔╝╚██████╔╝███████╗",
    "╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝",
])


class SponsorBanner(Vertical):
    """Boxed wordmark + product line + sponsor CTA for the main screen. (claude-header)"""

    def __init__(self, tool_count: int):
        self._count = tool_count
        super().__init__(id="ht-banner")

    def compose(self):
        yield Static(self._logo_text(), id="ht-logo", markup=False)
        yield Static(self._tagline_text(), id="ht-tagline", markup=False)
        yield Static(self._sponsor_text(), id="ht-sponsor", markup=False)
        yield Static("", id="ht-update", markup=False)   # filled iff a newer release exists

    def on_mount(self) -> None:
        self._check_update()   # background: never blocks first render on the network

    @work(thread=True, exit_on_error=False)
    def _check_update(self) -> None:
        newer = update_check.latest_if_newer()   # cached daily, offline-safe, opt-out honored
        if newer:
            self.app.call_from_thread(self._show_update, newer)

    def _show_update(self, newer: str) -> None:
        url = f"{REPO_WEB_URL}/releases"
        t = Text(f" {glyphs.STATUS} update available: v{newer} "
                 f"(you have {VERSION_DISPLAY}) · type /update · ", style="bold yellow")
        t.append(url, style=f"yellow link {url}")
        self.query_one("#ht-update", Static).update(t)

    def _logo_text(self) -> Text:
        return Text(_LOGO, style="bold bright_green")

    def _tagline_text(self) -> Text:
        t = Text(f" All-in-One pentest toolkit · {VERSION_DISPLAY} · "
                 f"{self._count} tools · ")
        t.append(f"{glyphs.STATUS} ready", style="bold yellow")
        t.append(" · ")
        t.append(REPO_WEB_URL, style=f"dim link {REPO_WEB_URL}")
        return t

    def _sponsor_text(self) -> Text:
        cta = sponsors.sponsor_cta()
        try:
            featured = sponsors.featured(1)
        except Exception:
            featured = []
        t = Text()
        if featured:
            s = featured[0]
            t.append(f" {glyphs.STATUS} Sponsored by ", style="bold")
            t.append(f"{s.name} → {s.url}", style=f"bold cyan link {s.url}")
            if s.tagline:
                t.append(f" · {s.tagline}", style="dim")
            t.append(" · ✦ Sponsor hackingtool → ", style="dim")
            t.append(cta, style=f"dim link {cta}")
        else:
            t.append(" ✦ Sponsor hackingtool · prime placement, seen every launch → ",
                     style="dim")
            t.append(cta, style=f"dim link {cta}")
        return t
