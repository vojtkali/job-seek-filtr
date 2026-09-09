"""LinkedIn přes knihovnu JobSpy (https://github.com/speedyapply/JobSpy) -
na rozdíl od jobs.cz/prace.cz tady nejde o vlastní HTML scraper, protože
LinkedIn běžný scraping čistým requests+BeautifulSoup aktivně blokuje.

Důležité omezení podle dokumentace JobSpy: "LinkedIn is the most
restrictive and usually rate limits around the 10th page with one ip" -
bez proxy (které tu nepoužíváme) se běh z jedné IP (GitHub Actions runner)
může časem začít zadrhávat/blokovat. Proto se drží výsledků per klíčové
slovo na rozumném počtu (~1 stránka) a chyby jednotlivých klíčových slov
se jen zalogují a scraper pokračuje dál, ne že by celý běh spadl.

LinkedIn nepodporuje "OR" mezi víc pozicemi v jednom vyhledávání
spolehlivě, takže se pro každé klíčové slovo z konfigurace volá
scrape_jobs() zvlášť a výsledky se spojí a odduplikují podle URL nabídky."""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from .common import Offer, clean_text

log = logging.getLogger(__name__)


def _id_from_job_url(url: str) -> str:
    path = urlparse(url).path
    digits = re.findall(r"\d+", path)
    return digits[-1] if digits else url


def _text_or_none(value) -> str | None:
    """Bezpečně převede hodnotu z pandas DataFrame (může být NaN/None/NaT)
    na text, nebo None - clean_text() sám o sobě prázdné pandas hodnoty
    neumí (spadl by na regexu, nebo by je zapsal jako text "NaT")."""
    import pandas as pd

    try:
        is_missing = pd.isna(value)
    except (TypeError, ValueError):
        is_missing = False
    if is_missing:
        return None
    return clean_text(str(value))


def _format_salary(row) -> str | None:
    import pandas as pd

    min_amount = row.get("min_amount")
    max_amount = row.get("max_amount")
    if pd.isna(min_amount) and pd.isna(max_amount):
        return None
    currency = _text_or_none(row.get("currency")) or ""
    interval = _text_or_none(row.get("interval"))
    interval = f"/{interval}" if interval else ""

    if pd.notna(min_amount) and pd.notna(max_amount) and min_amount != max_amount:
        amount = f"{min_amount:,.0f} - {max_amount:,.0f}"
    else:
        amount = f"{(min_amount if pd.notna(min_amount) else max_amount):,.0f}"
    return clean_text(f"{amount} {currency}{interval}")


def scrape_linkedin(
    search_terms: list[str],
    location: str,
    job_type: str | None,
    results_wanted: int,
) -> list[Offer]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        log.warning("python-jobspy není nainstalovaný - LinkedIn se přeskakuje.")
        return []

    offers: dict[str, Offer] = {}

    for term in search_terms:
        try:
            df = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=location,
                job_type=job_type,
                results_wanted=results_wanted,
                linkedin_fetch_description=False,
            )
        except Exception as exc:  # LinkedIn rate-limity/bloky nesmí shodit celý běh
            log.warning("LinkedIn hledání '%s' selhalo: %s", term, exc)
            continue

        if df is None or df.empty:
            continue

        for _, row in df.iterrows():
            job_url = _text_or_none(row.get("job_url"))
            title = _text_or_none(row.get("title"))
            if not job_url or not title:
                continue
            offer_id = _id_from_job_url(job_url)
            if offer_id in offers:
                continue

            offers[offer_id] = Offer(
                id=offer_id,
                site="linkedin",
                title=title,
                url=job_url,
                employer=_text_or_none(row.get("company")),
                salary=_format_salary(row),
                posted=_text_or_none(row.get("date_posted")),
            )

    return list(offers.values())
