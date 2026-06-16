"""
Target molecules and their known Spanish/English spelling variants.

Why this exists
----------------
PLACSP tender titles and descriptions mix English INN names, Spanish INN
names, brand names, and sometimes typos (e.g. "geftinib" instead of
"gefitinib", seen in the real example we worked from). To decide whether a
tender is "about" one of our target molecules, we do simple case-insensitive
substring matching against a list of known variants per molecule.

This is deliberately simple (per the assignment brief: "Simple text matching
is sufficient"). It will not catch every misspelling, but it covers the
documented Spanish INN variants plus a couple of common typos.

Add more variants here as you discover them in real tender text -- this is
the single place to extend matching coverage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Molecule:
    """A target molecule and the search/match terms associated with it."""

    # Canonical name used in the `productMolecule` output column.
    canonical_name: str

    # Term(s) we actually submit to the PLACSP search box. PLACSP's search
    # is a plain text search, so we search using the most common Spanish
    # term, since that's what tender descriptions are written in.
    search_terms: tuple[str, ...]

    # All known spelling variants (Spanish, English, common typos) used for
    # text matching against tender titles/descriptions. Matching is
    # case-insensitive, so list each variant once regardless of casing.
    match_variants: tuple[str, ...]


TARGET_MOLECULES: tuple[Molecule, ...] = (
    Molecule(
        canonical_name="Axitinib",
        search_terms=("Axitinib",),
        match_variants=("axitinib",),
    ),
    Molecule(
        canonical_name="Abiraterone",
        search_terms=("Abiraterone", "Abiraterona"),
        match_variants=("abiraterone", "abiraterona"),
    ),
    Molecule(
        canonical_name="Fingolimod",
        search_terms=("Fingolimod",),
        match_variants=("fingolimod",),
    ),
    Molecule(
        canonical_name="Tamsulosin",
        search_terms=("Tamsulosina", "Tamsulosin"),
        match_variants=("tamsulosin", "tamsulosina"),
    ),
    Molecule(
        canonical_name="Glatiramer Acetate",
        search_terms=("Acetato de glatiramero", "Glatiramer"),
        match_variants=(
            "glatiramer acetate",
            "acetato de glatiramero",
            "acetato de glatirámero",
            "acetato de glatiramer",
            "glatiramero",
            "glatirámero",
            "glatiramer",
        ),
    ),
)


def detect_molecule(text: str) -> tuple[str, bool, str | None]:
    """Check `text` against all known molecule variants.

    Parameters
    ----------
    text:
        Free text to search (e.g. a tender title or description).

    Returns
    -------
    A 3-tuple of:
        - the canonical molecule name that matched first (or "" if none)
        - whether *any* molecule matched (moleculeDetected)
        - the exact variant string that matched (moleculeVariant), or None

    Note: if multiple molecules match the same text (e.g. a combined order
    for several drugs, as in our worked example "Abiraterone, axitinib,
    geftinib..."), this returns only the first match in declaration order.
    The pipeline calls this once per *target molecule being searched for*,
    so in practice each row is checked against its own molecule's variants
    specifically -- see pipeline/extract.py.
    """
    if not text:
        return "", False, None

    lowered = text.lower()
    for molecule in TARGET_MOLECULES:
        for variant in molecule.match_variants:
            if variant in lowered:
                return molecule.canonical_name, True, variant

    return "", False, None


def variants_for(canonical_name: str) -> tuple[str, ...]:
    """Return the match variants for a given canonical molecule name."""
    for molecule in TARGET_MOLECULES:
        if molecule.canonical_name == canonical_name:
            return molecule.match_variants
    raise KeyError(f"Unknown molecule: {canonical_name!r}")
