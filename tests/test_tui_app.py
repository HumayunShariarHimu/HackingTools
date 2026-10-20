import asyncio

from textual.widgets import Input, OptionList

from hackingtool.tui.app import HackingToolApp
from hackingtool.tui.screens.main import MainScreen
from hackingtool.tui.screens.category import CategoryScreen
from hackingtool.tui.widgets.command_palette import CommandPalette


async def _until_screen(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def _prompt(app) -> Input:
    return app.screen.query_one("#ht-prompt", Input)


async def _type(pilot, text: str) -> None:
    # drive the real on_input_changed path
    _prompt(pilot.app).value = text
    await pilot.pause()


def test_boots_to_main_screen():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            assert isinstance(pilot.app.screen, MainScreen)

    asyncio.run(run())


def test_slash_opens_palette():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            assert len(pilot.app.screen.query(CommandPalette)) == 0
            await _type(pilot, "/")
            assert len(pilot.app.screen.query(CommandPalette)) == 1

    asyncio.run(run())


def test_slash_filters_palette():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/conf")
            pal = pilot.app.screen.query_one(CommandPalette)
            ids = [pal.get_option_at_index(i).id for i in range(pal.option_count)]
            assert ids == ["/config"]

    asyncio.run(run())


def test_clearing_slash_removes_palette():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/")
            assert len(pilot.app.screen.query(CommandPalette)) == 1
            await _type(pilot, "")
            assert len(pilot.app.screen.query(CommandPalette)) == 0

    asyncio.run(run())


def test_palette_quit_exits():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/quit")
            await pilot.press("enter")
            await pilot.pause()
            assert pilot.app._exit is True

    asyncio.run(run())


def test_palette_config_opens_config_screen():
    # /config now pushes a native in-TUI settings screen (no prompt_toolkit / suspend).
    from hackingtool.tui.screens.config import ConfigScreen

    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/conf")
            await pilot.press("enter")
            await _until_screen(pilot, ConfigScreen)
            assert isinstance(pilot.app.screen, ConfigScreen)

    asyncio.run(run())


def test_palette_update_opens_update_modal_and_copies():
    from hackingtool.tui.widgets.update_modal import UpdateModal

    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            copied = {}
            pilot.app.copy_to_clipboard = lambda s: copied.setdefault("cmd", s)
            await _type(pilot, "/update")
            await pilot.press("enter")
            await _until_screen(pilot, UpdateModal)
            await pilot.press("enter")          # copy detected command + close
            await _until_screen(pilot, MainScreen)
            assert copied.get("cmd")            # a command was copied
            assert isinstance(pilot.app.screen, MainScreen)

    asyncio.run(run())


def test_escape_with_palette_closes_it_and_clears_prompt():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/con")
            assert len(pilot.app.screen.query(CommandPalette)) == 1
            await pilot.press("escape")
            await pilot.pause()
            assert len(pilot.app.screen.query(CommandPalette)) == 0
            assert _prompt(pilot.app).value == ""

    asyncio.run(run())


def test_escape_without_palette_pops_category_screen():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            # enter on the highlighted category pushes a CategoryScreen
            await pilot.press("enter")
            await _until_screen(pilot, CategoryScreen)
            assert len(pilot.app.screen.query(CommandPalette)) == 0
            await pilot.press("escape")
            await _until_screen(pilot, MainScreen)
            assert isinstance(pilot.app.screen, MainScreen)

    asyncio.run(run())


def test_palette_floats_above_prompt_without_scrolling():
    async def run():
        async with HackingToolApp().run_test(size=(100, 30)) as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/")
            pal = pilot.app.screen.query_one(CommandPalette)
            prompt = _prompt(pilot.app)
            # prompt still docked at the very bottom (screen didn't grow/scroll)
            assert prompt.region.bottom == 30
            # palette sits ABOVE the prompt
            assert pal.region.bottom <= prompt.region.y
            assert pal.region.y < prompt.region.y

    asyncio.run(run())


def test_down_from_prompt_moves_list_highlight():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            assert isinstance(pilot.app.focused, Input)  # prompt is focused on mount
            ol = pilot.app.screen.query_one("#main-cats", OptionList)
            assert ol.highlighted == 0
            await pilot.press("down")
            await pilot.pause()
            # focus stays on the prompt; the list highlight advances
            assert isinstance(pilot.app.focused, Input)
            assert ol.highlighted == 1

    asyncio.run(run())


def test_down_from_prompt_moves_palette_highlight():
    async def run():
        async with HackingToolApp().run_test() as pilot:
            await _until_screen(pilot, MainScreen)
            await _type(pilot, "/")
            pal = pilot.app.screen.query_one(CommandPalette)
            assert pal.highlighted == 0
            await pilot.press("down")
            await pilot.pause()
            assert pal.highlighted == 1  # down steers the palette, not the list

    asyncio.run(run())
