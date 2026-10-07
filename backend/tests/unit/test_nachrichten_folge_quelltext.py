"""Wächter: Keine Abfrage sortiert Nachrichten nur nach `created_at` (07.10.2026).

Frage und Antwort eines Zuges tragen denselben Zeitstempel; die Folge legt
`NACHRICHTEN_FOLGE` in `app/db/models.py` fest. Eine neue Abfrage, die nur nach
`Message.created_at` sortiert, liefert die Antwort je nach Abfrageplan über der Frage —
und das fällt erst auf, wenn der Plan kippt. Deshalb ein Quelltext-Test statt eines
Laufzeittests je Stelle.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# `order_by(` … `Message.created_at` ohne zweites Kriterium — auch über Zeilen hinweg.
_NUR_ZEIT = re.compile(r"order_by\(\s*Message\.created_at(\.(asc|desc)\(\))?\s*\)")


def test_keine_sortierung_nur_nach_dem_zeitstempel():
    funde = [
        f"{pfad.relative_to(APP.parent)}"
        for pfad in APP.rglob("*.py")
        if _NUR_ZEIT.search(pfad.read_text(encoding="utf-8"))
    ]
    assert not funde, f"Nach `*NACHRICHTEN_FOLGE` sortieren, nicht nur nach der Zeit: {funde}"


def test_die_drei_gespraechsansichten_benutzen_die_folge():
    for datei in ("chat/router.py", "feedback/snapshot.py", "api/review.py"):
        assert "order_by(*NACHRICHTEN_FOLGE)" in (APP / datei).read_text(encoding="utf-8"), datei
