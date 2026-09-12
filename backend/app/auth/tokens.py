"""Persönliche Zugangstoken (PAT) — Authentifizierung ohne Browser.

Der zweite Weg neben dem Session-Cookie, gedacht für Clients außerhalb des Browsers
(zunächst den Unterrichtsplanungs-Sync). Ein Token trägt **Scopes**; welche Router es
damit erreicht, entscheidet das Gatter in `app.auth.scopes` — nicht diese Datei.

**Der Klartext lebt genau einmal.** `erzeuge` gibt ihn zurück, gespeichert wird nur sein
SHA-256. Wer ihn verliert, erzeugt ein neues Token; wiederherstellen kann ihn niemand.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.db.models import PersonalAccessToken, PseudonymAudit

PRAEFIX = "ggd_pat_"

# Die Scopes, die es gibt, samt Beschriftung für die Oberfläche. Lesen und Schreiben sind
# getrennt, damit ein Spiegel, der nur liest, nicht schreiben *kann* — nicht bloß nicht
# schreiben *soll*.
#
# Eine Quelle: Die Oberfläche holt die Beschriftungen über `/tokens/scopes`, statt sie
# zweitzuführen. Eine zweite Liste veraltete beim nächsten Scope, und zwar stumm — der
# neue fehlte dann einfach im Auswahlfeld.
SCOPE_BESCHRIFTUNG: dict[str, str] = {
    "planning:read": "Unterrichtsplanung lesen",
    "planning:write": "Unterrichtsplanung ändern",
    "context:read": "Bausteine lesen",
    "context:write": "Bausteine ändern",
}

SCOPES = frozenset(SCOPE_BESCHRIFTUNG)

# Obergrenze der Gültigkeit. Richtlinie der Anwendung, keine Invariante der Daten —
# deshalb hier und nicht als CHECK in der Migration.
MAX_GUELTIGKEIT = timedelta(days=365)

# Rollen, die überhaupt Token haben dürfen. Schüler:innen bewusst nicht: Sie dürfen zwar
# inzwischen eigene Bausteine bearbeiten, aber ein Token ist ein Dauerzugang ohne
# Sitzungsende — das ist eine andere Zusage als „darf im Browser schreiben".
ERLAUBTE_ROLLEN = frozenset({"teacher", "admin"})

# Wie oft `last_used_at` höchstens geschrieben wird. Ohne Drossel würde jede Leseanfrage
# zu einer Schreibanfrage; die Angabe soll zeigen, ob ein Token noch benutzt wird, und
# dafür genügt Stundenauflösung.
_NUTZUNG_AUFLOESUNG = timedelta(hours=1)


def _hash(klartext: str) -> str:
    return hashlib.sha256(klartext.encode()).hexdigest()


class TokenFehler(Exception):
    """Erzeugung abgelehnt — die Meldung ist für die Nutzerin bestimmt."""


async def erzeuge(
    db: AsyncSession,
    *,
    pseudonym: str,
    name: str,
    scopes: list[str],
    gueltig_bis: datetime,
    rollen: list[str],
) -> tuple[str, PersonalAccessToken]:
    """Legt ein Token an und gibt **(Klartext, Zeile)** zurück.

    Der Klartext ist das einzige Mal hier zu haben. Die Prüfungen sind absichtlich hier
    und nicht erst im Endpunkt: Sie gelten auch für Tests und spätere Aufrufer.
    """
    if not ERLAUBTE_ROLLEN & set(rollen):
        raise TokenFehler("Zugangstoken sind Lehrkräften und Admins vorbehalten.")
    if not name.strip():
        raise TokenFehler("Ein Token braucht einen Namen.")
    unbekannt = set(scopes) - SCOPES
    if unbekannt:
        raise TokenFehler(f"Unbekannte Berechtigung: {', '.join(sorted(unbekannt))}")
    if not scopes:
        raise TokenFehler("Ein Token ohne Berechtigung kann nichts — bitte mindestens eine wählen.")

    jetzt = datetime.now(timezone.utc)
    if gueltig_bis <= jetzt:
        raise TokenFehler("Das Ablaufdatum liegt in der Vergangenheit.")
    if gueltig_bis > jetzt + MAX_GUELTIGKEIT:
        raise TokenFehler("Ein Token gilt höchstens ein Jahr.")

    klartext = PRAEFIX + secrets.token_urlsafe(32)
    zeile = PersonalAccessToken(
        pseudonym=pseudonym,
        name=name.strip(),
        token_hash=_hash(klartext),
        scopes=sorted(set(scopes)),
        expires_at=gueltig_bis,
    )
    db.add(zeile)
    await db.commit()
    await db.refresh(zeile)
    return klartext, zeile


async def pruefe(db: AsyncSession, klartext: str) -> tuple[PersonalAccessToken, JwtPayload] | None:
    """Löst einen Token-Klartext in (Zeile, Principal) auf. `None` heißt: kein Zugang.

    Bewusst **ein** Rückgabewert für alle Ablehnungsgründe — unbekannt, abgelaufen,
    widerrufen, Rolle entzogen. Wer ein Token rät, soll nicht am Unterschied zwischen
    „gibt es nicht" und „ist abgelaufen" ablesen können, dass er nah dran war.
    """
    if not klartext.startswith(PRAEFIX):
        return None

    zeile = (await db.execute(
        sa.select(PersonalAccessToken).where(
            PersonalAccessToken.token_hash == _hash(klartext)
        )
    )).scalar_one_or_none()
    if zeile is None:
        return None

    jetzt = datetime.now(timezone.utc)
    if zeile.revoked_at is not None or zeile.expires_at <= jetzt:
        return None

    # Rollen frisch aus dem Audit, nicht aus dem Token: Wem die Lehrkraft-Rolle entzogen
    # wurde, dessen Token verliert sie im selben Moment.
    audit = await db.get(PseudonymAudit, zeile.pseudonym)
    if audit is None:
        return None
    rollen = list(audit.roles) if audit.roles else [audit.role]
    if not ERLAUBTE_ROLLEN & set(rollen):
        return None

    # Massen-Revokation (Sicherheits-Audit #11) gilt auch für Token. Für ein JWT zählt
    # `iat`, hier die Anlage: Ein vor dem Stichtag erzeugtes Token ist genauso alt.
    if audit.revoked_all_before and zeile.created_at < audit.revoked_all_before:
        return None

    if zeile.last_used_at is None or jetzt - zeile.last_used_at > _NUTZUNG_AUFLOESUNG:
        await db.execute(
            sa.update(PersonalAccessToken)
            .where(PersonalAccessToken.id == zeile.id)
            .values(last_used_at=jetzt)
        )
        await db.commit()

    principal = JwtPayload(
        sub=zeile.pseudonym,
        roles=rollen,
        grade=str(audit.grade) if audit.grade is not None else None,
        jti=f"pat:{zeile.id}",
        iat=int(zeile.created_at.timestamp()),
        exp=int(zeile.expires_at.timestamp()),
        token_scopes=zeile.scopes,
    )
    return zeile, principal


async def widerrufe(db: AsyncSession, token_id: UUID, pseudonym: str) -> bool:
    """Widerruft ein eigenes Token. `False`, wenn es das (für diese Person) nicht gibt."""
    ergebnis = await db.execute(
        sa.update(PersonalAccessToken)
        .where(
            PersonalAccessToken.id == token_id,
            PersonalAccessToken.pseudonym == pseudonym,
            PersonalAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return ergebnis.rowcount > 0


async def meine(db: AsyncSession, pseudonym: str) -> list[PersonalAccessToken]:
    """Alle Token einer Person, jüngste zuerst — auch widerrufene und abgelaufene."""
    return list((await db.execute(
        sa.select(PersonalAccessToken)
        .where(PersonalAccessToken.pseudonym == pseudonym)
        .order_by(PersonalAccessToken.created_at.desc())
    )).scalars().all())
