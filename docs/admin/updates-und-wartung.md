# Updates & Wartung

## Reguläres Update

```bash
git pull
docker compose build --no-cache
docker compose up -d
docker compose exec backend alembic upgrade head
```

> **Nur die Konfiguration geändert?** Dann ist `up -d` der **falsche** Befehl: Der Inhalt
> einer eingehängten Datei ist für Compose unsichtbar, der Container wird nicht neu
> erzeugt, und die Änderung bleibt wirkungslos — ohne Fehlermeldung. Welcher Befehl wofür
> gilt (und die beiden Ausnahmen, die sofort wirken), steht in
> [Konfigurationsdateien → Wann Änderungen wirken](konfiguration.md#wann-änderungen-wirken).

`alembic upgrade head` ist immer auszuführen — er ist idempotent und schadet
nicht, wenn keine neuen Migrationen vorliegen.

Nach dem Update die Plattform kurz im Browser prüfen und die Logs beobachten:

```bash
docker compose logs -f backend
```

Läuft alles, kann anschließend der Platz der überholten Images freigegeben werden — jedes
Update hinterlässt welche.

## Speicherplatz freigeben

Jedes `docker compose build --no-cache` schreibt vollständig neue Image-Schichten. Das
bisherige Image verschwindet dabei nicht — es verliert nur seinen Namen und bleibt als
`<none>` liegen. Dazu legt der Build-Vorgang einen eigenen Zwischenspeicher an; `--no-cache`
verhindert nur, dass er *gelesen* wird, nicht dass er *wächst*. Nach einigen Updates
summiert sich das auf mehrere Gigabyte.

Erst nachsehen, wo der Platz liegt:

```bash
docker system df
```

Die Spalte `RECLAIMABLE` zeigt je Kategorie (Images, Containers, Local Volumes, Build
Cache), wie viel davon freigegeben werden kann.

**Aufräumen — beides fasst nur an, was nichts mehr braucht:**

```bash
# 1. Überholte Images (Tag <none>) — die Vorgänger der aktuellen Builds
docker image prune -f

# 2. Build-Zwischenspeicher — nach --no-cache-Builds meist der größte Posten
docker builder prune -f
```

Laufende Container behalten ihr Image; die Plattform muss dafür nicht angehalten werden.

> **Erst prüfen, dann aufräumen.** Das vorherige Image ist der schnellste Weg zurück, falls
> ein Update Probleme macht. Deshalb gehört dieser Schritt ans **Ende** des Updates — nach
> dem Blick in Browser und Logs, nicht davor.

Reicht das nicht, lässt sich auch der noch verwendbare Build-Cache verwerfen. Der nächste
Build dauert dann länger, ist aber unverändert korrekt:

```bash
docker builder prune -af
```

Wer regelmäßig aufräumt, aber die letzten Tage behalten will:

```bash
docker builder prune -f --filter until=168h   # alles älter als 7 Tage
```

### Was auf keinen Fall

| Befehl | Wirkung |
|---|---|
| `docker volume prune` | Löscht das Volume `postgres_data` — **die gesamte Datenbank**: Konten, Konversationen, Budgets, Bildungsplan. |
| `docker system prune --volumes` | Dasselbe, zusätzlich zum übrigen Aufräumen. Das `--volumes` ist der gefährliche Teil. |
| `docker image prune -a` bei angehaltener Plattform | Entfernt auch die aktuell benötigten Images, weil ohne laufende Container nichts sie beansprucht. Keine Daten verloren, aber ein vollständiger Neubau nötig. |

Ohne `--volumes` bzw. `docker volume prune` sind Datenbank und `./data` (generierte Bilder,
Artefakte, Export-Vorlagen) nicht in Gefahr — `./data` ist ohnehin ein Verzeichnis des
Servers, kein Docker-Volume. Vor größeren Aufräumaktionen trotzdem sicherheitshalber ein
[Datenbank-Backup](#datenbank-backup) ziehen.

### Container-Logs

Neben den Builds wachsen die Logdateien der Container unbegrenzt — sie stehen nicht in
`docker system df`. Prüfen und begrenzen:

```bash
sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail -5
```

Dauerhaft begrenzen lässt sich das je Dienst in `docker-compose.yml`:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Die Begrenzung greift erst für **neu erzeugte** Container, also nach dem nächsten
`docker compose up -d`.

## Fächer ändern (`subjects.yaml`)

`config/subjects.yaml` ist die einzige Quelle der Wahrheit für die Fächerliste.
Nach **jeder** Änderung (neues Fach, geänderter `fach_code`, Umbenennung, Entfernung)
die `subjects`-Tabelle neu seeden:

```bash
# Vorschau: zeigt an, welche Fächer eingefügt/aktualisiert/verwaist sind (löscht nichts)
docker compose exec backend python scripts/seed_subjects.py
```

Das Skript ist ein **Upsert** über den Slug und legt keine Duplikate an. Es **löscht
standardmäßig nichts** — Fächer, die nicht mehr in der YAML stehen (z. B. nach einer
Umbenennung „Kunst" → „Bildende Kunst" oder Aufspaltung von „Religion" in Ev./Kath./Isl.),
bleiben als **verwaiste Zeilen** in der DB und werden nur als Warnung gemeldet.

Verwaiste Zeilen sind nicht harmlos: Sie erscheinen weiter im Fach-Dropdown, und wenn
der Bildungsplan unter der *neuen* Fach-`id` importiert wurde, zeigt die alte Zeile
einen **leeren Bildungsplan**. Zum Entfernen:

```bash
# entfernt verwaiste Fächer — aber NUR unreferenzierte
docker compose exec backend python scripts/seed_subjects.py --prune
```

`--prune` löscht ein verwaistes Fach nur, wenn es von **keiner** Konversation, Gruppe,
keinem Assistenten usw. mehr referenziert wird. Referenzierte Fächer werden nie gelöscht,
sondern mit Referenzzählung gemeldet — dann muss erst die Referenz umgehängt werden,
bevor die alte Zeile entfernt werden kann.

## Proxy-UI und Proxy-API erreichen

Der Port des LiteLLM-Proxys ist **nur an `127.0.0.1` gebunden** (`docker-compose.yml`).
Das ist Absicht: Wer die Proxy-UI erreicht, verwaltet mit dem Master-Key Schlüssel und
Budgets der ganzen Schule. Vom Netz aus ist sie deshalb nicht erreichbar — auch nicht aus
dem Schulnetz.

> **`LITELLM_PORT` ändert nur den Port, nicht die Bindung.** Ein anderer Wert verschiebt
> `127.0.0.1:4000` auf `127.0.0.1:<Port>`; öffentlich wird dadurch nichts.

### Im Alltag genügt die eigene Verwaltung

Vorher prüfen, ob es die Proxy-UI überhaupt braucht — das meiste steht in der Plattform
selbst:

| Aufgabe | Ort |
|---|---|
| Modelle je Nutzergruppe freischalten | `/settings/models` |
| Verbrauch und Budgets | `/budget` |
| Kosten- und Nutzungsstatistik | `/statistics` |
| Zustand des Jugendschutz-Guardrails | `/settings/guardrail` |

Modelle selbst kommen aus `infra/litellm_config.yaml`, nicht aus der Proxy-UI. Es bleiben
Sonderfälle: einen Schlüssel nachsehen, eine Team-Zuordnung prüfen, eine Buchung
nachvollziehen.

### Ohne UI: die Management-API

Aus dem `backend`-Container — er bringt `curl` mit und hat den Master-Key in der Umgebung.
Für ein headless System der bequemere Weg, weil kein Tunnel nötig ist:

```bash
# Modelle, die der Proxy führt (mit Preisen und Fähigkeiten):
docker compose exec backend sh -c \
  'curl -s $LITELLM_PROXY_URL/model/info -H "Authorization: Bearer $LITELLM_MASTER_KEY"'

# Eine Nutzerin samt Budget und Verbrauch (user_id = Pseudonym):
docker compose exec backend sh -c \
  'curl -s "$LITELLM_PROXY_URL/user/info?user_id=<pseudonym>" \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY"'

# Team-Zuordnung und Modell-Allowlist:
docker compose exec backend sh -c \
  'curl -s "$LITELLM_PROXY_URL/team/info?team_id=lehrkraefte" \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY"'

# Buchungen:
docker compose exec backend sh -c \
  'curl -s "$LITELLM_PROXY_URL/spend/logs" -H "Authorization: Bearer $LITELLM_MASTER_KEY"'
```

Ebenfalls verfügbar: `/key/info`, `/key/list`, `/global/spend/keys`.

> Das LiteLLM-Image bringt **kein `curl`** mit (es baut auf wolfi-base) — solche Aufrufe
> gehören deshalb in den `backend`-Container. Der prüft nebenbei den Weg, den die
> Anwendung tatsächlich geht.

### Mit UI: SSH-Tunnel

Der Tunnel läuft auf der Maschine, die **den Browser hat** — nicht auf dem Server:

```bash
# auf dem Arbeitsplatzrechner:
ssh -N -L 4000:127.0.0.1:4000 <nutzer>@<server>
# solange das läuft, dort im Browser: http://localhost:4000/ui
```

Der Server braucht dafür weder Browser noch grafische Oberfläche — genau dafür ist ein
Tunnel da. Führt der Weg über einen Sprungserver: zusätzlich `-J <sprungserver>`.

Ist der Server von außen nicht per SSH erreichbar und nur über einen Fernwartungs-PC im
Schulnetz, läuft der Tunnel **auf diesem PC** und der Browser ebenfalls dort.

Anmeldung mit `UI_USERNAME` / `UI_PASSWORD` aus der `.env`; ohne diese Variablen ist es
`admin` plus `LITELLM_MASTER_KEY`.

### Bewusste Freigabe im Netz

Wer die UI dauerhaft im Schulnetz erreichbar machen will, legt eine
`docker-compose.override.yml` neben die `docker-compose.yml`:

```yaml
services:
  litellm:
    ports:
      - "4000:4000"      # statt 127.0.0.1:4000
```

⚠️ Damit erreicht jedes Gerät im Netz eine Oberfläche, hinter der Schlüssel, Budgets und
Anbieter-Zugänge liegen. Nur mit vorgelagerter Zugangskontrolle, und nie ins offene
Internet.

## LiteLLM updaten

Der Proxy ist ein Dienst **derselben** Compose (`litellm`); alle Befehle laufen im
Anwendungsverzeichnis.

Die Version steht an zwei Stellen, und beide gehören zusammen geändert:

| Stelle | Wofür |
|---|---|
| `image:` am Dienst `litellm` in `docker-compose.yml` | Produktion |
| `litellm[proxy]==…` in `infra/litellm-requirements.txt` | der lokale Dev-Proxy |

Ein Unit-Test (`test_compose_litellm.py`) hält beide gegeneinander — wer nur eine ändert,
merkt es beim nächsten Testlauf statt erst im Betrieb.

```bash
# 1. Version in docker-compose.yml und infra/litellm-requirements.txt anheben
# 2. Neues Image ziehen und starten
docker compose pull litellm
docker compose up -d litellm

# 3. Warten, bis der Proxy wieder gesund ist
docker compose ps litellm
```

Das Schema aktualisiert der Proxy beim Start selbst; das Image bringt den Prisma-Client
mit. Die früher nötigen Schritte `prisma migrate deploy` und `prisma generate` entfallen
damit — sie stammen aus der Zeit selbstgebauter Proxy-Images.

> **Nach einem Versionssprung die Guardrail-Syntax prüfen.** Sie hat sich schon geändert:
> Den Typ `regex` gibt es seit 1.83.7 nicht mehr, und ein Proxy, der die Config nicht
> liest, startet gar nicht erst. Der erste Blick nach dem Update gehört deshalb
> `docker compose logs litellm`, der zweite `/settings/guardrail`.

> **Betreiben Sie den Proxy weiterhin als eigenen Stack?** Dann gelten die Befehle dieses
> Abschnitts für **jenes** Verzeichnis, und das Image dort baut sich womöglich selbst —
> in dem Fall bleiben `prisma migrate deploy` und `prisma generate` nötig. Zum Umstieg:
> [Runbook LiteLLM-Umzug](../runbooks/litellm-in-die-compose.md).

## „No Redis configured" in der Proxy-UI

**Das ist der erwartete Zustand, kein Befund.** Der Proxy läuft mit einem Worker; seine
Zähler liegen dann im Arbeitsspeicher dieses einen Prozesses und sind dort stimmig. Was
tatsächlich zählt, liegt ohnehin woanders: Der **Verbrauch** steht in der Proxy-Postgres,
und **gedrosselt** wird im Backend (`config/rate_limits.yaml`), nicht im Proxy — dessen
`tpm`/`rpm`-Limits setzt die Plattform gar nicht.

Ein gemeinsamer Zähler-Speicher wird erst nötig, wenn der Proxy mit **mehreren Workern**
läuft. Das ist kein Schalter, sondern ein Ausbauschritt mit eigenen Folgen (Budgets können
je Worker überzogen werden, Cooldowns wirken nur lokal) — er gehört gemessen, nicht
vermutet.

## Embeddings: Knoten ohne Vektor

Fehlt einem Knoten das Embedding, taucht er in der semantischen Suche nicht auf. Der
nächtliche Backfill (03:15) holt das nach; er wählt nach `embedding IS NULL`, eine
Fehlermarke aus einem früheren Lauf hält ihn also **nicht** ab.

Alle Befehle im Anwendungsverzeichnis:

```bash
# Überblick: wie viele Knoten haben keinen Vektor, wie viele eine Fehlermarke?
docker compose exec db psql -U postgres -d ggd_ki -c \
  "SELECT count(*) FILTER (WHERE embedding IS NULL)              AS ohne_vektor,
          count(*) FILTER (WHERE metadata ? 'embedding_error')   AS mit_fehlermarke,
          count(*)                                               AS aktive_knoten
     FROM context_nodes WHERE status = 'active';"
```

```bash
# Der eigentliche Grund: LiteLLMs Antworttext, wie er beim Fehlschlag gespeichert wurde.
# -x (erweiterte Ausgabe), weil die Meldungen lang sind.
docker compose exec db psql -U postgres -d ggd_ki -x -c \
  "SELECT count(*) AS knoten, left(metadata->>'embedding_error', 300) AS fehler
     FROM context_nodes WHERE metadata ? 'embedding_error'
    GROUP BY 2 ORDER BY 1 DESC LIMIT 5;"
```

Was der Text verrät:

| Meldung enthält | Bedeutung | Abhilfe |
|---|---|---|
| `No deployments available` + `cooldown_list` | **Folgefehler, keine Ursache.** LiteLLM hat das Modell in den Cooldown genommen und weist seitdem alles mit `429` ab | Nicht die 429 behandeln, sondern den Grund des Cooldowns suchen — siehe Kasten unten |
| `401` / `Incorrect API key` | Der Anbieter-Schlüssel in der LiteLLM-Config ist ungültig oder abgelaufen | Schlüssel erneuern, LiteLLM neu starten |
| `401 Unauthorized` **für die LiteLLM-URL selbst** | Nicht der Anbieter — der Proxy weist das Backend ab: `LITELLM_MASTER_KEY` passt nicht zu LiteLLMs Master-Key | Beide `.env` abgleichen |
| `429` / `rate limit` (ohne `cooldown_list`) | Echtes Kontingent überschritten — typisch nach einem Bildungsplan-Import, wenn der Backfill Tausende Knoten am Stück einbettet | Wird automatisch wiederholt (`EMBEDDING_MAX_RETRIES`, Vorgabe 3). Hält es an: `rpm`/`tpm` am Embedding-Modell setzen oder kleineres `--batch-size` |
| `400` / `Invalid 'input'` | Der Knoteninhalt passt dem Modell nicht (leer, zu lang, Sonderzeichen) | `EMBEDDING_MAX_CHARS` prüfen; einzelne Knoten inhaltlich ansehen |
| `dimensions` / Vektorbreite | Modell und Spaltenbreite passen nicht zusammen | `docs/runbooks/modellwechsel.md` — Migration + Re-Embedding |

> **Der häufigste Irrweg: `429` als Rate-Limit lesen.** LiteLLM kühlt eine Deployment
> ausdrücklich auch bei **401** ab („Cool down 401 Auth Errors"). Führt ein Modell nur
> eine Deployment — bei Embeddings die Regel —, sieht danach *jede* Anfrage so aus:
>
> ```
> {"code":"429","message":"No deployments available for selected model,
>  Try again in 5 seconds. Passed model=text-embedding-3-small,
>  cooldown_list=['19c8a004-…']"}
> ```
>
> Der eigentliche Grund steht bei den *älteren*, selteneren Einträgen derselben Abfrage —
> dort, wo noch `401 Incorrect API key` steht. Deshalb `LIMIT 5` und nicht `LIMIT 1`: Die
> Massenmeldung ist die Folge, die Handvoll darunter die Ursache.
>
> Gegenprobe ohne Umweg über die Knoten:
>
> ```bash
> # Aus dem backend-Container heraus — das LiteLLM-Image bringt kein curl mit,
> # und so wird zugleich der Weg geprüft, den die Anwendung tatsächlich geht:
> docker compose exec backend sh -c \
>   'curl -s -o /dev/null -w "%{http_code}\n" -X POST $LITELLM_PROXY_URL/embeddings \
>      -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
>      -H "Content-Type: application/json" \
>      -d "{\"model\":\"$EMBEDDING_MODEL\",\"input\":[\"Test\"]}"'
> ```

**Der Backfill bricht bei einer Fehlerserie ab.** Zehn Fehlschläge in Folge heißen: Es
liegt am Modellzugang, nicht an den Knoten. Der Lauf endet dann mit `ABBRUCH:` im Log,
statt Tausende Knoten mit vollem Wiederholungsbudget abzuarbeiten. Die nicht versuchten
Knoten bleiben unangetastet und kommen im nächsten Lauf wieder dran.

```bash
# Nachziehen, ohne bis zur Nacht zu warten (klein anfangen):
docker compose exec backend python scripts/embedding_backfill.py --limit 200
```

## PII-NER-Modell aktualisieren

Die PII-Erkennung (Datensparsamkeit) nutzt das deutsche spaCy-Modell `de_core_news_md`,
gepinnt in `backend/requirements.txt`. Zum Aktualisieren die Wheel-URL auf die neue
Version anheben (muss zur `spacy`-Minor-Version passen), den Lockfile neu erzeugen und das
Backend-Image neu bauen:

```bash
# requirements.txt: de_core_news_md-Wheel-URL auf neue Version setzen, dann:
uv pip compile requirements.txt --generate-hashes -o requirements.lock
docker compose build backend && docker compose up -d backend
```

Ein Modell-Update ist selten nötig und betrifft nur die Treffergüte der PII-Warnung —
keine Datenmigration. Es wird **nichts** extern aufgerufen; das Modell läuft lokal.

## Python-Abhängigkeiten aktualisieren

`backend/requirements.txt` listet die **direkten** Abhängigkeiten mit Ober-/Untergrenzen;
`backend/requirements.lock` pinnt daraus **alle** (auch transitiven) Pakete auf exakte Versionen
**mit Integritäts-Hashes** (Sicherheits-Audit #17 — reproduzierbare Installs, keine ungetesteten
Majors). Produktion/CI installiert aus dem Lock:

```bash
uv pip install --require-hashes -r requirements.lock
```

Zum Aktualisieren: die gewünschte Grenze in `requirements.txt` anpassen, Lock neu erzeugen und
die Tests laufen lassen — erst danach ausrollen:

```bash
uv pip compile requirements.txt --generate-hashes -o requirements.lock
pytest tests/unit -q
```

## Datenbank-Backup

Ein tägliches Backup des PostgreSQL-Volumes wird empfohlen:

```bash
docker compose exec db pg_dump -U postgres ggd_ki > backup_$(date +%F).sql
```

Das Backup enthält alle Nutzerkonten, Konversationen und Budgetdaten.
`SCHOOL_SECRET` separat sichern — ohne ihn ist eine De-Anonymisierung
auch mit Backup nicht möglich.

---

## Schuljahreswechsel

> Die vollständige Schritt-für-Schritt-Fassung mit Prüfpunkten steht im
> [Runbook Schuljahreswechsel](../runbooks/schuljahreswechsel.md). Hier nur der Überblick.

### Was automatisch passiert

- **Abgänger** (kein Login > 90 Tage) werden automatisch gelöscht. Nach dem
  Schuljahresende sind Abgänger spätestens in den Herbstferien bereinigt.
- **Neue Schüler:innen** erhalten beim ersten Login automatisch ein Konto und
  werden anhand ihrer SSO-Jahrgangsgruppe der richtigen Budget-Klasse zugeordnet.
- **Jahrgangs­wechsel:** Wenn Schüler:innen im SSO-System in die nächste
  Jahrgangsgruppe verschoben werden, greift der neue Wochenbetrag beim nächsten
  Zuteilungslauf (montags) automatisch; die Team-Zugehörigkeit zieht der
  Monatslauf nach.
- **Budget-Rücksetzung:** Sobald `config/school_year.yaml` das neue Schuljahr
  führt, setzt der erste Zuteilungslauf Obergrenze **und** Verbrauch zurück.
  Reste des Vorjahres wandern **nicht** mit — siehe
  [Budget-System → Schuljahreswechsel](budget.md#schuljahreswechsel).

### Was manuell geprüft werden sollte

**Im SSO-System (nicht in der Plattform):**
- Wurden alle Schüler:innen in ihre neuen Jahrgangsgruppen verschoben?
- Sind Abgänger aus den Schulgruppen entfernt?

**In der Plattform:**
- `config/school_year.yaml` auf das neue Schuljahr umstellen — Beginn, Ende, Ferien,
  Feiertage. **Danach die Zahl der Unterrichtswochen auf `/budget` prüfen:** Sie ist der
  Faktor der Jahreszusage, und ein vergessener Ferienzeitraum erzeugt zusätzliche Wochen
  und damit eine höhere Jahressumme als angezeigt.
- `config/budget_tiers.yaml`: Sollen sich die Wochenbeträge für bestimmte
  Jahrgänge ändern? Die Anpassung geht auch über `/budget`; dort steht die
  resultierende Jahressumme daneben.
- `STUDENT_GRADES` in `.env`: Enthält die Liste noch alle relevanten Jahrgänge?
  (Relevant wenn ein neuer 5. Jahrgang hinzukommt oder der 12. endet.)
- Assistenten: Sind alle Assistenten noch aktuell und für das neue Schuljahr passend?

### Abgänger vor der automatischen Löschung bereinigen

Falls Schule oder Datenschutzbeauftragte eine frühere Löschung wünschen:

```bash
# Vorschau: zeigt an, welche Konten gelöscht würden
docker compose exec backend python scripts/cleanup_inactive_accounts.py --dry-run

# Zum Testen mit einem fiktiven "jetzt"-Datum (90 Tage nach Schuljahresende):
docker compose exec backend python scripts/cleanup_inactive_accounts.py \
  --now 2026-10-01T02:00:00+00:00 --dry-run

# Tatsächlich ausführen (ohne --dry-run):
docker compose exec backend python scripts/cleanup_inactive_accounts.py \
  --now 2026-10-01T02:00:00+00:00
```

---

## Log-Auswertung

```bash
docker compose logs -f backend     # Backend-Logs
docker compose logs -f cron        # Cron-Job-Ausgaben
docker compose logs -f litellm     # LiteLLM-Proxy-Logs
```

Häufige Meldungen und ihre Bedeutung:

| Meldung | Bedeutung | Handlungsbedarf |
|---------|----------|----------------|
| `429` von LiteLLM | Budget einer Nutzerin aufgebraucht | Normal, kein Handlungsbedarf |
| `Connection refused` zu LiteLLM | LiteLLM-Container nicht erreichbar | `LITELLM_PROXY_URL` in `.env` prüfen |
| `alembic.util.exc.CommandError` beim Start | Datenbank-Migration fehlt | `alembic upgrade head` ausführen |
| `SCHOOL_SECRET not set` | Pflichtumgebungsvariable fehlt | `.env` prüfen |

## Troubleshooting

**Das Backend startet nicht: „Die Knotentyp-Taxonomie passt nicht zum System (ADR-018)"**
Der Start bricht ab, und das Log nennt jede Abweichung einzeln — welcher Typ, welche
Quelle. Die Meldung ist gewollt: Die Bausteinarten sind eine **Systemdatei** (siehe
[Konfigurationsdateien](konfiguration.md#was-ist-betreiber-konfiguration-was-systemdatei)),
und ohne diesen Abbruch liefe die Plattform mit Bausteinen weiter, für die sich keine
Ansicht mehr zuständig fühlt. Praktisch bedeutet die Meldung fast immer: **Migration
vergessen.** Steht dort „N Knoten tragen den content_type …, den die Taxonomie nicht
(mehr) kennt", fehlt der Datenbankteil des Updates:

```bash
docker compose exec backend alembic upgrade head
docker compose up -d backend
```

Vor einem Update lässt sich der datenbankfreie Teil vorab prüfen:

```bash
docker compose exec backend python scripts/check_production.py
```

**Beim Start steht „`…/config/taxonomy.yaml` ist eine Altlast und wird nicht gelesen"**
Kein Fehler. Bis Version 0.7 lag die Liste der Bausteinarten als `config/taxonomy.yaml`
auf dem Host; seit 0.8 gehört sie zum Anwendungsabbild
(`backend/app/context/taxonomy.yaml`) und wird von dort gelesen. Die alte Datei auf dem
Host wirkt nicht mehr — löschen Sie sie, sonst sieht sie bei der nächsten Fehlersuche
aus wie eine gültige Einstellung:

```bash
rm config/taxonomy.yaml
```

**Ein Assistent sagt, im Wissensgraph sei nichts zu einem Thema — obwohl Bausteine
vorhanden sind**
Seit 09/2026 antwortet die Suche in getrennten Abschnitten mit Zählung (siehe
[Kontextspeicher](../user/kontext.md)): Namensträger und Aufzählung sind vollständig, die
thematische Auswahl ist es ausdrücklich nie. Bleibt ein Baustein trotzdem ungenannt,
lohnen zwei Fragen: Hat das Modell **thematisch** gesucht, wo eine Aufzählung nötig
gewesen wäre? Und trägt der Knotentyp überhaupt ein Embedding — 15 der 45 Typen sind
bewusst nur über Name und Aufzählung erreichbar
([neuer-knotentyp.md](../dev/neuer-knotentyp.md)).

Welches Werkzeug der Assistent überhaupt gegriffen hat, steht seit 08/2026 im
Backend-Log:

```bash
docker compose logs backend | grep "^.*Tool '"
# INFO Tool 'search_context_nodes' (Runde 1) → Felder ['exakte_namenstraeger', …]
# INFO Tool 'list_context_nodes' (Runde 1) → Felder ['bausteine', 'gesamt', …]
# INFO Tool 'get_operatoren' (Runde 1) → Felder ['hinweis']
```

Damit lässt sich unterscheiden, welches der drei Werkzeuge gegriffen hat:

| Werkzeug | wofür |
|---|---|
| `search_context_nodes` | „Was gibt es zu diesem Thema?" — Namensträger und nächstliegende Bausteine |
| `list_context_nodes` | „Alle, die …" / „Wie viele?" — vollständige, gezählte Liste |
| `get_operatoren` | Operatoren des Konversationsfachs; ohne Fachbezug ein `hinweis` statt einer Liste |

Greift ein Modell für eine „alle …"-Frage zu `search_context_nodes` statt zu
`list_context_nodes`, bekommt es eine nach Ähnlichkeit gekürzte Liste und antwortet
womöglich unvollständig. Solche Fehlgriffe sind hier sichtbar — und der Grund, aus dem
`get_operatoren` vorerst bestehen bleibt.

**Wann `get_operatoren` entfällt.** Das Werkzeug ist seit 09/2026 nur noch ein Preset der
Aufzählung (Typ = `operator`, Fach = Konversationsfach); es tut nichts, was
`list_context_nodes` nicht könnte. Es bleibt allein deshalb, weil Modelle bei
fachbezogenen Fragen erwiesenermaßen dorthin greifen. Entfernt wird es, wenn **beides**
zutrifft:

1. Alle Aufzählungsfälle des Prüfsatzes (`config/search_eval.yaml`, Abschnitt
   `aufzaehlungen`) wählen in einem Werkzeugwahl-Durchlauf `list_context_nodes`.
2. **Zwei Wochen** Produktivbetrieb ohne einen Fehlgriff auf `get_operatoren` im Log —
   also ohne eine Zeile `Tool 'get_operatoren' … → Felder ['hinweis']`, die auf eine Frage
   folgte, die kein einzelnes Fach meinte.

Beobachtet wird mit dem `grep` oben. Punkt 2 ist der eigentliche Nachweis: Punkt 1 misst
eine Laborsituation, Punkt 2 den echten Gebrauch.

Der Suchtext selbst wird **nicht** protokolliert — er ist Nutzereingabe und gehört nicht
in Logs.

**Nutzer:innen können sich nicht einloggen — „Anmeldung fehlgeschlagen!" trotz
richtigem Passwort**
Häufigste Ursache: Der **OAuth-Client ist für die Gruppe der Person nicht freigegeben**.
IServ bleibt dann auf der eigenen Login-Seite und zeigt diese Meldung, obwohl die Anmeldung
*in IServ* erfolgreich war; gemeint ist „Die Anmeldung am gewünschten Dienst ist nicht
möglich". **In den Logs der Plattform steht dazu nichts** — die Anfrage erreicht sie nie.
Also die Client-Freigabe prüfen, nicht das Konto. Siehe
[Nutzerverwaltung](nutzerverwaltung.md#wer-die-plattform-nutzen-darf).

**Nutzer:innen kommen herein, haben aber die falsche Rolle**
`config/auth.yaml` prüfen: Sind die Gruppen in `group_role_map` exakt so
geschrieben wie im SSO-System? Groß-/Kleinschreibung beachten. Zur Diagnose hilft
`AUTH_DEBUG_USERINFO=true` (zeigt die rohen Claims — enthält Klarnamen, nur temporär).

**Nutzer:innen sehen keine Modelle**
Die Modell-Freischaltungsmatrix unter `/settings/models` ist noch leer.
Für jede Nutzergruppe mindestens ein Modell aktivieren.

**Budget wächst nicht**
Das Guthaben wird je **Unterrichtswoche** aufgestockt (montags 05:00), nicht monatlich.
In Ferienwochen passiert nichts — das ist kein Fehler. Sonst prüfen: Läuft der
`cron`-Container (`docker compose ps cron`)? Was sagt `docker compose logs cron`?
Trockenlauf zur Diagnose:

```bash
docker compose exec backend python scripts/weekly_budget_accrual.py --dry-run
```

Meldet er „kein Wochenbetrag konfiguriert", führt `budget_tiers.yaml` noch das alte
Monatsschema — siehe [Budget-System](budget.md#umstellung-vom-monatsmodell-einmalig).

**Pseudonyme haben sich geändert**
`SCHOOL_SECRET` wurde in `.env` geändert. Dieser Vorgang ist nicht
reversibel — alle bestehenden Nutzerzuordnungen sind ungültig.
Backup einspielen und `SCHOOL_SECRET` auf den ursprünglichen Wert zurücksetzen.

**Ein Fach erscheint doppelt im Dropdown oder zeigt „Kein Bildungsplan für dieses
Fach verfügbar"**
Eine verwaiste Fach-Zeile in der DB — das Fach wurde in `config/subjects.yaml`
umbenannt oder entfernt, die alte Zeile aber nie gelöscht. Der neue Bildungsplan
hängt an der neuen `id`, die alte Zeile bleibt leer. Bereinigen mit
`python scripts/seed_subjects.py --prune` (siehe [Fächer ändern](#fächer-ändern-subjectsyaml)).

**Lehrkraft hat eine `fs.*`-Gruppe, darf aber kein Curriculum im Fach anlegen
(„Sie müssen Mitglied der Fachschaft sein") / eine Fachschaft erscheint doppelt**
Doppelte Gruppen-Zeilen für dieselbe SSO-Gruppe, entstanden vor der case-
insensitiven Behandlung der `sso_group_id` (z. B. `FS.Chemie` **und** `fs.chemie`).
Die Mitgliedschaft sitzt dann evtl. an der „falschen" der beiden. Bereinigen
(verschmilzt Doppelgruppen je `lower(sso_group_id) + Typ + Fach`, hängt
Mitgliedschaften/Curricula auf die überlebende Gruppe um):
```bash
docker compose exec backend python scripts/dedup_groups.py          # Vorschau (Dry-Run)
docker compose exec backend python scripts/dedup_groups.py --apply  # ausführen
```
Neue Dubletten entstehen nicht mehr — der Gruppen-Sync speichert `sso_group_id`
seither normalisiert (lowercase) und sucht case-insensitiv.
