# PLACSP Pharmaceutical Tender Pipeline

A small Python pipeline that extracts pharmaceutical tender data from the
Spanish public procurement portal
([PLACSP](https://contrataciondelestado.es/wps/portal/plataforma/buscador/))
for five target molecules: **Axitinib, Abiraterone, Fingolimod, Tamsulosin,
and Glatiramer Acetate**.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the pipeline

```bash
python -m pipeline.run
```

This writes `output.csv` in the current directory. Useful flags:

```bash
# Write to a specific file
python -m pipeline.run --output output.csv

# Add tender URLs you've collected manually (live-fetched)
python -m pipeline.run --seed-urls seed_urls.example.csv

# Run fully offline against locally-saved HTML pages (no network calls)
python -m pipeline.run --no-live-search --seed-html-manifest seed_html_manifest.example.csv

# More verbose logging
python -m pipeline.run --log-level DEBUG
```

## Helper scripts

Two small standalone scripts (not part of the `pipeline` package, just
convenience tools) live in the project root:

- **`debug_fetch_page.py "<url>"`** — fetches one PLACSP detail page and
  saves its raw HTML to `debug_page.html`, so you can inspect real page
  structure (useful when extending `LABEL_MAP` for a new layout variant).
- **`filter_detected.py output.csv output_filtered.csv`** — keeps only
  rows where `moleculeDetected == TRUE`, producing a smaller but
  higher-confidence CSV. See "PLACSP search matches PDF attachments" below
  for why this matters.

## Running the tests

```bash
python -m pytest -v
```

22 unit tests cover molecule matching and field extraction/normalisation
(amounts, dates, IDs) using a realistic sample detail page as a fixture.
These tests don't touch the network and run in well under a second.

## Architecture

```
pipeline/
  molecules.py    # Target molecules + Spanish/English spelling variants,
                   # and the text-matching logic (detect_molecule).
  http_client.py  # PoliteSession: requests wrapper with rate limiting,
                   # retries/backoff, a meaningful User-Agent, and logging.
  search.py       # search_tenders(): submits a query to PLACSP's search
                   # form and parses result links into detail-page URLs.
  extract.py      # parse_detail_page(): turns one detail page's HTML into
                   # a TenderRecord (label/value parsing + normalisation).
  models.py       # TenderRecord dataclass = single source of truth for the
                   # CSV schema and column order.
  csv_writer.py   # write_csv(): TenderRecord list -> CSV file.
  run.py          # Orchestrator + CLI: combines URL sources, fetches,
                   # parses, writes output.
tests/
  test_molecules.py
  test_extract.py
  fixtures/sample_detail_page.html
seed_urls.example.csv          # Example "manually found URL" seed file
seed_html_manifest.example.csv # Example "saved HTML page" seed file
seed_pages/                    # Example saved HTML page
```

Each module has one job, so a structural change to PLACSP's HTML only
requires editing `extract.py` (and possibly `search.py`), not the
orchestration or CSV logic. `models.py` is the single place the CSV schema
is defined — `csv_writer.py` and `extract.py` both build on it, so the
columns can never silently drift apart.

## Time spent

Roughly 2.5 hours: ~45 min understanding PLACSP's page structure from a
worked example, ~1 hour writing the pipeline modules, ~30 min writing and
debugging tests against real-world HTML, ~15 min on this README.

## Limitations, assumptions, and trade-offs

**This is the most important section — please read it.**

### 0. PLACSP search matches text inside attached documents, not just the tender page (important finding)

While testing against live data, we found that PLACSP's search engine
indexes the *full text of attached documents* (PDFs, Excel annexes,
technical specification sheets) for each tender, not just the tender's own
title/summary page. For specific, narrow molecules like Abiraterone, this
mostly returns small, single-purpose tenders where the molecule is named
directly in the title (e.g. "Abiraterone, axitinib, gefitinib..."). For
others — Fingolimod, Glatiramer Acetate, Tamsulosin, and partially Axitinib
— most results turned out to be **large multi-lot framework agreements**
("Acuerdo Marco", covering 100+ different drugs across 100+ lots) where the
target molecule is named only inside an attached PDF/Excel annex listing
all the lots, never on the tender's own detail page.

Per the brief's "Out of Scope" section, **we do not parse PDFs**, so for
these tenders `moleculeDetected` correctly comes back `FALSE` — the
molecule genuinely isn't present in the page text we're allowed to read.
This is expected, correct behaviour, not a bug: it's the pipeline accurately
reflecting the limits of "simple text matching" against page text only.

**Practical effect on row count:** in our final test run, live search across
all five molecules returned 58 unique tenders. Of these, only **2** had
`moleculeDetected == TRUE` (both Abiraterone, both small "Contrato Menor"
tenders from Universidad Jaume I) -- the molecule name was genuinely absent
from the page text for the rest, even though many were clearly *plausible*
matches based on CPV code and disease area (e.g. a tender with CPV
"33652300-Inmunosupresores" for "esclerosis múltiple" treatment is almost
certainly about Fingolimod, but the word "Fingolimod" itself never appears
on the page). We deliberately kept `moleculeDetected` strict and
text-based rather than inferring from CPV/disease-area hints, since the
brief asks for text matching specifically, and a strict signal is fully
defensible ("the word is literally on this page") versus a inferred one
that would require medical judgment calls. The final `output.csv` includes
all 58 rows (not just the 2 confirmed ones) so a human reviewer can see
both the confirmed matches and the broader, well-extracted context. Run
`python filter_detected.py output.csv output_filtered.csv` to get just the
high-confidence subset.

### 1. PLACSP's search is a stateful JSF/Liferay portal, not a simple GET

Every link on `contrataciondelestado.es`, including search results, is a
"deep link" of the form `.../wps/portal/.../!ut/p/z1/<token>`. The `<token>`
encodes server-side JSF view-state tied to a browser session. A plain
`requests.get()` to the search page returns an *empty* search form — actual
results come back from a form **POST** carrying that view-state.

`pipeline/search.py` implements this honestly: it GETs the search page,
looks for the search form and its hidden view-state fields, injects the
query into the text field, and POSTs it. **If PLACSP's JSF layer rejects
this (returns the empty form again, a different view-state error, or a
non-200), `search_tenders()` logs a clear warning and returns an empty
list** rather than crashing the whole run. Live search is therefore
**best-effort**.

### 2. PLACSP returns HTTP 403 to requests from some networks (observed)

While developing this, **all requests to `contrataciondelestado.es` from
the development sandbox returned `403 Forbidden`** — for both the search
page and a known-good detail-page URL — regardless of User-Agent. This
looks like a block on cloud/datacenter IP ranges rather than anything
specific to this code. **On a residential/office network this may well
work fine**; the pipeline should simply be re-run there to confirm.

### 3. Why the pipeline has three input sources, not one

Because of (1) and (2), relying solely on live search is risky for a
take-home that needs to demonstrably produce 20-50 rows. So the pipeline
supports three sources of tender detail pages, combined and de-duplicated:

| Source | Flag | Needs network? | Notes |
|---|---|---|---|
| Live search | *(default)* | Yes | Best-effort; may return 0 results if (1) or (2) apply |
| Manually-found URLs | `--seed-urls` | Yes (to fetch the page) | CSV: `url,molecule` |
| Locally-saved HTML | `--seed-html-manifest` | **No** | CSV: `url,molecule,html_file`; fully offline |

**Recommended real-world workflow if live search is blocked:** browse
PLACSP manually (as the assignment author already did for Abiraterone),
collect detail-page URLs into `seed_urls.csv`, run
`python -m pipeline.run --no-live-search --seed-urls seed_urls.csv` from a
network where PLACSP isn't blocked. If even that's blocked, save the pages
from your browser and use `--seed-html-manifest` instead — `extract.py`,
`models.py`, and `csv_writer.py` (the parts of the pipeline doing the actual
"extraction" work the brief asks about) run identically either way.

### 4. Field extraction is label-driven, not selector-driven

`extract.py` doesn't hard-code CSS selectors for one specific page layout.
Instead it scans the page for known Spanish field labels ("Objeto del
Contrato", "Adjudicatario", "Importe (sin impuestos)", "Procedimiento",
"Fecha de Publicación", etc. — see `LABEL_MAP`) across four common HTML
patterns (`<dt>/<dd>`, table rows, bold-label-followed-by-text, and a
general "any element whose own text is exactly a known label" pattern for
`<span>`/`<div>`-based layouts). This is more robust to the page variants
the brief says we don't need to fully handle, at roughly the same code
cost as fixed selectors. We validated this against both our original
worked example and live pages fetched during testing across all 5
molecules, and extended the patterns based on real layout differences we
found (see point 4a below). **Extend `LABEL_MAP` as you encounter pages
with different label wording.**

### 4a. `publicationDate` needed a special fallback, not a label

One real layout difference we found during live testing: PLACSP's
"Advertisements and documents" section lists each published document as a
table row (document type | link | timestamp) with **no preceding label at
all** for the date — it's just a bare value like "27/01/2022 16:20:06" in
a table cell. None of our label-based patterns can find this, since they
all require a recognisable label first. We added a fallback
(`_extract_first_timestamp`) that scans the whole page for the first
`DD/MM/YYYY HH:MM:SS`-style timestamp when no labeled date was found. This
is a good example of why the label-driven approach above is "best effort,"
not exhaustive: even a field as basic as a date isn't consistently
labeled across real PLACSP pages.

### 5. `noticeId`

PLACSP detail pages don't show a single obvious "notice ID" field in the
label/value sense. The pipeline derives `noticeId` from the `idEvl=`
parameter in the page's own URL (e.g. `idEvl=pDbMY4x34FwSugstABGr5A%3D%3D` →
`pDbMY4x34FwSugstABGr5A`), which is PLACSP's internal tender identifier and
is stable/unique per tender. The `CM/8062/21/UG1`-style "File" reference
(the contracting body's own file number) is captured separately if present,
but isn't used as `noticeId` since it isn't guaranteed unique across
different contracting bodies.

### 6. One row per detail page (lots)

The brief's schema includes `lotId` for multi-lot tenders. The "contrato
menor" pages used to develop this pipeline describe a single, undivided
purchase, so `lotId` is left blank for them. If you encounter a genuinely
multi-lot tender (a single notice listing several `Lote N` sections), the
intended extension point is: `extract.py` would return a `list[TenderRecord]`
instead of one record, iterating over lot sections and copying the
notice-level fields (buyer, CPV, dates, etc.) into each lot's row while
filling in `lotId` and the lot-specific value/award fields. This wasn't
implemented because no multi-lot example was available to develop against,
and the brief allows "simple text matching" / doesn't require full coverage.

### 7. Molecule matching

Matching is case-insensitive substring matching against a curated list of
variants per molecule (`pipeline/molecules.py`), including the Spanish INN
names (e.g. *abiraterona*, *acetato de glatirámero*) and the typo
"geftinib" → "gefitinib" observed in real tender text doesn't currently
have its own variant list since gefitinib isn't a target molecule — but this
demonstrates that **real PLACSP text contains typos**, so `LABEL_MAP` and
`match_variants` should be treated as living lists to extend as you see more
real data, not exhaustive references.

If a target molecule's exact canonical spelling isn't found but *some*
molecule variant is (e.g. the page is actually about a different drug),
`moleculeDetected`/`moleculeVariant` fall back to whatever variant *was*
found, so you can see what the page is actually about even on a
near-miss.

### 8. Amount and currency

`awardValue` is normalised from Spanish "764,13 EUR." formatting to a plain
decimal string "764.13" (thousands separators removed, decimal comma →
dot). `currency` is hardcoded to `"EUR"` since every PLACSP tender we've
seen is denominated in euros; if a non-EUR tender were ever encountered,
this would need to become a parsed field.

### 9. Engineering practices implemented

- **Type hints** throughout (`from __future__ import annotations` + dataclasses).
- **Logging** at INFO (request URLs, result counts, fallback decisions) and
  DEBUG (rate-limit sleeps, parse failures) via the standard `logging`
  module — configurable with `--log-level`.
- **Rate limiting**: `PoliteSession` enforces a minimum delay (default 1.5s)
  between requests, including across retries.
- **Retries with backoff**: transient errors and 5xx responses are retried
  up to 3 times with linear backoff.
- **Meaningful User-Agent**: identifies this as a student take-home script
  with a contact point (`pipeline/http_client.py::USER_AGENT` — replace the
  placeholder email before any real use).
- **Graceful degradation**: every fetch/parse step is wrapped so that one
  bad page logs a warning and is skipped, rather than crashing the whole run.

### 10. Next steps if continuing this project

- Capture more real PLACSP pages (across different contracting bodies and
  procedure types) and expand `LABEL_MAP` / the multi-lot handling in (6)
  against them.
- If PLACSP consistently blocks automated requests, investigate the
  [PLACSP open data feeds](https://contrataciondelsectorpublico.gob.es/wps/portal/DatosAbiertos)
  (Atom/CODICE XML datasets) as a structured alternative data source —
  these are designed for bulk consumption and avoid the JSF session problem
  entirely, though they're a different format from the HTML scraping this
  brief asked for.
- Add an integration test that runs the full pipeline against
  `seed_html_manifest.example.csv` and asserts on `output.csv` contents
  (currently the unit tests cover `extract.py` directly; an end-to-end test
  would also exercise `run.py` and `csv_writer.py`).
