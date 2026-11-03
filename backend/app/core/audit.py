"""Audit-Log schreiben — der einzige Weg in die Tabelle `audit_log` (0.28, ADR-010 §2.5).

Zwei Funktionen:

* :func:`audit` hängt einen Eintrag an die Sitzung des Aufrufers. Er wird mit dessen Commit
  geschrieben und rollt mit ihm zurück — protokolliert wird, was geschah. Für `admin`,
  `moderation`, `system`.
* :func:`audit_getrennt` schreibt sofort in einer eigenen Sitzung. Für `auth`-Fehlschläge: Der
  Anlass ist ein abgewiesener Request, dessen eigene Transaktion nichts festschreibt. Fehler
  beim Schreiben werden geloggt, nie geworfen — eine gescheiterte Protokollzeile darf keine
  Anmeldung kippen.

**Positivliste.** Ereignisse stehen in :data:`EREIGNISSE`; ein unbekannter Name ist ein
Programmierfehler (`ValueError`), kein stiller neuer Wert. Wer ein Ereignis ergänzt, ergänzt
es hier — und damit an einer Stelle, die man liest.

**Was nie hineingehört** (ADR-010 §2.1): Chat- und Meldungstexte, Prompts, Tokens, Passwörter,
Cookies, Kontaktangaben, IP-Adressen. :func:`audit` weist `daten` mit solchen Schlüsseln ab,
auch verschachtelt. Die Prüfung geht über Schlüsselnamen — sie ersetzt nicht das Nachdenken
darüber, was man übergibt, aber sie fängt den naheliegenden Fehler.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog

logger = logging.getLogger(__name__)

#: Woher `audit_getrennt` seine Sitzung nimmt. `None` = die Anwendungsdatenbank
#: (`AsyncSessionLocal`). Die Integrationstests setzen hier ihre Test-Datenbank ein, die
#: Unit-Tests schalten das Schreiben ab (`SCHREIBEN = False`) — sonst landeten Einträge aus
#: Testläufen in der Datenbank der Entwicklungsinstanz (so geschehen am 01.11.2026).
SITZUNGSFABRIK = None
SCHREIBEN = True

#: Kategorie → erlaubte Ereignisse. `access` bleibt in `conversation_access_audit` (§2.5).
EREIGNISSE: dict[str, frozenset[str]] = {
    "auth": frozenset({
        "login_failed",
        "stepup_denied",
        "rate_limit_locked",
        # Abgewiesene Rückmeldung einer gesperrten Person (ADR-020 §3). Akteur ist die
        # gesperrte Person, kein Admin — deshalb hier und nicht unter `admin`, wo das
        # Pseudonym die Kontolöschung überlebte.
        "feedback_blocked",
        # Vorschaumodus (ADR-016, 0.29)
        "preview_entered",
        "preview_exited",
    }),
    "admin": frozenset({
        "assistant_approved",
        "assistant_rejected",
        "assistant_activated",
        "assistant_deactivated",
        "assistant_deleted",
        "model_access_changed",
        "budget_changed",
        "budget_granted",
        "guardrail_changed",
        "site_text_changed",
        "holidays_changed",
        "user_sessions_revoked",
        "feedback_status_changed",
        "feedback_public_changed",
    }),
    "access": frozenset(),
    "moderation": frozenset({
        "crisis_flag_created",
        "crisis_flag_resolved",
    }),
    "secret": frozenset(),
    "system": frozenset({
        "accounts_cleaned",
        "conversations_cleaned",
        "node_lifecycle_run",
        "audit_log_cleaned",
    }),
}

#: Wörter, die als Teil eines Schlüssels in `daten` nicht vorkommen dürfen, wenn der Wert Text
#: (oder ein Gebilde) ist. Zahlen und Wahrheitswerte sind erlaubt — `message_count`,
#: `max_tokens` oder `hat_kontakt: true` sagen nichts über den Inhalt. Verglichen wird je
#: Wortteil (`_`-getrennt) und für einige starke Wörter auch als Teilwort.
_VERBOTEN_WORT = frozenset({
    "text", "texte", "inhalt", "content", "message", "nachricht", "prompt",
    "token", "tokens", "passwort", "password", "cookie", "secret",
    "kontakt", "contact", "snapshot", "ip", "email", "mail",
})
_VERBOTEN_TEIL = ("prompt", "passwort", "password", "cookie", "secret", "kontakt")


def _verboten(schluessel: str, wert: Any) -> bool:
    if wert is None or isinstance(wert, (bool, int, float)):
        return False
    name = str(schluessel).lower()
    if re.search(r"(^|_)(id|ids)$", name):
        return False
    teile = set(re.split(r"[^a-z0-9]+", name))
    return bool(teile & _VERBOTEN_WORT) or any(t in name for t in _VERBOTEN_TEIL)


def _pruefe_daten(daten: Any, pfad: str = "daten") -> None:
    if isinstance(daten, dict):
        for schluessel, wert in daten.items():
            if _verboten(schluessel, wert):
                raise ValueError(
                    f"Audit-Log: {pfad}.{schluessel} gehört nicht ins Protokoll (ADR-010 §2.1)"
                )
            _pruefe_daten(wert, f"{pfad}.{schluessel}")
    elif isinstance(daten, (list, tuple)):
        for i, wert in enumerate(daten):
            _pruefe_daten(wert, f"{pfad}[{i}]")


def _rolle(rollen: Optional[list[str]]) -> Optional[str]:
    """Die führende Rolle für `actor_role` — Admin vor Lehrkraft vor Schüler:in."""
    for r in ("admin", "teacher", "review", "budget", "statistics", "student"):
        if r in (rollen or []):
            return r
    return (rollen or [None])[0]


def eintrag(
    kategorie: str,
    ereignis: str,
    *,
    akteur: Any = None,
    rolle: Optional[str] = None,
    ziel: Optional[tuple[str, Any]] = None,
    daten: Optional[dict] = None,
) -> AuditLog:
    """Baut die Zeile und prüft sie — ohne sie zu schreiben."""
    if kategorie not in EREIGNISSE:
        raise ValueError(f"Audit-Log: unbekannte Kategorie {kategorie!r}")
    if ereignis not in EREIGNISSE[kategorie]:
        raise ValueError(f"Audit-Log: unbekanntes Ereignis {kategorie}.{ereignis} — in EREIGNISSE ergänzen")
    _pruefe_daten(daten or {})

    pseudonym = None
    if isinstance(akteur, str):
        pseudonym = akteur
    elif akteur is not None:  # JwtPayload oder Ähnliches
        pseudonym = getattr(akteur, "sub", None)
        rolle = rolle or _rolle(getattr(akteur, "roles", None))

    return AuditLog(
        category=kategorie,
        event_type=ereignis,
        actor_pseudonym=pseudonym,
        actor_role=rolle,
        target_type=ziel[0] if ziel else None,
        target_id=str(ziel[1]) if ziel and ziel[1] is not None else None,
        payload=daten or {},
        retention_class=kategorie,
    )


async def audit(db: AsyncSession, kategorie: str, ereignis: str, **kwargs) -> None:
    """Hängt einen Eintrag an die Sitzung des Aufrufers — geschrieben mit dessen Commit."""
    db.add(eintrag(kategorie, ereignis, **kwargs))


async def audit_getrennt(kategorie: str, ereignis: str, **kwargs) -> None:
    """Schreibt sofort in einer eigenen Sitzung. Wirft nie — ein Fehler wird geloggt.

    Die Prüfung (`eintrag`) läuft vorher und **wirft** bei Programmierfehlern: Ein falscher
    Ereignisname soll im Test auffallen, nicht im Betrieb still verschwinden.
    """
    zeile = eintrag(kategorie, ereignis, **kwargs)
    if not SCHREIBEN:
        return
    fabrik = SITZUNGSFABRIK
    if fabrik is None:
        from app.db.session import AsyncSessionLocal as fabrik

    try:
        async with fabrik() as db:
            db.add(zeile)
            await db.commit()
    except Exception:
        logger.exception("Audit-Log: %s.%s ließ sich nicht schreiben", kategorie, ereignis)
