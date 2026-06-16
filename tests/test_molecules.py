from pipeline.molecules import detect_molecule, variants_for


def test_detect_molecule_exact_english_name():
    name, detected, variant = detect_molecule("Suministro de Axitinib 5mg")
    assert detected is True
    assert name == "Axitinib"
    assert variant == "axitinib"


def test_detect_molecule_spanish_variant():
    name, detected, variant = detect_molecule("Compra de Abiraterona para oncología")
    assert detected is True
    assert name == "Abiraterone"
    assert variant == "abiraterona"


def test_detect_molecule_glatiramer_spanish_variant():
    name, detected, variant = detect_molecule("Acetato de glatirámero 40mg/ml")
    assert detected is True
    assert name == "Glatiramer Acetate"


def test_detect_molecule_no_match():
    name, detected, variant = detect_molecule("Suministro de gasas y vendas")
    assert detected is False
    assert name == ""
    assert variant is None


def test_detect_molecule_case_insensitive():
    name, detected, variant = detect_molecule("FINGOLIMOD cápsulas")
    assert detected is True
    assert name == "Fingolimod"


def test_detect_molecule_empty_string():
    name, detected, variant = detect_molecule("")
    assert detected is False
    assert name == ""
    assert variant is None


def test_variants_for_known_molecule():
    variants = variants_for("Tamsulosin")
    assert "tamsulosin" in variants
    assert "tamsulosina" in variants


def test_variants_for_unknown_molecule_raises():
    import pytest

    with pytest.raises(KeyError):
        variants_for("NotARealMolecule")
