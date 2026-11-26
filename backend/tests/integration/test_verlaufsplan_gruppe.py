"""Plan der Fachschaft im Planer einer Gruppe (BD Teil B, Schritt 1). Erfordert TEST_DATABASE_URL.

Welt und Kalender wie in `test_verlaufsplan_endpunkte.py`: laufend ist 2025/26.
"""
import uuid

import pytest

from app.db.models import Group, GroupMembership

from tests.integration.test_verlaufsplan_endpunkte import (  # noqa: F401 — Fixtures
    FS, LK, TOKEN, _anlegen, _client, _person, db, welt,
)

pytestmark = pytest.mark.asyncio

LEHRKRAFT = f"vp-gr-{TOKEN}"


def _gruppen_client(db, user):
    c = _client(db, user)
    from app.planning.verlaufsplan_gruppe_router import router

    c._transport.app.include_router(router)
    return c


async def _gruppe(db, welt, *, jahrgang=9, name=None, fach=True):
    g = Group(name=name or f"9a M {uuid.uuid4().hex[:4]}", slug=f"g-{uuid.uuid4().hex[:8]}",
              type="teaching_group", subject_id=welt["fach"].id if fach else None, jahrgang=jahrgang)
    db.add(g)
    await db.flush()
    db.add(GroupMembership(group_id=g.id, pseudonym=LEHRKRAFT, role_in_group="teacher"))
    await db.flush()
    return g


def _lk():
    return _person(LEHRKRAFT, "teacher")


async def _lesen(db, g, user=None):
    async with _gruppen_client(db, user or _lk()) as c:
        return await c.get(f"/planning/groups/{g.id}/verlaufsplan")


async def test_entwurf_der_stufe_mit_wochen(db, welt):
    plan = (await _anlegen(db, welt)).json()
    g = await _gruppe(db, welt)
    r = await _lesen(db, g)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["schuljahr"], d["stufe"], d["grund"]) == ("2025/26", 9, None)
    assert d["plan"]["id"] == plan["id"] and d["plan"]["status"] == "draft"
    # Eine Lehrkraft der Gruppe ist nicht in der Fachschaft: lesen ja, bearbeiten nein
    assert not d["plan"]["darf_bearbeiten"]
    # 4 + 6 Wochen; Woche 1 beginnt am 15.09.2025 (KW 38), die Herbstferien liegen nach Woche 6
    woche = d["abschnitt_je_woche"]
    assert len(woche) == 10
    assert woche["2025-W38"] == 0 and woche["2025-W41"] == 0 and woche["2025-W42"] == 1
    assert "2025-W44" not in woche  # Herbstferien
    assert max(woche.values()) == 1


async def test_ohne_plan_ohne_stufe_ohne_fach(db, welt):
    await _anlegen(db, welt)
    andere = await _gruppe(db, welt, jahrgang=10)
    d = (await _lesen(db, andere)).json()
    assert (d["stufe"], d["grund"], d["plan"], d["abschnitt_je_woche"]) == (10, "kein_plan", None, {})

    unbekannt = await _gruppe(db, welt, jahrgang=None, name="Projektkurs Astronomie")
    d = (await _lesen(db, unbekannt)).json()
    assert (d["stufe"], d["grund"], d["plan"]) == (None, "keine_stufe", None)

    ohne_fach = await _gruppe(db, welt, fach=False)
    assert (await _lesen(db, ohne_fach)).json()["grund"] == "kein_fach"


async def test_plan_anderer_schuljahre_zaehlt_nicht(db, welt):
    assert (await _anlegen(db, welt, schuljahr="2026/27")).status_code == 201
    g = await _gruppe(db, welt)
    d = (await _lesen(db, g)).json()
    assert (d["grund"], d["plan"]) == ("kein_plan", None)


async def test_nur_lehrkraefte_der_gruppe(db, welt):
    await _anlegen(db, welt)
    g = await _gruppe(db, welt)
    # Fachschaft und fremde Lehrkraft sind nicht in der Gruppe
    assert (await _lesen(db, g, FS())).status_code == 403
    assert (await _lesen(db, g, LK())).status_code == 403
    assert (await _lesen(db, g, _person(LEHRKRAFT, "student"))).status_code == 403


# ── Vorschau (Schritt 3) ──────────────────────────────────────────────────────

async def _termine(db, g, tage, **kw):
    from app.db.models import LessonSlot

    slots = [LessonSlot(group_id=g.id, date=t, start_period=1, halbjahr=1, **kw) for t in tage]
    db.add_all(slots)
    await db.flush()
    return slots


async def _vorschau(db, g):
    async with _gruppen_client(db, _lk()) as c:
        return await c.get(f"/planning/groups/{g.id}/verlaufsplan/vorschau")


async def test_vorschau_je_abschnitt(db, welt, monkeypatch):
    from datetime import date

    from app.context import verlaufsplan as vp
    from app.db.models import ContextEdge, ContextNode

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))
    await _anlegen(db, welt, abschnitte=[
        {"titel": "", "wochen": 4, "kapitel_ids": [str(welt["kapitel"][0].id)]},
        {"titel": "Luft", "wochen": 1, "puffer": True},
        {"titel": "Pythagoras", "wochen": 2, "kapitel_ids": [str(welt["kapitel"][1].id)]},
    ])
    g = await _gruppe(db, welt)
    # Woche 1 (15.09.) zwei Termine, Woche 2 (22.09.) einer angepinnt, Woche 3 (29.09.) eine Prüfung,
    # Woche 6 (20.10.) einer
    t = await _termine(db, g, [date(2025, 9, 15), date(2025, 9, 18), date(2025, 9, 22), date(2025, 9, 29),
                               date(2025, 10, 20)])
    t[2].pinned = True
    t[3].kategorie = "pruefung"
    # Eine Einheit eines anderen Schuljahrs am selben Kapitel stört nicht
    alt = ContextNode(category="artifact", content_type="unterrichtseinheit", title="Alt", status="active",
                      read_scope="group_teachers", write_scope="group_teachers", read_scope_group_id=g.id,
                      write_scope_group_id=g.id, owner_pseudonym=LEHRKRAFT, subject_id=welt["fach"].id,
                      metadata_={"schuljahr": "2024/25"})
    db.add(alt)
    await db.flush()
    db.add(ContextEdge(from_node_id=alt.id, to_node_id=welt["kapitel"][0].id, relation="references"))
    # Pythagoras hat in diesem Schuljahr schon eine Einheit der Gruppe
    ue = ContextNode(category="artifact", content_type="unterrichtseinheit", title="Pyth", status="active",
                     read_scope="group_teachers", write_scope="group_teachers", read_scope_group_id=g.id,
                     write_scope_group_id=g.id, owner_pseudonym=LEHRKRAFT, subject_id=welt["fach"].id,
                     metadata_={"schuljahr": "2025/26"})
    db.add(ue)
    await db.flush()
    db.add(ContextEdge(from_node_id=ue.id, to_node_id=welt["kapitel"][1].id, relation="references"))
    await db.flush()

    r = await _vorschau(db, g)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "draft" and (d["neu"], d["stunden"]) == (1, 2)
    a, p, pyth = d["vorschlaege"]
    assert (a["anlegen"], a["titel"], a["kapitel_id"], a["wochen"]) == (True, "Ähnlichkeit", str(welt["kapitel"][0].id), "Woche 1–4")
    assert (a["stunden"], a["belegt"]) == (2, 1)
    assert (p["anlegen"], p["grund"], p["titel"]) == (False, "puffer", "Luft")
    assert (pyth["anlegen"], pyth["grund"]) == (False, "kapitel_vorhanden")
    # Nichts geschrieben
    from app.db.models import LessonSlot
    import sqlalchemy as sa
    gid = g.id
    db.expire_all()
    belegt = (await db.execute(sa.select(LessonSlot).where(LessonSlot.group_id == gid,
                                                            LessonSlot.ue_node_id.is_not(None)))).scalars().all()
    assert belegt == []


async def test_vorschau_sequenzgenau_mit_ersetztem_kapitel(db, welt, monkeypatch):
    """Das Curriculum wurde ersetzt: Der Plan nennt Sequenzen des alten Kapitels, die Einheit kommt
    an das Nachfolgekapitel (`kopie_von`)."""
    from datetime import date

    from app.context import verlaufsplan as vp
    from app.db.models import ContextEdge, ContextNode

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))
    alt_kap, seq = welt["kapitel"][0], welt["sequenzen"][0]
    plan = await _anlegen(db, welt, planungsart="sequenz",
                          abschnitte=[{"titel": "", "wochen": 2, "sequenz_ids": [str(seq.id)]}])
    assert plan.status_code == 201, plan.text
    alt_kap.status = "archived"
    neu = ContextNode(category="knowledge", content_type="kapitel", title="Ähnlichkeit (neu)", status="active",
                      subject_id=welt["fach"].id, read_scope="school", write_scope="private", owner_pseudonym="x",
                      metadata_={"kopie_von": str(alt_kap.id)})
    db.add(neu)
    await db.flush()
    g = await _gruppe(db, welt)
    (v,) = (await _vorschau(db, g)).json()["vorschlaege"]
    # Ohne Thema trägt die Einheit den Titel des (neuen) Kapitels
    assert (v["anlegen"], v["kapitel_id"], v["titel"], v["kapitel_fehlt"]) == (True, str(neu.id), "Ähnlichkeit (neu)", False)
    assert "Lernsequenzen: Strahlensätze" in v["beschreibung"]
    assert v["ohne_termine"]

    # Eine Einheit am Nachfolger: Der Abschnitt wird übersprungen
    ue = ContextNode(category="artifact", content_type="unterrichtseinheit", title="Ä", status="active",
                     read_scope="group_teachers", write_scope="group_teachers", read_scope_group_id=g.id,
                     write_scope_group_id=g.id, owner_pseudonym=LEHRKRAFT, subject_id=welt["fach"].id,
                     metadata_={"schuljahr": "2025/26"})
    db.add(ue)
    await db.flush()
    db.add(ContextEdge(from_node_id=ue.id, to_node_id=neu.id, relation="references"))
    await db.flush()
    (v,) = (await _vorschau(db, g)).json()["vorschlaege"]
    assert (v["anlegen"], v["grund"]) == (False, "kapitel_vorhanden")


async def test_vorschau_ohne_kalender_und_rechte(db, welt, monkeypatch):
    from app.context import verlaufsplan as vp

    await _anlegen(db, welt)
    g = await _gruppe(db, welt)
    async with _gruppen_client(db, FS()) as c:
        assert (await c.get(f"/planning/groups/{g.id}/verlaufsplan/vorschau")).status_code == 403
    monkeypatch.setattr(vp, "kalender_fuer", lambda sj: None)
    assert (await _vorschau(db, g)).status_code == 409


async def test_vorschau_ohne_plan_404(db, welt):
    g = await _gruppe(db, welt)
    assert (await _vorschau(db, g)).status_code == 404


# ── Anlegen und Rückgängig (Schritt 4) ────────────────────────────────────────

async def _post(db, g, pfad, json=None, user=None):
    """`g`: Gruppe oder ihre ID (nach `expire_all` nur noch die ID)."""
    gid = g if isinstance(g, int) else g.id
    async with _gruppen_client(db, user or _lk()) as c:
        return await c.post(f"/planning/groups/{gid}/verlaufsplan/{pfad}", json=json)


async def _einheiten(db, gid):
    import sqlalchemy as sa

    from app.db.models import ContextNode

    return (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "unterrichtseinheit", ContextNode.write_scope_group_id == gid))).scalars().all()


async def test_anlegen_und_rueckgaengig(db, welt, monkeypatch):
    from datetime import date

    import sqlalchemy as sa

    from app.context import verlaufsplan as vp
    from app.db.models import ContextEdge, LessonSlot, SlotPlanSnapshot

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))
    plan = (await _anlegen(db, welt, abschnitte=[
        {"titel": "", "wochen": 2, "kapitel_ids": [str(welt["kapitel"][0].id)], "notiz": "mit GeoGebra"},
        {"titel": "", "wochen": 1, "puffer": True},
        {"titel": "Satz des Pythagoras", "wochen": 1, "kapitel_ids": [str(welt["kapitel"][1].id)]},
    ])).json()
    g = await _gruppe(db, welt)
    gid = g.id
    # Woche 1 (15.09.) zwei, Woche 2 (22.09.) einer angepinnt, Woche 3 Puffer, Woche 4 (06.10.) einer
    t = await _termine(db, g, [date(2025, 9, 15), date(2025, 9, 18), date(2025, 9, 22), date(2025, 9, 29),
                               date(2025, 10, 6)])
    t[2].pinned = True
    ids = [s.id for s in t]

    r = await _post(db, g, "anlegen")
    assert r.status_code == 200, r.text
    lauf = r.json()
    assert (lauf["einheiten"], lauf["stunden"]) == (2, 3) and lauf["lauf_id"]

    einheiten = sorted(await _einheiten(db, gid), key=lambda e: e.title)
    assert [e.title for e in einheiten] == ["Satz des Pythagoras", "Ähnlichkeit"]
    pyth, aehn = einheiten
    assert aehn.metadata_["aus_verlaufsplan"]["plan_id"] == plan["id"]
    assert aehn.metadata_["aus_verlaufsplan"]["lauf_id"] == lauf["lauf_id"]
    assert (aehn.metadata_["farbe"], pyth.metadata_["farbe"]) == (0, 1)
    assert "Notiz: mit GeoGebra" in aehn.content and aehn.metadata_["schuljahr"] == "2025/26"
    kanten = (await db.execute(sa.select(ContextEdge.to_node_id).where(
        ContextEdge.from_node_id == aehn.id, ContextEdge.relation == "references"))).scalars().all()
    assert kanten == [welt["kapitel"][0].id]
    zuordnung = {s.date: s.ue_node_id for s in (await db.execute(
        sa.select(LessonSlot).where(LessonSlot.id.in_(ids)).execution_options(populate_existing=True))).scalars()}
    assert zuordnung == {date(2025, 9, 15): aehn.id, date(2025, 9, 18): aehn.id, date(2025, 9, 22): None,
                         date(2025, 9, 29): None, date(2025, 10, 6): pyth.id}
    snap = (await db.execute(sa.select(SlotPlanSnapshot).where(SlotPlanSnapshot.group_id == gid))).scalars().all()
    assert [s.label for s in snap] == ["Vor: Einheiten aus dem Jahresverlaufsplan"]

    # Ein zweiter Lauf legt nichts doppelt an
    assert (await _post(db, g, "anlegen")).json() == {"lauf_id": None, "einheiten": 0, "stunden": 0}
    # Die Vorschau sagt es
    v = (await _vorschau(db, g)).json()["vorschlaege"]
    assert [x["grund"] for x in v] == ["schon_angelegt", "puffer", "schon_angelegt"]

    # Rückgängig: Einheiten weg, Termine wieder frei
    r = await _post(db, g, "rueckgaengig", {"lauf_id": lauf["lauf_id"]})
    assert r.json() == {"einheiten": 2}, r.text
    db.expire_all()
    assert await _einheiten(db, gid) == []
    frei = (await db.execute(sa.select(LessonSlot.ue_node_id).where(LessonSlot.id.in_(ids)))).scalars().all()
    assert set(frei) == {None}
    assert (await _post(db, gid, "rueckgaengig", {"lauf_id": lauf["lauf_id"]})).status_code == 404


async def test_rueckgaengig_nicht_mit_stunden(db, welt, monkeypatch):
    from datetime import date

    from app.context import verlaufsplan as vp
    from app.db.models import ContextEdge, ContextNode

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))
    await _anlegen(db, welt)
    g = await _gruppe(db, welt)
    gid = g.id
    lauf = (await _post(db, g, "anlegen")).json()
    assert lauf["einheiten"] == 2
    ue = (await _einheiten(db, gid))[0]
    stunde = ContextNode(category="artifact", content_type="unterrichtsstunde", title="Stunde 1", status="active",
                         read_scope="group_teachers", write_scope="group_teachers", read_scope_group_id=gid,
                         write_scope_group_id=gid, owner_pseudonym=LEHRKRAFT, metadata_={})
    db.add(stunde)
    await db.flush()
    db.add(ContextEdge(from_node_id=stunde.id, to_node_id=ue.id, relation="part_of"))
    await db.flush()
    r = await _post(db, g, "rueckgaengig", {"lauf_id": lauf["lauf_id"]})
    assert r.status_code == 409 and "schon Stunden" in r.json()["detail"]
    assert len(await _einheiten(db, gid)) == 2


async def test_anlegen_nur_lehrkraefte_der_gruppe(db, welt):
    await _anlegen(db, welt)
    g = await _gruppe(db, welt)
    assert (await _post(db, g, "anlegen", user=FS())).status_code == 403
    assert (await _post(db, g, "rueckgaengig", {"lauf_id": "x"}, user=LK())).status_code == 403


async def test_anlegen_belegt_nur_was_noch_frei_ist(db, welt, monkeypatch):
    """Ein Termin, der zwischen Vorschau und Anlegen belegt wurde, bleibt, wie er ist (FB4/FB5)."""
    from datetime import date

    import sqlalchemy as sa

    from app.context import verlaufsplan as vp
    from app.db.models import ContextNode, LessonSlot
    from app.planning import verlaufsplan_gruppe as vg

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))
    await _anlegen(db, welt, abschnitte=[{"titel": "A", "wochen": 1, "kapitel_ids": [str(welt["kapitel"][0].id)]}])
    g = await _gruppe(db, welt)
    gid = g.id
    t = await _termine(db, g, [date(2025, 9, 15), date(2025, 9, 18)])
    fremd = ContextNode(category="artifact", content_type="unterrichtseinheit", title="Von Hand", status="active",
                        read_scope="group_teachers", write_scope="group_teachers", read_scope_group_id=gid,
                        write_scope_group_id=gid, owner_pseudonym=LEHRKRAFT, metadata_={"schuljahr": "2024/25"})
    db.add(fremd)
    await db.flush()
    termin_id, fremd_id = t[1].id, fremd.id

    # Nach der letzten Rechnung und vor dem Belegen ordnet jemand anderes den Termin zu: Die Liste
    # hält ihn für frei, das bedingte UPDATE darf ihn trotzdem nicht treffen.
    echte = vg.vorschlaege
    aufrufe = []

    async def mit_zwischenruf(*a, **kw):
        aufrufe.append(1)
        ergebnis = await echte(*a, **kw)
        if len(aufrufe) == 2:
            assert termin_id in ergebnis[0].slot_ids
            await db.execute(sa.update(LessonSlot).where(LessonSlot.id == termin_id).values(ue_node_id=fremd_id))
        return ergebnis

    monkeypatch.setattr(vg, "vorschlaege", mit_zwischenruf)
    r = (await _post(db, g, "anlegen")).json()
    assert (r["einheiten"], r["stunden"]) == (1, 1)
    zuordnung = (await db.execute(sa.select(LessonSlot.ue_node_id).where(LessonSlot.id == termin_id))).scalar_one()
    assert zuordnung == fremd_id


async def test_geloeschter_abschnitt_zaehlt_wieder_ueber_das_kapitel(db, welt, monkeypatch):
    from datetime import date

    from app.context import verlaufsplan as vp

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))
    plan = (await _anlegen(db, welt, abschnitte=[
        {"titel": "A", "wochen": 1, "kapitel_ids": [str(welt["kapitel"][0].id)]}])).json()
    g = await _gruppe(db, welt)
    await _termine(db, g, [date(2025, 9, 15), date(2025, 9, 22)])
    assert (await _post(db, g, "anlegen")).json()["einheiten"] == 1
    # Die Fachschaft ersetzt die Zeile durch eine neue mit demselben Kapitel (neue ID)
    async with _client(db, FS()) as c:
        r = await c.put(f"/context/verlaufsplaene/{plan['id']}", json={"planungsart": "kapitel", "abschnitte": [
            {"titel": "A neu", "wochen": 2, "kapitel_ids": [str(welt["kapitel"][0].id)]}]})
        assert r.status_code == 200, r.text
    (v,) = (await _vorschau(db, g)).json()["vorschlaege"]
    assert (v["anlegen"], v["grund"]) == (False, "kapitel_vorhanden")
