"""UP-6 Schritt 2: Tests für den Plan-Operationen-Executor."""

from uuid import uuid4

import psycopg2
import pytest

from app.db.models import ContextNode, LessonSlot
from app.planning import operations as ops_mod
from app.planning.operations import (
    CancelLesson, MoveContent, SetCategory, SetTopic, StrikePhase, TransferPhases,
    apply_operations, parse_operations,
)
from datetime import date, timedelta

GROUP_ID = 202
D0 = date(2026, 9, 1)


@pytest.fixture(scope="module")
def seed_ops_group(db_url, run_migrations):
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO subjects (id, slug, name, sort_order) "
                    "VALUES (202, 'op-test', 'OP Test', 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (202, 'OP 8a', 'op-8a', 'teaching_group', 202) "
                    "ON CONFLICT (id) DO NOTHING")
    conn.commit()
    conn.close()


def _slot(d, *, kategorie="unterricht", thema=None, ue_id=None, stunde_id=None, pinned=False,
          periods=1, halbjahr=1):
    return LessonSlot(
        id=uuid4(), group_id=GROUP_ID, date=d, halbjahr=halbjahr, periods=periods, start_period=3,
        kategorie=kategorie, thema=thema, ue_node_id=ue_id, stunde_node_id=stunde_id, pinned=pinned,
    )


def _stunde(title, phasen=None, refs_offen=None):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde", title=title,
        metadata_={"phasen": phasen or [], "refs_offen": refs_offen or []},
        read_scope="group", read_scope_group_id=GROUP_ID, status="active",
    )


async def _apply(db_session, ops, summary="t"):
    """apply_operations mit commit→flush, damit das Rollback-Fixture greift."""
    async def _commit_as_flush():
        await db_session.flush()
    import unittest.mock as m
    with m.patch.object(db_session, "commit", new=_commit_as_flush):
        return await apply_operations(db_session, GROUP_ID, ops, summary=summary)


def test_parse_operations_discriminated_union():
    ops = parse_operations([
        {"op": "set_topic", "slot_id": str(uuid4()), "thema": "X"},
        {"op": "strike_phase", "lesson_id": str(uuid4()), "phase_id": "p1"},
    ])
    assert isinstance(ops[0], SetTopic) and isinstance(ops[1], StrikePhase)


@pytest.mark.asyncio
async def test_apply_set_topic_and_category(db_session, seed_ops_group):
    s = _slot(D0)
    db_session.add(s)
    await db_session.flush()
    res = await _apply(db_session, [
        SetTopic(op="set_topic", slot_id=s.id, thema="Neues Thema"),
        SetCategory(op="set_category", slot_id=s.id, kategorie="puffer"),
    ])
    assert res.errors == [] and res.applied == 2
    assert s.thema == "Neues Thema" and s.kategorie == "puffer"
    assert res.snapshot_id is not None


@pytest.mark.asyncio
async def test_apply_move_content(db_session, seed_ops_group):
    ue = ContextNode(id=uuid4(), category="artifact", content_type="unterrichtseinheit",
                     title="UE", metadata_={}, read_scope="group",
                     read_scope_group_id=GROUP_ID, status="active")
    db_session.add(ue)
    src = _slot(D0, thema="Inhalt", ue_id=ue.id)
    dst = _slot(D0 + timedelta(days=1))
    db_session.add_all([src, dst])
    await db_session.flush()

    res = await _apply(db_session, [
        MoveContent(op="move_content", from_slot_id=src.id, to_slot_id=dst.id)
    ])
    assert res.errors == []
    assert dst.thema == "Inhalt" and dst.ue_node_id == ue.id
    assert src.thema is None and src.ue_node_id is None


@pytest.mark.asyncio
async def test_apply_atomicity_pinned_rejected(db_session, seed_ops_group):
    pin = _slot(D0, thema="Fix", pinned=True)
    other = _slot(D0 + timedelta(days=1), thema="A")
    db_session.add_all([pin, other])
    await db_session.flush()

    # Zweite Op ist invalid (gepinnt) → gar nichts wird angewendet.
    res = await _apply(db_session, [
        SetTopic(op="set_topic", slot_id=other.id, thema="Geändert"),
        SetTopic(op="set_topic", slot_id=pin.id, thema="Verboten"),
    ])
    assert res.applied == 0 and res.snapshot_id is None
    assert any("gepinnt" in e for e in res.errors)
    assert other.thema == "A"  # nicht verändert


@pytest.mark.asyncio
async def test_apply_move_to_occupied_rejected(db_session, seed_ops_group):
    a = _slot(D0, thema="A")
    b = _slot(D0 + timedelta(days=1), thema="B")
    db_session.add_all([a, b])
    await db_session.flush()
    res = await _apply(db_session, [
        MoveContent(op="move_content", from_slot_id=a.id, to_slot_id=b.id)
    ])
    assert res.applied == 0
    assert any("belegt" in e for e in res.errors)


@pytest.mark.asyncio
async def test_apply_transfer_phases(db_session, seed_ops_group):
    R = str(uuid4())
    src = _stunde("Quelle", phasen=[
        {"id": "p1", "name": "Übertrag", "prio": "uebung", "dauer_min": 15, "status": "offen"},
        {"id": "p2", "name": "Bleibt", "prio": "kern", "dauer_min": 10, "status": "erledigt"},
    ], refs_offen=[R])
    dst = _stunde("Ziel", phasen=[{"id": "q1", "name": "Vorhanden", "prio": "kern", "dauer_min": 20, "status": "geplant"}])
    db_session.add_all([src, dst])
    await db_session.flush()

    res = await _apply(db_session, [
        TransferPhases(op="transfer_phases", from_lesson_id=src.id, to_lesson_id=dst.id, phase_ids=["p1"])
    ])
    assert res.errors == []
    dst_phasen = dst.metadata_["phasen"]
    assert dst_phasen[0]["name"] == "Übertrag"          # an den Anfang
    assert dst_phasen[0]["uebertrag_von"] == str(src.id)
    assert dst_phasen[0]["status"] == "geplant"
    assert [p["id"] for p in src.metadata_["phasen"]] == ["p2"]  # aus Quelle entfernt
    assert any(r["node_id"] == R for r in dst.metadata_["refs"])  # refs_offen mitgeführt


# ── Halber Umzug: set_topic statt move_content (Paket 5, AP6) ────────────────


@pytest.mark.asyncio
async def test_set_topic_meldet_zurueckgebliebenen_inhalt(db_session, seed_ops_group):
    """⚠️ **Der Fall, der das nötig machte** (beobachtet 24.09.2026).

    Nach „Stunden verschieben" stand am Zieltermin nur das Thema — Unterrichtseinheit und
    Stundenentwurf blieben am ausgefallenen Termin. Das Modell hatte `set_topic` gewählt,
    wo `move_content` gemeint war. Verboten war es nicht, und niemand merkte es: Die
    Lehrkraft sah die Stunde am neuen Termin stehen und konnte sie dort nicht bearbeiten.

    Eine bessere Werkzeugbeschreibung macht das unwahrscheinlicher, nicht unmöglich.
    Dieser Hinweis sorgt dafür, dass das Ergebnis nicht **unbemerkt** bleibt — er ist
    kein Fehler, die Operation bleibt angewandt.
    """
    stunde = _stunde("Titration")
    db_session.add(stunde)
    ausgefallen = _slot(D0, kategorie="ausfall", thema="Titration", stunde_id=stunde.id)
    ziel = _slot(D0 + timedelta(days=7))
    db_session.add_all([ausgefallen, ziel])
    await db_session.flush()

    res = await _apply(db_session, [SetTopic(op="set_topic", slot_id=ziel.id,
                                             thema="Titration")])
    assert res.errors == []
    assert res.applied == 1
    assert len(res.hinweise) == 1
    assert "move_content" in res.hinweise[0]
    assert "Titration" in res.hinweise[0]


@pytest.mark.asyncio
async def test_move_content_erzeugt_keinen_hinweis(db_session, seed_ops_group):
    """Die Gegenprobe: derselbe Umzug, richtig gemacht."""
    stunde = _stunde("Titration")
    db_session.add(stunde)
    ausgefallen = _slot(D0, kategorie="ausfall", thema="Titration", stunde_id=stunde.id)
    ziel = _slot(D0 + timedelta(days=7))
    db_session.add_all([ausgefallen, ziel])
    await db_session.flush()

    res = await _apply(db_session, [MoveContent(op="move_content",
                                                from_slot_id=ausgefallen.id,
                                                to_slot_id=ziel.id)])
    assert res.errors == []
    assert res.hinweise == []


@pytest.mark.asyncio
async def test_ein_gewoehnlicher_ausfall_mit_inhalt_meldet_nichts(
    db_session, seed_ops_group
):
    """⚠️ **Eng geschnitten mit Absicht.**

    „Ein ausgefallener Termin trägt noch Inhalt" ist der **Normalfall** direkt nach einem
    Ausfall — die Zuordnung bleibt für die Nachvollziehbarkeit erhalten. Ein Hinweis
    darauf wäre Rauschen und entwertete die Fälle, die zählen.
    """
    stunde = _stunde("Titration")
    db_session.add(stunde)
    s = _slot(D0, thema="Titration", stunde_id=stunde.id)
    db_session.add(s)
    await db_session.flush()

    res = await _apply(db_session, [CancelLesson(op="cancel_lesson", slot_id=s.id)])
    assert res.errors == []
    assert res.hinweise == []


@pytest.mark.asyncio
async def test_set_topic_auf_anderes_thema_meldet_nichts(db_session, seed_ops_group):
    """Nur dasselbe Thema zählt — sonst hat niemand etwas verschoben."""
    stunde = _stunde("Titration")
    db_session.add(stunde)
    ausgefallen = _slot(D0, kategorie="ausfall", thema="Titration", stunde_id=stunde.id)
    ziel = _slot(D0 + timedelta(days=7))
    db_session.add_all([ausgefallen, ziel])
    await db_session.flush()

    res = await _apply(db_session, [SetTopic(op="set_topic", slot_id=ziel.id,
                                             thema="Ganz anderes Thema")])
    assert res.hinweise == []


@pytest.mark.asyncio
@pytest.mark.parametrize("art", ["streichen", "kuerzen"])
async def test_phasenoperation_kommt_in_der_datenbank_an(async_engine, seed_ops_group, art):
    """Bis 0.13 meldeten Streichen und Kürzen `applied=1` und hinterließen nichts.

    ⚠️ Gelesen wird in einer **frischen** Sitzung. Die übrigen Tests hier prüfen das
    Objekt im Speicher derselben Sitzung — dort war die Änderung (bis zum nächsten
    Neuladen) zu sehen, und genau deshalb blieb der Fehler unbemerkt.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.planning.operations import ShortenPhase

    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    nid = uuid4()
    async with fabrik() as db:
        db.add(ContextNode(
            id=nid, category="artifact", content_type="unterrichtsstunde", title="Persistenz",
            metadata_={"phasen": [{"id": "p1", "name": "Sicherung", "dauer_min": 20, "prio": "kern"}]},
            read_scope="group_teachers", write_scope="group_teachers",
            read_scope_group_id=GROUP_ID, write_scope_group_id=GROUP_ID, status="active",
        ))
        await db.commit()

    op = (StrikePhase(op="strike_phase", lesson_id=nid, phase_id="p1") if art == "streichen"
          else ShortenPhase(op="shorten_phase", lesson_id=nid, phase_id="p1", dauer_min=5))
    async with fabrik() as db:
        ergebnis = await apply_operations(db, GROUP_ID, [op], summary=art)
    assert ergebnis.applied == 1 and not ergebnis.errors

    async with fabrik() as db:
        phase = (await db.get(ContextNode, nid)).metadata_["phasen"][0]
    if art == "streichen":
        assert phase["status"] == "gestrichen" and phase["kuerzung"] is True
    else:
        assert phase["dauer_min"] == 5 and phase["kuerzung"] is True


# ── cancel_lesson (0.15, Päckchen A Schritt 8) ───────────────────────────────


@pytest.mark.asyncio
async def test_cancel_lesson_traegt_den_ausfall_ein(db_session, seed_ops_group):
    """Wie der Ausfall aus der Planungsansicht: Kategorie, Herkunft und Vorher in einem Zug
    (`ausfall.setze_kategorie`); der Inhalt bleibt am Termin."""
    s = _slot(D0, kategorie="pruefung", thema="Titration")
    db_session.add(s)
    await db_session.flush()

    res = await _apply(db_session, parse_operations([{"op": "cancel_lesson", "slot_id": str(s.id)}]))
    assert res.errors == [] and res.applied == 1
    assert (s.kategorie, s.ausfall_herkunft, s.ausfall_vorher) == ("ausfall", "assistent", "pruefung")
    assert s.thema == "Titration"


@pytest.mark.asyncio
async def test_ausfall_und_verschieben_in_einem_stapel(db_session, seed_ops_group):
    """Der Fall aus der Messung: „fällt aus, der Stoff soll weiter"."""
    src, dst = _slot(D0, thema="Titration"), _slot(D0 + timedelta(days=3))
    db_session.add_all([src, dst])
    await db_session.flush()

    res = await _apply(db_session, [
        CancelLesson(op="cancel_lesson", slot_id=src.id),
        MoveContent(op="move_content", from_slot_id=src.id, to_slot_id=dst.id),
    ])
    assert res.errors == []
    assert src.kategorie == "ausfall" and src.thema is None
    assert dst.thema == "Titration" and dst.kategorie == "unterricht"


@pytest.mark.asyncio
async def test_set_category_nimmt_keinen_ausfall_an(db_session, seed_ops_group):
    """Ein Weg, nicht zwei — sonst laufen die beiden auseinander (Todo, 24.09.2026)."""
    s = _slot(D0)
    db_session.add(s)
    await db_session.flush()

    res = await _apply(db_session, [SetCategory(op="set_category", slot_id=s.id, kategorie="ausfall")])
    assert res.applied == 0 and s.kategorie == "unterricht"
    assert any("cancel_lesson" in f for f in res.errors)


@pytest.mark.asyncio
async def test_unterricht_hebt_den_ausfall_wieder_auf(db_session, seed_ops_group):
    s = _slot(D0)
    db_session.add(s)
    await db_session.flush()
    await _apply(db_session, [CancelLesson(op="cancel_lesson", slot_id=s.id)])

    res = await _apply(db_session, [SetCategory(op="set_category", slot_id=s.id, kategorie="unterricht")])
    assert res.errors == []
    assert (s.kategorie, s.ausfall_herkunft, s.ausfall_vorher) == ("unterricht", None, None)


# ── cancel_lesson mit nachruecken (Jan, 11.10.2026, nach Messung 2) ──────────


def _tage(*n):
    return [D0 + timedelta(days=i) for i in n]


async def _reihe(db_session, *termine):
    """Termine in Reihenfolge; ein String ist ein Thema, None ein leerer Unterrichtstermin,
    ein Dict die Angaben für `_slot`."""
    slots = []
    for tag, t in zip(_tage(*range(len(termine))), termine):
        angaben = t if isinstance(t, dict) else {"thema": t}
        slots.append(_slot(tag, **angaben))
    db_session.add_all(slots)
    await db_session.flush()
    return slots


async def _nachruecken(db_session, quelle):
    return await _apply(db_session, [CancelLesson(op="cancel_lesson", slot_id=quelle.id, nachruecken=True)])


@pytest.mark.asyncio
async def test_nachruecken_bis_zum_ersten_freien_termin(db_session, seed_ops_group):
    a, b, c, frei, d = await _reihe(db_session, "A", "B", "C", None, "D")
    res = await _nachruecken(db_session, a)
    assert res.errors == []
    assert (a.kategorie, a.thema) == ("ausfall", None)
    assert [b.thema, c.thema, frei.thema, d.thema] == ["A", "B", "C", "D"]
    assert any("Nachgerückt" in h and "3 Termin" in h for h in res.hinweise)


@pytest.mark.asyncio
async def test_nachruecken_nimmt_einheit_und_entwurf_mit(db_session, seed_ops_group):
    stunde = _stunde("A")
    db_session.add(stunde)
    await db_session.flush()
    a, frei = await _reihe(db_session, {"thema": "A", "stunde_id": stunde.id}, None)
    await _nachruecken(db_session, a)
    assert (frei.thema, frei.stunde_node_id) == ("A", stunde.id) and a.stunde_node_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fixpunkt", [{"kategorie": "pruefung"}, {"thema": "Fix", "pinned": True}])
async def test_nachruecken_nie_ueber_einen_fixpunkt(db_session, seed_ops_group, fixpunkt):
    """Stoff rutscht nicht hinter eine Klassenarbeit — dann wird gar nichts angewandt."""
    a, b, fix, frei = await _reihe(db_session, "A", "B", fixpunkt, None)
    res = await _nachruecken(db_session, a)
    assert res.applied == 0 and any("Fixpunkt" in f for f in res.errors)
    assert (a.kategorie, a.thema, b.thema, frei.thema) == ("unterricht", "A", "B", None)


@pytest.mark.asyncio
async def test_nachruecken_nicht_ins_naechste_halbjahr(db_session, seed_ops_group):
    a, b, frei = await _reihe(db_session, "A", "B", {"thema": None, "halbjahr": 2})
    res = await _nachruecken(db_session, a)
    assert res.applied == 0 and any("Halbjahresende" in f for f in res.errors)


@pytest.mark.asyncio
async def test_nachruecken_ueberspringt_ausfall_vertretung_und_belegten_puffer(db_session, seed_ops_group):
    a, aus, vert, puffer, b, frei = await _reihe(
        db_session, "A", {"kategorie": "ausfall"}, {"kategorie": "vertretung"},
        {"kategorie": "puffer", "thema": "Wiederholung"}, "B", None)
    res = await _nachruecken(db_session, a)
    assert res.errors == []
    assert [b.thema, frei.thema] == ["A", "B"]
    assert (aus.thema, vert.thema, puffer.thema, puffer.kategorie) == (None, None, "Wiederholung", "puffer")


@pytest.mark.asyncio
async def test_ein_leerer_puffer_wird_verbraucht(db_session, seed_ops_group):
    a, b, puffer = await _reihe(db_session, "A", "B", {"kategorie": "puffer"})
    res = await _nachruecken(db_session, a)
    assert res.errors == []
    assert (puffer.thema, puffer.kategorie) == ("B", "unterricht")
    assert any("Puffer" in h and "verbraucht" in h for h in res.hinweise)


@pytest.mark.asyncio
async def test_entwurf_in_einem_termin_anderer_laenge_wird_markiert(db_session, seed_ops_group):
    """Verschiebe-Assistent: Eine 90′-Planung passt nicht stillschweigend in einen Einzelslot.
    Ein bloßes Thema schon — es wird nicht markiert."""
    stunde = _stunde("A")
    db_session.add(stunde)
    await db_session.flush()
    a, einzel, doppel, frei = await _reihe(
        db_session, {"thema": "A", "stunde_id": stunde.id, "periods": 2}, "B",
        {"thema": "C", "periods": 2}, {"thema": None, "periods": 1})
    res = await _nachruecken(db_session, a)
    assert res.errors == []
    assert einzel.stunde_node_id == stunde.id and einzel.anpassung_noetig
    assert doppel.thema == "B" and not doppel.anpassung_noetig
    assert frei.thema == "C" and not frei.anpassung_noetig
    assert any("Anpassung nötig" in h for h in res.hinweise)


@pytest.mark.asyncio
async def test_quelle_ohne_inhalt_rueckt_nichts(db_session, seed_ops_group):
    a, b, frei = await _reihe(db_session, None, "B", None)
    res = await _nachruecken(db_session, a)
    assert res.errors == [] and a.kategorie == "ausfall"
    assert (b.thema, frei.thema) == ("B", None)
    assert not any("Nachgerückt" in h for h in res.hinweise)


@pytest.mark.asyncio
async def test_ohne_nachruecken_bleibt_alles_stehen(db_session, seed_ops_group):
    a, b, frei = await _reihe(db_session, "A", "B", None)
    res = await _apply(db_session, [CancelLesson(op="cancel_lesson", slot_id=a.id)])
    assert res.errors == [] and (a.kategorie, a.thema, b.thema, frei.thema) == ("ausfall", "A", "B", None)


# ── Rückgängig nach einem Ausfall (0.15) ─────────────────────────────────────


async def _rueckgaengig(db_session, snapshot_id):
    """restore_snapshot mit commit→flush, wie `_apply`."""
    import unittest.mock as m
    from types import SimpleNamespace
    from uuid import UUID

    from app.planning.snapshots import restore_snapshot

    async def _commit_as_flush():
        await db_session.flush()
    with m.patch.object(db_session, "commit", new=_commit_as_flush), \
         m.patch.object(db_session, "refresh", new=m.AsyncMock()):
        return await restore_snapshot(db_session, UUID(snapshot_id), SimpleNamespace(sub="t"))


@pytest.mark.asyncio
async def test_rueckgaengig_nach_ausfall_leert_die_herkunft(db_session, seed_ops_group):
    """Bis 0.15 stand der Termin danach auf `unterricht`, trug aber noch die Herkunft."""
    s = _slot(D0, kategorie="pruefung")
    db_session.add(s)
    await db_session.flush()
    res = await _apply(db_session, [CancelLesson(op="cancel_lesson", slot_id=s.id)])
    assert (s.kategorie, s.ausfall_herkunft) == ("ausfall", "assistent")

    await _rueckgaengig(db_session, res.snapshot_id)
    assert (s.kategorie, s.ausfall_herkunft, s.ausfall_vorher) == ("pruefung", None, None)


@pytest.mark.asyncio
async def test_rueckgaengig_bringt_den_ausfall_mit_herkunft_zurueck(db_session, seed_ops_group):
    """Umgekehrt: Ein wiederhergestellter Ausfall verlor seine Herkunft — und damit den
    Schutz vor dem Stundenplan-Abgleich."""
    s = _slot(D0)
    db_session.add(s)
    await db_session.flush()
    await _apply(db_session, [CancelLesson(op="cancel_lesson", slot_id=s.id)])
    res = await _apply(db_session, [SetCategory(op="set_category", slot_id=s.id, kategorie="unterricht")])
    assert s.ausfall_herkunft is None

    await _rueckgaengig(db_session, res.snapshot_id)
    assert (s.kategorie, s.ausfall_herkunft, s.ausfall_vorher) == ("ausfall", "assistent", "unterricht")


@pytest.mark.asyncio
async def test_aelterer_snapshot_ohne_herkunft(db_session, seed_ops_group):
    """Snapshots vor 0.15 kennen die Felder nicht — `setze_kategorie` hält sie zusammen."""
    from app.db.models import SlotPlanSnapshot

    raus, rein = _slot(D0, kategorie="ausfall"), _slot(D0 + timedelta(days=1))
    raus.ausfall_herkunft, raus.ausfall_vorher = "assistent", "unterricht"
    db_session.add_all([raus, rein])
    alt = SlotPlanSnapshot(group_id=GROUP_ID, reason="reflow", label="alt", payload={"slots": [
        {"slot_id": str(raus.id), "kategorie": "unterricht", "pinned": False},
        {"slot_id": str(rein.id), "kategorie": "ausfall", "pinned": False},
    ]})
    db_session.add(alt)
    await db_session.flush()

    await _rueckgaengig(db_session, str(alt.id))
    assert (raus.kategorie, raus.ausfall_herkunft, raus.ausfall_vorher) == ("unterricht", None, None)
    assert (rein.kategorie, rein.ausfall_herkunft, rein.ausfall_vorher) == ("ausfall", "eigen", "unterricht")
