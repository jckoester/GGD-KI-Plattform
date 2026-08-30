# Runbook: LiteLLM in die Compose der Anwendung übernehmen

**Wann:** einmalig, wenn eine bestehende Installation den Proxy bisher als eigenen
Compose-Stack führt.
**Dauer:** etwa 45 Minuten, davon die Hälfte Prüfen.
**Ausfall:** Der Chat steht still, solange der alte Proxy gestoppt und der neue nicht
abgenommen ist. Anmeldung, Historie und Verwaltung laufen weiter.
**Risiko:** mittel — der Datenbestand des Proxys muss **mitgenommen** werden. Was dabei
schiefgehen kann, fällt nicht beim Umzug auf, sondern danach.

> **Neuinstallation?** Dann ist hier nichts zu tun. `docker compose up -d` startet den
> Proxy mit, die zweite Datenbank legt `infra/db-init/` an. Weiter in
> [Installation](../admin/installation.md).

---

## Was auf dem Spiel steht

**Die LiteLLM-Datenbank enthält die Virtual Keys**, und die Anwendungsdatenbank verweist
mit `pseudonym_audit.litellm_key` auf sie. Eine leere neue Proxy-Datenbank heißt deshalb
nicht „fängt frisch an", sondern: **jede Chat-Anfrage scheitert mit 401**, für alle
Nutzer:innen gleichzeitig. Mitgenommen wird also der Datenbestand, nicht nur die
Konfiguration.

Dazu kommt der Verbrauch: Budgets, Wochenzuteilung und Kostenstatistik stehen in
derselben Datenbank. Sie neu aufzubauen hieße, das laufende Schuljahr abrechnungsseitig
zu verlieren.

Zwei Schlüssel müssen **unverändert** übernommen werden:

- **`LITELLM_MASTER_KEY`** — sonst passt keiner der bestehenden Virtual Keys.
- **`LITELLM_SALT_KEY`** — er verschlüsselt die in der Datenbank abgelegten
  Anbieter-Zugänge (`store_model_in_db`). ⚠️ **War er im alten Stack nie gesetzt, hat
  LiteLLM den Master-Key benutzt.** Dann gehört *dessen alter Wert* in `LITELLM_SALT_KEY`,
  bevor der neue Proxy startet — sonst sind über die Proxy-UI angelegte Modelle und
  Credentials nicht mehr entschlüsselbar.

---

## Zuerst: was ein unvorbereitetes `docker compose up -d` tut

Wer den neuen Stand auscheckt und startet, **bevor** die Schritte unten erledigt sind,
zerstört nichts — der neue Dienst schreibt in keine Datenbank der Anwendung. Aber drei
Dinge passieren, und alle drei sehen nach einem kaputten Deployment aus:

| Was fehlt | Was man sieht |
|---|---|
| `LITELLM_DATABASE_URL` in der `.env` der Anwendung (sie stand bisher in der `.env` des Proxy-Stacks) | `warning: The "LITELLM_DATABASE_URL" variable is not set. Defaulting to a blank string.` — und danach ein Proxy ohne Datenbank |
| `infra/litellm_config.yaml` (liegt bisher im alten Stack-Verzeichnis) | Docker legt an dieser Stelle ein **leeres Verzeichnis** an; der Container startet nicht |
| Datenbank `litellm` im `db`-Dienst | Neustartschleife, im Log ein Verbindungsfehler von Prisma |
| Freier Host-Port 4000 | Der alte Stack belegt ihn — der neue Dienst startet nicht |

Die Warnung zur fehlenden Variablen erscheint bei **jedem** `docker compose`-Befehl, auch
bei `ps` und `logs`. Sie ist folgenlos, solange der Dienst abgeschaltet ist.

Die laufende Anwendung bleibt in allen drei Fällen erreichbar; `backend` hat bewusst
**keine** Abhängigkeit auf den Proxy.

**Wer erst gefahrlos schauen will**, legt vor dem ersten Start eine
`docker-compose.override.yml` neben die `docker-compose.yml`:

```yaml
services:
  litellm:
    profiles: ["nicht-verwendet"]   # startet nicht mit `docker compose up`
```

Damit verhält sich der Stack wie bisher, der Proxy bleibt außen vor, und
`docker compose config` zeigt trotzdem, was ankommen würde. Zum Aktivieren später die
Datei löschen. Ein leeres Verzeichnis `infra/litellm_config.yaml`, das aus einem
verfrühten Start stammt, vorher entfernen — sonst schlägt der Mount weiter fehl.

---

## Ablauf

### 1. Bestand sichern

```bash
# Im ALTEN LiteLLM-Verzeichnis
docker compose exec db pg_dump -U postgres litellm > ~/litellm-$(date +%F).sql
wc -l ~/litellm-*.sql        # nicht leer?
```

Die `.env` und die `config.yaml` des alten Stacks ebenfalls beiseitelegen — aus ihnen
kommen gleich die Werte.

### 2. Alten Proxy stoppen

```bash
# Im ALTEN LiteLLM-Verzeichnis
docker compose stop litellm
```

Ab hier ist der Chat aus. Der Dump aus Schritt 1 ist erst jetzt wirklich konsistent —
wer eine lange Pause vermeiden will, wiederholt ihn nach dem Stoppen; er dauert Sekunden.

**Den Stack noch nicht abbauen.** `docker compose down -v` würde das Volume löschen; das
bleibt, bis die Abnahme durch ist.

### 3. Neuen Stand auschecken

```bash
# Im ANWENDUNGS-Verzeichnis
git pull
```

### 4. Datenbank anlegen

Das Init-Verzeichnis greift nur bei leerem Datenverzeichnis — auf einer bestehenden
Installation also nicht:

```bash
docker compose exec db psql -U postgres -c "CREATE DATABASE litellm"
```

### 5. Bestand einspielen

```bash
docker compose exec -T db psql -U postgres -d litellm < ~/litellm-JJJJ-MM-TT.sql
```

Geprüft wird **nicht durch Zählen**, sondern durch Abgleich: Jedes Konto, auf das die
Anwendung verweist, muss im Proxy einen Schlüssel besitzen.

```bash
# Die Pseudonyme mit Schlüssel aus der Anwendungs-DB:
docker compose exec db psql -U postgres -d ggd_ki -At \
  -c "SELECT pseudonym FROM pseudonym_audit WHERE litellm_key IS NOT NULL"

# Diese Pseudonyme müssen im Proxy als Token-Besitzer auftauchen — alle:
docker compose exec db psql -U postgres -d litellm -c "
  SELECT user_id, count(*) AS schluessel, bool_or(coalesce(blocked,false)) AS gesperrt
    FROM \"LiteLLM_VerificationToken\"
   WHERE user_id IN ('<pseudonym1>','<pseudonym2>', …)
   GROUP BY user_id"
```

> **Warum nicht einfach Zeilen zählen?** Die Zahlen stimmen normalerweise **nicht**
> überein, und das ist in Ordnung:
>
> - **Mehrere Schlüssel je Person sind der Normalfall.** Bis 08/2026 legte `POST /user/new`
>   zusätzlich zum eigens erzeugten Schlüssel einen weiteren an (`auto_create_key`
>   war standardmäßig aktiv). Auf einer Bestandsinstallation stehen deshalb leicht
>   doppelt so viele Tokens wie Konten. Neu angelegte Konten bekommen nur noch einen.
> - **`proxy_admin` und Team-Schlüssel** haben ohnehin kein Gegenstück in der Anwendung.
>
> Aussagekräftig ist allein die **Gegenrichtung**: Fehlt ein Pseudonym aus der ersten
> Abfrage in der zweiten, scheitert für diese Person jede Anfrage mit `401`. Dann hier
> anhalten und die Ursache klären — nicht weitermachen und hoffen.

### 6. `.env` zusammenführen

Aus der alten Proxy-`.env` in die `.env` der Anwendung:

| Variable | Wert |
|---|---|
| `LITELLM_MASTER_KEY` | **unverändert** übernehmen |
| `LITELLM_SALT_KEY` | unverändert übernehmen; stand dort nichts → alten Master-Key eintragen |
| Anbieter-Schlüssel (`OPENAI_API_KEY`, `IONOS_API_KEY` …) | übernehmen, soweit nicht schon vorhanden |
| `UI_USERNAME` / `UI_PASSWORD` | übernehmen |
| `LITELLM_DATABASE_URL` | neu bilden — Passwort **der Anwendungs-Postgres**, s. u. |
| `LITELLM_PROXY_URL` | auf `http://litellm:4000` ändern |
| `LITELLM_PORT` | `4000`, falls der Port auf dem Host frei ist |

> ⚠️ **`LITELLM_PROXY_URL` nicht auf `localhost` stehen lassen.** Im Container ist das
> das Backend selbst. Der Chat scheitert dann mit „Connection refused", während alles
> andere normal aussieht.

> ⚠️ **Bei `LITELLM_DATABASE_URL` nicht nur Host und Datenbank ändern.** Der Proxy spricht
> jetzt die Postgres der **Anwendung** an, nicht mehr seine eigene — das Passwort ist also
> ein anderes. Es ist dasselbe wie in `DATABASE_URL`:
>
> ```
> postgresql://postgres:<Passwort aus DATABASE_URL>@db:5432/litellm
> ```
>
> Bleibt das alte stehen, startet der Proxy nicht:
>
> ```
> Error: P1000: Authentication failed against database server at `db`,
> the provided database credentials for `postgres` are not valid.
> ```
>
> Zum Vergleichen, ohne das Passwort auszugeben — zwei gleiche Kurz-Hashes heißt gleiches
> Passwort:
>
> ```bash
> grep -E '^(DATABASE_URL|LITELLM_DATABASE_URL)=' .env |
>   sed -E 's#.*://[^:]+:([^@]*)@.*#\1#' |
>   while read -r p; do printf '%s' "$p" | sha256sum | cut -c1-12; done
> ```
>
> Stimmen sie überein und es scheitert trotzdem, ist es die **Kodierung**: Enthält das
> Passwort `/`, `+`, `@`, `:`, `#`, `?` oder `%`, muss es prozent-kodiert werden — `/`
> beendet sonst den Adressteil. Das trifft besonders Passwörter aus
> `openssl rand -base64 32`, das genau `/` und `+` erzeugt.
>
> **Warum das erst hier auffällt:** Aufrufe wie `docker compose exec db psql -U postgres`
> laufen über den lokalen Socket und prüfen **kein** Passwort. Benutzt wird es erst, wenn
> sich ein anderer Container über TCP verbindet — also genau jetzt.

### 7. Config an ihren Platz

```bash
cp <alter-stack>/config.yaml infra/litellm_config.yaml
```

Darin prüfen:

- `health_file: "/app/data/guardrail_health.json"` — ein Host-Pfad aus der Zeit des
  getrennten Stacks (`/srv/…`) gehört jetzt ersetzt.
- `general_settings.database_url: os.environ/LITELLM_DATABASE_URL`
- `store_model_in_db: true`
- Guardrail-Modulpfad `guardrails.llm_moderation.LlmModerationGuardrail` — unverändert
  richtig, der Dienst hängt `infra/guardrails` passend ein.

### 8. Starten

```bash
docker compose up -d
docker compose ps          # litellm muss `healthy` werden (bis zu 60 s beim ersten Start)
docker compose logs -f litellm
```

### 9. Abnahme

In dieser Reihenfolge — jede Stufe deckt etwas ab, das die vorige nicht sieht:

```bash
# 1. Der Proxy antwortet — und zwar auf dem Weg, den die Anwendung geht
#    (aus dem backend-Container heraus; das LiteLLM-Image hat kein curl)
docker compose exec backend curl -s http://litellm:4000/health/readiness

# 2. Modelle, Preise, Fähigkeiten stimmen mit der .env überein
docker compose exec backend python scripts/check_litellm_config.py
```

3. **Eine Chat-Antwort erzeugen** und im Log der Anwendung nachsehen:
   `Kosten des Zuges: n von n Anfragen abgerechnet` mit einer Summe **größer als 0**.
   Steht dort 0, greifen weder Budgets noch Statistik.
4. **Budget einer Bestandsnutzerin** auf `/budget` prüfen: Der bisherige Verbrauch muss
   noch da sein. Steht er bei null, ist der Bestand aus Schritt 5 nicht angekommen.
5. **`/settings/guardrail`** zeigt einen frischen Bericht (nicht „kein Bericht"). Damit
   ist bewiesen, dass Proxy und Backend dieselbe Datei sehen.

### 10. Aufräumen — später

Erst wenn ein paar Tage Betrieb ohne Auffälligkeiten vergangen sind:

```bash
# Im ALTEN LiteLLM-Verzeichnis
docker compose down          # OHNE -v
```

Das Volume und der Dump bleiben bis mindestens zur nächsten Budgetabrechnung liegen.

---

## Wenn der Proxy nicht startet

| Meldung im Log | Ursache | Behebung |
|---|---|---|
| `P1000: Authentication failed against database server at 'db'` | `LITELLM_DATABASE_URL` trägt noch das Passwort der **alten** Proxy-Datenbank, oder ein Sonderzeichen ist nicht prozent-kodiert | Schritt 6 |
| `httpx.ConnectError: All connection attempts failed` **oberhalb** eines `P1000` | **Folgefehler, keine Ursache.** Die Prisma-Query-Engine kommt ohne Anmeldung nicht hoch, der Proxy findet sie dann nicht | Das `P1000` weiter unten im Log behandeln, nicht das Netz |
| Verbindungsfehler, Datenbank `litellm` unbekannt | Die zweite Datenbank fehlt — das Init-Verzeichnis greift nur bei leerem Datenverzeichnis | Schritt 4 |
| `--config`-Datei ist ein Verzeichnis | `infra/litellm_config.yaml` fehlte beim Start; Docker legt für ein fehlendes Mount-Ziel ein leeres Verzeichnis an | Verzeichnis löschen, Datei anlegen (Schritt 7), neu starten |
| `Prisma doesn't know which engines to download for the Linux distro "wolfi"` | **Nur eine Warnung.** wolfi ist glibc-basiert, die Debian-Engines laufen dort | Ignorieren |

## Wenn die Proxy-Datenbank doch verloren ist

Notlösung, keine Migration — der **bisherige Verbrauch ist damit weg**, alle Budgets
stehen wieder bei null:

```bash
docker compose exec db psql -U postgres -d ggd_ki \
  -c "UPDATE pseudonym_audit SET litellm_key = NULL"
docker compose exec backend python scripts/create_litellm_teams.py
docker compose exec backend python scripts/migrate_litellm_keys.py
```

`migrate_litellm_keys.py` legt für alle Nutzer:innen ohne Schlüssel neue an. Die Teams
müssen vorher existieren, sonst hängen die Schlüssel an keiner Freigabe. Danach unter
`/settings/models` prüfen, ob die Modell-Matrix noch besetzt ist.

---

## Beim getrennten Stack bleiben

Bleibt eine unterstützte Variante. Dann:

- `LITELLM_PROXY_URL` auf die Adresse des eigenen Proxys setzen,
- den mitgelieferten Dienst über die `docker-compose.override.yml` aus dem Abschnitt
  *Zuerst* abschalten,
- und für den Guardrail-Zählerstand weiterhin beide Seiten auf dasselbe
  **Host**-Verzeichnis mounten — siehe
  [Content-Moderation](../admin/content-moderation.md#wo-die-datei-liegen-muss).
</content>
</invoke>
