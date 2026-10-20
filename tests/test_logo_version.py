"""Guard: the static logo.svg version label must match constants.VERSION (single source)."""
from pathlib import Path

from hackingtool.constants import VERSION

_LOGO = Path(__file__).resolve().parents[1] / "images" / "logo.svg"


def test_logo_svg_version_matches_constants():
    assert f"hackingtool — v{VERSION}" in _LOGO.read_text(encoding="utf-8"), (
        f"images/logo.svg version label is stale; bump it to v{VERSION}")
