"""
Filter a raw pipeline output CSV down to only rows where the target
molecule was actually detected in the page text (moleculeDetected == TRUE).

Why this exists
----------------
PLACSP's search engine matches across attached PDF/Excel documents, not
just the tender's own title/summary text. This means a search for e.g.
"Fingolimod" can return large framework-agreement tenders that never
mention Fingolimod anywhere in the page itself -- the term only appears in
an attached spec PDF, which this pipeline intentionally does not parse
(per the assignment's "Out of Scope" section).

Running the raw pipeline output through this filter keeps only the rows
where we have actual textual evidence of the molecule on the page itself,
which is a much higher-quality (if smaller) result set.

Usage
-----
    python filter_detected.py output.csv output_filtered.csv
"""

from __future__ import annotations

import csv
import sys


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python filter_detected.py <input.csv> <output.csv>")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    kept = [row for row in rows if row.get("moleculeDetected") == "TRUE"]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"Read {len(rows)} row(s) from {input_path}")
    print(f"Kept {len(kept)} row(s) with moleculeDetected=TRUE")
    print(f"Wrote filtered result to {output_path}")


if __name__ == "__main__":
    main()
