"""Operator im Satz erkennen (Päckchen AF, Schritt 1) — als Satztabelle.

Die Titel sind die der naturwissenschaftlichen Fächer auf Dev (27.10.2026), dazu einige
mehrwortige aus anderen Fächern, die die Titelzerlegung prüfen.
"""
import pytest

from app.context.operator_erkennung import (
    MAX_OPERATOREN,
    Operatorindex,
    erkenne,
    muster_aus_titel,
)

TITEL = [
    "ableiten", "abschätzen", "analysieren", "angeben", "anwenden", "aufstellen", "auswerten",
    "begründen", "benennen", "berechnen", "beschreiben", "bestimmen", "beurteilen", "bewerten",
    "darstellen", "diskutieren", "durchführen", "entwerfen", "erfassen (Messwerte)", "erklären",
    "erläutern", "ermitteln", "herleiten", "Hypothesen aufstellen", "interpretieren", "messen",
    "nennen", "nutzen", "ordnen", "planen", "protokollieren", "skizzieren", "untersuchen",
    "vergleichen", "zeichnen", "zuordnen", "zusammenfassen",
    "beurteilen / Stellung nehmen", "Informationen entnehmen", "wiedergeben",
]
INDEX = Operatorindex.aus(TITEL)


@pytest.mark.parametrize("text, erwartet", [
    # regelmäßig, auch mit Schülerantwort dahinter
    ("Erläutere die Funktion der Spaltöffnungen. Meine Antwort: Durch die Spaltöffnungen …",
     ["erläutern"]),
    ("Bewerte, ob man Wildvögel im Winter füttern sollte.", ["bewerten"]),
    ("Beurteile, ob man Wildvögel füttern sollte.", ["beurteilen", "beurteilen / stellung nehmen"]),
    ("erkläre warum das eis schwimmt", ["erklären"]),                     # klein geschrieben
    ("Erläutern Sie den Treibhauseffekt.", ["erläutern"]),                 # Sie-Form
    ("Nenne drei Edelgase.", ["nennen"]),
    ("Plane einen Versuch zur Keimung.", ["planen"]),
    # trennbar: Partikel am Satzende oder vor dem Komma
    ("Werte das Diagramm aus: Die Stromstärke steigt …", ["auswerten"]),
    ("Werten Sie die Messreihe aus.", ["auswerten"]),
    ("Stelle die Reaktionsgleichung auf, indem du die Atome zählst.", ["aufstellen"]),
    ("Stelle eine Hypothese auf.", ["hypothesen aufstellen"]),             # Objekt schlägt das Verb allein
    ("Ordne die Stoffe den Gruppen zu.", ["zuordnen"]),                    # Partikel schlägt „ordnen"
    ("Ordne die Stoffe nach ihrer Dichte.", ["ordnen"]),
    ("Fasse den Text zusammen.", ["zusammenfassen"]),
    ("Führe den Versuch durch und notiere die Beobachtung.", ["durchführen"]),
    ("Leite die Formel her.", ["herleiten"]),
    ("Gib die Formel von Wasser an.", ["angeben"]),                        # unregelmäßig + trennbar
    ("Gib die wichtigsten Aussagen wieder.", ["wiedergeben"]),
    # unregelmäßig
    ("Miss die Temperatur alle 30 Sekunden.", ["messen"]),
    ("Entwirf ein Experiment.", ["entwerfen"]),
    ("Nimm Stellung zur Winterfütterung.", ["beurteilen / stellung nehmen"]),
    ("Entnimm dem Text die Informationen.", ["informationen entnehmen"]),
    # mitten im Satz in Anführungszeichen, nach Aufzählungszeichen
    ("In der Aufgabe steht „Erkläre den Kurvenverlauf“. Was soll ich machen?", ["erklären"]),
    ("a) Berechne die Masse. b) Begründe dein Vorgehen.", ["berechnen", "begründen"]),
    ("Aufgabe 2: Skizziere den Aufbau.", ["skizzieren"]),
    # berichtet: Infinitiv mit „sollen/müssen"
    ("Warum haben Vögel hohle Knochen? Das sollen wir erklären.", ["erklären"]),
    ("Warum hört man im Weltall nichts? Sollen wir begründen.", ["begründen"]),
    ("Wir müssen die Messreihe auswerten.", ["auswerten"]),
    ("Wir sollen rausfinden, ob Bohnen Licht brauchen.", []),               # kein Operator
    # Imperativ vor berichtetem Auftrag (Lauf 19, O8)
    ("Gib an, welche Stoffe entstehen. Meine Antwort: Sauerstoff. Muss ich das noch erklären?", ["angeben"]),
    ("Ich soll morgen erklären können, was Ionen sind.", ["erklären"]),    # Fehltreffer, hingenommen
    # keine Aufgabe
    ("Erkläre mir den Treibhauseffekt.", []),                              # F5
    ("Erklär uns bitte, was Ionen sind.", []),
    ("Erklären Sie mir das bitte.", []),
    ("Werte über 5 sind zu hoch.", []),                                    # Nomen, ohne Partikel
    ("Der Planet kreist um die Sonne.", []),
    ("Was heißt eigentlich erläutern?", []),                               # Frage, kein Imperativ
    ("Kannst du mir bei Mathe helfen? 3x + 5 = 20", []),
    ("Ist für Physik. Ich weiß, dass CO2 damit zu tun hat.", []),
    ("", []),
])
def test_satztabelle(text, erwartet):
    assert erkenne(text, INDEX) == erwartet


def test_hoechstens_drei():
    text = "Nenne die Stoffe. Beschreibe sie. Erkläre den Aufbau. Bewerte den Einsatz."
    assert erkenne(text, INDEX) == ["nennen", "beschreiben", "erklären"]
    assert MAX_OPERATOREN == 3


def test_doppelte_nur_einmal():
    assert erkenne("Erläutere A. Erläutere B.", INDEX) == ["erläutern"]


def test_titel_lesarten():
    """„Hypothesen aufstellen": Objekt Hypothese, getrennt mit „auf"; untrennbar auch."""
    lesarten = muster_aus_titel("Hypothesen aufstellen")
    assert {m.partikel for m in lesarten} == {None, "auf"}
    assert all(m.objekte == ("hypoth",) or m.objekte for m in lesarten)


def test_titel_ohne_verb_ergibt_nichts():
    assert muster_aus_titel("an‑") == []


def test_infinitiv_nach_begleiter_ist_kein_auftrag():
    """0.26, Versuche S2: „einen fertigen Versuchsplan“ ist ein Adjektiv, kein Operator *fertigen*."""
    index = Operatorindex.aus(["fertigen", "planen"])
    assert erkenne("Unsere Lehrerin hat gesagt, du sollst uns einen fertigen Versuchsplan geben.", index) == []
    assert erkenne("Wir sollen das Planen üben.", index) == []
    assert erkenne("Wir sollen eine Skizze fertigen.", index) == ["fertigen"]
