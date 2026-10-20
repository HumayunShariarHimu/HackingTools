from rich.text import Text
from textual.widgets import Static

from hackingtool.tui import glyphs


class Header(Static):
    """Top banner: title · status · tool count. (claude-header)"""

    def __init__(self, title: str, status: str, tool_count: int):
        self._title = title
        self._status = status
        self._count = tool_count
        super().__init__(id="ht-header")

    def render(self) -> Text:
        t = Text()
        t.append(f" {self._title}   ")
        t.append(f"{glyphs.STATUS} {self._status}", style="bold yellow")
        t.append(f"   {self._count} tools", style="dim")
        return t
