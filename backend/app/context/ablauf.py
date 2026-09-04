"""Das Ablaufdatum, das die Taxonomie für eine Bausteinart vorsieht.

**Eine Wahrheit, ein Aufrufweg.** Knoten entstehen an fünf Stellen — dem allgemeinen
Anlege-Endpunkt, dem Kopieren, der Unterrichtseinheit, der Stunde aus dem Planer und der
Stunde aus dem Planungsassistenten —, und keine davon ging bis 04.09.2026 durch die
andere. Die Vorgabe dort fünfmal einzutragen hieße, fünf Gelegenheiten zu schaffen, sie
beim sechsten Erzeuger zu vergessen. Deshalb hängt sie als ``before_insert``-Regel am
Modell (:mod:`app.db.models`) und nicht an den Aufrufern.

⚠️ **Ein gesetztes Datum bleibt unangetastet.** Die Regel füllt nur, was leer ist. Wer
ausdrücklich ein anderes Ende will, trägt es ein; wer gar keins will, leert das Feld nach
dem Anlegen — beim Ändern gilt der übergebene Wert unverändert, auch ``null``. Der
Unterschied ist beabsichtigt: Beim Anlegen gibt es keine vorherige Absicht, beim Ändern
schon.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def vorgeschlagenes_ablaufdatum(content_type: str | None) -> date | None:
    """Das ``valid_until`` aus der Taxonomie (``None`` = dauerhaft).

    Zwei Formen: ein Tages-Offset ab heute (``valid_until_default: 42``) oder das Ende des
    laufenden Schuljahres (``valid_until_default: schuljahresende``). Aktuell trägt kein
    Typ einen Offset; sieben tragen das Schuljahresende.
    """
    from app.context.taxonomy import (
        get_valid_until_offset,
        get_valid_until_schuljahresende,
    )

    heute = datetime.now(timezone.utc).date()

    if get_valid_until_schuljahresende(content_type):
        from app.planning.calendar import load_school_year

        ende = load_school_year().ende
        # ⚠️ Ein Schuljahresende in der Vergangenheit heißt: `school_year.yaml` ist nicht
        # umgestellt. Diesen Wert zu setzen wäre schlimmer als keiner — der nächtliche
        # Lauf archivierte den Baustein noch in derselben Nacht, und das Anlegen bzw. die
        # Reaktivierung sähe aus, als hätte sie nicht funktioniert. Am Live-Test am
        # 02.09.2026 genau so aufgetreten (Config stand auf 2025/26, Ende 29.07.2026).
        if ende <= heute:
            logger.warning(
                "Schuljahresende %s liegt nicht in der Zukunft — Baustein bekommt kein "
                "Ablaufdatum. config/school_year.yaml umstellen "
                "(docs/runbooks/schuljahreswechsel.md).", ende,
            )
            return None
        return ende

    tage = get_valid_until_offset(content_type)
    return (heute + timedelta(days=tage)) if tage else None
