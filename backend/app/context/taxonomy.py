"""Knoten-Taxonomie: valide category × content_type-Kombinationen und Lifecycle-Defaults."""

from typing import Final

# Valide content_types pro category.
# Erweiterungen erfordern einen bewussten Entscheid über Embedding-Strategie,
# Edge-Konventionen und Lifecycle-Defaults — daher kein dynamisches Laden.
VALID_CONTENT_TYPES: Final[dict[str, frozenset[str]]] = {
    "document": frozenset({
        "formatierungsvorlage",
        "vokabelliste",
        "aufgabenblatt",
        "quelltext",
        "konvention",
        "methodenblatt",
        "operatorenblatt",
        "praesentation",
    }),
    "knowledge": frozenset({
        "fachplan",
        "themengebiet",
        "leitidee",
        "ik_kompetenz",
        "pk_gruppe",
        "pk_kompetenz",
        "leitperspektive",
        "leitperspektive_aspekt",
        "curriculum",
        "unterrichtseinheit",
        "methode",
        "operator_didaktisch",
        "jahresplan",
        "pruefungsanforderung",
    }),
    "artifact": frozenset({
        "unterrichtsentwurf",
        "unterrichtsstunde",
        "reflexion",
        "arbeitsblatt",
        "aufgabe",
        "klausur",
        "code_beispiel",
        "lerntext",
        "gliederung",
        "mindmap",
        "lernplan",
        "schuelertext",
        "feedback_text",
    }),
    "concept": frozenset({
        "funktion",
        "bauteil",
        "operator_math",
        "abstrakt",
    }),
}

# Voreinstellung für valid_until-Offset in Tagen ab heute (None = permanent).
# Wird im Upload-Formular und beim Assistenten-Artefakt-Dialog als Vorschlagswert
# verwendet; die Lehrkraft kann überschreiben.
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
    "unterrichtsentwurf": None,       # Lehrkraft setzt manuell
    "unterrichtsstunde": None,         # Lehrkraft setzt manuell
    "reflexion": None,
    "arbeitsblatt": None,              # permanent wiederverwendbar
    "aufgabe": None,                   # permanent wiederverwendbar
    "klausur": None,
    "code_beispiel": None,
    "lerntext": None,
    "gliederung": 42,                  # ~6 Wochen
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
    "fachplan": ("global", "global"),
    "leitidee": ("global", "global"),
    "ik_kompetenz": ("global", "global"),
    "pk_gruppe": ("global", "global"),
    "pk_kompetenz": ("global", "global"),
    "leitperspektive": ("global", "global"),
    "leitperspektive_aspekt": ("global", "global"),
    "themengebiet": ("school", "school"),
    "curriculum": ("school", "subject"),
    "unterrichtseinheit": ("school", "subject"),
    "methode": ("school", "subject"),
    "operator_didaktisch": ("school", "subject"),
    "jahresplan": ("private", "private"),
    "pruefungsanforderung": ("school", "school"),
    "formatierungsvorlage": ("school", "school"),
    "konvention": ("school", "school"),
    "methodenblatt": ("school", "subject"),
    "operatorenblatt": ("school", "subject"),
    "praesentation": ("school", "subject"),
    "aufgabenblatt": ("group", "private"),
    "vokabelliste": ("group", "private"),
    "quelltext": ("group", "private"),
    "unterrichtsentwurf": ("private", "private"),
    "unterrichtsstunde": ("private", "private"),
    "reflexion": ("private", "private"),
    "arbeitsblatt": ("group", "private"),
    "aufgabe": ("group", "private"),
    "klausur": ("private", "private"),
    "code_beispiel": ("school", "private"),
    "lerntext": ("school", "private"),
    "gliederung": ("private", "private"),
    "mindmap": ("private", "private"),
    "lernplan": ("private", "private"),
    "schuelertext": ("private", "private"),
    "feedback_text": ("private", "private"),
    "funktion": ("school", "school"),
    "bauteil": ("school", "school"),
    "operator_math": ("school", "school"),
    "abstrakt": ("school", "school"),
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


# Gibt an, welche metadata-Felder der Embedding-Job zusaetzlich zu `content`
# in den Embedding-Input einbezieht. Kein Eintrag -> nur content wird embedded.
EMBEDDING_ENRICHMENT: Final[dict[tuple[str, str], list[str]]] = {
    ("concept", "bauteil"): ["metadata.schaltzeichen.beschreibung"],
    ("concept", "funktion"): ["metadata.signatur"],
    ("knowledge", "ik_kompetenz"): ["metadata.breadcrumb"],
    ("knowledge", "pk_kompetenz"): ["metadata.breadcrumb"],
}
