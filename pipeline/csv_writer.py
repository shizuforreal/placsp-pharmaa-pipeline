from __future__ import annotations

import csv
import logging
from pathlib import Path

from pipeline.models import CSV_COLUMNS, TenderRecord

logger = logging.getLogger(__name__)


def write_csv(records: list[TenderRecord], output_path: Path) -> None:
    """Write `records` to `output_path` as UTF-8 CSV with a header row.

    Creates parent directories if needed. Overwrites any existing file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_row())

    logger.info("Wrote %d row(s) to %s", len(records), output_path)
