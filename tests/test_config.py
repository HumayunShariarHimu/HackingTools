import pytest

from hackingtool import config


@pytest.fixture
def tmp_cfg(tmp_path, monkeypatch):
    f = tmp_path / "config.json"
    monkeypatch.setattr(config, "USER_CONFIG_FILE", f)
    return f


def test_set_value_roundtrip(tmp_cfg):
    ok, msg = config.set_value("background_runner", "off")
    assert ok
    assert config.load()["background_runner"] == "off"


def test_set_value_bool_coerce(tmp_cfg):
    ok, _ = config.set_value("show_archived", "on")
    assert ok and config.load()["show_archived"] is True
    config.set_value("show_archived", "false")
    assert config.load()["show_archived"] is False


def test_set_value_rejects_unknown(tmp_cfg):
    ok, msg = config.set_value("bogus", "x")
    assert not ok and "Unknown" in msg
    assert not tmp_cfg.exists()


def test_set_value_rejects_readonly(tmp_cfg):
    ok, msg = config.set_value("version", "9.9")
    assert not ok and "read-only" in msg
    assert not tmp_cfg.exists()


def test_set_value_rejects_bad_enum(tmp_cfg):
    ok, msg = config.set_value("background_runner", "maybe")
    assert not ok and "must be one of" in msg
    assert not tmp_cfg.exists()


def test_set_value_unique_prefix(tmp_cfg):
    ok, _ = config.set_value("background", "off")
    assert ok and config.load()["background_runner"] == "off"


def test_describe_marks_version_readonly():
    editable = {k: e for k, _, e in config.describe()}
    assert editable["version"] is False
    assert editable["background_runner"] is True


def test_ensure_user_files_scaffolds(tmp_cfg):
    config.ensure_user_files()
    assert tmp_cfg.exists()                       # config.json from defaults
    env = tmp_cfg.parent / ".env"
    assert env.exists()
    body = env.read_text()
    # Security: the template must NEVER ship an active secret — every AI-key
    # line stays commented out.
    for line in body.splitlines():
        if "HACKINGTOOL_AI_KEY" in line:
            assert line.lstrip().startswith("#")


def test_set_ai_key_writes_env_not_config(tmp_cfg, monkeypatch):
    import stat
    monkeypatch.delenv("HACKINGTOOL_AI_KEY", raising=False)   # ensure clean + auto-restore
    env = tmp_cfg.parent / ".env"
    env.write_text("# hackingtool\nHACKINGTOOL_AI_MODEL=claude-x\n"
                   "# HACKINGTOOL_AI_KEY=sk-ant-your-key-here\n")

    ok, _ = config.set_ai_key("sk-ant-real-123")
    assert ok
    body = env.read_text()
    assert "HACKINGTOOL_AI_KEY=sk-ant-real-123" in body        # written, uncommented
    assert "HACKINGTOOL_AI_MODEL=claude-x" in body             # other lines preserved
    assert stat.S_IMODE(env.stat().st_mode) == 0o600           # owner-only
    assert config.ai_key() == "sk-ant-real-123"                # live in-process, no restart
    assert not tmp_cfg.exists() or "sk-ant-real-123" not in tmp_cfg.read_text()  # never in config.json

    ok, _ = config.set_ai_key("")                              # clearing re-hides + unsets
    assert ok and config.ai_key() == ""
    assert "sk-ant-real-123" not in env.read_text()


def test_ensure_user_files_never_overwrites(tmp_cfg):
    tmp_cfg.write_text('{"theme": "cyan"}')       # pre-existing, hand-edited
    env = tmp_cfg.parent / ".env"
    env.write_text("# HACKINGTOOL_AI_KEY=sk-real-key\n")
    config.ensure_user_files()
    assert '"cyan"' in tmp_cfg.read_text()         # config untouched
    assert env.read_text() == "# HACKINGTOOL_AI_KEY=sk-real-key\n"


def test_allowed_values():
    assert set(config.allowed_values("background_runner").split(", ")) == {"auto", "off"}
    assert config.allowed_values("show_archived") == "true, false"
    assert config.allowed_values("tools_dir") is None


def test_config_command_no_arg_lists(monkeypatch, capsys):
    import hackingtool.cli as cli
    cli.config_command("")
    out = capsys.readouterr().out
    assert "background_runner" in out and "version" in out


def test_config_command_sets(monkeypatch):
    import hackingtool.cli as cli
    from hackingtool import config
    seen = {}
    monkeypatch.setattr(config, "set_value",
                        lambda k, v: seen.setdefault("call", (k, v)) or (True, "ok"))
    cli.config_command("background_runner off")
    assert seen["call"] == ("background_runner", "off")


def test_config_command_show_single(monkeypatch, capsys):
    import hackingtool.cli as cli
    cli.config_command("background_runner")
    out = capsys.readouterr().out
    assert "background_runner" in out and "auto" in out


def test_config_command_show_unique_prefix(monkeypatch, capsys):
    import hackingtool.cli as cli
    cli.config_command("background")
    out = capsys.readouterr().out
    assert "background_runner" in out


# ── config_ui (modal editor) ───────────────────────────────────────────────────
def test_config_ui_rows(tmp_cfg):
    from hackingtool import config_ui
    rows = config_ui._rows()
    by_key = {r["key"]: r for r in rows}
    assert by_key["ai_provider"]["kind"] == "choice"
    assert set(by_key["ai_provider"]["choices"]) == {"auto", "ollama", "openai-compat"}
    assert by_key["theme"]["kind"] == "choice"          # theme is now arrow-selectable
    assert "magenta" in by_key["theme"]["choices"]
    assert by_key["version"]["kind"] == "readonly"
    assert by_key["ai_key"]["kind"] == "secret"        # masked-editable → written to .env
    assert rows[-1]["key"] == "ai_key"


def test_config_ui_cycle():
    from hackingtool import config_ui
    c = ["auto", "ollama", "openai-compat"]
    assert config_ui._cycle_choice("auto", c) == "ollama"          # → forward
    assert config_ui._cycle_choice("openai-compat", c) == "auto"   # → wraps
    assert config_ui._cycle_choice("auto", c, -1) == "openai-compat"  # ← wraps back
    assert config_ui._cycle_choice("ollama", c, -1) == "auto"      # ← backward
    assert config_ui._cycle_choice("bogus", c) == "auto"           # unknown → first


def test_config_command_no_arg_opens_modal_on_tty(monkeypatch):
    import hackingtool.cli as cli
    from hackingtool import prompt, config_ui
    opened = {}
    monkeypatch.setattr(prompt, "_use_pt", lambda: True)
    monkeypatch.setattr(config_ui, "open_editor", lambda: opened.setdefault("hit", True))
    cli.config_command("")
    assert opened.get("hit") is True


# ── /config github (discover token check) ──────────────────────────────────────
def test_check_token_reports_missing(monkeypatch):
    from hackingtool import discover
    for name in ("HACKINGTOOL_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    ok, detail = discover.check_token()
    assert ok is False
    assert "no token" in detail.lower()


def test_check_token_reports_limit(monkeypatch):
    from hackingtool import discover
    monkeypatch.setenv("HACKINGTOOL_GITHUB_TOKEN", "ghp_x")
    monkeypatch.setattr(discover, "_fetch",
                        lambda url: {"resources": {"search": {"limit": 30}}})
    ok, detail = discover.check_token()
    assert ok is True and "30" in detail


def test_token_steps_never_leak_a_real_token():
    from hackingtool.discover import GITHUB_TOKEN_STEPS
    assert "ghp_" not in GITHUB_TOKEN_STEPS.replace("ghp_your-token-here", "")
    assert "no permissions" in GITHUB_TOKEN_STEPS.lower()


def test_check_token_never_leaks_token_on_rejection(monkeypatch):
    """Token hygiene: a failed check_token() must not echo the token value
    anywhere in its detail string, even indirectly via an exception message."""
    from hackingtool import discover
    secret = "ghp_supersecrettoken12345"
    monkeypatch.setenv("HACKINGTOOL_GITHUB_TOKEN", secret)

    def _boom(url):
        raise ValueError(f"bad request to {url}")
    monkeypatch.setattr(discover, "_fetch", _boom)
    ok, detail = discover.check_token()
    assert ok is False
    assert secret not in detail


def test_config_command_github_no_token(monkeypatch, capsys):
    import hackingtool.cli as cli
    from hackingtool import discover
    monkeypatch.setattr(discover, "check_token", lambda: (False, "no token configured"))
    cli.config_command("github")
    out = capsys.readouterr().out
    assert "GitHub" in out
    assert "no permissions" in out.lower()
