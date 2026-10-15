"""Gleichnamige Fachbegriffe über Fachgrenzen (0.16, Plan „Vorab-Suche-Begriffe" F7).

Jan, 13.10.2026: „Ziel soll ja sein, dass Begriffe nur dann doppelt angelegt werden, wenn sie
nicht gleich- oder ähnlichbedeutend genutzt werden. Dann brauchen sie eine klare Abgrenzung."
Gibt es in Biologie „Fotosynthese" und will NwT einen eigenen Eintrag dazu, muss das auffallen —
im Import, im Editor und für den schon vorhandenen Bestand (`scripts/fachbegriffe_kollisionen.py`).

**Erkannt wird am Namen, nicht an der Bedeutung:** normalisierter Titel des neuen Eintrags =
Titel oder Suchbegriff eines aktiven Begriffs oder Stoffsteckbriefs eines **anderen** Fachs, oder
einer seiner Suchbegriffe = fremder Titel. Deterministisch und ohne Embedding — der Import läuft
ohne LiteLLM. Geprüft wird gegen **alle** Fächer: Eine Dublette in einem Fach ohne Bezug ist
genau die, die niemand bemerkt.

⚠️ **Nur gegen Einträge, die alle lesen dürfen** (`OFFENE_SCOPES`). Ein privater Entwurf einer
Lehrkraft ist kein Bestand des Fachs und soll die Fachschaft nicht aufhalten — und die Meldung
im Editor nennte sonst den Titel eines fremden privaten Eintrags.

**Suchbegriff = Suchbegriff ist nur ein Hinweis.** Suchbegriffe sind lockere Suchwörter
(„Energie" tragen mehrere); daran zu sperren hieße, die Pflege zu bestrafen, die die Suche
verbessert.

**Fassungen im selben Fach** (zweimal „Oxidation", verbunden mit `vertieft_in`) sind das
bestehende Muster für Bedeutungen je Jahrgang und lösen nichts aus.

Eine Kollision ist **abgegrenzt**, wenn der neue Eintrag eine Abgrenzungskante auf den
vorhandenen trägt (`related_to`, `art: abgrenzung`) — dann erfährt das Modell den Unterschied
mit jedem Treffer (`search.abgrenzungen_zu`).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.aliase import ALIAS_NORMALISIERT, normalisiere
# Die Knotentypen, die als Fachbegriff zählen — dieselben, die der Import schreibt. Der Import
# lädt dieses Modul erst beim Lauf, sonst schlössen sich die beiden Importe im Kreis.
from app.context.fachbegriffe_import import TYPEN
from app.context.filters import TITEL_NORMALISIERT
from app.context.lookup import normalisiere_titel
from app.context.visibility import OFFENE_SCOPES
from app.db.models import ContextEdge, ContextNode, NodeAlias, Subject

#: Wie der Name zusammenfällt, absteigend nach Gewicht. Nur ``alias`` sperrt nicht.
ARTEN = {
    "titel": "gleicher Titel",
    "titel_alias": "der Titel ist dort ein Suchbegriff",
    "alias_titel": "ein Suchbegriff ist dort der Titel",
    "alias": "gleicher Suchbegriff",
}

#: Was eine Kante zur Abgrenzung macht — auch, wenn sie zugleich etwas anderes ist
#: (`vereinige` im Import zieht Nennungen zusammen und hält die Arten in `arten` fest).
ABGRENZUNG = "abgrenzung"


@dataclass(frozen=True)
class Kollision:
    """Ein vorhandener Eintrag eines anderen Fachs, der denselben Namen trägt."""

    node_id: UUID
    titel: str
    #: Fachname des vorhandenen Eintrags; ``None`` bei fachlosen.
    fach: str | None
    #: Seine Kennung (`seed_id`) — die Form, in der eine Datei ihn über Fachgrenzen
    #: eindeutig nennt (`[[bio-fotosynthese]]`). ``None``, wenn er keine hat.
    kennung: str | None
    art: str

    @property
    def sperrend(self) -> bool:
        return self.art != "alias"

    @property
    def beschreibung(self) -> str:
        return ARTEN[self.art]

    def als_text(self) -> str:
        """„Fotosynthese (Biologie, gleicher Titel)" — für Bericht und Meldung."""
        return f"„{self.titel}“ ({self.fach or 'fachlos'}, {self.beschreibung})"


async def kollisionen(
    db: AsyncSession,
    *,
    subject_id: int | None,
    titel: str,
    aliase: Iterable[str] = (),
    ohne: UUID | None = None,
) -> list[Kollision]:
    """Aktive Fachbegriffe **anderer** Fächer mit demselben Namen — die schwerste Art je
    Eintrag, sperrende zuerst. ``ohne`` nimmt den Eintrag selbst heraus (beim Ändern)."""
    titel_n = normalisiere_titel(titel)
    aliase_n = {normalisiere(a) for a in aliase} - {"", titel_n}
    namen = {titel_n, *aliase_n} - {""}
    if not namen:
        return []

    mit_alias = sa.select(NodeAlias.node_id).where(ALIAS_NORMALISIERT.in_(namen))
    bedingung = [
        ContextNode.status == "active",
        ContextNode.content_type.in_(TYPEN),
        ContextNode.read_scope.in_(OFFENE_SCOPES),
        ContextNode.subject_id.is_distinct_from(subject_id),
        sa.or_(TITEL_NORMALISIERT.in_(namen), ContextNode.id.in_(mit_alias)),
    ]
    if ohne is not None:
        bedingung.append(ContextNode.id != ohne)
    kandidaten = (await db.execute(
        sa.select(ContextNode.id, ContextNode.title, TITEL_NORMALISIERT, Subject.name,
                  ContextNode.metadata_["seed_id"].astext)
        .outerjoin(Subject, Subject.id == ContextNode.subject_id)
        .where(*bedingung)
    )).all()
    if not kandidaten:
        return []

    fremde_aliase: dict[UUID, set[str]] = {}
    for node_id, alias in (await db.execute(
        sa.select(NodeAlias.node_id, ALIAS_NORMALISIERT)
        .where(NodeAlias.node_id.in_([k[0] for k in kandidaten]))
    )).all():
        fremde_aliase.setdefault(node_id, set()).add(alias)

    ergebnis = []
    for node_id, fremder_titel, fremder_titel_n, fach, kennung in kandidaten:
        fremd = fremde_aliase.get(node_id, set())
        if fremder_titel_n == titel_n:
            art = "titel"
        elif titel_n in fremd:
            art = "titel_alias"
        elif fremder_titel_n in aliase_n:
            art = "alias_titel"
        elif aliase_n & fremd:
            art = "alias"
        else:  # pragma: no cover — die Abfrage liefert nur Namensgleiche
            continue
        ergebnis.append(Kollision(node_id, fremder_titel, fach, kennung or None, art))
    rang = list(ARTEN)
    return sorted(ergebnis, key=lambda k: (rang.index(k.art), k.fach or "", k.titel))


def ist_abgrenzung(metadata: dict | None) -> bool:
    """Trägt eine `related_to`-Kante die Abgrenzung — allein oder neben einer anderen Art?"""
    metadata = metadata or {}
    return metadata.get("art") == ABGRENZUNG or ABGRENZUNG in (metadata.get("arten") or [])


async def abgegrenzt(db: AsyncSession, von: UUID, ziele: Iterable[UUID]) -> set[UUID]:
    """Welche der ``ziele`` der Eintrag ``von`` schon mit einer Abgrenzungskante nennt."""
    ziele = list(ziele)
    if not ziele:
        return set()
    zeilen = (await db.execute(
        sa.select(ContextEdge.to_node_id, ContextEdge.metadata_)
        .where(ContextEdge.from_node_id == von, ContextEdge.to_node_id.in_(ziele),
               ContextEdge.relation == "related_to")
    )).all()
    return {ziel for ziel, metadata in zeilen if ist_abgrenzung(metadata)}


@dataclass(frozen=True)
class Bestandspaar:
    """Zwei vorhandene Einträge verschiedener Fächer mit demselben Namen."""

    a: Kollision
    b: Kollision
    art: str
    #: Nennt einer der beiden den anderen mit einer Abgrenzungskante?
    abgegrenzt: bool


async def bestand(db: AsyncSession) -> list[Bestandspaar]:
    """Alle Namensgleichen über Fachgrenzen im Bestand — die Aufräumliste (F7, „Bestand").

    Je Paar einmal, mit der schwereren Art aus beiden Richtungen.
    """
    knoten = (await db.execute(
        sa.select(ContextNode.id, ContextNode.title, ContextNode.subject_id, Subject.name,
                  ContextNode.metadata_["seed_id"].astext)
        .outerjoin(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.status == "active", ContextNode.content_type.in_(TYPEN),
               ContextNode.read_scope.in_(OFFENE_SCOPES))
        .order_by(Subject.name, ContextNode.title)
    )).all()
    aliase: dict[UUID, list[str]] = {}
    for node_id, alias in (await db.execute(
        sa.select(NodeAlias.node_id, NodeAlias.alias)
        .where(NodeAlias.node_id.in_([k[0] for k in knoten]))
    )).all():
        aliase.setdefault(node_id, []).append(alias)
    als_kollision = {
        k[0]: Kollision(k[0], k[1], k[3], k[4] or None, "titel") for k in knoten
    }

    paare: dict[frozenset, Bestandspaar] = {}
    rang = list(ARTEN)
    for node_id, titel, subject_id, _, _ in knoten:
        for k in await kollisionen(db, subject_id=subject_id, titel=titel,
                                   aliase=aliase.get(node_id, []), ohne=node_id):
            schluessel = frozenset((node_id, k.node_id))
            alt = paare.get(schluessel)
            if alt is not None and rang.index(alt.art) <= rang.index(k.art):
                continue
            grenze = bool(await abgegrenzt(db, node_id, [k.node_id])
                          or await abgegrenzt(db, k.node_id, [node_id]))
            erster, zweiter = sorted(
                (als_kollision[node_id], als_kollision[k.node_id]),
                key=lambda x: (x.fach or "", x.titel, str(x.node_id)),
            )
            paare[schluessel] = Bestandspaar(erster, zweiter, k.art, grenze)
    return sorted(paare.values(), key=lambda p: (rang.index(p.art), p.a.titel, p.a.fach or ""))
