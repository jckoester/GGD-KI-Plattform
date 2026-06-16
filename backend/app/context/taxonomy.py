"""Knoten-Taxonomie: valide category × content_type-Kombinationen und Lifecycle-Defaults.

Lädt aus config/taxonomy.yaml als Single Source of Truth.
"""

from datetime import date
from pathlib import Path
from typing import Final
import yaml
import os

_taxonomy_path = Path(
    os.environ.get("TAXONOMY_PATH")
    or Path(__file__).resolve().parent.parent.parent.parent / "config" / "taxonomy.yaml"
)


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
    "kapitel": None,
    "lernsequenz": None,
    "methode": None,
    "sozialform": None,
    "operator_didaktisch": None,
    "jahresplan": None,
    "pruefungsanforderung": None,
    # artifact — zeitlich begrenzte Inhalte
    "unterrichtseinheit": None,   # Lehrkraft setzt manuell
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


# content_types mit valid_until_default: schuljahresende — Lifecycle endet am Schuljahresende
SCHULJAHRESENDE_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    ct["key"]
    for cat_info in _data["categories"].values()
    for ct in cat_info["content_types"]
    if ct.get("valid_until_default") == "schuljahresende"
)


def get_valid_until_schuljahresende(content_type: str | None) -> bool:
    """True wenn der content_type einen Schuljahresende-Lifecycle hat."""
    return content_type in SCHULJAHRESENDE_CONTENT_TYPES


_VALID_PRIOS = frozenset({"kern", "uebung", "vertiefung"})
_VALID_PHASEN_STATUS = frozenset({"geplant", "erledigt", "offen", "gestrichen"})


def validate_unterrichtsstunde_metadata(metadata: dict) -> None:
    """Validiert das metadata-Objekt eines unterrichtsstunde-Knotens.

    Wirft ValueError bei Verstößen gegen das Phasen-Schema.
    """
    phasen = metadata.get("phasen", [])
    if not isinstance(phasen, list):
        raise ValueError("metadata.phasen muss eine Liste sein")

    for i, phase in enumerate(phasen):
        prefix = f"phasen[{i}]"
        for field in ("id", "titel", "dauer_min", "prio", "status"):
            if field not in phase:
                raise ValueError(f"{prefix}.{field} ist Pflichtfeld")

        dauer = phase["dauer_min"]
        if not isinstance(dauer, (int, float)) or dauer <= 0:
            raise ValueError(f"{prefix}.dauer_min muss > 0 sein")

        if phase["prio"] not in _VALID_PRIOS:
            raise ValueError(
                f"{prefix}.prio '{phase['prio']}' ist ungültig. "
                f"Erlaubt: {sorted(_VALID_PRIOS)}"
            )

        if phase["status"] not in _VALID_PHASEN_STATUS:
            raise ValueError(
                f"{prefix}.status '{phase['status']}' ist ungültig. "
                f"Erlaubt: {sorted(_VALID_PHASEN_STATUS)}"
            )

        for field in ("methode", "material"):
            if field in phase and phase[field] is not None:
                val = phase[field]
                has_text = "text" in val
                has_node = "node_id" in val
                if has_text == has_node:
                    raise ValueError(
                        f"{prefix}.{field} muss genau eines von 'text' oder 'node_id' enthalten"
                    )


# content_types die ein Embedding erhalten — abgeleitet aus taxonomy.yaml (embedding: true)
EMBEDDING_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    ct["key"]
    for cat_info in _data["categories"].values()
    for ct in cat_info["content_types"]
    if ct.get("embedding")
)

# Welche metadata-Felder der Embedding-Job zusätzlich zu `content` einbezieht.
# Key: (category, content_type) — abgeleitet aus taxonomy.yaml (embedding_enrichment: [...])
EMBEDDING_ENRICHMENT: Final[dict[tuple[str, str], list[str]]] = {
    (cat, ct["key"]): ct["embedding_enrichment"]
    for cat, cat_info in _data["categories"].items()
    for ct in cat_info["content_types"]
    if ct.get("embedding_enrichment")
}
