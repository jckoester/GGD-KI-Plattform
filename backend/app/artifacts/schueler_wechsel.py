"""Schüler-Bausteine in die Werkstatt überführen (0.41, Päckchen AN, Schritt 9).

Seit 0.41 bleibt, was Schüler:innen aus dem Chat behalten, ein **Produkt** in ihrer
Werkstatt; die Bausteinarten `schuelertext`, `lernplan` und `schuelerpraesentation` ruhen.
Dieser Lauf räumt den Bestand einmal um — aufgerufen über
`scripts/schueler_bausteine_ueberfuehren.py`, erst mit `--dry-run`.

Je Baustein einer dieser Arten:

- **Quellprodukt vorhanden** (`metadata.source_artifact_id`, gleiche Eigentümer:in): Fach
  ans Produkt, wenn dort keins steht; Titel, wenn das Produkt nur den Platzhalter trägt.
  Dann den Baustein löschen. Das ist der Regelfall — die Übernahme ging immer von einem
  Produkt aus.
- **Kein Quellprodukt mehr:** aus dem Inhalt ein Dokument anlegen (mit Fach und Titel des
  Bausteins), dann löschen. Reicht die Quota nicht, bleibt der Baustein stehen und das
  Protokoll sagt es — der Lauf bricht nicht ab.
- **Ohne Inhalt und ohne Produkt:** bleibt stehen (nichts zu retten, aber auch nichts
  still zu verwerfen).
- **Von fremden aktiven Bausteinen referenziert:** bleibt stehen (F7, wie beim Löschen
  in der Oberfläche).

`strukturierung` ist rollenoffen und bleibt für Lehrkräfte. Bausteine dieser Art von
Personen ohne Lehrkraft-Rolle **listet** der Lauf nur (F9: Jan entscheidet am Protokoll);
überführt werden sie erst mit ``mit_strukturierung=True``.

Das Protokoll nennt Kennungen, Arten und Ausgänge — keine Titel: Es landet in einer
Konsole, und die Titel sind Arbeiten von Schüler:innen.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts import store
from app.artifacts.limits import get_artifact_limits
from app.db.models import Artifact, ContextEdge, ContextNode, GroupMembership, PseudonymAudit

UEBERFUEHRTE_TYPEN: tuple[str, ...] = ("schuelertext", "lernplan", "schuelerpraesentation")
ROLLENOFFEN = "strukturierung"
_PLATZHALTER_TITEL = {"", "Dokument"}

# Ausgänge — die Schlüssel des Protokolls.
PRODUKT_VORHANDEN = "produkt_vorhanden"
DOKUMENT_ANGELEGT = "dokument_angelegt"
QUOTA = "quota_reicht_nicht"
OHNE_INHALT = "ohne_inhalt"
REFERENZIERT = "fremd_referenziert"
NUR_GELISTET = "nur_gelistet"  # strukturierung ohne `mit_strukturierung`

BLEIBT_STEHEN = {QUOTA, OHNE_INHALT, REFERENZIERT, NUR_GELISTET}


@dataclass
class Eintrag:
    node_id: UUID
    content_type: str
    ausgang: str
    produkt_id: UUID | None = None


@dataclass
class Bericht:
    dry_run: bool
    eintraege: list[Eintrag] = field(default_factory=list)

    def zaehlung(self) -> dict[str, int]:
        return dict(Counter(e.ausgang for e in self.eintraege))

    @property
    def geloescht(self) -> int:
        return sum(1 for e in self.eintraege if e.ausgang not in BLEIBT_STEHEN)


async def _ist_lehrkraft(db: AsyncSession, pseudonym: str) -> bool:
    """Lehrkraft-Rolle beim letzten Login oder eine Lehrkraft-Mitgliedschaft (F9)."""
    audit = await db.get(PseudonymAudit, pseudonym)
    if audit is not None:
        rollen = set(audit.roles or []) | {audit.role}
        if rollen & {"teacher", "admin"}:
            return True
    treffer = await db.execute(
        sa.select(sa.literal(1)).where(
            GroupMembership.pseudonym == pseudonym,
            GroupMembership.role_in_group == "teacher",
        ).limit(1)
    )
    return treffer.first() is not None


async def _rolle_und_jahrgang(db: AsyncSession, pseudonym: str) -> tuple[list[str], int | None]:
    """Für Quota und Frist des neuen Dokuments — wie beim letzten Login."""
    audit = await db.get(PseudonymAudit, pseudonym)
    if audit is None:
        return ["student"], None
    return list(audit.roles or [audit.role]), audit.grade


async def _fremd_referenziert(db: AsyncSession, node: ContextNode) -> bool:
    treffer = await db.execute(
        sa.select(sa.literal(1))
        .select_from(ContextEdge)
        .join(ContextNode, ContextNode.id == ContextEdge.from_node_id)
        .where(
            ContextEdge.to_node_id == node.id,
            ContextNode.status == "active",
            ContextNode.owner_pseudonym != node.owner_pseudonym,
        )
        .limit(1)
    )
    return treffer.first() is not None


async def _kandidaten(db: AsyncSession) -> list[ContextNode]:
    treffer = await db.execute(
        sa.select(ContextNode)
        .where(
            ContextNode.content_type.in_(UEBERFUEHRTE_TYPEN + (ROLLENOFFEN,)),
            ContextNode.status != "deleted",
            ContextNode.owner_pseudonym.isnot(None),
        )
        .order_by(ContextNode.owner_pseudonym, ContextNode.created_at)
    )
    return list(treffer.scalars())


async def _quellprodukt(db: AsyncSession, node: ContextNode) -> Artifact | None:
    roh = (node.metadata_ or {}).get("source_artifact_id")
    if not roh:
        return None
    try:
        produkt = await db.get(Artifact, UUID(str(roh)))
    except ValueError:
        return None
    if produkt is None or produkt.owner_pseudonym != node.owner_pseudonym:
        return None
    return produkt


async def ueberfuehre(
    db: AsyncSession, *, dry_run: bool, mit_strukturierung: bool = False
) -> Bericht:
    bericht = Bericht(dry_run=dry_run)
    # Im Probelauf entsteht nichts — die Quota rechnet die geplanten Dokumente mit.
    geplant: Counter[str] = Counter()

    for node in await _kandidaten(db):
        owner = node.owner_pseudonym
        if node.content_type == ROLLENOFFEN:
            if await _ist_lehrkraft(db, owner):
                continue
            if not mit_strukturierung:
                bericht.eintraege.append(Eintrag(node.id, node.content_type, NUR_GELISTET))
                continue

        if await _fremd_referenziert(db, node):
            bericht.eintraege.append(Eintrag(node.id, node.content_type, REFERENZIERT))
            continue

        produkt = await _quellprodukt(db, node)
        if produkt is not None:
            if not dry_run:
                if produkt.subject_id is None and node.subject_id is not None:
                    produkt.subject_id = node.subject_id
                if (produkt.title or "").strip() in _PLATZHALTER_TITEL and (node.title or "").strip():
                    produkt.title = node.title.strip()[:200]
                await db.delete(node)
                await db.commit()
            bericht.eintraege.append(
                Eintrag(node.id, node.content_type, PRODUKT_VORHANDEN, produkt.id)
            )
            continue

        inhalt = (node.content or "").strip()
        if not inhalt:
            bericht.eintraege.append(Eintrag(node.id, node.content_type, OHNE_INHALT))
            continue

        rollen, jahrgang = await _rolle_und_jahrgang(db, owner)
        if dry_run:
            _, quota = get_artifact_limits(rollen, jahrgang)
            groesse = len(inhalt.encode("utf-8"))
            belegt = await store.used_bytes(db, owner) + geplant[owner]
            if belegt + groesse > quota:
                bericht.eintraege.append(Eintrag(node.id, node.content_type, QUOTA))
            else:
                geplant[owner] += groesse
                bericht.eintraege.append(Eintrag(node.id, node.content_type, DOKUMENT_ANGELEGT))
            continue

        node_id, typ = node.id, node.content_type
        try:
            dokument = await store.create_document(
                db, owner_pseudonym=owner, roles=rollen, grade=jahrgang,
                title=node.title or "", markdown=inhalt, subject_id=node.subject_id,
            )
        except store.QuotaExceeded:
            bericht.eintraege.append(Eintrag(node_id, typ, QUOTA))
            continue
        # `create_document` committet schon; erst danach den Baustein löschen — schlägt
        # das fehl, gibt es das Dokument doppelt, aber nichts geht verloren.
        await db.delete(node)
        await db.commit()
        bericht.eintraege.append(Eintrag(node_id, typ, DOKUMENT_ANGELEGT, dokument.id))

    return bericht
