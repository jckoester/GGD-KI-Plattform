"""Strukturprüfung: Welche pseudonym-geführten Tabellen räumt die Kontolöschung ab?

**Warum es diesen Test gibt.** `calendar_sync_status` (UP-8, Schritt 10a) wurde angelegt,
ohne die Löschung aus ADR-003 Teil 6 mitzuziehen — aufgefallen ist das erst in Schritt 11,
zufällig. Nichts hätte es gemeldet: Die Tabelle hängt ohne Fremdschlüssel am Pseudonym, ein
vergessener Eintrag fällt nirgends auf, er hinterlässt nur still Daten.

Dieser Test zwingt für **jede** neue Tabelle mit Pseudonym-Spalte eine Entscheidung:
löschen, per Cascade abdecken, oder hier mit Begründung ausnehmen. Er prüft **nicht**, ob
die Ausnahmen richtig sind — nur, dass keine Tabelle unbemerkt durchrutscht.
"""

import ast
from pathlib import Path

from sqlalchemy import inspect as sa_inspect

from app.db.models import Base

_PSEUDONYM_SPALTEN = {"pseudonym", "owner_pseudonym", "updated_by_pseudonym"}

_CLEANUP = Path(__file__).resolve().parents[2] / "app" / "crons" / "cleanup_service.py"

# Tabellen, die die Kontolöschung bewusst **nicht** anfasst.
#
# ⚠️ Diese Liste ist eine Bestandsaufnahme, keine Freigabe. Die mit „OFFEN" markierten
# Einträge sind ungeklärte Altfälle aus früheren Phasen — sie stehen hier, damit sie
# sichtbar sind, nicht weil sie entschieden wären.
_AUSGENOMMEN = {
    # Cascade über conversations.id (ondelete="CASCADE") — geht mit den Konversationen.
    "generated_images": "Cascade über conversations",
    # Kein Personenmerkmal des Kontos, sondern Bearbeitungsspur an einem geteilten Objekt.
    "assistants": "updated_by_pseudonym ist Bearbeitungsspur, nicht Kontodatum",
    # Eigene Aufbewahrungsfrist (expires_at) — Artefakte verfallen ohnehin.
    "artifacts": "eigene Frist über expires_at",
    # OFFEN — Altfälle, in dieser Phase nicht entschieden:
    "context_nodes": "OFFEN: persönliche Wissensknoten überleben das Konto",
    "node_engagement": "OFFEN: Lernzustand überlebt das Konto",
    "group_memberships": "OFFEN: Mitgliedschaft wird beim Login synchronisiert, nicht gelöscht",
    "teacher_group_exclusions": "OFFEN: Ausblendungen überleben das Konto",
}


def _geloeschte_modelle() -> set[str]:
    """Modellnamen aus den `delete(X)`-Aufrufen in `cleanup_inactive_accounts`.

    Über den Syntaxbaum statt per Textsuche: Ein `delete(` in einem Kommentar oder in
    `cleanup_stale_conversations` soll nicht mitzählen.
    """
    baum = ast.parse(_CLEANUP.read_text(encoding="utf-8"))
    funktion = next(
        k
        for k in ast.walk(baum)
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "cleanup_inactive_accounts"
    )
    namen = set()
    for knoten in ast.walk(funktion):
        if (
            isinstance(knoten, ast.Call)
            and isinstance(knoten.func, ast.Name)
            and knoten.func.id == "delete"
            and knoten.args
            and isinstance(knoten.args[0], ast.Name)
        ):
            namen.add(knoten.args[0].id)
    return namen


def _tabellen_mit_pseudonym() -> dict[str, str]:
    """Tabellenname → Modellname für alle Modelle mit Pseudonym-Spalte."""
    gefunden = {}
    for mapper in Base.registry.mappers:
        modell = mapper.class_
        spalten = {c.name for c in sa_inspect(modell).columns}
        if spalten & _PSEUDONYM_SPALTEN:
            gefunden[modell.__tablename__] = modell.__name__
    return gefunden


def test_jede_pseudonym_tabelle_ist_entschieden():
    """Jede Tabelle mit Pseudonym ist entweder gelöscht oder begründet ausgenommen."""
    geloescht = _geloeschte_modelle()
    offen = {
        tabelle: modell
        for tabelle, modell in _tabellen_mit_pseudonym().items()
        if modell not in geloescht and tabelle not in _AUSGENOMMEN
    }
    assert not offen, (
        "Neue Tabelle(n) mit Pseudonym-Spalte, die die Kontolöschung nicht kennt: "
        f"{sorted(offen)}. Entweder in `cleanup_inactive_accounts` löschen oder in "
        "`_AUSGENOMMEN` mit Begründung eintragen."
    )


def test_stundenplan_kuerzel_und_abrufstatus_werden_geloescht():
    """UP-8, Schritt 11 — die beiden Spuren der Kalenderanbindung namentlich festgehalten.

    Die allgemeine Prüfung oben ließe sich durch einen Eintrag in `_AUSGENOMMEN`
    stilllegen; diese hier nicht.
    """
    geloescht = _geloeschte_modelle()
    assert "UserPreference" in geloescht      # trägt das Kürzel
    assert "CalendarSyncStatus" in geloescht  # trägt den Abrufstatus


def test_ausnahmeliste_bleibt_aktuell():
    """Eine Ausnahme für eine Tabelle, die es nicht mehr gibt, verschleiert den Stand."""
    tabellen = set(_tabellen_mit_pseudonym())
    verwaist = set(_AUSGENOMMEN) - tabellen
    assert not verwaist, f"Ausnahme ohne zugehörige Tabelle: {sorted(verwaist)}"
