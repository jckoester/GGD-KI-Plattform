"""Ist gegen Soll auf `/budget` — gegen die echte Datenbank (0.12, Paket 2, AP2).

Die Rechnung steht in `test_budget_forecast.py`. Hier die eine Zusage, die an der
Datenbank hängt: **Der letzte Punkt der Ist-Linie ist die Zahl „bisher verbraucht".**
Beide entstehen aus derselben Abfrage (`_wochenverbrauch`) — sonst stünde neben dem
Diagramm eine Zahl, die seinem Endpunkt widerspricht.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.api.admin.budgets import GradeInfo, _hochrechnung, _wochenverbrauch
from app.db.models import Conversation, Message
from app.planning.calendar import load_school_year

pytestmark = pytest.mark.asyncio


async def _nachricht(db, wann: datetime, kosten: float):
    conv = Conversation(pseudonym="verlauf-p", model_used="chat-standard")
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, role="assistant", content="…",
                   cost_usd=kosten, created_at=wann))
    await db.flush()


def _im_schuljahr(cfg, tage: int) -> datetime:
    d = cfg.beginn + timedelta(days=tage)
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)


async def test_letzter_ist_punkt_ist_der_bisherige_verbrauch(db_session):
    cfg = load_school_year()
    if not (cfg.beginn <= date.today() <= cfg.ende):
        pytest.skip("Das konfigurierte Schuljahr umfasst heute nicht")
    await _nachricht(db_session, _im_schuljahr(cfg, 1), 0.40)
    await _nachricht(db_session, _im_schuljahr(cfg, 8), 0.30)

    zeilen = [GradeInfo(key="jahrgang-9", grade=9, label="Klasse 9",
                        max_budget_eur=0.06, user_count=10)]
    hochrechnung, verlauf = await _hochrechnung(db_session, zeilen, 30, 1.0)

    vergangene = [p for p in verlauf if p.ist_eur is not None]
    assert vergangene, "Testaufbau: es muss vergangene Wochen geben"
    assert vergangene[-1].ist_eur == pytest.approx(hochrechnung.verbraucht_eur, abs=0.01)


async def test_woche_wird_am_montag_ortszeit_gezaehlt(db_session):
    """Montag 01:00 Ortszeit ist Sonntag 23:00 UTC — ohne Ortszeit landete eine
    Montagsnachricht in der Vorwoche.

    ⚠️ **Die Sitzung wird auf UTC festgenagelt.** `DATE_TRUNC` auf `timestamptz` rechnet
    in der Zeitzone der Datenbanksitzung, und die steht im Dev-System auf
    `Europe/Berlin`. Ohne diese Zeile bestand der Test auch dann, wenn die Ortszeit im
    Code fehlte (Gegenprobe vom 02.10.2026) — auf einem Produktionsserver im Container,
    der meist in UTC läuft, wäre der Fehler aber da gewesen.
    """
    from sqlalchemy import text

    await db_session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    cfg = load_school_year()
    # Ein Montag im Schuljahr
    tag = cfg.beginn + timedelta(days=(7 - cfg.beginn.weekday()) % 7 + 7)
    montag_frueh_utc = datetime(tag.year, tag.month, tag.day, tzinfo=timezone.utc) - timedelta(hours=1)
    await _nachricht(db_session, montag_frueh_utc, 0.25)  # 00:00 Ortszeit (Sommerzeit: 01:00)
    je_woche = await _wochenverbrauch(db_session, cfg.beginn, 1.0)
    assert je_woche.get(tag, 0.0) >= 0.25, "die Nachricht gehört in die Woche ab Montag"


async def test_vor_dem_schuljahr_zaehlt_nicht(db_session):
    cfg = load_school_year()
    vorher = datetime.combine(cfg.beginn - timedelta(days=20), datetime.min.time(),
                              tzinfo=timezone.utc)
    await _nachricht(db_session, vorher, 9.99)
    je_woche = await _wochenverbrauch(db_session, cfg.beginn, 1.0)
    assert all(m >= cfg.beginn - timedelta(days=6) for m in je_woche)
    assert 9.99 not in je_woche.values()
