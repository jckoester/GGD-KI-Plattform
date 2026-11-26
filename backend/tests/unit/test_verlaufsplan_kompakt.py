"""Der Jahresverlaufsplan für Programme (BD Teil B, Schritt 6): `verlaufsplan.kompakt`, ohne Datenbank."""
from datetime import date

from app.context.verlaufsplan import NICHT_MEHR_IM_CURRICULUM, kompakt

CURRICULA = [{"kapitel": [{"id": "k1", "titel": "Ähnlichkeit", "sequenzen": [{"id": "s1", "titel": "Strahlensätze"}]},
                          {"id": "k2", "titel": "Pythagoras", "sequenzen": []}]}]


def _voll(**kw):
    v = {"id": "p1", "titel": "Plan", "fach": "Mathematik", "stufe": 9, "schuljahr": "2025/26", "status": "draft",
         "beschlossen_am": None, "archiviert": False, "planungsart": "sequenz", "wochenstunden": 4,
         "curricula": CURRICULA, "darf_bearbeiten": True,
         "abschnitte": [{"id": "a", "titel": "Strahlen", "wochen": 2, "sequenz_ids": ["s1", "sX"], "notiz": " GeoGebra "},
                        {"id": "b", "titel": "Puffer", "wochen": 1, "puffer": True, "sequenz_ids": []}],
         "lage": {"unterrichtswochen": 37, "belegt": 3, "frei": 34, "ueberhang": 0, "puffer_wochen": 1,
                  "abschnitte": [{"von_woche": 1, "bis_woche": 2, "beginn": date(2025, 9, 15), "ende": date(2025, 9, 26),
                                  "ueber_ferien": [], "vor_ferien": None, "halbjahreswechsel": False, "ausserhalb": 0},
                                 {"von_woche": 3, "bis_woche": 3, "beginn": date(2025, 9, 29), "ende": date(2025, 10, 3),
                                  "ueber_ferien": [], "vor_ferien": "Herbstferien", "halbjahreswechsel": False, "ausserhalb": 0}],
                  "ferien": [{"name": "Herbstferien", "von": date(2025, 10, 27), "bis": date(2025, 10, 31), "nach_woche": 6}],
                  "halbjahr_ab_woche": 18,
                  "kapitel": [{"kapitel_id": "k1", "titel": "Ähnlichkeit", "soll": 12, "geplant": 8.0, "wochen": 2.0}],
                  "kapitel_ohne_abschnitt": ["k2"], "sequenzen_ohne_abschnitt": []}}
    v.update(kw)
    return v


def test_abschnitte_mit_titeln_und_daten():
    k = kompakt(_voll())
    assert (k["status"], k["planungsart"], k["stufe"]) == ("entwurf", "sequenzgenau", 9)
    a, p = k["abschnitte"]
    assert a == {"nr": 1, "titel": "Strahlen", "wochen": 2,
                 "lernsequenzen": [{"id": "s1", "titel": "Strahlensätze", "kapitel": "Ähnlichkeit"},
                                   {"id": "sX", "titel": NICHT_MEHR_IM_CURRICULUM, "kapitel": NICHT_MEHR_IM_CURRICULUM,
                                    "nicht_mehr_im_curriculum": True}],
                 "von_woche": 1, "bis_woche": 2, "beginn": "2025-09-15", "ende": "2025-09-26", "notiz": "GeoGebra"}
    assert p["puffer"] is True and p["vor_ferien"] == "Herbstferien" and "lernsequenzen" not in p
    assert k["ferien"] == [{"name": "Herbstferien", "von": "2025-10-27", "bis": "2025-10-31", "nach_woche": 6}]
    assert k["bilanz"][0] == {"kapitel": "Ähnlichkeit", "kapitel_id": "k1", "soll_stunden": 12,
                              "geplant_stunden": 8.0, "wochen": 2.0}
    assert k["kapitel_ohne_abschnitt"] == ["Pythagoras"] and k["lernsequenzen_ohne_abschnitt"] == []
    # Keine Rechte, kein Curricula-Baum
    assert "darf_bearbeiten" not in k and "curricula" not in k


def test_kapitelgenau_und_ohne_kalender():
    k = kompakt(_voll(planungsart="kapitel", status="active", beschlossen_am="2025-10-01", lage=None,
                      abschnitte=[{"titel": "", "wochen": 3, "kapitel_ids": ["k2"]}]))
    assert (k["status"], k["planungsart"]) == ("beschlossen", "kapitelgenau")
    assert k["abschnitte"] == [{"nr": 1, "titel": "", "wochen": 3, "kapitel": [{"id": "k2", "titel": "Pythagoras"}]}]
    assert "Kalender" in k["hinweis"] and "bilanz" not in k


def test_alte_titel_und_fremde_sequenz_in_der_bilanz():
    v = _voll()
    v["lage"]["kapitel"].append({"kapitel_id": "sX", "titel": None, "soll": None, "geplant": 4.0, "wochen": 1.0})
    k = kompakt(v, titel_alt={"sX": "Alte Sequenz"}, kapitel_alt={"sX": "Altes Kapitel"})
    assert k["abschnitte"][0]["lernsequenzen"][1] == {"id": "sX", "titel": "Alte Sequenz", "kapitel": "Altes Kapitel",
                                                      "nicht_mehr_im_curriculum": True}
    # Eine Sequenz außerhalb des Curriculums heißt in der Bilanz auch so, nicht „kapitel“
    assert k["bilanz"][1] == {"lernsequenz": "Alte Sequenz", "lernsequenz_id": "sX", "nicht_mehr_im_curriculum": True,
                              "soll_stunden": None, "geplant_stunden": 4.0, "wochen": 1.0}
    assert "nicht_mehr_im_curriculum" not in k["bilanz"][0]
    # Kapitelgenau: ein fremdes Kapitel bleibt ein Kapitel, mit altem Titel
    k = kompakt(_voll(planungsart="kapitel", abschnitte=[{"titel": "", "wochen": 1, "kapitel_ids": ["kAlt"]}],
                      lage=None), titel_alt={"kAlt": "Optik (alt)"})
    assert k["abschnitte"][0]["kapitel"] == [{"id": "kAlt", "titel": "Optik (alt)", "nicht_mehr_im_curriculum": True}]
