"""Die Auswahlregel des „Jetzt"-Blocks (AP5 des Fachseiten-Plans).

Reine Funktion, reine Tests: keine Datenbank, ein fester Stichtag. Geprüft werden
die Fälle, an denen so eine Regel scheitert — Ferien, Schuljahresende, ein
Unterrichtstag, der heute ist, und Slots ohne zugeordnete Einheit.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.planning.jetzt import waehle

UE_A = uuid4()
UE_B = uuid4()
HEUTE = date(2026, 9, 9)  # ein Mittwoch


@dataclass
class Slot:
    """Attrappe mit genau den Feldern, die die Regel liest."""
    date: date
    kategorie: str = "unterricht"
    ue_node_id: Optional[UUID] = None
    stunde_node_id: Optional[UUID] = None
    thema: Optional[str] = None
    nachbereitet_at: Optional[datetime] = None
    start_period: Optional[int] = 1
    id: UUID = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid4()


def tag(tag_im_september: int, **kw) -> Slot:
    return Slot(date=date(2026, 9, tag_im_september), **kw)


# ── Zuletzt und kommende Stunden ──────────────────────────────────────────────

def test_zuletzt_ist_die_juengste_vergangene_stunde():
    jetzt = waehle([tag(2), tag(4), tag(11)], HEUTE)
    assert jetzt.zuletzt.datum == date(2026, 9, 4)


def test_heutige_stunde_zaehlt_als_kommend_nicht_als_vergangen():
    # Slots tragen kein Ende; „schon gehalten" wäre die riskantere Vermutung.
    jetzt = waehle([tag(4), tag(9), tag(11)], HEUTE)
    assert jetzt.zuletzt.datum == date(2026, 9, 4)
    assert jetzt.kommende[0].datum == HEUTE
    assert jetzt.kommende[0].ist_heute is True
    assert jetzt.kommende[1].ist_heute is False


def test_kommende_sind_aufsteigend_und_gekappt():
    jetzt = waehle([tag(9), tag(11), tag(14), tag(16), tag(18)], HEUTE)
    assert [s.datum.day for s in jetzt.kommende] == [9, 11, 14]


def test_vor_dem_ersten_unterrichtstag_gibt_es_kein_zuletzt():
    jetzt = waehle([tag(14), tag(16)], HEUTE)
    assert jetzt.zuletzt is None
    assert [s.datum.day for s in jetzt.kommende] == [14, 16]


def test_am_schuljahresende_gibt_es_kein_kommendes():
    jetzt = waehle([tag(2), tag(4)], HEUTE)
    assert jetzt.zuletzt.datum == date(2026, 9, 4)
    assert jetzt.kommende == ()


def test_ohne_slots_bleibt_alles_leer():
    jetzt = waehle([], HEUTE)
    assert jetzt.zuletzt is None
    assert jetzt.kommende == ()
    assert jetzt.laufende_einheit is None
    assert jetzt.naechste_einheit is None


def test_ferienluecke_zeigt_die_stunde_danach():
    # Zwei Wochen Pause: „als Nächstes" bleibt richtig, auch wenn es weit weg ist.
    jetzt = waehle([tag(4), tag(28)], HEUTE)
    assert jetzt.zuletzt.datum == date(2026, 9, 4)
    assert jetzt.kommende[0].datum == date(2026, 9, 28)


# ── Ausfall ───────────────────────────────────────────────────────────────────

def test_ausfall_ist_weder_letzte_noch_naechste_stunde():
    jetzt = waehle(
        [tag(4), tag(7, kategorie="ausfall"), tag(11, kategorie="ausfall"), tag(14)],
        HEUTE,
    )
    assert jetzt.zuletzt.datum == date(2026, 9, 4)
    assert [s.datum.day for s in jetzt.kommende] == [14]


def test_ausfall_zaehlt_nicht_in_die_stundenzahl():
    jetzt = waehle(
        [tag(2, ue_node_id=UE_A), tag(4, ue_node_id=UE_A, kategorie="ausfall"),
         tag(11, ue_node_id=UE_A)],
        HEUTE,
    )
    assert jetzt.laufende_einheit.stunden_gesamt == 2
    assert jetzt.laufende_einheit.stunden_gehalten == 1


def test_pruefung_und_puffer_zaehlen_mit():
    # Verplante Zeit ist gehaltene Zeit — nur der Ausfall fällt raus.
    jetzt = waehle(
        [tag(2, ue_node_id=UE_A, kategorie="pruefung"),
         tag(4, ue_node_id=UE_A, kategorie="puffer")],
        HEUTE,
    )
    assert jetzt.laufende_einheit.stunden_gesamt == 2
    assert jetzt.zuletzt.kategorie == "puffer"


# ── Einheiten ─────────────────────────────────────────────────────────────────

def test_laufende_einheit_ist_die_des_juengsten_slots_bis_heute():
    jetzt = waehle(
        [tag(2, ue_node_id=UE_A), tag(4, ue_node_id=UE_A),
         tag(11, ue_node_id=UE_B), tag(14, ue_node_id=UE_B)],
        HEUTE,
    )
    assert jetzt.laufende_einheit.node_id == UE_A
    assert jetzt.laufende_einheit.stunden_gesamt == 2
    assert jetzt.laufende_einheit.stunden_gehalten == 2
    assert jetzt.naechste_einheit.node_id == UE_B
    assert jetzt.naechste_einheit.stunden_gehalten == 0


def test_mitten_in_der_einheit_zaehlt_der_fortschritt():
    jetzt = waehle(
        [tag(2, ue_node_id=UE_A), tag(4, ue_node_id=UE_A),
         tag(11, ue_node_id=UE_A), tag(14, ue_node_id=UE_A)],
        HEUTE,
    )
    assert jetzt.laufende_einheit.stunden_gehalten == 2
    assert jetzt.laufende_einheit.stunden_gesamt == 4
    # Es folgt keine andere Einheit — dann gibt es keine „nächste".
    assert jetzt.naechste_einheit is None


def test_vor_dem_start_ist_die_erste_einheit_die_naechste_nicht_die_laufende():
    jetzt = waehle([tag(14, ue_node_id=UE_A), tag(16, ue_node_id=UE_A)], HEUTE)
    assert jetzt.laufende_einheit is None
    assert jetzt.naechste_einheit.node_id == UE_A


def test_slots_ohne_einheit_stoeren_die_zuordnung_nicht():
    # Nicht jeder Slot hängt an einer Einheit — ein unverplanter dazwischen darf
    # die laufende Einheit nicht löschen.
    jetzt = waehle(
        [tag(2, ue_node_id=UE_A), tag(4), tag(11, ue_node_id=UE_B)],
        HEUTE,
    )
    assert jetzt.laufende_einheit.node_id == UE_A
    assert jetzt.naechste_einheit.node_id == UE_B


def test_heutige_stunde_gehoert_zur_laufenden_einheit():
    jetzt = waehle(
        [tag(4, ue_node_id=UE_A), tag(9, ue_node_id=UE_A), tag(11, ue_node_id=UE_B)],
        HEUTE,
    )
    assert jetzt.laufende_einheit.node_id == UE_A
    # Die heutige Stunde zählt in den Fortschritt, obwohl sie unter „kommend" steht.
    assert jetzt.laufende_einheit.stunden_gehalten == 2
    assert jetzt.naechste_einheit.node_id == UE_B


# ── Zustand je Stunde ─────────────────────────────────────────────────────────

def test_entwurf_und_nachbereitung_werden_gemeldet():
    jetzt = waehle(
        [tag(4, stunde_node_id=uuid4(), nachbereitet_at=datetime(2026, 9, 4, tzinfo=timezone.utc)),
         tag(11)],
        HEUTE,
    )
    assert jetzt.zuletzt.hat_entwurf is True
    assert jetzt.zuletzt.nachbereitet is True
    assert jetzt.kommende[0].hat_entwurf is False
    assert jetzt.kommende[0].nachbereitet is False


def test_reihenfolge_am_selben_tag_folgt_der_stunde():
    frueh = tag(11, start_period=1, thema="erste")
    spaet = tag(11, start_period=5, thema="zweite")
    jetzt = waehle([spaet, frueh], HEUTE)
    assert [s.thema for s in jetzt.kommende] == ["erste", "zweite"]


def test_fehlendes_stundenraster_kippt_die_sortierung_nicht():
    # Importierte Slots können ohne `start_period` kommen.
    ohne = tag(11, start_period=None, thema="ohne Raster")
    mit = tag(11, start_period=3, thema="mit Raster")
    jetzt = waehle([mit, ohne], HEUTE)
    assert [s.thema for s in jetzt.kommende] == ["ohne Raster", "mit Raster"]
