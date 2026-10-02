"""`budget` und `statistics` sind in Produktion vergebbar (0.12, Paket 2, AP1).

Beide Rollen prüfen Backend und Frontend seit Langem (`api/admin/budgets.py`,
`api/admin/stats.py`, `UserMenu.svelte`), `test_users.yaml` vergibt sie — im Dev
funktionierten sie also. In Produktion kommen Rollen aber nur über `group_role_map`, und
deren Typ ließ sie nicht zu. Aufgefallen bei F3 („alle, die Budget verwalten").
"""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.auth.base import NormalizedIdentity
from app.auth.config import GroupRoleMapping


@pytest.mark.parametrize("rolle", ["budget", "statistics"])
def test_rolle_laesst_sich_ueber_eine_gruppe_vergeben(rolle):
    assert GroupRoleMapping(group="Verwaltung", role=rolle).role == rolle


def test_unbekannte_rolle_bleibt_abgewiesen():
    """Die Liste ist erweitert, nicht geöffnet — ein Tippfehler fällt weiter auf."""
    with pytest.raises(ValidationError):
        GroupRoleMapping(group="X", role="budjet")


def test_lehrkraft_mit_budgetrolle_meldet_sich_an():
    """Der Regelfall: Wer Budget verwaltet, ist Lehrkraft und zusätzlich in der Gruppe."""
    assert NormalizedIdentity(external_id="a", roles=["teacher", "budget"]).roles == [
        "teacher", "budget",
    ]


def test_budgetrolle_allein_ist_kein_login():
    """⚠️ Bekannte Grenze, bewusst so festgehalten: `budget` und `statistics` sind
    **zusätzliche** Rollen wie `admin`, keine eigenständigen. Wer nur in der Budgetgruppe
    ist (etwa das Sekretariat), kann sich nicht anmelden. Ob sie wie `review` eigenständig
    werden sollen, ist eine Rechte-Entscheidung und offen (Plan, AP1).

    Wird das geändert, schlägt dieser Test fehl — dann ist er umzuschreiben, nicht zu
    löschen: Die Frage, was eine reine Budget-Person im Chat sieht, gehört dann geprüft.
    """
    with pytest.raises(ValidationError):
        NormalizedIdentity(external_id="b", roles=["budget"])
