"""Dieselbe Slug-Regel in Python und in SQL (Paket 10, AP2).

`app.context.fachbegriffe_import.leite_id_ab` baut die Kennung eines Knotens beim
Import; Alembic `0079` baut sie **nochmal**, in SQL, um den Bestand aus Paket 9
nachzurüsten. Zwei Umsetzungen derselben Regel — dieselbe Familie wie die
Relationsliste (`test_relationen_einheitlich.py`) und die Scope-Rangfolge.

⚠️ **Ein Auseinanderlaufen knallt nicht, es wirkt leise.** Die Migration schriebe
`ch-saure-base` (ohne die `ä`-Regel), der nächste Import suchte nach
`ch-saeure-base`, fände nichts, fiele auf `seed_quelle` zurück und überschriebe die
Kennung. Kein Fehler, keine Warnung — nur eine Migration, die nichts bewirkt hat, und
niemand merkt es, bis jemand eine Datei umbenennt.

Geprüft wird die SQL-Regel **in Postgres**, nicht nachgebaut: `lower()`, `replace()`
und `regexp_replace()` sind Verhalten der Datenbank, kein Python.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.context.fachbegriffe_import import leite_id_ab
from app.db.models import ContextNode, Subject

pytestmark = pytest.mark.asyncio

#: Dateinamen aus dem echten Pilot — jeder steht für eine Eigenart, an der die beiden
#: Regeln auseinanderlaufen könnten: Klammern, Umlaut, Bindestrich, Leerzeichen,
#: Ziffern, Kleinschreibung am Anfang.
NAMEN = [
    "Oxidation (Sauerstoffaufnahme)",
    "Redoxreaktion (Elektronenübergang)",
    "Säure-Base-Reaktion",
    "Stöchiometrie",
    "GHS03 Flamme über einem Kreis",
    "zwischenmolekulare Wechselwirkungen",
    "heterogenes Gemisch",
    "Wasserstoffbrücken",
    "Straße",          # ß → ss, das einzige Zeichen, das zu zweien wird
    "Übung",           # Umlaut am Wortanfang
    "A  B",            # zwei Leerzeichen → ein Bindestrich
    "--Rand--",        # Bindestriche am Rand fallen weg
]


@pytest.fixture(scope="module")
def migration():
    """Die Migration über den Dateipfad laden — `alembic/versions/` ist kein Paket."""
    pfad = (
        Path(__file__).resolve().parents[2]
        / "alembic" / "versions" / "0079_fachbegriff_kennung.py"
    )
    spec = importlib.util.spec_from_file_location("m0079", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.mark.parametrize("name", NAMEN)
async def test_sql_und_python_bauen_dieselbe_kennung(db_session, migration, name):
    ausdruck = migration.kennung_sql(":fach", ":datei")
    aus_sql = (await db_session.execute(
        sa.text(f"SELECT {ausdruck}"), {"fach": "CH", "datei": name}
    )).scalar_one()
    assert aus_sql == leite_id_ab("CH", name), name


async def test_beide_geben_bei_reinen_sonderzeichen_nichts_her(db_session, migration):
    """Die Migration lässt solche Zeilen liegen (`<> ''` in der Bedingung), der Import
    verlangt ein `id:`. Beide tun dasselbe: keine Kennung erfinden."""
    ausdruck = migration.slug_sql(":datei")
    aus_sql = (await db_session.execute(
        sa.text(f"SELECT {ausdruck}"), {"datei": "Δ …"}
    )).scalar_one()
    assert aus_sql == ""
    assert leite_id_ab("CH", "Δ …") == ""


class TestDieMigrationSelbst:
    """Nicht nur die Regel, sondern die Anweisung: Trifft sie die richtigen Zeilen?

    ⚠️ Eine Migration, die nur beim Hochziehen der Datenbank mitläuft, ist ungeprüft.
    Hier läuft ihr `UPDATE` gegen echte Zeilen — samt der Fälle, die sie **nicht**
    anfassen darf.
    """

    async def _fach(self, db_session) -> Subject:
        fach = Subject(
            slug=f"migfach-{uuid.uuid4().hex[:8]}", name="Migfach", fach_code="MF"
        )
        db_session.add(fach)
        await db_session.flush()
        return fach

    async def _knoten(self, db_session, fach, **kwargs) -> ContextNode:
        felder = {
            "category": "knowledge", "content_type": "begriff", "content": "Text.",
            "subject_id": fach.id, "status": "active",
            "read_scope": "school", "write_scope": "school",
        }
        knoten = ContextNode(**{**felder, **kwargs})
        db_session.add(knoten)
        await db_session.flush()
        return knoten

    async def test_bestandsknoten_bekommt_die_kennung(self, db_session, migration):
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Säure-Base-Reaktion",
            metadata_={"seed_quelle": "Säure-Base-Reaktion", "seed_hash": "abc"},
        )
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.refresh(knoten)
        assert knoten.metadata_["seed_id"] == "mf-saeure-base-reaktion"
        assert knoten.metadata_["seed_hash"] == "abc", "der Rest bleibt stehen"

    async def test_vorhandene_kennung_bleibt(self, db_session, migration):
        """Wer schon eine hat, hat sie aus der Datei — die Migration überstimmt sie nicht."""
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Alpha",
            metadata_={"seed_quelle": "Alpha", "seed_id": "mf-eigene"},
        )
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.refresh(knoten)
        assert knoten.metadata_["seed_id"] == "mf-eigene"

    async def test_knoten_ohne_herkunft_bleibt_unberuehrt(self, db_session, migration):
        """Ein im Editor angelegter Begriff stammt nicht aus einem Import."""
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Von Hand", metadata_={"genus": "der"}
        )
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.refresh(knoten)
        assert "seed_id" not in knoten.metadata_

    async def test_fremder_knotentyp_bleibt_unberuehrt(self, db_session, migration):
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Ein Kapitel", content_type="kapitel",
            metadata_={"seed_quelle": "Ein Kapitel"},
        )
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.refresh(knoten)
        assert "seed_id" not in knoten.metadata_

    async def test_unslugbarer_dateiname_bleibt_ohne_kennung(self, db_session, migration):
        """Lieber keine als eine erfundene — der Import verlangt dann ein `id:`."""
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Δ", metadata_={"seed_quelle": "Δ"}
        )
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.refresh(knoten)
        assert "seed_id" not in knoten.metadata_

    async def test_der_aenderungsstempel_bleibt_stehen(self, db_session, migration):
        """Eine nachgetragene Kennung ist keine Bearbeitung. Rohes SQL geht an
        SQLAlchemys `onupdate` vorbei — das ist hier die Zusage, nicht der Zufall."""
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Alpha", metadata_={"seed_quelle": "Alpha"}
        )
        vorher = knoten.updated_at
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.refresh(knoten)
        assert knoten.metadata_["seed_id"] == "mf-alpha"
        assert knoten.updated_at == vorher

    async def test_die_rueckrolle_nimmt_sie_wieder_weg(self, db_session, migration):
        fach = await self._fach(db_session)
        knoten = await self._knoten(
            db_session, fach, title="Alpha", metadata_={"seed_quelle": "Alpha"}
        )
        await db_session.execute(sa.text(migration.upgrade_sql()))
        await db_session.execute(sa.text(migration.downgrade_sql()))
        await db_session.refresh(knoten)
        assert "seed_id" not in knoten.metadata_
        assert knoten.metadata_["seed_quelle"] == "Alpha", "die Herkunft bleibt"
