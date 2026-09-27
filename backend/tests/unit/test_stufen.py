"""Passt ein Baustein zur Klassenstufe? (Paket 9, Nachgang N6)

⚠️ **Die Regel steht hier, nicht in der Komponente.** Sie ist an der Oberfläche nicht
zu erkennen: Ob „Oxidation (Elektronenabgabe)" für eine Neuntklässlerin „kommt ab
Klasse 10" heißt oder für eine Elftklässlerin gar nichts, entscheidet ein Vergleich
**zwischen** den Treffern — nicht der einzelne Knoten.
"""

from app.context.stufen import (
    FRUEHER,
    VORWISSEN,
    sortiere_passende_nach_vorn,
    vermerke,
)


def _begriff(knoten_id, titel, ab_klasse=None, typ="begriff"):
    return {
        "node_id": knoten_id, "title": titel, "content_type": typ,
        "metadata": {"ab_klasse": ab_klasse} if ab_klasse is not None else {},
    }


OXIDATION = [
    _begriff("elektron", "Oxidation", 10),
    _begriff("sauerstoff", "Oxidation", 8),
]


class TestFassungen:
    def test_klasse_9_bekommt_die_spaetere_gekennzeichnet(self):
        """Der Fall aus Szenario (a). Vor N6 standen beide Fassungen ununterscheidbar
        da — die spätere sogar zuerst."""
        assert vermerke(OXIDATION, 9, {}) == {"elektron": "kommt ab Klasse 10"}

    def test_klasse_11_bekommt_die_frühere_als_vorwissen(self):
        """Umgekehrt: Wer schon weiter ist, soll die alte Fassung als solche erkennen
        — nicht als konkurrierende Definition."""
        assert vermerke(OXIDATION, 11, {}) == {"sauerstoff": VORWISSEN}

    def test_klasse_10_genau_an_der_grenze(self):
        """`ab_klasse: 10` heißt „ab", nicht „nach"."""
        assert vermerke(OXIDATION, 10, {}) == {"sauerstoff": VORWISSEN}

    def test_einzelne_fassung_ist_kein_vorwissen(self):
        """⚠️ Ohne den Vergleich untereinander wäre jeder Begriff mit `ab_klasse`
        unterhalb der Stufe „Vorwissen" — also fast jeder."""
        allein = [_begriff("a", "Donator-Akzeptor-Prinzip", 10)]
        assert vermerke(allein, 11, {}) == {}

    def test_gleiche_stufe_verschiedene_begriffe_stoeren_sich_nicht(self):
        """Der Titel gruppiert, nicht die Stufe."""
        gemischt = [_begriff("a", "Oxidation", 8), _begriff("b", "Reduktion", 10)]
        assert vermerke(gemischt, 11, {}) == {}


class TestBildungsplanBand:
    def test_spaeterer_stoff_wird_angekuendigt(self):
        treffer = [_begriff("a", "Stöchiometrie")]
        assert vermerke(treffer, 8, {"a": (10, 10)}) == {"a": "kommt ab Klasse 10"}

    def test_frueherer_stoff_heisst_nicht_fassung(self):
        """⚠️ Zwei verschiedene Sachen, zwei verschiedene Wörter: Eine frühere
        **Fassung** desselben Begriffs ist etwas anderes als ein Begriff, der früher
        dran war."""
        treffer = [_begriff("a", "Gemisch")]
        assert vermerke(treffer, 12, {"a": (8, 10)}) == {"a": FRUEHER}
        assert FRUEHER != VORWISSEN

    def test_im_band_kein_vermerk(self):
        assert vermerke([_begriff("a", "Gemisch")], 9, {"a": (8, 10)}) == {}

    def test_ohne_fundstelle_keine_aussage(self):
        """Kein Band heißt: Wir wissen es nicht — nicht: passt."""
        assert vermerke([_begriff("a", "Gemisch")], 9, {}) == {}

    def test_ab_klasse_schlaegt_das_band(self):
        """Eine ausdrücklich gepflegte Stufe ist genauer als die Ableitung."""
        treffer = [_begriff("a", "Oxidation", 8), _begriff("b", "Oxidation", 10)]
        assert vermerke(treffer, 9, {"a": (11, 12), "b": (11, 12)}) == {
            "b": "kommt ab Klasse 10"
        }


class TestGrenzfaelle:
    def test_unbekannte_stufe_vermerkt_nichts(self):
        """Auf eine Vorgabe auszuweichen hieße, jeden Erwachsenen ohne Jahrgang wie
        eine Achtklässlerin zu behandeln."""
        assert vermerke(OXIDATION, None, {"elektron": (8, 10)}) == {}

    def test_andere_knotenarten_bekommen_keinen_vermerk(self):
        """Eine Bildungsplan-Kompetenz trägt ihre Stufe im Titel, ein Arbeitsblatt hat
        keine."""
        treffer = [_begriff("a", "3.2.1.1(1) …", typ="ik_kompetenz")]
        assert vermerke(treffer, 9, {"a": (11, 12)}) == {}

    def test_ab_klasse_muss_eine_zahl_sein(self):
        """`true` ist in Python ein `int` — ohne die Prüfung ginge es als Klasse 1 durch."""
        treffer = [{"node_id": "a", "title": "X", "content_type": "begriff",
                    "metadata": {"ab_klasse": True}}]
        assert vermerke(treffer, 9, {}) == {}


class TestSortierung:
    def test_passendes_nach_vorn(self):
        sortiert = sortiere_passende_nach_vorn(OXIDATION, {"elektron": "kommt ab Klasse 10"})
        assert [t["node_id"] for t in sortiert] == ["sauerstoff", "elektron"]

    def test_stabil_innerhalb_der_gruppen(self):
        """⚠️ Die Reihenfolge innerhalb einer Gruppe stammt aus der Suche — sie ist
        nach Ähnlichkeit sortiert und darf nicht durcheinandergeraten."""
        treffer = [_begriff(k, k) for k in ("a", "b", "c", "d")]
        sortiert = sortiere_passende_nach_vorn(treffer, {"a": "kommt ab Klasse 10"})
        assert [t["node_id"] for t in sortiert] == ["b", "c", "d", "a"]

    def test_ohne_vermerke_unveraendert(self):
        assert sortiere_passende_nach_vorn(OXIDATION, {}) == OXIDATION
