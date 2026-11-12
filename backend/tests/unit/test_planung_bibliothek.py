"""Unterrichtsplanung in der Bibliothek (0.40, Päckchen AM) — Liste und Wächter."""
from pathlib import Path

from app.context import taxonomy
from app.context.search import Suchprofil

APP = Path(__file__).resolve().parents[2] / "app"


def test_die_drei_planungstypen():
    assert set(taxonomy.PLANUNG_CONTENT_TYPES) == {"jahresplan", "unterrichtseinheit", "unterrichtsstunde"}
    assert set(taxonomy.PLANUNG_CONTENT_TYPES) <= set(taxonomy.CONTENT_TYPE_TO_CATEGORY)


def test_vorgabe_schliesst_nichts_aus():
    assert Suchprofil(pseudonym="p").ohne_typen == ()


def test_nur_der_suchendpunkt_blendet_aus():
    """⚠️ Der Chat muss Stunden finden („meine Stunde morgen“). `ohne_typen` setzt nur der
    Endpunkt der Suchseite; jede weitere Stelle wäre ein Weg, auf dem der Chat sie verliert."""
    nutzer = sorted(
        str(p.relative_to(APP)) for p in APP.rglob("*.py") if "ohne_typen" in p.read_text(encoding="utf-8")
    )
    assert nutzer == ["context/router.py", "context/search.py"]
