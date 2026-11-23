# MCP-Server für KI-Abos (seit 0.54)

Päckchen AW. Ein lesender MCP-Server im Backend (`app/mcp/`), über den ein KI-Programm mit dem
Zugangstoken einer Lehrkraft Curricula, Bildungspläne und Leitlinien liest. In AX (0.55) kommt
die Anmeldung per OAuth dazu; am Server selbst ändert sie nichts, er prüft weiter ein
Bearer-Token mit dem Scope `curriculum:read`.

Bibliothek: das offizielle Python-SDK `mcp` 2.3 (eng gepinnt, `<2.4`). ⚠️ 2.x hat die API
gegenüber 1.x umbenannt (`FastMCP` → `MCPServer`); Beispiele im Netz sind oft 1.x.

## Aufbau

| Datei | Was |
|---|---|
| `app/mcp/auth.py` | `ZugangstokenPruefer` (`TokenVerifier` des SDK) über `tokens.pruefe`, Scope Pflicht; `principal()` macht im Werkzeug ein `JwtPayload` daraus (ohne Vorschau) |
| `app/mcp/server.py` | `baue_server`, `transportschutz`, Drossel-Hülle `_Gedrosselt`, `einhaengen`, `lebenszyklus` |
| `app/mcp/werkzeuge.py` | die sieben Werkzeuge und ihre Lesefunktionen `lies_…(db, user, …)` |

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
3. Anmeldung: Middleware des SDK mit `ZugangstokenPruefer`; ohne gültiges Token `401` mit
   `WWW-Authenticate: Bearer`. `AuthSettings(resource_server_url=None)`: In AW veröffentlicht
   der Server keine OAuth-Metadaten.
4. Rechte: Die Lesefunktionen lesen mit `principal()` — dieselben Prüfungen wie die GET-Routen
   (`_lesbares_curriculum`, `darf_entwurf_lesen`, `eigenes_zaehlt`).

`curriculum:read` steht **nicht** in `app.auth.scopes._ZUSTAENDIG` und öffnet deshalb keinen
REST-Weg. `test_token_scopes.py` kennt den MCP-Server als zweite Stelle, die einen Scope
verlangt. Im Profil bietet `/tokens/scopes` den Scope nur an, wenn die Schnittstelle an ist,
mit `hinweis`, `adresse` und `hilfe`.

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
- `tests/unit/test_entwurf_leserecht_waechter.py`: die Lesefunktionen stehen als lesend.
- `tests/unit/test_mcp_aus.py`: ab Werk aus.

## Tests

- `tests/integration/test_mcp_zugang.py` — Token-Prüfung gegen die echte Datenbank.
- `tests/integration/test_mcp_server.py` — ASGI-App: 401, `initialize`/`tools/list`, Host,
  Drossel, aus.
- `tests/integration/test_mcp_werkzeuge.py` — alle Werkzeuge über die App mit echtem Token in der
  Test-Transaktion (`einhaengen(…, sitzung=…)`); jede Antwort ohne Pseudonym.

⚠️ **Der Session-Manager gehört nicht in eine async-Fixture.** Seine Task-Gruppe muss im selben
Task enden, in dem sie begann; pytest-asyncio räumt Fixtures in einem anderen auf
(`RuntimeError: Attempted to exit cancel scope in a different task`). Die Tests öffnen ihn
deshalb mit `async with` im Test selbst.

**Von Hand** (Dev, mit Token aus dem Profil):

```bash
MCP_AKTIV=true MCP_OEFFENTLICHE_URL=http://localhost:8000/mcp uvicorn app.main:app --reload
claude mcp add --transport http dev http://localhost:8000/mcp --header "Authorization: Bearer ggd_pat_…"
```
