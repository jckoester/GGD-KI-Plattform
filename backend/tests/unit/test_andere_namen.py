"""Namen aus dem Abschnitt „Andere allgemeine Assistenten“ für den Messkanal (0.26, Lauf 2, E1)."""
from app.assistants.andere import abschnitt, andere_namen


def test_andere_namen_aus_dem_abschnitt():
    text = abschnitt([("Mathe-Aufgaben", "Für Mathe: rechnen tust du selbst."),
                      ("Auswerten von Diagrammen, Tabellen und Statistiken", "Satz.")])
    assert andere_namen(text) == ["Mathe-Aufgaben", "Auswerten von Diagrammen, Tabellen und Statistiken"]
    assert andere_namen("") == []
