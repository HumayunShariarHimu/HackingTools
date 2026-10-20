import asyncio

from textual import work
from textual.app import App
from textual.widgets import RadioSet

from hackingtool.tui.widgets.permission import PermissionModal


class _App(App):
    result = None

    @work
    async def on_mount(self) -> None:
        self.result = await self.push_screen_wait(
            PermissionModal("Run nmap against 3 targets?")
        )
        self.exit()


async def _drive(*keys: str):
    async with _App().run_test() as pilot:
        for _ in range(20):
            await pilot.pause()
            if isinstance(pilot.app.screen, PermissionModal):
                break
        assert pilot.app.screen.query(RadioSet)  # modal is up and focusable
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
        return pilot.app.result


def test_yes_is_highlighted_first_and_enter_returns_yes():
    # on-mount highlights "Yes" (index 0); enter presses it
    assert asyncio.run(_drive("enter")) == "yes"


def test_down_then_enter_returns_no():
    # down -> highlight "No" (index 1), enter -> press it
    assert asyncio.run(_drive("down", "enter")) == "no"


def test_escape_returns_no():
    assert asyncio.run(_drive("escape")) == "no"
