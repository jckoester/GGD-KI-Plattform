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
cp .env.example                  .env
cp config/auth.example.yaml      config/auth.yaml
cp config/budget_tiers.example.yaml config/budget_tiers.yaml
cp infra/litellm_config.example.yaml infra/litellm_config.yaml
```

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
```

Die vollständige Beschreibung aller Variablen steht in [Konfigurationsdateien](konfiguration.md).

## Schritt 3: Docker Compose starten

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

## Schritt 4: Datenbank-Migration

```bash
docker compose exec backend alembic upgrade head
```

Dieser Befehl legt alle Datenbanktabellen an. Er ist bei jeder Installation
und nach jedem Update mit neuen Migrationen auszuführen.

## Schritt 5: Fächer einspielen

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

## Schritt 9: Reverse Proxy einrichten

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

## Schritt 10: Erster Login und Grundkonfiguration

1. Die Plattform im Browser unter der konfigurierten Domain aufrufen.
2. Mit einem Konto einloggen, das im SSO-Provider der Gruppe mit der Rolle
   `admin` zugeordnet ist (gemäß `group_role_map` in `auth.yaml`).
3. **Modell-Freischaltung:** Unter `/settings/models` für jede Nutzergruppe
   mindestens ein Modell aktivieren — solange die Matrix leer ist, können
   Nutzer:innen keine Anfragen stellen.
4. **Texte hinterlegen:** Unter `/settings/texts` Impressum, Datenschutzerklärung
   und Nutzungsregeln eingeben (rechtlich erforderlich).
