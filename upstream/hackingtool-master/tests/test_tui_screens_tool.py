import asyncio
import contextlib

from textual.app import App
from textual.widgets import OptionList

from hackingtool.tui.data import ToolRow
from hackingtool.tui.screens.tool import ToolScreen
from hackingtool.tui.widgets.permission import PermissionModal


class _Fake:
    ran = False

    def run(self):
        self.ran = True


def _row():
    return ToolRow(index=0, title="Sublist3r", description="Enumerate subdomains",
                   url="", installed=True, obj=_Fake())


class _App(App):
    def __init__(self, row):
        self._row = row
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(ToolScreen(self._row))


async def _until_screen(pilot, kind):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, kind):
            return
    raise AssertionError(f"{kind.__name__} never appeared")


def test_structure_option_ids():
    async def run():
        async with _App(_row()).run_test() as pilot:
            await _until_screen(pilot, ToolScreen)
            ol = pilot.app.screen.query_one("#tool-actions", OptionList)
            ids = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            assert set(ids) == {"run", "install", "open", "uninstall", "back"}

    asyncio.run(run())


def test_permission_gate_runs_fn():
    # HeadlessDriver.can_suspend is False, so real App.suspend() raises
    # SuspendNotSupported under run_test(); override it with a no-op so fn() still
    # fires. Production code keeps the real suspend() to give tools a TTY.
    # PermissionModal highlights "Yes" (index 0) on mount with nothing pre-pressed,
    # so a single "enter" presses it → "yes" and proceeds past the gate.
    row = _row()

    async def run():
        async with _App(row).run_test() as pilot:
            await _until_screen(pilot, ToolScreen)
            pilot.app.suspend = lambda: contextlib.nullcontext()
            ol = pilot.app.screen.query_one("#tool-actions", OptionList)
            ol.focus()
            ol.highlighted = ol.get_option_index("run")
            await pilot.press("enter")
            await _until_screen(pilot, PermissionModal)
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                if row.obj.ran:
                    break
            assert row.obj.ran

    asyncio.run(run())


def test_back_pops_screen():
    async def run():
        async with _App(_row()).run_test() as pilot:
            await _until_screen(pilot, ToolScreen)
            ol = pilot.app.screen.query_one("#tool-actions", OptionList)
            ol.focus()
            ol.highlighted = ol.get_option_index("back")
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                if not isinstance(pilot.app.screen, ToolScreen):
                    break
            assert not isinstance(pilot.app.screen, ToolScreen)

    asyncio.run(run())
