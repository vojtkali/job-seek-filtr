# job-seek-filtr

Hlídač nabídek práce na [jobs.cz](https://www.jobs.cz) a [prace.cz](https://www.prace.cz).
Řeší dvě věci:

1. **Nemusíš procházet nabídky ručně každý den a nic ti neuteče přes víkend.**
   Scraper si po každém běhu pamatuje ID nabídek, které už viděl. Při dalším
   běhu ukáže jen to, co je nové *od posledního běhu* – ne od posledních
   24 hodin. Takže když neběží v sobotu ani v neděli, pondělní běh
   automaticky ukáže úplně všechno nashromážděné za celý víkend, bez
   jakékoli speciální logiky pro "je pondělí".
2. **Zaměstnavatele, jejichž nabídky tě nezajímají, jednoduše zablokuješ** –
   stačí přidat jejich jméno (nebo jeho část) do `config/blacklist.txt`.

Výsledek je vidět na statické stránce (GitHub Pages), rozdělené po dnech,
kdy scraper běžel.

## Jak to funguje

- **GitHub Actions** (`.github/workflows/scrape.yml`) spouští scraper
  automaticky každý všední den (cron `0 8 * * 1-5`, tj. cca 9–10h ráno v
  Praze podle letního/zimního času) a taky ručně přes tlačítko *Run workflow*.
- Scraper (`scraper/`) stáhne výsledkové stránky z URL, které si nastavíš
  v `config/settings.yaml`, posbírá odkazy na jednotlivé nabídky, zkusí
  dohledat jméno firmy a plat, porovná s tím, co je uložené v `data/state.json`,
  odfiltruje blacklistované firmy a nové nabídky zapíše do `data/history.json`
  a `site/data.json`.
- Workflow změněná data commitne zpátky do repa a nasadí obsah `site/` na
  GitHub Pages.

## Než to poprvé spustíš – nastavení

### 1. Vlož skutečné vyhledávací URL

`config/settings.yaml` obsahuje pro jobs.cz a prace.cz placeholder URL.
Nejsou to URL, které bych si vymyslel obecně – jde o to, abys **na webu ve
filtru sám nastavil** požadovanou lokalitu/plat/obor (jobs.cz: Praha, plat
od 69 000 Kč; prace.cz: Praha, plný úvazek, vybrané obory, plat od částky,
kterou chceš) a **zkopíroval výslednou URL z adresního řádku prohlížeče**
do `search_urls`. Filtrování tak dělá přímo web (spolehlivě), scraper jen
čte výsledky.

Pokud web pro víc oborů/kritérií negeneruje jednu společnou URL, přidej do
seznamu URL pro každou kombinaci zvlášť – scraper všechny stáhne a spojí.

> Poznámka: URL v souboru teď jsou jen odhad tvaru parametrů (skládal jsem
> je bez přístupu na živý web z tohoto prostředí). Nahraď je před prvním
> ostrým během.

### 2. Zkontroluj/uprav `detail_url_pattern` a hints

- `detail_url_pattern` – kus URL, podle kterého scraper pozná odkaz na
  detail nabídky (např. `/rpd/`). Pokud po prvním běhu vidíš na stránce
  0 nabídek (nebo varování), zkontroluj v prohlížeči přes "Zobrazit zdrojový
  kód"/DevTools, jak vypadají odkazy na nabídky, a hodnotu uprav.
- `employer_hints` / `salary_hints` – slova, která scraper hledá v
  `class`/`data-testid` elementů kolem odkazu na nabídku, aby našel jméno
  firmy a plat. Pokud se u nabídek často objevuje "Neznámý zaměstnavatel",
  zkus doplnit další hint podle skutečné třídy v HTML.

Scraper navíc zkouší jako první zdroj dat JSON vložený na stránce (typicky
`__NEXT_DATA__` u moderních webů) – pokud ho web má, jméno firmy a plat
najde spolehlivě i bez CSS hintů.

### 3. Zapni GitHub Pages (jednorázově, ručně)

V nastavení repozitáře: **Settings → Pages → Build and deployment → Source:
GitHub Actions.** Tohle musí nastavit člověk s admin přístupem k repu přes
webové rozhraní, jde to udělat jen jednou.

### 4. Cron běží jen z výchozí (default) větve

GitHub spouští naplánované (`schedule`) workflow jen z výchozí větve repa.
Dokud tuhle větev nesloučíš/nenastavíš jako výchozí, spouštěj scraper ručně
přes záložku *Actions → Scrape job offers → Run workflow*.

## Blokování zaměstnavatelů

Přidej jméno firmy (stačí část, hledá se jako podřetězec, nezáleží na
velikosti písmen) na nový řádek do `config/blacklist.txt`:

```
Grafton Recruitment
Randstad
```

Nabídky od blokovaných firem se od dalšího běhu přestanou zobrazovat (ale
scraper si je dál interně eviduje jako "viděné", takže se po odblokování
znovu nevynoří jako "nové", pokud mezitím nepřibyla nová nabídka od stejné
firmy).

## Lokální spuštění / test

```bash
pip install -r requirements.txt
python -m scraper.main
```

Vygeneruje/aktualizuje `data/state.json`, `data/history.json` a
`site/data.json`. Stránku pak zobrazíš třeba přes `python -m http.server`
ve složce `site/`.

## Struktura repozitáře

```
config/settings.yaml   # vyhledávací URL, limity stránkování, hinty pro extrakci
config/blacklist.txt    # blokovaní zaměstnavatelé
scraper/                # samotný scraper (common/site_scraper/main)
data/state.json         # ID už viděných nabídek + čas posledního běhu
data/history.json       # historie běhů a nových nabídek (posledních 30 běhů)
site/                   # statická stránka nasazovaná na GitHub Pages
.github/workflows/      # GitHub Actions cron
```
