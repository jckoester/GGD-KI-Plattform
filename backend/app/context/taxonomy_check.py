"""Startprüfung der Knotentyp-Taxonomie (ADR-018).

**Wogegen das schützt.** `app/context/taxonomy.yaml` ist eine Systemdatei: Am
content_type hängen der Datenbestand, die Embedding-Strategie, die Suchgewichtung,
Werkzeug-Presets und die Oberfläche. Wird die Datei verändert, ohne dass die daran
hängenden Stellen mitgezogen werden, fällt das **nicht** auf — es gibt keine
Fehlermeldung, nur andere Ergebnisse:

- Ein entfernter Typ hinterlässt Knoten, die keine Ansicht mehr einordnen kann und
  die kein Filter mehr findet.
- Ein fehlender Eintrag in `VALID_UNTIL_DEFAULTS_DAYS` heißt „läuft nie ab"
  (`.get()` liefert `None`), nicht „Fehler".
- Ein `embedding_enrichment` an einem Typ ohne `embedding: true` ist wirkungslos.
- Zwei Listen derselben Sache driften auseinander — genau so geschehen bei den
  `retrieval_scope`-Ankern: Die YAML führte `kapitel`, die durchsetzende Liste in
  `retrieval.py` führte stattdessen `unterrichtseinheit`, und der Assistenten-Editor
  hatte eine dritte Kopie. Sichtbar war davon nur ein falsches Badge.

Die Prüfung macht daraus einen **Startfehler**. Das ist die Absicht von ADR-018: kein
stilles Weiterlaufen mit einer lokal veränderten Datei. Praktisch heißt das auch — und
das ist gewollt (Leitplanke 2 des Umsetzungsplans) —, dass ein vergessenes
``alembic upgrade head`` nach einer Typ-Streichung den Start verhindert, statt die
Knoten in einen Zustand ohne Zuständigkeit fallen zu lassen.

**Nicht** als Fehler gewertet wird eine unlesbare Datenbank (frische Installation vor
der ersten Migration): Das ist keine Abweichung, sondern eine noch nicht beantwortbare
Frage — sie wird protokolliert und übersprungen.

Die Funktionen sind bewusst getrennt in reine Prüfung (ohne Datenbank, ohne IO) und
Ladeteil, damit sie ohne laufendes System testbar sind und `check_production.py` den
lokalen Teil mitnehmen kann.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context import taxonomy

logger = logging.getLogger(__name__)


class TaxonomieFehler(RuntimeError):
    """Die Taxonomie passt nicht zu den Handtabellen oder zum Datenbestand."""


# Reihenfolge von eng nach weit — `write_scope` darf nie weiter reichen als `read_scope`.
_SCOPE_RANG = {"private": 0, "group": 1, "subject": 2, "school": 3, "global": 4}


def pruefe_altlast() -> str | None:
    """Meldet eine zurückgebliebene `config/taxonomy.yaml`.

    Bis 02.09.2026 lag die Taxonomie in `config/` und wurde von dort gemountet. Nach dem
    Update liegt in einer Bestandsinstallation die alte Datei weiterhin auf dem Host —
    sichtbar, bearbeitbar und **wirkungslos**. Genau die Fehlerklasse, gegen die dieses
    Modul gebaut ist: Man ändert etwas, nichts passiert, und niemand sagt warum.

    Keine Abweichung, deshalb kein Startfehler — nur ein Hinweis.
    """
    from app.core.paths import aufloesen

    altlast = aufloesen("config/taxonomy.yaml")
    if not altlast.is_file():
        return None
    return (
        f"{altlast} ist eine Altlast und wird **nicht** gelesen. Die Taxonomie ist seit "
        "09/2026 eine Systemdatei und liegt im Anwendungsabbild "
        "(app/context/taxonomy.yaml, ADR-018). Die Datei kann gelöscht werden; "
        "Änderungen daran wirken nicht."
    )


def pruefe_taxonomie() -> list[str]:
    """Die datenbankfreien Prüfungen. Gibt Befunde zurück; leere Liste = in Ordnung.

    Geprüft wird ausschließlich, was **auseinanderlaufen kann**. Alles, was
    `taxonomy.py` aus der YAML ableitet, ist per Konstruktion konsistent und steht
    hier nicht.
    """
    befunde: list[str] = []
    typen = set(taxonomy.SCOPE_DEFAULTS)

    # ── Kategorien-Zuordnung ──────────────────────────────────────────────────
    # Ein zweimal vergebener Schlüssel fällt sonst nirgends auf:
    # `CONTENT_TYPE_TO_CATEGORY` ist ein Dict — der zweite Eintrag überschreibt den
    # ersten still, und `validate_content_type` erlaubt den Typ danach in *beiden*
    # Kategorien, während die Rückwärtssuche nur eine kennt.
    gesehen: dict[str, str] = {}
    for kategorie, keys in taxonomy.VALID_CONTENT_TYPES.items():
        for key in keys:
            if key in gesehen:
                befunde.append(
                    f"content_type {key!r} ist doppelt vergeben "
                    f"(category {gesehen[key]!r} und {kategorie!r}) — "
                    "Quelle: app/context/taxonomy.yaml"
                )
            gesehen[key] = kategorie

    # ── Scope-Defaults ────────────────────────────────────────────────────────
    for key, (read, write) in sorted(taxonomy.SCOPE_DEFAULTS.items()):
        unbekannt = [s for s in (read, write) if s not in _SCOPE_RANG]
        if unbekannt:
            befunde.append(
                f"content_type {key!r} hat unbekannte Scope-Werte {unbekannt} — "
                f"erlaubt: {sorted(_SCOPE_RANG)}. Quelle: app/context/taxonomy.yaml"
            )
            continue
        if _SCOPE_RANG[write] > _SCOPE_RANG[read]:
            befunde.append(
                f"content_type {key!r}: write_scope {write!r} reicht weiter als "
                f"read_scope {read!r} — wer schreiben darf, könnte nicht lesen. "
                "Quelle: app/context/taxonomy.yaml"
            )

    # ── ui_status ─────────────────────────────────────────────────────────────
    for key, status in sorted(taxonomy.UI_STATUS.items()):
        if status not in taxonomy.GUELTIGE_UI_STATUS:
            befunde.append(
                f"content_type {key!r} hat ui_status {status!r} — erlaubt: "
                f"{sorted(taxonomy.GUELTIGE_UI_STATUS)}. "
                "Quelle: app/context/taxonomy.yaml"
            )

    # ── Lifecycle-Handtabelle ─────────────────────────────────────────────────
    # Zwei Mechanismen, die sich ausschließen: ein Tages-Offset **oder** das
    # Schuljahresende. Stünde beides an einem Typ, entschiede die Aufrufreihenfolge —
    # und die steht nirgends geschrieben.
    doppelt = sorted(
        key for key in taxonomy.SCHULJAHRESENDE_CONTENT_TYPES
        if taxonomy.VALID_UNTIL_DEFAULTS_DAYS.get(key) is not None
    )
    if doppelt:
        befunde.append(
            f"Diese Typen tragen zugleich einen Tages-Offset und "
            f"`valid_until_default: schuljahresende`: {doppelt}. Es gilt eins von "
            "beidem — bei Schuljahresende gehört in VALID_UNTIL_DEFAULTS_DAYS ein None."
        )

    fehlend = sorted(typen - set(taxonomy.VALID_UNTIL_DEFAULTS_DAYS))
    if fehlend:
        befunde.append(
            f"Ohne Lifecycle-Eintrag: {fehlend} — ein fehlender Eintrag heißt "
            "stillschweigend „läuft nie ab\". Quelle: VALID_UNTIL_DEFAULTS_DAYS in "
            "app/context/taxonomy.py"
        )
    verwaist = sorted(set(taxonomy.VALID_UNTIL_DEFAULTS_DAYS) - typen)
    if verwaist:
        befunde.append(
            f"Lifecycle-Eintrag für nicht (mehr) existierende Typen: {verwaist}. "
            "Quelle: VALID_UNTIL_DEFAULTS_DAYS in app/context/taxonomy.py"
        )

    # ── Rollenbasierte Typ-Gewichtung ─────────────────────────────────────────
    for rolle, tabelle in sorted(taxonomy.ROLLEN_TYP_BONUS.items()):
        unbekannte = sorted(set(tabelle) - typen)
        if unbekannte:
            befunde.append(
                f"Rollen-Gewichtung {rolle!r} nennt unbekannte Typen: {unbekannte} — "
                "der Bonus greift ins Leere. Quelle: ROLLEN_TYP_BONUS in "
                "app/context/taxonomy.py"
            )

    # ── Embedding-Zusätze ─────────────────────────────────────────────────────
    # Beide Tabellen sind aus der YAML abgeleitet, ihr Schlüssel kann also nicht
    # unbekannt sein. Wirkungslos werden sie trotzdem, wenn der Typ kein Embedding
    # bekommt — dann formuliert jemand einen Vektor-Input für einen Knoten, der nie
    # eingebettet wird.
    for name, tabelle in (
        ("embedding_enrichment", taxonomy.EMBEDDING_ENRICHMENT),
        ("embedding_input", taxonomy.EMBEDDING_INPUT),
    ):
        ohne_embedding = sorted(
            key for (_cat, key) in tabelle if key not in taxonomy.EMBEDDING_CONTENT_TYPES
        )
        if ohne_embedding:
            befunde.append(
                f"{name} ist gesetzt für Typen ohne `embedding: true`: "
                f"{ohne_embedding} — der Eintrag bleibt wirkungslos. "
                "Quelle: app/context/taxonomy.yaml"
            )

    # ── Sammlungs-Konfiguration und Feldschema (AP5a) ─────────────────────────
    from app.context.metadata import pruefe_schema_konsistenz

    befunde += pruefe_schema_konsistenz()

    # Eine Sammlung an einem ruhenden Typ wäre eine Ansicht, in der man nichts anlegen
    # kann — der Typ steht ja in keiner Auswahl.
    ruhende_sammlungen = sorted(set(taxonomy.COLLECTIONS) & taxonomy.RUHENDE_CONTENT_TYPES)
    if ruhende_sammlungen:
        befunde.append(
            f"Diese Typen haben eine Sammlung, ruhen aber: {ruhende_sammlungen}. "
            "Entweder `ui_status: aktiv` setzen oder die Sammlung entfernen. "
            "Quelle: app/context/taxonomy.yaml"
        )

    # ── Weitere Typ-Listen ────────────────────────────────────────────────────
    unbekannt_bp = sorted(set(taxonomy.BP_CURRICULUM_CONTENT_TYPES) - typen)
    if unbekannt_bp:
        befunde.append(
            f"bp_curriculum_content_types nennt unbekannte Typen: {unbekannt_bp} — "
            "sie werden aus der /knowledge-Liste ausgeschlossen, ohne zu existieren. "
            "Quelle: app/context/taxonomy.yaml"
        )

    # Die durchsetzende Ankerliste (`retrieval.py`) und die YAML sind seit 02.09.2026
    # dasselbe Objekt. Die Prüfung hält das fest: Wer die Liste dort wieder als Literal
    # hinschreibt, bekommt es beim Start gesagt und nicht erst durch ein falsches Badge.
    from app.context.retrieval import VALID_SCOPE_ANCHOR_TYPES as durchgesetzt

    if durchgesetzt != taxonomy.VALID_SCOPE_ANCHOR_TYPES:
        nur_dort = sorted(durchgesetzt - taxonomy.VALID_SCOPE_ANCHOR_TYPES)
        nur_yaml = sorted(taxonomy.VALID_SCOPE_ANCHOR_TYPES - durchgesetzt)
        befunde.append(
            "Die zulässigen retrieval_scope-Anker weichen voneinander ab: "
            f"nur in retrieval.py {nur_dort}, nur in taxonomy.yaml {nur_yaml}. "
            "Es darf nur eine Quelle geben (`scope_anchor: true` in der YAML)."
        )

    return befunde


def pruefe_bestand(kombinationen) -> list[str]:
    """Prüft die vorgefundenen (category, content_type, Anzahl)-Tripel gegen die Taxonomie.

    ``content_type`` darf ``None`` sein — strukturelle Knoten ohne fachliche Rolle sind
    laut `validate_content_type` zulässig und werden übersprungen.
    """
    befunde: list[str] = []
    typen = set(taxonomy.SCOPE_DEFAULTS)

    for kategorie, content_type, anzahl in kombinationen:
        if content_type is None:
            continue
        if content_type not in typen:
            befunde.append(
                f"{anzahl} Knoten tragen den content_type {content_type!r}, den die "
                "Taxonomie nicht (mehr) kennt. Entweder fehlt die Datenmigration "
                "(`alembic upgrade head`) oder die Taxonomie wurde lokal verändert. "
                "Quelle: Tabelle context_nodes"
            )
        elif content_type not in taxonomy.VALID_CONTENT_TYPES.get(kategorie, ()):
            befunde.append(
                f"{anzahl} Knoten stehen als category {kategorie!r} / content_type "
                f"{content_type!r} in der Datenbank; die Taxonomie führt den Typ unter "
                f"{taxonomy.CONTENT_TYPE_TO_CATEGORY.get(content_type)!r}. "
                "Quelle: Tabelle context_nodes"
            )

    return befunde


async def lade_bestandskombinationen(db: AsyncSession) -> list[tuple[str, str | None, int]]:
    """Die vorkommenden (category, content_type)-Paare mit Anzahl."""
    ergebnis = await db.execute(
        sa.text(
            "SELECT category, content_type, count(*) FROM context_nodes "
            "GROUP BY 1, 2 ORDER BY 1, 2"
        )
    )
    return [(zeile[0], zeile[1], zeile[2]) for zeile in ergebnis.all()]


async def pruefe_beim_start(session_factory) -> None:
    """Startprüfung. Wirft ``TaxonomieFehler``, wenn die Taxonomie nicht passt."""
    altlast = pruefe_altlast()
    if altlast:
        logger.warning("%s", altlast)

    befunde = pruefe_taxonomie()

    try:
        async with session_factory() as db:
            kombinationen = await lade_bestandskombinationen(db)
    except Exception as exc:  # noqa: BLE001 — jede Ursache führt hier zum selben Schluss
        logger.warning(
            "Knotentypen im Bestand nicht prüfbar (%s) — Tabelle context_nodes noch "
            "nicht da? Die Prüfung gegen den Datenbestand entfällt; die Taxonomie "
            "selbst wurde geprüft.", exc,
        )
    else:
        befunde += pruefe_bestand(kombinationen)

    if befunde:
        raise TaxonomieFehler(
            "Die Knotentyp-Taxonomie passt nicht zum System (ADR-018). "
            "app/context/taxonomy.yaml ist eine Systemdatei und wird nur im "
            "Entwicklungsprozess geändert — siehe docs/dev/neuer-knotentyp.md.\n  · "
            + "\n  · ".join(befunde)
        )

    logger.info(
        "Knotentyp-Taxonomie konsistent: %d Typen in %d Kategorien.",
        len(taxonomy.SCOPE_DEFAULTS), len(taxonomy.VALID_CONTENT_TYPES),
    )
