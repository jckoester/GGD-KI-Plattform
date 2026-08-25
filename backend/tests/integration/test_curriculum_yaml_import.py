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
        metadata_={"nr": "3.1.1", "bp_version": BP_VERSION},
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
    """Die Meldung muss handlungsfähig machen, nicht nur „nicht gefunden" sagen.

    Frühere Fassungen nannten `fachplan_id` (ein Feld, das der Export nicht füllt) und
    fragten pauschal, ob der Bildungsplan importiert sei. Jetzt nennt sie, welche Edition
    **tatsächlich aktiv** ist — daraus ergibt sich der nächste Schritt von selbst.
    """
    with pytest.raises(ValueError) as fehler:
        await import_curriculum_from_draft(
            db, _draft(bp_id="GIBTESNICHT", bp_version="9999"), "system"
        )
    text = str(fehler.value)
    assert "CH" in text and "9999" in text
    assert BP_VERSION in text, "Die vorhandene, aktive Edition muss genannt werden"


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


async def test_archivierte_edition_wird_benannt(db, welt):
    """Der Fall aus dem ersten Produktiv-Export (24.08.2026).

    Die Zielinstanz hatte den Plan der gesuchten Edition sehr wohl — nur **archiviert**,
    weil danach eine andere importiert worden war. Die alte Meldung fragte pauschal „Ist
    der Bildungsplan importiert?" und schickte damit in die falsche Richtung.
    """
    db.add(
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="fachplan",
            title="Chemie (alte Edition)", status="archived", owner_pseudonym="system",
            read_scope="global", write_scope="school", subject_id=welt["subject_id"],
            metadata_={"bp_id": BP_ID + ".ALT", "bp_version": "2016"},
        )
    )
    await db.flush()

    with pytest.raises(ValueError) as fehler:
        await import_curriculum_from_draft(
            db, _draft(bp_id=None, bp_version="2016"), "system"
        )

    text = str(fehler.value)
    assert "archiviert" in text
    assert BP_VERSION in text, "Die aktive Edition muss genannt werden"


async def test_verweis_auf_fremden_knoten_bricht_den_import_nicht_ab(db, welt):
    """Ein einzelner Verweis machte das ganze Curriculum unimportierbar.

    Bleibt beim Export ein Token als rohe UUID stehen (Zielknoten ohne Code), zeigt es in
    der Zielinstanz ins Leere. Ungeprüft eingefügt brach der Fremdschlüssel — und riss
    den **gesamten** Import mit, statt nur diesen Verweis zu verlieren. Am echten
    Produktiv-Export aufgefallen.
    """
    fremd = uuid.uuid4()
    draft = _draft()
    draft.kapitel[0].lernsequenzen[0].eintraege[0].hinweise = (
        f"Siehe #[Physik](ik:{fremd}) und @[BNE](lp:{uuid.uuid4()})"
    )

    cid, stats = await import_curriculum_from_draft(db, draft, "system")

    assert cid is not None, "Der Import muss durchlaufen"
    assert any(str(fremd) in w for w in stats.warnings)
    assert all("übersprungen" in w for w in stats.warnings if str(fremd) in w)


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
            metadata_={"kompetenz_nr": "3.2.2.1(1)", "bp_version": BP_VERSION},
        ),
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="pk_kompetenz",
            title="2.2.5 Erkenntnisgewinnung", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school",
            metadata_={"kompetenz_nr": "2.2.5", "bp_version": BP_VERSION},
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


# ── Verwaiste Kapitel abräumen (Punkt 2) ─────────────────────────────────────


def _draft_mit_kapiteln(*titel) -> CurriculumDraftConfirmed:
    return _draft(kapitel=[
        CurriculumDraftKapitel(
            titel=t, reihenfolge=i + 1, std="5",
            lernsequenzen=[
                CurriculumDraftLernsequenz(
                    bp_titel=f"LS {t}", reihenfolge=1, std="5",
                    eintraege=[
                        CurriculumDraftEntry(
                            ik=[], pk=[], konkretisierung="k", hinweise="", material="",
                        )
                    ],
                )
            ],
        )
        for i, t in enumerate(titel)
    ])


async def _kapiteltitel(db, cid) -> list[str]:
    tree = await load_curriculum_tree(db, cid)
    return [k["title"] for k in tree["kapitel"]]


async def test_geloeschtes_kapitel_verschwindet_beim_reimport(db, welt):
    """Der Import legte an und aktualisierte, räumte aber nie ab.

    Ein aus dem YAML entferntes Kapitel überlebte damit jeden Re-Import und hing weiter
    am Curriculum — sichtbar im Baum, obwohl die Quelle es nicht mehr kennt.
    """
    cid, _ = await import_curriculum_from_draft(db, _draft_mit_kapiteln("A", "B"), "system")
    assert await _kapiteltitel(db, cid) == ["A", "B"]

    _, stats = await import_curriculum_from_draft(db, _draft_mit_kapiteln("A"), "system")

    assert await _kapiteltitel(db, cid) == ["A"]
    assert stats.archived_count >= 1


async def test_unveraenderter_reimport_archiviert_nichts(db, welt):
    """Gegenprobe — sonst räumte jeder Lauf etwas ab und die Zahl wäre wertlos."""
    cid, _ = await import_curriculum_from_draft(db, _draft_mit_kapiteln("A", "B"), "system")
    _, stats = await import_curriculum_from_draft(db, _draft_mit_kapiteln("A", "B"), "system")
    assert stats.archived_count == 0
    assert await _kapiteltitel(db, cid) == ["A", "B"]


async def test_fremdes_curriculum_bleibt_unberuehrt(db, welt):
    """Die eigentliche Gefahr der alten Fassung: Sie durchsuchte die **ganze** Tabelle.

    Jedes andere Curriculum der Instanz wäre bei jedem Import mit archiviert worden.
    """
    cid_8, _ = await import_curriculum_from_draft(db, _draft_mit_kapiteln("A", "B"), "system")
    fremd = _draft_mit_kapiteln("X", "Y")
    fremd.jahrgangsstufe = "9"
    cid_9, _ = await import_curriculum_from_draft(db, fremd, "system")

    # Import für Band 8 mit weniger Kapiteln — Band 9 darf das nicht spüren.
    await import_curriculum_from_draft(db, _draft_mit_kapiteln("A"), "system")

    assert await _kapiteltitel(db, cid_8) == ["A"]
    assert await _kapiteltitel(db, cid_9) == ["X", "Y"]


async def test_editor_kapitel_wird_nicht_abgeraeumt(db, welt):
    """Im Editor angelegte Kapitel tragen `temp_<uuid>` und gehören keinem Import.

    Ein YAML-Import darf die Handarbeit einer Lehrkraft nicht stillschweigend
    entfernen, nur weil das YAML sie nicht kennt.
    """
    from app.db.models import ContextEdge

    cid, _ = await import_curriculum_from_draft(db, _draft_mit_kapiteln("A"), "system")

    handarbeit = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="kapitel",
        title="Von Hand ergänzt", status="active", owner_pseudonym="lehrkraft",
        read_scope="school", write_scope="school",
        metadata_={"import_key": f"temp_{uuid.uuid4()}", "reihenfolge": 2},
    )
    db.add(handarbeit)
    await db.flush()
    db.add(ContextEdge(from_node_id=handarbeit.id, to_node_id=cid, relation="part_of"))
    await db.flush()

    await import_curriculum_from_draft(db, _draft_mit_kapiteln("A"), "system")

    assert (await db.get(ContextNode, handarbeit.id)).status == "active"
    assert "Von Hand ergänzt" in await _kapiteltitel(db, cid)


# ── Leitperspektiven und Cross-Fach-IK: Rundreise über Kürzel (Punkt 3) ──────


@pytest_asyncio.fixture
async def lp_welt(db, welt):
    """Eine Leitperspektive **ohne** `code` — genau wie echte Daten."""
    lp = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="leitperspektive",
        title="Prävention und Gesundheitsförderung", status="active",
        owner_pseudonym="system", read_scope="global", write_scope="school",
        metadata_={"bp_id": "BP2016BW_ALLG_LP_PG"},      # kein 'code'!
    )
    db.add(lp)
    await db.flush()
    return {**welt, "lp": lp}


async def test_lp_verweis_wird_portabel_exportiert(db, lp_welt):
    """Vorher blieb **jeder** LP-Verweis als UUID stehen — in einer anderen Instanz wertlos."""
    from app.context.curriculum_export import hinweise_uuid_to_code

    roh = f"Vgl. @[PG](lp:{lp_welt['lp'].id})"
    assert await hinweise_uuid_to_code(roh, db) == "Vgl. @[PG](lp:PG)"


async def test_cross_fach_ik_wird_portabel_exportiert(db, lp_welt):
    """Dieselbe Asymmetrie wie bei den Resolvern: der Export las nur `nr`.

    Cross-Fach-Verweise blieben dadurch UUIDs und tauchten beim Import als
    „Knoten gibt es nicht" wieder auf — die vier Warnungen beim ersten Produktiv-Import
    hatten genau diese Ursache.
    """
    from app.context.curriculum_export import hinweise_uuid_to_code

    ik = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="ik_kompetenz",
        title="CH 3.2.2.1(1)", status="active", owner_pseudonym="system",
        read_scope="global", write_scope="school", subject_id=lp_welt["subject_id"],
        metadata_={"kompetenz_nr": "3.2.2.1(1)", "bp_version": BP_VERSION},        # kein 'nr'!
    )
    db.add(ik)
    await db.flush()

    roh = f"Vgl. #[Chemie](ik:{ik.id})"
    assert await hinweise_uuid_to_code(roh, db) == "Vgl. #[Chemie](ik:CH:3.2.2.1(1))"


async def test_lp_kuerzel_wird_beim_import_wieder_aufgeloest(db, lp_welt):
    """Die Rückrichtung — sonst ist der portable Export nur die halbe Miete."""
    from app.context.service import resolve_leitperspektive_node

    for schreibweise in ("PG", "L PG", "(L) PG", "pg"):
        assert await resolve_leitperspektive_node(db, schreibweise) == lp_welt["lp"].id, schreibweise


async def test_import_verknuepft_lp_ueber_kuerzel(db, lp_welt):
    """Vollständige Rundreise: Kürzel im YAML → Kante im Graphen."""
    from app.db.models import ContextEdge

    draft = _draft()
    draft.kapitel[0].lernsequenzen[0].eintraege[0].hinweise = "Vgl. @[PG](lp:PG)"
    cid, stats = await import_curriculum_from_draft(db, draft, "system")

    kanten = (
        await db.execute(
            sa.select(sa.func.count()).select_from(ContextEdge).where(
                ContextEdge.to_node_id == lp_welt["lp"].id,
                ContextEdge.relation == "references",
            )
        )
    ).scalar_one()
    assert kanten == 1, f"LP-Kante fehlt; Warnungen: {stats.warnings}"


# ── Auflösung nach Fach und Fassung (Schritt 7) ─────────────────────────────


async def _kanten_ziele(db: AsyncSession, relation: str) -> list[ContextNode]:
    """Zielknoten aller Kanten dieser Art, die von Lernsequenzen ausgehen."""
    from app.db.models import ContextEdge

    ergebnis = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.to_node_id == ContextNode.id)
        .join(
            sa.orm.aliased(ContextNode, name="ls"),
            sa.text("ls.id = context_edges.from_node_id"),
        )
        .where(ContextEdge.relation == relation, sa.text("ls.content_type = 'lernsequenz'"))
    )
    return list(ergebnis.scalars().all())


@pytest.mark.asyncio
async def test_pk_kante_trifft_das_eigene_fach(db: AsyncSession, welt):
    """Prozessbezogene Kompetenzen sind **je Fach** von 2.1.1 an nummeriert.

    Der Fehler, den dieser Test festhält: Die Auflösung filterte gar nicht nach Fach.
    `2.1.1` gibt es in 24 Fächern; welches getroffen wurde, entschied die Reihenfolge in
    der Datenbank. Beim Wiederimport eines echten Mathematik-Curriculums landeten so
    **54 von 65 PK-Kanten in fremden Fächern** — Gemeinschaftskunde, Musik, Sport —
    ohne eine einzige Warnung.
    """
    fremd_id = (
        await db.execute(
            sa.text(
                "INSERT INTO subjects (slug, name, fach_code) "
                "VALUES ('musik', 'Musik', 'MUS') ON CONFLICT (slug) DO UPDATE "
                "SET fach_code = EXCLUDED.fach_code RETURNING id"
            )
        )
    ).fetchone()[0]

    # Dieselbe Nummer in zwei Fächern — das fremde zuerst, damit ein ungefilterter
    # Zugriff mit hoher Wahrscheinlichkeit danebengreift.
    for sid, titel in ((fremd_id, "MUS PK 2.1.1"), (welt["subject_id"], "CH PK 2.1.1")):
        db.add(
            ContextNode(
                id=uuid.uuid4(), category="knowledge", content_type="pk_kompetenz",
                title=titel, status="active", owner_pseudonym="system",
                read_scope="global", write_scope="school", subject_id=sid,
                metadata_={"kompetenz_nr": "2.1.1", "bp_version": BP_VERSION},
            )
        )
    await db.flush()

    entwurf = _draft()
    entwurf.kapitel[0].lernsequenzen[0].eintraege[0].pk = [{"id": "2.1.1"}]
    _, stats = await import_curriculum_from_draft(db, entwurf, "system")

    assert stats.warnings == []
    ziele = await _kanten_ziele(db, "develops")
    assert len(ziele) == 1
    assert ziele[0].subject_id == welt["subject_id"], (
        f"PK-Kante zeigt auf Fach {ziele[0].subject_id} statt auf Chemie"
    )


@pytest.mark.asyncio
async def test_ik_kante_trifft_die_eigene_fassung(db: AsyncSession, welt):
    """Während eines Editionswechsels sind mehrere Fassungen gleichzeitig aktiv.

    Bei Mathematik kommen 316 von 319 IK-Nummern in V2 *und* V3 vor. Ohne
    Fassungsfilter entscheidet die Reihenfolge in der Datenbank — ein Curriculum für
    Klasse 9 könnte stillschweigend an V3-Kompetenzen hängen.
    """
    ik_v3 = ContextNode(
        id=uuid.uuid4(), category="knowledge", content_type="ik_kompetenz",
        title="CH IK 3.1.1 (V3)", status="active", owner_pseudonym="system",
        read_scope="global", write_scope="school", subject_id=welt["subject_id"],
        metadata_={"nr": "3.1.1", "bp_version": "2016.V3"},
    )
    db.add_all([
        ik_v3,
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="fachplan",
            title="Gymnasium - Chemie (V3)", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school", subject_id=welt["subject_id"],
            metadata_={"bp_id": BP_ID + "_V3", "bp_version": "2016.V3"},
        ),
    ])
    await db.flush()

    # **Beide Richtungen**, sonst prüft der Test nur, ob die Datenbank zufällig die
    # richtige Zeile zuerst liefert: Die eine Richtung entspricht der Einfügereihenfolge,
    # die andere widerspricht ihr.
    for fassung, bp_id, erwartet in (
        (BP_VERSION, BP_ID, welt["ik"].id),
        ("2016.V3", BP_ID + "_V3", ik_v3.id),
    ):
        _, stats = await import_curriculum_from_draft(
            db, _draft(bp_version=fassung, bp_id=bp_id), "system"
        )
        assert stats.warnings == [], f"{fassung}: {stats.warnings}"
        treffer = {
            z.id
            for z in await _kanten_ziele(db, "references")
            if z.content_type == "ik_kompetenz" and z.metadata_["bp_version"] == fassung
        }
        assert treffer == {erwartet}, f"{fassung} traf {treffer}"


@pytest.mark.asyncio
async def test_fehlende_fassung_wird_gemeldet_statt_ersetzt(db: AsyncSession, welt):
    """Kein Rückfall auf eine andere Fassung — die Lücke soll sichtbar sein.

    Eine Auflösung aus der falschen Fassung wäre nicht zu bemerken; eine Warnung schon.
    """
    # Die neue Fassung ist da (Fachplan vorhanden), aber sie kennt die Nummer nicht:
    # der einzige V3-Knoten trägt eine andere.
    db.add_all([
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="fachplan",
            title="Gymnasium - Chemie (V3)", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school", subject_id=welt["subject_id"],
            metadata_={"bp_id": BP_ID + "_V3", "bp_version": "2016.V3"},
        ),
        ContextNode(
            id=uuid.uuid4(), category="knowledge", content_type="ik_kompetenz",
            title="CH IK 3.9.9 (V3)", status="active", owner_pseudonym="system",
            read_scope="global", write_scope="school", subject_id=welt["subject_id"],
            metadata_={"nr": "3.9.9", "bp_version": "2016.V3"},
        ),
    ])
    await db.flush()

    _, stats = await import_curriculum_from_draft(
        db, _draft(bp_version="2016.V3", bp_id=BP_ID + "_V3"), "system"
    )

    # `3.1.1` gibt es in V2, aber nicht in V3 — gemeldet, nicht ersatzweise aufgelöst.
    assert any("3.1.1" in w and "2016.V3" in w for w in stats.warnings), stats.warnings
    assert await _kanten_ziele(db, "references") == []
