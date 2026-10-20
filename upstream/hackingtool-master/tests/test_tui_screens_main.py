import asyncio

from textual.app import App
from textual.widgets import OptionList, Input

from hackingtool.tui import data
from hackingtool.tui.screens.main import MainScreen
from hackingtool.tui.screens.category import CategoryScreen
from hackingtool.tui.screens.tool import ToolScreen
from hackingtool.tui.widgets import banner


class _App(App):
    async def on_mount(self) -> None:
        await self.push_screen(MainScreen())


async def _until_screen(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def test_lists_all_categories():
    async def run():
        async with _App().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            ol = pilot.app.screen.query_one("#main-cats", OptionList)
            assert ol.option_count == len(data.categories())

    asyncio.run(run())


def test_typing_searches_all_tools_globally():
    # Main-screen typing is a global tool search (reaches tools inside submenus),
    # not a category filter. Rows become tool hits (id "t:cat:tool").
    needle = "sql"
    expected = len(data.search_tools(needle))

    async def run():
        async with _App().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            ol = pilot.app.screen.query_one("#main-cats", OptionList)
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = needle
            await pilot.pause()
            assert expected > 0
            assert ol.option_count == expected
            assert ol.get_option_at_index(0).id.startswith("t:")
            # clearing returns to the category list
            inp.value = ""
            await pilot.pause()
            assert ol.option_count == len(data.categories())

    asyncio.run(run())


def test_enter_on_prompt_pushes_category_screen():
    # Prompt is focused and row 0 highlighted on mount; Enter opens it.
    async def run():
        async with _App().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            assert isinstance(pilot.app.focused, Input)
            await pilot.press("enter")
            await _until_screen(pilot, CategoryScreen)
            assert isinstance(pilot.app.screen, CategoryScreen)

    asyncio.run(run())


def test_enter_on_global_search_hit_opens_tool():
    async def run():
        async with _App().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = "sql"
            await pilot.pause()
            await pilot.press("enter")
            await _until_screen(pilot, ToolScreen)
            assert isinstance(pilot.app.screen, ToolScreen)

    asyncio.run(run())


def test_prompt_docked_bottom_list_fills_middle(monkeypatch):
    # Header pinned top, list in the middle, prompt pinned bottom: the screen
    # tiles instead of scrolling as a page. Verified at a short height.
    # No update line (it arrives async and re-lays-out the banner mid-assert).
    monkeypatch.setattr(banner.update_check, "latest_if_newer", lambda *a, **k: None)

    async def run():
        async with _App().run_test(size=(80, 20)) as pilot:
            await _until_screen(pilot, MainScreen)
            await pilot.pause()
            await pilot.pause()
            scr = pilot.app.screen
            prompt = scr.query_one("#ht-prompt", Input)
            ol = scr.query_one("#main-cats", OptionList)
            assert not scr.query("#main-filter")  # no top filter box
            assert prompt.region.y > ol.region.y  # prompt below the list
            assert prompt.region.y + prompt.region.height == scr.size.height

    asyncio.run(run())


def test_down_on_prompt_moves_list_highlight():
    async def run():
        async with _App().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            ol = pilot.app.screen.query_one("#main-cats", OptionList)
            assert ol.highlighted == 0
            await pilot.press("down")
            await pilot.pause()
            assert ol.highlighted == 1

    asyncio.run(run())
