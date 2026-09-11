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

    async def test_ohne_aliastreffer_ist_die_abfrage_unveraendert(self, erklaerplan):
        plan = await erklaerplan(identifikations_abfrage("nennen", Suchprofil(pseudonym="p")))
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


# ── Pflege über die Schnittstelle (Schritt 4) ────────────────────────────────


class TestPflege:
    """Anlegen, Ändern, Anzeigen — der Weg, auf dem Aliase überhaupt entstehen."""

    async def test_anlegen_speichert_aliase(self, test_client, auth_headers):
        resp = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge", "content_type": "methode",
                "title": "Placemat", "content": "Erst allein, dann gemeinsam.",
                "read_scope": "school", "write_scope": "school",
                "aliase": ["Platzdeckchen", "  Platzdeckchen  ", ""],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        # Leeres und normalisiert Doppeltes fallen weg — dieselbe Regel wie im Backfill.
        assert resp.json()["aliase"] == ["Platzdeckchen"]

    async def test_einzelabruf_liefert_die_aliase(self, test_client, auth_headers):
        angelegt = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge", "content_type": "methode",
                "title": "Kugellager", "content": "Innen- und Außenkreis.",
                "read_scope": "school", "write_scope": "school",
                "aliase": ["Zwiebelring"],
            },
            headers=auth_headers,
        )
        node_id = angelegt.json()["id"]
        resp = await test_client.get(f"/context/nodes/{node_id}", headers=auth_headers)
        assert resp.json()["aliase"] == ["Zwiebelring"]

    async def test_aendern_ersetzt_die_liste(self, test_client, auth_headers):
        angelegt = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge", "content_type": "methode",
                "title": "Blitzlicht", "content": "Kurze Runde.",
                "read_scope": "school", "write_scope": "school",
                "aliase": ["Stimmungsbild"],
            },
            headers=auth_headers,
        )
        node_id = angelegt.json()["id"]
        resp = await test_client.patch(
            f"/context/nodes/{node_id}",
            json={"aliase": ["Rundfrage", "Stimmungsbild"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["aliase"] == ["Rundfrage", "Stimmungsbild"]

    async def test_ohne_feld_bleiben_die_aliase_stehen(self, test_client, auth_headers):
        """Der Unterschied zwischen `None` und `[]`.

        Ein Formular ohne Aliasfeld — etwa der Verwalten-Weg oder ein Teil-Update —
        schickt den Schlüssel gar nicht. Würde das als „alle entfernen" gelesen,
        löschte jede Titeländerung stillschweigend die weiteren Namen.
        """
        angelegt = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge", "content_type": "methode",
                "title": "Museumsgang", "content": "Ergebnisse hängen aus.",
                "read_scope": "school", "write_scope": "school",
                "aliase": ["Galeriegang"],
            },
            headers=auth_headers,
        )
        node_id = angelegt.json()["id"]
        resp = await test_client.patch(
            f"/context/nodes/{node_id}", json={"title": "Museumsrundgang"},
            headers=auth_headers,
        )
        assert resp.json()["aliase"] == ["Galeriegang"]

    async def test_leere_liste_entfernt_alle(self, test_client, auth_headers):
        angelegt = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge", "content_type": "methode",
                "title": "Standbild", "content": "Eine Szene einfrieren.",
                "read_scope": "school", "write_scope": "school",
                "aliase": ["Freeze"],
            },
            headers=auth_headers,
        )
        node_id = angelegt.json()["id"]
        resp = await test_client.patch(
            f"/context/nodes/{node_id}", json={"aliase": []}, headers=auth_headers
        )
        assert resp.json()["aliase"] == []

    async def test_geloeschter_knoten_nimmt_seine_aliase_mit(
        self, test_client, auth_headers, db_session
    ):
        """Der Fremdschlüssel steht auf CASCADE — sonst blieben Namen ohne Knoten."""
        angelegt = await test_client.post(
            "/context/nodes",
            json={
                "category": "knowledge", "content_type": "methode",
                "title": "Fishbowl", "content": "Innenkreis diskutiert.",
                "read_scope": "school", "write_scope": "school",
                "aliase": ["Aquarium"],
            },
            headers=auth_headers,
        )
        node_id = uuid.UUID(angelegt.json()["id"])
        await test_client.delete(f"/context/nodes/{node_id}", headers=auth_headers)

        db_session.expire_all()
        uebrig = await db_session.execute(
            sa.select(sa.func.count()).select_from(NodeAlias).where(
                NodeAlias.node_id == node_id
            )
        )
        assert uebrig.scalar_one() == 0
