"""Regression tests for the TUI navigation/UX fixes (focus, left-back, hint line, stub feedback)."""
import asyncio

from textual.widgets import Input, OptionList, Static

from hackingtool.tui import data
from hackingtool.tui.app import HackingToolApp
from hackingtool.tui.screens.main import MainScreen
from hackingtool.tui.screens.category import CategoryScreen


async def _until(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def test_clicking_list_keeps_typing_on_prompt():
    # issue 4: list is not focusable, so a click can't steal focus from the prompt
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until(pilot, MainScreen)
            ol = pilot.app.screen.query_one("#main-cats", OptionList)
            assert ol.can_focus is False
            await pilot.click("#main-cats")
            await pilot.pause()
            assert isinstance(pilot.app.focused, Input)  # focus did NOT move to the list
            await pilot.press("w")
            await pilot.pause()
            assert pilot.app.screen.query_one("#ht-prompt", Input).value == "w"
    asyncio.run(run())


def test_left_arrow_goes_back_when_prompt_empty():
    # issue 2/3: ← pops the screen when the prompt is empty
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until(pilot, MainScreen)
            await pilot.press("enter")                 # open a category
            await _until(pilot, CategoryScreen)
            await pilot.press("left")
            await _until(pilot, MainScreen)
            assert isinstance(pilot.app.screen, MainScreen)
    asyncio.run(run())


def test_left_arrow_edits_text_when_prompt_has_value():
    # ← must still move the cursor (not navigate) while typing
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until(pilot, MainScreen)
            await pilot.press("enter")
            await _until(pilot, CategoryScreen)
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = "ab"
            inp.cursor_position = 2
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            assert isinstance(pilot.app.screen, CategoryScreen)  # did not go back
            assert inp.cursor_position == 1                       # cursor moved instead
    asyncio.run(run())


def test_left_arrow_does_not_pop_main_screen():
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until(pilot, MainScreen)
            await pilot.press("left")
            await pilot.pause()
            assert isinstance(pilot.app.screen, MainScreen)  # nothing to pop
    asyncio.run(run())


def test_hint_line_visible_and_context_aware():
    # issue 1/3: a real hint row (not a truncated border subtitle); shows back only when poppable
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until(pilot, MainScreen)
            main_hint = pilot.app.screen.query_one("#ht-hint", Static)
            assert "/ commands" in main_hint.content
            assert "back" not in main_hint.content          # root: no back
            await pilot.press("enter")
            await _until(pilot, CategoryScreen)
            cat_hint = pilot.app.screen.query_one("#ht-hint", Static)
            assert "← esc back" in cat_hint.content          # category: back shown
    asyncio.run(run())


def test_stub_command_notifies_instead_of_silent():
    # issue 5: /report is a Phase-2 stub -> must surface feedback, not do nothing
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until(pilot, MainScreen)
            seen = {}
            pilot.app.notify = lambda *a, **k: seen.setdefault("msg", (a, k))
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = "/report"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert "msg" in seen
            assert "/report" in seen["msg"][0][0]
    asyncio.run(run())
