"""Curriculum-YAML einlesen und bereinigen (0.56, Päckchen BA Schritt 1) — ohne Datenbank."""
import yaml

from app.context.curriculum_yaml import GRENZEN, Grenzen, einlesen, zu_entwurf

GRUND = {
    "schule": "S", "fach_code": "CH", "fach": "Chemie", "schulart": "Gymnasium", "jahrgangsstufe": 9,
    "bp_id": "BP_CH", "bp_version": "2016",
    "kapitel": [{"titel": "Stoffe", "reihenfolge": 1, "std": 10, "lernsequenzen": [
        {"bp_titel": "Teilchen", "reihenfolge": 1, "std": "4", "eintraege": [
            {"ik": [{"nr": "3.4.3(2)", "partiell": True}], "pk": [{"id": "2.1"}], "konkretisierung": "K",
             "hinweise": "Siehe @[BNE](lp:BNE) und #[Physik](ik:PH:3.1(1))", "material": "",
             "begriffe": ["Atom", {"name": "Ion", "fassung": "Kl. 9"}], "fachmethoden": ["Titration"]}]}]}],
}


def _yaml(daten=None, **abw):
    return yaml.safe_dump({**(daten or GRUND), **abw}, allow_unicode=True, sort_keys=False)


def test_gueltige_datei_wird_zum_entwurf():
    p = einlesen(_yaml())
    assert p.ok, p.fehler
    e = p.entwurf
    assert (e.fach_code, e.jahrgangsstufe, e.bp_id) == ("CH", "9", "BP_CH")
    kap = e.kapitel[0]
    assert (kap.titel, kap.std) == ("Stoffe", "10")
    eintrag = kap.lernsequenzen[0].eintraege[0]
    assert eintrag.ik == [{"nr": "3.4.3(2)", "partiell": True}]
    assert eintrag.pk == [{"id": "2.1"}]
    assert eintrag.begriffe == ["Atom", {"name": "Ion", "fassung": "Kl. 9"}]
    assert eintrag.hinweise == GRUND["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]["hinweise"]
    assert p.warnungen == []


def test_bom_und_windows_zeilenenden():
    p = einlesen(b"\xef\xbb\xbf" + _yaml().replace("\n", "\r\n").encode())
    assert p.ok, p.fehler


def test_aliase_und_anker_abgelehnt():
    bombe = "a: &a [x, x, x]\nb: &b [*a, *a, *a]\nc: [*b, *b, *b]\n"
    p = einlesen(bombe)
    assert not p.ok and "Anker" in p.fehler[0]


def test_python_tags_abgelehnt():
    p = einlesen("schule: !!python/object/apply:os.system ['true']\n")
    assert not p.ok and "YAML" in p.fehler[0]


def test_zu_gross_vor_dem_parsen():
    p = einlesen(b"x" * (GRENZEN.bytes + 1))
    assert not p.ok and "zu groß" in p.fehler[0]


def test_zu_tief_verschachtelt():
    p = einlesen("[" * 50 + "]" * 50)
    assert not p.ok and "verschachtelt" in p.fehler[0]


def test_kein_yaml_mit_zeile():
    p = einlesen("schule: S\nkapitel: [\n")
    assert not p.ok and p.fehler[0].startswith("Kein gültiges YAML")


def test_keine_liste_oben_und_kein_utf8():
    assert "Curriculum" in einlesen("- a\n- b\n").fehler[0]
    assert "UTF-8" in einlesen("schule: \xe4".encode("latin-1")).fehler[0]


def test_fehlende_pflichtfelder_mit_stelle():
    daten = {k: v for k, v in GRUND.items() if k not in ("fach_code", "bp_version")}
    p = zu_entwurf(daten)
    assert not p.ok
    assert "fach_code: fehlt." in p.fehler and "bp_version: fehlt." in p.fehler


def test_ohne_kapitel_fehler():
    assert "keine Kapitel" in zu_entwurf({**GRUND, "kapitel": []}).fehler[0]


def test_falsche_typen_mit_pfad():
    kap = {"titel": ["kein", "text"], "reihenfolge": "eins", "lernsequenzen": [
        {"bp_titel": "L", "eintraege": [{"ik_partiell": "ja", "pk": "2.1", "hinweise": {"a": 1}}]}]}
    p = zu_entwurf({**GRUND, "kapitel": [kap]})
    assert not p.ok
    assert "Kapitel 1, titel: muss Text sein." in p.fehler
    assert "Kapitel 1, reihenfolge: muss eine ganze Zahl sein." in p.fehler
    assert "Kapitel 1, Lernsequenz 1, Eintrag 1, ik_partiell: muss true oder false sein." in p.fehler
    assert "Kapitel 1, Lernsequenz 1, Eintrag 1, pk: muss eine Liste sein." in p.fehler
    assert "Kapitel 1, Lernsequenz 1, Eintrag 1, hinweise: muss Text sein." in p.fehler


def test_unbekannte_felder_nur_warnung():
    p = zu_entwurf({**GRUND, "exportiert_am": "heute",
                    "kapitel": [{**GRUND["kapitel"][0], "farbe": "rot"}]})
    assert p.ok, p.fehler
    assert "Datei: unbekannte Felder übergangen: exportiert_am." in p.warnungen
    assert "Kapitel 1: unbekannte Felder übergangen: farbe." in p.warnungen


def test_steuerzeichen_entfernt():
    kap = {**GRUND["kapitel"][0], "titel": "Sto\x00ffe\x1b[31m"}
    p = zu_entwurf({**GRUND, "kapitel": [kap]})
    assert p.ok and p.entwurf.kapitel[0].titel == "Stoffe[31m"
    assert "Kapitel 1, titel: Steuerzeichen entfernt." in p.warnungen


def test_unbekannte_verweisart_wird_text():
    ls = GRUND["kapitel"][0]["lernsequenzen"][0]
    eintrag = {**ls["eintraege"][0], "hinweise": "Klick @[hier](javascript:alert(1)) und @[BNE](lp:BNE)"}
    kap = {**GRUND["kapitel"][0], "lernsequenzen": [{**ls, "eintraege": [eintrag]}]}
    p = zu_entwurf({**GRUND, "kapitel": [kap]})
    assert p.ok
    assert p.entwurf.kapitel[0].lernsequenzen[0].eintraege[0].hinweise == "Klick hier und @[BNE](lp:BNE)"
    assert any("unbekannter Art (javascript)" in w for w in p.warnungen)


def test_grenzen():
    g = Grenzen(kapitel=2, lernsequenzen=2, eintraege=1, zeichen=10, liste=1)
    assert "zu viele (3" in zu_entwurf({**GRUND, "kapitel": GRUND["kapitel"] * 3}, grenzen=g).fehler[0]
    ls = GRUND["kapitel"][0]["lernsequenzen"]
    p = zu_entwurf({**GRUND, "kapitel": [{**GRUND["kapitel"][0], "lernsequenzen": ls * 3}]},
                   grenzen=Grenzen(eintraege=99, lernsequenzen=2))
    assert "Zu viele Lernsequenzen (3, höchstens 2)." in p.fehler
    p = zu_entwurf(GRUND, grenzen=g)
    assert any("zu lang" in f for f in p.fehler)
    assert any("begriffe: zu viele Einträge (2, höchstens 1)" in f for f in p.fehler)


def test_ohne_grenzen_fuer_das_admin_skript():
    lang = {**GRUND, "vorwort": "x" * (GRENZEN.zeichen + 1)}
    assert not zu_entwurf(lang).ok
    assert zu_entwurf(lang, grenzen=None).ok


def test_edition_ueberschreiben_laesst_bp_id_weg():
    e = zu_entwurf(GRUND, "2016.V2", grenzen=None).entwurf
    assert (e.bp_version, e.bp_id) == ("2016.V2", None)


def test_rahmen_wird_geprueft():
    assert zu_entwurf({**GRUND, "rahmen": {"wochenstunden": {"9": 2}}}).ok
    p = zu_entwurf({**GRUND, "rahmen": {"wochenstunden": {"neun": 2}}})
    assert not p.ok and p.fehler[0].startswith("rahmen:")


def test_titel_nur_leerraum_fehlt():
    p = zu_entwurf({**GRUND, "kapitel": [{**GRUND["kapitel"][0], "titel": "   "}]})
    assert "Kapitel 1, titel: fehlt." in p.fehler
