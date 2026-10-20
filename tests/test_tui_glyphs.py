from hackingtool.tui import glyphs


def test_glyphs_are_single_source():
    assert glyphs.PROMPT == "❯"
    assert glyphs.RUN == "⏺"
    assert glyphs.SUB == "⎿"
    assert glyphs.STATUS == "◆"
    assert glyphs.INSTALLED == "✔"
    assert glyphs.NOT_INSTALLED == "○"
