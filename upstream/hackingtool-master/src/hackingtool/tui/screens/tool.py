"""Tool detail screen: gated Run/Reinstall/Uninstall drop to a real TTY via App.suspend()."""
from textual.app import ComposeResult
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option
from textual import work

from hackingtool.tui import glyphs, working
from hackingtool.tui.data import ToolRow
from hackingtool.tui.screens.base import HTScreen
from hackingtool.tui.widgets.permission import PermissionModal

_GATED = ("run", "install", "uninstall")


class ToolScreen(HTScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back"), ("left", "app.pop_screen", "Back")]

    def __init__(self, row: ToolRow):
        self._row = row
        super().__init__()

    def _detail_text(self) -> str:
        r = self._row
        state = f"{glyphs.INSTALLED} installed" if r.installed else f"{glyphs.NOT_INSTALLED} not installed"
        return f" {r.title}   {state}\n {r.description}\n {r.url}"

    def content(self) -> ComposeResult:
        yield Static(self._detail_text(), id="tool-detail")
        yield OptionList(
            Option(f"{glyphs.RUN} Run", id="run"),
            Option("↻ Install", id="install"),
            Option("⧉ Open repo", id="open"),
            Option("⌫ Uninstall", id="uninstall"),
            Option("← Back", id="back"),
            id="tool-actions",
        )
        yield Static(f" {glyphs.PROMPT} ↑↓ move · ⏎ select · ← esc back", id="ht-hint")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        action = event.option.id
        if action == "back":
            self.app.pop_screen()
        elif action == "open":
            self._open_repo()
        elif action in _GATED:
            self._run_action(action)  # fire the worker; must NOT await push_screen_wait here

    def _open_repo(self) -> None:
        import webbrowser
        url = (self._row.url or "").strip()
        if url.lower().startswith(("http://", "https://")):
            webbrowser.open_new_tab(url)

    @work(exit_on_error=False)
    async def _run_action(self, action: str) -> None:
        answer = await self.app.push_screen_wait(PermissionModal(f"{action} {self._row.title}?"))
        if answer == "no":
            return
        fn = getattr(self._row.obj, action)
        with self.app.suspend():  # drop to raw terminal so the tool gets a TTY
            try:
                print(working.line(f"running {self._row.title}"))
                fn()
            except SystemExit:
                pass  # a tool quitting itself must not quit the TUI
            except BaseException:
                self.app.bell()
        # reflect the tool's new install state in the detail line
        try:
            self._row.installed = bool(self._row.obj.is_installed())
        except Exception:
            pass
        self.query_one("#tool-detail", Static).update(self._detail_text())
