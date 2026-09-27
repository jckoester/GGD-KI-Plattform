"""Der Leser des Fachbegriff-Imports (Paket 9/AP5, Paket 10/AP1).

Geprüft wird der **datenbankfreie** Teil von `app/context/fachbegriffe_import.py`:
Frontmatter, Abschnitte, Abgrenzungszeilen, Fundstellen, Abbildungen, Idempotenz-Hash.
Der Schreibteil braucht eine Datenbank und steht in
`tests/integration/test_seed_fachbegriffe_db.py`.

⚠️ **Seit 27.09.2026 nicht mehr aus dem Skript geladen.** Der Kern liegt im
Anwendungspaket, weil ab Paket 10 zwei Wege ihn benutzen — das Admin-Skript und der
Upload-Dialog. Die Eingabe ist deshalb ein **Bündel** (Pfad → Bytes) statt eines
Ordners; `_buendel()` unten baut es aus dem Fixture-Verzeichnis.

⚠️ **Die Fixtures sind erfunden** (`tests/fixtures/fachbegriffe/`). Keine GGD-Inhalte im
Repo — die Pilotdateien gehören der Fachschaft, nicht dem Projekt (Leitplanke 3). Jede
Eigenart, die im echten Pilot vorkam, hat dort ihren Fall: mehrere Wikilinks in einer
Abgrenzungszeile, ein Abschnitt außerhalb des Formats, ein ungültiger Auswahlwert, ein
GHS-Eintrag mit Bedingung, ein fehlendes SVG.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.context import fachbegriffe_import

VAULT = Path(__file__).resolve().parents[1] / "fixtures" / "fachbegriffe"


def _buendel() -> dict[str, bytes]:
    """Das Fixture-Verzeichnis als Bündel — wie der Endpunkt es aus einem Zip baut."""
    dateien = {p.name: p.read_bytes() for p in sorted(VAULT.glob("*.md"))}
    dateien |= {
        f"_Abb/{p.name}": p.read_bytes() for p in sorted((VAULT / "_Abb").glob("*"))
    }
    return dateien


def _lies(dateiname: str):
    """Eine Fixture-Datei einlesen — `lies_datei` nimmt Name und Text, keinen Pfad."""
    pfad = VAULT / dateiname
    return fachbegriffe_import.lies_datei(pfad.stem, pfad.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed():
    return fachbegriffe_import


@pytest.fixture(scope="module")
def fiktivum(seed):
    return _lies("Fiktivum.md")


@pytest.fixture(scope="module")
def teststoff(seed):
    return _lies("Teststoff.md")


class TestWasGelesenWird:
    def test_fremder_knotentyp_wird_uebergangen(self, seed):
        """Ein `arbeitsblatt` im Ordner ist kein Fehler — es gehört nur nicht hierher."""
        assert _lies("Fremdling.md") is None

    def test_datei_ohne_frontmatter_scheitert_laut(self, seed):
        """⚠️ Kein stilles Überspringen: Das ist ein Fehler **in der Datei**.

        Eine Datei, die niemand importiert und die sich auch nicht beschwert, fällt
        beim Zählen nicht auf — und genau danach sieht man im Bericht nicht.
        """
        with pytest.raises(ValueError, match="Frontmatter"):
            seed.lies_datei("Kaputt", "## Definition\n\nOhne Frontmatter.\n")

    def test_kopfdaten(self, fiktivum):
        assert fiktivum.datei == "Fiktivum"      # Dateiname = Schlüssel für Wikilinks
        assert fiktivum.titel == "Fiktivum"
        assert fiktivum.knotentyp == "begriff"
        assert fiktivum.fach == "Testfach"

    def test_aliase_bereinigt_und_in_reihenfolge(self, fiktivum):
        """Leeres weg, Dubletten weg — die Reihenfolge ist Teil der Daten."""
        assert fiktivum.aliase == ["Fikt", "Fiktivum"]

    def test_nur_schemafelder_werden_metadata(self, fiktivum):
        """`bildungsplan`, `oberbegriff`, `verwandt` steuern den Seed — sie sind keine
        Eigenschaften des Knotens und hätten am Knoten nichts verloren."""
        assert fiktivum.metadata["fassung"] == "Grundfassung"
        assert fiktivum.metadata["ab_klasse"] == 8
        assert "bildungsplan" not in fiktivum.metadata
        assert "oberbegriff" not in fiktivum.metadata
        assert "verwandt" not in fiktivum.metadata
        assert "knotentyp" not in fiktivum.metadata

    def test_freie_metadaten_gehen_mit(self, teststoff):
        """`eigenschaften` ist ein verschachteltes Objekt und deshalb kein Feld im
        Schema (AP2b) — mitgeschrieben wird es trotzdem."""
        assert teststoff.metadata["eigenschaften"]["schmelztemperatur"] == "42 °C"
        assert teststoff.metadata["trivialnamen"] == ["Wunderpulver"]


class TestContent:
    def test_definition_ohne_ueberschrift_am_anfang(self, fiktivum):
        """Das Feld heißt selbst „Definition" — eine Überschrift darüber wäre doppelt.

        Zugleich der Grund, warum sie **zuerst** steht: Die 800-Zeichen-Kürzung fürs
        Modell (AP3) schneidet von hinten.
        """
        assert fiktivum.content.startswith("Ein Fiktivum ist ein erfundener Begriff")

    def test_weitere_abschnitte_als_ueberschrift(self, fiktivum):
        assert "### Erklärung" in fiktivum.content
        assert "### Beispiele" in fiktivum.content

    def test_unbekannter_abschnitt_geht_mit_und_wird_gemeldet(self, fiktivum):
        """⚠️ Nicht verschwinden lassen. Im Pilot war das `## Darstellung` — von Hand
        geschriebener Fachtext, den das Format nicht kennt."""
        assert "### Darstellung" in fiktivum.content
        assert any("Darstellung" in w for w in fiktivum.warnungen)

    def test_offene_fragen_bleiben_draussen(self, fiktivum):
        assert "darf nirgends auftauchen" not in fiktivum.content

    def test_abgrenzung_bleibt_aus_dem_content(self, fiktivum):
        """Derselbe Grund wie bei den Fehlvorstellungen: Sie sagt, was der Begriff
        **nicht** ist, und zöge im Vektor genau die Fragen an, die sie abgrenzt."""
        assert "ist etwas anderes" not in fiktivum.content

    def test_fehlvorstellungen_werden_metadata(self, fiktivum):
        assert fiktivum.metadata["fehlvorstellungen"] == [
            "„Ein Fiktivum ist echt.“ – Ist es nicht.",
            "Zweiter Irrtum.",
        ]

    def test_wikilinks_im_text_werden_klartext(self, fiktivum):
        """Keine Kante — Kanten entstehen nur aus Frontmatter und `## Abgrenzung`."""
        assert "[[" not in fiktivum.content
        assert "Siehe Sammelbegriff und die Nebensache." in fiktivum.content

    def test_einbettung_wird_platzhalter(self, fiktivum):
        """Die Absprache mit AP3 (Beschreibung fürs Modell) und AP6 (SVG in der UI)."""
        assert "{{abbildung:schema.svg}}" in fiktivum.content
        assert "![[" not in fiktivum.content


class TestKanten:
    def _kanten(self, quelle, relation=None, art=None):
        return sorted(
            k.ziel_datei for k in quelle.kanten
            if (relation is None or k.relation == relation)
            and (art is None or k.metadata.get("art") == art)
        )

    def test_oberbegriff_wird_is_a(self, fiktivum):
        assert self._kanten(fiktivum, "is_a") == ["Sammelbegriff"]

    def test_stoffklasse_wird_is_a(self, teststoff):
        """Beim Steckbrief heißt `is_a` „gehört zur Stoffklasse" (Taxonomie AP2b)."""
        assert self._kanten(teststoff, "is_a") == ["Sammelbegriff"]

    def test_voraussetzung_wird_requires(self, fiktivum):
        assert self._kanten(fiktivum, "requires") == ["Vorwissen"]

    def test_vertiefung_traegt_ihre_art(self, fiktivum):
        assert self._kanten(fiktivum, art="vertiefung") == ["Fiktivum (vertieft)"]

    def test_teilchen_und_ghs_als_related_to_mit_art(self, teststoff):
        """Der Knotentyp führt `is_a`, `related_to` und `references` — mehr zu
        erfinden hieße, die Typentscheidung aus AP2b im Seed zu überstimmen."""
        assert self._kanten(teststoff, art="ghs") == ["Nebensache"]
        assert self._kanten(teststoff, art="teilchen") == ["Vorwissen"]

    def test_zwei_arten_auf_einem_ziel_entscheidet_der_rang(self, teststoff):
        """⚠️ Das Fixture nennt „Vorwissen" als Teilchen **und** als Piktogramm.

        Zwei Kanten kann die Datenbank nicht halten (eindeutiger Index über
        `from/to/relation`), also gewinnt eine — und zwar nach `ART_RANG`, nicht nach
        der Zahl der Metadatenschlüssel. Genau daran war die erste Fassung falsch: Bei
        „Redoxreaktion (Sauerstoffübertragung)" gewann die Abgrenzung (mit Hinweistext)
        über die Vertiefung, und damit fiel der Lernpfad weg.
        """
        [kante] = [k for k in teststoff.kanten if k.ziel_datei == "Vorwissen"]
        assert kante.metadata["art"] == "teilchen"
        # Nichts geht verloren: Die Angaben der unterlegenen Nennung wandern mit.
        assert kante.metadata["gilt_fuer"] == "ab 0,1 mol/L"
        assert kante.metadata["arten"] == ["ghs", "teilchen"]

    def test_vertiefung_gewinnt_ueber_abgrenzung(self, seed):
        """Der Fall aus dem Pilot, wegen dem es `ART_RANG` gibt.

        Dieselbe Fassung ist zugleich Abgrenzung und Vertiefung; die Vertiefung ist die
        Aussage, der eine Traversierung folgt (ADR-013).
        """
        kanten = seed.vereinige([
            seed.Kante("related_to", "Z", {"art": "abgrenzung", "hinweis": "Spezialfall"}),
            seed.Kante("related_to", "Z", {"art": "vertiefung"}),
        ])
        assert len(kanten) == 1
        assert kanten[0].metadata["art"] == "vertiefung"
        assert kanten[0].metadata["hinweis"] == "Spezialfall"
        assert kanten[0].metadata["arten"] == ["abgrenzung", "vertiefung"]

    def test_nennung_ohne_art_faellt_weg(self, seed):
        """`verwandt` sagt nichts, was `grenzt sich ab von` nicht auch sagt."""
        kanten = seed.vereinige([
            seed.Kante("related_to", "Z", {}),
            seed.Kante("related_to", "Z", {"art": "abgrenzung", "hinweis": "x"}),
        ])
        assert len(kanten) == 1 and kanten[0].metadata["art"] == "abgrenzung"
        # Keine Sammelangabe, wo es nichts zu sammeln gibt.
        assert "arten" not in kanten[0].metadata

    def test_ghs_bedingung_wird_kanten_metadata(self, teststoff):
        """„ab 0,1 mol/L" ist eine Eigenschaft der **Beziehung**: Sonst stünde am
        Piktogramm die Konzentration eines einzelnen Stoffs."""
        [kante] = [k for k in teststoff.kanten if k.metadata.get("gilt_fuer")]
        assert kante.ziel_datei == "Vorwissen"
        assert kante.metadata["gilt_fuer"] == "ab 0,1 mol/L"

    def test_unbrauchbarer_ghs_eintrag_wird_gemeldet(self, teststoff):
        assert any("GHS-Eintrag" in w for w in teststoff.warnungen)

    def test_abgrenzung_mit_hinweis(self, fiktivum):
        [kante] = [
            k for k in fiktivum.kanten
            if k.metadata.get("art") == "abgrenzung" and k.ziel_datei == "Nebensache"
        ]
        assert kante.metadata["hinweis"] == "ist etwas anderes; siehe den A–B-Vergleich."

    def test_mehrere_ziele_in_einer_abgrenzungszeile(self, fiktivum):
        """⚠️ Im Pilot echt vorgekommen („[[Natrium]] und [[Chlor]] – die Elemente").
        Ein Ausdruck, der nur den ersten Link nimmt, verliert die halbe Aussage."""
        beide = [
            k for k in fiktivum.kanten
            if k.metadata.get("hinweis") == "gelten beide gemeinsam."
        ]
        assert sorted(k.ziel_datei for k in beide) == ["Sammelbegriff", "Vorwissen"]

    def test_keine_abgrenzung_ist_keine_warnung(self, fiktivum):
        """`(keine)` ist die ausdrückliche Angabe, dass es nichts abzugrenzen gibt."""
        assert not any("(keine)" in w for w in fiktivum.warnungen)

    def test_abgrenzung_ohne_wikilink_wird_gemeldet(self, fiktivum):
        assert any("Abgrenzung ohne Wikilink" in w for w in fiktivum.warnungen)

    def test_doppelt_genanntes_ziel_ergibt_eine_kante(self, fiktivum):
        """„Sammelbegriff" steht unter `verwandt` **und** in der Abgrenzung.

        Die aussagekräftigere gewinnt: Der Hinweistext wäre sonst weg, und im Graphen
        stünde eine doppelte Linie.
        """
        treffer = [
            k for k in fiktivum.kanten
            if k.relation == "related_to" and k.ziel_datei == "Sammelbegriff"
        ]
        assert len(treffer) == 1
        assert treffer[0].metadata["art"] == "abgrenzung"


class TestFundstellen:
    def test_kompetenz(self, seed):
        f = seed.lies_fundstelle("CH.V2 3.2.1.3 (3)")
        assert (f.fach_code, f.suffix, f.content_type) == ("CH", ".V2", "ik_kompetenz")
        assert f.schluessel == "3.2.1.3(3)"

    def test_dreistellige_nummer(self, seed):
        """V3 nummeriert flacher (`3.1.1`) — der Ausdruck darf das nicht erzwingen."""
        f = seed.lies_fundstelle("CH.V3 3.1.1 (2)")
        assert f.schluessel == "3.1.1(2)" and f.suffix == ".V3"

    def test_einleitung_zeigt_auf_die_leitidee(self, seed):
        f = seed.lies_fundstelle("CH.V2 3.2.1.1 Einl.")
        assert f.content_type == "leitidee" and f.schluessel == "3.2.1.1"

    def test_basisedition_ohne_suffix(self, seed):
        assert seed.lies_fundstelle("CH 3.2.1.1 (1)").suffix == ""

    def test_unlesbares_gibt_none(self, seed):
        assert seed.lies_fundstelle("Unsinn") is None
        assert seed.lies_fundstelle("") is None

    def test_schluessel_trennt_1_von_10(self, seed):
        """⚠️ Der Grund, warum gegen `metadata.kompetenz_nr` aufgelöst wird und nicht
        gegen den Titel: Ein Präfix `3.2.1.1(1)` trifft auch `(10)` bis `(12)`."""
        assert seed.lies_fundstelle("CH.V2 3.2.1.1 (1)").schluessel == "3.2.1.1(1)"
        assert seed.lies_fundstelle("CH.V2 3.2.1.1 (10)").schluessel == "3.2.1.1(10)"


class TestAbbildungen:
    def test_svg_wird_eingelesen(self, seed, fiktivum):
        metadata = {"illustrationen": [dict(a) for a in fiktivum.metadata["illustrationen"]]}
        fehlend = seed.lade_svg(metadata, _buendel())
        assert metadata["illustrationen"][0]["svg"].startswith("<svg")
        assert fehlend == ["_Abb/fehlt.svg"]

    def test_tex_bleibt_pfadangabe(self, seed, fiktivum):
        """Die Quelle einer Strukturformel ist ein Arbeitsmittel des Autors, kein
        Inhalt des Wissensgraphen."""
        metadata = {"illustrationen": [dict(a) for a in fiktivum.metadata["illustrationen"]]}
        seed.lade_svg(metadata, _buendel())
        assert metadata["illustrationen"][0]["tex"] == "Irgendwo/im/Vault/schema.tex"

    def test_platzhalter_ohne_eintrag_wird_gemeldet(self, seed, fiktivum):
        """Sonst steht in der Oberfläche eine leere Stelle und beim Modell ein nacktes
        `[Abbildung]` — und niemand erfährt, dass ein Bild fehlt."""
        assert seed.pruefe_abbildungen(fiktivum) == []

        from dataclasses import replace
        ohne = replace(fiktivum, content="{{abbildung:unbekannt.svg}}")
        assert seed.pruefe_abbildungen(ohne) == ["unbekannt.svg"]


class TestMetadataBereinigung:
    def test_ungueltiger_auswahlwert_kostet_nur_das_feld(self, seed):
        """⚠️ Im Pilot echt vorgekommen (`genus: "der (Stoff)"`).

        Über einen Artikel die Definition, die Aliase und elf Kanten zu verlieren,
        stünde in keinem Verhältnis — gemeldet wird es trotzdem.
        """
        metadata = {"genus": "der (Stoff)", "plural": "Stoffe"}
        warnungen = seed.bereinige_metadata("begriff", metadata)
        assert metadata == {"plural": "Stoffe"}
        assert len(warnungen) == 1 and "genus" in warnungen[0]

    def test_gueltiges_bleibt_unangetastet(self, seed):
        metadata = {"genus": "das", "ab_klasse": 8, "fehlvorstellungen": ["x"]}
        assert seed.bereinige_metadata("begriff", dict(metadata)) == []


class TestStandHash:
    def test_gleicher_stand_gleicher_hash(self, seed):
        a = seed.stand_hash("T", "Text", {"x": 1}, ["a"])
        b = seed.stand_hash("T", "Text", {"x": 1}, ["a"])
        assert a == b

    def test_jede_zutat_zaehlt(self, seed):
        grund = seed.stand_hash("T", "Text", {"x": 1}, ["a"])
        assert seed.stand_hash("U", "Text", {"x": 1}, ["a"]) != grund
        assert seed.stand_hash("T", "Anders", {"x": 1}, ["a"]) != grund
        assert seed.stand_hash("T", "Text", {"x": 2}, ["a"]) != grund
        assert seed.stand_hash("T", "Text", {"x": 1}, ["b"]) != grund

    def test_die_seed_schluessel_zaehlen_nicht(self, seed):
        """Sonst hinge der Hash von sich selbst ab und wäre nie wieder gleich."""
        ohne = seed.stand_hash("T", "Text", {"x": 1}, [])
        mit = seed.stand_hash(
            "T", "Text", {"x": 1, "seed_hash": "egal", "seed_quelle": "T"}, []
        )
        assert ohne == mit


class TestSkriptHuelle:
    """Die Ordner-Ebene ist das Einzige, was nur das Admin-Skript kennt (Paket 10, AP1).

    Der Rest liegt im Service; dass beide Wege **dieselbe Bilanz** ergeben, prüft
    `tests/integration/test_seed_fachbegriffe_db.py`. Hier geht es nur um den Schritt
    davor: Aus einem Ordner muss dasselbe Bündel werden, das ein Zip liefern würde.
    """

    def test_ordner_wird_zum_selben_buendel(self):
        import importlib.util

        pfad = Path(__file__).resolve().parents[2] / "scripts" / "seed_fachbegriffe.py"
        spec = importlib.util.spec_from_file_location("seed_fachbegriffe", pfad)
        skript = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(skript)

        assert skript.lies_ordner(VAULT) == _buendel()

    def test_das_buendel_enthaelt_auch_die_abbildungen(self):
        """⚠️ Ohne `_Abb/` fände `lade_svg` nichts und meldete jede Illustration als
        fehlend — der Ordnerleser muss den Unterordner mitnehmen, obwohl `*.md` ihn
        nicht trifft."""
        assert any(name.startswith("_Abb/") for name in _buendel())


class TestWelcheDateienGelesenWerden:
    """Der Filter des Bündels (Paket 10, AP1) — er entscheidet, was überhaupt ankommt."""

    def test_unterstrich_dateien_bleiben_stumm(self, seed):
        """⚠️ **Nicht nur „wird übersprungen", sondern „ohne Warnung".**

        `_Format.md` hat kein Frontmatter. Ohne den Filter liefe sie in `lies_datei`,
        bekäme dort zu Recht ein `ValueError` („kein Frontmatter") und stünde bei
        **jedem** Lauf als „nicht lesbar" im Bericht. Ein Bericht, in dem immer dieselbe
        Warnung steht, wird nicht mehr gelesen — und genau dann geht die echte unter.
        """
        bilanz = seed.Bilanz()
        seed.lies_buendel(_buendel(), bilanz)
        assert not [w for w in bilanz.warnungen if w.startswith("_")]

    def test_unterordner_werden_nicht_als_knoten_gelesen(self, seed):
        """Eine `.md` unter `_Abb/` wäre ein Knoten aus einem Anhangverzeichnis."""
        bilanz = seed.Bilanz()
        gelesen = seed.lies_buendel(
            {"_Abb/Notiz.md": b"---\nknotentyp: begriff\ntitel: X\n---\n\nText.\n"},
            bilanz,
        )
        assert gelesen == [] and bilanz.warnungen == []

    def test_kaputte_kodierung_landet_im_bericht(self, seed):
        """Aus einem Zip kommen Bytes; eine Datei in Latin-1 darf den Lauf nicht kippen."""
        bilanz = seed.Bilanz()
        gelesen = seed.lies_buendel({"Kaputt.md": "---\ntitel: Café\n---\n".encode("latin-1")}, bilanz)
        assert gelesen == []
        assert any("UTF-8" in w for w in bilanz.warnungen), bilanz.warnungen
