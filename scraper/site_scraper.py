"""Scraper výsledkové stránky jobs.cz a prace.cz.

Filtrování (lokalita, plat, obor...) dělá web sám - my mu jen předáme URL,
kterou si uživatel sám nastavil a zkopíroval z prohlížeče. Tady jen sbíráme
karty jednotlivých nabídek a z jejich HTML vytahujeme jméno firmy, plat a
(pokud to web ukazuje) čas přidání.

Struktura karet byla zjištěná ze skutečného HTML obou webů (viz
SCRAPER_DEBUG_HTML v README), ne odhadem:

- jobs.cz: karta je `article.SearchResultCard`. Zaměstnavatel je v patičce
  v `li.SearchResultCard__footerItem`, který jako jediný z položek patičky
  nemá atribut `data-test` (ostatní mají `data-test="serp-locality"` nebo
  `"serp-atmoskop"`). Plat je `span` se třídou `Tag--success` v těle karty
  (nemusí být vždy vyplněný - ne každý inzerát plat uvádí). Čas přidání je
  v elementu s `data-test-ad-status="default"` (u `"jobsTip"` je tam místo
  toho promo text jako "Příležitost dne").
- prace.cz: karta je `article[id^="advert-"]`. Hodnoty (firma, plat,
  lokalita) jsou navázané na skryté accessibility popisky - třeba
  `<span class="accessibility-hidden">Název firmy:</span>` následovaný buď
  sourozencem s hodnotou, nebo (u platu) hodnotou rovnou za popiskem ve
  stejném elementu. Datum přidání není samostatné pole, ale jeden z
  "highlight" odznaků (`span.typography-body-medium-regular.text-primary`
  v druhém seznamu highlightů karty) - ve stejném seznamu jsou ale i jiné
  odznaky nesouvisející s datem (např. "Nutně vás potřebují", "Vhodné pro
  uprchlíky z Ukrajiny"), takže se pozná podle klíčových slov
  (_PRACECZ_AGE_HINTS), ne podle třídy/pozice.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from .common import USER_AGENT, Offer, clean_text

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20


def fetch(url: str, session: requests.Session) -> BeautifulSoup | None:
    try:
        resp = session.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "cs-CZ,cs;q=0.9",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Nepodařilo se stáhnout %s: %s", url, exc)
        return None
    return BeautifulSoup(resp.text, "lxml")


def _offer_id_from_url(url: str, detail_url_pattern: str) -> str:
    """ID nabídky = část cesty hned za detail_url_pattern. Nejde spoléhat na
    čísla v URL - prace.cz má detail nabídky pod UUID (např.
    /nabidka/a59791c8-7b9d-43db-b01a-7abadf50277e/), zatímco jobs.cz pod
    čistě číselným ID (/rpd/1234567/)."""
    path = urlparse(url).path
    idx = path.find(detail_url_pattern)
    if idx == -1:
        return path.strip("/")
    remainder = path[idx + len(detail_url_pattern):].strip("/")
    return remainder.split("/")[0] if remainder else path.strip("/")


def _url_with_page(url: str, page_param: str, page_num: int) -> str:
    """page_num je 1-based, aby seděl na typický '?page=1,2,3...' vzor.

    Zachovává opakované query klíče (např. prace.cz posílá "workAreaIds[]"
    vícekrát) - proto se query parsuje jako seznam dvojic, ne jako dict."""
    parts = urlparse(url)
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k != page_param
    ]
    query.append((page_param, str(page_num)))
    return urlunparse(parts._replace(query=urlencode(query)))


def _guess_from_card(card: Tag, hints: list[str]) -> str | None:
    """Poslední záchrana: element, jehož class/data-testid obsahuje jedno
    z hint slov (např. 'company', 'salary'). Použije se jen když site-specific
    extrakce nic nenajde (např. web mezitím trochu změnil markup)."""
    for hint in hints:
        el = card.find(
            lambda tag: (
                tag.has_attr("class") and any(hint in c.lower() for c in tag.get("class", []))
            )
            or (tag.has_attr("data-testid") and hint in tag["data-testid"].lower())
        )
        if el:
            text = clean_text(el.get_text(" "))
            if text:
                return text
    return None


def _extract_jobscz(card: Tag) -> tuple[str | None, str | None, str | None]:
    employer = None
    footer_item = card.select_one("li.SearchResultCard__footerItem:not([data-test])")
    if footer_item:
        span = footer_item.find("span")
        if span:
            employer = clean_text(span.get_text(" "))

    salary_el = card.select_one(".SearchResultCard__body .Tag--success")
    salary = clean_text(salary_el.get_text(" ")) if salary_el else None

    posted_el = card.select_one('[data-test-ad-status="default"]')
    posted = clean_text(posted_el.get_text(" ")) if posted_el else None

    return employer, salary, posted


def _find_by_accessibility_label(card: Tag, label_prefix: str) -> str | None:
    """prace.cz páruje hodnotu se skrytým popiskem pro čtečky obrazovky
    (`<span class="accessibility-hidden">Název firmy:</span>`). Hodnota je
    buď sourozenec popisku (firma, lokalita), nebo text hned za popiskem ve
    stejném elementu (plat)."""
    label_el = card.find(
        lambda tag: tag.name == "span"
        and "accessibility-hidden" in tag.get("class", [])
        and tag.get_text(strip=True).rstrip(":").strip() == label_prefix
    )
    if not label_el:
        return None

    sibling = label_el.find_next_sibling()
    if sibling:
        text = clean_text(sibling.get_text(" "))
        if text:
            return text

    parent = label_el.parent
    if parent:
        full = clean_text(parent.get_text(" "))
        label_text = clean_text(label_el.get_text(" "))
        if full and label_text and full.startswith(label_text):
            remainder = full[len(label_text):].strip()
            if remainder:
                return remainder
    return None


_PRACECZ_AGE_HINTS = (
    "nová nabídka",
    "jen pár hodin",
    "dnešní",
    "včerejší",
    "méně než týden",
    "před chvílí",
    " dny",
    " dní",
    " týden",
    " týdny",
)


def _extract_pracecz_posted(card: Tag) -> str | None:
    """Datum přidání není samostatné pole - je to jeden z "highlight" odznaků
    karty (spolu s jinými, nesouvisejícími odznaky jako "Nutně vás
    potřebují"), pozná se podle klíčových slov."""
    for span in card.select("span.typography-body-medium-regular.text-primary"):
        text = clean_text(span.get_text(" "))
        if text and any(hint in text.lower() for hint in _PRACECZ_AGE_HINTS):
            return text
    return None


def _extract_pracecz(card: Tag) -> tuple[str | None, str | None, str | None]:
    employer = _find_by_accessibility_label(card, "Název firmy")
    salary = _find_by_accessibility_label(card, "Plat")
    posted = _extract_pracecz_posted(card)
    return employer, salary, posted


_SITE_EXTRACTORS = {
    "jobscz": _extract_jobscz,
    "pracecz": _extract_pracecz,
}


def scrape_site(
    site_key: str,
    search_urls: list[str],
    card_selector: str,
    detail_url_pattern: str,
    employer_hints: list[str],
    salary_hints: list[str],
    max_pages: int,
    already_seen: set[str] | None = None,
    pagination_param: str | None = None,
    debug_dir: Path | None = None,
) -> list[Offer]:
    """already_seen: ID nabídek z minulých běhů (state.json). Pokud je zadáno
    (tj. nejde o úplně první běh) a dvě stránky po sobě obsahují jen už dřív
    viděné nabídky, scraper přestane dál stránkovat - šetří to požadavky a
    funguje to, protože výsledky jsou (typicky) řazené od nejnovějších.

    debug_dir: pokud je zadaný, uloží se do něj syrové HTML první stažené
    stránky (pro ladění card_selector/detail_url_pattern podle skutečné
    struktury webu)."""
    session = requests.Session()
    offers: dict[str, Offer] = {}
    already_seen = already_seen or set()
    debug_saved = False
    extractor = _SITE_EXTRACTORS.get(site_key)

    for start_url in search_urls:
        consecutive_fully_seen_pages = 0
        url: str | None = start_url
        for page_num in range(1, max_pages + 1):
            if url is None:
                break
            soup = fetch(url, session)
            if soup is None:
                break

            if debug_dir and not debug_saved:
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / f"{site_key}.html").write_text(str(soup), encoding="utf-8")
                debug_saved = True

            if card_selector:
                card_anchor_pairs = []
                for card in soup.select(card_selector):
                    anchor = card.find("a", href=lambda h: h and detail_url_pattern in h)
                    if anchor:
                        card_anchor_pairs.append((card, anchor))
            else:
                # bez card_selector nejde karty rozlišit - každý odpovídající
                # odkaz je vlastní "karta" (nápovědy pak hledají jen v jeho
                # bezprostředním okolí, ne v celé kartě).
                card_anchor_pairs = [
                    (a.parent or a, a)
                    for a in soup.find_all("a", href=lambda h: h and detail_url_pattern in h)
                ]

            page_offer_ids: list[str] = []
            for card, anchor in card_anchor_pairs:
                href = urljoin(url, anchor["href"])
                offer_id = _offer_id_from_url(href, detail_url_pattern)
                if not offer_id or offer_id in offers:
                    continue
                title = clean_text(anchor.get_text(" "))
                if not title:
                    continue
                page_offer_ids.append(offer_id)

                employer = salary = posted = None
                if extractor:
                    employer, salary, posted = extractor(card)
                if not employer:
                    employer = _guess_from_card(card, employer_hints)
                if not salary:
                    salary = _guess_from_card(card, salary_hints)

                offers[offer_id] = Offer(
                    id=offer_id,
                    site=site_key,
                    title=title,
                    url=href,
                    employer=clean_text(employer),
                    salary=clean_text(salary),
                    posted=clean_text(posted),
                )

            if not page_offer_ids and page_num > 1:
                break  # stránka bez nabídek = konec výsledků

            if already_seen and page_offer_ids and all(oid in already_seen for oid in page_offer_ids):
                consecutive_fully_seen_pages += 1
                if consecutive_fully_seen_pages >= 2:
                    break
            else:
                consecutive_fully_seen_pages = 0

            if pagination_param:
                url = _url_with_page(start_url, pagination_param, page_num + 1)
            else:
                next_link = soup.find("a", attrs={"rel": "next"}) or soup.find(
                    "a", string=re.compile(r"^(Další|Next)$", re.I)
                )
                url = urljoin(url, next_link["href"]) if next_link and next_link.get("href") else None

    return list(offers.values())
