"""HackingToolApp: boots to MainScreen; the bottom prompt's "/" opens a floating CommandPalette."""
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from hackingtool.tui.screens.main import MainScreen
from hackingtool.tui.screens.config import ConfigScreen
from hackingtool.tui.widgets.command_palette import CommandPalette


class HackingToolApp(App):
    CSS_PATH = Path(__file__).with_name("app.tcss")
    BINDINGS = [Binding("q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def on_command_palette_selected(self, event: CommandPalette.Selected) -> None:
        # close the palette + clear the prompt (covers mouse-click, which doesn't submit)
        for pal in self.screen.query(CommandPalette):
            pal.remove()
        for prompt in self.screen.query("#ht-prompt"):
            prompt.value = ""
        if event.command == "/quit":
            self.exit()
        elif event.command == "/menu":
            while not isinstance(self.screen, MainScreen):
                self.pop_screen()
        elif event.command == "/config":
            if not isinstance(self.screen, ConfigScreen):
                self.push_screen(ConfigScreen())
        elif event.command == "/update":
            from hackingtool import update_check
            from hackingtool.tui.widgets.update_modal import UpdateModal
            self.push_screen(UpdateModal(update_check.latest_if_newer()))
        else:  # /recommend, /report — Phase 2; tell the user instead of doing nothing
            self.notify(f"{event.command} is coming in a future release.",
                        title="Not yet available", severity="warning")


def run() -> None:
    HackingToolApp().run()
