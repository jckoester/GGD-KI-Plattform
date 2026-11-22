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


def test_vermerk_im_export():
    from datetime import date

    from app.context.curriculum_export import entwurf_vermerk

    assert entwurf_vermerk({"status": "draft"}, date(2026, 11, 15)) == "Entwurf, Stand 15.11.2026"
    assert entwurf_vermerk({"status": "active"}) is None
    assert entwurf_vermerk({}) is None


def test_pdf_vorlage_zeigt_den_vermerk():
    import os

    from jinja2 import Environment, FileSystemLoader, select_autoescape

    import app.context.curriculum_export as export

    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(export.__file__), "templates")),
                      autoescape=select_autoescape(["html"]))
    vorlage = env.get_template("curriculum_pdf.html")
    mit = vorlage.render(title="T", school_name="", meta={}, entwurf="Entwurf, Stand 15.11.2026", kapitel=[])
    ohne = vorlage.render(title="T", school_name="", meta={}, entwurf=None, kapitel=[])
    assert '<div class="doc-entwurf">Entwurf, Stand 15.11.2026</div>' in mit
    assert 'class="doc-entwurf"' not in ohne


# ── Lesen (0.52, Päckchen AZ: alle Lehrkräfte; hebt E7 auf) ─────────────────

import time

from app.auth import vorschau
from app.auth.jwt import JwtPayload
from app.context.curriculum_entwurf import darf_entwurf_lesen, pruefe_entwurf_lesen


def _wer(*rollen, preview=None):
    return JwtPayload(sub="p", roles=list(rollen), role=rollen[0], grade=None, exp=9999999999,
                      iat=0, jti="j", preview=preview)


@pytest.mark.parametrize("rollen,darf", [
    (("teacher",), True),
    (("teacher", "admin"), True),
    (("admin",), True),
    (("teacher", "fachvorsitz"), True),
    (("student",), False),
    (("review",), False),  # Krisen-Einsicht ohne Lehrkraft-Rolle: kein Curriculum-Material
])
def test_wer_entwuerfe_liest(rollen, darf):
    assert darf_entwurf_lesen(_wer(*rollen)) is darf


def test_vorschau_liest_keine_entwuerfe():
    jetzt = int(time.time())
    wer = _wer("student", preview=vorschau.Vorschau(echte_rollen=["teacher"], beginn=jetzt,
                                                    sitzung_ablauf=jetzt + 3600))
    assert darf_entwurf_lesen(wer) is False
    with pytest.raises(HTTPException) as e:
        pruefe_entwurf_lesen(wer)
    assert e.value.status_code == 404  # verrät den Entwurf nicht
