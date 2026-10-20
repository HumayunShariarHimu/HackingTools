import json
import logging
import os
from pathlib import Path
from typing import Any

from hackingtool.constants import (
    USER_CONFIG_FILE, USER_TOOLS_DIR, DEFAULT_CONFIG, THEME_CHOICES,
)

logger = logging.getLogger(__name__)


def _load_env() -> None:
    """Load ~/.hackingtool/.env once so HACKINGTOOL_AI_* (esp. the API key) works
    without exporting it each shell. Real shell env vars still win (override=False).
    dotenv is optional — the zero-dep base skips this cleanly."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_file = USER_CONFIG_FILE.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


_load_env()


def load() -> dict[str, Any]:
    """Load config from disk, merging with defaults for any missing keys."""
    if USER_CONFIG_FILE.exists():
        try:
            on_disk = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
            if not isinstance(on_disk, dict):          # e.g. [], "x", 42 — not a config object
                raise ValueError("config.json is not a JSON object")
            return {**DEFAULT_CONFIG, **on_disk}
        except (ValueError, OSError) as exc:           # ValueError covers JSONDecodeError
            logger.warning("Config file unreadable (%s), using defaults.", exc)
    return dict(DEFAULT_CONFIG)


def save(cfg: dict[str, Any]) -> None:
    """Write config to disk atomically, creating parent directories if needed."""
    from hackingtool.storage import write_json
    write_json(USER_CONFIG_FILE, cfg, indent=2, sort_keys=True)


_ENV_TEMPLATE = """\
# hackingtool — secrets & optional AI overrides. Auto-loaded at startup.
# Real shell environment variables always win over anything set here.
# Uncomment a line (remove the leading '# ') and fill it in to enable it.
# Keep this file private — it may hold your API key (chmod 600).

# ── AI API key ── secret; lives ONLY here, never in config.json ──
# Easiest: set it from /config (masked) — it writes the line below for you.
# HACKINGTOOL_AI_KEY=sk-ant-your-key-here

# ── AI transport ── these mirror /config (config.json); env wins if set ──
# HACKINGTOOL_AI_PROVIDER=openai-compat            # auto | ollama | openai-compat
# HACKINGTOOL_AI_BASE_URL=https://api.anthropic.com/v1
# HACKINGTOOL_AI_MODEL=claude-haiku-4-5-20251001

# ── GitHub token for /find ── optional; raises search 10 → 30 req/min ──
# Create one with NO permissions/scopes (public read only) — see '/config github'.
# HACKINGTOOL_GITHUB_TOKEN=ghp_your-token-here
"""


def ensure_user_files() -> None:
    """First-run scaffolding: create ~/.hackingtool/ with a real config.json
    (defaults) and a commented .env template, so users have files to edit.
    Never overwrites existing files and never writes a real secret."""
    USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG_FILE.exists():
        save(dict(DEFAULT_CONFIG))
    env_file = USER_CONFIG_FILE.parent / ".env"
    if not env_file.exists():
        env_file.write_text(_ENV_TEMPLATE, encoding="utf-8")
        try:
            env_file.chmod(0o600)      # secrets file — owner-only
        except OSError:
            pass


def get_tools_dir() -> Path:
    """
    Return the directory where external tools are stored.
    Creates it if it does not exist.
    Always an absolute path — never relies on process CWD.
    """
    cfg = load()
    tools_dir = Path(cfg.get("tools_dir", str(USER_TOOLS_DIR))).expanduser().resolve()
    tools_dir.mkdir(parents=True, exist_ok=True)
    return tools_dir


def get_sudo_cmd() -> str:
    """Return 'doas' if available, else 'sudo'. Never hardcode 'sudo'."""
    import shutil
    return "doas" if shutil.which("doas") else "sudo"


# ── /config settings surface ──────────────────────────────────────────────────
_READONLY = {"version"}                       # never editable at runtime
_ENUMS = {                                    # fixed string domains
    "background_runner": {"auto", "off"},
    "ai_provider": {"auto", "ollama", "openai-compat"},
    "theme": set(THEME_CHOICES),              # applies on next launch
}
_BOOLS = {"show_archived", "update_check"}     # boolean-valued keys
_TRUE = {"true", "on", "yes", "1"}
_FALSE = {"false", "off", "no", "0"}


def describe() -> list[tuple[str, Any, bool]]:
    """(key, current_value, editable) for every known config key."""
    cfg = load()
    return [(k, cfg.get(k), k not in _READONLY) for k in DEFAULT_CONFIG]


def _resolve_key(key: str) -> str | None:
    """Exact match (incl. read-only), else a unique prefix among editable keys."""
    if key in DEFAULT_CONFIG:
        return key
    matches = [k for k in DEFAULT_CONFIG
               if k not in _READONLY and k.startswith(key)]
    return matches[0] if len(matches) == 1 else None


def field_choices(key: str) -> list[str] | None:
    """Ordered choice list for a constrained key (enum or bool), else None for
    free-text. The modal editor cycles a row through these on Enter."""
    resolved = _resolve_key(key) or key
    if resolved in _ENUMS:
        return sorted(_ENUMS[resolved])
    if resolved in _BOOLS:
        return ["true", "false"]
    return None


def allowed_values(key: str) -> str | None:
    """Human hint of legal values for a key, or None for free-form."""
    resolved = _resolve_key(key) or key
    if resolved in _ENUMS:
        return ", ".join(sorted(_ENUMS[resolved]))
    if resolved in _BOOLS:
        return "true, false"
    return None


def set_value(key: str, value: str) -> tuple[bool, str]:
    """Validate + persist one config key. Returns (ok, message); no write on failure."""
    resolved = _resolve_key(key)
    if resolved is None:
        return False, f"Unknown or ambiguous key '{key}'. Try /config to list keys."
    if resolved in _READONLY:
        return False, f"'{resolved}' is read-only."
    coerced: Any = value
    if resolved in _BOOLS:
        low = value.strip().lower()
        if low in _TRUE:
            coerced = True
        elif low in _FALSE:
            coerced = False
        else:
            return False, f"'{resolved}' expects true/false (got '{value}')."
    elif resolved in _ENUMS:
        low = value.strip().lower()
        if low not in _ENUMS[resolved]:
            allowed = ", ".join(sorted(_ENUMS[resolved]))
            return False, f"'{resolved}' must be one of: {allowed} (got '{value}')."
        coerced = low
    cfg = load()
    cfg[resolved] = coerced
    try:
        save(cfg)
    except OSError as exc:
        return False, f"Could not save configuration: {exc}"
    return True, f"set {resolved} = {coerced}"


# ── AI transport settings ──────────────────────────────────────────────────────
# Non-secret knobs live in config.json (editable via /config); a shell/.env var of
# the same name overrides, so existing HACKINGTOOL_AI_* setups keep working. The
# API key is secret — env/.env ONLY, never written to config.json.


def ai_provider() -> str:
    return os.environ.get("HACKINGTOOL_AI_PROVIDER") or load().get("ai_provider", "auto")


def ai_model() -> str:
    return os.environ.get("HACKINGTOOL_AI_MODEL") or load().get("ai_model") or "llama3"


def ai_base_url() -> str:
    return os.environ.get("HACKINGTOOL_AI_BASE_URL") or load().get("ai_base_url") or ""


def ai_key() -> str:
    """The secret API key, from env/.env only (never config.json)."""
    return os.environ.get("HACKINGTOOL_AI_KEY") or ""


def ai_key_status() -> str:
    """Display-only status for the /config editor — never the value itself."""
    return "set (env)" if ai_key() else "not set"


def set_ai_key(value: str) -> tuple[bool, str]:
    """Persist the secret API key to ~/.hackingtool/.env — never config.json — and
    apply it to the running process so /config test works right away. Empty value
    clears it. Rewrites only the HACKINGTOOL_AI_KEY line, preserving the rest."""
    value = (value or "").strip()
    if "\n" in value or "\r" in value:
        return False, "API key can't contain newlines."
    env_file = USER_CONFIG_FILE.parent / ".env"
    new_line = f"HACKINGTOOL_AI_KEY={value}" if value else "# HACKINGTOOL_AI_KEY=sk-ant-your-key-here"
    try:
        env_file.parent.mkdir(parents=True, exist_ok=True)
        lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else _ENV_TEMPLATE.splitlines()
        for i, line in enumerate(lines):
            if line.lstrip("# ").startswith("HACKINGTOOL_AI_KEY="):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return False, f"Could not save API key: {type(exc).__name__}"   # never echo the secret
    try:
        env_file.chmod(0o600)                 # secrets file — owner-only
    except OSError:
        pass
    if value:
        os.environ["HACKINGTOOL_AI_KEY"] = value       # in-process, no restart needed
        return True, "API key saved to ~/.hackingtool/.env (0600)"
    os.environ.pop("HACKINGTOOL_AI_KEY", None)
    return True, "API key cleared from ~/.hackingtool/.env"