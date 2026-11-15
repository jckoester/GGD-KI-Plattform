"""Gebündelter Abgleich Name → Begriff (0.44, Päckchen AQ, Schritt 1).

`begriffe_abgleichen` löst viele Namen eines Fachs in einer Abfrage auf und wendet die Regeln
von `begriff_zum_titel` in Python an (Fassung, eigenes Fach vor Bezugsfach, Einzahlform nur
eindeutig, Sichtbarkeit). Die Planung läuft darauf; ihre Tests (`test_begriffe_der_stunde.py`)
sichern das gemessene Verhalten, diese hier die Funktion selbst.
"""
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event

from app.context.begriffe_abgleich import begriffe_abgleichen
from app.db.models import ContextNode, NodeAlias, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
LEHRKRAFT = SimpleNamespace(sub=f"abgleich-{TOKEN}", roles=["teacher"])


def _n(s: str) -> str:
    """Eindeutige Namen — die Bezugsfächer anderer Tests sollen nichts beitragen.

    Das Kennzeichen steht vorn: hinten verdeckte es die Mehrzahlendung, und mit einer Ziffer
    am Anfang striche die Normalisierung es als Gliederungsnummer weg.
    """
    return f"Q{TOKEN}{s}"


async def _fach(db, name: str, bezug=()) -> Subject:
    fach = Subject(slug=f"{name.lower()}-{TOKEN}-{uuid.uuid4().hex[:4]}", name=f"{name} {TOKEN}",
                   fach_code=f"{name[:2].upper()}{uuid.uuid4().hex[:3]}", bezugsfaecher=list(bezug))
    db.add(fach)
    await db.flush()
    return fach


async def _begriff(db, titel: str, fach: Subject, *, aliase=(), art="begriff", **kw) -> ContextNode:
    lesen = kw.pop("read_scope", "school")
    n = ContextNode(category="concept", content_type=art, title=titel, status=kw.pop("status", "active"),
                    subject_id=fach.id, read_scope=lesen, write_scope="private" if lesen == "private" else "school",
                    metadata_=kw.pop("metadata_", {}), **kw)
    db.add(n)
    await db.flush()
    db.add_all(NodeAlias(node_id=n.id, alias=a) for a in aliase)
    await db.flush()
    return n


@pytest_asyncio.fixture
async def faecher(db_session):
    bio = await _fach(db_session, "Bio")
    chemie = await _fach(db_session, "Chemie")
    nwt = await _fach(db_session, "NwT", bezug=[bio.slug, chemie.slug])
    return SimpleNamespace(bio=bio, chemie=chemie, nwt=nwt)


async def _ab(db, fach, *namen, user=LEHRKRAFT):
    eingabe = [n if isinstance(n, tuple) else (n, None) for n in namen]
    return await begriffe_abgleichen(db, user, fach.id, eingabe)


async def test_titel_alias_bindestrich_und_reihenfolge(db_session, faecher):
    benzol = await _begriff(db_session, _n("Benzol"), faecher.chemie, aliase=[_n("Benzen")])
    ion = await _begriff(db_session, _n("Arenium-Ion"), faecher.chemie)
    erg = await _ab(db_session, faecher.chemie,
                    _n("Unbekannt"), _n("benzen"), f"  {_n('BENZOL').upper()} ", _n("Arenium‑Ion"))
    assert [a.zustand for a in erg] == ["fehlt", "gefunden", "gefunden", "gefunden"]
    assert [a.knoten.id if a.knoten else None for a in erg] == [None, benzol.id, benzol.id, ion.id]
    assert erg[0].name == _n("Unbekannt")


async def test_fassung_und_mehrdeutig(db_session, faecher):
    alt = await _begriff(db_session, _n("Oxidation"), faecher.chemie, metadata_={"fassung": "Sauerstoff"})
    neu = await _begriff(db_session, _n("Oxidation"), faecher.chemie, metadata_={"fassung": "Elektronen"})
    ohne, mit, falsch = await _ab(db_session, faecher.chemie, _n("Oxidation"),
                                  (_n("Oxidation"), " elektronen "), (_n("Oxidation"), "Gibt es nicht"))
    assert ohne.zustand == "mehrdeutig"
    assert {k.id for k in ohne.kandidaten} == {alt.id, neu.id}
    assert (mit.zustand, mit.knoten.id) == ("gefunden", neu.id)
    assert falsch.zustand == "fehlt"


async def test_eigenes_fach_vor_bezugsfach(db_session, faecher):
    """Im eigenen Fach gefunden gilt es; sonst das Bezugsfach; zwei Bezugsfächer sind mehrdeutig."""
    eigen = await _begriff(db_session, _n("Zelle"), faecher.nwt)
    await _begriff(db_session, _n("Zelle"), faecher.bio)
    bio = await _begriff(db_session, _n("Osmose"), faecher.bio)
    await _begriff(db_session, _n("Energie"), faecher.bio)
    await _begriff(db_session, _n("Energie"), faecher.chemie)
    zelle, osmose, energie = await _ab(db_session, faecher.nwt, _n("Zelle"), _n("Osmose"), _n("Energie"))
    assert zelle.knoten.id == eigen.id
    assert (osmose.zustand, osmose.knoten.id) == ("gefunden", bio.id)
    assert energie.zustand == "mehrdeutig"
    # Umgekehrt ist NwT kein Bezugsfach der Biologie.
    (aus_bio,) = await _ab(db_session, faecher.bio, _n("Zelle"))
    assert aus_bio.knoten.subject_id == faecher.bio.id


async def test_einzahlform_nur_eindeutig(db_session, faecher):
    farb = await _begriff(db_session, _n("Chlorophyll"), faecher.bio, aliase=[_n("Blattfarbstoff")])
    await _begriff(db_session, _n("Salz"), faecher.chemie)
    await _begriff(db_session, _n("Salze"), faecher.chemie, status="archived")
    await _begriff(db_session, _n("Kristall"), faecher.chemie)
    await _begriff(db_session, _n("Kristalle"), faecher.chemie, read_scope="private",
                   owner_pseudonym="jemand-anderes")
    await _begriff(db_session, _n("Säur"), faecher.chemie)
    await _begriff(db_session, _n("Säure"), faecher.chemie)
    farbe, salz, kristall, saeure = await _ab(db_session, faecher.bio, _n("Blattfarbstoffe")) + \
        await _ab(db_session, faecher.chemie, _n("Salze"), _n("Kristalle"), _n("Säuren"))
    assert (farbe.zustand, farbe.knoten.id) == ("gefunden", farb.id)
    assert salz.zustand == "gefunden"        # das archivierte „Salze“ zählt nicht
    assert kristall.zustand == "gefunden"    # das fremde private „Kristalle“ auch nicht
    # „Säuren“ → „Säur“ und „Säure“: zwei Einzahlformen, zwei Treffer → fehlt, nicht mehrdeutig
    # (Regel aus `begriff_zum_titel`).
    assert saeure.zustand == "fehlt"


async def test_privates_nur_fuer_die_eigene_person(db_session, faecher):
    mein = await _begriff(db_session, _n("Notiz"), faecher.chemie, read_scope="private",
                          owner_pseudonym=LEHRKRAFT.sub)
    (ich,) = await _ab(db_session, faecher.chemie, _n("Notiz"))
    (andere,) = await _ab(db_session, faecher.chemie, _n("Notiz"),
                          user=SimpleNamespace(sub="jemand-anderes", roles=["teacher"]))
    assert ich.knoten.id == mein.id
    assert andere.zustand == "fehlt"


async def test_stoffsteckbrief_zaehlt_anderes_nicht(db_session, faecher):
    stoff = await _begriff(db_session, _n("Ethanol"), faecher.chemie, art="stoffsteckbrief")
    db_session.add(ContextNode(category="knowledge", content_type="methodenblatt", title=_n("Titration"),
                               status="active", subject_id=faecher.chemie.id, read_scope="school",
                               write_scope="school", metadata_={}))
    await db_session.flush()
    ethanol, titration = await _ab(db_session, faecher.chemie, _n("Ethanol"), _n("Titration"))
    assert ethanol.knoten.id == stoff.id
    assert titration.zustand == "fehlt"


async def test_eine_abfrage_fuer_viele_namen(db_session, faecher):
    for i in range(20):
        await _begriff(db_session, _n(f"Stoff{i}"), faecher.chemie, aliase=[_n(f"Alias{i}")])
    namen = [_n(f"Stoff{i}") for i in range(20)] + [_n(f"Alias{i}e") for i in range(20)] + \
        [_n(f"Fehlt{i}") for i in range(20)]

    abfragen = []
    sync_engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind

    def zaehle(conn, cursor, statement, *a):
        if "context_nodes" in statement:
            abfragen.append(statement)

    event.listen(sync_engine, "before_cursor_execute", zaehle)
    try:
        erg = await begriffe_abgleichen(db_session, LEHRKRAFT, faecher.chemie.id, [(n, None) for n in namen],
                                        bezugsfaecher=())
    finally:
        event.remove(sync_engine, "before_cursor_execute", zaehle)
    assert [a.zustand for a in erg] == ["gefunden"] * 40 + ["fehlt"] * 20
    assert len(abfragen) == 1


async def test_leere_eingabe(db_session, faecher):
    assert await begriffe_abgleichen(db_session, LEHRKRAFT, faecher.chemie.id, []) == []
