"""Täglicher Stundenplan-Abgleich (UP-8, Schritt 10a).

Gleicht für jede Lehrkraft mit hinterlegtem Kürzel Entfall, Vertretung und Verlegung ab
und hält das Ergebnis in `calendar_sync_status` fest.

**Fail-open, und zwar zweifach:**

1. **Je Lehrkraft.** Ein Kürzel, das WebUntis nicht kennt, darf nicht den Lauf für die
   übrigen 89 abbrechen. Jede wird einzeln abgeglichen und einzeln festgehalten.
2. **Je Lauf.** Ist die Quelle nicht erreichbar, bleibt die Planung **unverändert** und
   der Status sagt warum. Slots zu verwerfen, weil ein fremder Server kurz nicht antwortet,
   wäre der teuerste denkbare Fehler — die Jahresplanung ist Handarbeit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.base import AuthenticationError, CalendarSourceError
from app.calendar.service import KUERZEL_PREFERENCE_KEY, is_configured
from app.calendar.sync import apply_sync

logger = logging.getLogger(__name__)

# Wie viele Wochen der Cron je Lauf zurückblickt. Vier deckt nachgetragene Vertretungen
# ab, ohne bei jedem Lauf das halbe Schuljahr neu zu lesen. Nach vorn schaut das
# Abgleichfenster ohnehin (Verlegungsziele) — siehe `_abgleich_wochen`.
#
# Der Cron ist das **Sicherheitsnetz**, nicht der Hauptweg: Am GGD werden Änderungen erst
# Minuten vor Unterrichtsbeginn eingetragen, ein nächtlicher Lauf sieht sie also erst am
# Folgetag. Für den Tagesbedarf gibt es den Handabgleich (`POST /calendar/sync`) — bei
# Ausfall ist der Verzug verkraftbar, bei Verlegungen nicht.
_WOCHEN = 4


@dataclass
class SyncStats:
    lehrkraefte: int = 0
    erfolgreich: int = 0
    fehlgeschlagen: int = 0
    geaendert: int = 0
    konflikte: int = 0
    verlegungen: int = 0
    duration_ms: int = 0


def _status_fuer(exc: Exception) -> tuple[str, str]:
    """Fehler in einen Status übersetzen, der etwas aussagt.

    Ein einziger Sammelstatus („fehler") ließe die Lehrkraft raten, ob ihr Kürzel falsch
    ist oder der Server streikt — zwei Ursachen mit sehr verschiedenen Konsequenzen.
    """
    if isinstance(exc, AuthenticationError):
        return "anmeldung_fehlgeschlagen", str(exc)
    if isinstance(exc, CalendarSourceError):
        text_ = str(exc)
        if "nicht erreichbar" in text_ or "HTTP" in text_:
            return "nicht_erreichbar", text_
        return "fehler", text_
    return "fehler", f"{type(exc).__name__}"


async def _status_schreiben(
    db: AsyncSession,
    pseudonym: str,
    status: str,
    *,
    fehler: str | None = None,
    changed: int = 0,
    conflicts: int = 0,
    shifts: int = 0,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO calendar_sync_status
                (pseudonym, last_sync_at, status, error, changed, conflicts, shifts,
                 updated_at)
            VALUES (:p, now(), :s, :e, :c, :k, :v, now())
            ON CONFLICT (pseudonym) DO UPDATE SET
                last_sync_at = now(), status = EXCLUDED.status, error = EXCLUDED.error,
                changed = EXCLUDED.changed, conflicts = EXCLUDED.conflicts,
                shifts = EXCLUDED.shifts, updated_at = now()
            """
        ),
        {
            "p": pseudonym,
            "s": status,
            "e": (fehler or None) and fehler[:500],
            "c": changed,
            "k": conflicts,
            "v": shifts,
        },
    )
    await db.commit()


async def _lehrkraefte_mit_kuerzel(db: AsyncSession) -> list[str]:
    rows = await db.execute(
        text(
            "SELECT pseudonym FROM user_preferences "
            "WHERE coalesce(preferences->>:key, '') <> '' ORDER BY pseudonym"
        ),
        {"key": KUERZEL_PREFERENCE_KEY},
    )
    return [row[0] for row in rows.fetchall()]


async def run_calendar_sync(
    db: AsyncSession,
    *,
    wochen: int = _WOCHEN,
    bis: date | None = None,
    dry_run: bool = False,
) -> SyncStats:
    """Alle Lehrkräfte mit hinterlegtem Kürzel abgleichen."""
    start = perf_counter()
    stats = SyncStats()

    if not is_configured():
        logger.info("Keine Stundenplanquelle eingerichtet — Abgleich übersprungen")
        return stats

    # Lokal importiert: Der Router zieht FastAPI-Abhängigkeiten nach, die ein Cron nicht
    # braucht — und ein Zyklus Router → Cron → Router wäre sonst leicht gebaut.
    from app.calendar.router import _stundenplan_abgleich

    pseudonyme = await _lehrkraefte_mit_kuerzel(db)
    stats.lehrkraefte = len(pseudonyme)

    for pseudonym in pseudonyme:
        try:
            plan, kontext, hinweis = await _stundenplan_abgleich(db, pseudonym, wochen, bis)
        except Exception as exc:                      # noqa: BLE001 — je Lehrkraft fangen
            status, meldung = _status_fuer(exc)
            stats.fehlgeschlagen += 1
            logger.warning("Abgleich fehlgeschlagen (%s): %s", status, meldung)
            await _status_schreiben(db, pseudonym, status, fehler=meldung)
            continue

        if hinweis:
            stats.fehlgeschlagen += 1
            await _status_schreiben(db, pseudonym, "kein_kuerzel", fehler=hinweis)
            continue

        geaendert = 0 if dry_run else await apply_sync(db, plan)
        stats.erfolgreich += 1
        stats.geaendert += geaendert
        stats.konflikte += len(plan.conflicts)
        stats.verlegungen += len(plan.verlegungen)
        if not dry_run:
            await _status_schreiben(
                db,
                pseudonym,
                "ok",
                changed=geaendert,
                conflicts=len(plan.conflicts),
                shifts=len(plan.verlegungen),
            )
        logger.info(
            "Abgleich %s: %s geändert, %s Konflikte, %s Verlegungen",
            kontext["kuerzel"],
            geaendert,
            len(plan.conflicts),
            len(plan.verlegungen),
        )

    stats.duration_ms = int((perf_counter() - start) * 1000)
    return stats


async def letzter_status(db: AsyncSession, pseudonym: str) -> dict | None:
    """Der letzte Abgleich dieser Lehrkraft — Grundlage der Anzeige in 10b."""
    row = (
        await db.execute(
            text(
                "SELECT last_sync_at, status, error, changed, conflicts, shifts "
                "FROM calendar_sync_status WHERE pseudonym = :p"
            ),
            {"p": pseudonym},
        )
    ).fetchone()
    if row is None:
        return None
    return {
        "last_sync_at": row[0].isoformat() if row[0] else None,
        "status": row[1],
        "error": row[2],
        "changed": row[3],
        "conflicts": row[4],
        "shifts": row[5],
    }
