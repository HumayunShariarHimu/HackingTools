"""Full-screen modal settings editor — the interactive ``/config`` surface.

Claude-cli-style: ``/config`` opens this over the alternate screen (native REPL
scrollback is preserved and restored on Esc). ↑↓ move, PgUp/PgDn jump, ←→ change
the selected value (auto-saved — choice/bool rows show their options inline). The
few free-text rows (paths, model name) can't cycle, so they show "Enter to edit"
and open an inline input. Every change persists through ``config.set_value``
immediately, so only the values we allow ever land on disk.

Non-TTY / ``--classic`` / no prompt_toolkit never reaches here — ``cli.config_command``
gates on ``prompt._use_pt()`` and falls back to the read-only table.
"""
from __future__ import annotations

import asyncio
import threading

from hackingtool import config

_PAGE = 5  # PgUp/PgDn jump size


def _rows() -> list[dict]:
    """Build the editable row model from config + the synthetic (env-only) ai_key
    row. kind ∈ {'choice','text','readonly'}; 'choice' carries its allowed list."""
    rows: list[dict] = []
    for key, value, editable in config.describe():
        if not editable:
            rows.append({"key": key, "value": str(value), "kind": "readonly"})
            continue
        choices = config.field_choices(key)
        if choices:
            rows.append({"key": key, "value": str(value).lower(),
                         "kind": "choice", "choices": choices})
        else:
            rows.append({"key": key, "value": str(value), "kind": "text"})
    # API key is secret — set here with masked input, written to .env (never
    # config.json). The row shows only its status, never the key itself.
    rows.append({"key": "ai_key", "value": config.ai_key_status(), "kind": "secret"})
    return rows


def _cycle_choice(current, choices: list[str], step: int = 1) -> str:
    """Value ``step`` positions away in the ring (← = -1, → = +1); first value when
    current isn't a known choice."""
    cur = str(current).lower()
    if cur not in choices:
        return choices[0]
    return choices[(choices.index(cur) + step) % len(choices)]


def _short(value: str, width: int = 22) -> str:
    """Trim long values (paths) so the row's inline hint stays on screen."""
    return value if len(value) <= width else value[: width - 1] + "…"


def open_editor() -> None:
    """Run the modal editor. Assumes an interactive TTY (caller gates)."""
    from prompt_toolkit import Application
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
    from prompt_toolkit.layout.containers import ConditionalContainer
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import TextArea

    state = {"rows": _rows(), "sel": 0, "editing": False, "secret": False, "msg": ""}

    def _cur() -> dict:
        return state["rows"][state["sel"]]

    # ── rendering ──
    def render_body():
        out = []
        for i, row in enumerate(state["rows"]):
            selected = i == state["sel"]
            pointer = "›" if selected else " "
            if row["kind"] == "choice":
                value = f"‹ {row['value']} ›"
                hint = "   " + " · ".join(row["choices"])   # show the options inline
            elif row["kind"] == "text":
                value = _short(row["value"]) or "(unset)"
                hint = "   Enter to edit"
            elif row["kind"] == "secret":
                value = _short(row["value"]) or "(unset)"
                hint = "   Enter to set  ·  saved to .env"
            else:
                value = _short(row["value"]) or "(unset)"
                hint = "   read-only"
            out.append(("class:sel" if selected else "", f" {pointer} {row['key']:<18}"))
            out.append(("class:val" if selected else "class:dim", f"{value:<24}"))
            out.append(("class:dim", f"{hint}\n"))
        return out

    def footer_text():
        if state["editing"]:
            return [("class:footer", " type a value · Enter save · Esc cancel")]
        frags = [("class:footer", " ↑↓ move · ←→ change (auto-saved) · t test AI · Esc done")]
        if state["msg"]:
            frags.append(("class:msg", "    " + state["msg"]))
        return frags

    edit_area = TextArea(multiline=False, height=1, style="class:edit")
    secret_area = TextArea(multiline=False, height=1, password=True, style="class:edit")  # masks the key
    body = Window(FormattedTextControl(render_body, focusable=True, show_cursor=False))

    def _keylabel():
        return [("class:editkey", f" {_cur()['key']} ❯ ")]

    def _bar(area, secret):
        return ConditionalContainer(
            VSplit([Window(FormattedTextControl(_keylabel), dont_extend_width=True), area]),
            filter=Condition(lambda: state["editing"] and state["secret"] is secret),
        )

    root = HSplit([
        Window(FormattedTextControl(lambda: [("class:title", " hackingtool • Settings")]),
               height=1),
        Window(height=1, char="─", style="class:rule"),
        body,
        _bar(edit_area, False),
        _bar(secret_area, True),
        Window(height=1, char="─", style="class:rule"),
        Window(FormattedTextControl(footer_text), height=1),
    ])

    style = Style.from_dict({
        "title": "bold #ff5fd7", "rule": "#4a4a6a", "sel": "reverse",
        "dim": "#6a6a8a", "footer": "#b0b0d0", "msg": "#7fd77f",
        "val": "bold #7fd7ff", "editkey": "bold #ff5fd7", "edit": "#e0e0f0",
    })

    kb = KeyBindings()
    nav = Condition(lambda: not state["editing"])
    editing = Condition(lambda: state["editing"])

    def _move(delta):
        state["sel"] = max(0, min(len(state["rows"]) - 1, state["sel"] + delta))
        state["msg"] = ""

    @kb.add("up", filter=nav)
    def _(e): _move(-1)

    @kb.add("down", filter=nav)
    def _(e): _move(1)

    @kb.add("pageup", filter=nav)
    def _(e): _move(-_PAGE)

    @kb.add("pagedown", filter=nav)
    def _(e): _move(_PAGE)

    def _change(step):
        """←/→ on a choice/bool row: move one option and auto-save."""
        row = _cur()
        if row["kind"] != "choice":
            return
        new = _cycle_choice(row["value"], row["choices"], step)
        ok, state["msg"] = config.set_value(row["key"], new)
        if ok:
            row["value"] = new           # update in place — no full rebuild / disk reload
            if row["key"] == "theme":
                state["msg"] += "  ·  restart to apply"

    @kb.add("left", filter=nav)
    def _(e): _change(-1)

    @kb.add("right", filter=nav)
    def _(e): _change(1)

    @kb.add("enter", filter=nav)
    def _(e):
        row = _cur()
        if row["kind"] == "choice":
            _change(1)                       # Enter mirrors → for cyclable rows
        elif row["kind"] == "text":          # free-text → inline edit
            state["editing"] = True
            edit_area.text = "" if row["value"] in ("", "(unset)") else row["value"]
            e.app.layout.focus(edit_area)
        elif row["kind"] == "secret":        # API key → masked input, saved to .env
            state["editing"] = True
            state["secret"] = True
            secret_area.text = ""
            e.app.layout.focus(secret_area)
        else:
            state["msg"] = f"{row['key']} is read-only"

    @kb.add("enter", filter=editing)
    def _(e):
        row = _cur()
        if state["secret"]:                  # never touches config.json; status only
            ok, state["msg"] = config.set_ai_key(secret_area.text.strip())
            if ok:
                row["value"] = config.ai_key_status()
        else:
            value = edit_area.text.strip()
            ok, state["msg"] = config.set_value(row["key"], value)
            if ok:
                row["value"] = value         # in place — free-text keys aren't coerced
        state["editing"] = state["secret"] = False
        e.app.layout.focus(body)

    @kb.add("escape", filter=editing)
    def _(e):
        state["editing"] = state["secret"] = False
        state["msg"] = "cancelled"
        e.app.layout.focus(body)

    probing = {"on": False}

    @kb.add("t", filter=nav)
    def _(e):
        # AI probe can block up to 30s on the network — run it off the UI loop so
        # Escape/Ctrl-C stay responsive. Ignore repeat presses while one is in flight.
        if probing["on"]:
            return
        probing["on"] = True
        state["msg"] = "testing AI connection…"
        app = e.app
        loop = asyncio.get_running_loop()      # key handlers run on the app's event loop

        def worker():
            from hackingtool import ai_recommend
            try:
                ok, detail = ai_recommend.test_connection()
                msg = ("✓ " if ok else "✗ ") + (detail[:70] + "…" if len(detail) > 70 else detail)
            except Exception as exc:
                msg = f"✗ probe error: {exc}"

            def done():
                probing["on"] = False
                state["msg"] = msg
                app.invalidate()
            try:
                loop.call_soon_threadsafe(done)
            except RuntimeError:               # loop already closed (app exited mid-probe)
                probing["on"] = False

        threading.Thread(target=worker, daemon=True).start()

    @kb.add("escape", filter=nav, eager=True)
    @kb.add("c-c", filter=nav)
    def _(e): e.app.exit()

    Application(layout=Layout(root, focused_element=body), key_bindings=kb,
                full_screen=True, style=style, mouse_support=False).run()


def demo():
    """Offline self-check: row model + cycle logic (no TTY / Application)."""
    bykey = {r["key"]: r for r in _rows()}
    keys = list(bykey)
    assert keys[-1] == "ai_key", keys
    assert "ai_provider" in keys and "ai_model" in keys
    assert bykey["version"]["kind"] == "readonly"       # non-editable
    assert bykey["ai_key"]["kind"] == "secret"          # masked-editable → .env
    prov = next(r for r in _rows() if r["key"] == "ai_provider")
    assert prov["kind"] == "choice"
    assert _cycle_choice("auto", prov["choices"]) in prov["choices"]
    assert _cycle_choice("auto", ["auto", "ollama", "openai-compat"]) == "ollama"    # →
    assert _cycle_choice("auto", ["auto", "ollama", "openai-compat"], -1) == "openai-compat"  # ← wraps
    assert _cycle_choice("bogus", ["auto", "off"]) == "auto"  # unknown → first
    print("OK — config_ui: rows + cycle")


if __name__ == "__main__":
    demo()
