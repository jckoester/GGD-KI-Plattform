"""Eingeführte Begriffe einer Unterrichtsgruppe (0.20, Päckchen AC, Schritt 3)."""
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.db.models import ContextNode, NodeEngagement
from app.planning.eingefuehrt import LAUT_PLAN, NACHBEREITET, eingefuehrte_begriffe
from tests.integration.test_student_context import (  # noqa: F401 — Fixture
    GROUP_ID,
    TODAY,
    _slot,
    _ue,
    seed_sc_group,
)


def _knoten(titel, *, art="begriff", scope="school", gruppe=None, status="active"):
    return ContextNode(
        id=uuid4(), category="concept" if art == "begriff" else "knowledge", content_type=art,
        title=titel, metadata_={}, read_scope=scope, read_scope_group_id=gruppe, status=status,
    )


def _entwurf(*knoten):
    return ContextNode(
        id=uuid4(), category="artifact", content_type="unterrichtsstunde", title="Entwurf",
        metadata_={"refs": [{"node_id": str(k.id), "typ": "concept"} for k in knoten]},
        read_scope="group_teachers", read_scope_group_id=GROUP_ID, status="active",
    )


def _eingetragen(knoten, slot):
    return NodeEngagement(group_id=GROUP_ID, node_id=knoten.id, relation="introduced",
                          source="lesson_plan", metadata_={"slot_id": str(slot.id)})


@pytest.mark.asyncio
async def test_nachbereitet_und_laut_plan_juengste_zuerst(db_session, seed_sc_group):
    alt, neu = _ue("Stoffe"), _ue("Bindung")
    stoffe, gemisch, en = _knoten("Stoffe"), _knoten("Gemisch"), _knoten("Elektronegativität")
    nachbereitet, offen = _entwurf(stoffe, gemisch), _entwurf(en)
    db_session.add_all([alt, neu, stoffe, gemisch, en, nachbereitet, offen])
    s_alt = _slot(date(2026, 2, 16), stunde_id=nachbereitet.id, ue_id=alt.id, nachbereitet=True)
    s_neu = _slot(date(2026, 3, 13), stunde_id=offen.id, ue_id=neu.id)
    db_session.add_all([s_alt, s_neu])
    await db_session.flush()
    db_session.add_all([_eingetragen(stoffe, s_alt), _eingetragen(gemisch, s_alt)])
    await db_session.flush()

    liste = await eingefuehrte_begriffe(db_session, GROUP_ID, heute=TODAY)

    assert [(e.titel, e.herkunft, e.datum, e.ue_node_id) for e in liste] == [
        ("Elektronegativität", LAUT_PLAN, date(2026, 3, 13), neu.id),
        ("Gemisch", NACHBEREITET, date(2026, 2, 16), alt.id),
        ("Stoffe", NACHBEREITET, date(2026, 2, 16), alt.id),
    ]


@pytest.mark.asyncio
async def test_nur_vergangene_stunden_und_kein_ausfall(db_session, seed_sc_group):
    heute, morgen, ausfall = _knoten("Heute"), _knoten("Morgen"), _knoten("Ausgefallen")
    e1, e2, e3 = _entwurf(heute), _entwurf(morgen), _entwurf(ausfall)
    db_session.add_all([heute, morgen, ausfall, e1, e2, e3])
    db_session.add_all([
        _slot(TODAY, stunde_id=e1.id),
        _slot(date(2026, 3, 16), stunde_id=e2.id),
        _slot(date(2026, 3, 12), stunde_id=e3.id, kategorie="ausfall"),
    ])
    await db_session.flush()

    assert await eingefuehrte_begriffe(db_session, GROUP_ID, heute=TODAY) == []


@pytest.mark.asyncio
async def test_nur_begriffe_nur_aktive_nur_fuer_alle_lesbare(db_session, seed_sc_group):
    """Gegenprobe zu F3/F6: Kompetenz, Methode, Archiviertes, Privates und Lehrkraft-Knoten
    stehen in `refs` bzw. als `introduced` — eingeführte Begriffe sind sie nicht."""
    ja = _knoten("Begriff")
    steckbrief = _knoten("Kochsalz", art="stoffsteckbrief")
    nein = [
        _knoten("3.2.1.1(8) Lösungen untersuchen", art="ik_kompetenz"),
        _knoten("Gruppenpuzzle", art="methode"),
        _knoten("Archiviert", status="archived"),
        _knoten("Privat", scope="private"),
        _knoten("Nur Lehrkräfte", scope="group_teachers", gruppe=GROUP_ID),
    ]
    geplant, nachbereitet = _entwurf(ja, *nein), _entwurf()
    db_session.add_all([ja, steckbrief, *nein, geplant, nachbereitet])
    slot = _slot(date(2026, 3, 12), stunde_id=nachbereitet.id, nachbereitet=True)
    db_session.add_all([slot, _slot(date(2026, 3, 13), stunde_id=geplant.id)])
    await db_session.flush()
    db_session.add_all([_eingetragen(k, slot) for k in (steckbrief, *nein)])
    await db_session.flush()

    titel = {e.titel for e in await eingefuehrte_begriffe(db_session, GROUP_ID, heute=TODAY)}
    assert titel == {"Begriff", "Kochsalz"}


@pytest.mark.asyncio
async def test_nachbereitet_gewinnt_juengstes_datum_zaehlt(db_session, seed_sc_group):
    """Derselbe Begriff erst nachbereitet, später wieder geplant: nachbereitet, mit dem
    jüngeren Datum."""
    stoffe = _knoten("Stoffe")
    frueher, spaeter = _entwurf(stoffe), _entwurf(stoffe)
    db_session.add_all([stoffe, frueher, spaeter])
    s1 = _slot(date(2026, 2, 16), stunde_id=frueher.id, nachbereitet=True)
    db_session.add_all([s1, _slot(date(2026, 3, 13), stunde_id=spaeter.id)])
    await db_session.flush()
    db_session.add(_eingetragen(stoffe, s1))
    await db_session.flush()

    (e,) = await eingefuehrte_begriffe(db_session, GROUP_ID, heute=TODAY)
    assert (e.herkunft, e.datum) == (NACHBEREITET, date(2026, 3, 13))


@pytest.mark.asyncio
async def test_deckel(db_session, seed_sc_group):
    viele = [_knoten(f"B{i:02d}") for i in range(5)]
    entwurf = _entwurf(*viele)
    db_session.add_all([*viele, entwurf, _slot(date(2026, 3, 12), stunde_id=entwurf.id)])
    await db_session.flush()

    assert len(await eingefuehrte_begriffe(db_session, GROUP_ID, heute=TODAY, deckel=3)) == 3


@pytest.mark.asyncio
async def test_als_offen_nachbereitet_zaehlt_nicht(db_session, seed_sc_group):
    """Die Nachbereitung sagt „nicht drangekommen" (`refs_offen`) — dann darf der Begriff nicht
    über die `refs` derselben Stunde als „laut Plan" zurückkommen."""
    offen = _knoten("Nicht drangekommen")
    entwurf = _entwurf(offen)
    entwurf.metadata_["refs_offen"] = [str(offen.id)]
    db_session.add_all([offen, entwurf, _slot(date(2026, 3, 12), stunde_id=entwurf.id, nachbereitet=True)])
    await db_session.flush()

    assert await eingefuehrte_begriffe(db_session, GROUP_ID, heute=TODAY) == []


@pytest.mark.asyncio
async def test_kontext_der_konversation_nimmt_die_eingefuehrten_mit(db_session, seed_sc_group):
    """Verdrahtung (Schritt 5): Die Konversation mit Gruppe reicht deren Begriffe an die
    Vorab-Suche; ein Begriff im Graubereich steht dann als Baustein mit Grund `gruppe` da, ohne
    Gruppe nur als Angebot."""
    from unittest.mock import AsyncMock, patch

    from tests.integration.test_vorab_suche_db import FRAGE, _fuer_distanz

    from app.context.search import VORAB_ANGEBOT, VORAB_SCHWELLE
    from app.context.service import kontext_fuer_frage
    from app.db.models import Conversation

    gemisch = _knoten("Gemisch AC")
    gemisch.embedding = _fuer_distanz((VORAB_SCHWELLE + VORAB_ANGEBOT) / 2)
    entwurf = _entwurf(gemisch)
    mit = Conversation(pseudonym="stud-ac", model_used="m", group_id=GROUP_ID)
    ohne = Conversation(pseudonym="stud-ac", model_used="m")
    db_session.add_all([gemisch, entwurf, mit, ohne,
                        _slot(date.today() - timedelta(days=3), stunde_id=entwurf.id)])
    await db_session.flush()

    with patch("app.context.service.vektor_oder_none", AsyncMock(return_value=FRAGE)):
        k_mit = await kontext_fuer_frage(assistant_id=None, pseudonym="stud-ac", query_text="egal",
                                         chat_id=mit.id, db=db_session, rollen=["student"])
        k_ohne = await kontext_fuer_frage(assistant_id=None, pseudonym="stud-ac", query_text="egal",
                                          chat_id=ohne.id, db=db_session, rollen=["student"])

    assert [(b.titel, b.grund) for b in k_mit.bausteine if b.titel == "Gemisch AC"] == [("Gemisch AC", "gruppe")]
    assert "Gemisch AC" not in [b.titel for b in k_ohne.bausteine]
    assert "Gemisch AC" in [a.titel for a in k_ohne.angebot]


# ── Schritt 6: Block-Zeile „In dieser Gruppe bereits eingeführt" (F4 a) ─────────


async def _block(db):
    from app.planning.student_context import get_current_topic, render_topic_block

    topic = await get_current_topic(db, GROUP_ID, TODAY)
    return topic, render_topic_block(topic, "Chemie")


@pytest.mark.asyncio
async def test_block_zeile_laufende_einheit_ohne_die_zwei_stunden(db_session, seed_sc_group):
    """Begriffe der Einheit der letzten Stunde; was an den zwei Stunden steht, nicht noch einmal;
    eine frühere Einheit nicht; Herkunft getrennt."""
    bindung, stoffe_ue = _ue("Chemische Bindung"), _ue("Stoffe")
    ion, metall, en, stoff = (_knoten(t) for t in ("Ionenbindung", "Metallbindung", "Elektronegativität", "Stoffe"))
    e_alt, e1, e2, e3 = _entwurf(stoff), _entwurf(ion), _entwurf(metall), _entwurf(en)
    db_session.add_all([bindung, stoffe_ue, ion, metall, en, stoff, e_alt, e1, e2, e3])
    s_alt = _slot(date(2026, 2, 16), stunde_id=e_alt.id, ue_id=stoffe_ue.id, nachbereitet=True)
    s1 = _slot(date(2026, 3, 9), stunde_id=e1.id, ue_id=bindung.id, nachbereitet=True)
    db_session.add_all([s_alt, s1, _slot(date(2026, 3, 11), stunde_id=e2.id, ue_id=bindung.id),
                        _slot(date(2026, 3, 13), stunde_id=e3.id, ue_id=bindung.id)])
    await db_session.flush()
    db_session.add_all([_eingetragen(stoff, s_alt), _eingetragen(ion, s1)])
    await db_session.flush()

    topic, md = await _block(db_session)
    assert topic.bereits.einheit == "Chemische Bindung"
    assert [t for _, t in topic.bereits.eingefuehrt] == ["Ionenbindung"]
    assert topic.bereits.laut_plan == []  # Metall- und Elektronegativität stehen an den zwei Stunden
    assert '- In dieser Gruppe bereits eingeführt (UE „Chemische Bindung", nur Titel): Ionenbindung' in md
    assert "Stoffe" not in md


@pytest.mark.asyncio
async def test_block_zeile_ohne_einheit_letzte_acht_stunden(db_session, seed_sc_group):
    from app.planning.student_context import EINGEFUEHRT_STUNDEN

    alt, neu = _knoten("Zu alt"), _knoten("Im Fenster")
    e_alt, e_neu = _entwurf(alt), _entwurf(neu)
    db_session.add_all([alt, neu, e_alt, e_neu])
    db_session.add(_slot(date(2026, 1, 12), stunde_id=e_alt.id))
    db_session.add(_slot(date(2026, 2, 2), stunde_id=e_neu.id))
    # Danach EINGEFUEHRT_STUNDEN − 1 belegte Stunden mit Thema, ohne Entwurf.
    for i in range(EINGEFUEHRT_STUNDEN - 1):
        db_session.add(_slot(date(2026, 3, 1) + timedelta(days=i), thema=f"T{i}"))
    await db_session.flush()

    topic, md = await _block(db_session)
    assert topic.bereits.einheit is None
    assert [t for _, t in topic.bereits.laut_plan] == ["Im Fenster"]
    assert f"(letzte {EINGEFUEHRT_STUNDEN} Stunden, nur Titel): laut Plan: Im Fenster" in md


@pytest.mark.asyncio
async def test_block_zeile_deckel(db_session, seed_sc_group):
    from app.planning.student_context import EINGEFUEHRT_TITEL

    ue = _ue("Viel")
    viele = [_knoten(f"B{i:02d}") for i in range(EINGEFUEHRT_TITEL + 3)]
    alt = _entwurf(*viele)
    db_session.add_all([ue, *viele, alt,
                        _slot(date(2026, 3, 2), stunde_id=alt.id, ue_id=ue.id),
                        _slot(date(2026, 3, 11), thema="Übung", ue_id=ue.id),
                        _slot(date(2026, 3, 13), thema="Übung 2", ue_id=ue.id)])
    await db_session.flush()

    topic, _ = await _block(db_session)
    assert len(topic.bereits.node_ids) == EINGEFUEHRT_TITEL


@pytest.mark.asyncio
async def test_block_zeile_fehlt_ohne_begriffe(db_session, seed_sc_group):
    db_session.add(_slot(date(2026, 3, 13), thema="Nur Thema"))
    await db_session.flush()

    topic, md = await _block(db_session)
    assert topic.bereits is None and "bereits eingeführt" not in md


@pytest.mark.asyncio
async def test_block_titel_kommen_in_den_kontext_fuer_die_statistik(db_session, seed_sc_group):
    from unittest.mock import AsyncMock, patch

    from app.context.service import kontext_fuer_frage
    from app.db.models import Conversation

    ue, begriff = _ue("Einheit"), _knoten("Früher eingeführt")
    alt = _entwurf(begriff)
    konv = Conversation(pseudonym="stud-ac", model_used="m", group_id=GROUP_ID)
    db_session.add_all([ue, begriff, alt, konv,
                        _slot(date.today() - timedelta(days=20), stunde_id=alt.id, ue_id=ue.id),
                        _slot(date.today() - timedelta(days=3), thema="Zuletzt", ue_id=ue.id),
                        _slot(date.today() - timedelta(days=1), thema="Gestern", ue_id=ue.id)])
    await db_session.flush()

    with patch("app.context.service.vektor_oder_none", AsyncMock(return_value=None)):
        k = await kontext_fuer_frage(assistant_id=None, pseudonym="stud-ac", query_text="egal",
                                     chat_id=konv.id, db=db_session, rollen=["student"])
    assert k.block_angebot == [str(begriff.id)]
    assert "laut Plan: Früher eingeführt" in k.text
