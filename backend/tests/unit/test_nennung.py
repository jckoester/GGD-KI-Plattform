"""Begriffsnennung im Satz (0.16, Schritt 3) — was als Nennung zählt.

Nur die Kandidaten; über die Aufnahme entscheidet das Tor in `vorab()` (Integrationstests in
`test_vorab_suche_db.py`, Klasse `TestNennung`).
"""
from app.context.modellsicht import fuer_modell
from app.context.nennung import MAX_WOERTER, Namensindex, genannt, schluessel, stamm

CHEMIE, MATHE, NWT = 1, 2, 3


def _index(*titel, aliase=()):
    """``titel``/``aliase``: (node_id, subject_id, Name)."""
    return Namensindex.aus(titel, aliase)


# ── Endungen ─────────────────────────────────────────────────────────────────


def test_endungen_auf_beiden_seiten():
    assert stamm("alkane") == stamm("alkans") == "alkan"
    assert stamm("ionen") == stamm("ion") == "ion"
    assert stamm("mittelwerts") == "mittelwert"
    assert stamm("gruppen") == stamm("gruppe") == "grupp"


def test_kurze_woerter_bleiben_ganz():
    """Mindestens drei Zeichen bleiben — sonst würde aus „Eis" „ei" und aus „Ion" „io"."""
    assert stamm("eis") == "eis"
    assert stamm("ion") == "ion"


def test_schluessel_normalisiert_und_haelt_bindestriche():
    assert schluessel("Wie liest man einen Box-Plot?") == ("wie", "liest", "man", "ein", "box-plot")


# ── Nennungen ────────────────────────────────────────────────────────────────


def test_begriff_im_erzaehlsatz():
    index = _index(("en", CHEMIE, "Elektronegativität"))
    satz = "Letzte Stunde haben wir etwas über Elektronegativität gelernt, das ich nicht verstanden habe."
    assert genannt(satz, index, None) == {"en": "titel"}


def test_titel_im_plural_nennung_im_singular():
    index = _index(("alk", CHEMIE, "Alkane"))
    assert genannt("Ich verstehe den Aufbau eines Alkans nicht.", index, None) == {"alk": "titel"}


def test_mehrwortiger_titel_gebeugt():
    index = _index(("fg", CHEMIE, "funktionelle Gruppe"))
    assert genannt("Wir lernen die funktionellen Gruppen.", index, None) == {"fg": "titel"}


def test_kein_kompositum():
    """F2: „Veresterungsreaktion" nennt die Veresterung nicht."""
    index = _index(("ve", CHEMIE, "Veresterung"))
    assert genannt("Erklär mir die Veresterungsreaktion.", index, None) == {}


def test_laengste_nennung_zuerst():
    """„funktionelle Gruppen" ist genannt — „Gruppe" für sich nicht noch einmal."""
    index = _index(("fg", CHEMIE, "funktionelle Gruppe"), ("gr", CHEMIE, "Gruppe"))
    assert genannt("Was sind funktionelle Gruppen?", index, None) == {"fg": "titel"}


def test_titel_vor_alias():
    index = _index(("w", CHEMIE, "Wasser"), aliase=[("w", CHEMIE, "H2O")])
    assert genannt("Wasser ist H2O.", index, None) == {"w": "titel"}
    assert genannt("Was ist H2O?", index, None) == {"w": "alias"}


def test_derselbe_name_als_titel_und_als_fremder_alias():
    index = _index(("faktor", MATHE, "Faktor"), aliase=[("parameter", NWT, "Faktor")])
    assert genannt("Was ist ein Faktor?", index, None) == {"faktor": "titel", "parameter": "alias"}


def test_beilaeufiges_nennt_nichts():
    index = _index(("en", CHEMIE, "Elektronegativität"), ("w", CHEMIE, "Wasser"))
    assert genannt("Wie geht es dir?", index, None) == {}


def test_zu_lange_namen_werden_nicht_gesucht():
    lang = " ".join(f"wort{i}" for i in range(MAX_WOERTER + 1))
    assert _index(("x", None, lang)).namen == {}


# ── Fachbezug ────────────────────────────────────────────────────────────────


def test_fach_ohne_bezug_zaehlt_nicht():
    index = _index(("fs", NWT + 10, "Fotosynthese"), ("lb", None, "Laborbuch"))
    satz = "Fotosynthese und Laborbuch"
    assert genannt(satz, index, {NWT}) == {"lb": "titel"}           # fachlos immer
    assert genannt(satz, index, {NWT, NWT + 10}) == {"fs": "titel", "lb": "titel"}
    assert genannt(satz, index, None) == {"fs": "titel", "lb": "titel"}   # Chat ohne Fach


def test_fremdes_fach_blockiert_keine_kuerzere_nennung():
    """Ein Name, der nicht zählen darf, belegt auch keine Wörter."""
    index = _index(("fg", CHEMIE, "funktionelle Gruppe"), ("gr", MATHE, "Gruppe"))
    assert genannt("Was sind funktionelle Gruppen?", index, {MATHE}) == {"gr": "titel"}


# ── Was das Modell sieht ─────────────────────────────────────────────────────


def test_genannt_geht_nicht_ins_modell():
    """Ein Messmerkmal wie `distanz` — ein Prompt-Feld mehr wäre eine Prompt-Änderung."""
    eintrag = fuer_modell([{"node_id": "x", "title": "Ion", "content": "…", "distanz": 0.5,
                            "genannt": True}])[0]
    assert "genannt" not in eintrag and "distanz" not in eintrag
