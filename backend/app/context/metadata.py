"""Prüfung von `metadata` und `content` beim Anlegen und Ändern von Knoten.

**Woher die Regeln kommen.** Seit AP5a steht das Feldschema als `felder:` am Typ in der
Taxonomie — an **einer** Stelle für Editor und Backend. Der Editor baut sein Formular
daraus, diese Datei prüft dieselbe Beschreibung. Bis AP2 gab es die Regeln zweimal
(einmal als Formularfeld, einmal als handgeschriebene Prüfung); die Drift, die daraus
entsteht, hat AP1 bei den Ankertypen vorgefunden — drei Listen, zwei Meinungen, sichtbar
nur an einem falschen Badge.

Das Schema steht **neben** `collection:`, nicht darin: Ein Typ kann Felder haben, ohne
eine Sammlungsansicht zu haben. Der erste Entwurf hängte es unter `collection:` — damit
verlor `strukturierung` (ruhend bis 0.9, aber mit der Regel `form: gliederung | mindmap`)
seine Prüfung, und zwei Tests fielen um. Genau dafür sind sie da.

**Was hier bewusst nicht geprüft wird.** `metadata` bleibt ein freies JSON-Feld: Der
Kontextspeicher soll neue Felder aufnehmen können, ohne dass jedes eine Migration
braucht. Geprüft wird nur, was im Schema steht — also was eine Bedeutung für die
Anwendung trägt und falsch nicht auffiele. Unbekannte Schlüssel gehen durch.

⚠️ **`validate_unterrichtsstunde_metadata` bleibt daneben.** Sein Phasen-Schema ist
verschachtelt (Liste von Objekten mit eigenen Pflichtfeldern und Enums) und passt in
keine Feldliste. Es abzulösen wäre ein eigener Schritt, kein Nebenbei.
"""
from __future__ import annotations

from app.context.taxonomy import (
    GUELTIGE_FELDTYPEN,
    content_ist_pflicht,
    feld_schema,
)

# Die Relationen, die der CHECK-Constraint `check_context_edges_relation` zulässt.
# Eine Sammlung darf nur daraus anbieten — sonst schlüge das Anlegen der Kante fehl.
ERLAUBTE_RELATIONEN = frozenset({
    "requires", "used_with", "part_of", "develops", "supersedes",
    "references", "follows", "reflects_on", "derived_from", "related_to",
})


def _pruefe_feld(name: str, feld: dict, wert) -> None:
    """Ein einzelner Wert gegen seine Feldbeschreibung. Wirft ``ValueError``."""
    label = feld.get("label", name)
    typ = feld.get("typ")

    if typ == "int":
        # `bool` ist in Python ein `int` — `True` ginge sonst als 1 durch.
        if isinstance(wert, bool) or not isinstance(wert, int):
            raise ValueError(f"„{label}“ muss eine ganze Zahl sein (war: {wert!r})")
        unten, oben = feld.get("min"), feld.get("max")
        if unten is not None and wert < unten:
            raise ValueError(f"„{label}“ muss mindestens {unten} sein (war: {wert})")
        if oben is not None and wert > oben:
            raise ValueError(f"„{label}“ darf höchstens {oben} sein (war: {wert})")

    elif typ == "text":
        if not isinstance(wert, str):
            raise ValueError(f"„{label}“ muss Text sein (war: {type(wert).__name__})")

    elif typ == "auswahl":
        werte = feld.get("werte") or []
        if wert not in werte:
            raise ValueError(
                f"„{label}“ muss einer dieser Werte sein: {', '.join(map(str, werte))} "
                f"(war: {wert!r})"
            )

    elif typ == "liste":
        if not isinstance(wert, list) or not all(isinstance(e, str) for e in wert):
            raise ValueError(f"„{label}“ muss eine Liste von Texten sein")


def validate_node_metadata(content_type: str | None, metadata: dict | None) -> None:
    """Prüft die im Schema beschriebenen Felder. Fehlende Felder sind erlaubt.

    Pflichtfelder erzwingt :func:`validate_node_content` bzw. der Editor — hier geht es
    nur darum, dass ein **vorhandener** Wert brauchbar ist. Ein leeres Feld ist ein
    unvollständiger Eintrag, kein kaputter.
    """
    schema = feld_schema(content_type)
    if not schema or not metadata:
        return

    for name, feld in schema.items():
        if name not in metadata:
            continue
        wert = metadata[name]
        if wert is None or wert == "":
            continue   # ausdrücklich leer gelassen
        _pruefe_feld(name, feld, wert)


# Ein Knoten, der aus dem Verknüpfen-Dialog entstanden ist: Titel und Fach stehen, der
# Inhalt fehlt noch (UI-Notiz A8, Wiki-Muster).
STUB_MARKIERUNG = "unvollstaendig"


def ist_stub(metadata: dict | None) -> bool:
    return bool((metadata or {}).get(STUB_MARKIERUNG))


def validate_node_content(
    content_type: str | None, content: str | None, metadata: dict | None = None
) -> None:
    """Erzwingt den Knotentext, wo die Sammlung ihn als Pflicht führt.

    Der Grund steht in der Taxonomie: Ein Eintrag ohne Text ist nur unter seinem Namen
    auffindbar. Bei `methode` und `begriff` — beide mit Embedding — bestünde der
    Vektor faktisch aus dem Titel, und genau solche Knoten weist `traegt_substanz()`
    ab. Der Eintrag wäre also thematisch unsichtbar, ohne dass es jemandem auffiele.

    ⚠️ **Ausnahme: ausdrücklich als unvollständig markierte Knoten.** Der
    Verknüpfen-Dialog legt fehlende Begriffe im Hintergrund an, damit eine Fachschaft
    erst das Netz aufspannen und dann definieren kann (A8). Diese Stubs tragen
    `metadata.unvollstaendig` und sind damit **gezählt und filterbar** — der Unterschied
    zu einem stillschweigend leeren Eintrag ist genau der: Man sieht, dass etwas fehlt.
    """
    if ist_stub(metadata):
        return
    if content_ist_pflicht(content_type) and not (content or "").strip():
        from app.context.taxonomy import collection_config

        label = ((collection_config(content_type) or {}).get("content") or {}).get(
            "label", "Inhalt"
        )
        raise ValueError(f"„{label}“ ist bei diesem Bausteintyp ein Pflichtfeld.")


def pruefe_schema_konsistenz() -> list[str]:
    """Prüft die Sammlungs-Konfigurationen selbst — für die Startprüfung (ADR-018).

    Eine Sammlung, deren Spalte auf ein nicht existierendes Feld zeigt, zeigte eine
    leere Spalte; ein unbekannter Feldtyp würde vom Editor nicht dargestellt und vom
    Backend nicht geprüft. Beides fiele erst am fertigen Bestand auf.
    """
    from app.context.taxonomy import (
        COLLECTIONS,
        FELD_SCHEMATA,
        FESTE_SPALTEN,
        GUELTIGE_FELDTYPEN,
    )

    befunde: list[str] = []

    # Feldschemata — auch die von Typen ohne Sammlung (z. B. ruhende).
    for typ, felder in sorted(FELD_SCHEMATA.items()):
        for name, feld in felder.items():
            if feld.get("typ") not in GUELTIGE_FELDTYPEN:
                befunde.append(
                    f"Typ {typ!r}, Feld {name!r}: unbekannter Feldtyp "
                    f"{feld.get('typ')!r} — erlaubt: {sorted(GUELTIGE_FELDTYPEN)}. "
                    "Quelle: app/context/taxonomy.yaml"
                )
            if feld.get("typ") == "auswahl" and not feld.get("werte"):
                befunde.append(
                    f"Typ {typ!r}, Feld {name!r}: Auswahlfeld ohne `werte`. "
                    "Quelle: app/context/taxonomy.yaml"
                )
            if not feld.get("label"):
                befunde.append(
                    f"Typ {typ!r}, Feld {name!r}: kein `label` — der Editor hätte "
                    "eine unbeschriftete Eingabe. Quelle: app/context/taxonomy.yaml"
                )

    # Sammlungen — Spalten und Filter müssen auf feste Spalten oder Felder zeigen.
    for typ, config in sorted(COLLECTIONS.items()):
        bekannt = FESTE_SPALTEN | set(FELD_SCHEMATA.get(typ) or {})
        for schluessel, werte in (("spalten", config.get("spalten") or []),
                                  ("filter", config.get("filter") or [])):
            unbekannt = sorted(set(werte) - bekannt - {"titel"})
            if unbekannt:
                befunde.append(
                    f"Sammlung {typ!r}: {schluessel} nennt {unbekannt}, aber weder feste "
                    f"Spalte noch Feld. Quelle: app/context/taxonomy.yaml"
                )

        for relation, beschreibung in (config.get("relationen") or {}).items():
            if relation not in ERLAUBTE_RELATIONEN:
                befunde.append(
                    f"Sammlung {typ!r}: unbekannte Relation {relation!r} — erlaubt sind "
                    f"{sorted(ERLAUBTE_RELATIONEN)} (CHECK-Constraint "
                    "`check_context_edges_relation`). Quelle: app/context/taxonomy.yaml"
                )
            if not (beschreibung or {}).get("label"):
                befunde.append(
                    f"Sammlung {typ!r}, Relation {relation!r}: kein `label` — der Dialog "
                    "zeigt die Richtung als Satz, dafür braucht er einen. "
                    "Quelle: app/context/taxonomy.yaml"
                )

        if "sidebar" in config and not isinstance(config["sidebar"], bool):
            befunde.append(
                f"Sammlung {typ!r}: `sidebar` muss true oder false sein (war: "
                f"{config['sidebar']!r}). Quelle: app/context/taxonomy.yaml"
            )

        if not (config.get("beschreibung") or "").strip():
            befunde.append(
                f"Sammlung {typ!r}: keine `beschreibung` — die Liste hätte keinen Satz, "
                "der sagt, was hineingehört. Quelle: app/context/taxonomy.yaml"
            )

    return befunde
