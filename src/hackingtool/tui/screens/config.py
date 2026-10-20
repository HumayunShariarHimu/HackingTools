"""Native settings screen: filter rows, ⏎ cycles choices / edits text, auto-saved via config.set_value."""
from textual.widgets.option_list import Option
from textual import work

from hackingtool import config, config_ui
from hackingtool.tui.screens.base import HTScreen
from hackingtool.tui.widgets.edit_modal import EditModal


class ConfigScreen(HTScreen):
    LIST_ID = "config-rows"
    PROMPT_PLACEHOLDER = "search settings…"

    def _pretty(self, key: str) -> str:
        return key.replace("_", " ").capitalize()

    def _value_cell(self, row: dict) -> str:
        v = row["value"] or "(unset)"
        if row["kind"] == "choice":
            return f"‹ {v} ›"
        if row["kind"] == "readonly":
            return f"{v}   (read-only)"
        return f"{v}   (⏎ edit)"      # text / secret

    def options(self, needle: str = "") -> list[Option]:
        n = needle.lower().strip()
        out = []
        for row in config_ui._rows():
            label = self._pretty(row["key"])
            if n and n not in label.lower() and n not in row["key"].lower():
                continue
            out.append(Option(f"  {label:<24}{self._value_cell(row)}", id=row["key"]))
        return out

    def open_selected(self, key: str) -> None:
        row = next((r for r in config_ui._rows() if r["key"] == key), None)
        if row is None:
            return
        kind = row["kind"]
        if kind == "choice":
            nv = config_ui._cycle_choice(row["value"], row["choices"], +1)
            ok, msg = config.set_value(key, nv)
            if not ok:
                self.app.notify(msg, title="Invalid", severity="error")
            self._refresh()
        elif kind in ("text", "secret"):
            self._edit(key, row["value"], kind == "secret")
        else:  # readonly
            self.app.notify(f"{self._pretty(key)} is read-only.", severity="warning")

    @work
    async def _edit(self, key: str, current: str, secret: bool) -> None:
        new = await self.app.push_screen_wait(EditModal(key, current, secret))
        if new is None:
            return
        ok, msg = (config.set_ai_key(new) if secret else config.set_value(key, new))
        self.app.notify(msg, title="Saved" if ok else "Rejected",
                        severity="information" if ok else "error")
        self._refresh()

    def _refresh(self) -> None:
        ol = self._list()
        needle = self.query_one("#ht-prompt").value
        idx = ol.highlighted
        ol.clear_options()
        ol.add_options(self.options(needle))
        if ol.option_count:
            ol.highlighted = min(idx or 0, ol.option_count - 1)
