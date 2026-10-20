"""/update dialog: shows the detected install method's upgrade command (copyable). Never runs it."""
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from hackingtool import update_check
from hackingtool.constants import REPO_WEB_URL, VERSION_DISPLAY


class UpdateModal(ModalScreen):
    BINDINGS = [("escape", "close", "Close"), ("enter", "copy", "Copy command")]

    def __init__(self, newer: str | None):
        self._newer = newer
        self._method, self._cmds = update_check.upgrade_commands()
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="update-box"):
            yield Static(self._text(), markup=False)

    def _text(self) -> Text:
        t = Text()
        if self._newer:
            t.append(f"● Update   {VERSION_DISPLAY} → v{self._newer}\n\n", style="bold yellow")
        else:
            t.append(f"● Up to date   {VERSION_DISPLAY}\n\n", style="bold green")
        t.append(f" Detected install: {self._method}\n\n", style="dim")
        t.append(f"   {self._cmds[self._method]}\n\n", style="bold cyan")
        t.append(" Not right? Other methods:\n", style="dim")
        for m, cmd in self._cmds.items():
            if m != self._method:
                t.append(f"   {cmd}\n", style="dim")
        url = f"{REPO_WEB_URL}/releases"
        t.append(f"\n {url}\n", style=f"dim link {url}")
        t.append(" ⏎ copy command · esc close", style="dim")
        return t

    def action_copy(self) -> None:
        self.app.copy_to_clipboard(self._cmds[self._method])
        self.app.notify("Upgrade command copied to clipboard.", severity="information")
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()
