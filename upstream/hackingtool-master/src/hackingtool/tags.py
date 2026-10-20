"""Canonical tag taxonomy for the tool catalog.

One fixed, curated vocabulary so search / tag-filter / recommend run on facts
instead of regex guesses. Every catalog entry's ``tags`` must be a subset of
``TAXONOMY`` (a test enforces this). When curating a new tool, seed candidate
tags from its README/site, then map them onto the names below — add a new tag
here deliberately rather than inventing one per tool.

Grouped only for human readability; the check is a flat membership test.
"""

# Workflow / phase
_PHASE = {
    "recon", "osint", "scanner", "port-scan", "subdomain-enum",
    "vuln-scan", "fingerprint", "crawler", "enumeration",
    "exploitation", "post-exploitation", "privesc", "lateral-movement",
    "persistence", "reporting",
}

# Target surface
_SURFACE = {
    "web", "network", "wireless", "cloud", "mobile", "active-directory",
    "api", "dns", "email", "iot",
}

# Technique / capability
_TECHNIQUE = {
    "bruteforce", "hash-crack", "password-attack", "credentials",
    "social-engineering", "phishing", "payload", "c2", "reverse-shell",
    "mitm", "sniffing", "ddos", "fuzzing", "sql-injection", "xss",
    "steganography", "reversing", "forensics", "malware-analysis",
    "wordlist", "anonymity", "tunneling", "exfiltration",
    # Active Directory attack techniques
    "kerberos", "relay", "poisoning", "adcs",
}

# Data / artifact the tool works on
_ARTIFACT = {
    "pdf-extraction", "image", "metadata", "binary", "apk", "memory-dump",
    "pcap", "git-secrets", "document",
}

# Kind of catalog entry (not installable — a site/service/cheatsheet)
_RESOURCE = {
    "online-service", "lookup", "cheatsheet", "reference", "learning",
}

TAXONOMY: frozenset[str] = frozenset(
    _PHASE | _SURFACE | _TECHNIQUE | _ARTIFACT | _RESOURCE
)


def unknown_tags(tags) -> list[str]:
    """Return the tags that are NOT in the canonical taxonomy (empty == valid)."""
    return [t for t in (tags or []) if t not in TAXONOMY]


def demo() -> None:
    assert unknown_tags(["recon", "web"]) == []
    assert unknown_tags(["recon", "made-up-tag"]) == ["made-up-tag"]
    assert unknown_tags([]) == []
    assert "hash-crack" in TAXONOMY and "online-service" in TAXONOMY
    print(f"OK — {len(TAXONOMY)} canonical tags")


if __name__ == "__main__":
    demo()
