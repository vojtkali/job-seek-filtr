"""Playwright scraper pro startupjobs.cz.

Na rozdíl od jobs.cz/prace.cz je tohle Nuxt (Vue) SPA - nabídky se do HTML
nerenderují na serveru, natahují se přes JS až po načtení stránky v
prohlížeči. Skutečné API, které k tomu web používá (/api/search-offers,
zjištěné z JS bundlu stránky), při přímém volání zvenčí vrací 404 - frontend
na něj jde přes nějaké interní routování, které se nepodařilo
reverse-engineerovat bez spuštění prohlížeče. Jediná zbývající cesta je
tedy stránku v headless Chromiu opravdu vykreslit a počkat, až si nabídky
sám natáhne.

Extrakce karet (BOOTSTRAP_CARD_SELECTOR atd.) zatím není doladěná na
skutečné vykreslené HTML - viz TODO ve scrape_startupjobs().
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .common import USER_AGENT, Offer

log = logging.getLogger(__name__)

PAGE_TIMEOUT_MS = 30_000


def scrape_startupjobs(
    search_urls: list[str],
    max_pages: int,
    already_seen: set[str] | None = None,
    debug_dir: Path | None = None,
) -> list[Offer]:
    already_seen = already_seen or set()
    offers: dict[str, Offer] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)

            for start_url in search_urls:
                try:
                    page.goto(start_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    log.warning("startupjobs.cz: timeout při načítání %s", start_url)
                    continue

                # "networkidle" na téhle stránce nejspíš nikdy nenastane (běží
                # tam Intercom chat widget s trvalým spojením) - zkusíme ho
                # jako bonus s krátkým timeoutem, ale nespoléháme na něj.
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(2000)

                if debug_dir:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    (debug_dir / "startupjobs_rendered.html").write_text(
                        page.content(), encoding="utf-8"
                    )

                # TODO: doplnit skutečnou extrakci karet, jakmile se podle
                # debug_dir/startupjobs_rendered.html zjistí selektory
                # (podobně jako _extract_jobscz/_extract_pracecz v
                # site_scraper.py). Zatím vrací prázdný seznam.
        finally:
            browser.close()

    return list(offers.values())
