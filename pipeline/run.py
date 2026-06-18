from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from pipeline.csv_writer import write_csv
from pipeline.extract import parse_detail_page
from pipeline.http_client import PoliteSession
from pipeline.molecules import TARGET_MOLECULES
from pipeline.search import search_tenders

logger = logging.getLogger(__name__)


def load_seed_urls(path: Path) -> list[tuple[str, str]]:
    """Load (url, molecule) pairs from a seed CSV file.

    Expected columns: `url`, `molecule` (molecule = canonical name, e.g.
    "Abiraterone", matching `pipeline.molecules.TARGET_MOLECULES`).
    """
    pairs: list[tuple[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            molecule = (row.get("molecule") or "").strip()
            if url and molecule:
                pairs.append((url, molecule))
            else:
                logger.warning("Skipping malformed seed row: %r", row)
    logger.info("Loaded %d seed URL(s) from %s", len(pairs), path)
    return pairs


def load_seed_html_manifest(manifest_path: Path) -> list[tuple[str, str, Path]]:
  
    triples: list[tuple[str, str, Path]] = []
    with manifest_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            molecule = (row.get("molecule") or "").strip()
            html_file = (row.get("html_file") or "").strip()
            if not (url and molecule and html_file):
                logger.warning("Skipping malformed seed-html row: %r", row)
                continue

            html_path = Path(html_file)
            if not html_path.is_absolute():
                html_path = manifest_path.parent / html_path

            if not html_path.exists():
                logger.warning("Seed HTML file not found, skipping: %s", html_path)
                continue

            triples.append((url, molecule, html_path))

    logger.info("Loaded %d seed HTML page(s) from %s", len(triples), manifest_path)
    return triples


def collect_urls_from_search(
    session: PoliteSession, max_pages: int
) -> list[tuple[str, str]]:

    pairs: list[tuple[str, str]] = []
    for molecule in TARGET_MOLECULES:
        for term in molecule.search_terms:
            urls = search_tenders(session, term, max_pages=max_pages)
            logger.info(
                "Search for %r (%s) returned %d URL(s)",
                term,
                molecule.canonical_name,
                len(urls),
            )
            for url in urls:
                pairs.append((url, molecule.canonical_name))
    return pairs


def deduplicate(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Remove duplicate (url, molecule) pairs, preserving first-seen order."""
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for pair in pairs:
        if pair not in seen:
            seen.add(pair)
            result.append(pair)
    return result


def deduplicate_records(records: list) -> list:
    
    seen: set[tuple[str, str]] = set()
    result = []
    for record in records:
        key = (record.sourceUrl, record.productMolecule)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def run(
    output_path: Path,
    seed_urls_path: Path | None,
    seed_html_manifest_path: Path | None,
    skip_live_search: bool = False,
    max_pages: int = 20,
    include_unconfirmed: bool = False,
) -> None:
    url_molecule_pairs: list[tuple[str, str]] = []
    records: list = []

    # Offline seed pages: parsed directly from local files, no HTTP needed.
    if seed_html_manifest_path is not None:
        for url, molecule, html_path in load_seed_html_manifest(seed_html_manifest_path):
            try:
                html = html_path.read_text(encoding="utf-8")
                page_records = parse_detail_page(
                    html, source_url=url, target_molecule=molecule
                )
            except Exception:
                logger.exception("Failed to parse seed HTML %s -- skipping", html_path)
                continue
            # `parse_detail_page` now returns one record per molecule it
            # actually found mentioned on the page (e.g. a tender covering
            # both Axitinib and Abiraterone yields two records), so we
            # extend the list rather than appending a single record.
            records.extend(page_records)

    with PoliteSession() as session:
        if not skip_live_search:
            url_molecule_pairs.extend(collect_urls_from_search(session, max_pages))
        else:
            logger.info("Skipping live PLACSP search (--no-live-search)")

        if seed_urls_path is not None:
            url_molecule_pairs.extend(load_seed_urls(seed_urls_path))

        url_molecule_pairs = deduplicate(url_molecule_pairs)

        if not url_molecule_pairs and not records:
            logger.error(
                "No tender URLs to process (live search returned nothing, "
                "and no --seed-urls or --seed-html-manifest was given). "
                "Writing an empty CSV with headers only. See README.md for "
                "the recommended seed-data workflow."
            )
            write_csv([], output_path)
            return

        if url_molecule_pairs:
            logger.info("Fetching and parsing %d tender detail page(s)...", len(url_molecule_pairs))

        for url, molecule in url_molecule_pairs:
            try:
                response = session.get(url)
            except Exception:
                logger.exception("Failed to fetch %s -- skipping", url)
                continue

            try:
                page_records = parse_detail_page(
                    response.text, source_url=url, target_molecule=molecule
                )
            except Exception:
                logger.exception("Failed to parse %s -- skipping", url)
                continue

            records.extend(page_records)

    records = deduplicate_records(records)

    if not include_unconfirmed:
        before = len(records)
        records = [r for r in records if r.moleculeDetected]
        logger.info(
            "Filtered out %d unconfirmed record(s) (moleculeDetected=False); "
            "%d confirmed record(s) remain. Pass --include-unconfirmed to "
            "keep everything PLACSP's search returned.",
            before - len(records),
            len(records),
        )

    write_csv(records, output_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract pharmaceutical tender data from PLACSP into a CSV."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.csv"),
        help="Path to write the output CSV (default: output.csv)",
    )
    parser.add_argument(
        "--seed-urls",
        type=Path,
        default=None,
        help=(
            "Optional CSV file with columns 'url,molecule' listing tender "
            "detail-page URLs to include in addition to live search "
            "results. See seed_urls.example.csv."
        ),
    )
    parser.add_argument(
        "--seed-html-manifest",
        type=Path,
        default=None,
        help=(
            "Optional CSV file with columns 'url,molecule,html_file' "
            "pointing to locally saved copies of detail pages. Used as a "
            "fully offline fallback when PLACSP blocks automated requests. "
            "See seed_html_manifest.example.csv."
        ),
    )
    parser.add_argument(
        "--no-live-search",
        action="store_true",
        help=(
            "Skip the live PLACSP search step entirely (useful when running "
            "fully offline with --seed-html-manifest, or when PLACSP is "
            "known to be blocking this network)."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help=(
            "Max PLACSP result pages to follow per search term (25 results "
            "per page). Default 20 (~500 results), applied independently "
            "to each search term -- a molecule with fewer pages of results "
            "(e.g. Axitinib at 13 pages) simply stops early when PLACSP "
            "reports no more results, while one with more (e.g. 18-19 "
            "pages) is no longer cut off. Raise further for queries with "
            "even more total hits, e.g. --max-pages 30."
        ),
    )
    parser.add_argument(
        "--include-unconfirmed",
        action="store_true",
        help=(
            "Keep rows where moleculeDetected is False -- i.e. PLACSP's "
            "search matched the term, but the molecule name wasn't found "
            "in the scraped page text/title (often because the only "
            "mention is buried in a per-lot PDF attachment, which is out "
            "of scope). By default these rows are dropped so the CSV only "
            "contains confirmed matches."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    run(
        output_path=args.output,
        seed_urls_path=args.seed_urls,
        seed_html_manifest_path=args.seed_html_manifest,
        skip_live_search=args.no_live_search,
        max_pages=args.max_pages,
        include_unconfirmed=args.include_unconfirmed,
    )


if __name__ == "__main__":
    main()
