"""`python -m hackingtool` dispatches to cli.main."""
import runpy
from unittest import mock


def test_main_module_calls_cli_main():
    with mock.patch("hackingtool.cli.main") as m:
        runpy.run_module("hackingtool", run_name="__main__")
    assert m.called
