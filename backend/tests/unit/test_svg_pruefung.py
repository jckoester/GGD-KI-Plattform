"""Die SVG-Prüfung vor dem Speichern (Paket 10, AP3).

⚠️ **Warum es sie erst jetzt gibt.** Bis Paket 9 kamen alle SVGs im Wissensgraphen aus
eigenen Werkzeugen; `app/render/export.py` schreibt diese Annahme sogar hin. Mit dem
Upload-Dialog stimmt sie nicht mehr — und dieselben Bytes landen im PDF-Export, wo kein
DOMPurify sitzt.

Die echten Pilotdateien sind Teil des Prüfsatzes: Eine Prüfung, die alles Gefährliche
abweist und dabei die vorhandenen Zeichnungen gleich mit, hat nichts gewonnen.
"""
import pytest

from app.context.svg_pruefung import pruefe_svg

RUMPF = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">{}</svg>'


class TestWasDurchkommt:
    def test_eine_schlichte_zeichnung(self):
        assert pruefe_svg(RUMPF.format('<path d="M0 0 L10 10"/>')) is None

    def test_verweis_im_dokument(self):
        """`<use xlink:href="#g0-1">` ist der Normalfall aus dvisvgm — jede Glyphe."""
        inhalt = (
            '<defs><path id="g0" d="M0 0"/></defs>'
            '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#g0"/>'
        )
        assert pruefe_svg(RUMPF.format(inhalt)) is None

    def test_clip_pfad_im_dokument(self):
        assert pruefe_svg(RUMPF.format('<rect clip-path="url(#c1)"/>')) is None

    def test_fremder_namensraum_bleibt(self):
        """Die Pilotdateien tragen ein `c2pa:manifest`. Eine Positivliste der Elemente
        hätte sie abgewiesen, ohne dass irgendjemand dadurch sicherer wäre."""
        inhalt = '<c2pa:manifest xmlns:c2pa="http://c2pa.org/manifest">x</c2pa:manifest>'
        assert pruefe_svg(RUMPF.format(inhalt)) is None


class TestWasAbgewiesenWird:
    @pytest.mark.parametrize(
        "inhalt,stichwort",
        [
            ("<script>alert(1)</script>", "script"),
            ('<foreignObject><p>x</p></foreignObject>', "foreignobject"),
            ('<iframe src="x"/>', "iframe"),
            ('<animate attributeName="href" to="javascript:x()"/>', "animate"),
            ('<rect onload="x()"/>', "onload"),
            ('<rect onmouseover="x()"/>', "onmouseover"),
        ],
    )
    def test_verhalten_im_bild(self, inhalt, stichwort):
        grund = pruefe_svg(RUMPF.format(inhalt))
        assert grund and stichwort in grund.lower(), grund

    def test_javascript_in_einem_verweis(self):
        inhalt = '<a xmlns:xlink="http://www.w3.org/1999/xlink" href="javascript:x()"/>'
        assert "javascript:" in (pruefe_svg(RUMPF.format(inhalt)) or "")

    def test_javascript_mit_leerzeichen_getarnt(self):
        """`java script:` fängt der Browser ab, `java\\tscript:` nicht überall — deshalb
        wird der Wert ohne Leerraum verglichen."""
        inhalt = '<a href="java\tscript:x()"/>'
        assert "javascript:" in (pruefe_svg(RUMPF.format(inhalt)) or "")

    def test_verweis_nach_draussen(self):
        inhalt = '<image href="https://fremde.example/pixel.png"/>'
        grund = pruefe_svg(RUMPF.format(inhalt))
        assert grund and "nach außen" in grund

    def test_fuellung_von_einem_fremden_server(self):
        """Kein Skript, aber ein Aufruf: Wer das Bild ansieht, meldet sich dort."""
        grund = pruefe_svg(RUMPF.format('<rect fill="url(https://fremde.example/x#y)"/>'))
        assert grund and "nach außen" in grund

    def test_import_im_stilblock(self):
        grund = pruefe_svg(RUMPF.format('<style>@import url(https://fremde.example);</style>'))
        assert grund and "@import" in grund

    def test_entity_deklaration(self):
        """⚠️ **Vor dem Parsen geprüft.** Expat löst interne Entities auf — „billion
        laughs" wirkte, bevor irgendeine Elementprüfung den Baum zu sehen bekäme."""
        roh = '<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">]><svg xmlns="http://www.w3.org/2000/svg"/>'
        grund = pruefe_svg(roh)
        assert grund and "Entity" in grund

    def test_kein_xml(self):
        assert pruefe_svg("das ist kein bild") is not None

    def test_falsches_wurzelelement(self):
        """Eine HTML-Datei mit der Endung `.svg` ist keine Zeichnung."""
        grund = pruefe_svg("<html><body>x</body></html>")
        assert grund and "<svg>" in grund

    def test_svg_ohne_namensraum(self):
        """Der Namensraum ist die einzige Zusage der Datei, eine Zeichnung zu sein.

        Ohne ihn liest ein Browser den Inhalt als HTML — und jedes Zeichenwerkzeug
        schreibt ihn. Also: durchgefallen, mit dem fehlenden Attribut in der Meldung.
        """
        grund = pruefe_svg('<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>')
        assert grund and "xmlns" in grund

    def test_gefahr_tief_im_baum(self):
        """Nicht nur die erste Ebene: Geprüft wird jedes Element."""
        inhalt = "<g><g><g><script>x</script></g></g></g>"
        assert pruefe_svg(RUMPF.format(inhalt)) is not None


PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
       "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


class TestEingebettetesRasterbild:
    """0.14.1: Ein PNG, das als `data:` im SVG steckt, lädt nichts nach. Bis 0.14.0 galt es
    als „Verweis nach außen" — und die Orbital-Abbildungen der Chemie fielen beim Import
    über den Dialog weg."""

    @pytest.mark.parametrize("attribut", ['href', 'xlink:href'])
    def test_png_an_image_kommt_durch(self, attribut):
        xlink = ' xmlns:xlink="http://www.w3.org/1999/xlink"' if attribut.startswith("xlink") else ""
        inhalt = f'<image{xlink} {attribut}="{PNG}" width="10" height="10"/>'
        assert pruefe_svg(RUMPF.format(inhalt)) is None

    @pytest.mark.parametrize("art", ["jpeg", "jpg", "gif", "webp", "PNG"])
    def test_andere_rasterformate(self, art):
        inhalt = f'<image href="data:image/{art};base64,AAAA" width="1" height="1"/>'
        assert pruefe_svg(RUMPF.format(inhalt)) is None

    def test_svg_als_daten_bleibt_draussen(self):
        """Ein zweites SVG ginge an dieser Prüfung vorbei — der PDF-Export löst darin
        Verweise nach außen auf."""
        inhalt = '<image href="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=" width="1" height="1"/>'
        grund = pruefe_svg(RUMPF.format(inhalt))
        assert grund and "Rasterbild" in grund and "nach außen" not in grund

    def test_daten_an_einem_link_bleiben_draussen(self):
        grund = pruefe_svg(RUMPF.format(f'<a href="{PNG}"><rect width="1" height="1"/></a>'))
        assert grund and "<a>" in grund

    def test_ohne_base64_bleibt_draussen(self):
        """Nur die Form, die ein Zeichenprogramm schreibt — kein Freitext in der URI."""
        inhalt = '<image href="data:image/png,%89PNG" width="1" height="1"/>'
        assert pruefe_svg(RUMPF.format(inhalt)) is not None

    def test_fremde_url_an_image_weiter_nach_aussen(self):
        grund = pruefe_svg(RUMPF.format('<image href="https://fremde.example/x.png"/>'))
        assert grund and "nach außen" in grund
