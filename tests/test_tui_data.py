from hackingtool.tui import data


def test_categories_nonempty_and_shaped():
    cats = data.categories()
    assert len(cats) > 1
    c = cats[0]
    assert c.title and isinstance(c.icon, str) and c.count >= 0


def test_tools_in_first_category():
    cats = data.categories()
    tools = data.tools_in(cats[0].index)
    assert isinstance(tools, list)
    if tools:
        t = tools[0]
        assert t.title
        assert isinstance(t.installed, bool)
        assert t.obj is not None  # the live engine instance for actions


def test_tool_at_round_trips():
    cats = data.categories()
    for ci, c in enumerate(cats):
        tools = data.tools_in(c.index)
        if tools:
            got = data.tool_at(c.index, tools[0].index)
            assert got.title == tools[0].title
            break
