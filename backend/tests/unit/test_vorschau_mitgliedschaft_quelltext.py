"""Wächter: Die eigenen Mitgliedschaften werden nur über `mitglied()` gelesen (0.29).

In der Vorschau ist die Lehrkraft nur Schüler:in der gewählten Gruppe
(`app/auth/vorschau.py`). Ein direkter Vergleich ``GroupMembership.pseudonym == …`` sähe
ihre echten Mitgliedschaften — als Lehrkraft, in allen Gruppen. Genau so standen vor 0.29
die Wege zum Umbenennen einer Unterrichtsgruppe offen: Sie prüfen nur die Mitgliedschaft,
keine Rolle.

Ausgenommen sind Stellen, die nie mit einer Vorschau laufen oder nach **anderen** Personen
fragen.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

AUSNAHMEN = {
    "auth/vorschau.py": "der Helfer selbst",
    "auth/group_sync.py": "Abgleich beim Login — keine Vorschau, schreibt echte Mitgliedschaften",
    "api/admin/groups.py": "Admin-Wege, verwalten fremde Mitgliedschaften",
    "crons/cleanup_service.py": "Kontolöschung, läuft ohne Anfrage",
}


def _treffer():
    for datei in APP.rglob("*.py"):
        rel = datei.relative_to(APP).as_posix()
        for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
            if "GroupMembership.pseudonym ==" in zeile and not zeile.lstrip().startswith("#"):
                yield rel, nr


def test_kein_direkter_vergleich_ausserhalb_der_ausnahmen():
    verstoesse = [f"{d}:{n}" for d, n in _treffer() if d not in AUSNAHMEN]
    assert not verstoesse, (
        "Eigene Mitgliedschaften über `app.auth.vorschau.mitglied(pseudonym, rolle)` lesen, "
        f"nicht direkt — sonst sieht die Vorschau die Lehrkraft: {verstoesse}"
    )


def test_die_ausnahmen_gibt_es_noch():
    """Eine Ausnahme ohne Treffer ist eine tote Zeile, die später etwas durchwinkt."""
    mit_treffer = {d for d, _ in _treffer()}
    assert set(AUSNAHMEN) <= mit_treffer, set(AUSNAHMEN) - mit_treffer


def test_rolle_nicht_neben_mitglied_pruefen():
    """`mitglied(p)` plus eigenes ``role_in_group == "teacher"`` fragte in der Vorschau die
    echte Rolle ab. Die Rolle gehört in den Helfer: ``mitglied(p, "teacher")``."""
    verstoesse = []
    for datei in APP.rglob("*.py"):
        zeilen = datei.read_text(encoding="utf-8").splitlines()
        for i, zeile in enumerate(zeilen):
            if re.search(r"\bmitglied\(", zeile) and "def mitglied" not in zeile:
                fenster = zeilen[max(0, i - 4): i + 5]
                if any("role_in_group ==" in z for z in fenster):
                    verstoesse.append(f"{datei.relative_to(APP).as_posix()}:{i + 1}")
    assert not verstoesse, verstoesse
