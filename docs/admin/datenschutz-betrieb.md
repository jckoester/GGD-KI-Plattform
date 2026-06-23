# Datenschutz & Betrieb

## Pseudonymisierungskonzept

Der Schutz personenbezogener Daten ist in der Architektur der Plattform
verankert — nicht als nachträgliche Maßnahme.

**Ablauf:**

1. Der SSO-Provider übermittelt beim Login eine eindeutige Nutzer-ID (`external_id`).
2. Das Backend berechnet daraus mittels HMAC-SHA256 und `SCHOOL_SECRET` ein
   Pseudonym: `pseudonym = HMAC-SHA256(SCHOOL_SECRET, external_id)`.
3. Alle weiteren Vorgänge — Datenbankeinträge, LiteLLM-Anfragen, Kostenerfassung —
   verwenden ausschließlich das Pseudonym.
4. Externe KI-Anbieter erhalten nur den Gesprächsinhalt und das Pseudonym
   als technische Nutzer-ID. **Name, E-Mail-Adresse und Klasse verlassen den
   Schulserver nie.**

Die Zuordnung `Pseudonym ↔ externe Nutzer-ID` existiert nur auf dem Schulserver
und wird nirgendwo persistent gespeichert — sie lässt sich jederzeit neu berechnen,
solange `SCHOOL_SECRET` unverändert ist.

## SCHOOL_SECRET — kritischer Konfigurationswert

`SCHOOL_SECRET` ist der einzige Schlüssel, der zur De-Anonymisierung benötigt wird.

- **Niemals nach der Inbetriebnahme ändern.** Würde der Schlüssel geändert,
  wären alle bestehenden Pseudonyme ungültig: Nutzerkonten und Gesprächsverläufe
  könnten keiner Person mehr zugeordnet werden.
- Den Schlüssel sicher aufbewahren (z. B. im Passwortmanager der Schule).
- Bei einem Verlust des Schlüssels ist eine De-Anonymisierung nicht mehr möglich.

## Was externe Anbieter erhalten

| Übertragen | Nicht übertragen |
|------------|-----------------|
| Gesprächsinhalt (Prompts, Antworten) | Name |
| Pseudonym als technische Nutzer-ID | E-Mail-Adresse |
| Gewähltes Modell | Klasse / Jahrgang |
| | IP-Adresse der Nutzerin |

## PII-Eingabewarnung (Datensparsamkeit)

Zusätzlich zur Pseudonymisierung warnt die Plattform Nutzer:innen, **bevor** sie
versehentlich personenbezogene Daten in den Gesprächsinhalt tippen. Die Prüfung läuft
**lokal auf dem Schulserver**, ruft **nichts extern** auf und **speichert nichts** —
sie ist ein freiwilliger Schutz-Hinweis, keine Sperre (fail-open: bei Fehler oder
Timeout wird die Eingabe nicht blockiert).

| Kategorie | Schicht | Verfahren |
|-----------|---------|-----------|
| Name, Wohnort / Adresse | Backend | lokale NER (spaCy `de_core_news_md`) + Cue-Muster + Adress-Regex |
| E-Mail, Telefon, IBAN | Frontend | Regex (latenzfrei, ohne Server-Anfrage) |

**Pflege der Muster:** Die Erkennungsmuster liegen **im Code**, nicht in einer
YAML-Konfiguration:

- Name/Wohnort (Cues, Adress-Regex, NER-Schwelle): `backend/app/pii/scanner.py`
- E-Mail/Telefon/IBAN (Regex): `frontend/src/lib/pii_client.js`

Anpassungen sind also Code-Änderungen — mit den zugehörigen Tests in
`backend/tests/unit/test_pii_scanner.py` bzw. `frontend/src/lib/pii_*.test.js`. Das
NER-Modell wird wie unter
[PII-NER-Modell aktualisieren](updates-und-wartung.md#pii-ner-modell-aktualisieren)
beschrieben aktualisiert.

> **Grenzen:** Gute deutsche NER erkennt vieles, aber nicht jeden kleingeschriebenen
> oder seltenen Namen — die Warnung ist ein Nudge, kein vollständiger Filter.

## Automatische Datenlöschung (Cron-Jobs)

Drei automatische Cron-Jobs laufen täglich. Zwei davon löschen veraltete Daten, der dritte ergänzt fehlende Embeddings:

| Job | Zeitplan | Was wird ausgeführt |
|-----|---------|-----------------|
| `cleanup_inactive_accounts` | täglich 02:00 Uhr | Nutzerkonten ohne Login seit 90 Tagen löschen (inkl. aller Konversationen) |
| `cleanup_stale_conversations` | täglich 02:30 Uhr | Konversationen ohne neue Nachrichten seit 93 Tagen löschen |
| `embedding_backfill` | täglich 03:15 Uhr | Embeddings für Knoten ohne Embedding nachgenerieren |

Die Löschung ist unwiederbringlich. Es gibt keine Wiederherstellungsfunktion.

Manuell ausführen (z. B. zur Überprüfung mit `--dry-run`):

```bash
docker compose exec backend python scripts/cleanup_stale_conversations.py --dry-run
docker compose exec backend python scripts/cleanup_inactive_accounts.py --dry-run
```

## De-Anonymisierung und Audit-Log

Für begründete Ausnahmefälle (z. B. richterliche Anordnung, Missbrauchsverdacht)
kann ein Admin über den Admin-Bereich ein Pseudonym seiner realen Nutzer-ID
zuordnen. Jeder De-Anonymisierungsvorgang wird im Audit-Log mit Zeitstempel
und handelnder Person protokolliert.

Die Aufbewahrungsdauer des Audit-Logs ist schulspezifisch. Empfehlung:
mindestens so lange wie die gesetzliche Aufbewahrungspflicht für
Schülerakten in Ihrem Bundesland.

## Hinweise für den Datenschutzbeauftragten

Die folgenden Aspekte sind für einen Auftragsverarbeitungsvertrag (AVV) mit
KI-Anbietern relevant:

- Verarbeitete Daten: ausschließlich Gesprächsinhalte (keine Personendaten)
- Pseudonym als technische Kennung ohne Personenbezug auf Anbieterseite
- Automatische Löschung spätestens nach 93 Tagen
- Kein Training auf Basis der Anfragen (von Anbietern vertraglich sicherstellen)
- Zusätzliche Datensparsamkeit: lokale PII-Eingabewarnung vor dem Senden
  (siehe oben) — kein externer Aufruf, keine Speicherung der geprüften Eingaben

> **Hinweis:** Diese Seite ist eine technische Orientierungshilfe und kein
> Ersatz für rechtliche Beratung.
