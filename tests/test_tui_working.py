from hackingtool.tui import glyphs, working


def test_line_starts_with_run_glyph_and_word():
    out = working.line()
    assert out.startswith(glyphs.RUN)
    assert any(w in out for w in working.WORDS)
    assert "…" in out


def test_line_appends_suffix():
    assert "running Nmap" in working.line("running Nmap")


def test_words_are_nonempty_strings():
    assert working.WORDS
    assert all(isinstance(w, str) and w for w in working.WORDS)
