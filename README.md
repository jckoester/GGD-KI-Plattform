# GGD-KI-Plattform

Eine selbst gehostete KI-Zugangsplattform für Schulen. Sie bietet eine Web-Oberfläche für den Zugang zu großen Sprachmodellen (LLMs) und erfüllt dabei die Anforderungen der DSGVO durch konsequente Pseudonymisierung: Schüleridentitäten verlassen den Schulserver niemals.

---

## Funktionsumfang

### Vorhanden (Phase 1)

- **Chat-Oberfläche** mit Assistenten-Auswahl und Gesprächsverlauf
- **Budget-System**: monatliche EUR-Limits pro Jahrgang und Rolle, automatische Umrechnung über den EZB-Kurs, Anzeige des Restbudgets im Chat
- **Admin-Bereich**:
  - Modell-Freischaltungsmatrix (welche Teams dürfen welche Modelle nutzen)
  - Budget-Verwaltung (Limits je Jahrgang und Rolle)
  - Nutzungsstatistiken (Heatmap, Kostenübersicht nach Zeitraum)
  - Verwaltung von Seitentexten (Impressum, Datenschutz, Hilfe, Nutzungsregeln)
- **Authentifizierung** via IServ OAuth2/OIDC (Produktivbetrieb) oder YAML-Testadapter (Entwicklung)
- **DSGVO-Datenlöschung**: automatisch nach 90 Tagen Inaktivität (Account) bzw. 93 Tagen ohne neue Nachrichten (Konversation)

### Geplant (Phase 2)

- Markdown-Darstellung in der Chat-Oberfläche (inkl. Code-Blöcke)
- Bild- und Datei-Uploads im Chat
- Verbesserte Chat-Oberfläche

---

## Datenschutzkonzept

### Kernprinzip: Pseudonymisierung vor dem Netzwerkausgang

Der kritische Datenschutz-Invariant der Plattform: Pseudonymisierung findet im Backend statt, **bevor** Daten das Schullnetzwerk verlassen. Der Kommunikationsweg ist dreistufig:

```
Plattform (Pseudonym) → LiteLLM-Proxy (Pseudonym intern) → KI-Anbieter (nur Schul-API-Key)
```

**Entscheidend:** Der externe KI-Anbieter (OpenAI, Anthropic, …) sieht ausschließlich den API-Key der Schule — das Pseudonym wird von LiteLLM intern verwendet (für Budget-Tracking und Audit), aber **nicht** an den Anbieter weitergegeben. Der Anbieter kann einzelne Nutzer damit weder identifizieren noch unterscheiden.

- Das Pseudonym entsteht als Einwegfunktion: `HMAC-SHA256(SCHOOL_SECRET, externe_ID)`. Ohne `SCHOOL_SECRET` kann niemand die echte Identität rekonstruieren.
- Echtnamen sind nur clientseitig im Browser sichtbar (aus dem JWT-Cookie), werden aber nie ans Backend gesendet.
- Der Reverse-Mapping-Eintrag (`externe_ID → Pseudonym`) liegt ausschließlich im Audit-Log auf dem Schulserver und wird nur für gesetzlich vorgeschriebene Aufbewahrungsfristen vorgehalten.

### Datenhaltung

| Datum | Löschung |
|-------|----------|
| Kein Login seit 90 Tagen | Account + vollständiger Chatverlauf |
| Keine neue Nachricht seit 93 Tagen | Einzelne Konversation |

Die Löschskripte laufen als Cron-Jobs auf dem Server (siehe [backend/README.md](backend/README.md)).


---

## Installation

### Voraussetzungen

- Docker + Docker Compose
- Eine laufende **LiteLLM**-Proxy-Instanz (mit PostgreSQL-Backend)
- Eine laufende **PostgreSQL**-Instanz für die Plattform selbst
- Anmeldung mit OAuth2/OIDC (Produktivbetrieb) oder der YAML-Testadapter (Entwicklung)

### Schritt 1 — Repository klonen

```bash
git clone <repo-url> ggd-ki-plattform
cd ggd-ki-plattform
```

### Schritt 2 — Konfiguration anlegen

```bash
cp config/.env.example config/.env
cp config/auth.example.yaml config/auth.yaml
cp infra/litellm_config.example.yaml infra/litellm_config.yaml
```

`config/.env` befüllen — die wichtigsten Variablen:

| Variable | Bedeutung |
|---|---|
| `DATABASE_URL` | PostgreSQL-Verbindung der Plattform |
| `SCHOOL_SECRET` | Geheimnis für HMAC-Pseudonymisierung (`openssl rand -base64 32`) |
| `JWT_SECRET` | Geheimnis für JWT-Cookies (`openssl rand -base64 32`) |
| `LITELLM_PROXY_URL` | URL der LiteLLM-Instanz |
| `LITELLM_MASTER_KEY` | Master-Key der LiteLLM-Instanz |
| `PUBLIC_SCHOOL_NAME` | Anzeigename der Schule in der UI |
| `PUBLIC_SCHOOL_LOGO_URL` | Pfad zum Schul-Logo (leer = Initialen-Kreis) |

`config/auth.yaml` nach [`config/auth.example.yaml`](config/auth.example.yaml) befüllen (IServ-URL, OAuth2-Client-ID, Gruppen-Rollen-Mapping).

### Schritt 3 — Budget-Stufen festlegen

In [`config/budget_tiers.yaml`](config/budget_tiers.yaml) die monatlichen EUR-Limits pro Jahrgang und Rolle eintragen.

### Schritt 4 — Datenbank migrieren

```bash
cd backend
python -m alembic upgrade head
```

### Schritt 5 — LiteLLM-Teams anlegen

```bash
cd backend
python scripts/create_litellm_teams.py
```

Danach im Admin-Bereich (`/admin → Modell-Freischaltung`) für jedes Team mindestens ein Modell aktivieren — eine leere Allowlist gilt in LiteLLM als „alle Modelle erlaubt" (siehe [update.md](update.md)).

### Schritt 6 — Starten

```bash
docker compose up -d
```

---

## Update

Hinweise zu Fallstricken beim Update einzelner Komponenten (insbesondere LiteLLM) sind in [`update.md`](update.md) dokumentiert.
