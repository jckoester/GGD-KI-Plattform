"""`GET /calendar/school-year` — die Oberfläche soll das Schuljahr nicht selbst rechnen.

Der Knopf „Schuljahresende" im Baustein-Formular leitete das Datum bis 04.09.2026 aus dem
eingetippten Schuljahr ab und nahm dafür **fest den 31.07.** an. In der Config steht der
29.07.2026 bzw. der 28.07.2027. Zwei Tage daneben fällt niemandem auf — deshalb blieb es
stehen.

Der eigentliche Punkt ist der Gleichlauf: Dasselbe Datum trägt der Server ein, wenn beim
Anlegen kein Ablaufdatum angegeben wird (`_ablaufdatum_vorbelegen`). Der letzte Test hier
hält genau das fest.
"""
import os
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.calendar.router import router as calendar_router


def _payload(*rollen: str) -> JwtPayload:
    return JwtPayload(
        sub="pseudo-1", roles=list(rollen), grade=None, jti="jti-1", iat=1,
        exp=9999999999,
    )


def _client(nutzer: JwtPayload) -> TestClient:
    app = FastAPI()
    app.include_router(calendar_router)

    async def fake_current_user():
        return nutzer

    app.dependency_overrides[get_current_user] = fake_current_user
    return TestClient(app)


def test_liefert_die_vier_eckdaten():
    antwort = _client(_payload("teacher")).get("/calendar/school-year")
    assert antwort.status_code == 200
    daten = antwort.json()
    assert set(daten) == {"schuljahr", "beginn", "ende", "halbjahreswechsel"}
    # ISO-Strings, keine Datumsobjekte — das Frontend bekommt JSON.
    for feld in ("beginn", "ende", "halbjahreswechsel"):
        date.fromisoformat(daten[feld])


def test_ende_liegt_hinter_dem_beginn():
    daten = _client(_payload("teacher")).get("/calendar/school-year").json()
    assert date.fromisoformat(daten["beginn"]) < date.fromisoformat(daten["ende"])


def test_admin_darf_auch():
    assert _client(_payload("admin")).get("/calendar/school-year").status_code == 200


def test_schueler_nicht():
    """Denselben Schutz wie das Anlegen von Bausteinen (`_TEACHER_OR_ADMIN`)."""
    assert _client(_payload("student")).get("/calendar/school-year").status_code == 403


def test_gleichlauf_mit_der_automatik():
    """Knopf und automatische Vorbelegung müssen dasselbe Datum nennen.

    Sonst wirkt eines von beidem falsch: Man drückt den Knopf, bekommt den 31.07., und
    der Server hätte den 29.07. eingetragen.
    """
    from app.context.ablauf import vorgeschlagenes_ablaufdatum
    from app.planning.calendar import load_school_year

    daten = _client(_payload("teacher")).get("/calendar/school-year").json()
    ende = date.fromisoformat(daten["ende"])

    automatik = vorgeschlagenes_ablaufdatum("unterrichtsstunde")
    if load_school_year().ende <= date.today():
        # Abgelaufene Config: Die Automatik setzt bewusst nichts (sonst archivierte der
        # nächtliche Lauf sofort wieder). Der Endpunkt meldet den Stand trotzdem.
        assert automatik is None
    else:
        assert automatik == ende
