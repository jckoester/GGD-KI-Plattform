# Schnittstelle für KI-Abos (MCP)

Seit 0.54 kann die Plattform Curricula, Bildungspläne und Leitlinien an ein KI-Programm
liefern, das die Schule abonniert hat, etwa Claude. Lehrkräfte fragen dann dort: „Wo kommt
BNE in unseren Curricula vor?“, „Vergleiche die Curricula Klasse 7 in Mathematik und
Physik.“ Technisch ist das ein **MCP-Server** (Model Context Protocol) im Backend.

Seit 0.55 ist die Plattform dafür auch ein kleiner **OAuth-Autorisierungsserver**. Erst damit
verbinden sich Claude im Browser, in der Desktop-App und auf dem Handy, ChatGPT und Microsoft
365 Copilot: Sie melden Personen nur per OAuth an. Claude Code geht zusätzlich mit einem
Zugangstoken.

Ab Werk ist die Schnittstelle **aus**. Sie einzuschalten ist eine Entscheidung der Schule:
Was das Programm liest, geht an dessen Anbieter.

## Was die Schnittstelle kann

- **Nur lesen.** Neun Werkzeuge: Leitlinien, Leitperspektiven, die Übersicht einer Leitlinie
  oder Leitperspektive, Curricula finden, ein Curriculum lesen, seine Abdeckung, die
  Kompetenzen des Bildungsplans; seit 0.56 ein Curriculum als YAML und die Prüfung eines
  YAML-Entwurfs. Schreiben ist nicht möglich; ein Test im Code hält das so.
- **Entwürfe nur über die Lehrkraft.** Ein Programm kann ein Curriculum als YAML entwerfen und
  prüfen — die Prüfung ist der echte Import, der danach verworfen wird. Anlegen kann es nichts:
  Die Lehrkraft lädt die Datei in der Plattform hoch (**Aus YAML importieren**), sieht eine
  Vorschau, und es entsteht ein Entwurf, den die Fachschaft veröffentlicht.
- **Mit den Rechten der Lehrkraft.** Gelesen wird, was die Person auch im Browser sieht —
  veröffentlichte Curricula und Entwürfe, eigene private, keine fremden privaten.
- **Ohne Personen.** Die Antworten enthalten keine Pseudonyme und keine Namen. Chats,
  Unterrichtsplanung, Budgets und Verwaltung sind nicht erreichbar.
- **Nur für Lehrkräfte und Admins**, nicht in der Vorschau. Angemeldet per OAuth (Zustimmung
  auf einer Seite der Plattform) oder mit einem persönlichen Zugangstoken mit der Berechtigung
  `curriculum:read`. Diese Berechtigung öffnet sonst keinen Weg in die Plattform.

## Einschalten

In der `.env`:

```bash
MCP_AKTIV=true
MCP_OEFFENTLICHE_URL=https://ki.ihre-schule.de/api/mcp
FRONTEND_ORIGIN=https://ki.ihre-schule.de
```

- `MCP_OEFFENTLICHE_URL` ist die Adresse, wie die Programme sie aufrufen: **`https://`**,
  **mit** `/api` und **mit `/mcp` am Ende**. Aus ihr leitet der Server ab:
  - den OAuth-Issuer: die Adresse ohne `/mcp`, also `https://ki.ihre-schule.de/api`. Die
    Endpunkte `/api/authorize`, `/api/token`, `/api/register` und `/api/revoke` laufen damit
    durch dieselbe Proxy-Regel wie die übrige API;
  - die erlaubten Host- und Origin-Werte. Anfragen mit einem anderen Host-Kopf weist er ab
    (Schutz vor DNS-Rebinding).

  Fehlt die Adresse oder passt sie nicht (seit 0.55.1 auch: ohne `/api`), bleibt die
  Schnittstelle trotz `MCP_AKTIV=true` aus, und das Log des Backends meldet einen Fehler. Ob
  sie läuft, zeigt das Log beim Start:

  ```bash
  docker compose logs backend | grep -i "KI-Abos"
  ```

  Richtig ist `Schnittstelle für KI-Abos (MCP) unter https://…/api/mcp, OAuth-Issuer
  https://…/api`.
- `FRONTEND_ORIGIN` (gibt es schon, für CORS) bestimmt die Adresse der Zustimmungsseite
  `/oauth/consent`. Sie muss die öffentliche Adresse sein.
- Ein neues Geheimnis braucht es nicht: Die OAuth-Anfrage zwischen Programm und
  Zustimmungsseite ist mit `JWT_SECRET` signiert.

Danach den Container des Backends neu erzeugen, damit er die geänderte `.env` liest:

```bash
docker compose up -d --force-recreate backend
```

Im Profil erscheint die Berechtigung „Curricula, Bildungspläne und Leitlinien lesen — für
KI-Programme“ mit der Adresse erst, wenn die Schnittstelle eingeschaltet ist.

## Reverse Proxy

Zwei Pfadgruppen müssen das Backend erreichen:

| Öffentlich | Backend | Zweck |
|---|---|---|
| `/api/mcp`, `/api/authorize`, `/api/token`, `/api/register`, `/api/revoke`, `/api/oauth/…` | ohne `/api` | MCP-Server, OAuth-Endpunkte, Zustimmung |
| `/.well-known/oauth-protected-resource/api/mcp`, `/.well-known/oauth-authorization-server/api` | **unverändert** | Metadaten nach RFC 9728 und RFC 8414 |

Die Metadaten **müssen an der Wurzel der Domain** liegen; die Programme fragen genau dort.
Ohne sie findet Claude keine Anmeldung.

**Der mitgelieferte nginx** (`infra/nginx.conf.template`) leitet beides seit 0.55 weiter:
`location /api/` wie bisher, dazu `location ^~ /.well-known/oauth-` ungekürzt ans Backend.
Andere `/.well-known/`-Pfade (etwa `acme-challenge`) bleiben unberührt. Wer die Vorlage
angepasst hat, übernimmt den neuen Block. Nach einer Änderung `docker compose restart nginx`:
Die Vorlage ist eingehängt, `up -d` startet den Dienst dafür nicht neu.

**Ein Proxy vor dem Stack** (etwa ein eigener nginx, der TLS macht und auf den nginx der
Compose weiterleitet) muss:

1. `/api/…` **und** `/.well-known/oauth-…` an den Stack weiterreichen — **unverändert**, ohne
   `/api` abzuschneiden; das tut der nginx im Stack;
2. den `Host`-Kopf weitergeben (Host-Prüfung von `/mcp`, `ALLOWED_HOSTS`);
3. den Kopf `Authorization` stehen lassen;
4. Formular-Bodies (`application/x-www-form-urlencoded`) an `/api/token` durchlassen.

Außerdem gehört seine Adresse in `TRUSTED_PROXIES`. Sonst sieht das Backend alle Anfragen von
derselben IP, und die Drossel der OAuth-Endpunkte (je IP) bremst alle gemeinsam.

**Erreichbarkeit:** Claude ruft den Server von Anthropics Servern aus auf, nicht vom Gerät der
Lehrkraft — auch die Metadaten und `/api/token`. Wer den Zugang auf Adressbereiche beschränkt,
gibt den Bereich frei, den Anthropic dafür veröffentlicht (Stand 11/2026: `160.79.104.0/21`).
Die Zustimmungsseite öffnet dagegen der Browser der Lehrkraft, und Claude Code ruft vom Gerät
der Lehrkraft aus auf.

## Prüfen

Nach dem Einschalten, **von außen** (also durch alle Proxys):

```bash
# 1. Metadaten der Ressource: JSON mit "resource" = MCP_OEFFENTLICHE_URL
curl -s https://ki.ihre-schule.de/.well-known/oauth-protected-resource/api/mcp

# 2. Metadaten des Autorisierungsservers: JSON mit "issuer" = https://ki.ihre-schule.de/api
curl -s https://ki.ihre-schule.de/.well-known/oauth-authorization-server/api

# 3. Ohne Token: 401, im Kopf WWW-Authenticate mit resource_metadata="…" (die Adresse aus 1.)
curl -s -D - -o /dev/null -X POST https://ki.ihre-schule.de/api/mcp \
  -H "content-type: application/json" -d '{}'
```

| Ergebnis | Bedeutung |
|---|---|
| 1. oder 2. liefert HTML | Ein Proxy schickt `/.well-known/oauth-…` an das Frontend. |
| 1., 2. oder 3. liefert `{"detail":"Not Found"}` | Die Anfrage erreicht das Backend, die Route fehlt dort: Die Schnittstelle ist aus (Logzeile oben prüfen), oder ein Proxy reicht `/api/…` am nginx des Stacks vorbei direkt ans Backend. |
| 1. oder 2. liefert eine andere `404` | Ein Proxy schneidet den Pfad oder kennt ihn nicht. |
| 3. liefert eine andere `404` | `/api/mcp` kommt nicht am Stack an. |
| 3. liefert `421` oder `400` | Der `Host`-Kopf passt nicht zu `MCP_OEFFENTLICHE_URL`. |

Danach einmal mit einem echten Programm verbinden (Claude Code: `claude mcp add --transport
http schule <Adresse>`, dann `/mcp` → *Authenticate*; Claude: siehe unten). Die Verbindung muss
im Profil unter „Verbundene Programme“ erscheinen.

## Konnektor in Claude anlegen

Bei einem Abo für die Organisation (Team, Enterprise) legt ein Owner den Konnektor einmal für
alle an; die Lehrkräfte verbinden sich danach selbst. Bei Einzelabos (Pro, Max) legt ihn jede
Lehrkraft selbst an — die Schritte stehen in der Hilfe unter Profil → „KI-Programme verbinden“
(`/help/profil#ki-programme-verbinden`); den Link können Sie weitergeben.

1. In Claude *Organization settings → Connectors* → *Add* → *Custom* → *Web*.
2. Name, etwa „Schulplattform“, und die Adresse aus `MCP_OEFFENTLICHE_URL`. *Continue*.
3. Die erkannten Einstellungen prüfen:
   - **Authentication:** *Sign in when needed* (oder *Sign in now*).
   - **OAuth client: *Register automatically*.** Nicht die Voreinstellung *Use Claude's
     published identity*: Die Plattform kennt nur die automatische Registrierung, mit der
     Voreinstellung scheitert die Anmeldung.
   - **Request headers:** leer lassen.
4. *Add*.

Die Lehrkräfte finden den Konnektor dann in Claude unter *Customize → Connectors* (mit dem
Etikett „Custom“) und klicken *Connect*. Die Bezeichnungen der Oberfläche sind die von Claude,
Stand 11/2026; sie können sich ändern.

## Verbindungen einsehen

Jede Lehrkraft sieht und beendet ihre Verbindungen im Profil. Wie viele es schulweit gibt:

```sql
SELECT name, count(*) FROM personal_access_tokens
WHERE oauth_client_id IS NOT NULL AND revoked_at IS NULL AND expires_at > now()
GROUP BY name;
```

Eine Verbindung gilt 90 Tage ab der Zustimmung, dann verbindet die Lehrkraft neu. Ein
Zugriffstoken gilt eine Stunde; das Programm erneuert es selbst (Refresh mit Rotation). Kommt
ein schon eingelöster Refresh-Token noch einmal, endet die Verbindung — er gilt als gestohlen.

## Drossel und Aufräumen

- `/api/mcp`: je Token höchstens 60 Nachrichten in der Minute (Eimer `mcp`).
- `/api/register`, `/api/token`, `/api/revoke`: je IP höchstens 30 in der Minute (Eimer
  `oauth`). Registrieren kann jedes Programm, ohne Anmeldung — das ist Standard und Claude
  braucht es. Einen Zugang bekommt ein Programm erst mit Zustimmung einer Lehrkraft.
- Danach `429` mit `Retry-After`. Einstellbar in `config/rate_limits.yaml`.
- Der Cron-Lauf `cleanup_oauth` (täglich 04:20) löscht Registrierungen, die 30 Tage nie benutzt
  wurden, abgelaufene Codes und Token und eingelöste Refresh-Token nach 7 Tagen.

## Datenschutz

Die Schnittstelle liefert Curricula, Bildungspläne und Leitlinien, keine personenbezogenen
Daten aus der Plattform. In den Freitexten eines Curriculums kann trotzdem etwas stehen, das
nicht hinausgehen soll. Ob und mit welchem Anbieter die Schule das nutzt, entscheidet sie;
dazu gehört ein Vertrag zur Auftragsverarbeitung mit dem Anbieter des Abos und ein Eintrag im
Verarbeitungsverzeichnis.

Gespeichert werden je Verbindung Programm, Pseudonym, Zeitpunkte und die Token als Hash. Mit
dem Konto (90 Tage ohne Anmeldung) gehen auch seine Verbindungen und offenen Codes.

## Abschalten

`MCP_AKTIV=false` und das Backend neu starten. Die Routen verschwinden (`404`); vorhandene
Verbindungen und Token bleiben gespeichert, führen aber nirgends hin. Einzelne Verbindungen
beendet die Lehrkraft im Profil.
