from __future__ import annotations

import logging
import re
from dataclasses import replace

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from pipeline.models import TenderRecord
from pipeline.molecules import (
    TARGET_MOLECULES,
    detect_all_molecules,
    detect_molecule,
    variants_for,
)

logger = logging.getLogger(__name__)


LABEL_MAP: dict[str, str] = {
    "expediente": "noticeId",
    "objeto del contrato": "title",
    "órgano de contratación": "buyer",
    "entidad adjudicadora": "buyer",
    "código cpv": "cpv",
    "cpv": "cpv",
    "importe total ofertado (sin impuestos)": "awardValue",
    "importe (sin impuestos)": "awardValue",
    "presupuesto base de licitación sin impuestos": "awardValue",
    "adjudicatario": "awardedSupplier",
    "winning party": "awardedSupplier",
    "partido ganador": "awardedSupplier",
    "procedimiento": "procedureType",
    "procedimiento de contratación": "procedureType",
    "procurement procedure": "procedureType",
    "tramitación": "procedureType",
    "fecha de publicación": "publicationDate",
    "fecha del acuerdo": "publicationDate",
    "número de lote": "lotId",
    "nº de lote": "lotId",
    "lote": "lotId",
    "lot number": "lotId",
}

# Values that are really UI link/button labels rather than real data --
# PLACSP renders these in place of the actual field value on some pages
# (e.g. when the award detail lives on a separate sub-page we don't fetch).
# Any extracted value matching one of these (case-insensitive) is treated
# as "not found" rather than written to the CSV as-is.
_PLACEHOLDER_VALUES = {
    "ver detalle de la adjudicación",
    "ver detalle de la adjudicacion",
}

# Matches a lot number embedded in a noticeId, e.g.
# "52/F/26/SU/GE/T/015-01_LOTE_27" -> "27".
_LOTE_IN_ID_RE = re.compile(r"LOTE[_\s]?(\d+)", re.IGNORECASE)


def parse_detail_page(
    html: str, source_url: str, target_molecule: str
) -> list[TenderRecord]:
    """Parse a PLACSP tender detail page into one or more `TenderRecord`s.

    All the non-molecule fields (title, buyer, dates, award value, etc.)
    are extracted once from the page. The page text is then checked
    against *every* molecule in `TARGET_MOLECULES` -- not just
    `target_molecule` -- because a single tender often covers several
    drugs (e.g. a framework agreement listing both "Axitinib" and
    "Abiraterone" as separate lots/lines). Each molecule that's actually
    mentioned on the page gets its own output row, so the tender shows up
    correctly under every molecule's search results, regardless of which
    search term happened to surface this URL.

    If no target molecule is found on the page at all, a single
    unconfirmed row is returned for `target_molecule` (moleculeDetected=
    False), preserving the previous behavior so `--include-unconfirmed`
    still works and nothing is silently dropped.
    """
    soup = BeautifulSoup(html, "html.parser")
    record = TenderRecord(country="ES", currency="EUR", sourceUrl=source_url)

    text_by_label = _collect_label_value_pairs(soup)

    for label, value in text_by_label.items():
        field_name = LABEL_MAP.get(label)
        if not field_name:
            continue
        if _is_placeholder(value):
            continue
        current = getattr(record, field_name)
        if not current:
            setattr(record, field_name, value)
        elif field_name == "publicationDate" and label == "fecha de publicación":
            
            setattr(record, field_name, value)


    if not record.title:
        record.title = _extract_title_fallback(soup)


    if not record.noticeId:
        record.noticeId = _extract_id_from_url(source_url)

    if record.awardValue:
        record.awardValue = _normalise_amount(record.awardValue)

    # awardedSupplier: drop placeholder link text if it slipped through any
    # path other than the label/value loop above (e.g. a future fallback).
    if record.awardedSupplier and _is_placeholder(record.awardedSupplier):
        record.awardedSupplier = ""

    # lotId fallback: the detail page rarely exposes a dedicated lot field,
    # but multi-lot tenders often encode the lot number directly in the
    # noticeId (e.g. "...015-01_LOTE_27"). Use that when present.
    if not record.lotId:
        record.lotId = _extract_lot_from_id(record.noticeId)

    # Publication date fallback: PLACSP's "Advertisements and documents" /
    # "Anuncios y documentos" section lists each published document as a
    # table row (document type | link | timestamp), with NO preceding
    # "Fecha:" label at all -- so the label-based patterns above find
    # nothing on many real pages. As a fallback, scan the whole page for a
    # bare date+time stamp like "27/01/2022 16:20:06" and use the first
    # one found (documents are typically listed in publication order, so
    # this is usually the earliest/original publication date).
    if not record.publicationDate:
        record.publicationDate = _extract_first_timestamp(soup)

    # Publication date: normalise "16/12/2021" -> "2021-12-16".
    if record.publicationDate:
        record.publicationDate = _normalise_date(record.publicationDate)

    # Molecule matching: check the title (and full page text as a fallback)
    # against ALL target molecules' known variants, not just
    # `target_molecule`. A tender can legitimately cover several drugs
    # (e.g. separate lots for Axitinib and Abiraterone within the same
    # framework agreement), and we want a confirmed row for each one that
    # actually appears on the page -- regardless of which molecule's
    # search term originally found this URL.
    haystack = record.title or soup.get_text(" ", strip=True)
    all_matches = detect_all_molecules(haystack)

    if all_matches:
        records = [
            replace(
                record,
                productMolecule=canonical_name,
                moleculeDetected=True,
                moleculeVariant=variant,
            )
            for canonical_name, variant in all_matches
        ]
        # Make sure the molecule we were specifically asked to search for
        # is represented even if, oddly, it wasn't picked up by
        # `detect_all_molecules` for some reason (defensive; shouldn't
        # normally trigger since `target_molecule`'s variants are a
        # subset of what `detect_all_molecules` checks).
        if target_molecule and not any(
            r.productMolecule == target_molecule for r in records
        ):
            _, generic_detected, generic_variant = _detect_for_molecule(
                haystack, target_molecule
            )
            records.append(
                replace(
                    record,
                    productMolecule=target_molecule,
                    moleculeDetected=generic_detected,
                    moleculeVariant=generic_variant or "",
                )
            )
        return records

    # Nothing matched at all: fall back to generic detection so we at
    # least report *something* was matched, even if it wasn't this exact
    # target molecule's canonical spelling (e.g. page only contains a
    # typo'd variant). Returns a single unconfirmed row for
    # `target_molecule` if even that fails, so callers using
    # --include-unconfirmed still see the row.
    _, generic_detected, generic_variant = detect_molecule(haystack)
    record.productMolecule = target_molecule
    record.moleculeDetected = generic_detected
    record.moleculeVariant = generic_variant or ""
    return [record]


def _collect_label_value_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """Build a dict of {lowercased label: value} from the detail page.

    Handles three common patterns seen on PLACSP pages:
      1. <dt>Label</dt><dd>Value</dd>
      2. <th>Label</th><td>Value</td>  (and table rows generally)
      3. Bold/strong element containing "Label" followed by sibling text,
         e.g. the bullet-style "* Importe \\n 924,6 EUR." layout from the
         pasted page source.
    """
    pairs: dict[str, str] = {}

    # Pattern 1: definition lists.
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            label = _clean_text(dt.get_text())
            value = _clean_text(dd.get_text())
            if label and value:
                pairs.setdefault(label.lower(), value)

    # Pattern 2: table rows (th/td or two td cells).
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            label = _clean_text(cells[0].get_text())
            value = _clean_text(cells[1].get_text())
            if label and value:
                pairs.setdefault(label.lower(), value)

    # Pattern 3: bold/strong "label" elements followed by text, matching
    # the bullet layout from the worked example (e.g.
    # "**Importe**\n924,6 EUR.").
    for bold in soup.find_all(["b", "strong"]):
        label = _clean_text(bold.get_text())
        if not label:
            continue
        value = _clean_text(_text_after(bold))
        if label and value:
            pairs.setdefault(label.lower(), value)

    # Pattern 4: ANY element whose own text is *exactly* a known label
    # (optionally with a trailing ':'), regardless of tag name. This is the
    # most general pattern, and catches layouts like
    # <span class="label">Adjudicatario</span><span class="value">MERCK...</span>
    # or label/value as separate <div>/<li> siblings, which patterns 1-3
    # don't cover. We only look for *known* labels here (from LABEL_MAP),
    # since scanning every element for arbitrary "label-like" text would be
    # too noisy.
    known_labels = set(LABEL_MAP.keys())
    for element in soup.find_all(True):
        # Only consider elements whose *direct* text (ignoring nested tags)
        # is just the label -- this avoids matching huge parent containers
        # that happen to *contain* the label text somewhere deep inside.
        own_text = element.find(string=True, recursive=False)
        if own_text is None:
            continue
        label = _clean_text(str(own_text)).lower().rstrip(":").strip()
        if label not in known_labels:
            continue
        if label in pairs:
            continue

        value = _find_next_value(element)
        if value:
            pairs.setdefault(label, value)

    return pairs


def _find_next_value(label_element) -> str:
    
    # 1. Next sibling element.
    for sibling in label_element.next_siblings:
        if getattr(sibling, "name", None) is not None:
            text = _clean_text(sibling.get_text())
            if text:
                return text
        else:
            text = _clean_text(str(sibling))
            if text:
                return text

    # 2. Parent's next sibling element (label and value are "columns").
    parent = label_element.parent
    if parent is not None:
        for sibling in parent.next_siblings:
            if getattr(sibling, "name", None) is not None:
                text = _clean_text(sibling.get_text())
                if text:
                    return text

    return ""


def _text_after(tag) -> str:
    
    parts: list[str] = []
    for sibling in tag.next_siblings:
        name = getattr(sibling, "name", None)
        if name in ("b", "strong"):
            break
        if name in ("br",):
            continue
        text = sibling.get_text() if hasattr(sibling, "get_text") else str(sibling)
        parts.append(text)
        if "\n" in text and "".join(parts).strip():
            # Stop at the first line break once we have some content -- the
            # bullet layout puts one value per line after the label.
            break
    return " ".join(parts)


def _extract_title_fallback(soup: BeautifulSoup) -> str:
    
    full_text = soup.get_text("\n", strip=True)
    match = re.search(
        r"Objeto del Contrato\s*:?\s*\n?(.+)", full_text, re.IGNORECASE
    )
    if match:
        return _clean_text(match.group(1).splitlines()[0])
    return ""


_TIMESTAMP_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}:\d{2}\b")


def _extract_first_timestamp(soup: BeautifulSoup) -> str:
    
    full_text = soup.get_text(" ", strip=True)
    match = _TIMESTAMP_RE.search(full_text)
    return match.group(1) if match else ""


def _extract_id_from_url(url: str) -> str:
    """Extract PLACSP's `idEvl` tender identifier from a detail-page URL."""
    match = re.search(r"idEvl=([^&]+)", url)
    if not match:
        return ""
    # URL-decode %3D -> = and strip any trailing/leading '=' padding noise.
    value = match.group(1).replace("%3D", "=").rstrip("=")
    return value


def _extract_lot_from_id(notice_id: str) -> str:
    """Pull a lot number out of a noticeId like "...015-01_LOTE_27" -> "27".

    Returns "" if the noticeId has no embedded lot reference.
    """
    if not notice_id:
        return ""
    match = _LOTE_IN_ID_RE.search(notice_id)
    return match.group(1) if match else ""


def _is_placeholder(value: str) -> bool:
    """True if `value` is UI link text rather than real extracted data."""
    return value.strip().lower() in _PLACEHOLDER_VALUES


_AMOUNT_RE = re.compile(r"[\d.,]+")


def _normalise_amount(raw: str) -> str:
    """Convert e.g. "764,13 EUR." -> "764.13". Returns "" if unparseable."""
    match = _AMOUNT_RE.search(raw)
    if not match:
        logger.debug("Could not extract a numeric amount from %r", raw)
        return ""

    number = match.group(0)
    # Spanish format uses '.' as thousands separator and ',' as decimal.
    if "," in number:
        number = number.replace(".", "").replace(",", ".")

    try:
        return f"{float(number):.2f}"
    except ValueError:
        logger.debug("Could not parse normalised amount %r from %r", number, raw)
        return ""


def _normalise_date(raw: str) -> str:
    """Convert a date like "16/12/2021" -> "2021-12-16" (YYYY-MM-DD)."""
    try:
        parsed = date_parser.parse(raw, dayfirst=True)
    except (ValueError, OverflowError):
        logger.debug("Could not parse date %r", raw)
        return ""
    return parsed.strftime("%Y-%m-%d")


def _detect_for_molecule(text: str, canonical_name: str) -> tuple[str, bool, str | None]:
    """Check `text` against one molecule's variants specifically."""
    lowered = text.lower()
    for variant in variants_for(canonical_name):
        if variant in lowered:
            return canonical_name, True, variant
    return canonical_name, False, None


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip common bullet/separator characters."""
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip("*: \u00a0")
