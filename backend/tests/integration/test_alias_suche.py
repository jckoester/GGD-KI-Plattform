"""Aliase in der Namenssuche (Migration 0057) — gegen eine echte Datenbank.

Die Zusage: **Ein Alias verhält sich wie ein zweiter Titel.** Er trägt den exakten
Abgleich, die Ähnlichkeitsstufe und die Vervollständigung — sonst wäre er ein Feld, das
man pflegen kann und das nichts bewirkt, und genau das war der Zustand vor 0057.

Der zweite Gegenstand ist die **Plangüte**: Ein `OR` über zwei Tabellen kostet den
Ausdrucksindex aus Migration 0053 und damit rund 70 statt 0,3 ms je Suche — still, ohne
Fehler. `TestIndexBleibtInBenutzung` hält fest, dass der Weg über eine Vorabfrage das
nicht tut.
"""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.context.aliase import ALIAS_NORMALISIERT
from app.context.search import (
    Suchprofil,
    identifikation,
    identifikations_abfrage,
    knoten_mit_alias,
)
from app.db.models import ContextNode, NodeAlias

PSEUDO = "alias-suche-pseudo"


@pytest_asyncio.fixture
async def methode(db_session):
    """Eine Methode mit zwei weiteren Namen."""
    node = ContextNode(
        category="knowledge", content_type="methode", title="Think-Pair-Share",
        content="Zuerst allein, dann zu zweit, dann im Plenum.",
        read_scope="school", write_scope="school", status="active",
        owner_pseudonym=PSEUDO,
    )
    db_session.add(node)
    await db_session.flush()
    for alias in ("Ich-Du-Wir", "Murmelphase"):
        db_session.add(NodeAlias(node_id=node.id, alias=alias))
    await db_session.flush()
    return node


@pytest_asyncio.fixture
async def profil():
    return Suchprofil(pseudonym=PSEUDO, rollen=["teacher"])


class TestExakterTreffer:
    async def test_alias_findet_den_knoten(self, db_session, methode, profil):
        """Der Kern: „Ich-Du-Wir" führt zu „Think-Pair-Share"."""
        ergebnis = await identifikation("Ich-Du-Wir", profil, db_session)
        titel = [t["title"] for t in ergebnis.treffer]
        assert "Think-Pair-Share" in titel

    async def test_treffer_nennt_seine_weiteren_namen(self, db_session, methode, profil):
        """Sonst stünde nach der Eingabe von „Ich-Du-Wir" ein anderer Name da, ohne
        dass irgendetwas den Zusammenhang erklärt."""
        ergebnis = await identifikation("Ich-Du-Wir", profil, db_session)
        treffer = next(t for t in ergebnis.treffer if t["title"] == "Think-Pair-Share")
        assert treffer["aliase"] == ["Ich-Du-Wir", "Murmelphase"]

    async def test_alias_zaehlt_als_exakter_treffer(self, db_session, methode, profil):
        ergebnis = await identifikation("Murmelphase", profil, db_session)
        treffer = next(t for t in ergebnis.treffer if t["title"] == "Think-Pair-Share")
        assert treffer["treffer_art"] == "exakt"

    async def test_der_knoten_steht_einmal_da(self, db_session, methode, profil):
        """Zwei passende Aliase dürfen den Knoten nicht verdoppeln — deshalb wird über
        eine ID-Menge gefiltert und nicht gejoint."""
        db_session.add(NodeAlias(node_id=methode.id, alias="Ich Du Wir"))
        await db_session.flush()
        ergebnis = await identifikation("ich du wir", profil, db_session)
        ids = [t["node_id"] for t in ergebnis.treffer]
        assert len(ids) == len(set(ids))


class TestAehnlichkeit:
    async def test_teiltreffer_ueber_den_alias(self, db_session, methode, profil):
        """Die Lücke, die die Normalisierung offen lässt: Bindestrich gegen Leerzeichen.

        „Think Pair Share" ist unter der Titel-Normalisierung ein anderer Name als
        „Think-Pair-Share" — die Ähnlichkeitsstufe fängt das auf, für Titel wie für
        Aliase gleichermaßen.
        """
        ergebnis = await identifikation("Ich Du Wir", profil, db_session)
        assert any(t["title"] == "Think-Pair-Share" for t in ergebnis.treffer)

    async def test_reiner_aliastreffer_steht_nicht_hinten(self, db_session, profil):
        """Ohne das `greatest` in der Sortierung stünde ein Knoten, der **nur** über
        seinen Alias trifft, hinter jedem schwachen Titeltreffer."""
        schwach = ContextNode(
            category="knowledge", content_type="methode", title="Ich Du Wir Variante",
            content="Ein anderer Eintrag.", read_scope="school", write_scope="school",
            status="active", owner_pseudonym=PSEUDO,
        )
        treffer_knoten = ContextNode(
            category="knowledge", content_type="methode", title="Placemat",
            content="Etwas ganz anderes.", read_scope="school", write_scope="school",
            status="active", owner_pseudonym=PSEUDO,
        )
        db_session.add_all([schwach, treffer_knoten])
        await db_session.flush()
        db_session.add(NodeAlias(node_id=treffer_knoten.id, alias="Ich-Du-Wir"))
        await db_session.flush()

        ergebnis = await identifikation("Ich-Du-Wir", profil, db_session)
        titel = [t["title"] for t in ergebnis.treffer]
        assert "Placemat" in titel, "Aliastreffer fehlt ganz"
        # Der exakte Aliastreffer steht vor dem bloß ähnlichen Titel.
        assert titel.index("Placemat") < titel.index("Ich Du Wir Variante")


class TestVervollstaendigung:
    async def test_praefix_greift_auch_auf_aliase(self, db_session, methode, profil):
        """Der `@`-Shortcode: Wer „Ich-" tippt, soll die Methode angeboten bekommen."""
        ergebnis = await identifikation("Ich-", profil, db_session, praefix=True)
        assert any(t["title"] == "Think-Pair-Share" for t in ergebnis.treffer)


class TestIndexBleibtInBenutzung:
    """Der Grund, warum die Aliase **nicht** als korreliertes EXISTS in der Hauptabfrage
    stehen. Der erste Entwurf tat genau das und verdrängte den Index aus Migration 0053."""

    async def test_ohne_aliastreffer_ist_die_abfrage_unveraendert(self, db_url, run_migrations):
        from sqlalchemy.ext.asyncio import create_async_engine

        abfrage = identifikations_abfrage("nennen", Suchprofil(pseudonym="p"))
        roh = str(abfrage.compile(compile_kwargs={"literal_binds": True}))
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as con:
                plan = "\n".join(
                    r[0] for r in (await con.execute(sa.text("EXPLAIN " + roh))).all()
                )
        finally:
            await engine.dispose()
        assert "idx_context_nodes_titel_nachschlagen" in plan, plan

    async def test_mit_aliastreffern_wird_die_id_liste_angehaengt(self, db_session, methode):
        """Und mit Treffern? Dann kommt eine ID-Liste dazu — kein Join, kein EXISTS.

        `node_aliases` steht trotzdem in der Abfrage: als Ergebnis**spalte**, die die
        weiteren Namen mitliefert. Die trägt keine Auswahl und beeinflusst den Plan
        nicht — geprüft wird deshalb die Auswahlbedingung, nicht der ganze Text.
        """
        ids = await knoten_mit_alias(db_session, ALIAS_NORMALISIERT.in_(["ich-du-wir"]))
        assert methode.id in ids

        abfrage = identifikations_abfrage(
            ["ich-du-wir"], Suchprofil(pseudonym=PSEUDO), alias_ids=ids
        )
        roh = str(abfrage.compile(compile_kwargs={"literal_binds": True}))
        assert "EXISTS" not in roh.upper(), f"Alias-Auswahl als EXISTS statt ID-Liste:\n{roh}"
        assert "context_nodes.id IN (" in roh, roh
        # SQLAlchemy schreibt die UUID ohne Bindestriche in das Literal.
        assert methode.id.hex in roh
        # Genau ein Vorkommen als Datenquelle: die Ergebnisspalte. Käme ein zweites
        # dazu, wäre die Auswahl wieder über die Tabelle gegangen.
        assert roh.upper().count("FROM NODE_ALIASES") == 1


class TestOhneAliase:
    async def test_knoten_ohne_alias_tragen_kein_feld(self, db_session, profil):
        """`"aliase": []` an jedem Treffer wäre Rauschen im Modellkontext."""
        node = ContextNode(
            category="knowledge", content_type="methode", title="Placemat solo",
            content="Ohne weitere Namen.", read_scope="school", write_scope="school",
            status="active", owner_pseudonym=PSEUDO,
        )
        db_session.add(node)
        await db_session.flush()
        ergebnis = await identifikation("Placemat solo", profil, db_session)
        treffer = next(t for t in ergebnis.treffer if t["title"] == "Placemat solo")
        assert "aliase" not in treffer
