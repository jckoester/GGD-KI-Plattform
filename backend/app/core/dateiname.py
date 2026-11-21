"""Kennung für Dateinamen beim Herunterladen (0.50).

„Säure-Base-Titration“ → ``saeure-base-titration``. Bis 0.50 hatten Werkstatt und
Stundenexport je eine eigene Fassung: Die Werkstatt machte aus „Säure“ ``s-ure``, der
Stundenexport kannte kein „ß“.

**Nur für Dateinamen.** Kennungen, die als Identität gespeichert werden (etwa die der
Fachbegriffe, `fachbegriffe_import._slug`, auch in Alembic 0079), haben ihre eigene Regel
und bleiben unberührt.
"""
import re

_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def dateiname_slug(text: str | None, ersatz: str, laenge: int = 60) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"[äöüß]", lambda m: _UMLAUTE[m.group()], s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:laenge].strip("-") or ersatz
