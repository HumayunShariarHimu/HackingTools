"""AI4: draft a narrative engagement report from REAL findings only.

Product role: ``report.py`` renders a trustworthy facts-table; this drafts the
*narrative* a human actually hands off — an executive summary, methodology
(which pipelines ran), and per-finding impact/remediation. It is the payoff for
the bug-bounty / pentest / IR personas that the facts-table and the AI3 triage
blob don't give them.

It NEVER produces the facts: findings, severities, targets and tools come only
from the real data, rendered deterministically as an appendix
(``report.render_report``). The model writes prose *around* locked facts, so a
hijacked model can't add, hide, or re-severity a finding.

Security — this ingests untrusted, attacker-influenced scan output (a target
controls its own page titles, subdomains and banners, i.e. the ``name``/``raw``
fields). That is indirect prompt injection (OWASP LLM01). Defense in depth,
per the 2025 OWASP guidance:
  * facts stay deterministic — the model emits prose only;
  * findings are sanitized (control chars stripped) and wrapped in explicit
    ``<scan_data>`` delimiters that the system prompt marks as data, never
    instructions;
  * a groundedness check flags any URL host the narrative names that isn't in
    the real findings;
  * the draft is always labeled "AI-drafted / verify before use" and written to
    ``report.draft.md`` — it never overwrites the deterministic ``report.md``,
    and nothing here executes.
"""
import json
import re
from pathlib import Path

from hackingtool.ai_recommend import ask
from hackingtool.engagement import Engagement
from hackingtool.findings import Finding, load_findings
from hackingtool.report import render_report
from hackingtool.skill import charter, clean, sanitize, wrap_untrusted

# The persona, safety contract, and <scan_data> injection rule now come from the
# shared charter; only the report-format-specific instructions stay here.
_SYSTEM = charter() + "\n\n" + (
    "You are drafting an engagement report. Write a Markdown report with "
    "exactly these sections:\n"
    "## Executive Summary\n## Methodology\n## Findings\n\n"
    "Rules:\n"
    "- Use ONLY the findings inside <scan_data>. Do NOT invent or fabricate "
    "findings, hosts, CVEs, severities, or tools that are not present there.\n"
    "- Never change a finding's severity or target.\n"
    "- Under ## Findings, for each finding write a short Impact and a standard, "
    "generic Remediation for that finding's class.\n"
)

_URL_HOST = re.compile(r"https?://([^\s/)\]:]+)", re.IGNORECASE)   # capture the host of a URL


def _pipelines(e: Engagement) -> list[str]:
    return sorted({r.get("pipeline", "") for r in e.runs if r.get("pipeline")})


def _build_prompt(e: Engagement, findings: list[Finding]) -> str:
    ctx = {
        "engagement": clean(e.name),
        "targets": [clean(t) for t in e.targets],
        "scope_in": [clean(s) for s in e.scope_in],
        "scope_out": [clean(s) for s in e.scope_out],
        "pipelines_run": _pipelines(e),
    }
    data = wrap_untrusted(json.dumps([sanitize(f) for f in findings], indent=2))
    return f"{_SYSTEM}\nContext (trusted): {json.dumps(ctx)}\n{data}\n"


def _host_of(s: str) -> str:
    """Bare hostname of a target/scope/finding string ('https://a/x:8080' -> 'a')."""
    s = re.sub(r"^\w+://", "", (s or "").strip())
    return s.split("/")[0].split(":")[0].lower()


def _allowed_hosts(e: Engagement, findings: list[Finding]) -> set[str]:
    src = list(e.targets) + list(e.scope_in) + [f.target for f in findings]
    return {h for h in (_host_of(x) for x in src) if h}


def _ungrounded_hosts(draft: str, allowed: set[str]) -> list[str]:
    """URL hosts the narrative names that aren't in the real findings.

    High-precision on purpose: only ``http(s)://`` hosts are checked, so a plain
    word like ``report.md`` never trips it. ponytail: URL-only net — a coarse
    injection/hallucination signal, not a proof; the deterministic appendix is
    the real anchor, so misses are cheap and false alarms are the thing to avoid.
    """
    hosts = {h.lower() for h in _URL_HOST.findall(draft)}
    bad = [h for h in hosts
           if not any(h == a or h.endswith("." + a) or a.endswith("." + h)
                      for a in allowed)]
    return sorted(set(bad))


_BANNER = (
    "> **AI-drafted from real findings — verify before use.** The findings, "
    "severities and targets are rendered deterministically in the appendix; the "
    "narrative above is model-generated prose.\n"
)


def draft_report(e: Engagement) -> Path | None:
    """Write ``report.draft.md`` (narrative + deterministic appendix) and return
    its path. ``None`` when there are no findings or no model is reachable."""
    findings = load_findings(e.findings_file)
    if not findings:
        return None
    narrative = ask(_build_prompt(e, findings))
    if narrative is None:
        return None
    narrative = clean(narrative).strip()

    banner = _BANNER
    ungrounded = _ungrounded_hosts(narrative, _allowed_hosts(e, findings))
    if ungrounded:
        banner += ("> ⚠ **Ungrounded hosts in narrative** (not in findings — "
                   f"possible injection or hallucination): {', '.join(ungrounded)}\n")

    out = (f"# Engagement: {e.name} — Report (AI DRAFT)\n\n{banner}\n"
           f"{narrative}\n\n---\n\n## Appendix — Verified findings\n\n"
           f"{render_report(e, findings)}\n")
    e.report_draft_file.write_text(out)
    return e.report_draft_file


def demo() -> None:
    """Self-check: sanitize, delimiter framing, groundedness precision."""
    # Control chars in attacker-influenced fields are stripped before prompting.
    dirty = Finding("vulnerability", "https://a.example.com", "Exposed\x00 .git\x1b[hax",
                    "high", "nuclei", {"note": "x\x07y"}, "raw\x00", "T")
    s = sanitize(dirty)
    assert "\x00" not in s["name"] and "\x1b" not in s["name"], s["name"]
    assert s["details"]["note"] == "xy"

    # Prompt frames untrusted findings in <scan_data> and carries the guardrail.
    e = Engagement(name="acme", created="T", targets=["a.example.com"])
    prompt = _build_prompt(e, [dirty])
    assert "<scan_data>" in prompt and "</scan_data>" in prompt
    assert "do not invent" in prompt.lower() or "not fabricate" in prompt.lower()
    assert "\x00" not in prompt  # sanitized before it reaches the model

    # Groundedness: in-scope host passes, foreign host is flagged, filename doesn't trip.
    allowed = {"a.example.com"}
    assert _ungrounded_hosts("see https://a.example.com/x and report.md", allowed) == []
    assert _ungrounded_hosts("visit http://evil.attacker.com/x", allowed) == ["evil.attacker.com"]
    assert _host_of("https://a.example.com:8080/p") == "a.example.com"
    print("OK — ai_report: sanitize + delimiter guardrail + grounded-host check")


if __name__ == "__main__":
    demo()
