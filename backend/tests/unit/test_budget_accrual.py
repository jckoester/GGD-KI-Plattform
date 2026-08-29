"""Wöchentliche Aufstockung der Budget-Obergrenze.

Zwei Eigenschaften tragen das Modell, und beide sind hier festgehalten:

1. **Der Vorsprung deckelt.** Sonst wäre das Wochenmodell ein Ansparkonto, und ein Kind
   könnte ein halbes Schuljahr an einem Nachmittag in Bilder umsetzen.
2. **Der Lauf ist idempotent.** Bei ~40 Läufen im Schuljahr fällt ein doppelter oder
   ausgefallener Lauf nicht auf — er darf deshalb nichts kaputt machen.
"""
import os
from datetime import date

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.budget.accrual import berechne

WOCHE = 1.00  # USD je Unterrichtswoche, glatt gewählt für lesbare Erwartungen
VORSPRUNG = 3


def _berechne(grenze, verbrauch, wochen=1, vorsprung=VORSPRUNG):
    return berechne(
        wochenbetrag_usd=WOCHE,
        aktuelle_grenze_usd=grenze,
        verbrauch_usd=verbrauch,
        fehlende_wochen=wochen,
        vorsprung=vorsprung,
    )


# ── Normalfall ──────────────────────────────────────────────────────────────────────


def test_grenze_waechst_um_den_wochenbetrag():
    """Wer fleißig verbraucht, bekommt jede Woche einen Wochenbetrag dazu."""
    assert _berechne(grenze=5.0, verbrauch=4.5) == 6.0


def test_erstzuteilung_ohne_bestehende_grenze():
    assert _berechne(grenze=None, verbrauch=0.0) == 1.0


# ── Der Vorsprung ───────────────────────────────────────────────────────────────────


def test_vorsprung_deckelt_die_ansammlung():
    """Am Deckel angekommen, wächst die Grenze nicht weiter.

    Wer nichts verbraucht, steht bei drei Wochenbeträgen — die vierte Woche legt nichts
    mehr drauf.
    """
    assert _berechne(grenze=3.0, verbrauch=0.0) == 3.0


def test_deckel_richtet_sich_nach_dem_verbrauch_nicht_nach_der_zeit():
    """Wer viel verbraucht hat, darf entsprechend weiter vorauseilen."""
    assert _berechne(grenze=20.0, verbrauch=18.0) == 21.0


def test_nachholen_ist_ebenfalls_gedeckelt():
    """Ein ausgefallener Cron ist kein Freibrief.

    Sechs versäumte Wochen auf einmal ergeben trotzdem nur den Vorsprung — sonst könnte
    ein Betriebsfehler das Tempolimit aushebeln, das die Rücksetzung ersetzt hat.
    """
    assert _berechne(grenze=2.0, verbrauch=1.0, wochen=6) == 4.0


def test_grenze_wird_nie_gekuerzt():
    """Der Deckel bremst, er nimmt nicht weg.

    Durch Aufstocken allein kann die Grenze nie über den Deckel steigen. Sehr wohl aber
    von außen: wenn die Administration ein Budget anhebt oder eine Stufe in
    `budget_tiers.yaml` gesenkt wird. Dann darf der nächste Lauf das bereits zugesagte
    Guthaben nicht wieder einziehen — für die Nutzerin wäre das ein unerklärlich
    verschwundener Betrag.
    """
    assert _berechne(grenze=9.0, verbrauch=0.0) == 9.0


def test_vorsprung_eins_erlaubt_genau_eine_woche():
    assert _berechne(grenze=5.0, verbrauch=2.0, vorsprung=1) == 5.0
    assert _berechne(grenze=2.0, verbrauch=2.0, vorsprung=1) == 3.0


# ── Jahressumme ─────────────────────────────────────────────────────────────────────


def test_jahressumme_bleibt_unter_der_zusage():
    """Die harte Zusage: Betrag × Wochen wird nie überschritten.

    Simuliert ein Schuljahr mit 40 Wochen und einer Nutzerin, die jede Woche alles
    ausgibt — der Fall mit der höchsten Grenze.
    """
    grenze, verbrauch = 0.0, 0.0
    for _ in range(40):
        grenze = _berechne(grenze=grenze, verbrauch=verbrauch)
        verbrauch = grenze  # verbraucht sofort alles
    assert grenze == pytest.approx(40 * WOCHE)


def test_wer_nichts_nutzt_sammelt_nichts_an():
    grenze = 0.0
    for _ in range(40):
        grenze = _berechne(grenze=grenze, verbrauch=0.0)
    assert grenze == VORSPRUNG * WOCHE


# ── Planung gegen den Merkposten ────────────────────────────────────────────────────


class _FakeDb:
    """Minimaler Ersatz für `AsyncSession.get` / `add` — kein Postgres nötig."""

    def __init__(self, stand=None):
        self.stand = stand
        self.hinzugefuegt = []

    async def get(self, _modell, _pk):
        return self.stand

    def add(self, obj):
        self.hinzugefuegt.append(obj)


def _schuljahr():
    from app.planning.calendar import SchoolYearConfig

    return SchoolYearConfig(
        schuljahr="2026/27",
        beginn=date(2026, 9, 14),
        ende=date(2026, 10, 16),
        halbjahreswechsel=date(2026, 10, 1),
        ferien=[],
        feiertage=[],
        unterrichtsfreie_tage=[],
    )


@pytest.mark.asyncio
async def test_zweiter_lauf_derselben_woche_bucht_nicht():
    """Die Idempotenz — bei ~40 Läufen im Jahr die wichtigste Eigenschaft."""
    from app.budget.accrual import plane
    from app.db.models import BudgetAccrual

    stand = BudgetAccrual(pseudonym="p", schuljahr="2026/27", letzte_woche=2)
    zuteilung = await plane(
        _FakeDb(stand), "p",
        wochenbetrag_usd=1.0, aktuelle_grenze_usd=5.0, verbrauch_usd=4.0,
        stichtag=date(2026, 9, 22),   # Dienstag der 2. Woche
        cfg=_schuljahr(),
    )

    assert not zuteilung.zu_tun
    assert "bereits gebucht" in zuteilung.grund


@pytest.mark.asyncio
async def test_in_ferien_wird_nichts_gebucht():
    from app.budget.accrual import plane

    cfg = _schuljahr()
    cfg = cfg.model_copy(update={"ferien": [
        type(cfg).model_fields["ferien"].annotation.__args__[0](
            name="Herbst", von=date(2026, 9, 21), bis=date(2026, 9, 25)
        )
    ]})
    zuteilung = await plane(
        _FakeDb(), "p",
        wochenbetrag_usd=1.0, aktuelle_grenze_usd=5.0, verbrauch_usd=0.0,
        stichtag=date(2026, 9, 23),
        cfg=cfg,
    )

    assert not zuteilung.zu_tun
    assert "Unterrichtswoche" in zuteilung.grund


@pytest.mark.asyncio
async def test_neue_nutzerin_bekommt_nur_die_laufende_woche():
    """Wer im März dazukommt, hat nicht seit September Anspruch."""
    from app.budget.accrual import plane

    zuteilung = await plane(
        _FakeDb(), "neu",
        wochenbetrag_usd=1.0, aktuelle_grenze_usd=None, verbrauch_usd=0.0,
        stichtag=date(2026, 10, 13),   # 5. Woche
        cfg=_schuljahr(),
    )

    assert zuteilung.gebuchte_wochen == 1, "kein rückwirkendes Nachholen ab Woche 1"
    assert zuteilung.neue_grenze_usd == 1.0
    assert zuteilung.bis_woche == 5


@pytest.mark.asyncio
async def test_ausgefallene_laeufe_werden_nachgeholt():
    from app.budget.accrual import plane
    from app.db.models import BudgetAccrual

    stand = BudgetAccrual(pseudonym="p", schuljahr="2026/27", letzte_woche=1)
    zuteilung = await plane(
        _FakeDb(stand), "p",
        wochenbetrag_usd=1.0, aktuelle_grenze_usd=1.0, verbrauch_usd=1.0,
        stichtag=date(2026, 10, 13),   # 5. Woche → 2,3,4,5 offen
        cfg=_schuljahr(),
    )

    assert zuteilung.gebuchte_wochen == 4
    assert zuteilung.bis_woche == 5


@pytest.mark.asyncio
async def test_neues_schuljahr_beginnt_die_zaehlung_neu():
    """Der Jahreswechsel braucht keinen eigenen Rücksetzlauf."""
    from app.budget.accrual import plane
    from app.db.models import BudgetAccrual

    alt = BudgetAccrual(pseudonym="p", schuljahr="2025/26", letzte_woche=38)
    zuteilung = await plane(
        _FakeDb(alt), "p",
        wochenbetrag_usd=1.0, aktuelle_grenze_usd=40.0, verbrauch_usd=39.0,
        stichtag=date(2026, 9, 15),
        cfg=_schuljahr(),
    )

    assert zuteilung.gebuchte_wochen == 1
    assert zuteilung.bis_woche == 1


@pytest.mark.asyncio
async def test_ohne_wochenbetrag_passiert_nichts():
    from app.budget.accrual import plane

    zuteilung = await plane(
        _FakeDb(), "p",
        wochenbetrag_usd=None, aktuelle_grenze_usd=5.0, verbrauch_usd=0.0,
        stichtag=date(2026, 9, 15), cfg=_schuljahr(),
    )

    assert not zuteilung.zu_tun


# ── Der Lauf selbst ─────────────────────────────────────────────────────────────────


def _mock_session(users):
    """`async with AsyncSessionLocal() as db` für den Skript-Lauf."""
    from unittest.mock import AsyncMock, MagicMock

    scalars = MagicMock()
    scalars.all = MagicMock(return_value=users)
    ergebnis = MagicMock()
    ergebnis.scalars = MagicMock(return_value=scalars)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=ergebnis)
    db.get = AsyncMock(return_value=None)   # niemand hat einen Merkposten
    db.add = MagicMock()
    db.commit = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, db


def _nutzer(pseudonym, grade=7):
    from unittest.mock import MagicMock

    u = MagicMock()
    u.pseudonym, u.role, u.grade, u.roles = pseudonym, "student", grade, ["student"]
    return u


@pytest.mark.asyncio
async def test_fehler_bei_einer_nutzerin_stoppt_den_lauf_nicht():
    """825 Nutzer, ~40 Läufe: Ein Ausfall darf die übrigen nicht mitreißen.

    Und wichtiger: Für die gescheiterte Nutzerin darf der Merkposten **nicht**
    fortgeschrieben werden — sonst gilt die Woche als gebucht, obwohl die Grenze
    unverändert blieb, und niemand holt sie je nach.
    """
    from unittest.mock import AsyncMock, patch

    from scripts.weekly_budget_accrual import run

    cm, db = _mock_session([_nutzer("p1"), _nutzer("p2")])
    client = AsyncMock()
    client.close = AsyncMock()
    client.get_user = AsyncMock(return_value={"max_budget": 1.0, "spend": 0.5})
    client.update_user_budget = AsyncMock(
        side_effect=[RuntimeError("Proxy weg"), None]
    )

    with patch("scripts.weekly_budget_accrual.AsyncSessionLocal", return_value=cm), \
         patch("scripts.weekly_budget_accrual.get_current_rate", new=AsyncMock(return_value=1.1)), \
         patch("scripts.weekly_budget_accrual.get_budget_for", return_value=0.05), \
         patch("scripts.weekly_budget_accrual.load_school_year", return_value=_schuljahr()), \
         patch("scripts.weekly_budget_accrual.LiteLLMClient", return_value=client):
        await run(dry_run=False, stichtag=date(2026, 9, 15), pseudonym_filter=None)

    assert client.update_user_budget.await_count == 2, "p2 wurde trotz Fehler bei p1 bedient"
    assert len(db.add.call_args_list) == 1, "nur für die erfolgreiche Nutzerin gemerkt"
    assert db.add.call_args_list[0].args[0].pseudonym == "p2"
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_dry_run_schreibt_nichts():
    from unittest.mock import AsyncMock, patch

    from scripts.weekly_budget_accrual import run

    cm, db = _mock_session([_nutzer("p1")])
    client = AsyncMock()
    client.close = AsyncMock()
    client.get_user = AsyncMock(return_value={"max_budget": 1.0, "spend": 0.5})
    client.update_user_budget = AsyncMock()

    with patch("scripts.weekly_budget_accrual.AsyncSessionLocal", return_value=cm), \
         patch("scripts.weekly_budget_accrual.get_current_rate", new=AsyncMock(return_value=1.1)), \
         patch("scripts.weekly_budget_accrual.get_budget_for", return_value=0.05), \
         patch("scripts.weekly_budget_accrual.load_school_year", return_value=_schuljahr()), \
         patch("scripts.weekly_budget_accrual.LiteLLMClient", return_value=client):
        await run(dry_run=True, stichtag=date(2026, 9, 15), pseudonym_filter=None)

    client.update_user_budget.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert not db.add.call_args_list
