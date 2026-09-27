"""Die Abgrenzungen eines Treffers gegen eine echte Datenbank (Paket 9, N4).

Was hier steht und **nicht** im Unit-Test stehen kann: die Abfrage selbst — dass sie
nur `related_to`-Kanten mit `art: abgrenzung` nimmt, nur **aktive** Ziele, Titel statt
IDs, und dass der Deckel greift.

⚠️ **Der Wert dieser Sätze:** Sie stehen weder im Knotentext (`## Abgrenzung` bleibt
bewusst aus `content` heraus, sonst zögen sie im Vektor die Fragen an, die sie
abgrenzen sollen) noch im Embedding. Bis 09/2026 sah das Modell sie deshalb gar nicht.
"""
import uuid

import pytest
import sqlalchemy as sa

from app.context.search import ABGRENZUNGEN_JE_TREFFER, abgrenzungen_zu
from app.db.models import ContextEdge, ContextNode

pytestmark = pytest.mark.asyncio


async def _knoten(db, titel, *, status="active"):
    knoten = ContextNode(
        category="concept", content_type="begriff", title=titel, content="x",
        status=status, read_scope="school", write_scope="school",
    )
    db.add(knoten)
    await db.flush()
    return knoten


async def _kante(db, von, nach, metadata):
    db.add(ContextEdge(
        from_node_id=von.id, to_node_id=nach.id, relation="related_to",
        metadata_=metadata,
    ))
    await db.flush()


@pytest.fixture
async def begriff(db_session):
    return await _knoten(db_session, f"Wasserstoffbrücken {uuid.uuid4().hex[:6]}")


class TestAbgrenzungenZu:
    async def test_hinweis_und_ziel(self, db_session, begriff):
        ziel = await _knoten(db_session, "Elektronenpaarbindung X")
        await _kante(db_session, begriff, ziel,
                     {"art": "abgrenzung", "hinweis": "wirkt innerhalb eines Moleküls"})

        ergebnis = await abgrenzungen_zu(db_session, [str(begriff.id)])
        assert ergebnis[str(begriff.id)] == [
            {"zu": "Elektronenpaarbindung X", "hinweis": "wirkt innerhalb eines Moleküls"}
        ]

    async def test_titel_statt_id(self, db_session, begriff):
        """Eine UUID im Modellkontext taucht früher oder später in einer Antwort auf."""
        ziel = await _knoten(db_session, "Dipol X")
        await _kante(db_session, begriff, ziel, {"art": "abgrenzung"})

        [eintrag] = (await abgrenzungen_zu(db_session, [str(begriff.id)]))[str(begriff.id)]
        assert eintrag == {"zu": "Dipol X"}          # ohne Hinweis kein leeres Feld
        assert str(ziel.id) not in str(eintrag)

    async def test_archivierte_ziele_bleiben_draussen(self, db_session, begriff):
        """⚠️ Ein archivierter Knoten ist für die fragende Person nicht erreichbar.

        Ihn zu nennen hieße, auf etwas zu verweisen, das niemand aufschlagen kann —
        und im Dev-Bestand ist das kein Randfall: Die ganze V3-Edition Chemie ist
        archiviert.
        """
        aktiv = await _knoten(db_session, "Aktiv X")
        alt = await _knoten(db_session, "Archiviert X", status="archived")
        await _kante(db_session, begriff, aktiv, {"art": "abgrenzung"})
        await _kante(db_session, begriff, alt, {"art": "abgrenzung"})

        [eintrag] = (await abgrenzungen_zu(db_session, [str(begriff.id)]))[str(begriff.id)]
        assert eintrag["zu"] == "Aktiv X"

    async def test_andere_kantenarten_bleiben_draussen(self, db_session, begriff):
        """Nur `art: abgrenzung`. Eine Vertiefung oder ein schlichtes `verwandt` sagt
        etwas anderes und gehört nicht unter diese Überschrift."""
        for art, titel in (("vertiefung", "Vertieft X"), (None, "Verwandt X")):
            ziel = await _knoten(db_session, titel)
            await _kante(db_session, begriff, ziel, {"art": art} if art else {})
        andere = await _knoten(db_session, "Voraussetzung X")
        db_session.add(ContextEdge(
            from_node_id=begriff.id, to_node_id=andere.id, relation="requires",
            metadata_={"art": "abgrenzung"},
        ))
        await db_session.flush()

        assert await abgrenzungen_zu(db_session, [str(begriff.id)]) == {}

    async def test_deckel_greift(self, db_session, begriff):
        """Zwanzig Treffer mit je zehn Sätzen wären mehr Kontext als die Knotentexte."""
        for i in range(ABGRENZUNGEN_JE_TREFFER + 3):
            ziel = await _knoten(db_session, f"Ziel {i:02d} X")
            await _kante(db_session, begriff, ziel, {"art": "abgrenzung"})

        ergebnis = await abgrenzungen_zu(db_session, [str(begriff.id)])
        assert len(ergebnis[str(begriff.id)]) == ABGRENZUNGEN_JE_TREFFER

    async def test_mehrere_knoten_in_einer_abfrage(self, db_session, begriff):
        """Eine Abfrage für alle Treffer — bei zwanzig Treffern sonst zwanzig Rundreisen."""
        zweiter = await _knoten(db_session, "Zweiter X")
        ziel = await _knoten(db_session, "Gemeinsames Ziel X")
        await _kante(db_session, begriff, ziel, {"art": "abgrenzung"})
        await _kante(db_session, zweiter, ziel, {"art": "abgrenzung"})

        ergebnis = await abgrenzungen_zu(db_session, [str(begriff.id), str(zweiter.id)])
        assert set(ergebnis) == {str(begriff.id), str(zweiter.id)}

    async def test_leere_eingabe(self, db_session):
        assert await abgrenzungen_zu(db_session, []) == {}
        assert await abgrenzungen_zu(db_session, None) == {}
