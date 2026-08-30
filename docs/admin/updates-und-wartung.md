# Updates & Wartung

## Reguläres Update

```bash
git pull
docker compose build --no-cache
docker compose up -d
docker compose exec backend alembic upgrade head
```

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

## LiteLLM updaten

> **Anderes Verzeichnis!** Der LiteLLM-Proxy läuft in einem **eigenen Compose-Stack** mit
> eigener Postgres-Datenbank — die `docker-compose.yml` dieses Repos enthält ihn nicht.
> Alle `docker compose …`-Befehle dieses Abschnitts sind aus dem **LiteLLM-Verzeichnis**
> abzusetzen, nicht aus dem Anwendungsverzeichnis. Dort ausgeführt scheitern sie mit
> `no such service: litellm` — was leicht als Deployment-Fehler missgedeutet wird.
>
> Umgekehrt gilt dasselbe: `docker compose exec db psql -d ggd_ki` gehört ins
> **Anwendungs**verzeichnis. Beide Stacks haben einen Dienst namens `db`, und sie führen
> verschiedene Datenbanken (`ggd_ki` bzw. `litellm`).

LiteLLM verwaltet sein eigenes Datenbankschema über Prisma. Ein einfaches
`pip install --upgrade litellm` genügt nicht — Schema und Prisma-Client müssen
separat nachgezogen werden, sonst kann es zu Fehlern wie
`'LiteLLM_TeamTable' object has no attribute '...'` kommen.

**Reihenfolge beim LiteLLM-Update:**

```bash
# 1. LiteLLM-Container neu bauen (zieht neue Version)
docker compose build --no-cache litellm
docker compose up -d litellm

# 2. DB-Schema aktualisieren
docker compose exec litellm prisma migrate deploy

# 3. Prisma-Python-Client neu generieren
docker compose exec litellm sh -c "
  LITELLM_DIR=\$(python3 -c 'import litellm, os; print(os.path.dirname(litellm.__file__))')
  cd \"\$LITELLM_DIR/proxy\"
  prisma generate --schema=schema.prisma
"

# 4. LiteLLM neu starten
docker compose restart litellm
```

## Redis für LiteLLM

Meldet die Proxy-UI **„No Redis configured"**, hält LiteLLM seine Zähler — Budgets,
Rate-Limits, Router-Zustand — im Arbeitsspeicher des jeweiligen Workers. Mit mehreren
Workern zählt dann jeder für sich, und nach jedem Neustart beginnt die Zählung von vorn.

Die vollständige Vorlage steht in **`infra/litellm-redis.example.yml`**. Kurzfassung —
drei Eingriffe, alle im **LiteLLM-Verzeichnis**:

1. Dienst `redis` ergänzen (ohne `ports:`, ohne Persistenz — der Inhalt sind Zähler).
2. Am `litellm`-Dienst `REDIS_HOST: redis` / `REDIS_PORT: "6379"` setzen und `redis` in
   `depends_on` aufnehmen.
3. In der `config.yaml`:

   ```yaml
   litellm_settings:
     cache: true
     cache_params:
       type: redis
       supported_call_types: []
   ```

> **Die Umgebungsvariablen allein genügen nicht.** LiteLLM legt den gemeinsamen
> Zähler-Cache erst an, wenn `litellm_settings.cache` gesetzt **und** der Cache-Typ
> `redis` ist. Ohne den Config-Block bleibt Redis wirkungslos, obwohl der Container läuft.
>
> **`supported_call_types: []` ist Absicht.** `cache: true` schaltet sonst auch das
> Zwischenspeichern von **Modellantworten** ein: Zwei identische Anfragen bekämen
> dieselbe Antwort. Für eine Schulplattform ist das nicht gewollt — und sobald Prompts
> kollidieren, ist es ein Datenschutzthema. Mit der leeren Liste entsteht der
> Zähler-Cache, gecacht wird nichts.

```bash
docker compose up -d redis
docker compose restart litellm
docker compose exec redis redis-cli dbsize   # > 0, sobald Anfragen laufen
```

## Embeddings: Knoten ohne Vektor

Fehlt einem Knoten das Embedding, taucht er in der semantischen Suche nicht auf. Der
nächtliche Backfill (03:15) holt das nach; er wählt nach `embedding IS NULL`, eine
Fehlermarke aus einem früheren Lauf hält ihn also **nicht** ab.

Alle Befehle im **Anwendungsverzeichnis** (nicht im LiteLLM-Verzeichnis):

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
> # Im LiteLLM-Verzeichnis:
> docker compose exec litellm sh -c \
>   'curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:4000/embeddings \
>      -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
>      -H "Content-Type: application/json" \
>      -d "{\"model\":\"<EMBEDDING_MODEL aus der .env>\",\"input\":[\"Test\"]}"'
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

**Ein Assistent sagt, im Wissensgraph sei nichts zu einem Thema — obwohl Bausteine
vorhanden sind**
Die **Suche im Kontextspeicher ist experimentell** (siehe
[Kontextspeicher](../user/kontext.md)); je nach Formulierung findet sie das Gesuchte
nicht, und ein Modell deutet ein leeres Ergebnis erwartungsgemäß als „gibt es nicht".

Welches Werkzeug der Assistent überhaupt gegriffen hat, steht seit 08/2026 im
Backend-Log:

```bash
docker compose logs backend | grep "^.*Tool '"
# INFO Tool 'search_context_nodes' (Runde 1) → 8 Einträge
# INFO Tool 'get_operatoren' (Runde 1) → Felder ['hinweis']
```

Damit lässt sich unterscheiden, ob gesucht wurde und nichts kam (`0 Einträge`) oder ob
ein anderes Werkzeug gegriffen hat. `get_operatoren` etwa beantwortet nur Fragen zum Fach
der Konversation und meldet ohne Fachbezug einen `hinweis` statt einer Liste.

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
