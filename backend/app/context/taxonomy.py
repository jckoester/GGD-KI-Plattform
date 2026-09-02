"""Knoten-Taxonomie: valide category × content_type-Kombinationen und Lifecycle-Defaults.

Lädt aus `taxonomy.yaml` **neben dieser Datei** als Single Source of Truth.

⚠️ **`taxonomy.yaml` ist eine Systemdatei, keine Betreiber-Konfiguration** (ADR-018,
Nachtrag 02.09.2026). Sie lag bis dahin in `config/` — dort wird sie im Betrieb als
ganzes Verzeichnis in den Container gemountet, war also die Datei auf dem Host und
neben `auth.yaml` zum Bearbeiten eingeladen. Hier gehört sie zum Abbild und ist im
Betrieb nicht mehr erreichbar.

Ein Teil der Tabellen hier wird aus ihr abgeleitet und kann gar nicht abweichen; ein
anderer Teil (`VALID_UNTIL_DEFAULTS_DAYS`, die Rollenboni) wird **von Hand** gepflegt
und driftet lautlos, wenn ein Typ dazukommt oder verschwindet. Gegen genau diese Drift
läuft beim Start `taxonomy_check.py`.
"""

from datetime import date
from pathlib import Path
from typing import Final
import yaml
import os

# `TAXONOMY_PATH` bleibt als Override bestehen — Tests laden damit eine abgewandelte
# Fassung. In `docker-compose.yml` steht die Variable bewusst **nicht** mehr: Ein
# gemounteter Pfad wäre genau die Hintertür, die der Umzug schließt.
_taxonomy_path = Path(
    os.environ.get("TAXONOMY_PATH")
    or Path(__file__).resolve().parent / "taxonomy.yaml"
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

# Importierte Bildungsplan-/Curriculum-Typen — aus der freien /knowledge-Liste
# ausgeschlossen (C2). Verwendet wird die Liste bislang nur im Frontend
# (`generate_taxonomy.py` → `BP_CURRICULUM_CONTENT_TYPES`); hier steht sie, damit die
# Startprüfung sie gegen die Typenliste halten kann.
BP_CURRICULUM_CONTENT_TYPES: Final[tuple[str, ...]] = tuple(
    _data.get("bp_curriculum_content_types") or ()
)

# Voreinstellung für valid_until-Offset in Tagen ab heute (None = permanent).
VALID_UNTIL_DEFAULTS_DAYS: Final[dict[str, int | None]] = {
    # document
    "formatierungsvorlage": None,
    "vokabelliste": None,
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
    "operator": None,
    "jahresplan": None,
    "pruefungsanforderung": None,
    "lfdb_baustein": None,
    "lfdb_themenblock": None,
    "lfdb_kompetenz": None,
    # artifact — zeitlich begrenzte Inhalte
    "unterrichtseinheit": None,   # Lehrkraft setzt manuell
    "unterrichtsstunde": None,    # Lehrkraft setzt manuell
    "arbeitsblatt": None,         # permanent wiederverwendbar
    "aufgabe": None,              # permanent wiederverwendbar
    "klausur": None,
    "code_beispiel": None,
    "lerntext": None,
    # Schüler-Artefakte: kein Tages-Offset, sondern `valid_until_default:
    # schuljahresende` in der YAML — dieselbe Grenze wie bei Stunde und Einheit.
    # Bis 02.09.2026 standen hier 42 Tage; die Zahl war ein auf fünf Typen
    # verallgemeinertes Beispiel aus ADR-013 („artifact.lernplan → ~6 Wochen") und
    # nie begründet. Sie ist vorläufig — siehe Todo „valid_until-Defaults prüfen".
    "lernplan": None,
    "schuelertext": None,
    "schuelerpraesentation": None,
    "strukturierung": None,
    "feedback_text": None,
    # concept
    "funktion": None,
    "bauteil": None,
    "begriff": None,
}
# ⚠️ **Diese Liste wird von Hand gepflegt und deckt jeden content_type ab.** Ein
# fehlender Eintrag fällt sonst nicht auf: `get_valid_until_offset` liefert über
# `.get()` ein `None`, und `None` heißt hier „läuft nie ab" — ein Typ, der eigentlich
# verfallen sollte, bliebe also stillschweigend für immer stehen. Vier Typen fehlten aus
# genau diesem Grund unbemerkt (`begriff`, die drei LFDB-Typen; bei ihnen war „permanent"
# zufällig richtig). `test_context_taxonomy.py` hält die Vollständigkeit jetzt fest.


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


# ── ui_status (ADR-019 F6) ───────────────────────────────────────────────────
#
# `ruhend` heißt: Der Typ erscheint in **keiner** Auswahl — kein Formular, kein Filter,
# keine Such-Facette, keine Material-Liste. Vorhandene Knoten bleiben les-, such- und
# traversierbar; die Schnittstelle nimmt sie weiterhin an. Es ist eine Aussage über die
# Oberfläche, keine Rechteprüfung.
#
# Warum es das braucht: Mehrere Typen stehen seit dem ersten Entwurf in der Taxonomie,
# ohne dass es einen Weg gäbe, so einen Knoten anzulegen. In einer Auswahlliste sind sie
# ein Versprechen, das die Anwendung nicht einlöst. Der Wechsel `ruhend → aktiv` gehört
# zu dem Arbeitspaket, das den Erzeugungsweg baut, und wird in der YAML begründet.
UI_STATUS: Final[dict[str, str]] = {
    ct["key"]: ct.get("ui_status", "aktiv")
    for cat_info in _data["categories"].values()
    for ct in cat_info["content_types"]
}

GUELTIGE_UI_STATUS: Final[frozenset[str]] = frozenset({"aktiv", "ruhend"})

RUHENDE_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    key for key, status in UI_STATUS.items() if status == "ruhend"
)


def ist_ruhend(content_type: str | None) -> bool:
    """True, wenn der Typ in keiner Auswahlfläche erscheinen soll."""
    return content_type in RUHENDE_CONTENT_TYPES


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

        for field in ("sozialform", "methode", "material"):
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

# Woraus der Embedding-Input eines Typs **vollständig** besteht — die Liste ersetzt den
# Standardaufbau. Key: (category, content_type), abgeleitet aus taxonomy.yaml
# (embedding_input: [...]). Quellen: `title`, `content`, `metadata.<pfad>` und
# `metadata.<liste>[].<feld>`.
#
# Der Unterschied zu `embedding_enrichment` ist die Richtung: Anreicherung **ergänzt**
# `content`, dieser Eintrag **bestimmt** den Input und kann damit als einziger etwas
# gezielt weglassen (ADR-017, Nachtrag 01.09.2026: das Thema, nicht der Ablauf).
EMBEDDING_INPUT: Final[dict[tuple[str, str], list[str]]] = {
    (cat, ct["key"]): ct["embedding_input"]
    for cat, cat_info in _data["categories"].items()
    for ct in cat_info["content_types"]
    if ct.get("embedding_input")
}

# Welche metadata-Felder der Embedding-Job zusätzlich zu `content` einbezieht.
# Key: (category, content_type) — abgeleitet aus taxonomy.yaml (embedding_enrichment: [...])
EMBEDDING_ENRICHMENT: Final[dict[tuple[str, str], list[str]]] = {
    (cat, ct["key"]): ct["embedding_enrichment"]
    for cat, cat_info in _data["categories"].items()
    for ct in cat_info["content_types"]
    if ct.get("embedding_enrichment")
}


# ── Rollenbasierte Typ-Gewichtung (ADR-017, AP6) ─────────────────────────────
#
# Dieselbe Anfrage meint je nach Rolle etwas anderes. Wer als Schüler:in nach
# „Bruchrechnung" sucht, will lernen; wer als Lehrkraft danach sucht, will unterrichten
# oder prüfen. Beide sollen dieselben Bausteine finden — nur in anderer Reihenfolge.
#
# **Additiv und klein**, in Kosinus-Distanz wie der Fachbonus (0,05). Sie sortieren
# innerhalb dessen, was ohnehin zur Auswahl stand; zwischen Platz 1 und Platz 10 einer
# Zehnerliste liegen im Median 0,063.
#
# ⚠️ **Bildungsplan-Typen bleiben bei 0.** Sie sind für beide Rollen gleich richtig, und
# nur so bleibt der Prüfsatz auf reinem BP-Bestand unverändert — das ist zugleich das
# Abnahmekriterium dieser Tabelle.
#
# ⚠️ **Kein Filter.** Eine Klausur verschwindet für Schüler:innen nicht durch diese
# Tabelle — dafür sorgt der Sichtbarkeits-Scope (`visibility.py`). Wer beides verwechselt,
# baut einen Rechteschutz an die falsche Stelle.
#
# Assistentenbasierte Gewichtung wird ausdrücklich **nicht** gebaut (ADR-017,
# Entscheidung 3): Sie verlagert eine Suchentscheidung in die Assistentenpflege, wo sie
# niemand nachvollziehen kann.
#
# Die Werte sind bewusst noch nicht am Prüfsatz gemessen — messbar werden sie erst mit
# einem heterogenen Bestand nutzererzeugter Inhalte. Bis dahin gilt: so klein, dass sie
# im Zweifel nichts kaputtmachen.
_SCHUELER_BONUS: Final[dict[str, float]] = {
    # Material, das zum Lernen gedacht ist.
    "methodenblatt": 0.03,
    "operatorenblatt": 0.03,
    "lerntext": 0.03,
    "arbeitsblatt": 0.02,
    "aufgabe": 0.02,
    "begriff": 0.02,
}

_LEHRKRAFT_BONUS: Final[dict[str, float]] = {
    # Material, mit dem unterrichtet und geprüft wird.
    "unterrichtsstunde": 0.03,
    "unterrichtseinheit": 0.03,
    "klausur": 0.03,
    "pruefungsanforderung": 0.03,
    "methode": 0.02,
}

ROLLEN_TYP_BONUS: Final[dict[str, dict[str, float]]] = {
    "student": _SCHUELER_BONUS,
    "teacher": _LEHRKRAFT_BONUS,
}


def rollen_typ_bonus(rollen) -> dict[str, float]:
    """Die Gewichtungstabelle für diese Rollenliste.

    ``admin`` ist eine **Erweiterung** der Lehrkraft-Rolle, kein eigener Nutzertyp
    (CLAUDE.md) — er bekommt dieselbe Tabelle. Wer beides ist, zählt als Lehrkraft: Die
    Rolle bestimmt, wonach gesucht wird, und Lehrkräfte suchen Unterrichtsmaterial.
    """
    rollen = set(rollen or ())
    if rollen & {"teacher", "admin"}:
        return ROLLEN_TYP_BONUS["teacher"]
    if "student" in rollen:
        return ROLLEN_TYP_BONUS["student"]
    return {}
