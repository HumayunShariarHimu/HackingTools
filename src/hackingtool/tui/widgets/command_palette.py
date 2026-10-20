from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

# (command, help) — /config/menu/quit act now; /recommend,/report are Phase-2 (notify).
# No /search: just type in the prompt to filter live.
COMMANDS = [
    ("/config", "edit settings"),
    ("/update", "check for & how to update hackingtool"),
    ("/recommend", "AI tool recommendation"),
    ("/report", "export findings"),
    ("/menu", "browse categories"),
    ("/quit", "exit hackingtool"),
]


class CommandPalette(OptionList):
    """Floating slash-command palette, filtered by the bottom prompt. (claude-slash-menu)"""

    class Selected(Message):
        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    def __init__(self):
        super().__init__(*self._opts(""))
        self.can_focus = False      # prompt keeps focus; ↑↓ are routed here from it

    def _opts(self, needle: str) -> list[Option]:
        n = needle.lower()
        return [
            Option(f"{cmd}  {help_}", id=cmd)
            for cmd, help_ in COMMANDS
            if not n or n in cmd.lower() or n in help_.lower()
        ]

    def filter(self, needle: str) -> None:
        self.clear_options()
        self.add_options(self._opts(needle))
        if self.option_count:
            self.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:  # mouse click
        event.stop()
        self.post_message(self.Selected(event.option.id))
