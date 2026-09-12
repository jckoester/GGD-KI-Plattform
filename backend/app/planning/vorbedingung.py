"""Optimistisches Sperren: schreiben nur, wenn sich seither nichts geändert hat.

**Wofür.** `PATCH /planning/slots/{id}` und `PATCH /planning/lessons/{id}` sind
last-write-wins. Im Browser ist das in Ordnung — wer zwei Fenster offen hat, sieht seinen
eigenen Stand. Für einen Sync-Client ist es das nicht: Er schreibt einen Stand zurück, den
er vor Minuten gelesen hat, und überschreibt dabei stillschweigend, was inzwischen in der
Oberfläche entstanden ist.

**Freiwillig, nicht Pflicht.** Ohne `expected_updated_at` bleibt es beim bisherigen
Verhalten. Ein Pflichtfeld hätte jede bestehende Oberfläche gebrochen, und der Nutzen ist
einseitig: Wer nebenläufig schreibt, weiß das von sich.

⚠️ **Das setzt voraus, dass `updated_at` sich überhaupt bewegt.** Bis 12.09.2026 tat es
das auf mehreren Schreibwegen nicht — dann ginge der Vergleich immer auf, der 409 käme
nie, und man hielte sich für abgesichert. `test_updated_at_wird_fortgeschrieben.py` hält
die Voraussetzung fest; ohne sie ist diese Datei schlimmer als nichts.
"""

from datetime import datetime

from fastapi import HTTPException


def pruefe(tatsaechlich: datetime, erwartet: datetime | None, was: str) -> None:
    """Wirft 409, wenn `erwartet` gesetzt ist und nicht dem aktuellen Stand entspricht.

    `erwartet is None` heißt „ohne Vorbedingung" — kein Sperren, altes Verhalten.

    Verglichen wird auf **Gleichheit**, nicht auf „älter": Ein Client, der einen neueren
    Stempel schickt als der Server führt, hat ebenso ein falsches Bild — nur andersherum,
    und stillschweigend durchzulassen wäre die schlechtere Antwort.

    Der Körper nennt beide Werte. Ein blankes 409 ließe offen, ob der Client zu alt ist
    oder seinen Stempel falsch formatiert hat; mit beiden Werten sieht man es.
    """
    if erwartet is None:
        return
    if tatsaechlich != erwartet:
        raise HTTPException(
            status_code=409,
            detail={
                "grund": "veraltet",
                "nachricht": (
                    f"{was} wurde inzwischen geändert. Bitte neu laden und die Änderung "
                    "darauf aufsetzen."
                ),
                "erwartet": erwartet.isoformat(),
                "tatsaechlich": tatsaechlich.isoformat(),
            },
        )
