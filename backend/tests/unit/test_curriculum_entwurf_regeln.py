"""Regeln für Curriculum-Entwürfe ohne Datenbank (0.45, Päckchen AP Teil A, Schritt 1).

Die Gegenproben mit Datenbank stehen in `tests/integration/test_curriculum_entwurf.py`.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import pytest
from fastapi import HTTPException

from app.auth.config import AuthConfig
from app.context.curriculum_entwurf import pruefe_kante, pruefe_statuswechsel


@pytest.mark.parametrize("alt,neu", [("draft", "active"), ("draft", "archived"), ("active", "draft"),
                                     ("archived", "draft")])
def test_kein_statuswechsel_von_oder_nach_entwurf(alt, neu):
    with pytest.raises(HTTPException) as e:
        pruefe_statuswechsel(alt, neu)
    assert e.value.status_code == 422


@pytest.mark.parametrize("alt,neu", [("active", "archived"), ("archived", "active"), ("draft", None),
                                     ("draft", "draft")])
def test_uebrige_wechsel_bleiben_erlaubt(alt, neu):
    pruefe_statuswechsel(alt, neu)


def test_auf_entwurf_zeigt_nur_ein_entwurf():
    pruefe_kante("draft", "draft")
    pruefe_kante("draft", "active")  # Lernsequenz → Kompetenz
    pruefe_kante("active", "active")
    with pytest.raises(HTTPException):
        pruefe_kante("active", "draft")


def test_fachvorsitz_ist_vergebbar():
    """Ohne Eintrag in `VergebbareRolle` könnte die Rolle in Produktion niemand bekommen —
    so erging es `budget` und `statistics` bis 0.12."""
    cfg = AuthConfig(adapter="yaml_test", group_role_map=[{"group": "ki-fachvorsitz", "role": "fachvorsitz"}])
    assert cfg.group_role_map_dict == {"ki-fachvorsitz": "fachvorsitz"}
