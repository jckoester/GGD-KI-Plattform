"""Der Schreibteil des Exports, ohne Datenbank (Paket 10, AP5).

Ob der Kreis aufgeht, prüft `tests/integration/test_fachbegriffe_rundreise.py` — das ist
die eigentliche Zusage. Hier stehen die Einzelteile, die dort nur gemeinsam sichtbar
werden: die Umkehrung der Abschnitte, die Zuordnung Kante → Frontmatter-Feld und der
Dateiname.
"""
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.context import fachbegriffe_export as ex


class TestAbschnitteZurueck:
    def test_text_ohne_ueberschrift_ist_die_definition(self):
        """In `content` steht die Definition **ohne** Überschrift — die Taxonomie nennt
        das Feld selbst so. In der Datei bekommt sie ihren Namen zurück."""
        assert ex._abschnitte_aus_content("Ein Satz.") == [("Definition", "Ein Satz.")]

    def test_dritte_ebene_wird_zur_zweiten(self):
        """⚠️ Der Leser schreibt `### Erklärung` in `content`, die Datei trägt `##`.
        Eine Stufe daneben, und der Wiedereinleseschritt findet keinen Abschnitt mehr."""
        teile = ex._abschnitte_aus_content("Kurz.\n\n### Erklärung\n\nLang.")
        assert teile == [("Definition", "Kurz."), ("Erklärung", "Lang.")]

    def test_leere_bloecke_fallen_weg(self):
        assert ex._abschnitte_aus_content("### Erklärung\n\nNur das.") == [
            ("Erklärung", "Nur das.")
        ]

    def test_leerer_inhalt(self):
        assert ex._abschnitte_aus_content("") == []


class TestEinbettungen:
    def test_platzhalter_wird_wieder_obsidian(self):
        """Für den Rundgang gleichgültig, für den Menschen nicht: Wer die Datei im
        Vault öffnet, soll das Bild sehen."""
        assert ex._mit_einbettungen("Vor {{abbildung:EN_H2O.svg}} nach") == (
            "Vor ![[EN_H2O.svg]] nach"
        )

    def test_ohne_platzhalter_unveraendert(self):
        assert ex._mit_einbettungen("Nur Text") == "Nur Text"


class TestLesarten:
    def test_eine_art(self):
        assert ex._arten({"art": "vertiefung"}) == ["vertiefung"]

    def test_ohne_art(self):
        assert ex._arten({}) == [""]

    def test_mehrere_gehen_vor(self):
        """⚠️ `arten` schlägt `art`. Eine Kante kann aus zwei Nennungen entstanden sein;
        nur die Gewinner-Art zurückzuschreiben verlöre die andere bei jedem Rundgang."""
        assert ex._arten({"art": "vertiefung", "arten": ["abgrenzung", "vertiefung"]}) == [
            "abgrenzung", "vertiefung"
        ]


class TestKantenfelder:
    def _felder(self, knotentyp, kanten):
        warnungen: list[str] = []
        return (*ex._kantenfelder(knotentyp, kanten, warnungen), warnungen)

    def test_oberbegriff_und_stoffklasse_sind_dieselbe_relation(self):
        """Die Datenbank sähe keinen Unterschied — die Fachschaft schon."""
        felder, _, _, _ = self._felder("begriff", [("is_a", "Ober", {})])
        assert felder == {"oberbegriff": ["[[Ober]]"]}
        felder, _, _, _ = self._felder("stoffsteckbrief", [("is_a", "Ober", {})])
        assert felder == {"stoffklasse": ["[[Ober]]"]}

    def test_abgrenzung_wird_eine_textzeile(self):
        _, zeilen, _, _ = self._felder(
            "begriff",
            [("related_to", "Beta", {"art": "abgrenzung", "hinweis": "anderes Ding"})],
        )
        assert zeilen == ["[[Beta]] – anderes Ding"]

    def test_abgrenzung_ohne_hinweis(self):
        _, zeilen, _, _ = self._felder(
            "begriff", [("related_to", "Beta", {"art": "abgrenzung"})]
        )
        assert zeilen == ["[[Beta]]"]

    def test_ghs_kommt_nicht_aus_den_kanten(self):
        """Es steht wörtlich in `metadata.ghs` und wird von dort geschrieben — samt
        `gilt_fuer`, das an der Kante hängt. Zweimal wäre doppelt."""
        felder, zeilen, _, warnungen = self._felder(
            "stoffsteckbrief", [("related_to", "GHS02 Flamme", {"art": "ghs"})]
        )
        assert felder == {} and zeilen == [] and warnungen == []

    def test_fundstellen_gehen_ins_bildungsplanfeld(self):
        _, _, fundstellen, _ = self._felder(
            "begriff", [("references", "", {"fundstelle": "CH.V2 3.2.1.1 (1)"})]
        )
        assert fundstellen == ["CH.V2 3.2.1.1 (1)"]

    def test_ziel_ausserhalb_des_fachs_wird_gemeldet(self):
        """Der Zielname ist leer, weil der Knoten nicht im Bündel steht. Eine Kante
        ohne benennbares Ziel kann das Format nicht tragen — das gehört gesagt."""
        _, _, _, warnungen = self._felder("begriff", [("related_to", "", {})])
        assert warnungen and "außerhalb" in warnungen[0]

    def test_unbekannte_relation_wird_gemeldet(self):
        _, _, _, warnungen = self._felder("begriff", [("part_of", "Beta", {})])
        assert warnungen and "part_of" in warnungen[0]

    def test_doppelte_ziele_stehen_einmal(self):
        felder, _, _, _ = self._felder(
            "begriff", [("related_to", "Beta", {}), ("related_to", "Beta", {})]
        )
        assert felder == {"verwandt": ["[[Beta]]"]}


class TestDateiname:
    class _Knoten:
        def __init__(self, metadata, title):
            self.metadata_ = metadata
            self.title = title

    def test_herkunftsdatei_hat_vorrang(self):
        """⚠️ Sonst würde aus „Oxidation (Sauerstoffaufnahme).md" ein „Oxidation.md" —
        und beim nächsten Lauf ein zweiter Knoten, solange keine `id` in der Datei steht."""
        knoten = self._Knoten(
            {"seed_quelle": "Oxidation (Sauerstoffaufnahme)"}, "Oxidation"
        )
        assert ex._dateiname(knoten, set()) == "Oxidation (Sauerstoffaufnahme)"

    def test_sonst_der_titel(self):
        assert ex._dateiname(self._Knoten({}, "Neuer Begriff"), set()) == "Neuer Begriff"

    def test_bei_gleichem_namen_gewinnt_die_kennung(self):
        """Ein angehängtes „(2)" hinge davon ab, welcher Knoten zuerst drankommt; die
        Kennung ist je Fach eindeutig und ändert sich nicht."""
        knoten = self._Knoten({"seed_id": "ch-zweiter"}, "Oxidation")
        assert ex._dateiname(knoten, {"Oxidation"}) == "ch-zweiter"

    @pytest.mark.parametrize(
        "roh,erwartet",
        [
            ("A/B", "A-B"),          # `/` zerlegte den Pfad im Bündel
            ("_Format", "Format"),   # führender Unterstrich würde beim Import übergangen
        ],
    )
    def test_gefaehrliche_zeichen(self, roh, erwartet):
        assert ex._dateiname(self._Knoten({}, roh), set()) == erwartet
