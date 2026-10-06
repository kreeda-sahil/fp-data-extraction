"""Canonical space names from the furniture quiz catalog and alias mapping."""

from __future__ import annotations

CANONICAL_SPACES: tuple[str, ...] = (
    "Living Room",
    "Dining Room",
    "Kitchen",
    "Master Bedroom",
    "Bedroom 2",
    "Bedroom 3",
    "Guest Bedroom",
    "Kids' Bedroom",
    "Study / Home Office",
    "Puja Room",
    "Entertainment / Family Room",
    "Home Theatre",
    "Bathrooms / Toilets",
    "Utility / Laundry",
    "Balcony",
    "Terrace",
    "Entrance / Foyer",
    "Walk-in Wardrobe",
    "Dressing Room",
    "Store Room",
    "Servant / Staff Room",
    "Other",
)

_ALIAS_TO_CANONICAL: dict[str, str] = {
    "living": "Living Room",
    "living room": "Living Room",
    "living + dining": "Living Room",
    "living dining": "Living Room",
    "living+dining": "Living Room",
    "lounge": "Living Room",
    "drawing room": "Living Room",
    "dining": "Dining Room",
    "dining room": "Dining Room",
    "kitchen": "Kitchen",
    "master bedroom": "Master Bedroom",
    "master bedroom 01": "Master Bedroom",
    "m. bedroom": "Master Bedroom",
    "m bedroom": "Master Bedroom",
    "m.bedroom": "Master Bedroom",
    "master": "Master Bedroom",
    "bedroom": "Bedroom 2",
    "bedroom 01": "Master Bedroom",
    "bedroom 02": "Bedroom 2",
    "bedroom 2": "Bedroom 2",
    "bedroom 3": "Bedroom 3",
    "parent's bedroom": "Bedroom 2",
    "parent's bedroom 02": "Bedroom 2",
    "parents bedroom": "Bedroom 2",
    "guest bedroom": "Guest Bedroom",
    "kids bedroom": "Kids' Bedroom",
    "kids' bedroom": "Kids' Bedroom",
    "kid bedroom": "Kids' Bedroom",
    "children bedroom": "Kids' Bedroom",
    "study": "Study / Home Office",
    "study room": "Study / Home Office",
    "home office": "Study / Home Office",
    "work area": "Study / Home Office",
    "conference room": "Study / Home Office",
    "puja": "Puja Room",
    "pooja": "Puja Room",
    "puja room": "Puja Room",
    "pooja room": "Puja Room",
    "family room": "Entertainment / Family Room",
    "home theatre": "Home Theatre",
    "home theater": "Home Theatre",
    "toilet": "Bathrooms / Toilets",
    "toilets": "Bathrooms / Toilets",
    "toilet -2": "Bathrooms / Toilets",
    "toilet-2": "Bathrooms / Toilets",
    "bathroom": "Bathrooms / Toilets",
    "bathrooms": "Bathrooms / Toilets",
    "wash area": "Utility / Laundry",
    "shower": "Bathrooms / Toilets",
    "powder": "Bathrooms / Toilets",
    "powder room": "Bathrooms / Toilets",
    "wc": "Bathrooms / Toilets",
    "utility": "Utility / Laundry",
    "laundry": "Utility / Laundry",
    "utility / laundry": "Utility / Laundry",
    "balcony": "Balcony",
    "terrace": "Terrace",
    "entrance": "Entrance / Foyer",
    "foyer": "Entrance / Foyer",
    "lobby": "Entrance / Foyer",
    "entry": "Entrance / Foyer",
    "walk in": "Walk-in Wardrobe",
    "walk in wardrobe": "Walk-in Wardrobe",
    "walk-in wardrobe": "Walk-in Wardrobe",
    "dressing": "Dressing Room",
    "dressing room": "Dressing Room",
    "store": "Store Room",
    "store room": "Store Room",
    "servant": "Servant / Staff Room",
    "staff room": "Servant / Staff Room",
    "servant room": "Servant / Staff Room",
}

_FURNITURE_PHRASES: frozenset[str] = frozenset(
    {
        "sofa",
        "sofas",
        "seater",
        "3 seater",
        "side table",
        "side table +",
        "table",
        "tables",
        "center table",
        "centre table",
        "console",
        "tv unit",
        "crockery",
        "crockery unit",
        "fridge",
        "refrigerator",
        "appliances",
        "pantry",
        "pullout",
        "platform",
        "planter",
        "wardrobe",
        "puja unit",
        "pooja unit",
        "washing",
        "machine",
        "washing machine",
        "overhead",
        "overhead storage",
        "shoe rack",
        "seat",
        "safety door",
        "panelling",
        "paneling",
        "+ panelling",
        "unit",
        "bed",
        "queen bed",
        "king bed",
        "single",
        "side",
        "area",
    }
)

_FURNITURE_WORDS: frozenset[str] = frozenset(
    {
        "sofa",
        "sofas",
        "seater",
        "table",
        "tables",
        "console",
        "crockery",
        "fridge",
        "refrigerator",
        "appliances",
        "pantry",
        "pullout",
        "platform",
        "planter",
        "wardrobe",
        "washing",
        "machine",
        "overhead",
        "seat",
        "bed",
        "single",
        "crockery",
    }
)

_SPACE_WORDS: frozenset[str] = frozenset(
    {
        "living",
        "dining",
        "kitchen",
        "bedroom",
        "toilet",
        "bathroom",
        "bath",
        "puja",
        "pooja",
        "foyer",
        "lobby",
        "balcony",
        "terrace",
        "utility",
        "laundry",
        "dressing",
        "study",
        "office",
        "store",
        "master",
        "kids",
        "guest",
        "servant",
        "passage",
        "walk",
        "wc",
        "shower",
        "powder",
    }
)


def _norm_key(raw: str) -> str:
    """Collapse punctuation and whitespace for matching."""
    cleaned = raw.lower().replace("_", " ").replace("/", " ").replace("+", " ")
    cleaned = cleaned.replace("-", " ")
    return " ".join(cleaned.split())


def is_furniture_caption(raw: str | None) -> bool:
    """Return True if the span is an existing-furniture label, not a space name."""
    if not raw:
        return False
    key = _norm_key(raw)
    if not key:
        return False
    if key in _FURNITURE_PHRASES:
        return True
    words = set(key.split())
    if "unit" in words and not (words & {"living", "dining", "kitchen", "toilet"}):
        return True
    if words & _FURNITURE_WORDS and not (words & _SPACE_WORDS):
        return True
    return False


def normalize_space_name(raw: str | None) -> str | None:
    """Map a free-text room label to a catalog space name, or None if unknown.

    Furniture captions never map, including bare wardrobe and puja unit.
    """
    if not raw:
        return None
    if is_furniture_caption(raw):
        return None
    stripped = raw.strip()
    if stripped in CANONICAL_SPACES:
        return stripped
    key = _norm_key(raw)
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    # Prefer longest alias contained in the key (not the reverse, which is too greedy).
    matches = [
        (alias, canonical)
        for alias, canonical in _ALIAS_TO_CANONICAL.items()
        if len(alias) >= 4 and alias in key
    ]
    if matches:
        matches.sort(key=lambda item: len(item[0]), reverse=True)
        return matches[0][1]
    return None
