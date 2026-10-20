"""Base screen: header docked top, a filterable OptionList filling the middle, prompt docked bottom."""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from hackingtool.constants import VERSION_DISPLAY
from hackingtool.tui import data, glyphs
from hackingtool.tui.widgets.command_palette import CommandPalette
from hackingtool.tui.widgets.header import Header


class HTScreen(Screen):
    LIST_ID = "ht-list"                       # subclass overrides
    PROMPT_PLACEHOLDER = "type to filter…"     # subclass overrides
    SHOW_BACK = True                           # MainScreen (the root) sets False

    def compose(self) -> ComposeResult:
        yield self.header_widget()
        yield from self.content()

    def content(self) -> ComposeResult:
        ol = OptionList(*self.options(""), id=self.LIST_ID)
        ol.can_focus = False      # keep focus on the prompt so typing always lands there
        yield ol
        yield Static(self.hint_text(), id="ht-hint")
        prompt = Input(placeholder=self.PROMPT_PLACEHOLDER, id="ht-prompt")
        prompt.border_title = glyphs.PROMPT
        yield prompt

    def hint_text(self) -> str:
        back = " · ← esc back" if self.SHOW_BACK else ""
        return f" type to filter · / commands · ↑↓ move · ⏎ open{back} · shift+drag copy"

    def on_mount(self) -> None:
        # Highlight the first row and focus the prompt so ↑↓/⏎ and typing work at once.
        if self.query("#ht-prompt"):
            ol = self._list()
            if ol.option_count:
                ol.highlighted = 0
            self.query_one("#ht-prompt", Input).focus()

    # hooks
    def options(self, needle: str) -> list[Option]:
        return []

    def open_selected(self, option_id: str) -> None:
        ...

    def _list(self) -> OptionList:
        return self.query_one(f"#{self.LIST_ID}", OptionList)

    # slash command palette (lazy-mounted on the first "/")
    def _palette(self) -> CommandPalette | None:
        pals = self.query(CommandPalette)
        return pals.first() if pals else None

    def _ensure_palette(self) -> CommandPalette:
        pal = self._palette()
        if pal is None:
            pal = CommandPalette()
            self.mount(pal)
        return pal

    def _remove_palette(self) -> None:
        pal = self._palette()
        if pal is not None:
            pal.remove()

    def header_widget(self):
        total = sum(c.count for c in data.categories())
        return Header(f"hackingtool {VERSION_DISPLAY}", self.status_text(), total)

    def status_text(self) -> str:
        return "ready"

    def on_input_changed(self, event: Input.Changed) -> None:
        v = event.value
        if v.startswith("/"):
            self._ensure_palette().filter(v[1:])
        else:
            self._remove_palette()
            ol = self._list()
            ol.clear_options()
            ol.add_options(self.options(v))
            ol.highlighted = 0 if ol.option_count else None

    def on_key(self, event) -> None:
        if event.key == "escape":
            if self._palette() is not None:
                self.query_one("#ht-prompt", Input).value = ""  # clears → removes palette
                event.stop()
            return
        # ← goes back when the prompt is empty; with text it stays cursor-left (Input binds it).
        if event.key == "left" and isinstance(self.focused, Input):
            if not self.focused.value and self._palette() is None and self.SHOW_BACK:
                self.app.pop_screen()
                event.stop()
            return
        # Input binds neither up nor down (verified), so they bubble here.
        if event.key in ("down", "up") and isinstance(self.focused, Input):
            pal = self._palette()
            target = pal if pal is not None else self._list()
            if target.option_count:
                (target.action_cursor_down if event.key == "down" else target.action_cursor_up)()
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        pal = self._palette()
        if pal is not None:
            if pal.highlighted is not None:
                self.post_message(CommandPalette.Selected(pal.get_option_at_index(pal.highlighted).id))
            self.query_one("#ht-prompt", Input).value = ""  # clears → removes palette
            return
        ol = self._list()
        if ol.highlighted is not None:
            self.open_selected(ol.get_option_at_index(ol.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.open_selected(event.option.id)
