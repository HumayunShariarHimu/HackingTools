"""Sequential, stdin-driven pipeline runner. list-form subprocess only."""
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml

import hackingtool.findings as findings_mod
from hackingtool.engagement import Engagement

PIPELINES_DIR = Path(__file__).resolve().parent / "pipelines"
STEP_TIMEOUT = 1800  # 30 min per step; ponytail: bump if a step legitimately runs longer


def load_pipeline(name: str) -> dict:
    return yaml.safe_load((PIPELINES_DIR / f"{name}.yaml").read_text())


def _host_of(line: str) -> str:
    """Extract the hostname from a forward line that may be a bare host or a URL."""
    if "://" in line:
        return urlparse(line).hostname or line
    return line.split("/")[0].split(":")[0]


def run_pipeline(e: Engagement, pipeline_name: str = "recon") -> list[findings_mod.Finding]:
    pipeline = load_pipeline(pipeline_name)
    e.raw_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    all_findings: list[findings_mod.Finding] = []
    forward: list[str] = list(e.targets)

    for step in pipeline["steps"]:
        tool = step["tool"]
        if shutil.which(tool) is None:
            e.log(f"skip {tool}: not installed (install it from the menu)")
            forward = []
            continue
        stdin = "\n".join(e.targets if step["input"] == "targets" else forward)
        try:
            proc = subprocess.run([tool, *step["args"]], input=stdin,
                                  capture_output=True, text=True, timeout=STEP_TIMEOUT,
                                  encoding="utf-8", errors="replace")  # a stray non-UTF8 byte must not abort the run
            raw = proc.stdout
            if proc.returncode != 0:
                tail = (proc.stderr or "").strip().splitlines()[-3:]
                e.log(f"{tool}: exit {proc.returncode}; stderr: {' | '.join(tail)}")
        except subprocess.TimeoutExpired as exc:
            raw = exc.stdout or ""                       # keep records emitted before the deadline
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            (e.workspace / step["output"]).write_text(raw, encoding="utf-8")
            parsed, _ = findings_mod.PARSERS[step["parser"]](raw, ts)
            all_findings.extend(parsed)
            e.log(f"timeout {tool} after {STEP_TIMEOUT}s; salvaged {len(parsed)} finding(s)")
            forward = []                                 # incomplete step → don't forward to the next
            continue
        except OSError as exc:
            e.log(f"error {tool}: {exc}")
            forward = []
            continue
        (e.workspace / step["output"]).write_text(raw, encoding="utf-8")
        parsed, forward = findings_mod.PARSERS[step["parser"]](raw, ts)
        if e.scope_out:
            kept = []
            for line in forward:
                if e.is_excluded(_host_of(line)):
                    e.log(f"scope-out: dropped discovered {line} (matches exclusion)")
                else:
                    kept.append(line)
            forward = kept
        e.log(f"{tool}: {len(parsed)} findings, {len(forward)} forwarded")
        all_findings.extend(parsed)

    findings_mod.save_findings(e.findings_file, all_findings)
    e.add_run({"pipeline": pipeline_name, "at": ts, "findings": len(all_findings)})
    return all_findings
