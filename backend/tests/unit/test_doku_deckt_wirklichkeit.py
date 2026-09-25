"""Aufzählungen in der Doku gegen die Wirklichkeit (Paket 7, AP7).

Drei Tabellen beschreiben, was das System tut: die Backend-Module in
`docs/dev/architektur.md`, die nächtlichen Läufe und die Kontolöschung in
`docs/admin/datenschutz-betrieb.md`. Alle drei **sahen vollständig aus** und waren es
nicht — 12 von 21 Modulen, 5 von 14 Läufen, 5 von 13 Löschkategorien.

⚠️ **Das Muster ist wichtiger als die drei Fälle.** Eine Aufzählung, an die nichts
erinnert, wächst nicht mit; sie veraltet still und wird trotzdem gelesen — die
Modultabelle von Entwickler:innen beim Einstieg, die Löschtabelle von der
Datenschutzbeauftragten. Nachziehen hilft einmal, prüfen hilft dauerhaft.

**Vorbild:** `test_pseudonym_deletion_coverage.py`, der dieselbe Aufgabe für den Code
löst (jede Tabelle mit Pseudonym-Spalte ist entschieden).

⚠️ **Gegengeprüft:** Jeder Test hier muss rot werden, wenn man der Wirklichkeit etwas
hinzufügt, ohne die Doku zu ergänzen. Ein Wächter, der das nicht tut, bescheinigt
Vollständigkeit, statt sie zu prüfen.
"""

import ast
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[3]
APP = WURZEL / "backend" / "app"
ARCHITEKTUR = (WURZEL / "docs" / "dev" / "architektur.md").read_text(encoding="utf-8")
BETRIEB = (WURZEL / "docs" / "admin" / "datenschutz-betrieb.md").read_text(encoding="utf-8")
COMPOSE = (WURZEL / "docker-compose.yml").read_text(encoding="utf-8")


# ── 1. Backend-Module ────────────────────────────────────────────────────────

def _module() -> set[str]:
    """Die Paketverzeichnisse unter `backend/app/` — ohne Bytecode-Reste."""
    return {
        p.name
        for p in APP.iterdir()
        if p.is_dir() and p.name != "__pycache__" and (p / "__init__.py").exists()
    }


def test_jedes_backend_modul_steht_in_der_architektur():
    """Der zentrale Einstiegspunkt für Entwickler:innen — und der wird zuerst gelesen."""
    tabelle = ARCHITEKTUR[ARCHITEKTUR.index("## Backend-Module"):]
    tabelle = tabelle[: tabelle.index("\n## ")]
    fehlend = sorted(m for m in _module() if f"`{m}/`" not in tabelle)
    assert not fehlend, (
        f"Modul(e) ohne Zeile in der Tabelle „Backend-Module“: {fehlend}. "
        "Eine Zeile mit einem Satz, was das Modul tut — oder das Modul löschen."
    )


# ── 2. Nächtliche Läufe ──────────────────────────────────────────────────────

def _cronjobs() -> set[str]:
    """Die Skriptnamen aus den `cron.d`-Zeilen der Compose-Datei."""
    return set(re.findall(r"/app/scripts/(\w+)\.py", COMPOSE))


def test_jeder_cronjob_steht_in_der_betriebsdoku():
    """Wer wissen will, was der Server nachts tut, soll es vollständig finden."""
    fehlend = sorted(j for j in _cronjobs() if f"`{j}`" not in BETRIEB)
    assert not fehlend, (
        f"Cron-Lauf/Läufe ohne Zeile in `datenschutz-betrieb.md`: {fehlend}. "
        "In die Tabelle „Automatische Läufe“ eintragen, mit Zeitplan und Wirkung."
    )


def test_die_doku_erfindet_keine_laeufe():
    """Die Gegenrichtung: ein Eintrag für einen Lauf, den es nicht mehr gibt.

    Schlimmer als eine Lücke, weil er eine Zusage macht, die niemand einlöst.
    """
    tabelle = BETRIEB[BETRIEB.index("## Automatische Läufe"):]
    tabelle = tabelle[: tabelle.index("\n### ")]
    genannt = set(re.findall(r"^\| `(\w+)`", tabelle, re.MULTILINE))
    erfunden = sorted(genannt - _cronjobs())
    assert not erfunden, f"In der Doku, aber in keiner Cron-Zeile: {erfunden}"


# ── 3. Kontolöschung ─────────────────────────────────────────────────────────

_CLEANUP = APP / "crons" / "cleanup_service.py"

# Modellname → Tabellenname, soweit sie sich nicht durch Kleinschreibung ergeben.
# Bewusst hier und nicht aus `Base.registry`: Der Test soll ohne Datenbank und ohne
# vollständigen App-Import laufen wie sein Vorbild.
_TABELLE = {
    "Conversation": "conversations",
    "PseudonymAudit": "pseudonym_audit",
    "UserPreference": "user_preferences",
    "CalendarSyncStatus": "calendar_sync_status",
    "PersonalAccessToken": "personal_access_tokens",
    "JwtRevocation": "jwt_revocations",
    "BudgetAccrual": "budget_accruals",
    "Artifact": "artifacts",
    "NodeEngagement": "node_engagement",
    "GroupMembership": "group_memberships",
    "TeacherGroupExclusion": "teacher_group_exclusions",
    "SsoGroupOffer": "sso_group_offers",
    "ContextNode": "context_nodes",
    "Feedback": "feedback",
    "GroupJoinCode": "group_join_codes",
}


def _abgeraeumte_modelle() -> set[str]:
    """Modelle aus `delete(X)` in `cleanup_inactive_accounts` — über den Syntaxbaum."""
    baum = ast.parse(_CLEANUP.read_text(encoding="utf-8"))
    fn = next(
        k for k in ast.walk(baum)
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "cleanup_inactive_accounts"
    )
    return {
        k.args[0].id
        for k in ast.walk(fn)
        if isinstance(k, ast.Call)
        and isinstance(k.func, ast.Name)
        and k.func.id == "delete"
        and k.args
        and isinstance(k.args[0], ast.Name)
    }


def test_jede_geloeschte_kategorie_steht_in_der_betriebsdoku():
    """Die Tabelle, die man einem DSB vorlegt — sie muss vollständig sein.

    ⚠️ Die Löschung *geschieht*; unvollständig ist nur ihre Beschreibung. Das ist die
    weniger schlimme Richtung des Fehlers und trotzdem einer: Eine Auskunft, die eine
    Kategorie verschweigt, ist falsch, auch wenn die Daten längst weg sind.
    """
    # ⚠️ **Der Abschnitt, nicht der Rest der Datei.** Der erste Entwurf schnitt von der
    # Überschrift bis zum Dateiende — und fand `node_engagement` sechzig Zeilen weiter
    # unten in einem ganz anderen Absatz. Die Gegenprobe (Zeile aus der Tabelle gelöscht)
    # kam daraufhin grün zurück. Derselbe Fehler wie beim `.dark {`-Wächter im Frontend.
    abschnitt = BETRIEB[BETRIEB.index("### Was die Kontolöschung abräumt"):]
    abschnitt = abschnitt[: abschnitt.index("\n## ")]
    unbekannt = sorted(m for m in _abgeraeumte_modelle() if m not in _TABELLE)
    assert not unbekannt, (
        f"Neues Modell in der Kontolöschung, das dieser Test nicht kennt: {unbekannt}. "
        "In `_TABELLE` den Tabellennamen ergänzen und die Doku-Zeile schreiben."
    )
    fehlend = sorted(
        _TABELLE[m] for m in _abgeraeumte_modelle() if f"`{_TABELLE[m]}`" not in abschnitt
    )
    assert not fehlend, (
        f"Gelöschte Kategorie(n) ohne Zeile in der Doku: {fehlend}. "
        "In `docs/admin/datenschutz-betrieb.md` eintragen — und in ADR-003 Teil 6."
    )
