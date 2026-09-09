"""Obecný scraper výsledkové stránky (jobs.cz i prace.cz mají podobnou stavbu).

Filtrování (lokalita, plat, obor...) dělá web sám - my mu jen předáme URL,
kterou si uživatel sám nastavil a zkopíroval z prohlížeče. Tady jen sbíráme
odkazy na jednotlivé nabídky a co nejlíp k nim dohledáme jméno firmy a plat.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

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


def _offer_id_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    digits = re.findall(r"\d+", path)
    return digits[-1] if digits else path


def _find_next_data_offers(soup: BeautifulSoup) -> list[dict]:
    """Next.js aplikace často embedují data stránky jako JSON - pokud ano,
    je to spolehlivější zdroj jména firmy/platu než hádání podle CSS."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except (json.JSONDecodeError, TypeError):
        return []

    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            keys_lower = {k.lower() for k in node.keys()}
            has_title = any(k in keys_lower for k in ("title", "name", "positionname"))
            has_company = any(
                k in keys_lower for k in ("companyname", "employer", "company")
            )
            if has_title and has_company:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def _match_next_data_offer(records: list[dict], offer_id: str, url: str) -> dict | None:
    for rec in records:
        rec_id = str(rec.get("id") or rec.get("hashId") or "")
        if rec_id and rec_id == offer_id:
            return rec
        rec_url = rec.get("url") or rec.get("link")
        if rec_url and offer_id in str(rec_url):
            return rec
    return None


def _pick(d: dict, keys: list[str]) -> str | None:
    for k in d.keys():
        if k.lower() in keys:
            v = d[k]
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                for sub_key in ("name", "value", "text"):
                    if sub_key in v and isinstance(v[sub_key], str):
                        return v[sub_key]
    return None


def _guess_from_card(anchor, hints: list[str]) -> str | None:
    """Fallback: podívá se do okolí odkazu na nabídku po elementu, jehož
    class/data-testid obsahuje jedno z hint slov (např. 'company', 'salary')."""
    card = anchor
    for _ in range(5):
        if card.parent is None:
            break
        card = card.parent
        for hint in hints:
            el = card.find(
                lambda tag: tag.has_attr("class")
                and any(hint in c.lower() for c in tag.get("class", []))
                or (tag.has_attr("data-testid") and hint in tag["data-testid"].lower())
            )
            if el:
                text = clean_text(el.get_text(" "))
                if text:
                    return text
    return None


def scrape_site(
    site_key: str,
    search_urls: list[str],
    detail_url_pattern: str,
    employer_hints: list[str],
    salary_hints: list[str],
    max_pages: int,
) -> list[Offer]:
    session = requests.Session()
    offers: dict[str, Offer] = {}

    for start_url in search_urls:
        url: str | None = start_url
        for page_num in range(max_pages):
            if not url:
                break
            soup = fetch(url, session)
            if soup is None:
                break

            next_data_records = _find_next_data_offers(soup)

            anchors = [
                a
                for a in soup.find_all("a", href=True)
                if detail_url_pattern in a["href"]
            ]
            page_had_offer = False
            for a in anchors:
                href = urljoin(url, a["href"])
                offer_id = _offer_id_from_url(href)
                if not offer_id or offer_id in offers:
                    continue
                title = clean_text(a.get_text(" "))
                if not title:
                    continue
                page_had_offer = True

                employer = None
                salary = None
                nd_match = _match_next_data_offer(next_data_records, offer_id, href)
                if nd_match:
                    employer = _pick(
                        nd_match, ["companyname", "employer", "company"]
                    )
                    salary = _pick(nd_match, ["salary", "wage", "salaryrange"])
                if employer is None:
                    employer = _guess_from_card(a, employer_hints)
                if salary is None:
                    salary = _guess_from_card(a, salary_hints)

                offers[offer_id] = Offer(
                    id=offer_id,
                    site=site_key,
                    title=title,
                    url=href,
                    employer=clean_text(employer),
                    salary=clean_text(salary),
                )

            if not page_had_offer and page_num > 0:
                break

            next_link = soup.find("a", attrs={"rel": "next"}) or soup.find(
                "a", string=re.compile(r"^(Další|Další|Next)$", re.I)
            )
            url = urljoin(url, next_link["href"]) if next_link and next_link.get("href") else None

    return list(offers.values())
