from pathlib import Path
import platform
import shutil as _shutil

# ── Repository ────────────────────────────────────────────────────────────────
REPO_OWNER   = "Z4nzu"
REPO_NAME    = "hackingtool"
REPO_URL     = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
REPO_WEB_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"

# ── Versioning ────────────────────────────────────────────────────────────────
VERSION         = "3.1.0"
VERSION_DISPLAY = f"v{VERSION}"

# Maintainer-owned sponsor feed (fixed in code, NOT a user setting). Blank = committed
# sponsors.yaml only, ZERO network. A maintainer sets this + cuts a release to enable
# remote refresh; end users never point this anywhere.
SPONSORS_URL = ""

# ── Python requirement ────────────────────────────────────────────────────────
MIN_PYTHON = (3, 10)

# ── User-scoped paths (cross-platform, always computed at runtime) ─────────────
# NEVER hardcode /home/username — use Path.home() so it works for any user,
# including root (/root), regular users (/home/alice), macOS (/Users/alice).
USER_CONFIG_DIR  = Path.home() / f".{REPO_NAME}"
USER_TOOLS_DIR   = USER_CONFIG_DIR / "tools"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"
USER_LOG_FILE    = USER_CONFIG_DIR / f"{REPO_NAME}.log"
USER_HISTORY_FILE = USER_CONFIG_DIR / "history"   # persistent ↑↓ REPL command history

# ── System install paths (set per OS) ─────────────────────────────────────────
_system = platform.system()

if _system == "Darwin":
    # macOS — Homebrew convention
    APP_INSTALL_DIR = Path("/usr/local/share") / REPO_NAME
    APP_BIN_PATH    = Path("/usr/local/bin")   / REPO_NAME
elif _system == "Linux":
    APP_INSTALL_DIR = Path("/usr/share") / REPO_NAME
    APP_BIN_PATH    = Path("/usr/bin")   / REPO_NAME
else:
    # Fallback (Windows, FreeBSD, etc.)
    APP_INSTALL_DIR = USER_CONFIG_DIR / "app"
    APP_BIN_PATH    = USER_CONFIG_DIR / "bin" / REPO_NAME

# ── UI theme ──────────────────────────────────────────────────────────────────
# A theme just swaps the accent hue family (primary/border/accent); the semantic
# colours (success=green, error=red, …) stay constant so status always reads the
# same. Selecting a theme in /config applies on next launch — these are bound at
# import time and consumed across many modules as `from constants import THEME_*`.
_PALETTES = {                         # name -> (primary, border, accent, hex)
    "magenta": ("bold magenta", "bright_magenta", "bold cyan",    "#ff5fd7"),
    "cyan":    ("bold cyan",    "bright_cyan",    "bold magenta", "#5fd7ff"),
    "green":   ("bold green",   "bright_green",   "bold magenta", "#5fd75f"),
    "blue":    ("bold blue",    "bright_blue",    "bold cyan",    "#5f8fff"),
}
THEME_CHOICES = tuple(_PALETTES)      # source of truth for config's theme enum


def _configured_theme() -> str:
    """Theme name from config.json, read directly (constants must stay free of a
    config-module import cycle). Unknown/missing → 'magenta'."""
    try:
        import json
        payload = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
        name = payload.get("theme") if isinstance(payload, dict) else None
    except (OSError, ValueError):
        name = None
    return name if isinstance(name, str) and name in _PALETTES else "magenta"


# THEME_HEX drives the prompt_toolkit REPL surface (prompt + rule); the rich
# style strings drive classic menus / panels. Both swap together per theme.
THEME_PRIMARY, THEME_BORDER, THEME_ACCENT, THEME_HEX = _PALETTES[_configured_theme()]
THEME_SUCCESS  = "bold green"
THEME_ERROR    = "bold red"
THEME_WARNING  = "bold yellow"
THEME_DIM      = "dim white"
THEME_ARCHIVED = "dim yellow"
THEME_URL      = "underline bright_blue"

# ── Default config values ──────────────────────────────────────────────────────
DEFAULT_CONFIG: dict = {
    "tools_dir":      str(USER_TOOLS_DIR),
    "version":        VERSION,
    "theme":          "magenta",
    "show_archived":  False,
    "update_check":   True,        # check GitHub once/day for a newer release on startup
    "background_runner": "auto",   # "auto" (on iff tmux present) | "off"
    "ai_provider":    "auto",      # "auto" (BYO-key if set, else Ollama) | "ollama" | "openai-compat"
    "ai_model":       "llama3",    # model name sent to the transport
    "ai_base_url":    "",          # OpenAI-compatible endpoint (blank = local Ollama)
    "sudo_binary":    "sudo",
    "go_bin_dir":     str(Path.home() / "go" / "bin"),
    "gem_bin_dir":    str(Path.home() / ".gem" / "ruby"),
}

# ── Privilege escalation ───────────────────────────────────────────────────────
# Prefer doas if present (OpenBSD/some Linux setups), else sudo
PRIV_CMD = "doas" if _shutil.which("doas") else "sudo"