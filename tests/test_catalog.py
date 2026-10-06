"""Catalog space-name normalization tests."""

from __future__ import annotations

from app.catalog_spaces import is_furniture_caption, normalize_space_name


def test_common_aliases() -> None:
    """Map drawing labels onto quiz catalog spaces."""
    assert normalize_space_name("KITCHEN") == "Kitchen"
    assert normalize_space_name("M. BEDROOM") == "Master Bedroom"
    assert normalize_space_name("POOJA") == "Puja Room"
    assert normalize_space_name("TOILET") == "Bathrooms / Toilets"
    assert normalize_space_name("LIVING + DINING") == "Living Room"
    assert normalize_space_name("WORK AREA") == "Study / Home Office"
    assert normalize_space_name("WALK IN") == "Walk-in Wardrobe"


def test_furniture_captions_are_not_spaces() -> None:
    """Existing furniture labels must not become catalog spaces."""
    assert is_furniture_caption("SOFA")
    assert is_furniture_caption("SIDE TABLE +")
    assert is_furniture_caption("3 SEATER")
    assert is_furniture_caption("TV UNIT")
    assert is_furniture_caption("WARDROBE")
    assert is_furniture_caption("PUJA UNIT")
    assert normalize_space_name("WARDROBE") is None
    assert normalize_space_name("PUJA UNIT") is None
    assert normalize_space_name("SOFA") is None
    assert normalize_space_name("FRIDGE") is None


def test_unknown_returns_none() -> None:
    """Unrecognised labels stay unmapped."""
    assert normalize_space_name("NORTH") is None
    assert normalize_space_name("") is None
