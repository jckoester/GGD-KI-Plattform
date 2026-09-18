"""Unit tests für GET /groups und GET /groups/me."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.groups import router as groups_router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db


_FAKE_USER = JwtPayload(
    sub="test-pseudo", roles=["student"], grade="8",
    jti="jti", iat=1_000_000, exp=9_999_999_999,
)

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_group(**kwargs):
    """Ein **echtes** Group-Objekt.

    Früher ein `MagicMock`. Der liefert für jedes Attribut etwas — auch für solche, die es
    am Modell gar nicht gibt. Ein neues Antwortfeld (`display_name`, `anzeigename`) fiel
    damit erst auf, als Pydantic sich an einem Mock verschluckte; ein fehlendes Feld wäre
    stillschweigend durchgegangen.

    Die Vorgaben bilden eine **gespeicherte** Zeile nach. `student_visible` gehört dazu:
    Python-seitige Spaltenvorgaben greifen erst beim `flush()` — davor steht `None` am
    Objekt, was kein `bool` ist. Produktiv tritt das nicht auf (nachgemessen: `db.add` +
    `flush` ⇒ `False`), am unverankerten Objekt im Test aber schon.
    """
    from app.db.models import Group

    defaults = dict(id=1, name="Testgruppe", slug="testgruppe",
                    type="teaching_group", subject_id=None,
                    sso_group_id=None, source_class_group_id=None,
                    display_name=None, student_visible=False, created_at=_TS)
    defaults.update(kwargs)
    return Group(**defaults)


def _make_db_mock(items: list) -> MagicMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=lambda: items)
    db = MagicMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_app(db_mock, user=None) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: (user or _FAKE_USER)
    app.include_router(groups_router)
    return app


# ── GET /groups ───────────────────────────────────────────────────────────────

def test_get_groups_empty():
    client = TestClient(_make_app(_make_db_mock([])))
    resp = client.get("/groups")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_get_groups_returns_items_in_db_order():
    g1 = _make_group(id=1, slug="activity-gruppe", type="activity_group")
    g2 = _make_group(id=2, slug="lerngruppe", type="teaching_group")
    client = TestClient(_make_app(_make_db_mock([g1, g2])))

    items = client.get("/groups").json()["items"]
    assert len(items) == 2
    assert items[0]["type"] == "activity_group"
    assert items[1]["type"] == "teaching_group"


def test_get_groups_all_fields_present():
    client = TestClient(_make_app(_make_db_mock([_make_group(subject_id=5, sso_group_id="sso-1")])))
    item = client.get("/groups").json()["items"][0]
    for field in ("id", "name", "slug", "type", "subject_id", "sso_group_id", "created_at"):
        assert field in item, f"Feld '{field}' fehlt"
    assert item["subject_id"] == 5
    assert item["sso_group_id"] == "sso-1"


def test_get_groups_nullable_fields():
    client = TestClient(_make_app(_make_db_mock([_make_group()])))
    item = client.get("/groups").json()["items"][0]
    assert item["subject_id"] is None
    assert item["sso_group_id"] is None


# ── GET /groups/me ────────────────────────────────────────────────────────────

def test_get_groups_me_empty():
    client = TestClient(_make_app(_make_db_mock([])))
    resp = client.get("/groups/me")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_get_groups_me_returns_user_groups():
    g = _make_group(id=1, name="Meine Gruppe")
    client = TestClient(_make_app(_make_db_mock([g])))
    items = client.get("/groups/me").json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Meine Gruppe"


# ── Aktuelle und frühere Gruppen (AP8 Schritt 1) ─────────────────────────────

from datetime import date  # noqa: E402

from app.api.groups import GroupOut, MyGroupOut, ist_aktuell  # noqa: E402
from app.db.models import Group  # noqa: E402
from app.planning.calendar import SchoolYearConfig  # noqa: E402

JAHR = SchoolYearConfig(
    schuljahr="2026/27",
    beginn=date(2026, 9, 14),
    ende=date(2027, 7, 28),
    halbjahreswechsel=date(2027, 2, 8),
)


def _gruppe(**kwargs):
    """Ein **echtes** Group-Objekt, kein Mock — siehe `test_antwort_baut_sich_aus_echtem_modell`."""
    daten = dict(
        id=1, name="Mathematik 9C", slug="m-9c", type="teaching_group",
        subject_id=None, sso_group_id=None, source_class_group_id=None,
        # Wie eine gespeicherte Zeile: Spaltenvorgaben greifen erst beim `flush()`.
        student_visible=False,
        created_at=datetime(2025, 9, 20, tzinfo=timezone.utc),   # letztes Schuljahr
    )
    daten.update(kwargs)
    return Group(**daten)


def test_gruppe_aus_dem_schulkonto_bleibt_ohne_jeden_beleg_aktuell():
    """Der Wächter über die Entscheidung aus §6a des Gruppenübersicht-Plans.

    Für eine Gruppe mit `sso_group_id` ist die Mitgliedschaft schon die Antwort: Der
    Immediate Mirror entfernt beim Login, was das Token nicht mehr deckt. Das trägt den
    **Kursstufenkurs über zwei Schuljahre**, der am ersten Schultag weder Stunden noch
    Jahresplan im neuen Jahr hat — und auch keine bekommen kann, solange der Stundenplan
    nicht veröffentlicht ist.
    """
    kurs = _gruppe(sso_group_id="unterricht.ch2-ks-abi28")
    assert ist_aktuell(kurs, set(), JAHR) is True


def test_klassen_und_fachschaften_werden_nicht_beurteilt():
    for typ in ("school_class", "subject_department", "activity_group", "teachers"):
        assert ist_aktuell(_gruppe(type=typ), set(), JAHR) is True


def test_gruppe_mit_stunden_oder_planung_im_laufenden_jahr_ist_aktuell():
    assert ist_aktuell(_gruppe(id=7), {7}, JAHR) is True


def test_adoptierte_gruppe_ohne_beleg_ist_frueher():
    """Der eigentliche Fall: letztes Schuljahr angelegt, dieses Jahr nichts passiert."""
    assert ist_aktuell(_gruppe(), set(), JAHR) is False


def test_frisch_angelegte_gruppe_ist_aktuell():
    """Sie hat noch nichts, woran man sie erkennen könnte — ohne diese Regel wäre jede
    neue Gruppe im Moment ihrer Entstehung „früher"."""
    neu = _gruppe(created_at=datetime(2026, 9, 15, tzinfo=timezone.utc))
    assert ist_aktuell(neu, set(), JAHR) is True


def _wie_aus_der_datenbank(*teile) -> datetime:
    """Ein **lokaler** Zeitpunkt, so wie ihn die Datenbank zurückgibt: in UTC.

    Genau darauf kommt es an. Ein aware Zeitstempel mit lokalem Versatz beantwortet
    `.date()` schon richtig — der Fehler zeigt sich erst, wenn der Wert in einer anderen
    Zeitzone ankommt, und asyncpg liefert `timestamptz` grundsätzlich in UTC. Ein Test mit
    lokalem Versatz ginge deshalb auch ohne die Umrechnung durch und wäre wertlos.
    """
    return datetime(*teile).astimezone().astimezone(timezone.utc)


def test_der_erste_schultag_zaehlt_nach_dem_kalender_der_schule():
    """Grenzfall — und der Wächter über die Zeitzonen-Umrechnung.

    Der Zeitstempel kommt in der Zeitzone der Datenbanksitzung zurück, der
    Schuljahresbeginn ist ein Kalendertag der Schule. Ohne `astimezone()` entschiede die
    Zeitzone über die Jahresgrenze: Mitternacht am ersten Schultag ist in UTC noch der
    Vortag, und die Gruppe gälte als im Vorjahr angelegt.

    Deshalb stehen hier **lokale** Zeitpunkte, keine UTC-Werte — sonst prüfte der Test je
    nach Rechner etwas anderes.
    """
    erster = _wie_aus_der_datenbank(2026, 9, 14, 0, 0)
    davor = _wie_aus_der_datenbank(2026, 9, 13, 23, 0)
    assert ist_aktuell(_gruppe(created_at=erster), set(), JAHR) is True
    assert ist_aktuell(_gruppe(created_at=davor), set(), JAHR) is False


def test_antwort_baut_sich_aus_echtem_modell():
    """`MyGroupOut.model_validate(gruppe)` schlägt fehl — `aktuell` gibt es am ORM-Modell
    nicht, und die Validierung verlangt es.

    Die Router-Tests oben arbeiten mit `MagicMock`; dort liefert jeder Attributzugriff
    etwas, und der Fehler bliebe unsichtbar. Genau so ist er beim Bauen am 15.09.2026
    durchgerutscht.
    """
    gruppe = _gruppe()
    ausgabe = MyGroupOut(
        **GroupOut.model_validate(gruppe, from_attributes=True).model_dump(),
        aktuell=False,
    )
    assert ausgabe.aktuell is False
    assert ausgabe.name == "Mathematik 9C"

    with pytest.raises(ValidationError):
        MyGroupOut.model_validate(gruppe, from_attributes=True)


# ── GET /groups/config ────────────────────────────────────────────────────────
# Der Endpunkt reicht Schalter an die Oberfläche durch. Für `student_subjects_opt_in`
# (begrenzter Testbetrieb, Alembic 0063) hängt daran zweierlei: ob der Freigabe-Schalter
# bei den Unterrichtsgruppen überhaupt erscheint, und ob der Schülerzweig filtert. Meldet
# er falsch, ist entweder ein wirkungsloser Schalter zu sehen oder die Freigabe wirkungslos.

def _config_app(*, opt_in: bool, manuelle_gruppen: bool = True) -> FastAPI:
    from app.api import groups as groups_module
    from app.auth.config import SsoConfig
    from app.auth.dependencies import get_sso_config

    app = _make_app(_make_db_mock([]))
    app.dependency_overrides[get_sso_config] = lambda: SsoConfig(
        allow_manual_teaching_groups=manuelle_gruppen
    )
    groups_module.settings.student_subjects_opt_in = opt_in
    return app


@pytest.fixture(autouse=True)
def _schalter_zuruecksetzen():
    """Der Schalter ist ein Prozess-Zustand — sonst färbt ein Test auf den nächsten ab."""
    from app.api import groups as groups_module

    vorher = groups_module.settings.student_subjects_opt_in
    yield
    groups_module.settings.student_subjects_opt_in = vorher


@pytest.mark.parametrize("opt_in", [True, False])
def test_config_meldet_den_testbetriebs_schalter(opt_in):
    client = TestClient(_config_app(opt_in=opt_in))
    resp = client.get("/groups/config")
    assert resp.status_code == 200
    assert resp.json()["student_subjects_opt_in"] is opt_in


def test_config_meldet_weiterhin_manuelle_gruppen():
    """Der neue Schalter tritt neben den vorhandenen, er ersetzt ihn nicht."""
    client = TestClient(_config_app(opt_in=True, manuelle_gruppen=False))
    daten = client.get("/groups/config").json()
    assert daten["allow_manual_teaching_groups"] is False
    assert daten["student_subjects_opt_in"] is True
