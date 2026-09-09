"""Orchestrátor: stáhne nabídky z jobs.cz a prace.cz, porovná s tím, co už
jsme dřív viděli (state.json), odfiltruje blacklistované firmy a výsledek
zapíše jako den-po-dni historii pro statickou stránku.

Protože si pamatujeme ID už viděných nabídek (ne přesné datum zveřejnění),
funguje to samo i přes víkend: pokud skript neběžel v sobotu ani v neděli,
pondělní běh prostě ukáže úplně všechno, co je nové oproti poslednímu běhu
(pátku) - žádné speciální větvení pro "je pondělí" není potřeba.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .common import (
    DATA_DIR,
    REPO_ROOT,
    is_blacklisted,
    load_blacklist,
    load_state,
    save_state,
)
from .site_scraper import scrape_site

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

CONFIG_PATH = REPO_ROOT / "config" / "settings.yaml"
HISTORY_PATH = DATA_DIR / "history.json"
SITE_DATA_PATH = REPO_ROOT / "site" / "data.json"
HISTORY_KEEP_RUNS = 30
SITE_SHOW_RUNS = 14


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return []


def save_history(history: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history[-HISTORY_KEEP_RUNS:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run() -> int:
    config = load_config()
    state = load_state()
    blacklist = load_blacklist()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    state.setdefault("sites", {})
    seen_limit = config.get("seen_ids_limit", 5000)

    run_new_offers: list[dict] = []
    warnings: list[str] = []
    counts: dict[str, dict] = {}

    for site_key in ("jobscz", "pracecz"):
        site_cfg = config.get(site_key, {})
        if not site_cfg.get("enabled", True):
            continue

        site_state = state["sites"].setdefault(site_key, {"seen_ids": [], "last_run": None})
        seen_ids = set(site_state.get("seen_ids", []))

        log.info("Stahuji %s...", site_cfg.get("name", site_key))
        offers = scrape_site(
            site_key=site_key,
            search_urls=site_cfg.get("search_urls", []),
            detail_url_pattern=site_cfg.get("detail_url_pattern", ""),
            employer_hints=site_cfg.get("employer_hints", []),
            salary_hints=site_cfg.get("salary_hints", []),
            max_pages=site_cfg.get("max_pages", 5),
            already_seen=seen_ids,
            pagination_param=site_cfg.get("pagination_param"),
        )

        total_found = len(offers)
        new_count = 0
        blacklisted_count = 0

        for offer in offers:
            if offer.id in seen_ids:
                continue
            new_count += 1
            seen_ids.add(offer.id)
            if is_blacklisted(offer.employer, blacklist):
                blacklisted_count += 1
                continue
            offer.found_at = now_iso
            run_new_offers.append(offer.to_dict())

        # capni si seen_ids na rozumnou velikost, ať soubor neroste do nekonečna
        if len(seen_ids) > seen_limit:
            seen_ids = set(list(seen_ids)[-seen_limit:])

        site_state["seen_ids"] = sorted(seen_ids)
        site_state["last_run"] = now_iso
        counts[site_key] = {
            "total_found": total_found,
            "new": new_count,
            "blacklisted": blacklisted_count,
        }

        if total_found == 0:
            warnings.append(
                f"{site_cfg.get('name', site_key)}: nenalezena žádná nabídka. "
                "Scraper pravděpodobně potřebuje seřídit (zkontroluj search_urls "
                "a detail_url_pattern v config/settings.yaml)."
            )
        log.info(
            "%s: nalezeno %d, nových %d, blokovaných %d",
            site_key, total_found, new_count, blacklisted_count,
        )

    save_state(state)

    history = load_history()
    history.append(
        {
            "run_at": now_iso,
            "offers": run_new_offers,
            "counts": counts,
            "warnings": warnings,
        }
    )
    save_history(history)

    site_payload = {
        "generated_at": now_iso,
        "runs": history[-SITE_SHOW_RUNS:],
    }
    SITE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SITE_DATA_PATH.write_text(
        json.dumps(site_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log.info("Hotovo. Nových nabídek celkem: %d", len(run_new_offers))
    return 0


if __name__ == "__main__":
    sys.exit(run())
