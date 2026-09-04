#!/usr/bin/env python3
"""Grundvokabular für Methoden und Sozialformen in den Wissensgraph einspielen (Upsert).

Schulweit (`read_scope`/`write_scope` = `school`), fachübergreifend (`subject_id` bleibt
leer). Fachspezifische Methoden legen Fachschaften selbst an — die Taxonomie führt für
`methode` deshalb `write_scope: subject` als Vorgabewert; die hier geseedeten Einträge
gehören keiner Fachschaft und sind die Ausnahme davon (ADR-019, Zielbild K3).

    python scripts/seed_methodik.py
    python scripts/seed_methodik.py --dry-run
    python scripts/seed_methodik.py --ueberschreiben

**Der Seed füllt Lücken, er überschreibt nichts.** Nach dem ersten Lauf gehören die
Knoten der Schule: `write_scope = school` heißt, jede Lehrkraft darf sie über die
Sammlung bearbeiten. Ein zweiter Lauf, der Text und Aliase zurücksetzt, nähme diese
Arbeit weg — lautlos, denn niemand führt Buch darüber. Wer das ausdrücklich will, nimmt
`--ueberschreiben`.

Anders die **Scopes**: Sie sind kein Redaktionsergebnis, sondern das Zielbild aus
ADR-019, und werden bei jedem Lauf nachgezogen.

⚠️ **Einträge ohne Kurzbeschreibung werden als unvollständig markiert**
(`metadata.unvollstaendig`, dieselbe Markierung wie beim Verknüpfen-Dialog, UI-Notiz A8).
Der Grund ist nicht Ordnungsliebe: Bei `methode` bildet sich der Vektor aus Titel,
Aliasen und Text (`embedding_input` in `taxonomy.yaml`). Fehlt der Text, besteht er aus
dem Namen — eine unscharfe Titelsuche im Vektorraum, die die thematische Suche nur
verwässert. `traegt_substanz()` weist genau solche Knoten ab, und die Markierung sorgt
dafür, dass ein bereits gebildeter Vektor auch wieder verschwindet. Sobald die
Beschreibung nachgetragen ist, fällt die Markierung weg.

Geänderte Knoten verlieren ihr Embedding (`embedding = NULL`) und bekommen beim nächsten
Backfill ein neues — der Seed selbst braucht dafür keinen laufenden LiteLLM-Proxy:

    python scripts/embedding_backfill.py --content-type methode
"""
import argparse
import asyncio
import logging
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.context.metadata import STUB_MARKIERUNG
from app.context.taxonomy import (
    CONTENT_TYPE_TO_CATEGORY,
    EMBEDDING_CONTENT_TYPES,
    content_ist_pflicht,
)
from app.db.models import ContextNode

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Das Zielbild aus ADR-019 K3 — kein Redaktionsergebnis, sondern eine Systementscheidung.
ZIEL_SCOPES: dict[str, Any] = {
    "read_scope": "school",
    "write_scope": "school",
    "read_scope_group_id": None,
    "write_scope_group_id": None,
}


@dataclass(frozen=True)
class Baustein:
    """Ein Vokabeleintrag: kanonischer Titel, andere Bezeichnungen, Kurzbeschreibung.

    Die Aliase tragen den Vektor mit (`embedding_input: [title, metadata.aliase,
    content]`) und sind zugleich der lexikalische Weg: Wer „Ich-Du-Wir" sucht, soll
    „Think-Pair-Share" finden.
    """

    titel: str
    aliase: tuple[str, ...] = ()
    content: str = ""

    @property
    def text(self) -> str:
        return textwrap.dedent(self.content).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Das Grundvokabular.
#
# ⚠️ Die Kurzbeschreibungen stehen noch aus (AP6, Zulieferung 1). Bis dahin legt der
# Seed die Einträge als unvollständig markiert an: Sie sind über Namen und Aliase
# auffindbar und stehen in den Auswahllisten des Stundenentwurfs, bekommen aber keinen
# Vektor — siehe Modulkopf. Der Lauf meldet, wie viele Texte noch fehlen.
#
# Ein Text ersetzt keine Handreichung: zwei bis vier Sätze, die den Ablauf so
# beschreiben, dass jemand die Methode wiedererkennt, der ihren Namen nicht kennt.
# ─────────────────────────────────────────────────────────────────────────────

SOZIALFORMEN: list[Baustein] = [
    Baustein(
        "Plenum",
        ("Frontalunterricht", "Unterrichtsgespräch", "Lehrgespräch"),
        content="",
    ),
    Baustein("Einzelarbeit", ("Stillarbeit",), content=""),
    Baustein("Partnerarbeit", (), content=""),
    Baustein("Gruppenarbeit", ("Teamarbeit",), content=""),
]

METHODEN: list[Baustein] = [
    Baustein("Think-Pair-Share", ("Ich-Du-Wir", "Prinzip der wachsenden Gruppe"), content=""),
    Baustein("Placemat", (), content=""),
    Baustein("Gruppenpuzzle", ("Jigsaw", "Expertenpuzzle"), content=""),
    Baustein("Stationenlernen", ("Stationenarbeit",), content=""),
    Baustein("Lernzirkel", (), content=""),
    Baustein("Kugellager", ("Innen-Außen-Kreis",), content=""),
    Baustein("Galeriegang", ("Gallery Walk", "Museumsrundgang"), content=""),
    Baustein("Brainstorming", (), content=""),
    Baustein("Mindmap", (), content=""),
    Baustein("Fishbowl", ("Innenkreis-Außenkreis-Diskussion",), content=""),
    Baustein("Fragend-entwickelndes Gespräch", (), content=""),
    Baustein("Lerntempoduett", (), content=""),
    Baustein("Lerntheke", (), content=""),
    Baustein("Debatte", ("Pro-Contra-Debatte", "Streitgespräch"), content=""),
    Baustein("Rollenspiel", (), content=""),
]

BESTAND: list[tuple[str, list[Baustein]]] = [
    ("sozialform", SOZIALFORMEN),
    ("methode", METHODEN),
]


@dataclass
class Aenderung:
    """Was ein Lauf an einem Knoten täte — ohne Datenbank entschieden und deshalb prüfbar."""

    felder: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    geaendert: list[str] = field(default_factory=list)
    behalten: list[str] = field(default_factory=list)
    embedding_verwerfen: bool = False

    @property
    def wirkt(self) -> bool:
        return bool(self.geaendert) or self.embedding_verwerfen


def plane_aenderung(
    ist: dict[str, Any],
    baustein: Baustein,
    content_type: str,
    *,
    ueberschreiben: bool = False,
) -> Aenderung:
    """Vergleicht Ist und Soll und beschreibt den Unterschied.

    ``ist`` ist der Zustand des vorhandenen Knotens (leer für einen neuen): ``content``,
    ``aliase``, die vier Scope-Felder und ``embedding_vorhanden``.

    Eine Regel für Anlegen und Aktualisieren — ein neuer Knoten ist hier nur der Fall,
    in dem alles fehlt. Zwei getrennte Wege wären zwei Gelegenheiten, auseinanderzulaufen.
    """
    aenderung = Aenderung(metadata=dict(ist.get("metadata") or {}))

    # ── Text ──────────────────────────────────────────────────────────────────
    ist_text = (ist.get("content") or "").strip()
    soll_text = baustein.text
    if soll_text and soll_text != ist_text:
        if ist_text and not ueberschreiben:
            aenderung.behalten.append("Text")
        else:
            aenderung.felder["content"] = soll_text
            aenderung.geaendert.append("Text")
            aenderung.embedding_verwerfen = True

    # ── Aliase ────────────────────────────────────────────────────────────────
    ist_aliase = list(ist.get("aliase") or [])
    soll_aliase = list(baustein.aliase)
    if soll_aliase != ist_aliase:
        if ist_aliase and not ueberschreiben:
            aenderung.behalten.append("Aliase")
        else:
            aenderung.metadata["aliase"] = soll_aliase
            aenderung.geaendert.append("Aliase")
            aenderung.embedding_verwerfen = True

    # ── Unvollständig-Markierung ──────────────────────────────────────────────
    # Maßgeblich ist der Text *nach* dieser Änderung, nicht der gelieferte: Ein Eintrag,
    # dessen Beschreibung die Schule geschrieben hat, ist vollständig, auch wenn der Seed
    # keinen Text mitbringt.
    text_danach = aenderung.felder.get("content", ist_text)
    war_stub = bool(aenderung.metadata.get(STUB_MARKIERUNG))
    ist_stub_jetzt = content_ist_pflicht(content_type) and not text_danach
    if ist_stub_jetzt and not war_stub:
        aenderung.metadata[STUB_MARKIERUNG] = True
        aenderung.geaendert.append("als unvollständig markiert")
        aenderung.embedding_verwerfen = True
    elif war_stub and not ist_stub_jetzt:
        aenderung.metadata.pop(STUB_MARKIERUNG, None)
        aenderung.geaendert.append("Markierung „unvollständig“ entfernt")

    # ── Scopes ────────────────────────────────────────────────────────────────
    for name, soll in ZIEL_SCOPES.items():
        if name in ist and ist[name] == soll:
            continue
        aenderung.felder[name] = soll
        if name in ist:
            aenderung.geaendert.append(name)

    if aenderung.metadata != (ist.get("metadata") or {}):
        aenderung.felder["metadata_"] = aenderung.metadata

    # Ein Vektor, den es gar nicht gibt, ist nichts zu verwerfen — und ein Typ ohne
    # Embedding (`sozialform`) hat nie einen.
    aenderung.embedding_verwerfen = (
        aenderung.embedding_verwerfen
        and content_type in EMBEDDING_CONTENT_TYPES
        and bool(ist.get("embedding_vorhanden"))
    )
    return aenderung


def _ist_zustand(node: ContextNode) -> dict[str, Any]:
    metadata = dict(node.metadata_ or {})
    return {
        "content": node.content,
        "aliase": list(metadata.get("aliase") or []),
        "metadata": metadata,
        "read_scope": node.read_scope,
        "write_scope": node.write_scope,
        "read_scope_group_id": node.read_scope_group_id,
        "write_scope_group_id": node.write_scope_group_id,
        "embedding_vorhanden": node.embedding is not None,
    }


@dataclass
class Bilanz:
    neu: int = 0
    aktualisiert: int = 0
    unveraendert: int = 0
    neu_einzubetten: int = 0
    behalten: list[str] = field(default_factory=list)
    ohne_text: list[str] = field(default_factory=list)


async def _upsert(
    db: AsyncSession,
    content_type: str,
    baustein: Baustein,
    bilanz: Bilanz,
    *,
    ueberschreiben: bool,
) -> None:
    vorhanden = (
        await db.execute(
            select(ContextNode).where(
                ContextNode.content_type == content_type,
                ContextNode.title == baustein.titel,
            )
        )
    ).scalar_one_or_none()

    ist = _ist_zustand(vorhanden) if vorhanden else {}
    aenderung = plane_aenderung(ist, baustein, content_type, ueberschreiben=ueberschreiben)

    if aenderung.behalten:
        bilanz.behalten.append(
            f"{baustein.titel}: {', '.join(aenderung.behalten)} aus der Schule behalten"
        )
    if content_ist_pflicht(content_type) and not aenderung.felder.get(
        "content", (ist.get("content") or "").strip()
    ):
        bilanz.ohne_text.append(baustein.titel)

    if vorhanden is None:
        felder = {k: v for k, v in aenderung.felder.items() if k != "metadata_"}
        db.add(
            ContextNode(
                category=CONTENT_TYPE_TO_CATEGORY[content_type],
                content_type=content_type,
                title=baustein.titel,
                status="active",
                metadata_=aenderung.metadata,
                **felder,
            )
        )
        bilanz.neu += 1
        return

    if not aenderung.wirkt:
        bilanz.unveraendert += 1
        return

    for name, wert in aenderung.felder.items():
        setattr(vorhanden, name, wert)
    if aenderung.embedding_verwerfen:
        vorhanden.embedding = None
        bilanz.neu_einzubetten += 1
    bilanz.aktualisiert += 1
    logger.info("  %-12s %-35s %s", content_type, baustein.titel, ", ".join(aenderung.geaendert))


async def seed(*, dry_run: bool = False, ueberschreiben: bool = False) -> Bilanz:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    bilanz = Bilanz()
    async with session_factory() as db:
        for content_type, eintraege in BESTAND:
            for baustein in eintraege:
                await _upsert(
                    db, content_type, baustein, bilanz, ueberschreiben=ueberschreiben
                )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    await engine.dispose()
    return bilanz


def _berichte(bilanz: Bilanz, *, dry_run: bool) -> None:
    logger.info(
        "Methodik-Seed%s: %d neu, %d aktualisiert, %d unverändert.",
        " (Probelauf, nichts geschrieben)" if dry_run else "",
        bilanz.neu,
        bilanz.aktualisiert,
        bilanz.unveraendert,
    )
    for zeile in bilanz.behalten:
        logger.info("Nicht überschrieben — %s (mit --ueberschreiben erzwingen).", zeile)
    if bilanz.ohne_text:
        logger.warning(
            "%d Einträge ohne Kurzbeschreibung, als unvollständig markiert und ohne "
            "Vektor: %s",
            len(bilanz.ohne_text),
            ", ".join(bilanz.ohne_text),
        )
    if bilanz.neu_einzubetten:
        logger.info(
            "%d Vektoren verworfen — ihre Eingabe hat sich geändert.",
            bilanz.neu_einzubetten,
        )
    if bilanz.neu_einzubetten or bilanz.neu:
        logger.info(
            "Nächster Schritt: python scripts/embedding_backfill.py --content-type methode"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grundvokabular Methoden/Sozialformen einspielen"
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen, nichts schreiben")
    parser.add_argument(
        "--ueberschreiben",
        action="store_true",
        help="Auch Text und Aliase ersetzen, die in der Schule geändert wurden",
    )
    args = parser.parse_args()

    bilanz = asyncio.run(seed(dry_run=args.dry_run, ueberschreiben=args.ueberschreiben))
    _berichte(bilanz, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
