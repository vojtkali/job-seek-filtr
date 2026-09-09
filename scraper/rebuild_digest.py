"""Rychlé přegenerování site/data.json podle aktuálního blacklistu -
bez jakéhokoli síťového požadavku na jobs.cz/prace.cz.

Používá se při úpravě config/blacklist.txt (přes push trigger ve
workflow), aby se digest hned přefiltroval, aniž by to zbytečně
zatěžovalo cizí weby dalším scrapem."""
from __future__ import annotations

import logging
import sys

from .common import load_blacklist
from .main import build_site_payload, current_repo_info, load_history, write_site_payload

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rebuild_digest")


def run() -> int:
    history = load_history()
    blacklist = load_blacklist()
    payload = build_site_payload(history, blacklist, current_repo_info())
    write_site_payload(payload)

    total = sum(len(r["offers"]) for r in payload["runs"])
    log.info(
        "Digest přegenerován bez scrapu (blacklist má %d položek). "
        "Zobrazeno nabídek po filtru: %d.",
        len(blacklist), total,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
