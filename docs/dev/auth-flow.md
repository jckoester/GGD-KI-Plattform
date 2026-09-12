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

## Zweiter Weg: persönliche Zugangstoken (PAT)

Für Clients außerhalb des Browsers. Fehlt das Session-Cookie, prüft `get_current_user`
den `Authorization: Bearer ggd_pat_…`-Header und baut daraus **denselben**
`JwtPayload`-Principal — alle Guards dahinter (`require_group_teacher`, die
Sichtbarkeitsfilter) arbeiten unverändert.

Gespeichert wird nur `sha256(token)` (`personal_access_tokens`, Migration 0061); der
Klartext ist einmal sichtbar, bei der Erzeugung. **Rollen stehen nicht im Token** — sie
kommen bei jeder Anfrage frisch aus `pseudonym_audit`, damit ein Rollenentzug sofort
wirkt. `revoked_all_before` gilt sinngemäß mit.

### Das Scope-Gatter ist der eigentliche Sicherheitsteil

156 Guard-Stellen in 32 Dateien laufen über `get_current_user`. Ein zweiter Auth-Zweig
dort öffnet sie ohne Weiteres alle. `app/auth/scopes.py` ist deshalb die einzige Stelle,
an der ein Token Zugang bekommt, und sie arbeitet **deny-by-default**: Was nicht in
`_ZUSTAENDIG` steht, ist für Token gesperrt — ein neuer Router also ab der ersten Zeile.

```python
_ZUSTAENDIG = {
    "/planning":      ("planning:read", "planning:write"),
    "/context/nodes": ("context:read",  "context:write"),
    ...
}
```

Präfixe, aber **so eng wie der Zweck**: `/context` als Ganzes wäre zu viel gewesen —
darunter hängen auch Assistenten-Anker und Chat-Anhänge.

Schreibrecht enthält kein Leserecht; wer beides braucht, bekommt beide Scopes.
Gedrosselt wird **je Token** (`token`-Eimer), nicht je Person: Eine durchdrehende
Sync-Schleife soll ihre Besitzerin nicht aus dem Browser aussperren.

### Step-up ohne Ressource

Die Krisen-Aktionen binden ihr Step-up-Token an eine `resource_id` (Audit #3). Das
Anlegen eines Zugangstokens hat kein solches Gegenüber — die Ressource entsteht erst
dadurch. Dafür gibt es `require_fresh_stepup_ohne_ressource(action)` und die Liste
`STEPUP_AKTIONEN_OHNE_RESSOURCE`; die Fabrik weist eine ressourcengebundene Aktion ab,
damit keine Bindung stillschweigend verlorengeht.

Geprüft wird symmetrisch: Eine gebundene Aktion **braucht** eine ID, eine ressourcenlose
darf keine tragen — sonst gäbe es zwei Lesarten desselben Tokens.
