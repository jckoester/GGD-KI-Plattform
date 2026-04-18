from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from jose import jwt, JWTError
from pydantic import BaseModel

from app.db.models import JwtRevocation, PseudonymAudit
from sqlalchemy.ext.asyncio import AsyncSession


class JwtPayload(BaseModel):
    sub: str                                      # Pseudonym
    role: Literal["student", "teacher", "admin"]
    grade: str | None
    jti: str                                      # UUID4, für Revokation
    iat: int                                      # Unix-Timestamp
    exp: int                                      # Unix-Timestamp


class JwtService:
    def __init__(self, secret: str, algorithm: str = "HS256", ttl_days: int = 30) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = timedelta(days=ttl_days)

    def issue(self, pseudonym: str, role: str, grade: str | None) -> tuple[str, str]:
        """Gibt (token, jti) zurück."""
        now = datetime.now(timezone.utc)
        jti = str(uuid4())
        payload = {
            "sub": pseudonym,
            "role": role,
            "grade": grade,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, jti

    def verify(self, token: str) -> JwtPayload:
        """Wirft JWTError bei ungültigem oder abgelaufenem Token."""
        raw = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        return JwtPayload.model_validate(raw)

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
