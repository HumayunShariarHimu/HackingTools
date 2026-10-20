"""Tool discovery (`/find`): catalog-first, then the GitHub search API.

Deterministic and model-free by design — the refusal filter runs before any
network I/O, and repo metadata never reaches an instruction path. Suggest
only: nothing here clones, installs, or runs anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import log10
from pathlib import Path

from hackingtool.ai_recommend import keyword_match
from hackingtool.catalog_owners import CATALOG_OWNERS
from hackingtool.tags import TAXONOMY

_SEARCH_URL = "https://api.github.com/search/repositories"
_TIMEOUT = 8
_TOP = 5

# Matched against the repo NAME ONLY. Matching the description too measured a
# net-zero improvement while killing Sublist3r ("list"), kubescape ("resources"),
# mentalist and flare-vm ("collection"). Demotion, not exclusion: a pro
# searching "sql injection payloads" genuinely wants SecLists.
_DOCS_RE = re.compile(
    r"(^|[-_])awesome([-_]|$)|(^|[-_])(lists?|wordlists?|payloads?|dicts?)([-_]|$)"
    r"|cheat.?sheets?|tutorials?|courses?|roadmaps?|writeups?|(^|[-_])notes?$"
    r"|learning|100.?days|interview", re.I)

_DOC_LANGS = {None, "", "Markdown", "HTML", "TeX"}

# Out-of-scope intents refused before any search. Each maps a matched need to a
# short authorized alternative ("" = plain refusal, no adjacent capability offered).
# Data-driven: adding a category is one entry.
#
# The "evasion" category is checked separately (see _refuse), ahead of the
# defensive-intent guard below: its own keys ("evade detection", "bypass
# antivirus") contain the word "detect"/"antivirus" that the guard would
# otherwise treat as blue-team phrasing, wrongly waving through "evade
# detection on the host". Checking evasion first keeps that phrase refused
# while still letting "detect a SYN flood" through via the guard.
_EVASION_KEYS = ("evade detection", "bypass antivirus", "disable edr", "hide from soc")
_EVASION_ALT = "Detection-evasion for offensive use is out of scope."

# "avoid logging" was dropped from _EVASION_KEYS: unlike its siblings it has no
# offensive-only phrasing to anchor on (a dev asking to avoid logging secrets
# is indistinguishable from an attacker avoiding logging by substring alone),
# and no regression case requires refusing it.
_REFUSALS: list[tuple[tuple[str, ...], str]] = [
    # "jammer" is safe where bare "jam" was not — neither "jamf" nor "jamstack"
    # contains it. "flood" is likewise safe now that the defensive guard runs
    # first: "detect a SYN flood" exits before this table is consulted.
    (("jamming", "jammer", "deauth flood"),
     "Jamming is a denial-of-service attack and is out of scope. For authorized "
     "work, wifi AUDITING tools test your own/scoped networks: aircrack-ng, "
     "hcxtools, wifite (offline WPA/WPA2 handshake cracking)."),
    (("ddos", "dos attack", "flood", "take down", "take it down", "knock offline",
      "stress the server", "booter", "stresser"),
     "Denial-of-service / flooding is destructive and out of scope."),
    (("mass scan the internet", "scan the whole internet", "spray every",
      "mass target", "build a botnet", "run a botnet", "deploy ransomware",
      "build ransomware", "keylogger for", "steal credentials from"),
     "Mass-targeting / malware use is out of scope for authorized testing."),
]


@dataclass
class Repo:
    """One GitHub search hit, reduced to the fields we are allowed to read."""
    full_name: str
    description: str
    url: str
    stars: int
    forks: int
    pushed_at: str
    created_at: str
    archived: bool
    fork: bool
    license: str
    language: str
    topics: list[str] = field(default_factory=list)
    owner: str = ""
    owner_type: str = ""
    score: float = 0.0
    why: list[str] = field(default_factory=list)

    @property
    def clone_cmd(self) -> str:
        """Display-only. Nothing in this module executes it."""
        return f"git clone {self.url}"


@dataclass
class Rewrite:
    """How a plain-English need was turned into GitHub search terms."""
    tags: list[str] = field(default_factory=list)
    topic: str = ""
    jargon: str = ""
    source: str = "raw"          # "intents" | "keyword" | "raw"


@dataclass
class DiscoveryResult:
    need: str = ""
    refused: str = ""            # "" == allowed
    rewrite: Rewrite = field(default_factory=Rewrite)
    catalog: list = field(default_factory=list)
    repos: list[Repo] = field(default_factory=list)
    note: str = ""


_DEFENSIVE_RE = re.compile(
    r"detect|detection|\bhunt\w*|analy|forensic|mitigat|defen|blue.?team|incident")
# Discussing AV/EDR false positives is triage/analyst work, never evasion —
# carve it out before the (more literal) evasion-key check below.
_FALSE_POSITIVE_RE = re.compile(r"false positives?")


def _refuse(need: str) -> str:
    """Charter filter: refusal text for out-of-scope needs, else ''. No model."""
    low = (need or "").lower()
    # The false-positive carve-out belongs INSIDE the evasion check, not ahead
    # of it: as a top-level early return it bypassed every category, so
    # "build a botnet false positive" was allowed through.
    if any(k in low for k in _EVASION_KEYS) and not _FALSE_POSITIVE_RE.search(low):
        return _EVASION_ALT
    if _DEFENSIVE_RE.search(low):
        return ""  # defensive/DFIR intent — never refuse blue-team work
    for keys, alt in _REFUSALS:
        if any(k in low for k in keys):
            return alt
    return ""


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _months(since: datetime | None, now: datetime) -> float:
    return (now - since).days / 30.44 if since else 0.0


def _is_docs_repo(repo: Repo) -> bool:
    """True for docs/list/course repos — by NAME only. See _DOCS_RE."""
    name = repo.full_name.split("/")[-1]
    return bool(_DOCS_RE.search(name))


_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "is",
    "with", "that", "this", "from", "by", "as", "your", "you", "its",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOPWORDS}


def _need_terms(rewrite: Rewrite) -> set[str]:
    """Terms the need cares about: tags, topic, jargon — split on hyphens too
    so a tag like "sql-injection" also matches a description word "injection"."""
    terms: set[str] = set()
    for chunk in (*rewrite.tags, rewrite.topic):
        terms.update(_words(chunk.replace("-", " ")))
    terms.update(_words(rewrite.jargon))
    return terms


def _topic_terms(repo: Repo) -> set[str]:
    """Structured, curated signal: GitHub topics the maintainer picked."""
    terms: set[str] = set()
    for topic in repo.topics:
        terms.update(_words(topic.replace("-", " ")))
    return terms


def _text_terms(repo: Repo) -> set[str]:
    """Free-text signal: description + repo name. Unconstrained prose is the
    easier thing for a maintainer to keyword-stuff than a visible topic list,
    so callers must weight this lower than _topic_terms (see _score)."""
    terms = _words(repo.description)
    terms.update(_words(repo.full_name.split("/")[-1].replace("-", " ").replace("_", " ")))
    return terms


def _score(repo: Repo, now: datetime, rewrite: Rewrite | None = None) -> float:
    """Additive, explainable rank. Ported from libraries.io SourceRank's design.

    Staleness is a soft demotion, never a filter: 75% of genuinely unmaintained
    projects committed within the last year (Coelho et al., ESEM'18), and the
    best single cutoff is only 66% accurate (Avelino et al., ESEM'19). A hard
    cutoff would delete THC-Hydra and John the Ripper.
    """
    why: list[str] = []
    score = log10(max(repo.stars, 1)) + 0.5 * log10(max(repo.forks, 1))
    why.append(f"{repo.stars}★")

    age_mo = _months(_parse_ts(repo.created_at), now)
    stale_mo = _months(_parse_ts(repo.pushed_at), now)

    if repo.license:
        score += 1.0
    if repo.description and len(repo.description) > 30:
        score += 1.0
    if repo.owner in CATALOG_OWNERS:
        score += 1.0
        why.append("trusted author (ships in our catalog)")
    if age_mo >= 12:
        score += 1.0
    if stale_mo <= 12:
        score += 1.0
        why.append("active")
    else:
        why.append(f"quiet {int(stale_mo)}mo")
    if repo.language not in _DOC_LANGS:
        score += 1.0

    if repo.fork:
        score -= 2.0
        why.append("fork")
    if _is_docs_repo(repo):
        score -= 3.0
        why.append("docs/list repo")
    if age_mo < 3:
        score -= 2.0
        why.append("brand new")

    if rewrite is not None:
        need_terms = _need_terms(rewrite)
        if need_terms:
            # Topics are curated/visible and get full credit; description+name
            # are unconstrained prose (cheaper to keyword-stuff) and get half
            # credit, only for terms topics didn't already cover.
            matched_topic = need_terms & _topic_terms(repo)
            matched_text = (need_terms & _text_terms(repo)) - matched_topic
            if matched_topic or matched_text:
                # One combined cap of 3 matched terms, not one cap per bucket —
                # topic terms take slots first (curated signal wins ties), then
                # any leftover slots go to text-only terms at half weight.
                # Otherwise a repo stuffing 3 terms into topics AND 3 different
                # terms into description could net 6.75, beating the pre-fix
                # flat scheme's 4.5 ceiling instead of capping it.
                topic_slots = min(len(matched_topic), 3)
                text_slots = min(len(matched_text), 3 - topic_slots)
                score += 1.5 * topic_slots + 0.75 * text_slots
                why.append(f"matches: {', '.join(sorted(matched_topic | matched_text)[:3])}")
            else:
                score -= 3.0
                why.append("no keyword overlap with need")

    repo.score = score
    repo.why = why
    return score


def _rank(repos: list[Repo], now: datetime | None = None,
          rewrite: Rewrite | None = None) -> list[Repo]:
    """Drop hard-excluded repos, score the rest, return best-first."""
    now = now or datetime.now(timezone.utc)
    live = [r for r in repos if not r.archived]
    for r in live:
        _score(r, now, rewrite)
    live.sort(key=lambda r: r.score, reverse=True)
    return live


# Plain English -> (catalog tags, GitHub topic, 2-3 word jargon phrase).
# Curated and verified live against the GitHub search API; see
# docs/superpowers/specs/2026-07-26-find-intents-table.md for the evidence.
# Adding an intent is one row. Jargon is hard-capped at 3 terms: 4+ terms
# collapses GitHub's result set to near-zero (measured). Row order matters:
# first match wins (the reverse-engineering row's negative lookahead
# depends on the mobile row appearing before it).
_INTENTS: list[tuple[re.Pattern, list[str], str, str]] = [
    # --- web app testing -------------------------------------------------
    (re.compile(r"hidden director|content discovery|dirbust|director(y|ies) (brute|discovery|fuzz)"
     r"|admin (panel|page|portal)|hidden (page|endpoint|file)"
     r"|brute.?forc\w* director|web fuzz|\bffuf\b|\bgobuster\b"),
     ["fuzzing", "web"], "fuzzing", "web fuzzer"),
    (re.compile(r"sql inject|\bsqli\b|\bsqlmap\b|database inject|union select|blind sql"),
     ["sql-injection", "web"], "sql-injection", "sql injection"),
    (re.compile(r"\bxss\b|cross.?site script|javascript inject|dom (based )?xss"),
     ["xss", "web"], "xss", "xss scanner"),
    (re.compile(r"\bapi (test|secur|fuzz|pentest)|\bgraphql\b|\bswagger\b|openapi|\brest api\b|\bpostman\b"),
     ["api", "web", "fuzzing"], "api-security", "api fuzzing"),
    (re.compile(r"intercept\w*( web| http)? (proxy|request|traffic)|\bburp\b|\bmitmproxy\b"
     r"|proxy (the )?request|http proxy|repeater"),
     ["web", "mitm"], "burpsuite", "intercepting proxy"),
    (re.compile(r"crawl|spider|\bwayback\b|archived url|\bjs (file|endpoint)"
     r"|endpoint (discover|extract)|link (extract|discover)"),
     ["crawler", "web", "recon"], "web-crawler", "crawling framework"),
    (re.compile(r"source code (review|audit|scan)|\bsast\b|static (code )?analys|\blinter\b"
     r"|dependency (scan|check|audit)|\bsca\b"),
     ["vuln-scan", "scanner"], "static-analysis", "static analysis"),

    # --- recon / OSINT ---------------------------------------------------
    (re.compile(r"subdomain|sub-domain|dns (enum|recon|brute)|host(name)? enum|\bamass\b"
     r"|\bsubfinder\b|virtual host"),
     ["subdomain-enum", "dns", "recon"], "subdomain-enumeration", "subdomain enumeration"),
    (re.compile(r"\bosint\b|open.source intel|find (someone|a person)|people search"
     r"|username (search|lookup)|social media (recon|profil)|phone number"),
     ["osint", "recon"], "osint", "osint framework"),
    (re.compile(r"have i been pwned|\bpwned\b|\bbreach(es|ed)?\b"
     r"|leaked (email|password|account|credential)|credentials?.{0,12}(were|been|was) leaked"
     r"|email (lookup|osint|enum|harvest)"),
     ["osint", "credentials", "email"], "osint", "email osint"),
    (re.compile(r"secret scan|hardcoded (secret|password|credential|key)|api key (leak|expos)"
     r"|leaked (api key|token|secret)"
     r"|credentials? in (the )?(code|repo|git)|\bgit(hub)? (token|secret)"
     r"|\.env (leak|expos)|\btrufflehog\b"),
     ["git-secrets", "credentials", "scanner"], "secrets-detection", "secret scanning"),

    # --- network / infra -------------------------------------------------
    (re.compile(r"port scan|open ports|\bnmap\b|\bmasscan\b|network (scan|sweep)"
     r"|service (detect|version|enum)|host discovery|live hosts"),
     ["port-scan", "network", "scanner"], "port-scanner", "port scanner"),
    (re.compile(r"vulnerabilit(y|ies) (scan|assess)|\bcve\b|known vulnerabilit|missing patch"
     r"|\bnuclei\b|\bnessus\b|\bopenvas\b"),
     ["vuln-scan", "scanner"], "vulnerability-scanner", "vulnerability scanner"),
    (re.compile(r"packet (captur|sniff|analy)|\bpcap\b|\bwireshark\b|\btcpdump\b"
     r"|network (traffic|packet)|sniff traffic"),
     ["sniffing", "pcap", "network"], "pcap", "packet sniffer"),
    (re.compile(r"\bmitm\b|man.in.the.middle|arp (spoof|poison)|dns spoof|\bssl.?strip\b"
     r"|\bbettercap\b|network intercept"),
     ["mitm", "network", "poisoning"], "mitm", "mitm attack"),
    (re.compile(r"\bsmb\b|network share|\bsamba\b|file share (enum|access)|\bnetbios\b|\brpcclient\b"),
     ["enumeration", "network"], "smb", "smb enumeration"),
    (re.compile(r"pivot|reverse tunnel|port forward|\bsocks\d?\b|\bngrok\b|expose (a )?local"
     r"|\bchisel\b|lateral movement"),
     ["tunneling", "lateral-movement"], "tunneling", "reverse tunnel"),
    (re.compile(r"\btor\b|\banonym|hide my ip|proxy.?chain|\bvpn\b|traffic obfuscat"),
     ["anonymity", "tunneling"], "anonymity", "anonymity network"),

    # --- wireless / hardware ---------------------------------------------
    (re.compile(r"\bwi-?fi\b|\bwpa[23]?\b|\bwep\b|wireless (network|audit|security)|802\.11"
     r"|\bwlan\b|deauth|handshake captur|evil twin|aircrack|\bpmkid\b"),
     ["wireless"], "wifi-security", "wifi security"),
    (re.compile(r"firmware|\biot\b|embedded device|router (firmware|hack)|\bbinwalk\b"
     r"|\buart\b|\bjtag\b"),
     ["iot", "binary", "reversing"], "iot-security", "firmware analysis"),

    # --- cloud / container -----------------------------------------------
    (re.compile(r"kubernetes|\bk8s\b|kubectl|helm chart|cluster (security|audit|rbac)|\bkubeconfig\b"),
     ["cloud", "scanner"], "kubernetes-security", "kubernetes security"),
    (re.compile(r"docker image|container image|container scan|\bdockerfile\b|image vulnerabilit"
     r"|\bcontainer\b.{0,15}(scan|hardening|escape)"),
     ["cloud", "vuln-scan"], "container-security", "container scanning"),
    (re.compile(r"\baws\b|\bs3 bucket\b|\biam\b|cloud (security|audit|pentest|config|bucket)"
     r"|\bazure\b|\bgcp\b"),
     ["cloud", "enumeration"], "aws-security", "aws security"),

    # --- mobile ----------------------------------------------------------
    (re.compile(r"\bandroid\b|\bapk\b|\bios app\b|\bipa\b|mobile app|\bsmali\b|\bfrida\b|\bjadx\b"),
     ["mobile", "apk"], "mobile-security", "android pentesting"),

    # --- AD / Windows ----------------------------------------------------
    (re.compile(r"active directory|\bad\b (attack|enum|pentest)|kerberos|kerberoast"
     r"|domain (controller|admin)|ntlm relay|\bdcsync\b|\bbloodhound\b"
     r"|\bimpacket\b|\bldap\b"),
     ["active-directory", "kerberos", "enumeration"], "active-directory", "active directory"),

    # --- passwords / credentials -----------------------------------------
    (re.compile(r"crack.{0,20}\bhash|password crack|hash crack|\bhashcat\b|john the ripper"
     r"|rainbow table|ntlm hash|dehash"),
     ["hash-crack", "password-attack"], "password-cracking", "password cracking"),
    (re.compile(r"brute.?forc\w* (a |the )?(login|password|ssh|ftp|rdp|form|account|service)"
     r"|credential stuff|spray\w* (password|credential|o365|login)|password spray"
     r"|login (brute|attack)"),
     ["bruteforce", "password-attack", "credentials"], "brute-force", "brute force"),
    (re.compile(r"(generat|creat|build|mak\w+|custom|need a|good) \w*\s?word ?list"
     r"|word ?list (generat|creat|build)|dictionary (attack|file|generat)"
     r"|password list|\bseclists\b|\brockyou\b"),
     ["wordlist"], "wordlist", "password wordlist"),

    # --- exploitation / post-exploitation --------------------------------
    (re.compile(r"\bexploit\b|\bpoc\b|proof.of.concept|metasploit|\bmsf\b"
     r"|pwn (a|the) (box|machine|host)|public exploit|(gain|get|pop) (a )?shell"),
     ["exploitation"], "exploit", "exploit framework"),
    (re.compile(r"reverse shell|bind shell|shellcode|payload (gener|encod|craft)|\bmsfvenom\b"
     r"|\bstager\b|obfuscat\w* payload|payload.{0,20}(bypass|evad)|av (bypass|evasion)"),
     ["payload", "reverse-shell"], "reverse-shell", "reverse shell"),
    (re.compile(r"privilege escalat|\bprivesc\b|escalate (my |to )?(privile|root|admin)|\bsuid\b"
     r"|become (root|admin|system)|root the (box|machine)|post.?exploit"),
     ["privesc", "post-exploitation"], "privilege-escalation", "privilege escalation"),
    (re.compile(r"\bc2\b|command and control|\bimplant\b|\bbeacon\b|cobalt strike"
     r"|red team (framework|infra)|\bsliver\b"),
     ["c2", "post-exploitation", "persistence"], "command-and-control", "c2 framework"),
    (re.compile(r"phish|social engineer|credential harvest|fake (login|page|site)"
     r"|clone (a |the )?(website|login)|\bgophish\b|awareness (training|campaign)"),
     ["phishing", "social-engineering"], "phishing", "phishing framework"),

    # --- forensics / DFIR / malware / RE ---------------------------------
    (re.compile(r"memory (dump|forensic|analys)|ram dump|incident response|\bdfir\b"
     r"|disk (image|forensic)|\bvolatility\b|forensic (triage|artifact|image)|\bautopsy\b"),
     ["forensics", "memory-dump"], "dfir", "memory forensics"),
    (re.compile(r"malware|\bransomware\b|suspicious (file|sample|binary|attachment)"
     r"|sample (analys|triage)|\bsandbox\b|virustotal|unpack\w* (a )?binary"),
     ["malware-analysis", "binary"], "malware-analysis", "malware analysis"),
    (re.compile(r"^(?!.*\b(apk|android|ipa|smali)\b).*"   # mobile binaries -> the mobile row
     r"(reverse engineer|decompil|disassembl|binary analys|\bghidra\b|\bida pro\b"
     r"|\bradare2?\b|debugger)"),
     ["reversing", "binary"], "reverse-engineering", "reverse engineering"),
    (re.compile(r"\bexif\b|(file|image|photo|document) metadata|metadata (from|extract)"
     r"|strip metadata|\bexiftool\b"),
     ["metadata", "image", "forensics"], "exif", "exif metadata"),
    (re.compile(r"stegano|\bstego\b|hidden (message|data|file) (in|inside)"
     r"|hide (a )?(message|file|data|text) (in|inside)|\blsb\b"),
     ["steganography", "image"], "steganography", "steganography tool"),

    # --- blue team / reporting / learning ---------------------------------
    (re.compile(r"detection rule|\bsiem\b|\bsigma\b|\byara\b|threat hunt|hunt for threat"
     r"|(event|windows|security) log|log (analys|triage)"
     r"|blue.?team|\bedr\b|detection engineering"),
     ["forensics", "reference"], "threat-hunting", "threat hunting"),
    (re.compile(r"pentest report|report (generat|templat|writ)|deliverable|write.?up the"
     r"|document (the )?finding|engagement note"),
     ["reporting"], "pentest", "pentest report"),
    (re.compile(r"\bctf\b|capture the flag|hackthebox|\bhtb\b|tryhackme|\bthm\b"
     r"|practice (box|lab|machine)|wargame"),
     ["learning", "reference"], "ctf-tools", "ctf tools"),
]


def _rewrite(need: str) -> Rewrite:
    """Plain English -> GitHub search terms. Deterministic, offline, no model."""
    low = (need or "").strip().lower()
    if not low:
        return Rewrite()
    for rx, tags, topic, jargon in _INTENTS:
        if rx.search(low):
            return Rewrite(tags=list(tags), topic=topic, jargon=jargon, source="intents")
    tags = keyword_match(low, TAXONOMY, limit=3)
    if tags:
        # Tag names are already GitHub-topic-shaped (lowercase, hyphenated).
        return Rewrite(tags=tags, topic=tags[0],
                        jargon=" ".join(low.split()[:3]), source="keyword")
    words = sorted(low.split(), key=len, reverse=True)[:2]
    return Rewrite(jargon=" ".join(words), source="raw")


_CACHE_TTL = 24 * 3600
_USER_AGENT = "hackingtool/find (+https://github.com/Z4nzu/hackingtool)"


class RateLimited(Exception):
    """GitHub primary rate limit hit. Carries a human-readable reset hint."""


def _token() -> str:
    """Optional GitHub token. Ours first, then the conventional env names."""
    for name in ("HACKINGTOOL_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def _cache_key(query: str) -> str:
    """Keyed on the query ONLY — never on the token."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]


def _cache_path(query: str) -> Path:
    from hackingtool.constants import USER_CONFIG_FILE
    return USER_CONFIG_FILE.parent / "cache" / "find" / f"{_cache_key(query)}.json"


def _cache_get(query: str):
    p = _cache_path(query)
    try:
        if time.time() - p.stat().st_mtime < _CACHE_TTL:
            return json.loads(p.read_text())
    except (OSError, ValueError):
        pass
    return None


def _cache_put(query: str, payload) -> None:
    p = _cache_path(query)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
    except (OSError, TypeError):
        pass          # cache failures are never fatal


def _fetch(url: str) -> dict:
    """The single network seam. Tests monkeypatch this and nothing else."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": _USER_AGENT,
    })
    tok = _token()
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429) and exc.headers.get("x-ratelimit-remaining") == "0":
            reset = exc.headers.get("x-ratelimit-reset", "")
            wait = ""
            try:
                wait = f" (~{max(0, int(reset) - int(time.time()))}s)"
            except ValueError:
                pass
            raise RateLimited(f"GitHub search rate limit reached{wait}") from exc
        raise


def _to_repo(item: dict) -> Repo:
    """Read ONLY the allowlisted fields. Nothing else is touched."""
    lic = item.get("license") or {}
    owner = item.get("owner") or {}
    return Repo(
        full_name=item.get("full_name", ""),
        description=(item.get("description") or "").strip(),
        url=item.get("html_url", ""),
        stars=int(item.get("stargazers_count") or 0),
        forks=int(item.get("forks_count") or 0),
        pushed_at=item.get("pushed_at") or "",
        created_at=item.get("created_at") or "",
        archived=bool(item.get("archived")) or bool(item.get("disabled")),
        fork=bool(item.get("fork")),
        license=(lic.get("spdx_id") or "") if lic.get("spdx_id") != "NOASSERTION" else "",
        language=item.get("language") or "",
        topics=list(item.get("topics") or []),
        owner=owner.get("login", ""),
        owner_type=owner.get("type", ""),
    )


def _search(query: str) -> list[Repo]:
    """One search call. Cached 24h. Returns [] on any failure except RateLimited."""
    cached = _cache_get(query)
    if cached is None:
        url = (f"{_SEARCH_URL}?q={urllib.parse.quote_plus(query)}"
               f"&sort=stars&order=desc&per_page=10")
        data = _fetch(url)                       # RateLimited propagates
        cached = data.get("items") if isinstance(data, dict) else None
        cached = cached or []
        _cache_put(query, cached)
    # A tampered or foreign-format cache file (or a non-conforming API
    # response) can be any JSON shape — only ever treat dict items as repos.
    if not isinstance(cached, list):
        cached = []
    return [_to_repo(i) for i in cached if isinstance(i, dict)]


def _since(months: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=months * 30)).strftime("%Y-%m-%d")


def _catalog_matches(tag_names: list[str]) -> list:
    """Tools we already ship for these tags. Offline; never raises."""
    if not tag_names:
        return []
    try:
        from hackingtool import registry
        wanted = set(tag_names)
        return [t for c in registry.load().categories for t in c.tools
                if wanted & set(getattr(t, "TAGS", []) or [])][:5]
    except Exception:
        return []


def _found_path() -> Path:
    from hackingtool.constants import USER_CONFIG_FILE
    return USER_CONFIG_FILE.parent / "found.yaml"


def save_repo(repo: Repo, tags: list[str]) -> Path | None:
    """Persist a discovered repo to the user catalog. Display-only fields only.

    Deliberately writes NO `install:` and NO `run:` key: repo metadata is
    attacker-controllable, and registry._install_commands() turns `install:`
    into a runnable command. Discovered entries are structurally inert.

    Never raises: an unwritable home dir or a hand-edited found.yaml with an
    unexpected shape (list at the top, a non-list `tools:`, ...) must not crash
    the REPL. Returns None (and writes nothing) if the file can't be read back
    into the expected shape or can't be written — callers must not report
    success in that case.
    """
    import yaml

    from hackingtool import skill

    path = _found_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("category", {"title": "Discovered tools"})
    tools = data.setdefault("tools", [])
    if not isinstance(tools, list):
        tools = []
        data["tools"] = tools

    url = repo.url
    if any(isinstance(t, dict) and t.get("project_url") == url for t in tools):
        return path

    tools.append({
        "title": f"{skill.clean(repo.full_name.split('/')[-1])} (discovered)",
        "kind": "reference",                      # never "install"
        "tags": [t for t in tags if t in TAXONOMY],
        "description": skill.clean(repo.description)[:300],
        "project_url": url,
        "discovered": True,
    })
    try:
        from hackingtool.storage import write_text
        write_text(path, yaml.safe_dump(data, sort_keys=False))   # atomic: never truncate saved discoveries
    except OSError:
        return None
    return path


def find(need: str) -> DiscoveryResult:
    """Catalog-first discovery, then GitHub. Never raises."""
    need = (need or "").strip()
    res = DiscoveryResult(need=need)

    res.refused = _refuse(need)
    if res.refused:
        return res                                # gates the network
    if not need:
        res.note = "Usage: /find <what you are trying to do>"
        return res

    res.rewrite = _rewrite(need)
    res.catalog = _catalog_matches(res.rewrite.tags)

    arms = []
    if res.rewrite.topic:
        arms.append(f"topic:{res.rewrite.topic} pushed:>{_since(12)}")
    if res.rewrite.jargon:
        arms.append(f"{res.rewrite.jargon} stars:>500 pushed:>{_since(18)} "
                    f"archived:false fork:false")

    found: dict[str, Repo] = {}
    try:
        for query in arms:
            for repo in _search(query):
                found.setdefault(repo.full_name, repo)
        if not found and arms:
            for repo in _search(arms[-1].split(" stars:")[0]):   # relaxation ladder
                found.setdefault(repo.full_name, repo)
    except RateLimited as exc:
        res.note = (f"{exc}. Add a GitHub token to triple the limit — "
                    f"run '/config github' for the steps.")
        return res
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError,
             AttributeError):
        res.note = "GitHub unreachable — showing catalog results only."
        return res

    res.repos = _rank(list(found.values()), rewrite=res.rewrite)[:_TOP]
    if not res.repos:
        res.note = "No maintained tools matched on GitHub."
    return res


def run(need: str, ctx=None) -> None:
    """Print discovery results. All display; find() holds the logic.

    Repo-derived strings (full_name, description, license, why, catalog
    TITLE) are untrusted (they flow from maintainer-controlled GitHub
    metadata) and are markup-escape()d before hitting a markup-enabled
    console.print — otherwise embedded Rich markup like "[bold red]owned[/]"
    would be parsed as styling instead of shown literally.
    """
    from rich.markup import escape

    from hackingtool.core import console
    from hackingtool import skill

    res = find(need)

    if res.refused:
        console.print(f"[warning]Out of scope:[/warning] {skill.clean(res.refused)}")
        return
    if not res.need:
        console.print(f"[dim]{res.note}[/dim]")
        return

    if res.catalog:
        console.print("\n[success]In your toolbox (vetted)[/success]")
        for tool in res.catalog:
            title = escape(skill.clean(getattr(tool, "TITLE", "?")))
            console.print(f"  • {title}")

    if res.repos:
        console.print("\n[warning]Found on GitHub — NOT vetted by us[/warning]")
        for r in res.repos:
            name = escape(skill.clean(r.full_name))
            lic = escape(skill.clean(r.license or "no license"))
            console.print(f"\n  [bold]{name}[/bold]  {r.stars}★  {lic}")
            if r.description:
                console.print(f"    {skill.clean(r.description)}", markup=False)
            why = " · ".join(skill.clean(w) for w in r.why)
            console.print(f"    [dim]{escape(why)}[/dim]")
            console.print(f"    [dim]{escape(skill.clean(r.clone_cmd))}[/dim]")

    if res.note:
        console.print(f"\n[dim]{escape(skill.clean(res.note))}[/dim]")
    if not _token():
        console.print("[dim]Tip: '/config github' — a no-permission token triples "
                      "the search rate limit.[/dim]")

    if res.repos and sys.stdin.isatty():
        from hackingtool import prompt
        choice = prompt.simple("[a] add one to your toolbox · [Enter] done: ")
        if (choice or "").strip().lower().startswith("a"):
            pick = prompt.simple(f"which? 1-{len(res.repos)}: ")
            try:
                idx = int(pick.strip()) - 1
                if not 0 <= idx < len(res.repos):
                    raise ValueError
                repo = res.repos[idx]
            except (ValueError, IndexError):
                return
            path = save_repo(repo, res.rewrite.tags)
            if path is None:
                console.print("[warning]Could not save — check permissions on "
                              "~/.hackingtool.[/warning]")
            else:
                console.print(f"[success]Added.[/success] [dim]{path}[/dim]")


GITHUB_TOKEN_STEPS = """\
/find works without a token (10 searches/min). A token raises that to 30/min.
Create one that grants NOTHING beyond public read:

  1. GitHub → your profile picture → Settings
  2. Left sidebar → Developer settings
  3. Personal access tokens → Fine-grained tokens → Generate new token
  4. Name it (e.g. hackingtool-find) and pick an expiration
  5. Resource owner: yourself. Repository access: leave the default —
     do NOT select any repositories
  6. Permissions: select no permissions at all. (GitHub: "Tokens always
     include read-only access to all public repositories on GitHub.")
  7. Generate token and copy it
  8. Add it to ~/.hackingtool/.env (chmod 600):
         HACKINGTOOL_GITHUB_TOKEN=ghp_your-token-here

Classic tokens work too: Developer settings → Tokens (classic) → Generate
new token → tick NO scopes at all. ("A token with no assigned scopes can
only access public information.")

Then run '/config github' to verify it.
"""


def check_token() -> tuple[bool, str]:
    """Probe the configured GitHub token. Never raises, never echoes the token."""
    if not _token():
        return False, "no token configured — unauthenticated search is 10 req/min"
    try:
        data = _fetch("https://api.github.com/rate_limit")
        limit = ((data.get("resources") or {}).get("search") or {}).get("limit")
        return True, f"token OK — search limit {limit} req/min"
    except RateLimited as exc:
        return False, str(exc)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "token rejected — GitHub returned unauthorized"
        return False, f"GitHub returned an error (HTTP {exc.code})"
    except (urllib.error.URLError, OSError):
        return False, "could not reach GitHub — check your network, not the token"
    except Exception as exc:
        return False, f"token rejected ({type(exc).__name__})"
