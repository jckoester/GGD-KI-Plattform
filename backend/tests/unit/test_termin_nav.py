"""Vorige und nächste Stunde nach Terminen der Gruppe (0.48, Päckchen N, F4–F6)."""
from dataclasses import dataclass
from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from app.planning.termin_nav import termin_nachbarn


@dataclass
class T:
    id: UUID
    date: date
    start_period: Optional[int] = None
    kategorie: str = "unterricht"
    stunde_node_id: Optional[UUID] = None
    thema: Optional[str] = None


def _termin(tag, stunde=1, **kw):
    return T(id=uuid4(), date=date(2026, 11, tag), start_period=stunde, **kw)


def test_nachbarn_nach_datum_und_stunde_nicht_nach_reihenfolge_der_liste():
    a, b, c = _termin(10, 3), _termin(12, 1), _termin(12, 5)
    vorher, nachher = termin_nachbarn([c, a, b], b.id, set(), anlegen_erlaubt=True)
    assert vorher.slot_id == a.id
    assert nachher.slot_id == c.id


def test_ausfall_wird_uebersprungen_F5():
    a, ausfall, c = _termin(10), _termin(11, kategorie="ausfall"), _termin(12)
    _, nachher = termin_nachbarn([a, ausfall, c], a.id, set(), anlegen_erlaubt=True)
    assert nachher.slot_id == c.id


def test_termin_ohne_entwurf_zaehlt_und_traegt_keine_stunde_F4():
    a, leer = _termin(10, stunde_node_id=uuid4()), _termin(11)
    _, nachher = termin_nachbarn([a, leer], a.id, {a.stunde_node_id}, anlegen_erlaubt=True)
    assert nachher.slot_id == leer.id
    assert nachher.stunde_node_id is None


def test_im_lesezustand_nur_termine_mit_entwurf():
    e1, e2 = uuid4(), uuid4()
    a, leer, b = _termin(10, stunde_node_id=e1), _termin(11), _termin(12, stunde_node_id=e2)
    _, nachher = termin_nachbarn([a, leer, b], a.id, {e1, e2}, anlegen_erlaubt=False)
    assert nachher.slot_id == b.id
    assert nachher.stunde_node_id == e2


def test_geloeschter_oder_archivierter_entwurf_gilt_als_kein_entwurf():
    weg = uuid4()
    a, b = _termin(10), _termin(11, stunde_node_id=weg)
    _, nachher = termin_nachbarn([a, b], a.id, set(), anlegen_erlaubt=True)
    assert nachher.stunde_node_id is None
    assert termin_nachbarn([a, b], a.id, set(), anlegen_erlaubt=False) == (None, None)


def test_pruefung_und_puffer_zaehlen():
    a, p = _termin(10), _termin(11, kategorie="pruefung")
    _, nachher = termin_nachbarn([a, p], a.id, set(), anlegen_erlaubt=True)
    assert nachher.kategorie == "pruefung"


def test_am_rand_und_unbekannter_termin():
    a, b = _termin(10), _termin(11)
    assert termin_nachbarn([a, b], a.id, set(), anlegen_erlaubt=True)[0] is None
    assert termin_nachbarn([a, b], b.id, set(), anlegen_erlaubt=True)[1] is None
    assert termin_nachbarn([a, b], uuid4(), set(), anlegen_erlaubt=True) == (None, None)


def test_termin_ohne_stunde_im_tag_steht_vor_den_gezaehlten():
    ohne, erste = _termin(10, None), _termin(10, 1)
    vorher, _ = termin_nachbarn([erste, ohne], erste.id, set(), anlegen_erlaubt=True)
    assert vorher.slot_id == ohne.id
