"""AI2: tool + free-text goal -> one runnable command. Curated-first, AI fills gaps.

Guardrails (project posture is no-fabrication, authorized-targets-only):
- **Curated first.** The goal is matched against the tool's own ``USAGE`` cheatsheet
  (``[(task, command)]``) with ``difflib``. A close match returns that *exact*
  curated command — offline, zero fabrication.
- **AI only fills the gap.** If nothing curated matches AND a model is reachable
  (via ``ai_recommend.ask`` — BYO-key endpoint or local Ollama), the model is
  asked for one command, grounded on the tool's own USAGE as few-shot examples,
  temperature 0.
- **Structural anti-fabrication (the AI1 analog).** An AI command whose first
  token isn't a binary already seen in the curated USAGE is dropped — same shape
  as AI1 dropping tags outside the taxonomy. Stops the hashcat view from ever
  emitting an ``nmap ...`` line.
- **Never executes.** Callers display the command for copy-paste only; the AI leg
  is labeled unverified.
"""
import difflib
import re

from hackingtool import skill
from hackingtool.ai_recommend import ask

_CUTOFF = 0.6                              # same close-match bar as recommend_tools
_FENCE = re.compile(r"^```[a-z]*\n?|\n?```$")   # strip ```sh ... ``` code fences

# Shared operator charter (persona + safety + anti-fabrication) + AI2 output contract.
_PROMPT = skill.charter() + "\n\n" + (
    "Task: output ONE shell command for the tool {tool}, tailored to the user's goal.\n"
    "Base it strictly on these VERIFIED example commands for {tool}:\n{examples}\n"
    "Reply with the single command line only, no prose, no markdown. "
    "If {tool} cannot do the goal, reply exactly NO-COMMAND.\n"
    "GOAL: {goal}\n"
)


def _known_binaries(usage) -> set[str]:
    """Leading token of every curated command — the tool's real invocations."""
    return {cmd.split()[0] for _task, cmd in usage if cmd.split()}


def _match_curated(goal: str, usage):
    """Closest curated (task, command) whose task matches the goal, or ``None``."""
    tasks = [task for task, _cmd in usage]
    hit = difflib.get_close_matches(goal.lower(), [t.lower() for t in tasks],
                                    n=1, cutoff=_CUTOFF)
    if not hit:
        return None
    idx = [t.lower() for t in tasks].index(hit[0])
    return usage[idx][1]


def _parse_command(reply: str | None, usage) -> str | None:
    """First real command line from a model reply, gated by known binaries."""
    if not reply:
        return None
    line = _FENCE.sub("", reply.strip()).strip()
    line = next((ln.strip() for ln in line.splitlines() if ln.strip()), "")
    if not line or line == "NO-COMMAND":
        return None
    if line.split()[0] not in _known_binaries(usage):
        return None                        # foreign binary -> likely fabricated
    return line


def build_command(tool_title: str, usage, goal: str):
    """(source, command) for ``goal`` on ``tool_title``, or ``None``.

    ``source`` is ``"curated"`` (exact, verified) or ``"ai"`` (unverified).
    Needs a non-empty ``usage`` to ground on; returns ``None`` otherwise.
    """
    if not usage or not goal.strip():
        return None

    curated = _match_curated(goal, usage)
    if curated is not None:
        return ("curated", curated)

    examples = "\n".join(f"- {task}: {cmd}" for task, cmd in usage)
    reply = ask(_PROMPT.format(tool=tool_title, examples=examples, goal=goal))
    command = _parse_command(reply, usage)
    if command is None:
        return None
    return ("ai", command)


def demo():
    """Self-check: curated match, binary guard, NO-COMMAND, empty usage."""
    usage = [
        ("crack MD5 with a wordlist", "hashcat -m 0 -a 0 hash.txt rockyou.txt"),
        ("show already-cracked results", "hashcat -m 0 hash.txt --show"),
    ]
    # Curated leg returns the exact verified command, no model needed.
    src, cmd = build_command("Hashcat", usage, "crack an md5 with a wordlist")
    assert src == "curated" and cmd == "hashcat -m 0 -a 0 hash.txt rockyou.txt", cmd

    # Foreign-binary AI reply is dropped (fabrication guard).
    assert _parse_command("nmap -sV target", usage) is None
    # NO-COMMAND and fenced known-binary command.
    assert _parse_command("NO-COMMAND", usage) is None
    assert _parse_command("```sh\nhashcat -m 100 hash.txt\n```", usage) == \
        "hashcat -m 100 hash.txt"

    # No grounding -> no feature.
    assert build_command("Hashcat", [], "anything") is None
    assert build_command("Hashcat", usage, "  ") is None
    print("OK — ai_command guardrails hold")


if __name__ == "__main__":
    demo()
