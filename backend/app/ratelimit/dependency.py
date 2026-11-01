"""FastAPI-Dependency für das Ratelimiting (Sicherheits-Audit #2)."""
import time

from fastapi import Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.ratelimit.drossel import pruefe

#: (Eimer, Pseudonym) → Zeitpunkt des letzten Audit-Eintrags. Eine gedrosselte Person
#: schickt oft Dutzende Anfragen hintereinander; protokolliert wird die Sperre, nicht jede
#: abgewiesene Anfrage — höchstens ein Eintrag je Eimer, Person und Viertelstunde.
_ZULETZT_PROTOKOLLIERT: dict[tuple[str, str], float] = {}
_PROTOKOLL_ABSTAND = 900.0


def _sperre_protokollieren(bucket: str, current_user: JwtPayload) -> None:
    jetzt = time.monotonic()
    schluessel = (bucket, current_user.sub)
    if jetzt - _ZULETZT_PROTOKOLLIERT.get(schluessel, -_PROTOKOLL_ABSTAND) < _PROTOKOLL_ABSTAND:
        return
    _ZULETZT_PROTOKOLLIERT[schluessel] = jetzt
    from app.core.audit import audit_getrennt
    from app.core.hintergrund import im_hintergrund

    im_hintergrund(
        lambda: audit_getrennt("auth", "rate_limit_locked", akteur=current_user, daten={"eimer": bucket}),
        was="Audit rate_limit_locked",
    )


def rate_limit(bucket: str):
    """Dependency-Fabrik: drosselt pro Nutzer:in (JWT `sub`) nach `rate_limits.yaml`.

    Gibt die `JwtPayload` zurück → **Drop-in-Ersatz** für `get_current_user`. 429 mit
    `Retry-After`, wenn das Fenster-Limit überschritten ist.
    """
    async def _dep(current_user: JwtPayload = Depends(get_current_user)) -> JwtPayload:
        try:
            pruefe(bucket, current_user.sub, current_user.roles)
        except HTTPException:
            # Nur auf diesem Weg (Pseudonym), nicht im Token-Pfad: Dort ist der Schlüssel das
            # Zugangstoken selbst, und das gehört nie ins Protokoll.
            _sperre_protokollieren(bucket, current_user)
            raise
        return current_user

    return _dep
