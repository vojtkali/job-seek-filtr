"""Sdílené věci pro scraper: model nabídky, stav mezi běhy, blacklist."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CONFIG_DIR = REPO_ROOT / "config"
STATE_PATH = DATA_DIR / "state.json"
BLACKLIST_PATH = CONFIG_DIR / "blacklist.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class Offer:
    id: str
    site: str
    title: str
    url: str
    employer: str | None = None
    salary: str | None = None
    posted: str | None = None
    found_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"sites": {}}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_blacklist() -> list[str]:
    """Vrací položky blacklistu v původním tvaru (bez #komentářů/prázdných
    řádků), zachovává velikost písmen - kvůli zobrazení na stránce.
    Porovnávání proti nabídkám dělá is_blacklisted case-insensitive samo."""
    if not BLACKLIST_PATH.exists():
        return []
    entries = []
    for line in BLACKLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def _term_pattern(term: str) -> re.Pattern:
    """Víceslovný termín se hledá po jednotlivých slovech v daném pořadí,
    ne jako jeden pevný řetězec - české názvy pozic mají často mezi slovy
    vloženou genderovou příponu (např. "Prodejce/-kyně po telefonu" pro
    termín "prodejce po telefonu"), takže přesná shoda by je minula."""
    words = term.split()
    pattern = r".*?".join(re.escape(w) for w in words)
    return re.compile(pattern, re.IGNORECASE)


def is_blacklisted(offer: Offer, blacklist: list[str]) -> bool:
    """Blacklist se hledá (case-insensitive, přes libovolné znaky mezi
    slovy) v názvu pozice i ve jméně zaměstnavatele - jeden seznam pokrývá
    obojí (firmy i klíčová slova jako "stavbyvedoucí")."""
    haystack = f"{offer.title} {offer.employer or ''}"
    return any(_term_pattern(term).search(haystack) for term in blacklist)


_WS_RE = re.compile(r"\s+")


def clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    text = _WS_RE.sub(" ", text).strip()
    return text or None
