# Auth-Flow & Pseudonymisierung

## AuthAdapter-Interface (`app/auth/base.py`)

Jeder Auth-Adapter implementiert die abstrakte Klasse `AuthAdapter` und gibt
eine `NormalizedIdentity` zurück — eine einheitliche Darstellung des eingeloggten
Nutzers, unabhängig vom SSO-Provider.

```python
class NormalizedIdentity(BaseModel):
    external_id: str          # Stabile Nutzer-ID vom Provider — wird pseudonymisiert
    roles: list[str]          # Mind. eine aus {student, teacher, admin}
    grade: str | None         # Nur für Schüler:innen (z. B. "10")
    display_name: str | None  # Nur UI-Anzeige — NIEMALS persistieren

class AuthAdapter(ABC):
    @property
    @abstractmethod
    def mode(self) -> Literal["redirect", "direct"]: ...

    @abstractmethod
    async def get_login_challenge(self) -> LoginChallenge: ...

    # OAuth2: Code gegen Identity tauschen
    @abstractmethod
    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity: ...

    # Formular-Login (z. B. yaml_test-Adapter)
    @abstractmethod
    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None: ...
```

## OAuth2-Redirect-Flow (Produktionsbetrieb)

```
Browser          Backend              SSO-Provider
  │                │                      │
  ├─GET /auth/login─▶                     │
  │                ├─get_login_challenge()─▶
  │                │◀── LoginChallenge ───┤
  │◀── redirect ───┤                      │
  │                                       │
  ├────── Nutzer meldet sich an ──────────▶
  │◀── redirect /auth/callback?code=... ──┤
  │                │                      │
  ├─GET /callback──▶                      │
  │                ├─exchange_code() ─────▶
  │                │◀── NormalizedIdentity┤
  │                │                      │
  │                ├─ pseudonymize(external_id, SCHOOL_SECRET)
  │                ├─ DB: User upsert (pseudonym, roles, grade)
  │                ├─ JWT ausstellen (sub=pseudonym, roles, grade)
  │◀── HttpOnly Cookie (30 Tage) ─────────┤
```

## JWT-Struktur (`app/auth/jwt.py`)

```python
class JwtPayload(BaseModel):
    sub: str            # Pseudonym — einzige Nutzerkennung im Backend
    roles: list[str]    # ["student"] / ["teacher"] / ["admin"] / ["teacher","admin"]
    grade: str | None   # Jahrgang für Budget-Tier-Auflösung
    jti: str            # UUID4 — ermöglicht gezielte Token-Revokation
    iat: int            # Ausstellungszeitpunkt (Unix-Timestamp)
    exp: int            # Ablaufzeitpunkt (iat + 30 Tage)
```

Token-Lebensdauer: **30 Tage**, HttpOnly-Cookie (kein JavaScript-Zugriff).

**Token-Revokation** — zwei Mechanismen in `JwtService.is_revoked()`:
1. **Gezielt:** `jti` ist in der Tabelle `jwt_revocations` vorhanden.
2. **Massen-Revokation:** `iat` liegt vor `pseudonym_audit.revoked_all_before`
   — damit können alle Token eines Nutzers auf einmal ungültig gemacht werden
   (z. B. nach Passwortänderung).

## Pseudonymisierung (`app/auth/pseudonym.py`)

```python
def pseudonymize(external_id: str, school_secret: str) -> str:
    return hmac.new(
        school_secret.encode(), external_id.encode(), hashlib.sha256
    ).hexdigest()
```

- **Deterministisch:** Gleiche Inputs → gleicher Hex-String. Das Pseudonym
  ist über alle Logins stabil, solange `SCHOOL_SECRET` unverändert bleibt.
- **Nicht umkehrbar:** Ohne `SCHOOL_SECRET` ist keine Rückrechnung möglich.
- **Keine Datenbank:** Die Zuordnung `pseudonym ↔ external_id` wird nirgendwo
  gespeichert — sie kann jederzeit neu berechnet werden.

## Dependency Injection in Endpunkten

```python
# In jedem geschützten Endpunkt:
async def my_endpoint(
    user: JwtPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pseudonym = user.sub
    is_admin = "admin" in user.roles
```

`get_current_user` (`app/auth/dependencies.py`) liest das JWT-Cookie, verifiziert
die Signatur und prüft ob das Token revoziert ist. Bei ungültigem Token: HTTP 401.
