from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import RadioButton, RadioSet, Static


class PermissionModal(ModalScreen[str]):
    """Confirm before a sudo / target-touching action. Returns 'yes'|'no'. (claude-permission)"""

    BINDINGS = [("escape", "cancel", "Cancel")]
    _VALUES = ["yes", "no"]

    def __init__(self, message: str):
        self._message = message
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="perm-box"):
            yield Static(f"● Permission required\n{self._message}")
            yield RadioSet(
                RadioButton("Yes"),
                RadioButton("No"),
            )

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        self.dismiss(self._VALUES[event.radio_set.pressed_index])

    def action_cancel(self) -> None:
        self.dismiss("no")
