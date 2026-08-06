"""Ferienkalender-Import (UP-8, Schritt 4).

Liest Ferien und Schuljahresgrenzen aus der Stundenplanquelle und schreibt daraus
`config/school_year.yaml`. Zwei Felder bleiben dabei unangetastet, weil die Quelle sie
nicht kennt: `halbjahreswechsel` (eine Schulentscheidung) und die Schreibweise von
`schuljahr` (wird von `parse_schuljahr_start` gelesen).
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import require_role
from app.auth.jwt import JwtPayload
from app.calendar.base import CalendarSourceError, NoActiveSchoolYearError
from app.calendar.holidays import (
    build_proposal,
    render_school_year,
    to_yaml_block,
    write_school_year,
)
from app.calendar.service import get_adapter, is_configured
from app.planning.calendar import _DEFAULT_PATH, SchoolYearConfig, load_school_year

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/holidays", tags=["admin-holidays"])


class ApplyRequest(BaseModel):
    """Was übernommen werden soll.

    `bounds_uebernehmen` getrennt schaltbar, weil geänderte Schuljahresgrenzen den
    Halbjahreswechsel ungültig machen können — dann muss erst der gesetzt werden.
    """

    bounds_uebernehmen: bool = True
    # Ohne Angabe das Schuljahr der bestehenden Konfiguration.
    schuljahr: str | None = None


def _waehle_jahr(years: list, cfg: SchoolYearConfig, gewuenscht: str | None):
    """Welches Schuljahr importiert wird.

    Ohne Angabe **das der bestehenden Konfiguration** — wer den Kalender mitten im Jahr
    abruft, soll nicht versehentlich auf das kommende umgestellt werden.

    Das allein genügt aber nicht: Zum Schuljahreswechsel wäre es ein Zirkelschluss. Solange
    die Datei 2025/26 sagt, käme der Import nie ins neue Jahr — und `beginn` müsste von
    Hand eingetragen werden, obwohl die Quelle ihn kennt. Deshalb ist das Jahr **wählbar**.
    """
    if gewuenscht:
        treffer = next((y for y in years if y.name == gewuenscht), None)
        if treffer is None:
            raise HTTPException(
                status_code=404,
                detail=f"Die Quelle kennt kein Schuljahr '{gewuenscht}'. "
                       f"Bekannt: {', '.join(y.name for y in years) or '—'}.",
            )
        return treffer
    return next(
        (y for y in years if y.start <= cfg.beginn <= y.end), None
    ) or next((y for y in years if y.contains(date.today())), None)


async def _hole_vorschlag(
    schuljahr: str | None = None,
) -> tuple[SchoolYearConfig, object, tuple[date, date] | None, list]:
    """Ferien und Schuljahresgrenzen abrufen. Gemeinsam für Vorschau und Übernahme."""
    cfg = load_school_year()
    adapter = get_adapter()
    async with adapter:  # type: ignore[attr-defined]
        years = await adapter.fetch_school_years()  # type: ignore[attr-defined]
        gewaehlt = _waehle_jahr(years, cfg, schuljahr)
        bounds = (gewaehlt.start, gewaehlt.end) if gewaehlt else None
        holidays = await adapter.fetch_holidays(  # type: ignore[attr-defined]
            within=bounds or (cfg.beginn, cfg.ende)
        )
    return cfg, holidays, bounds, years


def _bounds_pruefen(
    cfg: SchoolYearConfig, bounds: tuple[date, date] | None
) -> tuple[tuple[date, date] | None, list[str]]:
    """Grenzen nur übernehmen, wenn der Halbjahreswechsel darin liegt.

    `SchoolYearConfig` verlangt `beginn < halbjahreswechsel < ende`. Grenzen zu schreiben,
    die das verletzen, machte die Datei unladbar — und zwar erst beim nächsten Start.
    """
    if bounds is None:
        return None, []
    if bounds == (cfg.beginn, cfg.ende):
        return None, []
    if not (bounds[0] < cfg.halbjahreswechsel < bounds[1]):
        return None, [
            f"Die Schuljahresgrenzen der Quelle ({bounds[0]} – {bounds[1]}) passen nicht "
            f"zum eingetragenen Halbjahreswechsel ({cfg.halbjahreswechsel}). Erst den "
            f"Halbjahreswechsel in school_year.yaml setzen, dann erneut übernehmen."
        ]
    return bounds, [
        f"Beginn und Ende werden von {cfg.beginn} – {cfg.ende} auf "
        f"{bounds[0]} – {bounds[1]} geändert."
    ]


def _antwort(cfg, proposal, bounds, hinweise, years=None, gewaehlt=None) -> dict:
    return {
        "configured": True,
        "schuljahr": cfg.schuljahr,
        # Auswählbare Schuljahre der Quelle — ohne sie käme der Import zum Jahreswechsel
        # nie aus der bestehenden Konfiguration heraus.
        "schuljahre": [
            {"name": y.name, "beginn": y.start.isoformat(), "ende": y.end.isoformat(),
             "gewaehlt": gewaehlt is not None and y.name == gewaehlt.name}
            for y in (years or [])
        ],
        "halbjahreswechsel": cfg.halbjahreswechsel.isoformat(),
        "beginn": (bounds or (cfg.beginn, cfg.ende))[0].isoformat(),
        "ende": (bounds or (cfg.beginn, cfg.ende))[1].isoformat(),
        "abschnitte": len(proposal.ferien)
        + len(proposal.feiertage)
        + len(proposal.unterrichtsfreie_tage),
        "neu": [tag.isoformat() for tag in proposal.neu],
        "nur_in_config": [tag.isoformat() for tag in proposal.nur_in_config],
        "warnungen": [*proposal.warnungen, *hinweise],
        "freie_wochentage": proposal.freie_wochentage,
        "yaml": render_school_year(proposal, cfg, bounds),
        "pfad": str(_DEFAULT_PATH),
    }


@router.get("/proposal")
async def holiday_proposal(
    schuljahr: str | None = None,
    _: JwtPayload = Depends(require_role("admin")),
) -> dict:
    """Vorschau — ändert nichts."""
    if not is_configured():
        return {
            "configured": False,
            "detail": "Es ist keine Stundenplanquelle eingerichtet (WEBUNTIS_SERVER).",
        }
    try:
        cfg, holidays, bounds, years = await _hole_vorschlag(schuljahr)
    except NoActiveSchoolYearError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except CalendarSourceError as exc:
        logger.warning("Ferienabruf fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from None

    genutzte_bounds, hinweise = _bounds_pruefen(cfg, bounds)
    gewaehlt = _waehle_jahr(years, cfg, schuljahr)
    proposal = build_proposal(holidays, cfg)
    return _antwort(cfg, proposal, genutzte_bounds, hinweise, years, gewaehlt)


@router.post("/apply")
async def holiday_apply(
    payload: ApplyRequest,
    _: JwtPayload = Depends(require_role("admin")),
) -> dict:
    """`school_year.yaml` schreiben. Die bisherige Fassung wird daneben gesichert."""
    if not is_configured():
        raise HTTPException(status_code=409, detail="Keine Stundenplanquelle eingerichtet.")
    try:
        cfg, holidays, bounds, _years = await _hole_vorschlag(payload.schuljahr)
    except NoActiveSchoolYearError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except CalendarSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None

    genutzte_bounds, hinweise = _bounds_pruefen(cfg, bounds)
    if not payload.bounds_uebernehmen:
        genutzte_bounds = None
    proposal = build_proposal(holidays, cfg)
    inhalt = render_school_year(proposal, cfg, genutzte_bounds)

    # Gegenprobe vor dem Schreiben: Was nicht lädt, darf die Datei nicht ersetzen. Der
    # Fehler fiele sonst erst beim nächsten Start auf — und dann ohne Zusammenhang.
    import yaml as pyyaml

    try:
        SchoolYearConfig.model_validate(pyyaml.safe_load(inhalt))
    except Exception as exc:
        logger.error("Erzeugte school_year.yaml ist ungültig: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Der erzeugte Kalender ist ungültig und wurde nicht geschrieben: {exc}",
        ) from None

    backup = write_school_year(_DEFAULT_PATH, inhalt)
    # Ohne das Leeren arbeitet der laufende Prozess mit dem alten Stand weiter.
    load_school_year.cache_clear()
    neu = load_school_year()
    logger.info(
        "school_year.yaml geschrieben: %s Ferien, %s Feiertage, %s unterrichtsfreie Tage",
        len(neu.ferien), len(neu.feiertage), len(neu.unterrichtsfreie_tage),
    )
    return {
        "geschrieben": True,
        "pfad": str(_DEFAULT_PATH),
        "sicherung": str(backup) if backup else None,
        "warnungen": [*proposal.warnungen, *hinweise],
        "uebernommen": len(proposal.neu),
    }
