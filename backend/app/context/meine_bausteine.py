"""„Meine Bausteine" — eigener Bestand mit Aufmerksamkeits-Zählung (AP7, Schritt 1).

Die Seite (`/knowledge/mine`, alle Rollen) beantwortet nicht „wo ist Baustein X" —
dafür sind Sammlung, Planner und Fachseite schneller, weil sie vorfiltern. Sie ist
Rechenschaft über den eigenen Bestand, Auffangbecken über alle Erzeugungswege und
der einzige Ort, an dem der Lebenszyklus quer über die Fächer zusammenläuft
(Notiz-Knotentyp-UI, A4).

**Warum eine eigene Abfrageschicht und nicht `GET /context/nodes?owner=me`:** Jener
Weg ist auf teacher/admin beschränkt, liefert eine flache Liste ohne Fachgruppen
und kennt die Aufmerksamkeits-Kategorien nicht. Hier ist der Eigentümer die einzige
Sichtbarkeitsregel — `owner_pseudonym = ich` —, deshalb braucht es
`visibility.py` nicht: Wer den eigenen Bestand sieht, sieht nichts Fremdes.

**Eine Zählung für zwei Stellen.** Warnbanner und Sidebar-Zähler zeigen dieselbe
Gesamtzahl. Sie stammt aus derselben Funktion; zwei Zählwege gäben irgendwann zwei
Antworten auf dieselbe Frage — dieselbe Fehlerklasse, die das Projekt schon bei
den drei Anker-Listen und den zwei Schuljahresende-Funktionen hatte.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.metadata import STUB_MARKIERUNG
from app.db.models import ContextEdge, ContextNode, Subject

#: Ab wann ein Ablaufdatum als „läuft bald ab" gilt (A4).
VORLAUF_TAGE = 14


# ── Die vier Kategorien, als SQL-Bedingungen an einer Stelle ─────────────────
#
# Sie stehen hier zusammen, weil Zählung und Filter („Nur diese anzeigen")
# dieselben Bedingungen brauchen. Getrennt formuliert wären sie irgendwann
# uneins, und der Banner zählte etwas anderes, als die Liste zeigt.

def _laeuft_bald_ab(stichtag: date):
    """Aktiv und Ablaufdatum in höchstens 14 Tagen.

    Bewusst ohne Untergrenze: Ein bereits überfälliger, aber noch aktiver Knoten
    (der nächtliche Lauf war noch nicht dran) gehört ebenfalls hierher — er
    braucht Aufmerksamkeit, und die Alternative wäre, ihn gar nicht zu zählen.
    """
    return sa.and_(
        ContextNode.status == "active",
        ContextNode.valid_until.is_not(None),
        ContextNode.valid_until <= stichtag + timedelta(days=VORLAUF_TAGE),
    )


def _abgelaufen_archiviert(stichtag: date):
    """Archiviert **und** Ablaufdatum überschritten.

    Der nächtliche Lauf (`crons/node_lifecycle_service.py`) setzt beim Ablauf nur
    den Status — ein eigenes Kennzeichen „automatisch archiviert" gibt es nicht,
    und `archived_at` tragen von Hand archivierte Knoten genauso. Das
    Ablaufdatum in der Vergangenheit ist deshalb das brauchbare Merkmal; für die
    Lesende ist der Unterschied ohnehin gering. Reaktivierte Knoten fallen von
    selbst heraus (Status wieder `active`), gelöschte ohnehin.
    """
    return sa.and_(
        ContextNode.status == "archived",
        ContextNode.valid_until.is_not(None),
        ContextNode.valid_until < stichtag,
    )


def _verweist_auf_archiviertes():
    """Der Knoten hat eine **ausgehende** Kante auf einen archivierten Knoten.

    Richtung mit Bedacht: „verweist auf archivierte Referenzen" (A4) heißt, dass
    das eigene Material auf etwas zeigt, das aus dem Verkehr gezogen wurde — ein
    Curriculum auf einen abgelösten Bildungsplan-Knoten etwa. Die Gegenrichtung
    („wer zeigt auf mich") ist die F7-Löschregel und eine andere Frage.
    """
    ziel = sa.orm.aliased(ContextNode)
    return sa.exists(
        sa.select(1)
        .select_from(ContextEdge)
        .join(ziel, ziel.id == ContextEdge.to_node_id)
        .where(
            ContextEdge.from_node_id == ContextNode.id,
            ziel.status == "archived",
        )
    )


def _unvollstaendig():
    """Stub aus dem Verknüpfen-Dialog: angelegt, aber ohne Inhalt (A8).

    Nur für Lehrkräfte gezählt — Schüler:innen erzeugen keine Stubs, und eine
    Warnung, die sie nicht auflösen können, wäre Lärm.

    ⚠️ **Zweite Fassung derselben Frage.** `metadata.ist_stub()` prüft in Python
    `bool(metadata.get(STUB_MARKIERUNG))`, hier steht ein Vergleich auf das
    JSON-Literal `true`. Für alles, was der Code selbst schreibt, ist das
    dasselbe — er setzt einen Bool. Auseinander liefen sie erst bei von Hand
    gesetzten Werten wie `"ja"`: In Python wahr, hier falsch. Bewusst der strenge
    Vergleich statt eines Casts: `CAST(… AS BOOLEAN)` bräche bei solchen Werten
    mit einem Datenbankfehler, statt sie bloß nicht zu zählen.
    """
    return ContextNode.metadata_[STUB_MARKIERUNG].astext == "true"


def aufmerksamkeits_bedingung(stichtag: date, *, ist_lehrkraft: bool):
    """Alle zutreffenden Kategorien als ein ODER — für Zählung *und* Filter."""
    teile = [
        _laeuft_bald_ab(stichtag),
        _abgelaufen_archiviert(stichtag),
        _verweist_auf_archiviertes(),
    ]
    if ist_lehrkraft:
        teile.append(_unvollstaendig())
    return sa.or_(*teile)


# ── Zählung ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Aufmerksamkeit:
    """Was Banner und Sidebar-Zähler anzeigen.

    `gesamt` ist **nicht** die Summe der Kategorien: Ein Knoten kann in mehreren
    zugleich stecken (abgelaufen *und* auf Archiviertes verweisend) und wird nur
    einmal gezählt. Der Banner nennt die Kategorien einzeln, die Zahl davor ist
    die der betroffenen Bausteine.
    """

    gesamt: int = 0
    laeuft_bald_ab: int = 0
    abgelaufen: int = 0
    archivierte_referenzen: int = 0
    unvollstaendig: int = 0


async def zaehle_aufmerksamkeit(
    db: AsyncSession, pseudonym: str, *, ist_lehrkraft: bool, stichtag: date | None = None
) -> Aufmerksamkeit:
    """Eine Abfrage für Banner und Sidebar-Zähler."""
    heute = stichtag or date.today()
    eigen = ContextNode.owner_pseudonym == pseudonym

    zeilen = await db.execute(
        sa.select(
            sa.func.count().filter(aufmerksamkeits_bedingung(heute, ist_lehrkraft=ist_lehrkraft)),
            sa.func.count().filter(_laeuft_bald_ab(heute)),
            sa.func.count().filter(_abgelaufen_archiviert(heute)),
            sa.func.count().filter(_verweist_auf_archiviertes()),
            sa.func.count().filter(_unvollstaendig()) if ist_lehrkraft else sa.literal(0),
        ).select_from(ContextNode).where(eigen)
    )
    gesamt, bald, abgelaufen, referenzen, unvollstaendig = zeilen.one()
    return Aufmerksamkeit(
        gesamt=gesamt,
        laeuft_bald_ab=bald,
        abgelaufen=abgelaufen,
        archivierte_referenzen=referenzen,
        unvollstaendig=unvollstaendig,
    )


# ── Liste, nach Fach gruppiert ───────────────────────────────────────────────

@dataclass
class Baustein:
    """Eine Zeile der Liste — was A4 dafür verlangt, nicht mehr."""

    node: ContextNode
    kategorien: list[str]


@dataclass
class Fachabschnitt:
    subject_id: int | None
    fach: str | None  # None → „Ohne Fach"
    bausteine: list[Baustein]


async def lade_meine_bausteine(
    db: AsyncSession,
    pseudonym: str,
    *,
    ist_lehrkraft: bool,
    content_type: str | None = None,
    nur_aufmerksamkeit: bool = False,
    stichtag: date | None = None,
) -> list[Fachabschnitt]:
    """Eigene Knoten, nach Fach gruppiert, innerhalb nach Aktualität.

    Abschnitte in der Reihenfolge von `subjects.sort_order` — dieselbe wie in der
    Sidebar; „Ohne Fach" steht am Ende (A4). Innerhalb eines Abschnitts nach
    `updated_at` absteigend, mit `id` als stabilem Zweitschlüssel: Ohne ihn
    springt die Reihenfolge bei gleichzeitig geänderten Knoten.
    """
    heute = stichtag or date.today()

    query = (
        sa.select(
            ContextNode,
            Subject.name,
            Subject.sort_order,
            _laeuft_bald_ab(heute).label("bald"),
            _abgelaufen_archiviert(heute).label("abgelaufen"),
            _verweist_auf_archiviertes().label("referenzen"),
            _unvollstaendig().label("unvollstaendig"),
        )
        .outerjoin(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.owner_pseudonym == pseudonym)
    )
    if content_type:
        query = query.where(ContextNode.content_type == content_type)
    if nur_aufmerksamkeit:
        query = query.where(aufmerksamkeits_bedingung(heute, ist_lehrkraft=ist_lehrkraft))

    # NULLS LAST bildet „Ohne Fach am Ende" ab, ohne die Gruppierung in Python
    # nachsortieren zu müssen.
    query = query.order_by(
        sa.nulls_last(Subject.sort_order.asc()),
        sa.nulls_last(Subject.name.asc()),
        ContextNode.updated_at.desc(),
        ContextNode.id,
    )

    abschnitte: list[Fachabschnitt] = []
    for node, fach, _sort, bald, abgelaufen, referenzen, unvollstaendig in await db.execute(query):
        kategorien = []
        if bald:
            kategorien.append("laeuft_bald_ab")
        if abgelaufen:
            kategorien.append("abgelaufen")
        if referenzen:
            kategorien.append("archivierte_referenzen")
        if unvollstaendig and ist_lehrkraft:
            kategorien.append("unvollstaendig")

        if not abschnitte or abschnitte[-1].subject_id != node.subject_id:
            abschnitte.append(Fachabschnitt(subject_id=node.subject_id, fach=fach, bausteine=[]))
        abschnitte[-1].bausteine.append(Baustein(node=node, kategorien=kategorien))

    return abschnitte


def herkunft(node: ContextNode) -> dict[str, Any] | None:
    """Herkunfts-Chip: Ursprungs-Artefakt oder Assistent, falls bekannt (A4).

    `source_artifact_id` setzt erst AP8; bis dahin trägt nur `assistant_id`
    etwas bei. Die Funktion gibt es trotzdem schon, damit die Oberfläche nicht
    zweimal gebaut werden muss.
    """
    artefakt = (node.metadata_ or {}).get("source_artifact_id")
    if artefakt:
        return {"art": "artefakt", "id": str(artefakt)}
    if node.assistant_id:
        return {"art": "assistent", "id": str(node.assistant_id)}
    return None
