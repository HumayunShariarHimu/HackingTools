"""Category screen: tools in a category with install marks; the bottom prompt filters them."""
from textual.widgets.option_list import Option

from hackingtool.tui import glyphs, data
from hackingtool.tui.screens.base import HTScreen
from hackingtool.tui.screens.tool import ToolScreen


class CategoryScreen(HTScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]
    LIST_ID = "cat-tools"
    PROMPT_PLACEHOLDER = "type to filter tools…"

    def __init__(self, cat_index: int):
        self._cat = cat_index
        self._rows = data.tools_in(cat_index)
        super().__init__()

    def options(self, needle: str = "") -> list[Option]:
        opts = []
        for r in self._rows:
            if needle and needle.lower() not in r.title.lower():
                continue
            mark = glyphs.INSTALLED if r.installed else glyphs.NOT_INSTALLED
            opts.append(Option(f"{mark}  {r.title}", id=str(r.index)))
        return opts

    def open_selected(self, option_id: str) -> None:
        self.app.push_screen(ToolScreen(data.tool_at(self._cat, int(option_id))))
