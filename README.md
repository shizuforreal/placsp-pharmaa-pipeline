# PLACSP Pharmaceutical Tender Pipeline

## Overview

This project is a small Python pipeline that searches the Spanish public procurement portal (PLACSP) for tenders related to five target molecules:

* Axitinib
* Abiraterone
* Fingolimod
* Tamsulosin
* Glatiramer Acetate

The pipeline extracts tender information from PLACSP tender pages and outputs a single CSV containing the fields requested in the assignment, including buyer, title, award value, supplier, publication date, and molecule matching information.

The goal was to build a clean, maintainable pipeline that can reliably collect and structure relevant procurement data.

---

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the pipeline:

```bash
python -m pipeline.run
```

The output will be written to:

```text
output.csv
```

Run tests:

```bash
python -m pytest -v
```

---

## Approach

I started by exploring PLACSP manually to understand how tender pages are structured and what information is consistently available.

One of the first challenges was that PLACSP is not a simple website where search results can be retrieved with a standard URL. Search requests depend on hidden form fields and session state, so I spent some time understanding how the portal behaves before automating the search process.

After understanding the site structure, I split the solution into small modules with a single responsibility:

| Module          | Responsibility                          |
| --------------- | --------------------------------------- |
| `search.py`     | Search PLACSP and collect tender URLs   |
| `extract.py`    | Extract fields from tender detail pages |
| `molecules.py`  | Molecule matching and variant handling  |
| `models.py`     | Defines the CSV schema                  |
| `csv_writer.py` | Writes results to CSV                   |
| `run.py`        | Pipeline orchestration                  |

This structure keeps the code easier to maintain and allows extraction logic to evolve independently from the rest of the pipeline.

---

## Molecule Matching

The assignment required matching both English and Spanish molecule names.

Each target molecule therefore has a list of common variants.

Examples:

| Molecule           | Variants                                   |
| ------------------ | ------------------------------------------ |
| Abiraterone        | abiraterone, abiraterona                   |
| Glatiramer Acetate | glatiramer acetate, acetato de glatirámero |

Matching is implemented using simple case-insensitive text searches, which is sufficient for the scope of this exercise.

The CSV contains:

* `productMolecule` – target molecule being searched
* `moleculeDetected` – whether the molecule was actually found in the page content
* `moleculeVariant` – exact matched term

---

## Output Notes

One thing I noticed while testing is that many tenders returned by PLACSP search do **not** explicitly mention the target molecule in the title or detail page content.

As a result, many rows have:

```text
moleculeDetected = FALSE
```

This is intentional.

PLACSP search appears to match against information broader than the fields captured by this pipeline (for example, indexed procurement documents or metadata that are not visible in the tender summary page).

The `moleculeDetected` flag allows the output to distinguish between:

* search results returned by PLACSP
* tenders where the molecule was actually confirmed in the extracted content

This makes it easy to filter for verified matches.

---

## What I Learned During Extraction

The only confirmed matches I found for both **Abiraterone** and **Axitinib** were small purchases made by **Universidad Jaume I**.

Examples:

* "Abiraterone, axitinib, geftinib..."
* "Abiraterone, axitinib, gefitinib CRS..."

These appear to be laboratory reference standards or research reagents rather than hospital pharmaceutical procurement contracts.

This highlights an important limitation of keyword-based matching: a molecule name may appear in research, laboratory, or testing purchases rather than clinical medicine procurement.

---

## Engineering Practices

To keep the pipeline reliable and maintainable, I included:

* Type hints throughout the codebase
* Logging with configurable log levels
* HTTP retries with backoff
* Request rate limiting
* A custom User-Agent
* Unit tests for molecule matching and field extraction
* Graceful handling of failed requests and parsing errors

If a page cannot be fetched or parsed, the pipeline logs the issue and continues processing the remaining records.

---

## Limitations

### PLACSP Search Behaviour

PLACSP uses a stateful portal architecture and search requests depend on session-specific form data. Because of this, automated searching is less predictable than scraping a typical website.

### Search Results Are Not Always Confirmed Matches

Many search results returned by PLACSP do not contain an explicit mention of the target molecule in the extracted page content.

This is why the output includes the `moleculeDetected` field.

### No PDF Processing

The solution only extracts information available on tender detail pages and does not process attached documents or PDFs, which was outside the scope of the assignment.

---

## Time Spent

## Time Spent

Approximately 2.5 hours.

The biggest time investment was understanding PLACSP itself rather than writing code. I spent a good portion of the exercise manually exploring the site, inspecting page structures, and figuring out how search results were generated.

After that, with the help of claude I implemented the extraction pipeline, added molecule matching and data normalisation, wrote a small set of tests, and documented the main limitations and assumptions of the approach.
---

## Running the Pipeline

```bash
python -m pipeline.run
```

Example output:

```text
noticeId,title,productMolecule,moleculeDetected,awardValue
CM/8062/21/UG1,"Abiraterone, axitinib, geftinib...",Abiraterone,TRUE,764.13
```
