# MCP-Server für KI-Abos (seit 0.54)

Päckchen AW. Ein lesender MCP-Server im Backend (`app/mcp/`), über den ein KI-Programm mit dem
Zugangstoken einer Lehrkraft Curricula, Bildungspläne und Leitlinien liest. Seit AX (0.55) ist die
Plattform zusätzlich OAuth-Autorisierungsserver (Abschnitt [OAuth](#oauth-seit-055)); der
MCP-Server prüft weiter ein Bearer-Token mit dem Scope `curriculum:read`, nun beider Arten.

Bibliothek: das offizielle Python-SDK `mcp` 2.3 (eng gepinnt, `<2.4`). ⚠️ 2.x hat die API
gegenüber 1.x umbenannt (`FastMCP` → `MCPServer`); Beispiele im Netz sind oft 1.x.

## Aufbau

| Datei | Was |
|---|---|
| `app/mcp/auth.py` | `ZugangstokenPruefer` (`TokenVerifier` des SDK) über `tokens.pruefe`, Scope Pflicht; `principal()` macht im Werkzeug ein `JwtPayload` daraus (ohne Vorschau) |
| `app/mcp/server.py` | `aussteller`, `baue_server`, `transportschutz`, Drossel-Hülle `_Gedrosselt`, `einhaengen`, `lebenszyklus` |
| `app/mcp/werkzeuge.py` | die neun Werkzeuge und ihre Lesefunktionen `lies_…(db, user, …)` |
| `app/mcp/oauth.py` | `Provider` (Speicher des Autorisierungsservers, seit 0.55), `oauth_aufraeumen` |
| `app/api/oauth.py` | Routen der Zustimmungsseite `/oauth/anfrage`, `/oauth/entscheidung` (seit 0.55) |

**Einhängen** (`app/main.py`): Mit `MCP_AKTIV` und `MCP_OEFFENTLICHE_URL` hängt `einhaengen`
eine **Route** `/mcp` an die App, keinen `Mount` — ein Mount auf `/mcp` beantwortet `/mcp` mit
einer Weiterleitung auf `/mcp/`, hinter nginx ohne `/api`. Die Hülle ist eine Klasse mit
`__call__`: Eine Funktion nähme Starlette als Request-Endpunkt (nur GET). Der Session-Manager
des SDK läuft im `lifespan` der App (`lebenszyklus`).

**Zustandslos, JSON** (`stateless_http=True`, `json_response=True`): jede Nachricht eine eigene
HTTP-Anfrage, keine Sitzung im Server, kein SSE. Für lesende Werkzeuge genügt das, und eine
Verbindung übersteht einen Neustart.

**Schutzschichten**, von außen nach innen:

1. Drossel `mcp` (60/min) je Token, gezählt je POST, Schlüssel = SHA-256 des
   `Authorization`-Kopfs. Antwort 429 mit `Retry-After`, bevor das SDK die Nachricht liest.
2. Host/Origin nur aus `MCP_OEFFENTLICHE_URL` (`TransportSecuritySettings`). Ohne Angabe ließe
   das SDK nur localhost zu — deshalb ist die Adresse Pflicht.
3. Anmeldung: Middleware des SDK; seit 0.55 baut sie den Prüfer aus `Provider.load_access_token`
   (OAuth-Zugriff `ggd_oat_…` **und** Zugangstoken `ggd_pat_…`). Ohne gültiges Token `401` mit
   `WWW-Authenticate: Bearer … resource_metadata="…"`. `validate_token_resource=True`: nur Token
   für genau diese Ressource; der Provider setzt `resource` auf beide Arten.
4. Rechte: Die Lesefunktionen lesen mit `principal()` — dieselben Prüfungen wie die GET-Routen
   (`_lesbares_curriculum`, `darf_entwurf_lesen`, `eigenes_zaehlt`).

`curriculum:read` steht **nicht** in `app.auth.scopes._ZUSTAENDIG` und öffnet deshalb keinen
REST-Weg. `test_token_scopes.py` kennt den MCP-Server als zweite Stelle, die einen Scope
verlangt. Im Profil bietet `/tokens/scopes` den Scope nur an, wenn die Schnittstelle an ist,
mit `hinweis`, `adresse` und `hilfe`.

## OAuth (seit 0.55)

Päckchen AX. Claude (Web, Desktop, Mobil), ChatGPT und Copilot melden Personen nur per OAuth 2.1
an. Die Endpunkte liefert das SDK (`create_auth_routes`, `create_protected_resource_routes`);
`app/mcp/oauth.py` ist der Speicher dahinter (`OAuthAuthorizationServerProvider`).

**Ablauf:**

1. Der Client holt `/.well-known/oauth-protected-resource/api/mcp` (RFC 9728; die Adresse steht
   auch im `WWW-Authenticate` des 401) und daraus den Issuer `https://<schule>/api`, dann
   `/.well-known/oauth-authorization-server/api` (RFC 8414).
2. `POST /api/register` — Dynamic Client Registration, offen; Redirect-URIs nur `https://` oder
   Loopback-`http` (`redirect_erlaubt`).
3. `GET /api/authorize` (PKCE S256) → `Provider.authorize` schreibt die Anfrage in ein
   signiertes JWT (`typ: oauth_anfrage`, 10 min, `JWT_SECRET`) und leitet auf
   `<FRONTEND_ORIGIN>/oauth/consent?anfrage=…`.
4. Die Zustimmungsseite (`routes/oauth/consent`, außerhalb von `(app)`) holt
   `GET /api/oauth/anfrage`; ohne Sitzung zur Anmeldung mit `return_to` und zurück.
   `POST /api/oauth/entscheidung` → `code_ausstellen` (256 Bit, 5 min, Hash) bzw. `ablehnen`
   (`access_denied`); die Antwort `weiter` ist der registrierte Rücksprung.
5. `POST /api/token` (Formular; PKCE prüft das SDK) → `exchange_authorization_code`: Code per
   `DELETE … RETURNING` einmalig, **Verbindung** anlegen, Token-Paar ausstellen.
6. Refresh → `exchange_refresh_token`: Rotation über `rotiert_at`; kommt ein eingelöster
   Refresh-Token noch einmal (`load_refresh_token`), endet die Verbindung.
7. `POST /api/revoke` → `revoke_token` beendet die Verbindung.

**Datenmodell (Migration 0112):**

| Tabelle | Inhalt |
|---|---|
| `oauth_clients` | `client_id`, `client_secret` **im Klartext** (das SDK vergleicht so; bei offener Registrierung schützt es wenig), Metadaten (JSONB), `last_used_at` |
| `oauth_codes` | Hash, Client, Pseudonym, Scopes, PKCE-Challenge, Redirect-URI, Ablauf |
| `personal_access_tokens` + `oauth_client_id` | die **Verbindung**: ein Eintrag je Person und Programm, `token_hash` leer, 90 Tage ab Zustimmung (fest) |
| `oauth_tokens` | Zugriff (`ggd_oat_`, 1 h) und Refresh (`ggd_ort_`, bis Verbindungsende) als Hash, `rotiert_at` |

Ein Zugriff prüft über seine Verbindung dasselbe wie ein Zugangstoken (`tokens.pruefe_zeile`):
Widerruf, Ablauf, Rollen frisch, `revoked_all_before`, `last_used_at`. Widerruf im Profil
(`DELETE /tokens/{id}`) wirkt deshalb sofort; Cascade löscht die Token mit.

**Adressen und Proxy.** Issuer = `MCP_OEFFENTLICHE_URL` ohne `/mcp` (`aussteller`). Die
SDK-Routen hängen einzeln an der App: `/authorize`, `/token`, `/register`, `/revoke` (gedrosselt,
Eimer `oauth` je Client-IP), `/.well-known/oauth-protected-resource/api/mcp` und die
AS-Metadaten zweimal: `/.well-known/oauth-authorization-server` (über `/api/…` gekürzt) und
`/.well-known/oauth-authorization-server/api` (RFC 8414 bei Issuer mit Pfad; nginx reicht
`location ^~ /.well-known/oauth-` ungekürzt durch). Alle öffentlichen Adressen kommen aus der
Konfiguration, nicht aus der Anfrage — hinter zwei Proxys ist `X-Forwarded-Proto` dort `http`.

**Aufräumen** `oauth_aufraeumen` (`scripts/cleanup_oauth.py`, Cron 04:20): nie benutzte Clients
nach 30 Tagen, abgelaufene Codes und Token, rotierte Refresh-Token nach 7 Tagen. Die
Kontolöschung nimmt Verbindungen (als Zugangstoken) und `oauth_codes` mit.

## Werkzeuge

| Werkzeug | Lesefunktion | Grundlage |
|---|---|---|
| `leitlinien` | `lies_leitlinien` | `alle_leitlinien` |
| `leitperspektiven` | `lies_leitperspektiven` | `leitperspektiven_lesen` des Assistenten |
| `leitlinie_uebersicht` | `lies_uebersicht` | `leitlinien_uebersicht` (AU); nimmt das **Kürzel**, `je_fach` mit Fachnamen |
| `curricula_finden` | `lies_curricula` | eigene Abfrage über alle Fächer, Regel wie `_lesbare_curricula` |
| `curriculum_lesen` | `lies_curriculum` | `_lesbares_curriculum` + `entwurf_lesen` |
| `curriculum_abdeckung` | `lies_abdeckung` | `abdeckung_kompakt` |
| `bildungsplan_kompetenzen` | `lies_kompetenzen` | `kompetenzen_lesen`; ein ungespeicherter `ContextNode` trägt Fach, Fassung und Stufen |
| `curriculum_yaml` (0.56) | `lies_curriculum_yaml` | `_lesbares_curriculum` + `build_curriculum_export_dict` — der YAML-Export |
| `curriculum_yaml_pruefen` (0.56) | `lies_yaml_pruefung` | `curriculum_yaml.durchlauf(…, speichern=False)`: der Import als Entwurf im Savepoint, verworfen ([YAML-Import](curriculum-yaml-import.md)); ohne Fachschaft `ok: false` mit Meldung |

Alle mit `ToolAnnotations(read_only_hint=True, destructive_hint=False, …)` und
`structured_output=False` (JSON als Text). Fehler als `ToolError` mit lesbarer Meldung.
`_ohne_personen` entfernt bekannte Personenfelder rekursiv (F6) — heute enthält keine Antwort
eines, der Filter ist das Netz für künftige Felder.

**Ein neues Werkzeug:** Lesefunktion `lies_…(db, user, …)`, Registrierung in `registrieren`
mit `annotations=LESEND`, Beschreibung für das Modell (was es liefert, nicht wie). Jeder neue
Import aus `app.*` muss in `ERLAUBT` des Wächters, mit Grund.

## Wächter

- `tests/unit/test_mcp_nur_lesend.py`: Importe nur aus `ERLAUBT` (deny-by-default), keine
  schreibenden Aufrufe im Paket, jedes Werkzeug lesend gekennzeichnet; Gegenproben. Grenze:
  Ob eine erlaubte Funktion intern schreibt, sichert die Begründung in `ERLAUBT`, kein Test.
  `oauth.py` ist ausgenommen und eng geprüft: schreibt nur `oauth_clients`, `oauth_codes`,
  `oauth_tokens`, `personal_access_tokens`, importiert nur `OAUTH_ERLAUBT`; `werkzeuge.py`
  importiert weder `oauth` noch `server`. **Begründete Ausnahme (0.56):** `durchlauf` schreibt
  im Savepoint und verwirft; `test_durchlauf_nur_ohne_speichern` verlangt bei jedem Aufruf aus
  dem Paket ausdrücklich `speichern=False`. Embeddings löst der Entwurfsmodus nicht aus.
- `tests/unit/test_entwurf_leserecht_waechter.py`: die Lesefunktionen stehen als lesend.
- `tests/unit/test_mcp_aus.py`: ab Werk aus.

## Tests

- `tests/integration/test_mcp_zugang.py` — Token-Prüfung gegen die echte Datenbank.
- `tests/integration/test_mcp_server.py` — ASGI-App: 401, `initialize`/`tools/list`, Host,
  Drossel, aus.
- `tests/integration/test_mcp_werkzeuge.py` — alle Werkzeuge über die App mit echtem Token in der
  Test-Transaktion (`einhaengen(…, sitzung=…)`); jede Antwort ohne Pseudonym.
- `tests/integration/test_oauth_modell.py`, `test_oauth_provider.py`, `test_oauth_http.py`,
  `test_oauth_zustimmung.py` — Modell, Provider ohne HTTP, der ganze Ablauf über HTTP wie bei
  Claude (Metadaten, Registrieren, Authorize, Zustimmung, Token, Werkzeug, Refresh, Diebstahl,
  Widerruf, falscher Verifier, abgelaufener Code, Drossel), die Zustimmungsrouten (Rollen,
  Vorschau, Zugangstoken gesperrt); `tests/unit/test_mcp_adressen.py`.

⚠️ **Der Session-Manager gehört nicht in eine async-Fixture.** Seine Task-Gruppe muss im selben
Task enden, in dem sie begann; pytest-asyncio räumt Fixtures in einem anderen auf
(`RuntimeError: Attempted to exit cancel scope in a different task`). Die Tests öffnen ihn
deshalb mit `async with` im Test selbst.

**Von Hand** (Dev): `MCP_AKTIV=true`, `MCP_OEFFENTLICHE_URL=http://localhost:8000/mcp` in der
`.env` (Backend neu starten, `--reload` liest die `.env` nicht neu). Mit OAuth — die
Zustimmungsseite kommt über `FRONTEND_ORIGIN` (`http://localhost:5173`):

```bash
claude mcp add --transport http dev http://localhost:8000/mcp      # dann /mcp → Authenticate
claude mcp add --transport http dev-token http://localhost:8000/mcp --header "Authorization: Bearer ggd_pat_…"
```
