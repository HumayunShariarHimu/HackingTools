"""AI2 build_command: curated-first, AI-gap fill, anti-fabrication binary guard."""
import hackingtool.ai_command as ai_command

USAGE = [
    ("crack MD5 with a wordlist", "hashcat -m 0 -a 0 hash.txt rockyou.txt"),
    ("show already-cracked results", "hashcat -m 0 hash.txt --show"),
]


def test_curated_match_returns_exact_command():
    src, cmd = ai_command.build_command("Hashcat", USAGE, "crack an md5 with a wordlist")
    assert src == "curated"
    assert cmd == "hashcat -m 0 -a 0 hash.txt rockyou.txt"


def test_foreign_binary_dropped():
    # AI reply naming another tool is fabrication -> dropped.
    assert ai_command._parse_command("nmap -sV target", USAGE) is None


def test_no_command_sentinel():
    assert ai_command._parse_command("NO-COMMAND", USAGE) is None
    assert ai_command._parse_command(None, USAGE) is None


def test_code_fence_stripped_and_known_binary_kept():
    assert ai_command._parse_command("```sh\nhashcat -m 100 hash.txt\n```", USAGE) == \
        "hashcat -m 100 hash.txt"


def test_empty_usage_or_goal_returns_none():
    assert ai_command.build_command("Hashcat", [], "anything") is None
    assert ai_command.build_command("Hashcat", USAGE, "   ") is None


def test_ai_leg_used_only_when_no_curated_match(monkeypatch):
    monkeypatch.setattr(ai_command, "ask", lambda p: "hashcat -m 1800 shadow.txt")
    src, cmd = ai_command.build_command("Hashcat", USAGE, "crack a sha512crypt shadow entry")
    assert src == "ai"
    assert cmd == "hashcat -m 1800 shadow.txt"


def test_ai_leg_none_when_unreachable(monkeypatch):
    monkeypatch.setattr(ai_command, "ask", lambda p: None)
    assert ai_command.build_command("Hashcat", USAGE, "some novel uncurated goal xyz") is None
