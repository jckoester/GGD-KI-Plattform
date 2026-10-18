"""Begriffe aus den Phasentexten (0.18, Schritt 5) — was ohne Datenbank prüfbar ist.

Format von Entwurf und Nachricht, Lesen der Antwort, Prüfsumme, Anzeige. Der Abgleich und
die Ablage laufen in `tests/integration/test_begriffe_der_stunde.py`.
"""
import hashlib

from app.planning.begriffe import (
    ANLEITUNG, HINWEIS_FRUEHER, SCHLUESSEL, entwurfstext, lies_antwort, nachricht, phase_kurz,
    pruefsumme, vorschlag_zur_anzeige,
)

PHASEN = [
    {"name": "Erarbeitung II: Fallunterscheidung", "dauer_min": 5, "prio": "kern",
     "sozialform": {"typ": "text", "wert": "LSG"}, "beschreibung": "gerade und\nungerade Hochzahlen"},
    {"name": "Sicherung wird HA", "prio": "kern"},
]


def test_anleitung_ist_die_gemessene():
    """Die Anleitung ist die des Vorlaufs, der bestand (Plan § 9). Wer sie ändert, misst neu —
    und trägt danach die neue Prüfsumme hier ein."""
    assert hashlib.sha256(ANLEITUNG.encode()).hexdigest()[:16] == "26e5e0aa9662b613"


def test_phase_in_einer_zeile_wie_im_vorlauf():
    assert phase_kurz(PHASEN[0]) == "Erarbeitung II: Fallunterscheidung (5′, kern, LSG) — gerade und / ungerade Hochzahlen"
    assert phase_kurz(PHASEN[1]) == "Sicherung wird HA (ohne Dauer, kern)"


def test_entwurfstext():
    text = entwurfstext("Gleichungen xⁿ = a", {"stundenziel": "", "phasen": PHASEN})
    assert text.splitlines() == [
        "Stunde: „Gleichungen xⁿ = a“", "Stundenziel: —", "Phasen:",
        "- Erarbeitung II: Fallunterscheidung (5′, kern, LSG) — gerade und / ungerade Hochzahlen",
        "- Sicherung wird HA (ohne Dauer, kern)",
    ]


def test_nachricht_wie_im_vorlauf():
    n = nachricht("Fach: Mathematik · Jahrgang: Klasse 9", ["Potenz", "Exponent"],
                  [{"titel": "Potenzgleichung", "aliase": []}, {"titel": "n-te Wurzel", "aliase": ["Wurzel"]}],
                  "Stunde: „T“")
    assert n == ("Fach: Mathematik · Jahrgang: Klasse 9\n"
                 "Begriffe früherer Stunden dieser Gruppe: Potenz, Exponent\n\n"
                 "Kandidaten aus dem Wissensspeicher (Schreibhilfe, keine Auswahl):\n"
                 "- Potenzgleichung\n- n-te Wurzel (Aliase: Wurzel)\n\n"
                 "Stunde: „T“")


def test_nachricht_ohne_fruehere_und_ohne_kandidaten():
    n = nachricht("Fach: Chemie", [], [], "Stunde: „T“")
    assert "Begriffe früherer Stunden dieser Gruppe: keine eingetragen" in n
    assert "Kandidaten" not in n


def test_antwort_lesen():
    assert lies_antwort('{"begriffe": [{"name": "Potenz", "phase": "Einstieg", "art": "eingeführt"}]}') == [
        {"name": "Potenz", "phase": "Einstieg", "art": "eingeführt"}]
    # JSON mitten im Text, leere Namen fallen weg.
    assert lies_antwort('Hier: {"begriffe": [{"name": "Basis"}, {"name": " "}, "kaputt"]} Ende') == [{"name": "Basis"}]
    assert lies_antwort("keine Ahnung") is None
    assert lies_antwort('{"begriffe": "Potenz"}') is None
    assert lies_antwort('{"begriffe": [}') is None


def test_pruefsumme_folgt_dem_entwurf():
    a = pruefsumme(entwurfstext("T", {"phasen": PHASEN}))
    assert a == pruefsumme(entwurfstext("T", {"phasen": PHASEN}))
    assert a != pruefsumme(entwurfstext("T", {"phasen": PHASEN[:1]}))


def test_anzeige_filtert_und_sagt_ob_aktuell():
    meta = {"phasen": PHASEN, "refs": [{"node_id": "a", "typ": "concept"}], "refs_dismissed": ["b"]}
    meta[SCHLUESSEL] = {
        "pruefsumme": pruefsumme(entwurfstext("T", meta)),
        "eintraege": [{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"}],
        "frueher": [{"node_id": "b"}, {"node_id": "d"}], "ohne_knoten": [],
    }
    v = vorschlag_zur_anzeige("T", meta)
    assert [e["node_id"] for e in v["eintraege"]] == ["c"]
    assert [f["node_id"] for f in v["frueher"]] == ["d"]
    assert v["aktuell"] is True and v["hinweis_frueher"] == HINWEIS_FRUEHER
    assert vorschlag_zur_anzeige("Anderer Titel", meta)["aktuell"] is False
    assert vorschlag_zur_anzeige("T", {"phasen": PHASEN}) is None


def test_hinweis_nennt_nichts_bekannt():
    """F1 (Jan, 18.10.2026): eine Planungshilfe, kein Lernstand — nirgends „bekannt"."""
    assert "bekannt" not in HINWEIS_FRUEHER.casefold() and "Lernstand" in HINWEIS_FRUEHER


def test_werkzeugtexte_folgen_dem_prompt():
    """Die Anleitung im Werkzeugergebnis steht nach dem Prompt und überstimmt ihn: In der ersten
    Messung zu 0.18 Schritt 7 verlangte sie noch den Absatz „Begriffe dieser Stunde", und das
    Modell schrieb ihn trotz neuem Prompt (Regression 1/3 und 0/3). Kein Werkzeugtext darf das
    alte Verhalten verlangen."""
    import json

    from app.chat.tools import TOOL_REGISTRY
    from app.planning import assistant_tools

    assert "nicht von dir" in assistant_tools.BEGRIFFE_ANLEITUNG
    for name in ("get_lesson_detail", "update_lesson_phases"):
        text = json.dumps(TOOL_REGISTRY[name].definition, ensure_ascii=False)
        assert "Begriffe dieser Stunde" not in text, name
    assert "Begriffe dieser Stunde" not in assistant_tools.BEGRIFFE_ANLEITUNG
