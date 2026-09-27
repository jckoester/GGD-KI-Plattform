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

# ⚠️ **Suffix statt fester Liste** (erweitert 23.09.2026). Bis dahin standen hier drei
# Namen — `pseudonym`, `owner_pseudonym`, `updated_by_pseudonym`. Eine neue Spalte mit
# einem anderen Namen war für diesen Wächter unsichtbar, und genau das ist beim
# Beitrittscode passiert: `group_join_codes.erstellt_von` fiel durch, obwohl es ein
# Pseudonym führt. Der Wächter verspricht „jede Tabelle mit Pseudonym" — dann darf er
# nicht an einer Aufzählung hängen, die jemand pflegen muss.
#
# Die Regel hat einen Preis: Wer eine Pseudonym-Spalte anders benennt (`besitzer`,
# `angelegt_von`), rutscht weiterhin durch. Das ist hinnehmbar, solange die Konvention
# „endet auf `_pseudonym`" gilt — und sie steht jetzt in `docs/dev/`.
def _ist_pseudonymspalte(name: str) -> bool:
    return name == "pseudonym" or name.endswith("_pseudonym")


_PSEUDONYM_SPALTEN = {"pseudonym", "owner_pseudonym", "updated_by_pseudonym"}

_CLEANUP = Path(__file__).resolve().parents[2] / "app" / "crons" / "cleanup_service.py"

# Tabellen, die die Kontolöschung bewusst **nicht** anfasst.
#
# ⚠️ Diese Liste ist eine Bestandsaufnahme, keine Freigabe.
#
# Seit dem 08.09.2026 steht hier **kein „OFFEN" mehr** — die vier Altfälle aus früheren
# Phasen sind entschieden und werden gelöscht: `context_nodes` (nach `read_scope`
# getrennt, 07.09.), `artifacts`, `node_engagement`, `group_memberships` und
# `teacher_group_exclusions` (alle 08.09.). Damit ist Kriterium 3 der 1.0-Roadmap
# erfüllt. Wer hier einen neuen Eintrag ergänzt, begründet ihn — „später" ist keine
# Begründung, sondern der Zustand, aus dem dieser Test herausführen sollte.
_AUSGENOMMEN = {
    # Cascade über conversations.id (ondelete="CASCADE") — geht mit den Konversationen.
    "generated_images": "Cascade über conversations",
    # Kein Personenmerkmal des Kontos, sondern Bearbeitungsspur an einem geteilten Objekt.
    "assistants": "updated_by_pseudonym ist Bearbeitungsspur, nicht Kontodatum",
}


def _funktion() -> ast.AsyncFunctionDef:
    """Der Syntaxbaum von `cleanup_inactive_accounts` — nicht der ganzen Datei.

    Über den Baum statt per Textsuche: Ein `delete(` in einem Kommentar oder in
    `cleanup_stale_conversations` soll nicht mitzählen.
    """
    baum = ast.parse(_CLEANUP.read_text(encoding="utf-8"))
    return next(
        k
        for k in ast.walk(baum)
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "cleanup_inactive_accounts"
    )


def _geloeschte_modelle() -> set[str]:
    """Modellnamen aus den `delete(X)`-Aufrufen in `cleanup_inactive_accounts`."""
    funktion = _funktion()
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


def _anonymisierte_modelle() -> set[str]:
    """Modellnamen aus `update(X)…values(pseudonym=None)` in `cleanup_inactive_accounts`.

    Nicht jede Tabelle wird geleert. `context_nodes` behält geteilte Bausteine,
    `feedback` behält die Meldung — beide verlieren nur den Personenbezug. Ohne diesen
    zweiten Weg meldete der Wächter unten sie als vergessen, und der einzige Weg, ihn zu
    beruhigen, wäre ein Eintrag in `_AUSGENOMMEN`: genau die Verschleierung, gegen die
    er gebaut ist.

    Gezählt wird nur, was eine **Pseudonym-Spalte auf NULL** setzt. Ein `update(...)`,
    das irgendetwas anderes schreibt, macht eine Tabelle nicht personenbezugsfrei.
    """
    namen = set()
    for knoten in ast.walk(_funktion()):
        if not (
            isinstance(knoten, ast.Call)
            and isinstance(knoten.func, ast.Attribute)
            and knoten.func.attr == "values"
        ):
            continue
        nullt = any(
            kw.arg is not None
            and _ist_pseudonymspalte(kw.arg)
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is None
            for kw in knoten.keywords
        )
        if not nullt:
            continue
        # `update(X)` steht am Anfang derselben Aufrufkette (`update(X).where(…).values(…)`).
        for teil in ast.walk(knoten.func):
            if (
                isinstance(teil, ast.Call)
                and isinstance(teil.func, ast.Name)
                and teil.func.id == "update"
                and teil.args
                and isinstance(teil.args[0], ast.Name)
            ):
                namen.add(teil.args[0].id)
    return namen


def _tabellen_mit_pseudonym() -> dict[str, str]:
    """Tabellenname → Modellname für alle Modelle mit Pseudonym-Spalte."""
    gefunden = {}
    for mapper in Base.registry.mappers:
        modell = mapper.class_
        spalten = {c.name for c in sa_inspect(modell).columns}
        if any(_ist_pseudonymspalte(s) for s in spalten):
            gefunden[modell.__tablename__] = modell.__name__
    return gefunden


def test_jede_pseudonym_tabelle_ist_entschieden():
    """Jede Tabelle mit Pseudonym ist entweder gelöscht oder begründet ausgenommen."""
    behandelt = _geloeschte_modelle() | _anonymisierte_modelle()
    offen = {
        tabelle: modell
        for tabelle, modell in _tabellen_mit_pseudonym().items()
        if modell not in behandelt and tabelle not in _AUSGENOMMEN
    }
    assert not offen, (
        "Neue Tabelle(n) mit Pseudonym-Spalte, die die Kontolöschung nicht kennt: "
        f"{sorted(offen)}. Entweder in `cleanup_inactive_accounts` löschen, dort das "
        "Pseudonym auf NULL setzen oder in `_AUSGENOMMEN` mit Begründung eintragen."
    )


def test_stundenplan_kuerzel_und_abrufstatus_werden_geloescht():
    """UP-8, Schritt 11 — die beiden Spuren der Kalenderanbindung namentlich festgehalten.

    Die allgemeine Prüfung oben ließe sich durch einen Eintrag in `_AUSGENOMMEN`
    stilllegen; diese hier nicht.
    """
    geloescht = _geloeschte_modelle()
    assert "UserPreference" in geloescht      # trägt das Kürzel
    assert "CalendarSyncStatus" in geloescht  # trägt den Abrufstatus


def test_die_vier_entschiedenen_altfaelle_werden_geloescht():
    """08.09.2026 — namentlich festgehalten, damit die Entscheidung nicht still zurückfällt.

    Die allgemeine Prüfung oben ließe sich durch einen Eintrag in `_AUSGENOMMEN`
    stilllegen; diese hier nicht. Jede Zeile stand vorher als „OFFEN" in der
    Ausnahmeliste bzw. — bei `artifacts` — als Beschreibung des Status quo.
    """
    geloescht = _geloeschte_modelle()
    assert "Artifact" in geloescht               # Bibliothek ist strikt privat
    assert "NodeEngagement" in geloescht         # Lernzustand je Person
    assert "GroupMembership" in geloescht        # sonst bleiben Ehemalige Mitglied
    assert "TeacherGroupExclusion" in geloescht  # persönliche Ansichtseinstellung


def test_keine_offenen_faelle_mehr():
    """1.0-Kriterium 3 der Roadmap: Der Wächtertest kennt kein `OFFEN` mehr."""
    offen = {t: g for t, g in _AUSGENOMMEN.items() if "OFFEN" in g}
    assert not offen, (
        f"Wieder ungeklärte Ausnahmen: {sorted(offen)}. Kriterium 3 der 1.0-Roadmap "
        "verlangt für jede Tabelle mit Pseudonym-Spalte eine getroffene Entscheidung."
    )


def test_ausnahmeliste_bleibt_aktuell():
    """Eine Ausnahme für eine Tabelle, die es nicht mehr gibt, verschleiert den Stand."""
    tabellen = set(_tabellen_mit_pseudonym())
    verwaist = set(_AUSGENOMMEN) - tabellen
    assert not verwaist, f"Ausnahme ohne zugehörige Tabelle: {sorted(verwaist)}"


def test_feedback_wird_anonymisiert_statt_geloescht():
    """ADR-020 — die Meldung bleibt, der Personenbezug geht.

    Zwei Zusagen in einem Test, weil sie nur zusammen etwas wert sind: Ein `delete`
    statt der Nullung nähme der Sichtung die Vorgeschichte einer Regression; eine
    Nullung, die `contact` vergisst, ließe den einzigen möglichen Klarnamen im System
    stehen. Die allgemeine Prüfung oben deckt nur die erste Hälfte ab.
    """
    assert "Feedback" in _anonymisierte_modelle()
    assert "Feedback" not in _geloeschte_modelle()

    quelle = ast.unparse(_funktion())
    assert "contact=None" in quelle, "Die Kontaktangabe bleibt stehen"
