import asyncio
import io

from rich.console import Console

from hackingtool import sponsors
from hackingtool.constants import REPO_WEB_URL, VERSION_DISPLAY
from hackingtool.tui import data
from hackingtool.tui.screens.main import MainScreen
from hackingtool.tui.screens.category import CategoryScreen
from hackingtool.tui.widgets.banner import SponsorBanner
from hackingtool.tui.widgets.header import Header
from textual.app import App


def _ansi(text, width=120) -> str:
    buf = io.StringIO()
    Console(file=buf, force_terminal=True, width=width).print(text)
    return buf.getvalue()


def test_logo_is_big_oneword_block_art():
    logo = SponsorBanner(42)._logo_text().plain
    lines = [l for l in logo.split("\n") if l.strip()]
    assert len(lines) == 6            # big block font, 6 rows
    assert "█" in logo               # block art, not plain letters
    assert "TOOL" not in logo         # not the stacked HACKING/TOOL split — one word


def test_tagline_product_line():
    text = SponsorBanner(42)._tagline_text().plain
    assert "pentest" in text
    assert VERSION_DISPLAY in text
    assert "42 tools" in text
    assert REPO_WEB_URL in text


def test_empty_sponsor_cta():
    # committed sponsors.yaml ships empty -> CTA empty-state line
    text = SponsorBanner(42)._sponsor_text().plain
    assert "Sponsor hackingtool" in text
    assert sponsors.sponsor_cta() in text
    assert "No sponsors yet" not in text
    assert "your name appears here" not in text


def test_featured_sponsor_shown(monkeypatch):
    s = sponsors.Sponsor("Acme Security", "https://acme.example", "Cloud pentest", "gold")
    monkeypatch.setattr(sponsors, "featured", lambda n=1: [s])
    text = SponsorBanner(10)._sponsor_text().plain
    assert "Acme Security" in text
    assert "https://acme.example" in text
    assert "Cloud pentest" in text
    # CTA still present alongside the active sponsor
    assert sponsors.sponsor_cta() in text


def test_osc8_links_rendered(monkeypatch):
    s = sponsors.Sponsor("Acme Security", "https://acme.example", "", "gold")
    monkeypatch.setattr(sponsors, "featured", lambda n=1: [s])
    b = SponsorBanner(10)
    out = _ansi(b._tagline_text()) + _ansi(b._sponsor_text())
    assert "\x1b]8;" in out
    assert "github.com/Z4nzu/hackingtool" in out
    assert "acme.example" in out


class _Host(App):
    def __init__(self, screen):
        self._screen = screen
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(self._screen)


async def _until(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def test_main_screen_uses_banner():
    async def run():
        async with _Host(MainScreen()).run_test() as pilot:
            await _until(pilot, MainScreen)
            banner = pilot.app.screen.query_one(SponsorBanner)
            assert banner.query_one("#ht-logo")
            assert banner.query_one("#ht-tagline")
            assert banner.query_one("#ht-sponsor")
    asyncio.run(run())


def test_update_notice_shown_when_newer(monkeypatch):
    from hackingtool.tui.widgets import banner as b
    from textual.widgets import Static
    monkeypatch.setattr(b.update_check, "latest_if_newer", lambda *a, **k: "9.9.9")

    async def run():
        async with _Host(MainScreen()).run_test() as pilot:
            await _until(pilot, MainScreen)
            upd = pilot.app.screen.query_one("#ht-update", Static)
            for _ in range(40):            # wait for the background thread worker
                await pilot.pause()
                if str(upd.render()).strip():
                    break
            assert "9.9.9" in str(upd.render())
    asyncio.run(run())


def test_no_update_notice_when_current(monkeypatch):
    from hackingtool.tui.widgets import banner as b
    from textual.widgets import Static
    monkeypatch.setattr(b.update_check, "latest_if_newer", lambda *a, **k: None)

    async def run():
        async with _Host(MainScreen()).run_test() as pilot:
            await _until(pilot, MainScreen)
            for _ in range(10):
                await pilot.pause()
            assert str(pilot.app.screen.query_one("#ht-update", Static).render()).strip() == ""
    asyncio.run(run())


def test_category_screen_keeps_header():
    idx = next(c.index for c in data.categories() if c.count > 0)

    async def run():
        async with _Host(CategoryScreen(idx)).run_test() as pilot:
            await _until(pilot, CategoryScreen)
            assert pilot.app.screen.query_one(Header)
    asyncio.run(run())
