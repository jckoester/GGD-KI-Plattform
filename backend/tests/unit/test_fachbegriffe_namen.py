"""Umlaute in Dateinamen beim Fachbegriffe-Import (0.14, Schritt 8).

Ein Zip ohne UTF-8-Kennzeichen, dessen Namen trotzdem UTF-8 sind — so schreibt es u. a.
macOS —, las `zipfile` als CP437. Aus `Hückel-Regel` (zerlegt: `u` + U+0308) wurde
`Hu╠êckel-Regel` und die Kennung `ch-hu-ckel-regel`.
"""
import io
import unicodedata
import zipfile

import pytest

from app.context.fachbegriffe_namen import zurueckgelesen
from app.context.fachbegriffe_upload import eintragsname

NFD = unicodedata.normalize("NFD", "Hückel-Regel")


def zip_ohne_kennzeichen(name_bytes: bytes, inhalt: bytes = b"x") -> bytes:
    """Ein Archiv, dessen Eintragsname aus genau diesen Bytes besteht — **ohne**
    UTF-8-Kennzeichen. `zipfile` setzt das Kennzeichen bei jedem Nicht-ASCII-Namen
    selbst; deshalb erst mit einem ASCII-Platzhalter gleicher Länge schreiben und die
    Bytes danach tauschen (Name steht im lokalen Kopf und im Verzeichnis, die Prüfsumme
    deckt nur den Inhalt)."""
    platzhalter = b"N" * len(name_bytes)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr(platzhalter.decode("ascii"), inhalt)
    roh = puffer.getvalue()
    assert roh.count(platzhalter) == 2
    return roh.replace(platzhalter, name_bytes)


def _erster(roh: bytes) -> zipfile.ZipInfo:
    return zipfile.ZipFile(io.BytesIO(roh)).infolist()[0]


class TestEintragsname:
    def test_utf8_ohne_kennzeichen_wird_als_utf8_gelesen(self):
        eintrag = _erster(zip_ohne_kennzeichen(f"{NFD}.md".encode("utf-8")))
        assert not eintrag.flag_bits & 0x800
        assert "╠" in eintrag.filename, "zipfile liest es als CP437 — sonst prüft der Test nichts"
        assert eintragsname(eintrag) == f"{NFD}.md"

    def test_echtes_cp437_bleibt_cp437(self):
        """„Übung" aus einem alten DOS-Packer: Ü ist dort 0x9A — kein gültiges UTF-8."""
        eintrag = _erster(zip_ohne_kennzeichen("Übung.md".encode("cp437")))
        assert eintragsname(eintrag) == "Übung.md"

    def test_mit_kennzeichen_unveraendert(self):
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as z:
            z.writestr("Säure.md", b"x")
        eintrag = _erster(puffer.getvalue())
        assert eintrag.flag_bits & 0x800
        assert eintragsname(eintrag) == "Säure.md"


class TestZurueckgelesen:
    @pytest.mark.parametrize("verstuemmelt, gemeint", [
        ("Hu╠êckel-Regel", "Hückel-Regel"),                 # zerlegtes ü
        ("╧â- und ╧Ç-Bindung", "σ- und π-Bindung"),          # griechisch, zusammengesetzt
        ("Sto╠êchiometrie", "Stöchiometrie"),
    ])
    def test_verstuemmelte_namen(self, verstuemmelt, gemeint):
        assert zurueckgelesen(verstuemmelt) == gemeint
        assert unicodedata.is_normalized("NFC", zurueckgelesen(verstuemmelt))

    @pytest.mark.parametrize("name", ["Hückel-Regel", "Straße", "Ion", "Preis in €", NFD])
    def test_richtige_namen_bleiben(self, name):
        assert zurueckgelesen(name) is None
