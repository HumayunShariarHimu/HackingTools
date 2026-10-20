import asyncio

from textual.app import App, ComposeResult

from hackingtool.tui.widgets.command_palette import CommandPalette, COMMANDS


class _App(App):
    picked = None

    def compose(self) -> ComposeResult:
        yield CommandPalette()

    def on_command_palette_selected(self, e: CommandPalette.Selected) -> None:
        self.picked = e.command


def _ids(pal: CommandPalette) -> list[str]:
    return [pal.get_option_at_index(i).id for i in range(pal.option_count)]


def test_empty_needle_shows_all_commands():
    pal = CommandPalette()
    opts = pal._opts("")
    assert len(opts) == len(COMMANDS) == 6
    assert "/config" in [o.id for o in opts]
    assert "/update" in [o.id for o in opts]
    assert "/search" not in [o.id for o in opts]   # type-to-filter replaces it


def test_opts_narrows_by_name():
    pal = CommandPalette()
    assert [o.id for o in pal._opts("conf")] == ["/config"]


def test_opts_narrows_by_help_text():
    pal = CommandPalette()
    assert [o.id for o in pal._opts("export")] == ["/report"]  # /report's help


def test_filter_updates_list_and_highlights_first():
    async def run():
        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            pal = app.query_one(CommandPalette)
            assert pal.option_count == len(COMMANDS)
            pal.filter("conf")
            await pilot.pause()
            assert _ids(pal) == ["/config"]
            assert pal.highlighted == 0

    asyncio.run(run())


def test_selecting_emits_selected():
    async def run():
        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            pal = app.query_one(CommandPalette)
            pal.highlighted = pal.get_option_index("/config")
            pal.action_select()   # palette is non-focusable; real UI drives it from the prompt/mouse
            await pilot.pause()
            assert app.picked == "/config"

    asyncio.run(run())
