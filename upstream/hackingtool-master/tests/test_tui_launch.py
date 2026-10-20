import sys
from unittest import mock
import hackingtool.cli as cli


# NOTE: cli imports get_tools_dir via `from hackingtool.config import get_tools_dir`,
# so the live name is hackingtool.cli.get_tools_dir (patching hackingtool.config.*
# would not intercept it). ensure_user_files is called as config.ensure_user_files,
# so it is patched on the config module.
def test_default_launches_tui(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hackingtool"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    with mock.patch("hackingtool.tui.app.run") as tui, \
         mock.patch("hackingtool.config.ensure_user_files"), \
         mock.patch("hackingtool.cli.get_tools_dir"):
        cli.main()
    assert tui.called


def test_classic_flag_skips_tui(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hackingtool", "--classic"])
    with mock.patch("hackingtool.tui.app.run") as tui, \
         mock.patch("hackingtool.cli.interact_menu") as classic, \
         mock.patch("hackingtool.repl._use_repl", return_value=False), \
         mock.patch("hackingtool.config.ensure_user_files"), \
         mock.patch("hackingtool.cli.get_tools_dir"):
        cli.main()
    assert not tui.called
    assert classic.called
