

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Molecule:
   
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


def variants_for(canonical_name: str) -> tuple[str, ...]:
    """Return the match variants for a given canonical molecule name."""
    for molecule in TARGET_MOLECULES:
        if molecule.canonical_name == canonical_name:
            return molecule.match_variants
    raise KeyError(f"Unknown molecule: {canonical_name!r}")
