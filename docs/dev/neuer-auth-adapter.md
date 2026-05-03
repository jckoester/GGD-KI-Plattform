# Neuen Auth-Adapter implementieren

Ein neuer Adapter ist nötig, wenn die Schule einen anderen SSO-Provider
verwendet als den mitgelieferten (z. B. Keycloak, Azure AD, LDAP).

## Interface (`app/auth/base.py`)

```python
class AuthAdapter(ABC):

    @property
    @abstractmethod
    def mode(self) -> Literal["redirect", "direct"]:
        """
        "redirect": OAuth2/OIDC-Flow — Nutzer wird zum Provider weitergeleitet.
        "direct":   Formular-Login — Credentials direkt im Backend geprüft.
        """
        ...

    @abstractmethod
    async def get_login_challenge(self) -> LoginChallenge:
        """
        Für mode="redirect": Gibt die Provider-URL zurück, zu der der Browser
        weitergeleitet wird.
        Für mode="direct": Gibt LoginChallenge(type="form") zurück.
        """
        ...

    @abstractmethod
    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity:
        """
        Nur für mode="redirect".
        Tauscht den OAuth2-Authorization-Code gegen eine NormalizedIdentity.
        Wirft eine Exception bei ungültigem Code.
        """
        ...

    @abstractmethod
    async def authenticate_direct(
        self, username: str, password: str
    ) -> NormalizedIdentity | None:
        """
        Nur für mode="direct".
        Gibt None zurück, wenn Credentials ungültig sind.
        """
        ...
```

## Schritt-für-Schritt

**1. Adapter-Datei anlegen**

```python
# backend/app/auth/adapters/mein_provider.py

from app.auth.base import AuthAdapter, LoginChallenge, NormalizedIdentity

class MeinProviderAdapter(AuthAdapter):

    def __init__(self, config, settings, group_role_map: dict[str, str]):
        self._config = config
        self._settings = settings
        self._group_role_map = group_role_map

    @property
    def mode(self) -> Literal["redirect"]:
        return "redirect"

    async def get_login_challenge(self) -> LoginChallenge:
        # Provider-URL aufbauen, state generieren
        state = secrets.token_urlsafe(32)
        url = f"{self._config.base_url}/authorize?..."
        return LoginChallenge(type="redirect", redirect_url=url, state=state)

    async def exchange_code(self, code: str, state: str) -> NormalizedIdentity:
        # Code gegen Token tauschen, Userinfo abrufen
        # Gruppen auf Rollen mappen
        roles = [
            self._group_role_map[g]
            for g in user_groups
            if g in self._group_role_map
        ]
        return NormalizedIdentity(
            external_id=user_id,
            roles=roles,
            grade=grade_from_groups(user_groups),
            display_name=user_info.get("name"),  # nur UI, nie persistieren
        )

    async def authenticate_direct(self, username, password):
        return None  # Nicht unterstützt für redirect-Adapter
```

**2. Adapter in `get_auth_adapter()` registrieren**

```python
# backend/app/auth/dependencies.py

@lru_cache(maxsize=1)
def get_auth_adapter() -> AuthAdapter:
    auth_config = load_auth_config(settings.auth_config_path)
    if auth_config.adapter == "mein_provider":
        from app.auth.adapters.mein_provider import MeinProviderAdapter
        return MeinProviderAdapter(auth_config.mein_provider, settings, ...)
    # ... bestehende Adapter
```

**3. Config-Klasse in `app/auth/config.py` ergänzen**

Analog zur bestehenden Provider-Config-Klasse eine `MeinProviderConfig` anlegen und in
`AuthConfig` als optionales Feld eintragen.

**4. `config/auth.yaml` anpassen**

```yaml
adapter: mein_provider
mein_provider:
  base_url: https://sso.beispielschule.de
  client_id: ki-plattform
  redirect_uri: https://ki.beispielschule.de/auth/callback
```

## Wichtige Invarianten

Diese Regeln müssen in jedem Adapter eingehalten werden:

**`display_name` nie persistieren.**
Er darf nur als Feld in `NormalizedIdentity` zurückgegeben werden und wird
vom Backend ausschließlich in die HTTP-Antwort des Login-Endpunkts geschrieben,
von wo aus das Frontend ihn im `sessionStorage` hält. Er landet nie in der DB.

**`external_id` muss über alle Logins stabil sein.**
Das Pseudonym wird deterministisch aus `external_id` berechnet. Ändert sich
`external_id` für denselben Nutzer (z. B. nach einer Passwortänderung), entsteht
ein neues Pseudonym — der Nutzer verliert seinen bisherigen Chat-Verlauf.

**`grade` nur setzen, wenn `student` in `roles`.**
Das wird von `NormalizedIdentity` als Validator erzwungen — ein Adapter,
der dagegen verstößt, löst beim Konstruieren eine `ValueError` aus.

## Referenzimplementierung

`app/auth/adapters/yaml_test.py` ist die einfachste Implementierung
(`mode="direct"`, kein OAuth-Redirect) und eignet sich gut als Ausgangspunkt.
