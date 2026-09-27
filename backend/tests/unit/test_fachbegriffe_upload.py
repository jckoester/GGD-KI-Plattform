"""Aus hochgeladenen Dateien ein Bündel — mit Grenzen (Paket 10, AP3).

⚠️ **Der Unterschied zum Ordner ist nicht die Herkunft, sondern das Vertrauen.** Das
Admin-Skript liest ein Verzeichnis, das dem Admin gehört. Hier kommt, was eine Lehrkraft
schickt: womöglich groß, viel, mit Pfaden aus dem Bündel heraus oder einem SVG mit
Skript darin. Jede dieser Grenzen hat unten ihren Fall — und jede ist einzeln gebrochen
worden, um zu sehen, dass sie trägt.
"""
import io
import zipfile

import pytest

from app.context.fachbegriffe_upload import (
    BuendelFehler,
    Grenzen,
    baue_buendel,
)

MD = b"---\nknotentyp: begriff\ntitel: Alpha\nfach: Testfach\n---\n\nText.\n"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
SVG_BOESE = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _zip(eintraege: dict[str, bytes]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for pfad, inhalt in eintraege.items():
            z.writestr(pfad, inhalt)
    return puffer.getvalue()


class TestEinzelneDateien:
    def test_markdown_landet_oben(self):
        buendel, warnungen = baue_buendel([("Alpha.md", MD)])
        assert buendel == {"Alpha.md": MD} and warnungen == []

    def test_abbildung_landet_im_abbildungsordner(self):
        """Das Frontmatter schreibt `_Abb/…`; eine einzeln gewählte Datei hat keinen
        Ordner. Sie dorthin zu legen ist der einzige Ort, an dem sie gesucht wird."""
        buendel, _ = baue_buendel([("Alpha.md", MD), ("EN_H2O.svg", SVG)])
        assert set(buendel) == {"Alpha.md", "_Abb/EN_H2O.svg"}

    def test_pfad_im_dateinamen_wird_abgeschnitten(self):
        """Manche Browser schicken bei Ordner-Uploads den ganzen Pfad mit."""
        buendel, _ = baue_buendel([("/home/jan/vault/Alpha.md", MD)])
        assert set(buendel) == {"Alpha.md"}

    def test_fremde_endung_ist_ein_fehler(self):
        """Anders als im Zip: Wer eine Datei einzeln auswählt, meint sie."""
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("Notizen.docx", b"x")])
        assert fehler.value.status == 415

    def test_nichts_verwertbares(self):
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([])
        assert fehler.value.status == 422


class TestZip:
    def test_flaches_archiv(self):
        roh = _zip({"Alpha.md": MD, "_Abb/EN_H2O.svg": SVG})
        buendel, warnungen = baue_buendel([("pilot.zip", roh)])
        assert set(buendel) == {"Alpha.md", "_Abb/EN_H2O.svg"}
        assert warnungen == []

    def test_gepackter_ordner_verliert_seine_ebene(self):
        """⚠️ Im Finder packt man einen **Ordner**. Ohne diesen Schritt läge keine
        einzige Knotendatei oben, und der Import meldete ein leeres Bündel."""
        roh = _zip({"Ch Pilot/Alpha.md": MD, "Ch Pilot/_Abb/EN_H2O.svg": SVG})
        buendel, _ = baue_buendel([("pilot.zip", roh)])
        assert set(buendel) == {"Alpha.md", "_Abb/EN_H2O.svg"}

    def test_nur_abbildungen_behalten_ihren_ordner(self):
        """Gegenfall zum vorigen: `_Abb` ist keine Verpackung, sondern die Absprache."""
        roh = _zip({"_Abb/EN_H2O.svg": SVG})
        buendel, _ = baue_buendel([("bilder.zip", roh)])
        assert set(buendel) == {"_Abb/EN_H2O.svg"}

    def test_zwei_wurzeln_bleiben_stehen(self):
        """Abgeschnitten wird nur, was **alle** teilen — sonst verschöbe sich `_Abb/`.

        Hier bleibt also nichts übrig, und das ist der Fall, in dem die Begründung
        zählt: Wer sein Archiv vor sich hat und die Dateien darin sieht, braucht den
        Satz „eine Ebene zu tief" und nicht „keine verwertbare Datei".
        """
        roh = _zip({"A/Alpha.md": MD, "B/Beta.md": MD})
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("zwei.zip", roh)])
        assert fehler.value.status == 422
        assert "oben im Bündel" in fehler.value.text

    def test_apple_beiwerk_wird_ignoriert(self):
        roh = _zip({"Alpha.md": MD, "__MACOSX/._Alpha.md": b"\x00\x05"})
        buendel, warnungen = baue_buendel([("pilot.zip", roh)])
        assert set(buendel) == {"Alpha.md"} and warnungen == []

    def test_fremde_endungen_werden_gemeldet_nicht_verweigert(self):
        """Ein gepackter Arbeitsordner enthält `.tex`-Quellen und `.DS_Store`. Deshalb
        abzubrechen wäre gegenüber der Fachschaft unhöflich und ohne Gewinn."""
        roh = _zip({"Alpha.md": MD, "quelle.tex": b"\\documentclass{x}"})
        buendel, warnungen = baue_buendel([("pilot.zip", roh)])
        assert set(buendel) == {"Alpha.md"}
        assert any("quelle.tex" in w and "übergangen" in w for w in warnungen)

    def test_knotendatei_im_unterordner_wird_gemeldet(self):
        """Sie würde sonst **stumm** fehlen — `lies_buendel` überspringt Unterordner."""
        roh = _zip({"Alpha.md": MD, "Alt/Beta.md": MD})
        buendel, warnungen = baue_buendel([("pilot.zip", roh)])
        assert set(buendel) == {"Alpha.md"}
        assert any("Alt/Beta.md" in w for w in warnungen)

    def test_kaputtes_archiv(self):
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("pilot.zip", b"PK\x03\x04 kaputt")])
        assert fehler.value.status == 400


class TestPfadeAusDemBuendelHeraus:
    @pytest.mark.parametrize(
        "pfad", ["../heimlich.md", "/etc/passwd.md", "a/../../b.md", "C:/x.md"]
    )
    def test_ausbruchsversuch_bricht_ab(self, pfad):
        """⚠️ Kein Zurechtrücken. Ein `..` im Archiv ist kein Zuschnitt-Problem."""
        roh = _zip({pfad: MD})
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("pilot.zip", roh)])
        assert fehler.value.status == 400

    def test_rueckwaerts_schraegstrich_zaehlt_mit(self):
        """Die Zip-Spezifikation verlangt `/`. Wer `\\` schickt, will an einem Prüfer
        vorbei — der Name bliebe sonst ein einziges Segment ohne `..`."""
        roh = _zip({"..\\\\heimlich.md": MD})
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("pilot.zip", roh)])
        assert fehler.value.status == 400


class TestGrenzen:
    KLEIN = Grenzen(dateien=3, gesamt_bytes=2000, einzeln_bytes=500)

    def test_zu_viele_eintraege_im_archiv(self):
        roh = _zip({f"K{i}.md": MD for i in range(5)})
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("pilot.zip", roh)], grenzen=self.KLEIN)
        assert fehler.value.status == 413

    def test_zu_grosse_einzeldatei(self):
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("Alpha.md", b"x" * 600)], grenzen=self.KLEIN)
        assert fehler.value.status == 413

    def test_zip_bombe_faellt_an_der_kopfangabe(self):
        """⚠️ **Bevor ein Byte entpackt wird.** Ein Megabyte Nullen komprimiert auf
        wenige hundert Byte — das Archiv sieht harmlos aus und ist es nicht."""
        roh = _zip({"Alpha.md": b"\x00" * 100_000})
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([("bombe.zip", roh)], grenzen=self.KLEIN)
        assert fehler.value.status == 413
        assert "entpackt" in fehler.value.text

    def test_gefaelschte_kopfangabe_kommt_nicht_durch(self):
        """Die Kopfangabe steht im Archivverzeichnis und lässt sich fälschen.

        ⚠️ Geprüft wird die **Zusage**, nicht der Weg: Eine kleiner gelogene Größe
        fängt `zipfile` selbst ab (CRC-Summe), eine größere die Deckelprüfung. Auf
        welchen der beiden Wege, ist gleichgültig — durch darf sie nicht.
        """
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Alpha.md", b"x" * 1000)
        roh = bytearray(puffer.getvalue())
        # `file_size` im zentralen Verzeichnis auf 10 herunterlügen.
        stelle = roh.rindex(b"PK\x01\x02")
        roh[stelle + 24:stelle + 28] = (10).to_bytes(4, "little")
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel(
                [("bombe.zip", bytes(roh))],
                grenzen=Grenzen(dateien=3, gesamt_bytes=2000, einzeln_bytes=100),
            )
        assert fehler.value.status in (400, 413)

    def test_summe_ueber_mehrere_dateien(self):
        """Jede für sich unter der Einzelgrenze, zusammen über der Gesamtgrenze."""
        klein = Grenzen(dateien=9, gesamt_bytes=1000, einzeln_bytes=500)
        with pytest.raises(BuendelFehler) as fehler:
            baue_buendel([(f"K{i}.md", b"x" * 400) for i in range(3)], grenzen=klein)
        assert fehler.value.status == 413

    def test_archiv_darf_groesser_sein_als_eine_einzeldatei(self):
        """Ein Zip ist die Sammlung, keine einzelne Datei. Mit der Einzelgrenze
        gemessen wäre eine vollständige Fachschaftssammlung abgelehnt worden."""
        roh = _zip({f"K{i}.md": MD for i in range(3)})
        assert len(roh) > 300
        buendel, _ = baue_buendel(
            [("pilot.zip", roh)], grenzen=Grenzen(dateien=5, gesamt_bytes=9000, einzeln_bytes=300)
        )
        assert len(buendel) == 3


class TestAbbildungspruefung:
    def test_svg_mit_skript_kommt_nicht_ins_buendel(self):
        buendel, warnungen = baue_buendel([("Alpha.md", MD), ("boese.svg", SVG_BOESE)])
        assert set(buendel) == {"Alpha.md"}
        assert any("boese.svg" in w and "abgelehnt" in w for w in warnungen)

    def test_auch_aus_dem_archiv(self):
        roh = _zip({"Alpha.md": MD, "_Abb/boese.svg": SVG_BOESE})
        buendel, warnungen = baue_buendel([("pilot.zip", roh)])
        assert set(buendel) == {"Alpha.md"}
        assert any("abgelehnt" in w for w in warnungen)

    def test_die_datei_bleibt_der_lauf_auch(self):
        """Eine abgelehnte Abbildung kostet das Bild, nicht den Knoten — dieselbe
        Verhältnismäßigkeit wie bei einem verworfenen Metadatenfeld."""
        buendel, _ = baue_buendel([("Alpha.md", MD), ("boese.svg", SVG_BOESE)])
        assert buendel["Alpha.md"] == MD

    def test_kaputte_kodierung_einer_abbildung(self):
        buendel, warnungen = baue_buendel([("Alpha.md", MD), ("krumm.svg", b"\xff\xfe\x00")])
        assert set(buendel) == {"Alpha.md"}
        assert any("UTF-8" in w for w in warnungen)
