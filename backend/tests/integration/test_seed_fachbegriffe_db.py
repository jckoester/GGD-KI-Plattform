"""Der Schreibteil des Fachbegriff-Seeds gegen eine echte Datenbank (Paket 9, AP5).

Was hier steht und **nicht** im Unit-Test stehen kann: Scopes gegen den
CHECK-Constraint, Aliase in `node_aliases`, Kanten, das Auflösen der Fundstellen gegen
importierte Bildungsplan-Knoten — und die Idempotenz, die ohne zweiten Lauf gegen
denselben Bestand keine Aussage ist.

⚠️ **Der Bestand wird hier angelegt, nicht vorausgesetzt.** Die Testdatenbank führt
keinen Bildungsplan; die beiden Kompetenzknoten unten sind das Minimum, an dem sich
zeigt, dass `3.2.1.1(1)` nicht `3.2.1.1(10)` trifft.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.db.models import ContextEdge, ContextNode, Group, NodeAlias, Subject

pytestmark = pytest.mark.asyncio

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_fachbegriffe.py"
VAULT = Path(__file__).resolve().parents[1] / "fixtures" / "fachbegriffe"


def _seed_modul():
    spec = importlib.util.spec_from_file_location("seed_fachbegriffe", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def seed():
    return _seed_modul()


@pytest.fixture
async def testfach(db_session):
    """Fach „Testfach" samt Fachschaftsgruppe und zwei Bildungsplan-Knoten."""
    fach = Subject(
        slug=f"testfach-{uuid.uuid4().hex[:8]}", name="Testfach", fach_code="TF"
    )
    db_session.add(fach)
    await db_session.flush()
    kennung = uuid.uuid4().hex[:8]
    db_session.add(Group(
        name="FS Testfach", slug=f"fs-testfach-{kennung}",
        type="subject_department", subject_id=fach.id,
        sso_group_id=f"fs-tf-{kennung}",
    ))
    for nr, titel, typ in (
        ("3.2.1.1(1)", "3.2.1.1(1) die erste Kompetenz", "ik_kompetenz"),
        # ⚠️ Der Gegenfall zum Titelpräfix: `3.2.1.1(1)` ist ein Präfix von
        # `3.2.1.1(10)`. Deshalb wird gegen `metadata.kompetenz_nr` aufgelöst.
        ("3.2.1.1(10)", "3.2.1.1(10) die zehnte Kompetenz", "ik_kompetenz"),
    ):
        db_session.add(ContextNode(
            category="knowledge", content_type=typ, title=titel, content="x",
            subject_id=fach.id, bp_version="2016.V2", status="active",
            read_scope="school", write_scope="school",
            metadata_={"kompetenz_nr": nr},
        ))
    db_session.add(ContextNode(
        category="knowledge", content_type="leitidee",
        title="3.2.1.1 Die Leitidee", content="x",
        subject_id=fach.id, bp_version="2016.V2", status="active",
        read_scope="school", write_scope="school", metadata_={"nr": "3.2.1.1"},
    ))
    await db_session.flush()
    return fach


async def _lauf(seed, db_session, *, ueberschreiben=False):
    bilanz = seed.Bilanz()
    gelesen = seed.lies_ordner(VAULT, bilanz)
    await seed.seed_in_session(db_session, gelesen, bilanz, ueberschreiben=ueberschreiben)
    await db_session.flush()
    return bilanz


async def _knoten(db_session, titel):
    return (await db_session.execute(
        sa.select(ContextNode).where(ContextNode.title == titel)
    )).scalars().one()


class TestErsterLauf:
    async def test_beide_typen_werden_angelegt(self, seed, db_session, testfach):
        bilanz = await _lauf(seed, db_session)
        assert bilanz.neu == 2 and bilanz.aktualisiert == 0

        begriff = await _knoten(db_session, "Fiktivum")
        stoff = await _knoten(db_session, "Teststoff")
        assert begriff.content_type == "begriff"
        assert stoff.content_type == "stoffsteckbrief"
        assert begriff.subject_id == testfach.id

    async def test_scopes_sind_fachschaftsgut(self, seed, db_session, testfach):
        """Das Zielbild aus ADR-019: alle lesen, die Fachschaft pflegt.

        `write_scope = subject` **ohne** Gruppe verletzt
        `check_context_nodes_write_group_id` — ein Unit-Test sähe das nie.
        """
        await _lauf(seed, db_session)
        gruppe_id = (await db_session.execute(
            sa.select(Group.id).where(Group.subject_id == testfach.id)
        )).scalar_one()
        knoten = await _knoten(db_session, "Fiktivum")
        assert (knoten.read_scope, knoten.write_scope) == ("school", "subject")
        assert knoten.write_scope_group_id == gruppe_id

    async def test_aliase_landen_in_der_tabelle(self, seed, db_session, testfach):
        """Seit Migration 0057 sind Aliase eine eigene Tabelle, keine Metadaten."""
        await _lauf(seed, db_session)
        knoten = await _knoten(db_session, "Fiktivum")
        aliase = (await db_session.execute(
            sa.select(NodeAlias.alias)
            .where(NodeAlias.node_id == knoten.id).order_by(NodeAlias.id)
        )).scalars().all()
        assert list(aliase) == ["Fikt", "Fiktivum"]

    async def test_fundstelle_trifft_die_richtige_kompetenz(self, seed, db_session, testfach):
        """⚠️ Der eigentliche Grund für diesen Test: `(1)` darf nicht `(10)` treffen."""
        await _lauf(seed, db_session)
        begriff = await _knoten(db_session, "Fiktivum")
        ziele = (await db_session.execute(
            sa.select(ContextNode.title)
            .join(ContextEdge, ContextEdge.to_node_id == ContextNode.id)
            .where(ContextEdge.from_node_id == begriff.id,
                   ContextEdge.relation == "references")
        )).scalars().all()
        assert sorted(ziele) == ["3.2.1.1 Die Leitidee", "3.2.1.1(1) die erste Kompetenz"]

    async def test_unbekannte_fundstelle_bricht_nicht_ab(self, seed, db_session, testfach):
        """`3.9.9.9 (1)` gibt es nicht, `Unsinn` ist nicht einmal lesbar."""
        bilanz = await _lauf(seed, db_session)
        assert "TF.V2 3.9.9.9 (1)" in bilanz.offene_fundstellen
        assert any("Fundstelle unlesbar" in w for w in bilanz.warnungen)

    async def test_unaufloesbare_ziele_stehen_im_bericht(self, seed, db_session, testfach):
        """E3: keine Stub-Knoten — die Sammlung sehen Schüler:innen."""
        bilanz = await _lauf(seed, db_session)
        assert bilanz.offene_ziele["Sammelbegriff"] >= 1
        vorhanden = (await db_session.execute(
            sa.select(sa.func.count()).select_from(ContextNode)
            .where(ContextNode.title == "Sammelbegriff")
        )).scalar_one()
        assert vorhanden == 0

    async def test_kante_zwischen_zwei_pilotknoten(self, seed, db_session, testfach):
        """Teststoff nennt Fiktivum unter `verwandt` — beide kommen aus dem Ordner."""
        await _lauf(seed, db_session)
        stoff = await _knoten(db_session, "Teststoff")
        begriff = await _knoten(db_session, "Fiktivum")
        kante = (await db_session.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == stoff.id,
                ContextEdge.to_node_id == begriff.id,
            )
        )).scalars().one()
        assert kante.relation == "related_to" and kante.metadata_["seed"] is True

    async def test_svg_liegt_am_knoten(self, seed, db_session, testfach):
        await _lauf(seed, db_session)
        knoten = await _knoten(db_session, "Fiktivum")
        [erste, zweite] = knoten.metadata_["illustrationen"]
        assert erste["svg"].startswith("<svg")
        assert "svg" not in zweite          # die Datei gibt es nicht


class TestZweiterLauf:
    async def test_zweiter_lauf_aendert_nichts(self, seed, db_session, testfach):
        """Die eigentliche Zusage der Idempotenz — ohne zweiten Lauf ist sie keine."""
        await _lauf(seed, db_session)
        zweite = await _lauf(seed, db_session)
        assert (zweite.neu, zweite.aktualisiert, zweite.unveraendert) == (0, 0, 2)
        assert zweite.kanten_geaendert == 0

    async def test_handarbeit_wird_nicht_ueberschrieben(self, seed, db_session, testfach):
        """⚠️ Der Fall, für den es `seed_hash` gibt.

        Ohne ihn nähme jeder Lauf der Fachschaft ihre Arbeit weg — lautlos, denn
        niemand führt darüber Buch.
        """
        await _lauf(seed, db_session)
        knoten = await _knoten(db_session, "Fiktivum")
        knoten.content = "Von Hand überarbeitet."
        await db_session.flush()

        bilanz = await _lauf(seed, db_session)
        assert bilanz.uebersprungen == ["Fiktivum"]
        assert (await _knoten(db_session, "Fiktivum")).content == "Von Hand überarbeitet."

    async def test_ueberschreiben_erzwingt(self, seed, db_session, testfach):
        await _lauf(seed, db_session)
        knoten = await _knoten(db_session, "Fiktivum")
        knoten.content = "Von Hand überarbeitet."
        await db_session.flush()

        bilanz = await _lauf(seed, db_session, ueberschreiben=True)
        assert bilanz.aktualisiert == 1 and not bilanz.uebersprungen
        assert (await _knoten(db_session, "Fiktivum")).content.startswith("Ein Fiktivum")

    async def test_handkanten_ueberleben(self, seed, db_session, testfach):
        """Was im Verknüpfen-Dialog entstand, darf der Import nicht wegräumen.

        ⚠️ **Eine Seed-Kante muss vorher weg.** Der erste Entwurf legte nur die
        Handkante an und ließ den Seed nochmal laufen — und war grün, auch als der
        Seed testweise **alle** Kanten des Knotens löschte. Der Grund: Ohne Unterschied
        zwischen Soll und Ist rührt der Seed die Kanten gar nicht an, der Löschpfad lief
        also nie. Ein Wächter, der den geprüften Code nicht erreicht, bescheinigt nur
        sich selbst.
        """
        await _lauf(seed, db_session)
        begriff = await _knoten(db_session, "Fiktivum")
        stoff = await _knoten(db_session, "Teststoff")
        db_session.add(ContextEdge(
            from_node_id=begriff.id, to_node_id=stoff.id,
            relation="requires", metadata_={},
        ))
        # Eine Seed-Kante entfernen, damit Soll und Ist auseinandergehen und der
        # Löschpfad tatsächlich läuft.
        await db_session.execute(
            sa.delete(ContextEdge).where(
                ContextEdge.from_node_id == begriff.id,
                ContextEdge.relation == "references",
            )
        )
        await db_session.flush()

        bilanz = await _lauf(seed, db_session)
        assert bilanz.kanten_geaendert > 0, "Der Löschpfad lief nicht — Test wirkungslos"
        ueberlebt = (await db_session.execute(
            sa.select(sa.func.count()).select_from(ContextEdge).where(
                ContextEdge.from_node_id == begriff.id,
                ContextEdge.to_node_id == stoff.id,
                ContextEdge.relation == "requires",
            )
        )).scalar_one()
        assert ueberlebt == 1

    async def test_geaenderte_datei_verwirft_den_vektor(self, seed, db_session, testfach):
        """Ein Vektor zu altem Text ist schlimmer als keiner: Er sieht gültig aus.

        Nachgestellt wird eine **ältere Fassung** des Knotens: anderer Text, und
        `seed_hash` passend dazu — so, wie ihn ein früherer Lauf hinterlassen hätte.
        Nur `seed_hash` zu verstellen genügt nicht: `stand_hash` lässt die
        Seed-Schlüssel bewusst außen vor, der Knoten gälte also weiter als aktuell.
        """
        await _lauf(seed, db_session)
        knoten = await _knoten(db_session, "Fiktivum")
        # Die Spaltenbreite steht in der Migration, nicht in `settings`: Die
        # Testdatenbank kann eine ältere Breite führen als die Vorgabe.
        breite = (await db_session.execute(sa.text(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = "
            "'context_nodes'::regclass AND attname = 'embedding'"
        ))).scalar_one()
        knoten.embedding = [0.1] * breite
        knoten.content = "Der Stand von gestern."
        aliase = (await db_session.execute(
            sa.select(NodeAlias.alias)
            .where(NodeAlias.node_id == knoten.id).order_by(NodeAlias.id)
        )).scalars().all()
        knoten.metadata_ = {
            **knoten.metadata_,
            "seed_hash": seed.stand_hash(
                knoten.title, knoten.content, dict(knoten.metadata_), list(aliase)
            ),
        }
        await db_session.flush()

        bilanz = await _lauf(seed, db_session)
        assert bilanz.aktualisiert == 1 and not bilanz.uebersprungen
        assert bilanz.neu_einzubetten == 1
        frisch = await _knoten(db_session, "Fiktivum")
        assert frisch.embedding is None and frisch.content.startswith("Ein Fiktivum")


class TestFachOhneFachschaft:
    async def test_ohne_fachschaftsgruppe_wird_uebersprungen(self, seed, db_session):
        """Auf `school` auszuweichen wäre kein Notbehelf, sondern eine andere Zusage:
        Dann dürfte jede Lehrkraft den Eintrag ändern, nicht die Fachschaft."""
        db_session.add(Subject(
            slug=f"testfach-{uuid.uuid4().hex[:8]}", name="Testfach", fach_code="TF"
        ))
        await db_session.flush()

        bilanz = await _lauf(seed, db_session)
        assert bilanz.neu == 0
        assert any("keine Fachschaftsgruppe" in w for w in bilanz.warnungen)

    async def test_unbekanntes_fach_wird_gemeldet(self, seed, db_session):
        bilanz = await _lauf(seed, db_session)
        assert bilanz.neu == 0
        assert any("unbekannt" in w for w in bilanz.warnungen)
