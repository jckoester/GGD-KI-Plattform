"""Der Lebenszyklus eines Assistenten — getrennt nach Reichweite (Paket 7, AP4).

**Der Auftrag** (Jan, 25.09.2026): „Unterrichtsgruppenassistenten müssten den kompletten
Lebenszyklus ohne Adminfreigabe durchlaufen können. Schulweite Assistenten müssen nicht
sofort deaktiviert werden."

**Der Befund beim Nachmessen:** Sie konnten es nicht — ab dem Moment ihrer Entstehung.
`_initial_status` gibt einem privaten, Gruppen- oder Fachschafts-Assistenten sofort
`active` (so gewollt, keine Freigabe), und `_check_assistant_update_permission` erlaubte
PATCH nur im Status `draft`. In `draft` kam er nie. Bearbeiten, Abschalten und Löschen
gingen damit nur über einen Admin.

Die Zielmatrix, die dieser Test festhält:

| | privat · Gruppe · Fachschaft | schulweit (`teachers`, `grade`, `all_students`, `all`) |
|---|---|---|
| Anlegen | sofort `active` | `pending_review` |
| Bearbeiten | jederzeit | nur im Entwurf |
| Löschen | jederzeit | Entwurf/eingereicht selbst, sonst Antrag |

⚠️ **Beide Richtungen.** Ein Test, der nur das Erlaubte prüft, ginge auch dann durch,
wenn gar nichts mehr geprüft würde.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.assistants import (
    GROUP_SCOPES,
    SCHOOLWIDE_SCOPES,
    VALID_SCOPES,
    _check_assistant_delete_permission,
    _check_assistant_update_permission,
    _initial_status,
)
from app.auth.jwt import JwtPayload

LEHRKRAFT = JwtPayload(
    sub="lk1", roles=["teacher"], grade=None, jti="j", iat=1, exp=9_999_999_999
)
FREMDE = JwtPayload(
    sub="lk2", roles=["teacher"], grade=None, jti="j", iat=1, exp=9_999_999_999
)

EIGENE = ["private", "teaching_group", "subject_department", "activity_group"]
SCHULWEIT = sorted(SCHOOLWIDE_SCOPES)


def _assistent(scope: str, status: str = "active", besitzer: str = "lk1"):
    return SimpleNamespace(scope=scope, status=status, created_by=besitzer)


def _darf(pruefung, assistent, nutzer=LEHRKRAFT) -> bool:
    try:
        pruefung(assistent, nutzer, False)
        return True
    except HTTPException:
        return False


# ── Anlegen ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scope", EIGENE)
def test_eigene_reichweiten_entstehen_sofort_aktiv(scope):
    """Ohne Freigabe — das war schon so und bleibt so."""
    assert _initial_status(scope, "teacher", "all", None) == "active"


@pytest.mark.parametrize("scope", SCHULWEIT)
def test_schulweite_reichweiten_gehen_in_die_freigabe(scope):
    assert _initial_status(scope, "teacher", "all", None) == "pending_review"


def test_alle_lehrkraefte_zaehlt_als_schulweit():
    """⚠️ **Der Scope `teachers` fehlte in beiden Mengen** (bis 25.09.2026).

    Er ist weder eine Gruppe noch stand er in `SCHOOLWIDE_SCOPES` — ein Assistent „für
    alle Lehrkräfte" entstand deshalb ohne Freigabe und war zugleich frei änderbar,
    obwohl er das ganze Kollegium erreicht.
    """
    assert "teachers" in SCHOOLWIDE_SCOPES
    assert "teachers" not in GROUP_SCOPES


def test_jede_reichweite_ist_einer_seite_zugeordnet():
    """Kein dritter Fall: Was weder Gruppe noch schulweit ist, fiele durch jede Regel.

    `private` ist die eine Ausnahme — sie erreicht niemanden außer der Urheberin.
    """
    zugeordnet = GROUP_SCOPES | SCHOOLWIDE_SCOPES | {"private"}
    assert VALID_SCOPES == zugeordnet


# ── Bearbeiten ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scope", EIGENE)
@pytest.mark.parametrize("status", ["active", "draft", "disabled"])
def test_eigene_reichweiten_sind_jederzeit_bearbeitbar(scope, status):
    """⚠️ **Der eigentliche Fehler.** Vorher: 409, in jedem dieser Fälle."""
    assert _darf(_check_assistant_update_permission, _assistent(scope, status))


@pytest.mark.parametrize("scope", SCHULWEIT)
def test_schulweit_nur_im_entwurf_bearbeitbar(scope):
    assert _darf(_check_assistant_update_permission, _assistent(scope, "draft"))
    for status in ("pending_review", "active"):
        assert not _darf(_check_assistant_update_permission, _assistent(scope, status)), (
            f"{scope}/{status} dürfte nicht bearbeitbar sein — die Freigabe prüfte einen "
            "Prompt, der sich danach still ändern ließe."
        )


@pytest.mark.parametrize("scope", EIGENE + SCHULWEIT)
def test_fremde_assistenten_bleiben_tabu(scope):
    """Die Lockerung gilt für **eigene** Assistenten, nicht für fremde."""
    assert not _darf(
        _check_assistant_update_permission, _assistent(scope), nutzer=FREMDE
    )


# ── Löschen ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scope", EIGENE)
@pytest.mark.parametrize("status", ["active", "draft", "disabled"])
def test_eigene_reichweiten_sind_jederzeit_loeschbar(scope, status):
    """Die Chats bleiben — `assistant_id` steht auf `ON DELETE SET NULL`."""
    assert _darf(_check_assistant_delete_permission, _assistent(scope, status))


@pytest.mark.parametrize("scope", SCHULWEIT)
def test_schulweit_nur_vor_der_freigabe_selbst_loeschbar(scope):
    for status in ("draft", "pending_review"):
        assert _darf(_check_assistant_delete_permission, _assistent(scope, status))
    assert not _darf(_check_assistant_delete_permission, _assistent(scope, "active")), (
        "Ein freigegebener schulweiter Assistent wird beantragt, nicht gelöscht."
    )


# ── Die Menge gibt es zweimal ────────────────────────────────────────────────

def test_frontend_kennt_dieselben_schulweiten_reichweiten():
    """⚠️ **Genau dieses Auseinanderlaufen war der Fehler.**

    Die Oberfläche entscheidet mit derselben Menge über die Bearbeitbarkeit
    (`AssistantEditor.svelte`). Kennt sie eine Reichweite als „nicht schulweit", die der
    Server als schulweit führt, bietet sie ein Feld an, das das Speichern mit 409
    ablehnt — und niemand sieht warum.
    """
    quelle = (
        Path(__file__).resolve().parents[3]
        / "frontend/src/lib/components/AssistantEditor.svelte"
    )
    text = quelle.read_text(encoding="utf-8")
    zeile = next(z for z in text.splitlines() if "SCHOOLWIDE_SCOPES = new Set" in z)
    im_frontend = set(teil.strip(' "\'') for teil in zeile.split("[")[1].split("]")[0].split(","))
    assert im_frontend == SCHOOLWIDE_SCOPES, (
        f"Frontend: {sorted(im_frontend)} · Backend: {sorted(SCHOOLWIDE_SCOPES)}"
    )
