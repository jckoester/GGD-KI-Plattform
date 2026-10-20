"""Eingeführte Begriffe einer Unterrichtsgruppe (0.20, Päckchen AC, Schritt 3)."""
from datetime import date
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
