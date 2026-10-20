"""First-class engagement + persisted workspace. Deterministic, code-owned."""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

from hackingtool.constants import USER_CONFIG_DIR

ENGAGEMENTS_ROOT = USER_CONFIG_DIR / "engagements"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Engagement:
    name: str
    created: str
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)

    @property
    def workspace(self) -> Path:
        return ENGAGEMENTS_ROOT / self.name

    @property
    def raw_dir(self) -> Path:
        return self.workspace / "raw"

    @property
    def findings_file(self) -> Path:
        return self.workspace / "findings.json"

    @property
    def report_file(self) -> Path:
        return self.workspace / "report.md"

    @property
    def report_draft_file(self) -> Path:
        return self.workspace / "report.draft.md"

    @property
    def log_file(self) -> Path:
        return self.workspace / "run.log"

    def in_scope(self, host: str) -> bool:
        if any(fnmatch(host, p) for p in self.scope_out):
            return False
        return any(fnmatch(host, p) for p in self.scope_in)

    def is_excluded(self, host: str) -> bool:
        """True if host matches any scope_out exclusion pattern."""
        return any(fnmatch(host, p) for p in self.scope_out)

    def log(self, msg: str) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a") as fh:
            fh.write(f"{_now()} {msg}\n")

    def add_run(self, run: dict) -> None:
        self.runs.append(run)
        self.save()

    def save(self) -> None:
        from hackingtool.storage import write_json
        write_json(self.workspace / "engagement.json", asdict(self), indent=2)


def load(name: str) -> Engagement | None:
    f = ENGAGEMENTS_ROOT / name / "engagement.json"
    if not f.exists():
        return None
    return Engagement(**json.loads(f.read_text(encoding="utf-8")))


def create(name: str, targets: list[str] | None = None,
           scope_in: list[str] | None = None,
           scope_out: list[str] | None = None) -> Engagement:
    targets = targets or []
    # default scope-in to the targets themselves when none given
    scope_in = scope_in if scope_in is not None else list(targets)
    e = Engagement(name=name, created=_now(), scope_in=scope_in,
                   scope_out=scope_out or [], targets=targets, runs=[])
    e.save()
    return e


def get_or_create(name: str, targets: list[str] | None = None) -> Engagement:
    existing = load(name)
    if existing:
        if targets:
            existing.targets = targets
            if not existing.scope_in:
                existing.scope_in = list(targets)
            existing.save()
        return existing
    return create(name, targets=targets)
