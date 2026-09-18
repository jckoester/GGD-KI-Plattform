"""„In Werkstatt öffnen" / „Als Baustein speichern" legen kein zweites Dokument an.

Bis 18.09.2026 trug `create_document` bewusst **kein** `origin_ref` — mit der Begründung,
Dokumente seien veränderbar und damit nicht inhalts-adressierbar. Das stimmt, trifft aber
den Schlüssel nicht: `message:<id>` benennt die **Herkunft**, und die bleibt über jede
Bearbeitung stabil. Seit „Als Baustein speichern" (AP8) ist die Lücke ein echter Fehler —
ein zweiter Klick erzeugte einen Zweitknoten statt einer neuen Fassung.

Gegen echtes Postgres, nicht gegen Mocks: Die Zusage hängt am partiellen Unique-Index
`uq_artifacts_owner_origin` (Alembic 0041), und den kann ein Mock nicht widerlegen.
"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.artifacts import store
from app.db.models import Artifact
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

ICH = "doc-idem-ich"
ANDERE = "doc-idem-andere"
BETEILIGTE = [ICH, ANDERE, TEACHER1_PSEUDO]


@pytest.fixture(autouse=True)
def ablage(monkeypatch, tmp_path):
    """Artefakt-Dateien in ein Wegwerf-Verzeichnis, nicht in die echte Ablage."""
    monkeypatch.setattr(store.settings, "artifact_storage_dir", str(tmp_path))
    return tmp_path


def _factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(async_engine):
    """Hinterlässt keine Artefakte in der Test-DB.

    Nötig, weil diese Tests **festschreiben** müssen: `save_artifact` committet selbst,
    und die Idempotenz hängt genau an dem Index, der dabei greift.
    """
    yield
    async with _factory(async_engine)() as s:
        await s.execute(delete(Artifact).where(Artifact.owner_pseudonym.in_(BETEILIGTE)))
        await s.commit()


@pytest_asyncio.fixture
async def sitzung(async_engine):
    """Session, die committen darf.

    Die `db_session` der conftest trägt hier nicht: Sie hält den Test in einem offenen
    `session.begin()`, und der erste `commit()` im Store bricht ihn ab
    („Can't operate on closed transaction").
    """
    async with _factory(async_engine)() as s:
        yield s


async def _dokument(db, owner: str, *, message_id, titel="Entwurf", text="# Hallo"):
    return await store.create_document(
        db,
        owner_pseudonym=owner,
        roles=["teacher"],
        grade=None,
        title=titel,
        markdown=text,
        origin_ref=store.document_origin_ref(message_id),
    )


async def _anzahl(db, owner: str) -> int:
    res = await db.execute(
        select(func.count()).select_from(Artifact).where(Artifact.owner_pseudonym == owner)
    )
    return int(res.scalar_one())


async def test_zweiter_klick_liefert_dasselbe_dokument(sitzung):
    nachricht = uuid4()
    erst = await _dokument(sitzung, ICH, message_id=nachricht)
    zweit = await _dokument(sitzung, ICH, message_id=nachricht)

    assert zweit.id == erst.id
    assert await _anzahl(sitzung, ICH) == 1


async def test_bearbeitetes_dokument_wird_nicht_ueberschrieben(sitzung):
    """Der zweite Klick führt in die eigene Fassung zurück, nicht zum Rohtext."""
    nachricht = uuid4()
    doc = await _dokument(sitzung, ICH, message_id=nachricht, text="# Rohfassung")
    await store.update_document(
        sitzung, record=doc, roles=["teacher"], grade=None,
        title="Mein Arbeitsblatt", markdown="# Rohfassung\n\nMeine Ergänzung",
    )

    wieder = await _dokument(sitzung, ICH, message_id=nachricht, text="# Rohfassung")

    assert wieder.id == doc.id
    assert wieder.source == "# Rohfassung\n\nMeine Ergänzung"
    assert wieder.title == "Mein Arbeitsblatt"


async def test_leeres_dokument_bleibt_jedes_mal_ein_neues(sitzung):
    """Ohne Nachricht kein Schlüssel: Zweimal „Neues Dokument" sind zwei Dokumente."""
    erst = await _dokument(sitzung, ICH, message_id=None, titel="Neues Dokument", text="")
    zweit = await _dokument(sitzung, ICH, message_id=None, titel="Neues Dokument", text="")

    assert zweit.id != erst.id
    assert await _anzahl(sitzung, ICH) == 2


async def test_der_schluessel_gilt_je_eigentuemerin(sitzung):
    """Zwei Lehrkräfte am selben Gruppenchat bekommen je ein eigenes Dokument."""
    nachricht = uuid4()
    meins = await _dokument(sitzung, ICH, message_id=nachricht)
    ihres = await _dokument(sitzung, ANDERE, message_id=nachricht)

    assert meins.id != ihres.id
    assert await _anzahl(sitzung, ICH) == 1
    assert await _anzahl(sitzung, ANDERE) == 1


async def test_endpunkt_meldet_beim_zweiten_mal_created_false(test_client, auth_headers, ablage):
    """`created` ist die Auskunft, an der die Oberfläche „neu" von „schon da" trennt."""
    nachricht = str(uuid4())
    rumpf = {"title": "Aus dem Chat", "markdown": "# Text", "message_id": nachricht}

    erst = await test_client.post("/artifacts/document", json=rumpf, headers=auth_headers)
    zweit = await test_client.post("/artifacts/document", json=rumpf, headers=auth_headers)

    assert erst.status_code == 200, erst.text
    assert zweit.status_code == 200, zweit.text
    assert erst.json()["created"] is True
    assert zweit.json()["created"] is False
    assert zweit.json()["id"] == erst.json()["id"]


async def test_endpunkt_ohne_nachricht_meldet_jedes_mal_created(test_client, auth_headers, ablage):
    rumpf = {"title": "Neues Dokument", "markdown": ""}

    erst = await test_client.post("/artifacts/document", json=rumpf, headers=auth_headers)
    zweit = await test_client.post("/artifacts/document", json=rumpf, headers=auth_headers)

    assert erst.json()["created"] is True
    assert zweit.json()["created"] is True
    assert zweit.json()["id"] != erst.json()["id"]
