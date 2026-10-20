"""findings.json -> Markdown report."""
from pathlib import Path

from hackingtool.engagement import Engagement
from hackingtool.findings import load_findings, Finding

_KIND_TITLES = {"subdomain": "Subdomains", "service": "Live Services",
                "vulnerability": "Vulnerabilities"}
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_report(e: Engagement, findings=None) -> str:
    """Deterministic facts-table report as a Markdown string (no file write).

    The single source of report truth: findings/severities/targets/tools come
    straight from ``findings.json``. AI4 reuses this verbatim as its verified
    appendix so the model never has to emit the facts. Pass ``findings`` to reuse an
    already-loaded snapshot (keeps narrative and appendix consistent); else re-reads.
    """
    if findings is None:
        findings = load_findings(e.findings_file)
    lines: list[str] = [f"# Engagement: {e.name}", ""]
    lines.append(f"- **Targets:** {', '.join(e.targets) or '(none)'}")
    lines.append(f"- **Scope in:** {', '.join(e.scope_in) or '(none)'}")
    lines.append(f"- **Scope out:** {', '.join(e.scope_out) or '(none)'}")
    lines.append(f"- **Created:** {e.created}")
    lines.append(f"- **Total findings:** {len(findings)}")
    lines.append("")

    if not findings:
        lines.append("_No findings recorded yet._")
        return "\n".join(lines)

    for kind, title in _KIND_TITLES.items():
        group = [f for f in findings if f.kind == kind]
        if not group:
            continue
        lines.append(f"## {title} ({len(group)})")
        lines.append("")
        lines.append("| Severity | Name | Target | Tool |")
        lines.append("|---|---|---|---|")
        for f in sorted(group, key=lambda f: _SEV_ORDER.get(f.severity, 9)):
            lines.append(f"| {f.severity} | {_cell(f.name)} | {_cell(f.target)} | {f.source_tool} |")
        lines.append("")

    return "\n".join(lines)


def generate_report(e: Engagement) -> Path:
    e.report_file.write_text(render_report(e))
    return e.report_file
