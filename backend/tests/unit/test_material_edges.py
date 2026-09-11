"""Unit-Tests für app.planning.material_edges — AP6b, Schritt 1.

Geprüft wird die **Entscheidung**, nicht die Datenbank: `soll_kanten` liest die
Phasen, `plane_abgleich` vergleicht Ist und Soll. Beide sind DB-frei und deshalb
ohne Fixtures prüfbar — dasselbe Muster wie `plane_aenderung` in
`scripts/seed_methodik.py`. Die dünne DB-Schicht darüber deckt Schritt 2 mit
Integrationstests ab.
"""
import os
from uuid import UUID, uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.planning.material_edges import (
    RELATION,
    VIA,
    plane_abgleich,
    soll_kanten,
)

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")


def _phase(phase_id, *material):
    return {"id": phase_id, "name": "Erarbeitung", "dauer_min": 20, "material": list(material)}


def _knoten(node_id, titel="Arbeitsblatt"):
    return {"typ": "node", "node_id": str(node_id), "titel": titel}


def _text(wert="Buch S. 42"):
    return {"typ": "text", "wert": wert}


# ── soll_kanten ──────────────────────────────────────────────────────────────

class TestSollKanten:
    def test_knoten_material_ergibt_einen_eintrag(self):
        meta = {"phasen": [_phase("p1", _knoten(A))]}
        assert soll_kanten(meta) == {A: ["p1"]}

    def test_freitext_ergibt_nichts(self):
        """`typ: "text"` ist kein Verweis — daraus darf keine Kante entstehen."""
        meta = {"phasen": [_phase("p1", _text(), _text("Tafel"))]}
        assert soll_kanten(meta) == {}

    def test_gemischte_phase_nimmt_nur_die_knoten(self):
        meta = {"phasen": [_phase("p1", _text(), _knoten(A), _text("Tafel"))]}
        assert soll_kanten(meta) == {A: ["p1"]}

    def test_dasselbe_material_in_zwei_phasen_ergibt_eine_kante(self):
        """Der Kern der Phasen-Liste: eine Kante, zwei Phasen — keine Dublette.

        Nötig, weil `create_edge` über (from, to, relation) idempotent ist: Eine
        zweite Kante mit anderer Phase fiele stillschweigend unter den Tisch.
        """
        meta = {"phasen": [_phase("p1", _knoten(A)), _phase("p3", _knoten(A))]}
        assert soll_kanten(meta) == {A: ["p1", "p3"]}

    def test_phasen_sind_sortiert(self):
        """Sonst schlüge der Vergleich zweier Stände an der Reihenfolge fehl."""
        meta = {"phasen": [_phase("p3", _knoten(A)), _phase("p1", _knoten(A))]}
        assert soll_kanten(meta)[A] == ["p1", "p3"]

    def test_mehrere_bausteine_in_einer_phase(self):
        meta = {"phasen": [_phase("p1", _knoten(A), _knoten(B, "Begriff"))]}
        assert soll_kanten(meta) == {A: ["p1"], B: ["p1"]}

    def test_phase_ohne_id_liefert_kante_ohne_verortung(self):
        """`LessonPhaseItem.id` ist Optional — die Kante ist trotzdem richtig."""
        meta = {"phasen": [_phase(None, _knoten(A))]}
        assert soll_kanten(meta) == {A: []}

    def test_uuid_objekt_wird_akzeptiert(self):
        meta = {"phasen": [{"id": "p1", "material": [{"typ": "node", "node_id": A}]}]}
        assert soll_kanten(meta) == {A: ["p1"]}

    def test_unbrauchbare_node_id_faellt_weg(self):
        """Kaputte Daten dürfen den Speichervorgang nicht sprengen."""
        meta = {
            "phasen": [
                {"id": "p1", "material": [{"typ": "node", "node_id": "keine-uuid"}]},
                {"id": "p2", "material": [{"typ": "node"}]},
            ]
        }
        assert soll_kanten(meta) == {}

    def test_leere_und_fehlende_eingaben(self):
        assert soll_kanten(None) == {}
        assert soll_kanten({}) == {}
        assert soll_kanten({"phasen": []}) == {}
        assert soll_kanten({"phasen": [{"id": "p1"}]}) == {}

    def test_unerwartete_strukturen_stuerzen_nicht_ab(self):
        meta = {"phasen": ["kaputt", None, _phase("p1", "auch kaputt", _knoten(A))]}
        assert soll_kanten(meta) == {A: ["p1"]}

    def test_methode_und_sozialform_bleiben_aussen_vor(self):
        """Die Regel: Kante = Abhängigkeit, nicht Nennung.

        Beide zeigen zwar ebenfalls auf Knoten (das AP6-Vokabular), aber sie
        beschreiben die Phase, statt ihr Inhalt zu liefern — und `titel` bleibt
        in der Stunde stehen, wenn der Knoten verschwindet.
        """
        meta = {
            "phasen": [
                {
                    "id": "p1",
                    "methode": {"typ": "node", "node_id": str(A), "titel": "Galeriegang"},
                    "sozialform": {"typ": "node", "node_id": str(B), "titel": "Partnerarbeit"},
                    "material": [],
                }
            ]
        }
        assert soll_kanten(meta) == {}


# ── plane_abgleich ───────────────────────────────────────────────────────────

class TestPlaneAbgleich:
    def test_neues_material_wird_angelegt(self):
        a = plane_abgleich(ist={}, soll={A: ["p1"]})
        assert a.anlegen == {A: ["p1"]}
        assert a.aktualisieren == {} and a.loeschen == []

    def test_entferntes_material_wird_geloescht(self):
        """Der Punkt, an dem ein reines „anlegen" eine Karteileiche hinterließe."""
        a = plane_abgleich(ist={A: ["p1"]}, soll={})
        assert a.loeschen == [A]
        assert a.anlegen == {} and a.aktualisieren == {}

    def test_unveraendert_ergibt_nichts_zu_tun(self):
        a = plane_abgleich(ist={A: ["p1", "p3"]}, soll={A: ["p1", "p3"]})
        assert a.leer

    def test_verschobene_phase_aktualisiert_statt_neu_anzulegen(self):
        a = plane_abgleich(ist={A: ["p1"]}, soll={A: ["p2"]})
        assert a.aktualisieren == {A: ["p2"]}
        assert a.anlegen == {} and a.loeschen == []

    def test_zusaetzliche_phase_aktualisiert_die_kante(self):
        a = plane_abgleich(ist={A: ["p1"]}, soll={A: ["p1", "p3"]})
        assert a.aktualisieren == {A: ["p1", "p3"]}

    def test_alle_drei_faelle_zugleich(self):
        c = uuid4()
        a = plane_abgleich(ist={A: ["p1"], B: ["p2"]}, soll={A: ["p9"], c: ["p1"]})
        assert a.anlegen == {c: ["p1"]}
        assert a.aktualisieren == {A: ["p9"]}
        assert a.loeschen == [B]
        assert not a.leer

    def test_kante_ohne_verortung_bleibt_stabil(self):
        """Zwei Läufe über eine Phase ohne `id` dürfen nicht dauernd schreiben."""
        assert plane_abgleich(ist={A: []}, soll={A: []}).leer


def test_relation_und_via_sind_festgelegt():
    """Beide sind Vertrag: `via` grenzt eigene Kanten von fremden ab.

    Ohne die Marke fasste der Abgleich auch von Hand gezogene
    `used_with`-Verbindungen an und löschte sie beim nächsten Speichern.
    """
    assert RELATION == "used_with"
    assert VIA == "material"
