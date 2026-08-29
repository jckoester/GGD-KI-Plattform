# Installation

## Systemvoraussetzungen

- **Docker** ≥ 24
- **Docker Compose** ≥ 2.20 (als Plugin: `docker compose`, nicht `docker-compose`)
- Eine öffentlich erreichbare Domain (für HTTPS und den OAuth-Redirect des SSO-Providers)
- Internetzugang zu mindestens einem KI-Anbieter — oder ein lokal laufendes Ollama
- Internetzugang **beim Build** (das Backend-Image lädt aus `requirements.txt` u. a. das
  deutsche NER-Modell `de_core_news_md` ~45 MB von GitHub für die PII-Erkennung)

## Schritt 1: Repository klonen

```bash
git clone https://github.com/jckoester/GGD-KI-Plattform.git ki-plattform
cd ki-plattform
```

## Schritt 2: Konfiguration anlegen

Alle Konfigurationsdateien liegen im Verzeichnis `config/` und `infra/`.
Aus den mitgelieferten Beispieldateien jeweils eine produktive Kopie erstellen:

```bash
cp .env.example                          .env
cp infra/litellm_config.example.yaml     infra/litellm_config.yaml

for f in auth budget_tiers subjects crisis_triggers help_resources \
         rate_limits pedagogy image_blocklist artifact_limits school_year; do
  cp "config/$f.example.yaml" "config/$f.yaml"
done
```

> **Alle kopieren, auch wenn nicht jede den Start verhindert.** Diese Dateien stehen in
> `.gitignore` und werden vom Repository nicht mitgeliefert; **auf die `.example`-Fassung
> fällt keine von ihnen zurück**. `auth`, `budget_tiers`, `crisis_triggers` und
> `image_blocklist` brechen ohne ihre Datei mit `FileNotFoundError` ab;
> `rate_limits` und `artifact_limits` starten mit eingebauten Vorgaben und einer Warnung
> im Log — was leicht übersehen wird. `config/subjects.yaml` braucht spätestens Schritt 6.

Anschließend `.env` mit einem Texteditor öffnen und mindestens diese
Pflichtfelder befüllen:

```bash
# Datenbankpasswort (zufällig generieren):
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# Pseudonymisierungsschlüssel — NIEMALS nach Inbetriebnahme ändern:
SCHOOL_SECRET=$(openssl rand -base64 32)

# Schlüssel für JWT-Tokens:
JWT_SECRET=$(openssl rand -base64 32)

# LiteLLM-Zugangsschlüssel (frei wählbar, muss mit litellm_config.yaml übereinstimmen):
LITELLM_MASTER_KEY=sk-$(openssl rand -hex 16)

# EIGENE Datenbank für den Proxy — plain postgresql://, nicht der asyncpg-DSN der App:
LITELLM_DATABASE_URL=postgresql://postgres:<POSTGRES_PASSWORD>@db:5432/litellm
```

Die Modell-Variablen (`CHAT_DEFAULT_MODEL`, `TITLE_MODEL`, `EMBEDDING_MODEL`) und den
Zugang zum KI-Anbieter füllt der nächste Schritt — sie hängen davon ab, welche Modelle
in der LiteLLM-Config stehen.

Die vollständige Beschreibung aller Variablen steht in [Konfigurationsdateien](konfiguration.md).

## Schritt 3: Modelle eintragen

Ohne diesen Schritt startet die Plattform, aber **kein Chat funktioniert**. Er ist der
einzige Schritt, den keine Vorlage vorwegnehmen kann: Welcher Anbieter, welche Modelle und
welche Preise, entscheidet die Schule.

**1. Anbieter wählen.** Gemessene Preise, Fähigkeiten und Fallstricke je Anbieter stehen
in [Vor der Installation → Modellwahl](vor-der-installation.md#modellwahl). Die
Entscheidung über das **Embedding-Modell** vorziehen: Seine Vektorbreite lässt sich später
nur mit Schemaänderung und vollständigem Re-Embedding korrigieren
([Runbook Modellwechsel](../runbooks/modellwechsel.md)).

**2. `model_list` befüllen.** Fertige, vollständige Blöcke für IONOS, Mistral, OpenAI,
Anthropic und den Mischbetrieb stehen in
[Modell-Szenarien](modell-szenarien.md) — sie lassen sich übernehmen und nur beim
Preis nachziehen. Für den EU-Betrieb ist `infra/litellm_config.ionos.example.yaml` die
bessere Ausgangsdatei als die allgemeine Vorlage.

> **Die `model_name`s sind Aufgabennamen, keine Produktnamen** — `chat-standard` statt
> `gpt-4o-mini`. Sie stehen in der `.env`, in Assistenten-Datensätzen und in den
> Team-Allowlists, und Schüler:innen lesen sie im Modellwähler. Wer rohe Produktnamen
> einträgt, macht den Filter `MODEL_PICKER_HIDDEN_PREFIXES` wirkungslos (das Titelmodell
> steht dann sichtbar im Dropdown) und fasst bei jedem Anbieterwechsel `.env` und
> Datenbank an. Begründung und Stufenschema:
> [Modelle & Assistenten](modelle-und-assistenten.md#welche-modelle-es-geben-sollte).

**3. Zugang und Namen in die `.env` eintragen.** Die Werte sind die `model_name`s aus der
LiteLLM-Config, nicht die Modell-IDs des Anbieters:

```bash
OPENAI_API_KEY=…            # bzw. IONOS_API_KEY / MISTRAL_API_KEY / ANTHROPIC_API_KEY
CHAT_DEFAULT_MODEL=chat-standard
TITLE_MODEL=system-titel
EMBEDDING_MODEL=embedding-standard
EMBEDDING_DIMENSIONS=1536   # muss zur Vektorbreite des gewählten Modells passen
```

Drei Dinge scheitern hier **still** — nichts stürzt ab, es passiert nur nicht das
Gewünschte. Sie stehen mit ihren Folgen in
[Konfiguration → Drei Dinge, die still schiefgehen](konfiguration.md#drei-dinge-die-still-schiefgehen):
fehlendes `supports_function_calling`, fehlende Token-Preise, fehlende `IMAGE_PRICES`.

Geprüft wird das in Schritt 9, sobald der Proxy läuft.

## Schritt 4: Docker Compose starten

```bash
docker compose up -d
```

Alle Container starten nun. Den Status prüfen:

```bash
docker compose ps
```

Alle Services sollten den Status `healthy` bzw. `running` erreichen. Der
`db`-Container muss healthy sein, bevor `backend` startet — das wird durch
den `depends_on`-Healthcheck im `docker-compose.yml` sichergestellt.

## Schritt 5: Datenbank-Migration

```bash
docker compose exec backend alembic upgrade head
```

Dieser Befehl legt alle Datenbanktabellen an. Er ist bei jeder Installation
und nach jedem Update mit neuen Migrationen auszuführen.

## Schritt 6: Fächer einspielen

Die Fächer-Tabelle wird nicht automatisch befüllt. Vor dem ersten Login müssen
die Fächer aus `config/subjects.yaml` in die Datenbank eingespielt werden:

```bash
docker compose exec backend python scripts/seed_subjects.py
```

Das Skript liest `config/subjects.yaml` und legt alle darin definierten Fächer
(Slug, Name, Icon, Farbe, Jahrgangsstufen, Bildungsplan-Fachcode, SSO-Aliase)
per Upsert an. Es ist idempotent — mehrfaches Ausführen aktualisiert bestehende
Einträge, legt keine Duplikate an.

> **Nach Code-Änderung in `subjects.yaml`** (neuer/geänderter `fach_code`) dieses
> Seed-Skript erneut ausführen — sonst kennt die Datenbank die neuen Codes nicht.

> **Entfernte oder umbenannte Fächer:** Der Standardlauf *löscht nichts*. Fächer,
> die nicht (mehr) in der YAML stehen (z. B. nach Umbenennung wie „Kunst" →
> „Bildende Kunst" oder Aufspaltung von „Religion" in Ev./Kath./Isl.), bleiben
> sonst als verwaiste Zeilen in der DB — sie tauchen weiter im Fach-Dropdown auf
> und zeigen u. U. einen leeren Bildungsplan (die andere `id` trägt den Fachplan).
> Solche Zeilen meldet das Skript als Warnung. Zum Entfernen:
>
> ```bash
> docker compose exec backend python scripts/seed_subjects.py --prune
> ```
>
> `--prune` löscht **nur unreferenzierte** verwaiste Fächer; Fächer, die noch von
> Konversationen, Gruppen, Assistenten o. Ä. referenziert werden, werden nie
> gelöscht, sondern mit Referenzzählung gemeldet.

> **Wichtig:** Ohne diesen Schritt können Nutzer:innen zwar Fächer und Gruppen
> aus dem SSO-System sehen, aber die Fach-Zuordnung (Icon, Farbe) fehlt. Bei
> Lehrkräften erscheinen SSO-Unterrichtsgruppen nicht in der Fach-Ansicht.

## Schritt 7: Initialen Wechselkurs eintragen

Das Budget-System rechnet intern in USD und benötigt einen EUR/USD-Wechselkurs
in der Datenbank. Den aktuellen Kurs (z. B. von der EZB) eintragen:

```bash
docker compose exec backend python scripts/seed_exchange_rate.py --rate 1.08
```

Der monatliche Cron-Job aktualisiert den Kurs danach automatisch. Das Skript
bricht ab, wenn bereits ein Eintrag vorhanden ist.

## Schritt 8: LiteLLM-Teams anlegen

Einmalig nach der Erstinstallation:

```bash
docker compose exec backend python scripts/create_litellm_teams.py
```

Dieses Skript legt in LiteLLM die Teams an, über die Budgets und
Modell-Freischaltungen pro Nutzergruppe durchgesetzt werden. Es ist idempotent —
mehrfaches Ausführen ist unschädlich.

## Schritt 9: Modellkonfiguration prüfen

Jetzt läuft der Proxy, und die Konfiguration aus Schritt 3 lässt sich gegen ihn abgleichen:

```bash
docker compose exec backend python scripts/check_litellm_config.py
```

Das Skript meldet genau die Fälle, die sonst erst im Betrieb auffallen — und dort nicht als
Fehler, sondern als „funktioniert irgendwie nicht": Modellnamen aus der `.env`, die der
Proxy nicht kennt, fehlendes `supports_function_calling`, fehlende Token- oder Bildpreise,
falsch gesetztes `mode` und nicht ersetzte Platzhalter.

Was es **nicht** prüfen kann, ist der Praxistest: eine Chat-Antwort erzeugen und
nachsehen, dass die zugehörige SpendLog-Zeile einen Betrag **größer als 0** trägt. Steht
dort 0, greifen weder Budgets noch die 429-Sperre noch die Kostenstatistik.

## Schritt 10: Reverse Proxy einrichten

Der nginx-Container hört auf Port 80 und leitet Anfragen intern an Backend und
Frontend weiter. Für HTTPS wird ein vorgelagerter Reverse Proxy empfohlen.

### Option A: Caddy (empfohlen — automatisches TLS via Let's Encrypt)

```
# infra/Caddyfile (aus infra/Caddyfile.example anpassen)
ki.beispielschule.de {
    reverse_proxy localhost:80
}
```

Caddy als Systemdienst oder in einem separaten Container betreiben.

### Option B: Externer nginx mit TLS

Den internen nginx-Port in `docker-compose.yml` auf einen anderen Host-Port
legen (z. B. `8080:80`) und einen externen nginx als TLS-Terminator davor
schalten.

## Schritt 11: Erster Login und Grundkonfiguration

1. Die Plattform im Browser unter der konfigurierten Domain aufrufen.
2. Mit einem Konto einloggen, das im SSO-Provider der Gruppe mit der Rolle
   `admin` zugeordnet ist (gemäß `group_role_map` in `auth.yaml`).
3. **Modell-Freischaltung:** Unter `/settings/models` für jede Nutzergruppe
   mindestens ein Modell aktivieren — solange die Matrix leer ist, können
   Nutzer:innen keine Anfragen stellen.

   > **Das Titelmodell (`TITLE_MODEL`) gehört in *jede* Gruppe.** Die Titelgenerierung
   > läuft über den persönlichen Virtual Key der Nutzer:innen, nicht über den Master-Key —
   > LiteLLM prüft also deren Allowlist. Fehlt es, bleiben die Gespräche unbetitelt, ohne
   > dass irgendwo ein Fehler erscheint. Dass `MODEL_PICKER_HIDDEN_PREFIXES` es aus dem
   > Chat-Dropdown ausblendet, ändert daran nichts: Der Filter ist rein kosmetisch, in
   > dieser Matrix bleibt das Modell sichtbar.

4. **Texte hinterlegen:** Unter `/settings/texts` Impressum, Datenschutzerklärung
   und Nutzungsregeln eingeben (rechtlich erforderlich).
