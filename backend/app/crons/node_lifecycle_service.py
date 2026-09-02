"""Lebenszyklus der Kontextknoten: automatisch archivieren, spät löschen (ADR-013).

ADR-013 beschreibt beide Läufe seit dem ersten Entwurf (Abschnitt „Knoten-Lifecycle",
Nächste Schritte 8/9) — gebaut wurden sie nie. Die Folge war ein **wirkungsloses**
`valid_until`: Formulare erfassten es, die Datenbank speicherte es, und niemand las es je.
Ein Knoten mit Ablaufdatum blieb aktiv, im Retrieval und im Prompt.

Zwei Läufe, bewusst getrennt:

1. :func:`archiviere_abgelaufene` — ``active → archived``, sobald ``valid_until``
   überschritten ist. Archiviert heißt: raus aus Suche und Retrieval, für die
   Eigentümerin über die Archivansicht weiter erreichbar, Kanten bleiben.
2. :func:`loesche_alte_archivierte` — physisch löschen nach **1095 Tagen** (drei
   Schuljahre) im Archiv.

**Eine Wahrheit: der Status.** Der Job setzt ihn, alle Abfragen lesen nur ihn. Es gibt
bewusst **keinen** zusätzlichen ``valid_until``-Filter in den Abfragepfaden — sonst gäbe
es zwei Stellen, die „abgelaufen" verschieden beantworten könnten, und die Suche verhielte
sich anders als die Archivansicht.

⚠️ **Drei Schutzregeln beim Löschen**, jede aus einem konkreten Grund:

* **``write_scope = 'global'`` wird nie automatisch gelöscht.** Nicht Vorsicht, sondern
  Notwendigkeit: Der Bildungsplan wird jahrgangsweise archiviert, wenn eine neue Edition
  greift. Am 02.09.2026 waren **alle** 4770 archivierten Knoten der Entwicklungsdatenbank
  `global` — ohne diese Regel hätte der Lauf nach drei Jahren den archivierten
  Bildungsplan gelöscht, auf den Curricula weiterhin verweisen.
* **``metadata.loeschung_ausgesetzt = true`` schützt einzeln.** Für den Fall, den keine
  Regel vorhersieht.
* **Ohne ``archived_at`` keine Löschung.** Wer nicht weiß, seit wann etwas liegt, kann
  keine Frist berechnen. Betrifft Knoten, die vor der Einführung des Feldes archiviert
  wurden; sie brauchen eine bewusste Entscheidung, keinen Automatismus.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode

logger = logging.getLogger(__name__)

# Drei Schuljahre — lang genug für die Wiederverwendung im übernächsten Jahrgang,
# kurz genug, dass das Archiv nicht unbegrenzt wächst (ADR-013).
ARCHIV_AUFBEWAHRUNG_TAGE = 1095


@dataclass
class Archivlauf:
    geprueft: int
    archiviert: int


@dataclass
class Loeschlauf:
    faellig: int
    geloescht: int
    geschuetzt_global: int
    geschuetzt_ausgesetzt: int


async def archiviere_abgelaufene(
    db: AsyncSession, *, dry_run: bool = False, heute: date | None = None
) -> Archivlauf:
    """Setzt abgelaufene aktive Knoten auf ``archived``.

    Idempotent: Ein zweiter Lauf findet nichts mehr, weil der Status schon gewechselt hat.
    """
    stichtag = heute or datetime.now(timezone.utc).date()

    faellig = sa.and_(
        ContextNode.status == "active",
        ContextNode.valid_until.is_not(None),
        ContextNode.valid_until < stichtag,
    )

    anzahl = (
        await db.execute(sa.select(sa.func.count()).select_from(ContextNode).where(faellig))
    ).scalar_one()

    if not anzahl or dry_run:
        return Archivlauf(geprueft=anzahl, archiviert=0)

    await db.execute(
        sa.update(ContextNode)
        .where(faellig)
        .values(status="archived", archived_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return Archivlauf(geprueft=anzahl, archiviert=anzahl)


async def loesche_alte_archivierte(
    db: AsyncSession, *, dry_run: bool = False, jetzt: datetime | None = None
) -> Loeschlauf:
    """Löscht Knoten, die lange genug archiviert sind — mit den drei Schutzregeln.

    Kanten verschwinden über ``ON DELETE CASCADE``; Kinder werden **nicht** mitgenommen
    (anders als beim ausdrücklichen Löschen über die Oberfläche): Ein Kind mit eigenem
    Ablaufdatum wird selbst archiviert und selbst fällig. Wer die Kaskade will, löscht von
    Hand.
    """
    zeitpunkt = jetzt or datetime.now(timezone.utc)
    grenze = zeitpunkt - timedelta(days=ARCHIV_AUFBEWAHRUNG_TAGE)

    alt_genug = sa.and_(
        ContextNode.status == "archived",
        ContextNode.archived_at.is_not(None),
        ContextNode.archived_at < grenze,
    )
    ist_global = ContextNode.write_scope == "global"
    ist_ausgesetzt = ContextNode.metadata_["loeschung_ausgesetzt"].astext == "true"

    async def _zaehle(bedingung) -> int:
        return (
            await db.execute(sa.select(sa.func.count()).select_from(ContextNode).where(bedingung))
        ).scalar_one()

    faellig = await _zaehle(alt_genug)
    geschuetzt_global = await _zaehle(sa.and_(alt_genug, ist_global))
    geschuetzt_ausgesetzt = await _zaehle(sa.and_(alt_genug, ~ist_global, ist_ausgesetzt))

    zu_loeschen = sa.and_(alt_genug, ~ist_global, sa.not_(ist_ausgesetzt))
    anzahl = await _zaehle(zu_loeschen)

    if not anzahl or dry_run:
        return Loeschlauf(
            faellig=faellig,
            geloescht=0,
            geschuetzt_global=geschuetzt_global,
            geschuetzt_ausgesetzt=geschuetzt_ausgesetzt,
        )

    await db.execute(sa.delete(ContextNode).where(zu_loeschen))
    await db.commit()
    return Loeschlauf(
        faellig=faellig,
        geloescht=anzahl,
        geschuetzt_global=geschuetzt_global,
        geschuetzt_ausgesetzt=geschuetzt_ausgesetzt,
    )
