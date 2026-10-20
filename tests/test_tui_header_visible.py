import asyncio

from textual.app import App

from hackingtool.tui import data
from hackingtool.tui.data import ToolRow
from hackingtool.tui.screens.main import MainScreen
from hackingtool.tui.screens.category import CategoryScreen
from hackingtool.tui.screens.tool import ToolScreen
from hackingtool.tui.widgets.header import Header
from hackingtool.tui.widgets.banner import SponsorBanner


class _Fake:
    def run(self):
        pass


def _cat_with_tools() -> int:
    return next(c.index for c in data.categories() if c.count > 0)


def _tool_row() -> ToolRow:
    return ToolRow(index=0, title="Sublist3r", description="Enumerate subdomains",
                   url="", installed=True, obj=_Fake())


class _Host(App):
    def __init__(self, screen):
        self._screen = screen
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(self._screen)


async def _until_screen(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def _assert_header(screen_factory, kind):
    async def run():
        async with _Host(screen_factory()).run_test() as pilot:
            await _until_screen(pilot, kind)
            header = pilot.app.screen.query_one(Header)
            assert "hackingtool" in header.render().plain

    asyncio.run(run())


def test_main_screen_header_visible():
    # MainScreen swaps the thin Header for the richer SponsorBanner.
    async def run():
        async with _Host(MainScreen()).run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            banner = pilot.app.screen.query_one(SponsorBanner)
            assert "pentest" in banner.query_one("#ht-tagline").content.plain

    asyncio.run(run())


def test_category_screen_header_visible():
    idx = _cat_with_tools()
    _assert_header(lambda: CategoryScreen(idx), CategoryScreen)


def test_tool_screen_header_visible():
    _assert_header(lambda: ToolScreen(_tool_row()), ToolScreen)
