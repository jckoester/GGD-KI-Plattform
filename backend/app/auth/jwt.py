from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from jose import jwt, JWTError
from pydantic import BaseModel

from app.auth.vorschau import Vorschau
from app.db.models import JwtRevocation, PseudonymAudit
from sqlalchemy.ext.asyncio import AsyncSession


class JwtPayload(BaseModel):
    sub: str                                      # Pseudonym
    roles: list[str]                              # Liste aller Rollen
    grade: str | None
    display_name: str | None = None               # nur Browser-Anzeige, nicht persistiert
    sso_groups: list[str] = []                    # rohe SSO-Gruppen, nur Browser-Diagnose
    sso_roles: list[str] = []                     # rohe SSO-Rollen, nur Browser-Diagnose
    jti: str                                      # UUID4, für Revokation
    iat: int                                      # Unix-Timestamp
    exp: int                                      # Unix-Timestamp
    # Nur bei Zugangstoken gesetzt (`app.auth.tokens`); eine Browser-Sitzung hat hier
    # `None`. Der Unterschied ist nicht kosmetisch: `None` heißt „volle Sitzung", eine
    # Liste heißt „nur diese Scopes, und nur auf Routern, die sie führen"
    # (`app.auth.scopes`). Aus einem JWT kommt das Feld nie — Sitzungen tragen es nicht.
    token_scopes: list[str] | None = None
    # Vorschaumodus (0.29, ADR-016, Ansatz C): In einem Vorschau-Token stehen in `roles`
    # und `grade` die **simulierten** Werte (`student`, gewählter Jahrgang); die echten
    # stehen hier. `None` heißt: keine Vorschau. Siehe `app.auth.vorschau`.
    preview: Vorschau | None = None


class JwtService:
    def __init__(self, secret: str, algorithm: str = "HS256", ttl_days: int = 30) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = timedelta(days=ttl_days)

    def issue(
        self, pseudonym: str, roles: list[str], grade: str | None,
        display_name: str | None = None,
        sso_groups: list[str] | None = None,
        sso_roles: list[str] | None = None,
        *,
        preview: Vorschau | None = None,
        exp: int | None = None,
    ) -> tuple[str, str]:
        """Gibt (token, jti) zurück.

        ``exp`` setzt den Ablauf fest (Unix-Zeit) statt ``jetzt + ttl`` — für das
        Vorschau-Token und den Rückweg aus ihm, der die alte Sitzung nicht verlängern darf
        (0.29, F1). ``preview`` ist das Vorschau-Merkmal (`app.auth.vorschau`).
        """
        now = datetime.now(timezone.utc)
        jti = str(uuid4())
        payload = {
            "sub": pseudonym,
            "roles": roles,
            "grade": grade,
            "display_name": display_name,
            "sso_groups": sso_groups or [],
            "sso_roles": sso_roles or [],
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": exp if exp is not None else int((now + self._ttl).timestamp()),
        }
        if preview is not None:
            payload["preview"] = preview.model_dump()
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, jti

    def verify(self, token: str) -> JwtPayload:
        """Wirft JWTError bei ungültigem oder abgelaufenem Token."""
        raw = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        # `token_scopes` gehört dem Token-Pfad und kann aus einer Sitzung nicht kommen.
        # `issue` setzt es nie; hier steht es trotzdem, damit ein künftiger Aufrufer mit
        # zusätzlichen Claims nicht versehentlich eine Sitzung in ein Token verwandelt.
        return JwtPayload.model_validate({**raw, "token_scopes": None})

    def verify_ohne_ablauf(self, token: str) -> JwtPayload:
        """Wie :meth:`verify`, aber ein abgelaufenes Token gilt noch als lesbar.

        **Nur** für den Rückweg aus der Vorschau (0.29, F1): Nach 60 Minuten trägt das Cookie
        ein abgelaufenes Vorschau-Token und sonst nichts — ohne diesen Weg wäre mit der
        Vorschau auch die Sitzung der Lehrkraft vorbei. Die Signatur wird geprüft; ob der
        Rückweg zulässig ist (Merkmal, Widerruf, Ablauf der Ausgangssitzung), entscheidet
        der Aufrufer.
        """
        raw = jwt.decode(token, self._secret, algorithms=[self._algorithm],
                         options={"verify_exp": False})
        return JwtPayload.model_validate({**raw, "token_scopes": None})

    async def revoke(
        self,
        db: AsyncSession,
        jti: str,
        pseudonym: str,
        expires_at: datetime,
        reason: str | None = None,
    ) -> None:
        db.add(JwtRevocation(
            jti=jti,
            pseudonym=pseudonym,
            expires_at=expires_at,
            reason=reason,
        ))
        await db.commit()

    async def is_revoked(self, db: AsyncSession, payload: JwtPayload) -> bool:
        # 1. Gezielte Revokation: jti in jwt_revocations?
        row = await db.get(JwtRevocation, payload.jti)
        if row is not None:
            return True
        # 2. Massen-Revokation: iat < pseudonym_audit.revoked_all_before?
        audit = await db.get(PseudonymAudit, payload.sub)
        if audit and audit.revoked_all_before:
            if datetime.fromtimestamp(payload.iat, timezone.utc) < audit.revoked_all_before:
                return True
        return False
