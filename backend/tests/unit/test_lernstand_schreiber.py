"""Wächter: Wer schreibt `node_engagement`? (0.29, Schritt 6, ADR-016 Nachtrag)

Persönlicher Lernstand aus dem Chat entsteht heute nirgends. Käme ein Schreiber dazu,
schriebe er auch aus der Vorschau — und eine Lehrkraft, die als Schüler:in ausprobiert,
hinterließe Lernstand unter ihrem eigenen Pseudonym. Dieser Test schlägt an, sobald eine neue
Datei `node_engagement` schreibt. Dann: `app.auth.vorschau.schreibt_lernstand(user)` fragen
und die Datei hier mit Begründung eintragen.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

#: Datei → warum sie schreiben darf, ohne die Vorschau zu fragen.
BEKANNTE_SCHREIBER = {
    "planning/review_service.py": "Gruppenstand (`introduced`, ohne Pseudonym) aus der "
                                  "Nachbereitung — Lehrkraft-Wege und Auto-Bestätigung per Cron",
    "crons/cleanup_service.py": "löscht mit dem Konto, schreibt nichts",
}

_SCHREIBEN = re.compile(
    r"(?:pg_)?insert\(\s*NodeEngagement\b|update\(\s*NodeEngagement\b|delete\(\s*NodeEngagement\b"
    r"|\bNodeEngagement\(|INSERT INTO node_engagement|UPDATE node_engagement"
)


def _schreiber() -> set[str]:
    gefunden = set()
    for datei in APP.rglob("*.py"):
        rel = datei.relative_to(APP).as_posix()
        if rel == "db/models.py":
            continue
        if _SCHREIBEN.search(datei.read_text(encoding="utf-8")):
            gefunden.add(rel)
    return gefunden


def test_nur_bekannte_schreiber():
    neu = sorted(_schreiber() - set(BEKANNTE_SCHREIBER))
    assert not neu, (
        f"Neuer Schreiber von node_engagement: {neu}. Aus der Vorschau darf kein "
        "Lernstand entstehen — `schreibt_lernstand(user)` fragen und hier eintragen."
    )


def test_die_bekannten_gibt_es_noch():
    assert set(BEKANNTE_SCHREIBER) <= _schreiber()


def test_schreibt_lernstand():
    from app.auth.jwt import JwtPayload
    from app.auth.vorschau import Vorschau, schreibt_lernstand

    basis = dict(sub="x", roles=["student"], grade="9", jti="j", iat=0, exp=2**31)
    assert schreibt_lernstand(JwtPayload(**basis))
    assert not schreibt_lernstand(JwtPayload(**basis, preview=Vorschau(
        echte_rollen=["teacher"], beginn=0, sitzung_ablauf=2**31)))
