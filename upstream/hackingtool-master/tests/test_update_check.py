"""update_check: version comparison + fail-safe behaviour (never raises, honours opt-out)."""
import hackingtool.update_check as uc


def _reset():
    uc._memo_done = False
    uc._memo_val = None


def test_parse_handles_v_prefix_and_prerelease():
    assert uc._parse("v3.0.1") == (3, 0, 1)
    assert uc._parse("3.0") == (3, 0, 0)
    assert uc._parse("v3.1.0-rc1") == (3, 1, 0)
    assert uc._parse("v3.0.1") > uc._parse("3.0.0")


def test_newer_release_reported(monkeypatch):
    _reset()
    monkeypatch.setattr(uc, "_cached_latest", lambda timeout: "v9.9.9")
    assert uc.latest_if_newer() == "9.9.9"


def test_same_or_older_returns_none(monkeypatch):
    _reset()
    monkeypatch.setattr(uc, "_cached_latest", lambda timeout: f"v{uc.VERSION}")
    assert uc.latest_if_newer() is None


def test_network_error_is_swallowed(monkeypatch):
    _reset()
    def boom(timeout):
        raise OSError("offline")
    monkeypatch.setattr(uc, "_cached_latest", boom)
    assert uc.latest_if_newer() is None


def test_env_opt_out(monkeypatch):
    _reset()
    monkeypatch.setenv("HACKINGTOOL_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(uc, "_cached_latest", lambda timeout: "v9.9.9")
    assert uc.latest_if_newer() is None
