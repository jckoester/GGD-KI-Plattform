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

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.lookup import normalisiere_titel, titel_normalisiert_sql
from app.db.models import ContextNode, NodeAlias, ohne_aenderungsstempel

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


def hat_alias_wie(muster: str):
    """``EXISTS``: Der Knoten hat einen Alias, der ``ILIKE muster`` erfüllt.

    Für den Namensfilter ``?q=`` (`filters.wende_an`). Dort ist das korrelierte
    ``EXISTS`` unbedenklich — anders als in der Identifikation, wo es den Index-Scan auf
    dem Titelausdruck zerstört (`search.knoten_mit_alias`): Der Titelteil des Filters,
    ``title ILIKE '%…%'``, kann ohnehin keinen Index nutzen, die Abfrage ist mit und
    ohne ``EXISTS`` ein Durchlauf. Gemessen am 04.10.2026 auf Dev (18 969 Knoten, Median
    aus neun Läufen): Vorschlagsfeld Methode 0,02 → 0,36 ms, Sammlung Operatoren
    1,0 → 1,5 ms, ohne Typ 17 → 14 ms (Rauschen).
    """
    return sa.exists().where(
        NodeAlias.node_id == ContextNode.id, NodeAlias.alias.ilike(muster)
    )


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


# ── Nachzügler im toten Feld (0.13.1) ────────────────────────────────────────────
#
# Migration 0057 hat `metadata.aliase` einmal in die Tabelle übernommen und das Feld
# geleert. Danach schrieben drei Wege weiter dorthin, wo niemand mehr liest: der
# Bildungsplan-Import (Operator-Synonyme), der Methodik-Seed und `POST/PATCH
# /context/nodes`. Alle drei sind in 0.13.1 behoben; was sie bis dahin abgelegt haben,
# holt `nachziehen()` einmal nach.
#
# **Ergänzt, ersetzt nicht** — anders als der Backfill in 0057, der in eine leere Tabelle
# schrieb: Ein Knoten kann hier Aliase an beiden Orten haben, und was in der Tabelle
# steht, hat womöglich jemand im Editor gepflegt. Neue Namen kommen hinten dazu, in der
# Reihenfolge aus dem Feld; Dubletten (auch in anderer Schreibweise) weist der eindeutige
# Index ab.

_NACHZUG_SQL = """
    INSERT INTO node_aliases (node_id, alias)
    SELECT n.id, btrim(a.alias)
      FROM context_nodes n
      CROSS JOIN LATERAL jsonb_array_elements_text(n.metadata->'aliase')
           WITH ORDINALITY AS a(alias, ord)
     WHERE jsonb_typeof(n.metadata->'aliase') = 'array'
       AND btrim(a.alias) <> ''
     ORDER BY n.id, a.ord
    ON CONFLICT DO NOTHING
    RETURNING node_id
"""

_FELD_RAEUMEN_SQL = """
    UPDATE context_nodes SET metadata = metadata - 'aliase'
     WHERE metadata ? 'aliase'
    RETURNING id
"""


@dataclass
class Nachzug:
    knoten_mit_altfeld: int = 0
    neue_aliase: int = 0
    knoten_mit_neuen_aliasen: int = 0
    vektoren_verworfen: int = 0


async def nachziehen(db: AsyncSession) -> Nachzug:
    """Übernimmt `metadata.aliase` in die Tabelle und räumt das Feld. Committet nicht.

    Ein Knoten, der dabei neue Namen bekommt **und** sie im Embedding-Input trägt (etwa
    `methode`, `operator`; `embedding.braucht_aliase`), verliert seinen Vektor: Er
    entstand ohne diese Namen. Den neuen rechnet der nächtliche Backfill. Ein zweiter
    Lauf findet nichts mehr.
    """
    from app.context.embedding import braucht_aliase

    neu = [zeile[0] for zeile in (await db.execute(sa.text(_NACHZUG_SQL))).all()]
    geraeumt = (await db.execute(sa.text(_FELD_RAEUMEN_SQL))).all()
    bilanz = Nachzug(
        knoten_mit_altfeld=len(geraeumt),
        neue_aliase=len(neu),
        knoten_mit_neuen_aliasen=len(set(neu)),
    )
    if neu:
        mit_vektor = (
            await db.execute(
                sa.select(ContextNode.id, ContextNode.category, ContextNode.content_type)
                .where(ContextNode.id.in_(set(neu)), ContextNode.embedding.is_not(None))
            )
        ).all()
        verwerfen = [k.id for k in mit_vektor if braucht_aliase(k)]
        if verwerfen:
            # Kein Änderungsstempel: Der Knoten liest sich danach wie gedacht, nur sein
            # Vektor wird neu gerechnet (`ohne_aenderungsstempel`).
            await db.execute(
                sa.update(ContextNode)
                .where(ContextNode.id.in_(verwerfen))
                .values(embedding=None, **ohne_aenderungsstempel())
            )
        bilanz.vektoren_verworfen = len(verwerfen)
    return bilanz
