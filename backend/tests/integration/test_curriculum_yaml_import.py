"""Wiederimport exportierter Curricula (YAML) — für promptLab und Dev-Instanzen.

Die vorhandenen Round-Trip-Tests in `test_curriculum_export.py` arbeiten mit
Fachplan-Knoten, die ein `fachplan_id` in den Metadaten tragen. **Echte Daten tun das
nicht**: Vom Scraper importierte Fachpläne haben `bp_id` und `bp_version`, aber kein
`fachplan_id` — geprüft an allen 28 Knoten der Dev-Instanz. Ein Export schrieb deshalb
`fachplan_id: null`, und der Wiederimport scheiterte mit „Bildungsplan-Import fehlt?",
obwohl der Plan vorhanden war.

Diese Datei prüft deshalb den Weg, den echte Exporte gehen: **ohne `fachplan_id`**.
Erfordert TEST_DATABASE_URL.
"""

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.curriculum_export import build_curriculum_export_dict
from app.context.schemas import (
    CurriculumDraftConfirmed,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
)
from app.context.service import (
    import_curriculum_from_draft,
    load_curriculum_tree,
    resolve_fachplan,
)
from app.db.models import ContextNode

BP_ID = "BP2016BW_ALLG_GYM_CH_YAMLTEST.V2"
BP_VERSION = "2016.V2"


def _lade_konverter():
    """`convert_yaml_to_draft` aus `backend/scripts/` holen.

    Über den Dateipfad statt `from scripts...`: `backend/scripts/` und `scripts/` im
    Repo-Wurzelverzeichnis heißen beide „scripts"; ein Paketimport griffe womöglich das
    falsche (siehe CLAUDE.md, „scripts/-Paketkonflikt").
    """
    import importlib.util
    from pathlib import Path

    pfad = Path(__file__).resolve().parents[2] / "scripts" / "import_curriculum.py"
    spec = importlib.util.spec_from_file_location("_import_curriculum", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul.convert_yaml_to_draft


@pytest_asyncio.fixture
async def db(db_session, monkeypatch):
    async def _flush():
        await db_session.flush()

    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


@pytest_asyncio.fixture
async def welt(db: AsyncSession):
    """Fach, Fachplan **ohne `fachplan_id`** (wie echte Daten) und eine IK-Kompetenz."""
    subject_id = (
        await db.execute(
            sa.text(
                "INSERT INTO subjects (slug, name, fach_code) "
                "VALUES ('chemie', 'Chemie', 'CH') "
                "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code "
                "RETURNING id"
            )
        )
    ).fetchone()[0]

    fachplan = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="fachplan",
        title="Gymnasium - Chemie", status="active", owner_pseudonym="system",
        read_scope="global", write_scope="school", subject_id=subject_id,
        metadata_={"bp_id": BP_ID, "bp_version": BP_VERSION},   # kein fachplan_id!
    )
    ik = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="ik_kompetenz",
        title="CH IK 3.1.1", status="active", owner_pseudonym="system",
        read_scope="global", write_scope="school", subject_id=subject_id,
        metadata_={"nr": "3.1.1"},
    )
    db.add_all([fachplan, ik])
    await db.flush()
    return {"subject_id": subject_id, "fachplan": fachplan, "ik": ik}


def _draft(**abweichungen) -> CurriculumDraftConfirmed:
    grund = dict(
        schule="Test-Schule", fach_code="CH", fach="Chemie", schulart="Gymnasium",
        jahrgangsstufe="8", fachplan_id=None, bp_id=BP_ID, bp_version=BP_VERSION,
        kapitel=[
            CurriculumDraftKapitel(
                titel="Stoffe", reihenfolge=1, std="10",
                lernsequenzen=[
                    CurriculumDraftLernsequenz(
                        bp_titel="Aggregatzustände", reihenfolge=1, std="5",
                        eintraege=[
                            CurriculumDraftEntry(
                                ik=[{"nr": "3.1.1", "partiell": False}], pk=[],
                                konkretisierung="Teilchenmodell", hinweise="", material="",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    grund.update(abweichungen)
    return CurriculumDraftConfirmed(**grund)


# ── Fachplan-Auflösung ───────────────────────────────────────────────────────


async def test_fachplan_wird_ueber_bp_id_gefunden(db, welt):
    node = await resolve_fachplan(db, bp_id=BP_ID)
    assert node is not None and node.id == welt["fachplan"].id


async def test_fachplan_wird_ueber_fach_und_edition_gefunden(db, welt):
    """Rückfallebene für Exporte, die vor dem `bp_id`-Feld entstanden sind."""
    node = await resolve_fachplan(
        db, subject_id=welt["subject_id"], bp_version=BP_VERSION
    )
    assert node is not None and node.id == welt["fachplan"].id


async def test_mehrdeutige_edition_liefert_keinen_treffer(db, welt):
    """Zwei Fachpläne für dasselbe Fach und dieselbe Edition — dann lieber gar keiner.

    Den falschen zu wählen hieße, ein Curriculum an den falschen Plan zu hängen; das
    fiele erst auf, wenn die Kompetenzverweise nicht mehr passen.
    """
    db.add(
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="fachplan",
            title="Chemie (Doppelgänger)", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school", subject_id=welt["subject_id"],
            metadata_={"bp_id": BP_ID + "_ZWEIT", "bp_version": BP_VERSION},
        )
    )
    await db.flush()
    assert await resolve_fachplan(
        db, subject_id=welt["subject_id"], bp_version=BP_VERSION
    ) is None


async def test_ohne_fachplan_klare_meldung(db, welt):
    """Die alte Meldung nannte `fachplan_id` — ein Feld, das der Export gar nicht füllt."""
    with pytest.raises(ValueError) as fehler:
        await import_curriculum_from_draft(
            db, _draft(bp_id="GIBTESNICHT", bp_version="9999"), "system"
        )
    text = str(fehler.value)
    assert "CH" in text and "9999" in text
    assert "importiert" in text


# ── Import ohne fachplan_id ──────────────────────────────────────────────────


async def test_import_ohne_fachplan_id(db, welt):
    """Der Fall, der vorher scheiterte."""
    cid, stats = await import_curriculum_from_draft(db, _draft(), "system")
    node = await db.get(ContextNode, cid)
    assert node.title == "Chemie Kl. 8"
    assert stats.warnings == []


async def test_import_key_traegt_die_bp_id(db, welt):
    """Ohne `fachplan_id` hieße der Schlüssel sonst schlicht `_8` — für **jedes** Fach
    derselbe. Der zweite Import überschriebe dann ein fremdes Curriculum."""
    cid, _ = await import_curriculum_from_draft(db, _draft(), "system")
    node = await db.get(ContextNode, cid)
    assert node.metadata_["import_key"] == f"{BP_ID}_8"


async def test_zweiter_import_erzeugt_kein_zweites_curriculum(db, welt):
    """Idempotenz — sonst wächst bei jedem Einspielen eine Dublette heran."""
    cid1, _ = await import_curriculum_from_draft(db, _draft(), "system")
    cid2, _ = await import_curriculum_from_draft(db, _draft(), "system")
    assert cid1 == cid2

    anzahl = (
        await db.execute(
            sa.select(sa.func.count()).select_from(ContextNode).where(
                ContextNode.content_type == "curriculum",
                ContextNode.metadata_["import_key"].astext == f"{BP_ID}_8",
            )
        )
    ).scalar_one()
    assert anzahl == 1


async def test_verschiedene_baender_bleiben_getrennt(db, welt):
    cid8, _ = await import_curriculum_from_draft(db, _draft(), "system")
    cid9, _ = await import_curriculum_from_draft(db, _draft(jahrgangsstufe="9"), "system")
    assert cid8 != cid9


# ── Fehlende Kompetenzen: melden, nicht abbrechen ────────────────────────────


async def test_unaufloesbare_kompetenz_bricht_nicht_ab(db, welt):
    """Der Kern des Anwendungsfalls.

    In einer Dev- oder promptLab-Instanz ist der Bildungsplan oft unvollständig.
    Abbrechen wäre unbrauchbar — das Curriculum entsteht, der Verweis fehlt und **wird
    gemeldet**. Stilles Verwerfen wäre die schlechteste der drei Möglichkeiten.
    """
    draft = _draft()
    draft.kapitel[0].lernsequenzen[0].eintraege[0].ik = [
        {"nr": "9.9.9", "partiell": False}
    ]

    cid, stats = await import_curriculum_from_draft(db, draft, "system")

    assert cid is not None
    assert any("9.9.9" in w for w in stats.warnings)


# ── Round-Trip über echtes YAML ──────────────────────────────────────────────


async def test_roundtrip_ueber_yaml_datei(db, welt):
    """Export → YAML-Text → Konverter des CLI → Import. Der komplette Weg."""
    cid, _ = await import_curriculum_from_draft(db, _draft(), "system")
    tree = await load_curriculum_tree(db, cid)
    export = await build_curriculum_export_dict(db, tree)

    # Der Export muss die bp_id mitführen — sonst ist er nicht übertragbar.
    assert export["bp_id"] == BP_ID

    # Wirklich durch YAML schicken: Zahlen/None verhalten sich dort anders als im Dict.
    daten = yaml.safe_load(yaml.safe_dump(export, allow_unicode=True, sort_keys=False))
    draft = _lade_konverter()(daten)

    cid2, stats = await import_curriculum_from_draft(db, draft, "system")
    assert cid2 == cid
    assert stats.warnings == []


async def test_kompetenzen_werden_ueber_kompetenz_nr_gefunden(db, welt):
    """Der teuerste der gefundenen Fehler.

    Der Baum liest die Nummer aus `kompetenz_nr`, die Auflösung suchte sie in `nr` bzw.
    `pk_id`. Beim Re-Import **in dieselbe Instanz** verlor ein echtes Curriculum dadurch
    69 Kompetenzverweise — die Knoten waren da, nur unter dem anderen Feldnamen.
    Diese Fixture bildet echte Daten nach: nur `kompetenz_nr`, kein `nr`/`pk_id`.
    """
    from app.context.service import resolve_ik_node, resolve_pk_node

    db.add_all([
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="ik_kompetenz",
            title="3.2.2.1(1) Metalle", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school", subject_id=welt["subject_id"],
            metadata_={"kompetenz_nr": "3.2.2.1(1)"},
        ),
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="pk_kompetenz",
            title="2.2.5 Erkenntnisgewinnung", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school",
            metadata_={"kompetenz_nr": "2.2.5"},
        ),
    ])
    await db.flush()

    assert await resolve_ik_node(db, welt["subject_id"], "3.2.2.1(1)") is not None
    assert await resolve_pk_node(db, "2.2.5") is not None


async def test_altes_feld_nr_funktioniert_weiterhin(db, welt):
    """Gegenprobe — Bestands- und Testdaten mit `nr`/`pk_id` dürfen nicht ausfallen."""
    from app.context.service import resolve_ik_node

    # `welt["ik"]` trägt bewusst `nr`, nicht `kompetenz_nr`.
    assert await resolve_ik_node(db, welt["subject_id"], "3.1.1") is not None


async def test_konverter_akzeptiert_fehlendes_fachplan_id(db):
    """Der CLI-Konverter darf `fachplan_id` nicht mehr als Pflichtfeld verlangen —
    die eigene Exportfunktion füllt es nicht."""
    konverter = _lade_konverter()
    draft = konverter(
        {
            "schule": "", "fach_code": "CH", "schulart": "Gymnasium",
            "jahrgangsstufe": "8", "bp_version": BP_VERSION, "bp_id": BP_ID,
            "kapitel": [
                {"titel": "K", "reihenfolge": 1, "lernsequenzen": []},
            ],
        }
    )
    assert draft.fachplan_id is None
    assert draft.bp_id == BP_ID
