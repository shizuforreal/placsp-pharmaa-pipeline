from __future__ import annotations

from dataclasses import dataclass, fields


CSV_COLUMNS: tuple[str, ...] = (
    "noticeId",
    "lotId",
    "title",
    "country",
    "buyer",
    "productMolecule",
    "moleculeDetected",
    "moleculeVariant",
    "cpv",
    "awardValue",
    "currency",
    "awardedSupplier",
    "publicationDate",
    "procedureType",
    "sourceUrl",
)


@dataclass
class TenderRecord:
    """One row of the output CSV: a single tender or tender lot."""

    noticeId: str = ""
    lotId: str = ""
    title: str = ""
    country: str = "ES"
    buyer: str = ""
    productMolecule: str = ""
    moleculeDetected: bool = False
    moleculeVariant: str = ""
    cpv: str = ""
    awardValue: str = ""
    currency: str = "EUR"
    awardedSupplier: str = ""
    publicationDate: str = ""
    procedureType: str = ""
    sourceUrl: str = ""

    def to_csv_row(self) -> dict[str, str]:
        """Return this record as a dict of strings, ready for `csv.DictWriter`.

        - Booleans become "TRUE"/"FALSE" (matches the assignment's example
          row formatting and is unambiguous in a CSV).
        - `None` values become "" (CSV convention for "no data").
        - Everything else is converted with `str()`.
        """
        row: dict[str, str] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None:
                row[field.name] = ""
            elif isinstance(value, bool):
                row[field.name] = "TRUE" if value else "FALSE"
            else:
                row[field.name] = str(value)
        return row
