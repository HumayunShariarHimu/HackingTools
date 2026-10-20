from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.markup import escape

from hackingtool import ai_recommend, prompt, skill
from hackingtool.constants import USER_CONFIG_DIR
from hackingtool.core import console

STEP_TIMEOUT = 1800
GOALS_ROOT = USER_CONFIG_DIR / "goals"


@dataclass
class Step:
    tool: str
    argv: list[str]
    why: str
    installed: bool = False
    install_hint: str = ""   # model-suggested install one-liner (display only, never run)


@dataclass
class Plan:
    target: str
    steps: list[Step] = field(default_factory=list)


def _validate(raw: dict) -> Plan:
    """Parsed model reply -> Plan. Drops any step whose argv isn't a non-empty
    list of strings; sets installed from shutil.which(argv[0]). Never raises."""
    if not isinstance(raw, dict):
        return Plan("", [])
    target = str(raw.get("target", "")).strip()
    steps: list[Step] = []
    for s in raw.get("steps", []) if isinstance(raw.get("steps"), list) else []:
        if not isinstance(s, dict):
            continue
        argv = s.get("argv")
        if not (isinstance(argv, list) and argv
                and all(isinstance(a, str) for a in argv)):
            continue
        steps.append(Step(tool=argv[0], argv=argv, why=str(s.get("why", "")),
                          installed=shutil.which(argv[0]) is not None,
                          install_hint=str(s.get("install", "")).strip()))
    return Plan(target, steps)


_CONTRACT = (
    "\n\nTask: plan how to accomplish the security OBJECTIVE below like an expert "
    "operator, as an ordered list of steps using real command-line tools.\n"
    "Rules:\n"
    "- Reply with ONLY a JSON object, no prose: "
    '{{\"target\": \"<primary host/target or empty>\", \"steps\": '
    '[{{\"tool\": \"<binary>\", \"argv\": [\"<binary>\", \"<arg>\", ...], '
    '\"why\": \"<one line>\", \"install\": \"<one install command>\"}}]}}\n'
    "- argv MUST be a JSON array of strings (the exact command, list-form). "
    "Never use a shell: no pipes, no ';', no '&&', no '$(...)', no redirection "
    "operators as elements.\n"
    "- Never use sudo. Choose the CANONICAL, widely-used, maintained tool for each "
    "phase of the objective (e.g. active port scan → nmap/naabu/masscan; subdomain "
    "enum → subfinder/amass; web fuzzing → ffuf/feroxbuster; templated vuln scan → "
    "nuclei). Prefer tools from the TOOLBOX, but you MAY name any well-known real "
    "tool. Never invent tools or flags.\n"
    "- Match intrusiveness to the objective's wording: if it says passive / OSINT / "
    "'without touching the target', use only passive tools (shodan, censys, "
    "theHarvester, dnsx passive) and NO active scanners. Prefer least-intrusive first.\n"
    "- For each step set \"install\" to the SINGLE best install command for that tool "
    "(e.g. 'go install ...@latest', 'pipx install ...', 'sudo apt install ...'); "
    "leave it \"\" only if you are unsure.\n"
    "- Chain steps by writing/reading files in the current directory (e.g. one "
    "step writes '-o hosts.txt', the next reads '-l hosts.txt').\n"
    "TOOLBOX (grouped by category): {toolbox}\nOBJECTIVE: {objective}\n"
)


def _toolbox() -> list[dict]:
    """Catalog tools as light prompt context: title + category + one example."""
    from hackingtool import cli
    box = []
    for tool, cat in cli._collect_all_tools():
        if not getattr(tool, "TITLE", ""):
            continue
        usage = getattr(tool, "USAGE", []) or []
        example = usage[0][1] if usage else ""
        box.append({"title": tool.TITLE, "category": str(cat), "example": example})
    return box


def _toolbox_str(toolbox: list[dict]) -> str:
    """Group the toolbox by category so the planner can pick the canonical tool
    per phase (a flat list buries nmap/subfinder among 270 others)."""
    by_cat: dict[str, list[str]] = {}
    for t in toolbox:
        label = t["title"] + (f" (e.g. {t['example']})" if t.get("example") else "")
        by_cat.setdefault(t.get("category", "Other"), []).append(label)
    return "\n".join(f"[{cat}] " + "; ".join(items) for cat, items in by_cat.items()) \
        or "(none listed)"


def plan(objective: str, toolbox: list[dict]) -> Plan | None:
    """Call the model ONCE to draft a JSON plan. None when no model is reachable;
    Plan("", []) when the reply carries no usable JSON object."""
    methodology = skill.methodology()
    guide = (f"\n\nOPERATOR PLAYBOOK (canonical tools by phase — prefer these; they "
              f"are real and maintained):\n{methodology}\n") if methodology else ""
    planner_prompt = skill.charter() + guide + _CONTRACT.format(
        toolbox=_toolbox_str(toolbox), objective=objective)
    reply = ai_recommend.ask(planner_prompt)
    if reply is None:
        return None
    m = re.search(r"\{.*\}", reply, re.DOTALL)
    if not m:
        return Plan("", [])
    try:
        parsed = json.loads(m.group(0))
    except ValueError:
        return Plan("", [])
    return _validate(parsed)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "tool"


def _audit(workspace: Path, msg: str) -> None:
    """Append one UTC-timestamped line to the goal's run.log. Never raises."""
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with (workspace / "run.log").open("a") as fh:
            fh.write(f"{stamp} {msg}\n")
    except OSError:
        pass


def _workspace() -> Path:
    ws = GOALS_ROOT / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _run_step(step: Step, n: int, total: int, workspace: Path) -> None:
    """Run one approved step, list-form, in the shared workspace cwd. Prints
    output; writes it to a per-step file. Never raises."""
    console.print(f"[dim]─ step {n}/{total} ─[/dim] [cyan]{escape(' '.join(step.argv))}[/cyan]")
    try:
        # ponytail: capture-then-print; switch to Popen line-streaming if long tools feel laggy.
        proc = subprocess.run(step.argv, cwd=str(workspace), capture_output=True,
                              text=True, timeout=STEP_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        console.print(f"[error]✗ step {n} timed out after {STEP_TIMEOUT}s[/error]")
        _audit(workspace, f"step {n} TIMEOUT after {STEP_TIMEOUT}s")
        return
    except OSError as exc:
        console.print(f"[error]✗ step {n} failed to launch: {escape(str(exc))}[/error]")
        _audit(workspace, f"step {n} launch-failed: {exc}")
        return
    if proc.stdout:
        console.print(proc.stdout.rstrip(), markup=False)
    if proc.returncode != 0:
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-3:])
        console.print(f"[error]✗ exit {proc.returncode}[/error] [dim]{escape(tail)}[/dim]")
        _audit(workspace, f"step {n} exit {proc.returncode} stderr_tail={tail!r}")
    else:
        console.print(f"[success]✓ step {n} done[/success]")
        _audit(workspace, f"step {n} exit 0")
    try:
        (workspace / f"step-{n}-{_slug(step.tool)}.txt").write_text(proc.stdout or "")
    except OSError as exc:
        console.print(f"[error]✗ step {n} failed to write output: {escape(str(exc))}[/error]")


def _print_plan(plan: Plan) -> None:
    console.print(f"[bold magenta]Plan ({len(plan.steps)} steps)[/bold magenta]")
    for i, step in enumerate(plan.steps, 1):
        mark = "[success][installed][/success]" if step.installed \
            else "[error][not installed → will skip][/error]"
        console.print(f"  {i}. [cyan]{escape(' '.join(step.argv))}[/cyan]  {mark}"
                      + (f"  [dim]{escape(step.why)}[/dim]" if step.why else ""))
        if not step.installed and step.install_hint:
            console.print(f"       [yellow]↳ install:[/yellow] [cyan]{escape(step.install_hint)}[/cyan]")


def run(objective: str, ctx=None) -> None:
    """`/goal` entry: AI-plan an objective, confirm authorization, then run each
    approved step (list-form). No model → AI1 tool recommendations instead."""
    objective = (objective or "").strip()
    if not objective:
        console.print("[dim]Usage: /goal <objective>  e.g. /goal find live subdomains of example.com[/dim]")
        return

    with console.status("[bold magenta]Planning your engagement…[/bold magenta]", spinner="dots"):
        plan_ = plan(objective, _toolbox())
    if plan_ is None or not plan_.steps:
        import hackingtool.cli as cli
        console.print("[dim]No AI plan available — showing tool recommendations instead. "
                      "(Set up a model via /config.)[/dim]")
        cli.recommend_tools(objective)
        return

    _print_plan(plan_)

    target = plan_.target or "(unspecified — review each command)"
    console.print(f"\n[bold yellow]⚠  This goal will run tools against:[/bold yellow]  {escape(target)}")
    if prompt.simple(escape("   Confirm you are AUTHORIZED to test this target? [y/N] ")).strip().lower()[:1] != "y":
        console.print("[dim]Aborted — no steps run.[/dim]")
        return

    workspace = _workspace()
    try:
        (workspace / "plan.json").write_text(json.dumps({
            "objective": objective,
            "target": plan_.target,
            "steps": [{"tool": s.tool, "argv": s.argv, "why": s.why,
                       "installed": s.installed, "install": s.install_hint}
                      for s in plan_.steps],
        }, indent=2))
    except OSError:
        pass
    _audit(workspace, f"authorized target={plan_.target or '(unspecified)'} objective={objective!r}")

    total = len(plan_.steps)
    for i, step in enumerate(plan_.steps, 1):
        if not step.installed:
            console.print(f"[dim]─ step {i}/{total} ─ skip {step.tool} (not installed)[/dim]")
            _audit(workspace, f"step {i} skip (not installed): {' '.join(step.argv)}")
            continue
        ans = prompt.simple(escape(
            f"─ step {i}/{total} ─ {' '.join(step.argv)}\n"
            "  [y] run  [s] skip  [e] edit  [q] abort  › ")).strip().lower()[:1]
        _audit(workspace, f"step {i} [{ans or 'enter'}]: {' '.join(step.argv)}")
        if ans == "q":
            console.print("[dim]Aborted remaining steps.[/dim]")
            break
        if ans == "s":
            continue
        if ans == "e":
            edited = prompt.simple("  edit command › ").strip()
            if not edited:
                console.print("[dim]No command entered — skipping step.[/dim]")
                continue
            try:
                step = Step(step.tool, shlex.split(edited), step.why, installed=True)
            except ValueError as exc:
                console.print(f"[error]✗ couldn't parse command: {escape(str(exc))}[/error]")
                continue
            _audit(workspace, f"step {i} edited: {' '.join(step.argv)}")
        if ans in ("y", "e"):
            _run_step(step, i, total, workspace)

    missing = sum(1 for s in plan_.steps if not s.installed)
    if missing:
        console.print(f"[yellow]{missing} tool(s) not installed[/yellow] — install the ones you "
                      "want (see [cyan]↳ install[/cyan] above), then re-run [cyan]/goal[/cyan].")
    console.print(f"[dim]Outputs saved in {workspace}[/dim]")


def demo() -> None:
    # Validator drops malformed steps and keeps the list-form invariant.
    p = _validate({"target": "t", "steps": [
        {"tool": "a", "argv": ["a", "-x"], "why": ""},
        {"tool": "b", "argv": "bad", "why": ""},
    ]})
    assert [s.tool for s in p.steps] == ["a"]
    assert all(isinstance(x, str) for s in p.steps for x in s.argv)
    assert _validate({}).steps == []
    print("OK — ai_goal: validator drop rules + list-form invariant")


if __name__ == "__main__":
    demo()
