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

### Token anlegen: frische Sitzung statt Step-up *(seit 0.18.3)*

`POST /tokens` hängt an `require_frische_sitzung()` (`auth/dependencies.py`): Das `iat` des
Sitzungs-JWT darf höchstens `FRISCHE_SITZUNG_S` (15 min) zurückliegen, sonst 401 mit
`X-Frische-Anmeldung: 1`. Das Sitzungs-JWT entsteht nur beim Login, `iat` ist also die
Anmeldezeit. Die Oberfläche bietet dann „Kurz neu anmelden" (`neuAnmelden` in `api.js`):
Formular merken (`merkeFormular`), abmelden, `/?return_to=<pfad>`. Die Anmeldeseite reicht
`return_to` an `/auth/login-challenge` weiter; der Callback liest es aus dem dritten Feld des
Bindungs-Cookies (`state|verifier|ziel`) und leitet dorthin. Im Redirect-Modus springt die
Anmeldeseite ohne Knopf gleich weiter. Ziele laufen beidseits durch dieselbe Regel
(`_safe_return_to` / `lokalesZiel`): nur lokale Pfade, kein `//`, kein `/\`, keine
Steuerzeichen.

Was das schützt und was nicht: Ein **gestohlenes Cookie** reicht nicht — ohne Sitzung beim
Schulkonto kein neuer Login. Ein **entsperrtes, angemeldetes Gerät** schon — bewusst so
entschieden (Jan, 19.10.2026), weil das Schulkonto keine frische Anmeldung nachweist
(`auth_time` fehlt, `prompt=login` wird übergangen). Bis 0.18.2 lief das Anlegen über ein
ressourcenloses Step-up (`create_token`); das ist entfernt, jede Step-up-Aktion ist jetzt an
einen Krisen-Antrag gebunden.

### Step-up im Redirect-Modus: Frische ohne `auth_time` *(0.18.4)*

`_handle_stepup_callback` prüft `auth_time` nur noch, **wenn es kommt**. Fehlt es — das
Schulkonto liefert es nie —, gilt der Rücksprung als frisch: Die Challenge schickt
`prompt=login` (+ `max_age=0`), und das Schulkonto verlangt dann nachweislich (Prod-Test
19.10.2026) Passwort und 2FA. Am Token prüfbar ist das nicht; `sid` bleibt bei der
erzwungenen Anmeldung sogar gleich (nur echtes Abmelden erzeugt eine neue). In jedem Fall
Pflicht: die Werte aus `oauth.stepup_amr` (Vorgabe `["mfa"]`) in `FreshIdentity.amr`, das
nur aus einem geprüften bzw. über den Back-Channel gelieferten ID-Token stammt; sonst
`stepup_fehler=ohne_2fa`. Angenommene Rücksprünge ohne `auth_time` loggen
`Step-up angenommen ohne auth_time`. Restrisiko (Weiterleitung ohne `prompt=login`
nachgebaut, an einem entsperrten Gerät): ADR-008, Nachtrag 19.10.2026.

### Step-up im Redirect-Modus: Rücksprung und Protokoll *(0.18.1)*

Der Callback (`_handle_stepup_callback`) lehnt nie mehr mit JSON ab, sondern springt über
`_stepup_abgelehnt(grund, return_to, detail)` auf die Ausgangsseite zurück:
`return_to?stepup_fehler=<grund>` mit `abgebrochen`, `fehlgeschlagen`, `nicht_frisch` oder
`anderes_konto`. Ist der State nicht gültig signiert, ist auch `return_to` nicht
vertrauenswürdig — dann `/welcome`. Ohne gültige Sitzung geht es auf die Anmeldeseite.

Jede Ablehnung schreibt eine Logzeile `Step-up abgelehnt (<grund>)` mit Aktion,
Pseudonym-Präfix, Alter von `auth_time` (negativ = Zukunft) und `FreshIdentity.diagnose`:
ob ein ID-Token kam, wie die Signatur ausfiel, ob UserInfo ein `auth_time` trägt, und die
**Namen** der Claims. Keine Werte.

*Seit 0.18.2* zusätzlich `sitzung` — `sitzungsmerkmale()` aus `adapters/oauth.py`: die ersten
12 Zeichen von sha256(`sid`), `amr`, `acr` — und das Alter von `iat`. Dieselben Merkmale stehen
beim Login in der Zeile `OAuth-Login: …`. Hintergrund: Das Schulkonto liefert kein `auth_time`
(Discovery ohne den Claim), und `prompt=login` wird bei bestehender Sitzung übergangen. Der
Vergleich soll zeigen, ob ein Abmelden beim Schulkonto mit anschließender Anmeldung an einer
neuen `sid` erkennbar ist.

Im Frontend liest `StepUpFehler.svelte` (einmal im Layout) den Code und zeigt einen Satz
dazu (`lib/stepup_rueckkehr.js`). Ein Formular, das nach einer Anmeldung weitermachen soll,
merkt sich seine Eingaben vor dem Verlassen der Seite (`merkeFormular`) und holt sie beim
nächsten Laden einmal zurück (`holeFormular`, 15 Minuten gültig) — seit 0.18.3 genutzt von
„Kurz neu anmelden" im `Zugangstoken.svelte`.

### Die eigenen Gruppen: `GET /planning/groups`

Die Unterrichtsgruppen, in denen der Nutzer **Lehrkraft** ist — genau die, für die
`/planning/groups/{id}/…` durchlässt (`planning:read`). Je Gruppe: Anzeigename, Fach mit
Bildungsplan-Kürzel (`fach.fach_code`), Jahrgang (dieselbe Regel wie die
Curriculum-Auswahl, `groups.jahrgang.jahrgang_aus`), Quellklassen, `aktuell` wie in
`/groups/me` und die Zahl der Termine im laufenden Schuljahr. `/groups/me` taugt dafür
nicht: Es liefert jede Mitgliedschaft ohne Rolle, vom Fach nur die Kennung.

⚠️ **Die Gruppen-ID wechselt nicht immer mit dem Schuljahr.** Ein Kursstufenkurs behält
Gruppe und Mitgliedschaft über zwei Jahre und gilt in beiden als `aktuell`. Wer Daten
einem Schuljahr zuordnet, nimmt das Datum des Termins, nicht die Gruppe und nicht
`overview.schuljahr` (das ist das eingestellte Jahr).

### Kein Chat über Token — auch kein Stundenbezug

`/chat` und `/conversations` stehen nicht in `_ZUSTAENDIG`. Den Stundenbezug eines Chats
(`conversations.stunde_node_id`, 0.15) setzt deshalb nur die Oberfläche — beim Anlegen über
`POST /chat` oder ein Werkzeug des Stundenassistenten (`waehle_stunde`); Felder und Ereignis
`bezug` in [chat-streaming.md](chat-streaming.md). Ein Sync-Client, der Stunden liest oder
schreibt, braucht ihn nicht: Er spricht die Stunde über `/planning/lessons/{id}` direkt an.

### Nebenläufig schreiben: `expected_updated_at`

`PATCH /planning/slots/{id}` und `PATCH /planning/lessons/{id}` nehmen optional den
`updated_at`-Stand entgegen, den der Client gelesen hat. Weicht er vom aktuellen ab,
antwortet der Endpunkt mit **409** und nennt im Körper beide Werte (`erwartet`,
`tatsaechlich`) — statt still zu überschreiben, was inzwischen in der Oberfläche
entstanden ist.

Freiwillig: Ohne das Feld bleibt es beim bisherigen Verhalten; die Oberfläche schickt es
nicht. Der `PATCH` auf eine Stunde gibt den neuen Stand zurück, damit ein Client zweimal
hintereinander schreiben kann, ohne dazwischen neu zu lesen: `updated_at` und seit 0.13
auch `phasen` und `stundenziel`, **so wie gespeichert** — dieselbe Form wie
`GET /planning/lessons/{id}`, mit den Kennungen, die neue Phasen bekommen haben.

**Felder, die der Client nicht kennt, bleiben erhalten (0.13).** Nachbereitung, Streichen,
Kürzen und Übertragen setzen an einer Phase Felder außerhalb des Phasenschemas (`status`,
`status_vorher`, `kuerzung`, `uebertrag_von`; `status_vorher` hält den Status vor der
Nachbereitung fest, damit „Rückgängig" ihn zurückgibt). Ein Client schickt nur die Schemafelder zurück; für jede Phase
mit bekannter `id` übernimmt der Server die übrigen aus dem gespeicherten Stand. Er muss sie
also weder kennen noch zurückschicken — wohl aber die `id` jeder bestehenden Phase, sonst
gilt sie als neu. Regel: `app/planning/phasen.py`, `uebernimm_zusatzfelder`.

⚠️ Das Ganze steht und fällt damit, dass `updated_at` sich bewegt. Bis 12.09.2026 tat es
das auf mehreren Schreibwegen nicht — dann ginge der Vergleich immer auf und der 409 käme
nie. `tests/integration/test_updated_at_wird_fortgeschrieben.py` hält die Voraussetzung
fest.
