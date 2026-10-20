import asyncio

from textual.app import App
from textual.widgets import OptionList, Input

from hackingtool.tui import data
from hackingtool.tui.screens.category import CategoryScreen
from hackingtool.tui.screens.tool import ToolScreen


def _cat_with_tools() -> int:
    return next(c.index for c in data.categories() if c.count > 0)


class _App(App):
    def __init__(self, idx):
        self._idx = idx
        super().__init__()

    async def on_mount(self) -> None:
        await self.push_screen(CategoryScreen(self._idx))


async def _until_screen(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def test_lists_tools():
    idx = _cat_with_tools()

    async def run():
        async with _App(idx).run_test() as pilot:
            await _until_screen(pilot, CategoryScreen)
            ol = pilot.app.screen.query_one("#cat-tools", OptionList)
            assert ol.option_count > 0

    asyncio.run(run())


def test_filter_narrows_list():
    idx = _cat_with_tools()
    rows = data.tools_in(idx)
    needle = rows[0].title[:3]
    expected = sum(1 for r in rows if needle.lower() in r.title.lower())

    async def run():
        async with _App(idx).run_test() as pilot:
            await _until_screen(pilot, CategoryScreen)
            ol = pilot.app.screen.query_one("#cat-tools", OptionList)
            original = ol.option_count
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = needle
            await pilot.pause()
            assert ol.option_count == expected
            assert 0 < ol.option_count <= original

    asyncio.run(run())


def test_enter_on_prompt_pushes_tool_screen():
    idx = _cat_with_tools()

    async def run():
        async with _App(idx).run_test() as pilot:
            await _until_screen(pilot, CategoryScreen)
            assert isinstance(pilot.app.focused, Input)  # prompt focused on mount
            await pilot.press("enter")
            await _until_screen(pilot, ToolScreen)
            assert isinstance(pilot.app.screen, ToolScreen)

    asyncio.run(run())
