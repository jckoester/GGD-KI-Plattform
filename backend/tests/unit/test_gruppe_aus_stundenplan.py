"""AP3: Eine Gruppe aus dem Stundenplan anlegen — die Berechtigungsregel.

**Worum es hier geht.** Der Endpunkt legt eine Unterrichtsgruppe an und macht die
aufrufende Person zur Lehrkraft darin. Die einzige Berechtigung dafür ist, dass die
Lerngruppe **im eigenen Stundenplan** als fehlend auftaucht. Würde er dem Client glauben,
könnte jede Lehrkraft jede beliebige Gruppe anlegen und sich hineinschreiben.

Geprüft wird deshalb nicht die Anlage (das tun die Integrationstests), sondern die
**Torwächterfunktion**: Was kommt durch, was nicht.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_any_role
from app.auth.jwt import JwtPayload
from app.calendar.router import router as calendar_router
from app.db.session import get_db

_LEHRKRAFT = JwtPayload(
    sub="lk-pseudo", roles=["teacher"], grade=None,
    jti="jti", iat=1_000_000, exp=9_999_999_999,
)


def _vorschlag(label="CH 9D", subject_id=7, klassen=("9D",)):
    """Ein `GroupSuggestion`, wie der serverseitige Abgleich ihn liefert."""
    return SimpleNamespace(
        key=SimpleNamespace(label=label),
        subject_id=subject_id,
        subject_slug="chemie",
        class_names=klassen,
        vorschlag_name=f"Chemie {klassen[0] if klassen else ''}".strip(),
        codes=("CH",),
        kursart="regulaer",
    )


def _app(monkeypatch, fehlend, anlage=None):
    """Router mit ersetzter Musterlage — der Netzabruf gehört nicht in diesen Test."""
    monkeypatch.setattr("app.calendar.router.is_configured", lambda: True)
    monkeypatch.setattr(
        "app.calendar.router.get_preferences",
        AsyncMock(return_value={"webuntis_kuerzel": "MUE"}),
    )
    monkeypatch.setattr(
        "app.calendar.router._musterlage",
        AsyncMock(return_value=SimpleNamespace(
            result=SimpleNamespace(proposals=[], wochen=[], hinweise=[]),
            abgleich=SimpleNamespace(fehlend=fehlend, vorhanden=[], zuordnung={},
                                     unbekannte_faecher=[], ohne_klasse=[], mehrdeutig=[]),
            halbjahr=1,
            warnungen=[],
        )),
    )
    monkeypatch.setattr(
        "app.calendar.router.lege_gruppe_aus_vorschlag_an",
        AsyncMock(return_value=anlage or SimpleNamespace(
            group_id=42, name="Chemie 9D", subject_id=7,
            quellklassen=("9D",), ohne_treffer=(), kursstufe=False, erbt=True,
        )),
    )
    db = AsyncMock()
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _LEHRKRAFT
    app.dependency_overrides[require_any_role(["teacher", "admin"])] = lambda: _LEHRKRAFT
    from app.auth.dependencies import get_sso_config
    app.dependency_overrides[get_sso_config] = lambda: SimpleNamespace(
        allow_manual_teaching_groups=True
    )
    app.include_router(calendar_router)
    return TestClient(app)


# ── Der Torwächter ───────────────────────────────────────────────────────────


def test_eigene_fehlende_gruppe_wird_angelegt(monkeypatch):
    client = _app(monkeypatch, [_vorschlag()])
    antwort = client.post("/calendar/teaching-groups",
                          json={"gruppe": "CH 9D", "subject_id": 7})
    assert antwort.status_code == 201, antwort.text
    assert antwort.json()["group_id"] == 42


def test_fremde_gruppe_wird_abgewiesen(monkeypatch):
    """⚠️ **Die Gegenprobe zur Berechtigungsregel.**

    Im eigenen Stundenplan steht `CH 9D`. Wer `M 10A` anfordert — eine Lerngruppe, die
    es durchaus geben mag, nur nicht bei dieser Lehrkraft —, bekommt 403. Nimmt der
    Endpunkt statt des serverseitigen Vorschlags die Angaben aus der Anfrage, fällt
    dieser Test.
    """
    client = _app(monkeypatch, [_vorschlag(subject_id=7)])
    # **Gleiches Fach wie der eigene Vorschlag.** Sonst wiese schon die Fachprüfung ab,
    # und der Test bewiese nicht, was er behauptet — genau das war beim ersten Entwurf
    # der Fall (die Gegenprobe kam mit 409 statt 201 zurück).
    antwort = client.post("/calendar/teaching-groups",
                          json={"gruppe": "M 10A", "subject_id": 7})
    assert antwort.status_code == 403
    assert "Stundenplan" in antwort.json()["detail"]


def test_abweichendes_fach_bricht_ab(monkeypatch):
    """Das Fach kommt vom Server; die Anfrage darf es nur **bestätigen**.

    Weicht es ab, hat sich die Lage seit dem Laden der Liste geändert — dann ist
    Abbrechen richtiger als Anlegen, weil sonst eine Gruppe im falschen Fach entstünde.
    """
    client = _app(monkeypatch, [_vorschlag(subject_id=7)])
    antwort = client.post("/calendar/teaching-groups",
                          json={"gruppe": "CH 9D", "subject_id": 99})
    assert antwort.status_code == 409
    assert "Fach" in antwort.json()["detail"]


def test_ohne_kuerzel_kein_anlegen(monkeypatch):
    """Ohne Kürzel gibt es keinen Stundenplan — und damit keine Berechtigungsgrundlage."""
    monkeypatch.setattr("app.calendar.router.is_configured", lambda: True)
    monkeypatch.setattr("app.calendar.router.get_preferences",
                        AsyncMock(return_value={}))
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: _LEHRKRAFT
    app.dependency_overrides[require_any_role(["teacher", "admin"])] = lambda: _LEHRKRAFT
    app.include_router(calendar_router)
    antwort = TestClient(app).post("/calendar/teaching-groups",
                                   json={"gruppe": "CH 9D", "subject_id": 7})
    assert antwort.status_code == 409
    assert "Kürzel" in antwort.json()["detail"]


def test_ohne_stundenplan_anbindung_kein_anlegen(monkeypatch):
    monkeypatch.setattr("app.calendar.router.is_configured", lambda: False)
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: _LEHRKRAFT
    app.dependency_overrides[require_any_role(["teacher", "admin"])] = lambda: _LEHRKRAFT
    app.include_router(calendar_router)
    antwort = TestClient(app).post("/calendar/teaching-groups",
                                   json={"gruppe": "CH 9D", "subject_id": 7})
    assert antwort.status_code == 409


# ── Ganze Klasse oder Teilgruppe? ────────────────────────────────────────────


def test_entscheidung_der_lehrkraft_geht_mit(monkeypatch):
    """Die Wahl „ganze Klasse / Teilgruppe" muss bis zur Anlage durchkommen.

    ⚠️ Sie ist der einzige Weg, den Religion-und-Ethik-Fall zu lösen: Der Stundenplan
    nennt dort **eine** Klasse, die Gruppe ist trotzdem eine Auswahl daraus. Verschluckt
    der Endpunkt das Feld, erbt die Gruppe die ganze Klasse — und niemand merkt es.
    """
    client = _app(monkeypatch, [_vorschlag()])
    antwort = client.post("/calendar/teaching-groups",
                          json={"gruppe": "CH 9D", "subject_id": 7, "erbt": False})
    assert antwort.status_code == 201, antwort.text

    from app.calendar.router import lege_gruppe_aus_vorschlag_an
    # Viertes Argument ist die Entscheidung.
    assert lege_gruppe_aus_vorschlag_an.await_args.args[3] is False


def test_ohne_angabe_entscheidet_die_vorbelegung(monkeypatch):
    """Ohne Feld bleibt die serverseitige Vorbelegung — `None`, nicht `False`."""
    client = _app(monkeypatch, [_vorschlag()])
    antwort = client.post("/calendar/teaching-groups",
                          json={"gruppe": "CH 9D", "subject_id": 7})
    assert antwort.status_code == 201

    from app.calendar.router import lege_gruppe_aus_vorschlag_an
    assert lege_gruppe_aus_vorschlag_an.await_args.args[3] is None


def test_abgeschalteter_schalter_sperrt_auch_diesen_weg(monkeypatch):
    """⚠️ **Der Schalter darf keine Hintertür haben.**

    `allow_manual_teaching_groups=false` heißt „der SSO führt die Unterrichtsgruppen,
    Lehrkräfte legen keine eigenen an". Dieser Weg ist besser belegt als „Klasse ×
    Fach", erzeugt aber dieselbe Art Gruppe — und in einer SSO-geführten Installation
    dieselben Dubletten. Griffe der Schalter hier nicht, wäre er wirkungslos, ohne dass
    es jemand merkt.
    """
    from app.auth.dependencies import get_sso_config

    client = _app(monkeypatch, [_vorschlag()])
    client.app.dependency_overrides[get_sso_config] = lambda: SimpleNamespace(
        allow_manual_teaching_groups=False
    )
    antwort = client.post("/calendar/teaching-groups",
                          json={"gruppe": "CH 9D", "subject_id": 7})
    assert antwort.status_code == 403
    assert "Schulkonto" in antwort.json()["detail"]
