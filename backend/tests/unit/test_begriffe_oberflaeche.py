"""Wächter: Meldungen an Nutzer:innen benutzen die Wörter der Oberfläche (0.40, Päckchen AM).

Geprüft werden die Texte in `HTTPException(…)` unter `app/` — das `detail` erscheint in der
Oberfläche. „Knoten“ heißt dort „Baustein“ (Schritt 7a). Log-Meldungen und Texte für das
Modell sind nicht gemeint (Plan F7). Schritt 8 ergänzt „Wissensgraph“ und „Artefakt“.
"""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _meldungen():
    for pfad in APP.rglob("*.py"):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
            if name != "HTTPException":
                continue
            for teil in [*knoten.args, *(k.value for k in knoten.keywords)]:
                for c in ast.walk(teil):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        yield f"{pfad.relative_to(APP)}:{c.lineno}", c.value


def test_die_suche_greift():
    assert sum(1 for _ in _meldungen()) > 100


def test_kein_knoten_in_meldungen():
    funde = [f"{ort}: {text!r}" for ort, text in _meldungen()
             if re.search(r"knoten", text, re.IGNORECASE)]
    assert funde == []
