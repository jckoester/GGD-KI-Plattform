"""Welcher Statuswechsel erlaubt ist — und was er mitnimmt (ADR-020, AP3).

Die Übergangstabelle steht hier vollständig als Testdaten, nicht als Verweis auf
`service.UEBERGAENGE`: Ein Test, der die Tabelle aus dem Code liest, prüft nur, dass
sie sich selbst gleicht. Wer einen Übergang öffnet oder schließt, muss beides ändern.
"""
import pytest

from app.feedback import service

ALLE = ["open", "in_progress", "done", "declined", "spam"]

ERLAUBT = {
    ("open", "in_progress"), ("open", "done"), ("open", "declined"), ("open", "spam"),
    ("in_progress", "done"), ("in_progress", "declined"), ("in_progress", "spam"),
    ("in_progress", "open"),
    # Aus einem abgeschlossenen Zustand führt nur der Weg zurück an den Anfang.
    ("done", "open"), ("declined", "open"), ("spam", "open"),
}


@pytest.mark.parametrize("von", ALLE)
@pytest.mark.parametrize("nach", ALLE)
def test_uebergangstabelle(von, nach):
    if von == nach or (von, nach) in ERLAUBT:
        service.pruefe_uebergang(von, nach)  # wirft nicht
        return
    with pytest.raises(Exception) as fehler:
        service.pruefe_uebergang(von, nach)
    assert fehler.value.status_code == 409


def test_gleicher_status_ist_kein_wechsel():
    """Die Oberfläche schickt den Status mit, auch wenn nur die Antwort sich ändert."""
    for s in ALLE:
        service.pruefe_uebergang(s, s)


def test_abgeschlossen_ist_genau_die_drei():
    """Woran die Nullung von Kontakt und Anhang hängt — und die 180-Tage-Frist."""
    assert service.ABGESCHLOSSEN == {"done", "declined", "spam"}
