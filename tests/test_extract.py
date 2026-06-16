from pathlib import Path

import pytest

from pipeline.extract import (
    _extract_id_from_url,
    _normalise_amount,
    _normalise_date,
    parse_detail_page,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_html() -> str:
    return (FIXTURES_DIR / "sample_detail_page.html").read_text(encoding="utf-8")


SOURCE_URL = (
    "https://contrataciondelestado.es/wps/poc?"
    "uri=deeplink:detalle_licitacion&idEvl=pDbMY4x34FwSugstABGr5A%3D%3D"
)

SOURCE_URL_2 = (
    "https://contrataciondelestado.es/wps/poc?"
    "uri=deeplink:detalle_licitacion&idEvl=exampleSpanLayout123"
)


def test_parse_detail_page_span_layout():
    html = (FIXTURES_DIR / "sample_detail_page_span_layout.html").read_text(encoding="utf-8")
    record = parse_detail_page(html, source_url=SOURCE_URL_2, target_molecule="Tamsulosin")

    assert record.title == "Suministro de Tamsulosina para hospital"
    assert record.buyer == "Servicio Madrileño de Salud"
    assert record.cpv == "33690000"
    assert record.awardValue == "1500.00"
    assert record.awardedSupplier == "FARMA EJEMPLO S.A."
    assert record.procedureType == "Abierto"
    assert record.publicationDate == "2023-02-03"
    assert record.moleculeDetected is True
    assert record.moleculeVariant == "tamsulosin"


def test_parse_detail_page_extracts_core_fields(sample_html: str):
    record = parse_detail_page(sample_html, source_url=SOURCE_URL, target_molecule="Abiraterone")

    assert record.title == "Abiraterone, axitinib, geftinib..."
    assert record.buyer == "Rectorado de la Universidad Jaume I"
    assert record.cpv == "33690000"
    assert record.awardedSupplier == "MERCK LIFE SCIENCE S.L.U."
    assert record.procedureType == "Contrato Menor"
    assert record.country == "ES"
    assert record.currency == "EUR"
    assert record.sourceUrl == SOURCE_URL


def test_parse_detail_page_normalises_amount_and_date(sample_html: str):
    record = parse_detail_page(sample_html, source_url=SOURCE_URL, target_molecule="Abiraterone")

    assert record.awardValue == "764.13"
    assert record.publicationDate == "2021-12-16"


def test_parse_detail_page_detects_target_molecule(sample_html: str):
    record = parse_detail_page(sample_html, source_url=SOURCE_URL, target_molecule="Abiraterone")

    assert record.productMolecule == "Abiraterone"
    assert record.moleculeDetected is True
    assert record.moleculeVariant == "abiraterone"


def test_parse_detail_page_detects_secondary_molecule_via_generic_fallback(sample_html: str):
    # The page text also mentions "axitinib", even though we searched for
    # Abiraterone. If we pass Axitinib as the target, it should be detected
    # directly via this molecule's own variants.
    record = parse_detail_page(sample_html, source_url=SOURCE_URL, target_molecule="Axitinib")

    assert record.productMolecule == "Axitinib"
    assert record.moleculeDetected is True
    assert record.moleculeVariant == "axitinib"


def test_parse_detail_page_no_molecule_present():
    html = "<html><body><b>Objeto del Contrato</b>: Suministro de gasas</body></html>"
    record = parse_detail_page(html, source_url=SOURCE_URL, target_molecule="Fingolimod")

    assert record.productMolecule == "Fingolimod"
    assert record.moleculeDetected is False
    assert record.moleculeVariant == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("764,13 EUR.", "764.13"),
        ("924,6 EUR.", "924.60"),
        ("1.256,00 EUR.", "1256.00"),
        ("not a number", ""),
    ],
)
def test_normalise_amount(raw: str, expected: str):
    assert _normalise_amount(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("16/12/2021", "2021-12-16"),
        ("27/01/2022", "2022-01-27"),
        ("not a date", ""),
    ],
)
def test_normalise_date(raw: str, expected: str):
    assert _normalise_date(raw) == expected


def test_extract_id_from_url():
    url = "https://example.com/wps/poc?uri=deeplink:x&idEvl=pDbMY4x34FwSugstABGr5A%3D%3D"
    assert _extract_id_from_url(url) == "pDbMY4x34FwSugstABGr5A"


def test_extract_id_from_url_missing():
    assert _extract_id_from_url("https://example.com/no-id-here") == ""


def test_publication_date_falls_back_to_bare_timestamp():
    # No "Fecha de Publicación" label at all -- just a bare timestamp in a
    # documents table, matching the real PLACSP page structure discovered
    # via live testing.
    html = """
    <html><body>
    <table>
      <tr><td>Document</td><td>Veure documents</td><td>27/01/2022 16:20:06</td></tr>
    </table>
    </body></html>
    """
    record = parse_detail_page(html, source_url=SOURCE_URL, target_molecule="Abiraterone")
    assert record.publicationDate == "2022-01-27"
