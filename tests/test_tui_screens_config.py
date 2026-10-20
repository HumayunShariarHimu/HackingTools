"""ConfigScreen: native settings editor — filter, cycle choices (persisted), read-only guard."""
import asyncio

from textual.app import App
from textual.widgets import Input, OptionList

from hackingtool import config
from hackingtool.tui.screens.config import ConfigScreen


class _App(App):
    async def on_mount(self) -> None:
        await self.push_screen(ConfigScreen())


async def _until(pilot):
    for _ in range(40):
        await pilot.pause()
        if isinstance(pilot.app.screen, ConfigScreen):
            return
    raise AssertionError("ConfigScreen never appeared")


def test_lists_settings():
    async def run():
        async with _App().run_test() as pilot:
            await _until(pilot)
            ol = pilot.app.screen.query_one("#config-rows", OptionList)
            ids = [ol.get_option_at_index(i).id for i in range(ol.option_count)]
            assert "theme" in ids
            assert "ai_key" in ids          # synthetic secret row present
    asyncio.run(run())


def test_filter_narrows_settings():
    async def run():
        async with _App().run_test() as pilot:
            await _until(pilot)
            ol = pilot.app.screen.query_one("#config-rows", OptionList)
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = "theme"
            await pilot.pause()
            assert ol.option_count == 1
            assert ol.get_option_at_index(0).id == "theme"
    asyncio.run(run())


def test_enter_cycles_choice_and_persists(monkeypatch):
    saved = {}

    def _fake_set(k, v):
        saved[k] = v
        return (True, "ok")

    monkeypatch.setattr(config, "set_value", _fake_set)

    async def run():
        async with _App().run_test() as pilot:
            await _until(pilot)
            inp = pilot.app.screen.query_one("#ht-prompt", Input)
            inp.value = "show archived"      # a bool row -> cycles true/false
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert "show_archived" in saved   # set_value was called with the new value
    asyncio.run(run())


def test_readonly_row_notifies_instead_of_editing():
    async def run():
        async with _App().run_test() as pilot:
            await _until(pilot)
            scr = pilot.app.screen
            seen = {}
            pilot.app.notify = lambda *a, **k: seen.setdefault("msg", (a, k))
            inp = scr.query_one("#ht-prompt", Input)
            inp.value = "version"            # read-only
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert "msg" in seen
            assert "read-only" in seen["msg"][0][0].lower()
    asyncio.run(run())
