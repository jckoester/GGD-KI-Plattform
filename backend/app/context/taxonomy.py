"""Knoten-Taxonomie: valide category × content_type-Kombinationen und Lifecycle-Defaults.

Lädt aus config/taxonomy.yaml als Single Source of Truth.
"""

from pathlib import Path
from typing import Final
import yaml
import os

# Ermittele den absoluten Pfad dieses Moduls
_module_path = Path(__file__).resolve()
# Navigiere zum Projekt-Root: backend/app/context -> backend -> Projekt-Root
_project_root = _module_path.parent.parent.parent.parent
_taxonomy_path = _project_root / "config" / "taxonomy.yaml"


def _load() -> dict:
    with open(_taxonomy_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_data = _load()

# dict[category_key, list[content_type_key]]
VALID_CONTENT_TYPES: Final[dict[str, list[str]]] = {
    cat: [ct["key"] for ct in info["content_types"]]
    for cat, info in _data["categories"].items()
}

# frozenset[content_type_key] — identisch mit SCOPE_ANCHOR_CONTENT_TYPES in frontend
VALID_SCOPE_ANCHOR_TYPES: Final[frozenset[str]] = frozenset(
    ct["key"]
    for cat_info in _data["categories"].values()
    for ct in cat_info["content_types"]
    if ct.get("scope_anchor")
)

# dict[content_type_key, category_key] — für schnelle Rückwärtssuche
CONTENT_TYPE_TO_CATEGORY: Final[dict[str, str]] = {
    ct["key"]: cat
    for cat, info in _data["categories"].items()
    for ct in info["content_types"]
}

# dict[category, color_token] für Frontend-Icons
CATEGORY_COLORS: Final[dict[str, str]] = {
    cat: info["color"]
    for cat, info in _data["categories"].items()
}

# Voreinstellung für valid_until-Offset in Tagen ab heute (None = permanent).
VALID_UNTIL_DEFAULTS_DAYS: Final[dict[str, int | None]] = {
    # document
    "formatierungsvorlage": None,
    "vokabelliste": None,
    "aufgabenblatt": None,
    "quelltext": None,
    "konvention": None,
    "methodenblatt": None,
    "operatorenblatt": None,
    "praesentation": None,
    # knowledge
    "fachplan": None,
    "leitidee": None,
    "ik_kompetenz": None,
    "pk_gruppe": None,
    "pk_kompetenz": None,
    "leitperspektive": None,
    "leitperspektive_aspekt": None,
    "themengebiet": None,
    "curriculum": None,
    "unterrichtseinheit": None,
    "methode": None,
    "operator_didaktisch": None,
    "jahresplan": None,
    "pruefungsanforderung": None,
    # artifact — zeitlich begrenzte Inhalte
    "unterrichtsentwurf": None,  # Lehrkraft setzt manuell
    "unterrichtsstunde": None,    # Lehrkraft setzt manuell
    "reflexion": None,
    "arbeitsblatt": None,         # permanent wiederverwendbar
    "aufgabe": None,              # permanent wiederverwendbar
    "klausur": None,
    "code_beispiel": None,
    "lerntext": None,
    "gliederung": 42,             # ~6 Wochen
    "mindmap": 42,
    "lernplan": 42,
    "schuelertext": 42,
    "feedback_text": 42,
    # concept
    "funktion": None,
    "bauteil": None,
    "operator_math": None,
    "abstrakt": None,
}


# Typische read_scope/write_scope-Defaults pro content_type.
# Tuple: (read_scope, write_scope)
SCOPE_DEFAULTS: Final[dict[str, tuple[str, str]]] = {
    ct["key"]: (
        ct["scope_defaults"]["read_scope"],
        ct["scope_defaults"]["write_scope"],
    )
    for cat_info in _data["categories"].values()
    for ct in cat_info["content_types"]
}


def validate_content_type(category: str, content_type: str | None) -> None:
    """Wirft ValueError wenn content_type zur category nicht passt.

    content_type darf None sein (strukturelle Knoten ohne fachliche Rolle).
    """
    if content_type is None:
        return
    valid = VALID_CONTENT_TYPES.get(category)
    if valid is None:
        raise ValueError(f"Unbekannte category: {category!r}")
    if content_type not in valid:
        raise ValueError(
            f"content_type {content_type!r} ist nicht gültig für category {category!r}. "
            f"Erlaubt: {sorted(valid)}"
        )


def get_valid_until_offset(content_type: str | None) -> int | None:
    """Gibt den empfohlenen valid_until-Offset in Tagen zurück (None = permanent)."""
    if content_type is None:
        return None
    return VALID_UNTIL_DEFAULTS_DAYS.get(content_type)


def get_scope_defaults(content_type: str | None) -> tuple[str, str]:
    """Gibt (read_scope, write_scope)-Defaults für content_type zurück.

    Fallback: ('school', 'private') wenn content_type unbekannt oder None.
    """
    if content_type is None:
        return ("school", "private")
    return SCOPE_DEFAULTS.get(content_type, ("school", "private"))


# Gibt an, welche metadata-Felder der Embedding-Job zusätzlich zu `content`
# in den Embedding-Input einbezieht. Kein Eintrag -> nur content wird embedded.
EMBEDDING_ENRICHMENT: Final[dict[tuple[str, str], list[str]]] = {
    ("concept", "bauteil"): ["metadata.schaltzeichen.beschreibung"],
    ("concept", "funktion"): ["metadata.signatur"],
    ("knowledge", "ik_kompetenz"): ["metadata.breadcrumb"],
    ("knowledge", "pk_kompetenz"): ["metadata.breadcrumb"],
}
