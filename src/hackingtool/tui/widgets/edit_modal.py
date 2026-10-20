"""Inline value editor for free-text / secret config rows. Returns the new string, or None."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class EditModal(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, key: str, current: str = "", secret: bool = False):
        self._key = key
        self._current = current
        self._secret = secret
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-box"):
            yield Static(f"● Set {self._key.replace('_', ' ')}")
            value = "" if self._secret else self._current
            inp = Input(value=value, password=self._secret, id="edit-input")
            inp.border_subtitle = "⏎ save · esc cancel"
            yield inp

    def on_mount(self) -> None:
        self.query_one("#edit-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
