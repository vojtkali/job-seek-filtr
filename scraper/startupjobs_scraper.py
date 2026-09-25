"""Playwright scraper pro startupjobs.cz.

Na rozdíl od jobs.cz/prace.cz je tohle Nuxt (Vue) SPA - nabídky se do HTML
nerenderují na serveru, natahují se přes JS až po načtení stránky v
prohlížeči. Skutečné API, které k tomu web používá (/api/search-offers,
zjištěné z JS bundlu stránky), při přímém volání zvenčí vrací 404 - frontend
na něj jde přes nějaké interní routování, které se nepodařilo
reverse-engineerovat bez spuštění prohlížeče. Jediná zbývající cesta je
tedy stránku v headless Chromiu opravdu vykreslit a počkat, až si nabídky
sám natáhne.

Struktura zjištěná ze skutečného vykresleného HTML (SCRAPER_DEBUG_HTML):
každá nabídka je celá jeden `<a href="/nabidka/{id}/{slug}">` (dvakrát -
samostatná desktopová a mobilní varianta stejné karty, druhá se zahodí přes
dedup podle href). Jméno zaměstnavatele je v `alt` atributu loga
(`"{Firma} - logo"`), název pozice v `<div>` se třídou obsahující "text-lg"
(uvnitř bývá ještě odznak "HOT" jako `<span>`, ten se ze title odstraní).
Plat (pokud je uvedený) je jedna z položek `<ul><li>` obsahující "Kč". Datum
přidání web u nabídek v seznamu vůbec neukazuje - Offer.posted proto
zůstává vždy None.

Stránkování je přes tlačítko "Načíst další stránku", ne přes URL parametr -
nové karty se donačítají do stejné stránky (DOM), takže stačí tlačítko
kliknout a znovu přečíst obsah.
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .common import USER_AGENT, Offer, clean_text
from .site_scraper import _offer_id_from_url

log = logging.getLogger(__name__)

PAGE_TIMEOUT_MS = 30_000
DETAIL_URL_PATTERN = "/nabidka/"
LOAD_MORE_TEXT = "Načíst další stránku"


def _extract_card(anchor: Tag) -> tuple[str | None, str | None, str | None]:
    """Vrací (title, employer, salary)."""
    employer = None
    img = anchor.find("img")
    if img and img.get("alt"):
        alt = clean_text(img["alt"])
        if alt:
            employer = alt[: -len(" - logo")].strip() if alt.lower().endswith(" - logo") else alt

    title = None
    title_div = anchor.find("div", class_=lambda c: c and "text-lg" in c)
    if title_div:
        # odznak "HOT" je <span> uvnitř title divu - odstranit, ať se
        # nedostane do názvu pozice.
        clone = BeautifulSoup(str(title_div), "lxml")
        for span in clone.find_all("span"):
            span.decompose()
        title = clean_text(clone.get_text(" "))

    salary = None
    for li in anchor.select("ul li"):
        text = clean_text(li.get_text(" "))
        if text and "Kč" in text:
            salary = text
            break

    return title, employer, salary


def _offer_anchors(soup: BeautifulSoup) -> list[Tag]:
    return [
        a for a in soup.find_all("a", href=True)
        if a["href"].split("?")[0].strip("/").split("/")[0] == "nabidka"
    ]


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

                seen_hrefs: set[str] = set()
                for page_num in range(max_pages):
                    soup = BeautifulSoup(page.content(), "lxml")

                    if debug_dir and page_num == 0:
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        (debug_dir / "startupjobs.html").write_text(str(soup), encoding="utf-8")

                    new_hrefs: set[str] = set()
                    for anchor in _offer_anchors(soup):
                        href = anchor["href"]
                        if href in seen_hrefs:
                            continue
                        seen_hrefs.add(href)
                        new_hrefs.add(href)

                        full_url = urljoin(start_url, href)
                        offer_id = _offer_id_from_url(full_url, DETAIL_URL_PATTERN)
                        if not offer_id or offer_id in offers:
                            continue
                        title, employer, salary = _extract_card(anchor)
                        if not title:
                            continue
                        offers[offer_id] = Offer(
                            id=offer_id,
                            site="startupjobs",
                            title=title,
                            url=full_url,
                            employer=employer,
                            salary=salary,
                            posted=None,
                        )

                    if page_num > 0 and not new_hrefs:
                        break  # klik nic nového nedonačetl - konec výsledků

                    # early-stop jako u ostatních webů: nové karty se sem
                    # donačítají kumulativně (ne jako samostatné stránky), takže
                    # stačí jedna dávka samých už-viděných ID a dál nemá cenu
                    # klikat.
                    if already_seen and new_hrefs:
                        batch_ids = {
                            _offer_id_from_url(urljoin(start_url, h), DETAIL_URL_PATTERN)
                            for h in new_hrefs
                        }
                        if batch_ids and batch_ids <= already_seen:
                            break

                    load_more = page.get_by_role("button", name=LOAD_MORE_TEXT)
                    if load_more.count() == 0 or not load_more.first.is_enabled():
                        break
                    load_more.first.click()
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except PlaywrightTimeoutError:
                        pass
                    page.wait_for_timeout(1500)
        finally:
            browser.close()

    return list(offers.values())
