"""Titel und Jahrgangsband eines Curriculums ändern (`PATCH /context/curricula/{id}`).

Warum als Integrationstest: Die Änderung des Bandes zieht drei Dinge nach — die Metadaten,
die strukturellen Spalten `min_grade`/`max_grade` und die `import_key`s des ganzen Baums.
Ein Mock könnte belegen, dass ein UPDATE abgesetzt wurde, nicht aber, dass danach alles
zusammenpasst. Erfordert TEST_DATABASE_URL.
"""

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.context.router import update_curriculum_meta, update_node
from app.context.schemas import (
    ContextNodeUpdate,
    CurriculumDraftConfirmed,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
    CurriculumMetaUpdate,
)
from app.context.service import import_curriculum_from_draft
from app.db.models import ContextNode
from fastapi import HTTPException

FACHPLAN = "BP_2016_MA_META_UPDATE"


def _user(*rollen, sub="lehrkraft-pseudo"):
    return JwtPayload(
        sub=sub, roles=list(rollen), role=rollen[0], grade=None,
        exp=9999999999, iat=0, jti=str(uuid.uuid4()),
    )


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def curriculum_id(db: AsyncSession):
    """Ein Curriculum mit einem Kapitel und einer Lernsequenz — Band „5"."""
    result = await db.execute(
        sa.text(
            "INSERT INTO subjects (slug, name, fach_code) "
            "VALUES ('mathematik', 'Mathematik', 'MA') "
            "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id"
        )
    )
    result.fetchone()

    db.add(
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="fachplan",
            title="BP 2016 Mathematik", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school",
            metadata_={"fachplan_id": FACHPLAN},
        )
    )
    await db.flush()

    draft = CurriculumDraftConfirmed(
        schule="Test-Schule", fach_code="MA", fach="Mathematik", schulart="G8",
        jahrgangsstufe="5", fachplan_id=FACHPLAN, bp_version="2016",
        kapitel=[
            CurriculumDraftKapitel(
                titel="Kapitel A", reihenfolge=1, std="10",
                lernsequenzen=[
                    CurriculumDraftLernsequenz(
                        bp_titel="Sequenz 1", reihenfolge=1, std="5",
                        eintraege=[
                            CurriculumDraftEntry(
                                ik=[], pk=[], konkretisierung="K", hinweise="", material="",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    cid, _ = await import_curriculum_from_draft(db, draft, "lehrkraft-pseudo")
    await db.flush()
    return cid


async def _schluessel(db: AsyncSession) -> set[str]:
    rows = await db.execute(
        sa.select(ContextNode.metadata_["import_key"].astext).where(
            ContextNode.content_type.in_(["curriculum", "kapitel", "lernsequenz"]),
            ContextNode.metadata_["import_key"].astext.like(f"{FACHPLAN}%"),
        )
    )
    return {r[0] for r in rows.all()}


# ── Titel ────────────────────────────────────────────────────────────────────


async def test_titel_wird_geaendert(db, curriculum_id):
    await update_curriculum_meta(
        curriculum_id, CurriculumMetaUpdate(title="Schulcurriculum Mathematik 5"),
        db=db, user=_user("admin", "teacher"),
    )
    node = await db.get(ContextNode, curriculum_id)
    assert node.title == "Schulcurriculum Mathematik 5"


async def test_titel_aendern_laesst_das_band_unberuehrt(db, curriculum_id):
    """`exclude_unset` — wer nur den Titel schickt, verstellt das Band nicht."""
    vorher = await _schluessel(db)
    await update_curriculum_meta(
        curriculum_id, CurriculumMetaUpdate(title="Neuer Titel"),
        db=db, user=_user("admin", "teacher"),
    )
    node = await db.get(ContextNode, curriculum_id)
    assert node.metadata_["jahrgangsstufe"] == "5"
    assert (node.min_grade, node.max_grade) == (5, 5)
    assert await _schluessel(db) == vorher


# ── Jahrgangsband ────────────────────────────────────────────────────────────


async def test_band_setzt_auch_die_strukturspalten(db, curriculum_id):
    """Das Band ist nicht nur Text: `min_grade`/`max_grade` steuern die Editionsauflösung."""
    await update_curriculum_meta(
        curriculum_id, CurriculumMetaUpdate(jahrgangsstufe="7/8"),
        db=db, user=_user("admin", "teacher"),
    )
    node = await db.get(ContextNode, curriculum_id)
    assert node.metadata_["jahrgangsstufe"] == "7/8"
    assert (node.min_grade, node.max_grade) == (7, 8)


async def test_band_erhaelt_die_uebrigen_metadaten(db, curriculum_id):
    """Die eigentliche Falle: `update_node` ersetzt `metadata_` als Ganzes.

    Wer hier ein neues Dict zuwiese, löschte fach_code, fachplan_id, schulart — und
    bp_version. Der Schaden fiele erst beim nächsten Export oder Relink auf.
    """
    await update_curriculum_meta(
        curriculum_id, CurriculumMetaUpdate(jahrgangsstufe="9"),
        db=db, user=_user("admin", "teacher"),
    )
    meta = (await db.get(ContextNode, curriculum_id)).metadata_
    assert meta["fach_code"] == "MA"
    assert meta["fachplan_id"] == FACHPLAN
    assert meta["schulart"] == "G8"
    assert meta["bp_version"] == "2016"


async def test_band_zieht_die_import_keys_des_ganzen_baums_nach(db, curriculum_id):
    """Sonst kollidiert ein später angelegtes Curriculum des alten Bandes mit diesem."""
    assert await _schluessel(db) == {
        f"{FACHPLAN}_5",
        f"{FACHPLAN}_5_kapitel_1",
        f"{FACHPLAN}_5_kapitel_1_ls_1",
    }

    await update_curriculum_meta(
        curriculum_id, CurriculumMetaUpdate(jahrgangsstufe="7/8"),
        db=db, user=_user("admin", "teacher"),
    )

    assert await _schluessel(db) == {
        f"{FACHPLAN}_7/8",
        f"{FACHPLAN}_7/8_kapitel_1",
        f"{FACHPLAN}_7/8_kapitel_1_ls_1",
    }


async def test_band_in_der_mitte_des_schluessels(db):
    """Das Format, das die **Oberfläche** erzeugt (`POST /curricula/new`).

    Dort lautet der Schlüssel `new_{pseudonym}_{fach}_{band}_{bp_version}` — das Band steht
    in der Mitte, nicht am Ende. Eine erste Fassung rekonstruierte den Präfix aus
    `fachplan_id` und ließ genau diese Curricula stillschweigend unverändert; an der
    Dev-Datenbank fiel auf, dass das der häufigere Fall ist.
    """
    node = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="curriculum",
        title="CH Kl. 8", status="active", owner_pseudonym="lehrkraft-pseudo",
        read_scope="school", write_scope="school", min_grade=8, max_grade=8,
        metadata_={
            "import_key": "new_abc123_CH_8_2016",
            "jahrgangsstufe": "8", "bp_version": "2016", "fach_code": "CH",
        },
    )
    db.add(node)
    await db.flush()

    await update_curriculum_meta(
        node.id, CurriculumMetaUpdate(jahrgangsstufe="9"),
        db=db, user=_user("admin", "teacher"),
    )

    aktualisiert = await db.get(ContextNode, node.id)
    assert aktualisiert.metadata_["import_key"] == "new_abc123_CH_9_2016"
    assert aktualisiert.metadata_["bp_version"] == "2016"
    assert (aktualisiert.min_grade, aktualisiert.max_grade) == (9, 9)


async def test_unbekanntes_schluesselformat_bleibt_unangetastet(db, caplog):
    """Enthält der Schlüssel das Band nicht als Segment, wird er nicht geraten.

    Ein halb umgeschriebener Schlüssel wäre schlimmer als ein veralteter: Er zeigt auf
    nichts und niemand erkennt mehr, woher er stammte.

    Geprüft wird **auch die Warnung**. Dass der Schlüssel unverändert bleibt, ergäbe sich
    schon aus der Segment-Ersetzung von selbst — der Wächter existiert für den Hinweis an
    den Betrieb, dass hier ein Schlüssel zurückbleibt, der nicht mehr zum Band passt.
    Ohne diese Zusicherung wäre der Wächter ungetestet und ließe sich folgenlos entfernen.
    """
    caplog.set_level("WARNING", logger="app.context.router")
    node = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="curriculum",
        title="Sonderfall", status="active", owner_pseudonym="lehrkraft-pseudo",
        read_scope="school", write_scope="school",
        metadata_={"import_key": "voellig-anderes-format", "jahrgangsstufe": "8"},
    )
    db.add(node)
    await db.flush()

    await update_curriculum_meta(
        node.id, CurriculumMetaUpdate(jahrgangsstufe="9"),
        db=db, user=_user("admin", "teacher"),
    )

    aktualisiert = await db.get(ContextNode, node.id)
    assert aktualisiert.metadata_["import_key"] == "voellig-anderes-format"
    # Band und Strukturspalten werden trotzdem gesetzt — nur der Schlüssel bleibt.
    assert aktualisiert.metadata_["jahrgangsstufe"] == "9"
    assert (aktualisiert.min_grade, aktualisiert.max_grade) == (9, 9)
    assert any(
        "nicht umgeschrieben" in r.getMessage() for r in caplog.records
    ), "Der Betrieb erfährt nichts von dem zurückgebliebenen Schlüssel"


async def test_fremde_curricula_bleiben_unberuehrt(db, curriculum_id):
    """Gegenprobe zur Schlüsselpflege — ein zu weit gefasster Präfixvergleich träfe
    Nachbarn. `_` ist in SQL-LIKE ein Platzhalter, und `fachplan_id` steckt voller
    Unterstriche; deshalb wird in Python verglichen, nicht per LIKE."""
    fremd = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="curriculum",
        title="Fremdes Curriculum", status="active", owner_pseudonym="x",
        read_scope="school", write_scope="school",
        metadata_={"import_key": f"{FACHPLAN}X_5", "fachplan_id": f"{FACHPLAN}X"},
    )
    db.add(fremd)
    await db.flush()

    await update_curriculum_meta(
        curriculum_id, CurriculumMetaUpdate(jahrgangsstufe="7/8"),
        db=db, user=_user("admin", "teacher"),
    )

    assert (await db.get(ContextNode, fremd.id)).metadata_["import_key"] == f"{FACHPLAN}X_5"


# ── bp_version bleibt unveränderlich ─────────────────────────────────────────


async def test_schema_kennt_die_bp_version_gar_nicht():
    """Der engste mögliche Schutz: Das Feld existiert im Schema nicht.

    Ein mitgeschicktes `bp_version` wird von Pydantic verworfen, statt durchzurutschen.
    """
    assert set(CurriculumMetaUpdate.model_fields) == {"title", "jahrgangsstufe"}


async def test_generischer_knoten_endpunkt_weist_editionswechsel_ab(db, curriculum_id):
    """Die Lücke, die dieser Änderung vorausging.

    `PATCH /context/nodes/{id}` schreibt `metadata_` als Ganzes — darüber ließ sich die
    Edition eines Curriculums umstellen, ohne dass ein einziger Verweis geprüft wurde.
    """
    node = await db.get(ContextNode, curriculum_id)
    with pytest.raises(HTTPException) as fehler:
        await update_node(
            curriculum_id,
            ContextNodeUpdate(metadata={**node.metadata_, "bp_version": "2016.V3"}),
            db=db, user=_user("admin", "teacher"),
        )
    assert fehler.value.status_code == 422
    assert "relink" in fehler.value.detail.lower()


async def test_generischer_endpunkt_erlaubt_andere_metadaten_weiterhin(db, curriculum_id):
    """Gegenprobe — die Sperre darf nicht jede Metadatenänderung blockieren."""
    node = await db.get(ContextNode, curriculum_id)
    await update_node(
        curriculum_id,
        ContextNodeUpdate(metadata={**node.metadata_, "schule": "Andere Schule"}),
        db=db, user=_user("admin", "teacher"),
    )
    assert (await db.get(ContextNode, curriculum_id)).metadata_["schule"] == "Andere Schule"


# ── Rechte ───────────────────────────────────────────────────────────────────


async def test_fremde_lehrkraft_darf_nicht(db, curriculum_id):
    """Schreibrecht hat nur die Fachschaft — oder ein Admin."""
    with pytest.raises(HTTPException) as fehler:
        await update_curriculum_meta(
            curriculum_id, CurriculumMetaUpdate(title="Übernommen"),
            db=db, user=_user("teacher", sub="fremde-lehrkraft"),
        )
    assert fehler.value.status_code == 403


async def test_schuelerin_darf_nicht(db, curriculum_id):
    with pytest.raises(HTTPException) as fehler:
        await update_curriculum_meta(
            curriculum_id, CurriculumMetaUpdate(title="Übernommen"),
            db=db, user=_user("student"),
        )
    assert fehler.value.status_code == 403
