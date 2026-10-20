"""Non-blocking 'is a newer release out?' check against GitHub Releases, cached daily."""
import json
import os
import time
import urllib.request
from itertools import takewhile
from pathlib import Path

from .constants import REPO_NAME, REPO_OWNER, USER_CONFIG_DIR, VERSION

_CACHE = USER_CONFIG_DIR / "update_check.json"
_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
_TTL = 86400   # hit the network at most once a day; otherwise serve the cache

_memo_done = False   # process-lifetime memo: the header re-renders every keystroke
_memo_val: str | None = None


def _parse(v: str) -> tuple[int, int, int]:
    """'v3.0.1' -> (3,0,1). Non-numeric parts (pre-release tags) degrade to 0, never raise."""
    nums = []
    for part in v.lstrip("vV").split(".")[:3]:
        digits = "".join(takewhile(str.isdigit, part))   # "0-rc1" -> "0", not "01"
        nums.append(int(digits) if digits else 0)
    return tuple(nums + [0] * (3 - len(nums)))  # type: ignore[return-value]


def _fetch_latest(timeout: float) -> str:
    req = urllib.request.Request(
        _API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"{REPO_NAME}/{VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URL)
        return json.load(r).get("tag_name") or ""


def _cached_latest(timeout: float) -> str:
    try:
        data = json.loads(_CACHE.read_text())
        if time.time() - data.get("ts", 0) < _TTL:
            return data.get("latest", "")
    except Exception:
        pass
    latest = _fetch_latest(timeout)
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({"ts": time.time(), "latest": latest}))
    except Exception:
        pass
    return latest


def latest_if_newer(timeout: float = 2.0) -> str | None:
    """Latest release tag (without the 'v') if newer than the running one, else None. Never raises."""
    global _memo_done, _memo_val
    if _memo_done:
        return _memo_val
    _memo_done = True
    _memo_val = None

    if os.environ.get("HACKINGTOOL_NO_UPDATE_CHECK"):
        return None
    try:
        from . import config
        if not config.load().get("update_check", True):
            return None
    except Exception:
        pass

    try:
        latest = _cached_latest(timeout)
        if latest and _parse(latest) > _parse(VERSION):
            _memo_val = latest.lstrip("vV")
    except Exception:
        _memo_val = None
    return _memo_val


def install_method() -> str:
    """Best-effort guess at how hackingtool was installed, for the /update hint."""
    p = str(Path(__file__).resolve())
    if Path("/.dockerenv").exists():
        return "docker"
    if "/pipx/" in p:
        return "pipx"
    if (Path(__file__).resolve().parents[2] / ".git").exists():
        return "source"
    if "dist-packages" in p:
        return "apt"
    return "pip"


def upgrade_commands() -> tuple[str, dict[str, str]]:
    """(detected_method, {method: upgrade command}). The dialog shows all; detection just picks the default."""
    repo = Path(__file__).resolve().parents[2]
    cmds = {
        "pipx":   f"pipx upgrade {REPO_NAME}",
        "pip":    f"pip install -U {REPO_NAME}",
        "apt":    f"sudo apt install --only-upgrade {REPO_NAME}",
        "docker": f"docker pull hardikzinzu/{REPO_NAME}",
        "source": f"git -C {repo} pull",
    }
    return install_method(), cmds
