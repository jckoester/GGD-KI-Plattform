"""Fachbegriffe im Teilgraphen eines Anker-Assistenten (Paket 9, N7 / E4 Variante A).

⚠️ **Warum es den dritten Weg braucht.** Ein Fachbegriff verweist **auf** die
Kompetenz, in der der Bildungsplan ihn verlangt — die Kante entsteht am Begriff, nicht
an der Kompetenz (AP1: sonst trüge sie Tausende Rückverweise). Über `part_of` nach
unten und die **ausgehenden** Verweise des Ankers ist er damit unerreichbar. Gemessen
am Dev-Bestand (26.09.2026): 13 Knoten unter der Chemie-Leitidee, kein einziger
Begriff.

⚠️ **Und warum er eng bleibt.** Ohne die Typbeschränkung holte die Umkehrung jedes
Arbeitsblatt und jede Klausur herein, die auf dieselbe Kompetenz zeigt — genau die
Kantendichte, vor der ADR-013 bei Bildungsplan-Knoten warnt.
"""
import uuid

import pytest
import sqlalchemy as sa

from app.context.search import teilgraph
from app.db.models import ContextEdge, ContextNode, Subject

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def anker_mit_kompetenz(db_session):
    """Leitidee ← Kompetenz (`part_of`), wie der Bildungsplan-Import sie anlegt."""
    fach = Subject(slug=f"tf-{uuid.uuid4().hex[:8]}", name="Testfach N7", fach_code="TN7")
    db_session.add(fach)
    await db_session.flush()

    def knoten(typ, titel, **extra):
        return ContextNode(
            category="knowledge" if typ != "begriff" else "concept",
            content_type=typ, title=titel, content="x", subject_id=fach.id,
            status="active", read_scope="school", write_scope="school", **extra,
        )

    leitidee = knoten("leitidee", "9.9.9 Anker N7")
    kompetenz = knoten("ik_kompetenz", "9.9.9(1) Eine Kompetenz")
    db_session.add_all([leitidee, kompetenz])
    await db_session.flush()
    db_session.add(ContextEdge(
        from_node_id=kompetenz.id, to_node_id=leitidee.id,
        relation="part_of", metadata_={},
    ))
    await db_session.flush()
    return fach, leitidee, kompetenz, knoten


async def _im_teilgraph(db, anker) -> set[str]:
    return {
        t for (t,) in (await db.execute(
            sa.select(ContextNode.title).where(ContextNode.id.in_(teilgraph((anker.id,))))
        )).all()
    }


class TestEingehendeVerweise:
    async def test_begriff_kommt_herein(self, db_session, anker_mit_kompetenz):
        _, leitidee, kompetenz, knoten = anker_mit_kompetenz
        begriff = knoten("begriff", "Testbegriff N7")
        db_session.add(begriff)
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=begriff.id, to_node_id=kompetenz.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        assert "Testbegriff N7" in await _im_teilgraph(db_session, leitidee)

    async def test_stoffsteckbrief_ebenso(self, db_session, anker_mit_kompetenz):
        _, leitidee, kompetenz, knoten = anker_mit_kompetenz
        stoff = ContextNode(
            category="concept", content_type="stoffsteckbrief", title="Teststoff N7",
            content="x", subject_id=kompetenz.subject_id, status="active",
            read_scope="school", write_scope="school",
        )
        db_session.add(stoff)
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=stoff.id, to_node_id=kompetenz.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        assert "Teststoff N7" in await _im_teilgraph(db_session, leitidee)

    async def test_andere_typen_bleiben_draussen(self, db_session, anker_mit_kompetenz):
        """⚠️ Der eigentliche Wächter. Ein Arbeitsblatt, das auf dieselbe Kompetenz
        zeigt, gehört **nicht** in den Wissensbereich des Assistenten — sonst zieht
        jeder Anker den halben Materialbestand der Schule herein."""
        _, leitidee, kompetenz, _ = anker_mit_kompetenz
        blatt = ContextNode(
            category="document", content_type="arbeitsblatt", title="Testblatt N7",
            content="x", subject_id=kompetenz.subject_id, status="active",
            read_scope="school", write_scope="school",
        )
        db_session.add(blatt)
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=blatt.id, to_node_id=kompetenz.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        assert "Testblatt N7" not in await _im_teilgraph(db_session, leitidee)

    async def test_archivierter_begriff_bleibt_draussen(self, db_session, anker_mit_kompetenz):
        _, leitidee, kompetenz, _ = anker_mit_kompetenz
        alt = ContextNode(
            category="concept", content_type="begriff", title="Altbegriff N7",
            content="x", subject_id=kompetenz.subject_id, status="archived",
            read_scope="school", write_scope="school",
        )
        db_session.add(alt)
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=alt.id, to_node_id=kompetenz.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        assert "Altbegriff N7" not in await _im_teilgraph(db_session, leitidee)

    async def test_andere_relation_zaehlt_nicht(self, db_session, anker_mit_kompetenz):
        """Nur `references`. Ein `related_to` auf eine Kompetenz sagt etwas anderes."""
        _, leitidee, kompetenz, knoten = anker_mit_kompetenz
        nachbar = knoten("begriff", "Nachbar N7")
        db_session.add(nachbar)
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=nachbar.id, to_node_id=kompetenz.id,
            relation="related_to", metadata_={},
        ))
        await db_session.flush()

        assert "Nachbar N7" not in await _im_teilgraph(db_session, leitidee)

    async def test_begriff_am_anker_selbst(self, db_session, anker_mit_kompetenz):
        """Ein Begriff darf auch direkt auf die Leitidee zeigen (Fundstelle „Einl.")."""
        _, leitidee, _, knoten = anker_mit_kompetenz
        begriff = knoten("begriff", "Einleitungsbegriff N7")
        db_session.add(begriff)
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=begriff.id, to_node_id=leitidee.id,
            relation="references", metadata_={},
        ))
        await db_session.flush()

        assert "Einleitungsbegriff N7" in await _im_teilgraph(db_session, leitidee)
