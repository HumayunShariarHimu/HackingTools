"""Main screen: all categories with icon + count; the bottom prompt filters them."""
from textual.widgets.option_list import Option

from hackingtool.tui import data, glyphs
from hackingtool.tui.screens.base import HTScreen
from hackingtool.tui.screens.category import CategoryScreen
from hackingtool.tui.screens.tool import ToolScreen
from hackingtool.tui.widgets.banner import SponsorBanner


class MainScreen(HTScreen):
    LIST_ID = "main-cats"
    PROMPT_PLACEHOLDER = "type to search all tools…"
    SHOW_BACK = False      # root screen — nothing to go back to

    def __init__(self):
        self._cats = data.categories()
        super().__init__()

    def header_widget(self):
        total = sum(c.count for c in self._cats)
        return SponsorBanner(total)

    def options(self, needle: str = "") -> list[Option]:
        # Empty prompt browses categories; typing searches every tool in every submenu.
        if not needle.strip():
            return [Option(f"{c.icon}  {c.label}   {c.count}", id=str(c.index))
                    for c in self._cats]
        return [Option(f"{glyphs.RUN}  {h.title}   ·  {h.cat_label}",
                       id=f"t:{h.cat_index}:{h.tool_index}")
                for h in data.search_tools(needle)]

    def open_selected(self, option_id: str) -> None:
        if option_id.startswith("t:"):
            _, cat, tool = option_id.split(":")
            self.app.push_screen(ToolScreen(data.tool_at(int(cat), int(tool))))
        else:
            self.app.push_screen(CategoryScreen(int(option_id)))
