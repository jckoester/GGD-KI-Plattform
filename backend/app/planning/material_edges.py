"""Materialkanten aus der Stundenplanung (AP6b).

Eine Stunde führt ihr Material **je Phase** in `metadata.phasen[].material[]` — je
Eintrag entweder Freitext (`typ: "text"`) oder eine Knotenreferenz
(`typ: "node"`, mit `node_id`). Die Phase ist der richtige Ort dafür: Ein
Arbeitsblatt gehört zur Erarbeitung, nicht zur ganzen Stunde.

Für die **Rückrichtung** taugt das nicht. „Wo wird dieser Baustein eingesetzt?" —
und damit „kann ich ihn gefahrlos ändern oder löschen?" — ist eine Frage an den
Baustein, nicht an alle Stunden der Schule. Deshalb entsteht daraus zusätzlich
eine `used_with`-Kante **von der Stunde auf den Baustein**, mit den Phasen als
Angabe an der Kante.

**Die Kante ist ein abgeleiteter Index, kein zweiter Speicherort.** Sie wird bei
jedem Speichern neu aus den Phasen bestimmt; die Phasen bleiben die Wahrheit.
Dasselbe Muster nutzt der Curriculum-Editor (`context/service.py`, Material-Token
→ `used_with` mit `via: "material"`).

**Warum `material[]` und nicht `methode`/`sozialform`.** Eine Kante markiert eine
*Abhängigkeit* — das Ziel zu ändern oder zu löschen hat Folgen für die Stunde.
Sie markiert keine *Nennung*. `LessonLinkedItem` speichert `titel` redundant:
Verschwindet der Knoten „Gruppenpuzzle", steht in der Stunde weiterhin
„Gruppenpuzzle" — es fehlt nichts. Verschwindet ein Arbeitsblatt, fehlt das
Arbeitsblatt. Die Regel ist am Feld ablesbar (`material` ist eine Liste von
Inhalten, `methode`/`sozialform` sind beschreibende Einzelfelder) und braucht
keine Typprüfung. Sie gilt auch für Ziele, die niemandem persönlich gehören —
ein `begriff` der Fachschaft kann ebenso geändert oder archiviert werden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextEdge

#: Relation und Herkunftsmarke der erzeugten Kanten. Über `via` sind sie von
#: anderen `used_with`-Kanten unterscheidbar — der Abgleich unten fasst nur
#: eigene an und lässt von Hand gezogene Verbindungen in Ruhe.
RELATION = "used_with"
VIA = "material"


# ── Soll-Zustand: was die Phasen sagen ───────────────────────────────────────

def soll_kanten(metadata: dict[str, Any] | None) -> dict[UUID, list[str]]:
    """Aus den Phasen einer Stunde: Baustein → Phasen, in denen er vorkommt.

    Freitext-Material (`typ != "node"`) und Einträge ohne verwertbare `node_id`
    fallen weg. Dasselbe Material in mehreren Phasen ergibt **einen** Eintrag mit
    mehreren Phasen — nicht mehrere Kanten. Die Phasen sind sortiert, damit ein
    Vergleich zweier Stände nicht an der Reihenfolge scheitert.

    Phasen ohne `id` liefern keine Phasenangabe; der Baustein erscheint dann mit
    leerer Liste. Das ist Absicht: Die Kante ist trotzdem richtig, nur die
    Verortung fehlt.
    """
    treffer: dict[UUID, set[str]] = {}
    for phase in (metadata or {}).get("phasen") or []:
        if not isinstance(phase, dict):
            continue
        phase_id = phase.get("id")
        for eintrag in phase.get("material") or []:
            if not isinstance(eintrag, dict) or eintrag.get("typ") != "node":
                continue
            knoten = _als_uuid(eintrag.get("node_id"))
            if knoten is None:
                continue
            phasen = treffer.setdefault(knoten, set())
            if phase_id:
                phasen.add(str(phase_id))
    return {knoten: sorted(phasen) for knoten, phasen in treffer.items()}


def _als_uuid(wert: Any) -> UUID | None:
    """Nimmt UUID oder String; alles andere ist kein Verweis."""
    if isinstance(wert, UUID):
        return wert
    if isinstance(wert, str):
        try:
            return UUID(wert)
        except ValueError:
            return None
    return None


# ── Abgleich: Ist gegen Soll, ohne Datenbank ─────────────────────────────────

@dataclass
class Abgleich:
    """Was ein Lauf an den Kanten täte — ohne Datenbank entschieden, deshalb prüfbar."""

    anlegen: dict[UUID, list[str]] = field(default_factory=dict)
    aktualisieren: dict[UUID, list[str]] = field(default_factory=dict)
    loeschen: list[UUID] = field(default_factory=list)

    @property
    def leer(self) -> bool:
        return not (self.anlegen or self.aktualisieren or self.loeschen)


def plane_abgleich(
    ist: dict[UUID, list[str]], soll: dict[UUID, list[str]]
) -> Abgleich:
    """Vergleicht die vorhandenen Kanten mit dem, was die Phasen verlangen.

    ⚠️ **Löschen gehört dazu.** `create_edge` in `context/service.py` ist zwar
    idempotent, legt also keine Dubletten an — es entfernt aber nichts. Wer nur
    anlegt, hinterlässt beim Herausnehmen von Material eine Kante, die einen
    Einsatz behauptet, den es nicht mehr gibt. „Eingesetzt in" zeigte dann auf
    eine Stunde, in der der Baustein längst nicht mehr vorkommt.
    """
    abgleich = Abgleich()
    for knoten, phasen in soll.items():
        if knoten not in ist:
            abgleich.anlegen[knoten] = phasen
        elif ist[knoten] != phasen:
            abgleich.aktualisieren[knoten] = phasen
    abgleich.loeschen = [knoten for knoten in ist if knoten not in soll]
    return abgleich


# ── Datenbankschicht: dünn, die Entscheidung steckt oben ─────────────────────

async def synchronisiere_materialkanten(
    db: AsyncSession, stunde_id: UUID, metadata: dict[str, Any] | None
) -> Abgleich:
    """Bringt die Materialkanten einer Stunde auf den Stand ihrer Phasen.

    Ruft **jeder** Speicherpfad auf — Editor, Planungsassistent, Verschiebe- und
    Übertragungslogik. Eine Regel, ein Ort: Die `valid_until`-Vorbelegung lief an
    fünf Anlegestellen vorbei und griff deshalb nie (AP4).

    Committet nicht; das überlässt sie dem Aufrufer, damit die Kanten in dieselbe
    Transaktion fallen wie die Stunde selbst.
    """
    vorhanden = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == stunde_id,
            ContextEdge.relation == RELATION,
            ContextEdge.metadata_["via"].astext == VIA,
        )
    )
    kanten = {kante.to_node_id: kante for kante in vorhanden.scalars()}
    ist = {
        ziel: sorted(kante.metadata_.get("phasen") or [])
        for ziel, kante in kanten.items()
    }

    abgleich = plane_abgleich(ist, soll_kanten(metadata))

    for knoten, phasen in abgleich.anlegen.items():
        db.add(
            ContextEdge(
                from_node_id=stunde_id,
                to_node_id=knoten,
                relation=RELATION,
                metadata_={"via": VIA, "phasen": phasen},
            )
        )
    for knoten, phasen in abgleich.aktualisieren.items():
        # Neu zuweisen statt in-place ändern — SQLAlchemy verfolgt JSONB-Spalten
        # nicht auf Mutationen im Dict.
        kanten[knoten].metadata_ = {"via": VIA, "phasen": phasen}
    for knoten in abgleich.loeschen:
        await db.delete(kanten[knoten])

    if not abgleich.leer:
        await db.flush()
    return abgleich
