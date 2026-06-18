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
 
    if not text:
        return "", False, None

    lowered = text.lower()
    for molecule in TARGET_MOLECULES:
        for variant in molecule.match_variants:
            if variant in lowered:
                return molecule.canonical_name, True, variant

    return "", False, None


def detect_all_molecules(text: str) -> list[tuple[str, str]]:
    
    if not text:
        return []

    lowered = text.lower()
    matches: list[tuple[str, str]] = []
    for molecule in TARGET_MOLECULES:
        for variant in molecule.match_variants:
            if variant in lowered:
                matches.append((molecule.canonical_name, variant))
                break  # one match per molecule is enough; move to the next
    return matches


def variants_for(canonical_name: str) -> tuple[str, ...]:
    """Return the match variants for a given canonical molecule name."""
    for molecule in TARGET_MOLECULES:
        if molecule.canonical_name == canonical_name:
            return molecule.match_variants
    raise KeyError(f"Unknown molecule: {canonical_name!r}")
