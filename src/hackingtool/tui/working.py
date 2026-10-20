"""Random Claude-style 'working…' words shown when a tool launches."""
import random

from hackingtool.tui import glyphs

WORDS = [
    "Conjuring", "Summoning", "Herding", "Probing", "Enumerating", "Brewing",
    "Forging", "Scanning", "Unpacking", "Wrangling", "Assembling", "Hacking",
    "Rummaging", "Sniffing", "Cranking", "Spelunking", "Decoding", "Marshalling",
]


def line(suffix: str = "") -> str:
    """e.g. '⏺ Conjuring… running Nmap'. suffix appended after the ellipsis."""
    word = random.choice(WORDS)
    tail = f" {suffix}" if suffix else ""
    return f"{glyphs.RUN} {word}…{tail}"
