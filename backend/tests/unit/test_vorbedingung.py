"""Die Vorbedingung des optimistischen Sperrens — ohne Datenbank.

Die Fallunterscheidung ist klein genug, dass sie sich hier vollständig prüfen lässt; die
Integrationstests zeigen dann nur noch, dass sie an den Endpunkten auch greift.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.planning.vorbedingung import pruefe

JETZT = datetime(2026, 9, 12, 10, 0, 0, 123456, tzinfo=timezone.utc)


class TestOhneVorbedingung:
    def test_none_laesst_durch(self):
        """Das alte Verhalten bleibt der Normalfall — die Oberfläche schickt nichts."""
        pruefe(JETZT, None, "Diese Stunde")


class TestMitVorbedingung:
    def test_gleicher_stand_laesst_durch(self):
        pruefe(JETZT, JETZT, "Diese Stunde")

    def test_veralteter_stand_ergibt_409(self):
        with pytest.raises(HTTPException) as exc:
            pruefe(JETZT, JETZT - timedelta(seconds=1), "Diese Stunde")
        assert exc.value.status_code == 409
        assert exc.value.detail["grund"] == "veraltet"

    def test_neuerer_stand_ergibt_ebenfalls_409(self):
        """Nicht „älter", sondern „ungleich".

        Ein Client, der einen neueren Stempel schickt, als der Server führt, hat genauso
        ein falsches Bild — nur andersherum. Stillschweigend durchzulassen wäre die
        schlechtere Antwort.
        """
        with pytest.raises(HTTPException) as exc:
            pruefe(JETZT, JETZT + timedelta(seconds=1), "Diese Stunde")
        assert exc.value.status_code == 409

    def test_mikrosekunden_zaehlen(self):
        """Ein abgeschnittener Stempel ist nicht derselbe Stand.

        Wer die Mikrosekunden verliert (manche Formatierer tun das), bekommt ein 409 statt
        eines stillen Überschreibens — und sieht am Körper, woran es lag.
        """
        with pytest.raises(HTTPException):
            pruefe(JETZT, JETZT.replace(microsecond=0), "Diese Stunde")


class TestDieAntwortIstDiagnostizierbar:
    def test_beide_werte_stehen_im_koerper(self):
        """Ein blankes 409 ließe offen, ob der Client zu alt ist oder falsch formatiert."""
        erwartet = JETZT - timedelta(minutes=5)
        with pytest.raises(HTTPException) as exc:
            pruefe(JETZT, erwartet, "Dieser Slot")
        detail = exc.value.detail
        assert detail["erwartet"] == erwartet.isoformat()
        assert detail["tatsaechlich"] == JETZT.isoformat()
        assert "Dieser Slot" in detail["nachricht"]
