# PLACSP Pharmaceutical Tender Pipeline

## Overview

This project is a small Python pipeline that searches the Spanish public procurement portal (PLACSP) for tenders related to five target molecules:

- Axitinib
- Abiraterone
- Fingolimod
- Tamsulosin
- Glatiramer Acetate

The pipeline extracts tender information from PLACSP tender pages and outputs a single CSV containing the fields requested in the assignment, including buyer, title, award value, supplier, publication date, and molecule matching information.

The goal was to build a clean, maintainable pipeline that can reliably collect and structure relevant procurement data, and to be upfront about what it can and can't confirm.

## Setup

Create and activate a virtual environment:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the pipeline:

```
python -m pipeline.run
```

The output will be written to: `output.csv`

Run tests:

```
python -m pytest -v
```

## Approach

I started by exploring PLACSP manually to understand how tender pages are structured and what information is consistently available. One of the first challenges was that PLACSP isn't a simple website where search results can be retrieved with a standard URL. Search requests depend on hidden form fields and session state (it's built on JSF/PrimeFaces, so pagination is a server-side postback rather than a `?page=N` link), so I spent real time understanding how the portal behaves before automating the search process.

After understanding the site structure, I split the solution into small modules with a single responsibility:

| Module | Responsibility |
|---|---|
| `search.py` | Search PLACSP and collect tender URLs |
| `extract.py` | Extract fields from tender detail pages |
| `molecules.py` | Molecule matching and variant handling |
| `models.py` | Defines the CSV schema |
| `csv_writer.py` | Writes results to CSV |
| `run.py` | Pipeline orchestration |

This structure keeps the code easier to maintain and lets the extraction logic evolve independently from the rest of the pipeline.

## Making Sure Pagination Actually Covers the Results

This is worth its own section, since it shaped a lot of how the search step ended up working.

PLACSP's results list isn't simple to page through. The "Next" button isn't a link, it's an `<input type="image">` tied to the form's `javax.faces.ViewState`, so moving to the next page means rePOSTing the entire form (including a fresh ViewState each time) with the Next button's name included, as if it had actually been clicked. Once that part was working, a molecule with hundreds of results meant following that postback across as many pages as it took, rather than stopping after the first batch of 25.

While testing that against real data, I noticed something more interesting: PLACSP's results view is tied to the session itself, not just to the form's ViewState token. Running all five molecules' searches through one shared session meant that after one molecule had paginated deep into its results, the next molecule's search would sometimes pick up mid-range instead of starting cleanly at result 1 — and a couple of queries later, the results table could disappear from the page entirely. I caught this by watching the per-page result-count logs at `--log-level DEBUG`: a query reporting "results 276–292" right out of the gate, instead of "1–25", was the tell that the server still thought I was mid-pagination on a previous search.

The fix was to give each individual search term its own fresh session and cookie jar, so PLACSP has no way to carry state from one molecule's search into the next. Each search now starts clean and pages forward using PLACSP's own "X – Y de Z Resultados" count to know when it's genuinely done — so a molecule with a lot of results gets fully paginated, and one with fewer just stops naturally, without a shared fixed cap getting in the way either direction.

I also widened the link-detection logic in `search.py` once I noticed PLACSP renders some result rows as a `deeplink:detalle_licitacion` query-string URL and others as a WebSpherePortal-style `!ut/p/z1/...` path-encoded URL — visually identical on the results page, but only one of those formats was being picked up. Both share the substring `detalle`, so matching is now scoped to that instead of one specific URL shape.

## Molecule Matching

The assignment required matching both English and Spanish molecule names. Each target molecule has a list of common variants, e.g.:

| Molecule | Variants |
|---|---|
| Abiraterone | abiraterone, abiraterona |
| Glatiramer Acetate | glatiramer acetate, acetato de glatirámero |

Matching is implemented using simple case-insensitive text search, which is sufficient for the scope of this exercise.

One thing I added once pagination was actually working: a single tender page can legitimately mention more than one target molecule (a framework agreement covering several drugs at once is a normal pattern on PLACSP). The extraction step now checks each parsed page against every target molecule, not just the one whose search term happened to find it, and emits one output row per molecule it confirms — so a tender mentioning both Axitinib and Abiraterone shows up correctly under both, regardless of which molecule's search surfaced the URL first.

The CSV contains:

- `productMolecule` — target molecule for this row
- `moleculeDetected` — whether the molecule was actually confirmed on the page
- `moleculeVariant` — the exact matched term

## Output Notes

With pagination covering the full result set, the search now sees hundreds of results per molecule instead of just the first page, and most of those still won't show a confirmed molecule mention on the tender detail page itself. That's expected: PLACSP's text search is intentionally broad, and a fair share of genuine matches only appear inside an attached PDF (pliego, anexo, etc.), which is out of scope for this exercise. The pipeline keeps this transparent rather than guessing — by default it only writes rows where `moleculeDetected = TRUE`, and `--include-unconfirmed` is there if you want to see everything PLACSP's search surfaced, unfiltered.

Two of the five target molecules — Tamsulosin and Glatiramer Acetate — currently come back with zero confirmed rows. I checked this directly against PLACSP's own search before trusting the output: searching those terms on the site itself turns up very little right now that's both live and phrased in a way the page text exposes, rather than buried in an attachment. I'm treating this as an accurate reflection of what's currently on PLACSP for those two molecules, and calling it out explicitly here so it reads as a finding rather than a silent gap.

## What I Learned During Extraction

The clearest confirmed matches I found for both Abiraterone and Axitinib were small purchases made by Universidad Jaume I, e.g. "Abiraterone, axitinib, geftinib..." and "Abiraterone, axitinib, gefitinib CRS...". These read as laboratory reference standards or research reagents rather than hospital pharmaceutical procurement contracts, a good reminder that keyword matching on a molecule name doesn't tell you anything about *why* that name appears. A reagent catalogue and a hospital supply contract can use identical wording.

I also noticed, just from manually reading detail pages, that some target-molecule mentions live in tender attachments rather than the summary page itself. Since PDF parsing was explicitly out of scope for this exercise, the pipeline only ever confirms matches found in the HTML of the tender detail page, and is upfront about that boundary via the `moleculeDetected` flag rather than guessing.

## Engineering Practices

To keep the pipeline reliable and maintainable, I included:

- Type hints throughout the codebase
- Logging with configurable log levels
- HTTP retries with backoff
- Request rate limiting
- A custom, honest User-Agent identifying the script
- Unit tests for molecule matching and field extraction
- Graceful handling of failed requests and parsing errors — if a page can't be fetched or parsed, the pipeline logs it and keeps going

## Known Limitations

**PLACSP uses stateful search forms.** It relies on a JSF architecture with hidden fields like `javax.faces.ViewState` to manage search state and navigation, so automated searching is more involved than scraping a site with predictable URLs. Pagination now works correctly per the fix described above, but the underlying site behavior is still worth flagging for anyone picking this up later.

**PDF/attachment content isn't parsed.** As noted above, some molecule mentions only exist inside attached documents. This is out of scope for this exercise but would be the natural next step for more complete coverage.

**Result-page markup can vary.** PLACSP's results table id, label wording, and URL format aren't perfectly consistent across pages — I handle the variations I've actually encountered (see `LABEL_MAP` in `extract.py` and the dual URL-format handling in `search.py`), but a structural change on PLACSP's end could still surface a new pattern that needs adding.

## Time Spent

Roughly 3.5 hours across two sessions. The first pass (~2.5 hours) covered understanding PLACSP itself, exploring the site, inspecting page structures, and figuring out how search results were generated — followed by the initial extraction pipeline, molecule matching, normalization, and a first set of tests. The second pass (~1 hour) went into hardening the search step against PLACSP's full result set, once manual checks against the live site showed there was more to cover: fixing the pagination POST so every result page per molecule actually gets visited, giving each molecule's search its own session so PLACSP doesn't carry pagination state from one query into the next, and widening link detection to catch both detail-page URL formats. The multimolecule fanout was added in this same pass.

## Future Improvements

- Process attached procurement documents and PDFs to identify molecule mentions that don't appear in the tender summary page.
- Enhance molecule matching with fuzzy matching and NLP-based techniques to improve detection accuracy.
- Add automated validation and quality checks for extracted procurement records.
- Improve performance through controlled parallelisation while continuing to respect portal rate limits and responsible scraping practices.

## Example Output

```
noticeId,lotId,title,productMolecule,moleculeDetected,awardValue
CM/8062/21/UG1,,"Abiraterone, axitinib, geftinib...",Abiraterone,TRUE,764.13
CM/8062/21/UG1,,"Abiraterone, axitinib, geftinib...",Axitinib,TRUE,764.13
```
