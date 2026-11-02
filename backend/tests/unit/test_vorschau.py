"""Vorschau-Helfer (0.29, Schritt 1, ADR-016 Ansatz C)."""
import time

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.auth import vorschau
from app.auth.jwt import JwtPayload, JwtService
from app.auth.vorschau import Vorschau


def _sql(bedingung) -> str:
    return str(bedingung.compile(dialect=postgresql.dialect(),
                                 compile_kwargs={"literal_binds": True}))


def _jwt(pseudonym="lk", *, gruppe=None, assistent=None, vorschau_an=True) -> JwtPayload:
    merkmal = Vorschau(echte_rollen=["teacher"], gruppe_id=gruppe, assistent_id=assistent,
                       beginn=0, sitzung_ablauf=2**31) if vorschau_an else None
    return JwtPayload(sub=pseudonym, roles=["student"] if vorschau_an else ["teacher"],
                      grade="9" if vorschau_an else None, jti="j", iat=0, exp=2**31,
                      preview=merkmal)


def test_ohne_vorschau_bleibt_alles_wie_es_war():
    vorschau.fuer_anfrage(_jwt(vorschau_an=False))
    assert _sql(vorschau.mitglied("lk")) == "group_memberships.pseudonym = 'lk'"
    assert "role_in_group = 'teacher'" in _sql(vorschau.mitglied("lk", "teacher"))
    assert vorschau.eigenes_zaehlt("lk")
    assert vorschau.rolle_in_gruppe("lk", "teacher") == "teacher"
    assert vorschau.eintrittsassistent("lk") is None


def test_vorschau_mit_gruppe_ist_schuelerin_dieser_gruppe():
    vorschau.fuer_anfrage(_jwt(gruppe=7, assistent=3))
    sql = _sql(vorschau.mitglied("lk"))
    assert "group_memberships.group_id = 7" in sql
    assert _sql(vorschau.mitglied("lk", "student")) == sql
    assert _sql(vorschau.mitglied("lk", "teacher")) == "false"
    assert vorschau.rolle_in_gruppe("lk", "teacher") == "student"
    assert not vorschau.eigenes_zaehlt("lk")
    assert vorschau.eintrittsassistent("lk") == 3


def test_vorschau_ohne_gruppe_hat_keine_mitgliedschaften():
    vorschau.fuer_anfrage(_jwt(gruppe=None))
    assert _sql(vorschau.mitglied("lk")) == "false"


def test_die_vorschau_gilt_nur_fuer_ihr_pseudonym():
    """Fragt dieselbe Anfrage nach einer anderen Person (etwa Mitglieder einer Gruppe),
    bleibt deren Antwort echt."""
    vorschau.fuer_anfrage(_jwt("lk", gruppe=7))
    assert _sql(vorschau.mitglied("jemand")) == "group_memberships.pseudonym = 'jemand'"
    assert vorschau.eigenes_zaehlt("jemand")


def test_die_naechste_anfrage_setzt_zurueck():
    vorschau.fuer_anfrage(_jwt("lk", gruppe=7))
    vorschau.fuer_anfrage(_jwt("lk", vorschau_an=False))
    assert vorschau.aktive("lk") is None


def test_token_traegt_das_merkmal_und_den_festen_ablauf():
    dienst = JwtService(secret="x" * 32)
    ablauf = int(time.time()) + 3600
    merkmal = Vorschau(echte_rollen=["teacher", "admin"], echter_jahrgang=None, gruppe_id=4,
                       beginn=int(time.time()), sitzung_ablauf=ablauf + 99)
    token, _ = dienst.issue("lk", ["student"], "9", preview=merkmal, exp=ablauf)
    payload = dienst.verify(token)
    assert payload.roles == ["student"] and payload.grade == "9"
    assert payload.preview == merkmal
    assert payload.exp == ablauf
    assert vorschau.ist_vorschau(payload)


def test_normale_sitzung_hat_kein_merkmal():
    dienst = JwtService(secret="x" * 32)
    token, _ = dienst.issue("lk", ["teacher"], None)
    assert dienst.verify(token).preview is None


async def test_budget_in_der_vorschau_mit_echten_rollen(monkeypatch):
    """Bezahlt wird aus dem Konto der Lehrkraft — ihr Wochenbetrag gilt, nicht der einer
    Schüler:in (sonst stand „+600 Einheiten am Mo." neben dem Kontostand der Lehrkraft)."""
    from app.budget import router as budget_router

    gesehen = {}

    async def fake(db, pseudonym, *, roles, grade):
        gesehen.update(roles=roles, grade=grade)
        return {}

    monkeypatch.setattr(budget_router, "get_budget_info", fake)
    user = JwtPayload(sub="lk", roles=["student"], grade="9", jti="j", iat=0, exp=2**31,
                      preview=Vorschau(echte_rollen=["teacher", "admin"], echter_jahrgang=None,
                                       beginn=0, sitzung_ablauf=2**31))
    await budget_router.read_my_budget(current_user=user, db=None)
    assert gesehen == {"roles": ["teacher", "admin"], "grade": None}
