"""Weitere Namen eines Bausteins — Lesen, Schreiben, Vergleichen.

Seit Migration 0057 liegen Aliase in `node_aliases` statt in `metadata.aliase`. Dieses
Modul ist die einzige Stelle, die das weiß: Wer Aliase braucht, holt sie hier, und wer
sie vergleicht, nimmt denselben normalisierten Ausdruck wie die Titelsuche.

**Die Reihenfolge ist Teil der Daten.** Für `methode` und `operator` gehen die Aliase in
den Embedding-Input ein; eine andere Reihenfolge ergäbe einen anderen Eingabetext und
damit Vektoren, die mit den bestehenden nicht mehr vergleichbar sind — ohne Fehler, ohne
Meldung. Deshalb wird überall nach `id` sortiert (= Einfügereihenfolge), nie alphabetisch.
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.lookup import normalisiere_titel, titel_normalisiert_sql
from app.db.models import NodeAlias

#: Derselbe Ausdruck, auf dem die Indizes aus Migration 0057 liegen. Weicht eine Abfrage
#: davon ab, benutzt PostgreSQL sie stillschweigend nicht (vgl. `filters.TITEL_NORMALISIERT`).
ALIAS_NORMALISIERT = sa.literal_column(titel_normalisiert_sql("node_aliases.alias"))


def normalisiere(alias: str) -> str:
    """Dieselbe Normalisierung wie bei Titeln — klein, ohne Gliederungsnummer, ein Leerraum.

    ⚠️ **Bindestriche werden nicht gefaltet.** „Think-Pair-Share" und „Think Pair Share"
    sind darunter zwei Namen, genau wie bei Titeln. Diese Lücke schließt die
    Ähnlichkeitsstufe der Suche, nicht die Normalisierung — sonst verhielten sich Aliase
    anders als Titel, und die Suche hätte zwei Regeln statt einer.
    """
    return normalisiere_titel(alias or "")


async def lade(db: AsyncSession, node_id: UUID) -> list[str]:
    """Die Aliase eines Knotens in Einfügereihenfolge."""
    treffer = await db.execute(
        sa.select(NodeAlias.alias)
        .where(NodeAlias.node_id == node_id)
        .order_by(NodeAlias.id)
    )
    return list(treffer.scalars().all())


async def lade_viele(
    db: AsyncSession, node_ids: list[UUID]
) -> dict[UUID, list[str]]:
    """Dasselbe für viele Knoten — eine Abfrage statt einer je Knoten.

    Der Embedding-Backfill läuft über Tausende Knoten; eine Abfrage je Knoten wäre dort
    die teuerste Zeile des Laufs.
    """
    if not node_ids:
        return {}
    treffer = await db.execute(
        sa.select(NodeAlias.node_id, NodeAlias.alias)
        .where(NodeAlias.node_id.in_(node_ids))
        .order_by(NodeAlias.node_id, NodeAlias.id)
    )
    ergebnis: dict[UUID, list[str]] = {}
    for node_id, alias in treffer:
        ergebnis.setdefault(node_id, []).append(alias)
    return ergebnis


def bereinige(aliase: list[str] | None) -> list[str]:
    """Leeres weg, Dubletten weg — Reihenfolge und Schreibweise des ersten Vorkommens
    bleiben.

    Verglichen wird normalisiert, gespeichert wird, was jemand geschrieben hat: In der
    Anzeige soll „Think-Pair-Share" stehen, nicht „think-pair-share".
    """
    gesehen: set[str] = set()
    sauber: list[str] = []
    for alias in aliase or []:
        wert = (alias or "").strip()
        schluessel = normalisiere(wert)
        if not schluessel or schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        sauber.append(wert)
    return sauber


async def setze(db: AsyncSession, node_id: UUID, aliase: list[str] | None) -> list[str]:
    """Ersetzt die Aliase eines Knotens vollständig. Committet nicht.

    Löschen und neu einfügen statt eines Abgleichs: Die Reihenfolge ist Teil der Aussage,
    und ein Abgleich müsste sie mitziehen — für eine Handvoll Zeilen je Knoten wäre das
    mehr Code als Nutzen. Der Preis ist, dass `id` bei jeder Änderung neu vergeben wird;
    das ist folgenlos, weil nur die *relative* Ordnung zählt.
    """
    sauber = bereinige(aliase)
    await db.execute(sa.delete(NodeAlias).where(NodeAlias.node_id == node_id))
    for alias in sauber:
        db.add(NodeAlias(node_id=node_id, alias=alias))
    await db.flush()
    return sauber
