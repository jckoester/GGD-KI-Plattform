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

## Stundenplan-Integration (WebUntis)

Nur relevant, wenn `WEBUNTIS_SERVER` gesetzt ist. Einrichtung und Betrieb:
[Stundenplan-Integration](stundenplan-integration.md).

**Die Verarbeitung erweitert den Empfängerkreis nicht.** Lehrerpläne sind
kollegiumsöffentlich, Ausfälle und Vertretungen schulintern bekannt. Die Plattform liest
sie maschinell aus einer Quelle, die die Schule ohnehin betreibt, und zeigt sie denselben
Personen. Neu ist die Automatisierung, nicht der Zugang.

### Eintrag für das Verarbeitungsverzeichnis

| Feld | Angabe |
|---|---|
| **Zweck** | Automatische Übernahme von Wochenstunden, Ferien, Entfall, Vertretung und Verlegung in die Unterrichtsplanung der Lehrkräfte |
| **Betroffene** | Lehrkräfte der Schule. **Keine Schüler:innen** — das Servicekonto kann sie nicht aufzählen (vor Freischaltung mit `scripts/webuntis_probe.py` prüfen) |
| **Datenkategorien** | Lehrkraft-Kürzel; Unterrichtsstunden mit Datum, Stunde, Fach, Klasse, Raum; Status (regulär, entfallen, Vertretung, verlegt, Klausur) |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. e DSGVO i. V. m. dem Schulgesetz — Organisation des Unterrichts |
| **Empfänger** | Keine. Die Daten verlassen den Schulserver nicht; insbesondere gehen sie **nicht** an KI-Anbieter |
| **Herkunft** | WebUntis-Instanz der Schule, gelesen über ein technisches Servicekonto |
| **Löschfrist** | Kürzel und Abrufstatus: mit dem Konto nach 90 Tagen ohne Login. Übernommene Stundeneinträge: mit der Unterrichtsplanung der Gruppe |
| **TOM** | Zugangsdaten nur in der `.env` (ein schulweites Dienstkonto, keine persönlichen Zugänge); Fehlermeldungen der Quelle werden nie durchgereicht, da sie Zugangsdaten enthalten können |

### Was je Lehrkraft gespeichert wird

Nur zweierlei — beides pseudonym, beides mit dem Konto gelöscht:

| Ort | Inhalt |
|---|---|
| `user_preferences` | das Kürzel (z. B. `AK`), von der Lehrkraft selbst gesetzt und jederzeit entfernbar |
| `calendar_sync_status` | Zeitpunkt und Ergebnis des letzten Abgleichs |

**Das Kürzel wird nie an ein Sprachmodell übergeben.** Das ist nicht nur eine Zusage,
sondern durch einen Test abgesichert, der prüft, dass der Schlüsselname in den Chat-,
Kontext- und Pädagogik-Modulen nicht vorkommt.

Die Übernahme ist **freiwillig**: Ohne eingetragenes Kürzel ruft die Plattform für diese
Person nichts ab.

## Automatische Läufe (Cron-Jobs)

**Alle** nächtlichen Läufe, nicht nur die löschenden — wer wissen will, was der Server
nachts tut, findet es hier vollständig. Die Spalte **Löscht** sagt, welche davon Daten
entfernen.

⚠️ **Bis zum 25.09.2026 standen hier fünf von vierzehn.** Die Liste war nicht falsch,
nur unvollständig — und nichts erinnerte daran, sie mitzuziehen, wenn ein Lauf
dazukommt. Jetzt prüft ein Test sie gegen die `docker-compose.yml`
(`tests/unit/test_doku_deckt_wirklichkeit.py`).

| Job | Zeitplan | Löscht | Was wird ausgeführt |
|-----|---------|:--:|-----------------|
| `cleanup_inactive_accounts` | täglich 02:00 Uhr | ✅ | Nutzerkonten ohne Login seit 90 Tagen löschen (inkl. aller Konversationen) |
| `cleanup_stale_conversations` | täglich 02:30 Uhr | ✅ | Konversationen ohne neue Nachrichten seit 93 Tagen löschen |
| `cleanup_feedback` | täglich 02:50 Uhr | ✅ | Abgeschlossene Rückmeldungen 180 Tage nach dem Statuswechsel löschen |
| `embedding_backfill` | täglich 03:15 Uhr | — | Embeddings für Knoten ohne Embedding nachgenerieren |
| `auto_confirm_reviews` | täglich 03:45 Uhr | — | Nachbereitungen, die niemand bestätigt hat, automatisch abschließen |
| `cleanup_rendered_svg` | täglich 04:00 Uhr | ✅ | Zwischengespeicherte Server-Renderings räumen |
| `cleanup_generated_images` | täglich 04:30 Uhr | ✅ | Erzeugte Bilder nach Ablauf der Frist löschen |
| `cleanup_artifacts` | täglich 04:45 Uhr | ✅ | Abgelaufene Artefakte der Bibliothek löschen |
| `node_lifecycle` | täglich 05:00 Uhr | ✅ | Abgelaufene Bausteine archivieren, lange archivierte löschen |
| `weekly_budget_accrual` | montags 05:00 Uhr | — | Wochenguthaben zuteilen (idempotent; ein ausgefallener Lauf holt nach) |
| `sync_timetable` | Mo–Fr 05:30 Uhr | — | Stundenplan abgleichen: Entfall, Vertretung, Verlegung |
| `crisis_reminders` | täglich 06:00 Uhr | — | An unerledigte Krisenfälle erinnern, vor der Löschgrenze warnen |
| `refresh_ecb_rate` | monatlich, 1. um 06:00 Uhr | — | EZB-Wechselkurs EUR→USD holen |
| `monthly_team_reconcile` | monatlich, 1. um 07:00 Uhr | — | LiteLLM-Teams und Budgets abgleichen |

Die Löschung ist unwiederbringlich. Es gibt keine Wiederherstellungsfunktion.

### Was `node_lifecycle` tut — und was nicht

Zwei Schritte in einem Lauf (ADR-013), seit 0.8 überhaupt vorhanden: Bis dahin wurde ein
Ablaufdatum zwar erfasst und gespeichert, aber **nie ausgewertet**.

1. **Archivieren.** Bausteine mit überschrittenem Ablaufdatum wechseln auf „archiviert":
   raus aus Suche und Assistenten, für die Eigentümerin über das Archiv weiter
   erreichbar, Verknüpfungen bleiben. Kein Datenverlust — das ist eine Sichtbarkeits-,
   keine Löschentscheidung.
2. **Löschen.** Archivierte Bausteine verschwinden **nach drei Schuljahren** (1095 Tagen)
   endgültig. Drei Ausnahmen schützen davor:
   - **Importiertes bleibt.** Bildungsplan und Leitperspektiven (`write_scope = global`)
     werden nie automatisch gelöscht — sie werden beim Editionswechsel jahrgangsweise
     archiviert, und Curricula verweisen weiter darauf.
   - **Einzelne Bausteine lassen sich ausnehmen** (`metadata.loeschung_ausgesetzt: true`).
   - **Ohne Archivdatum keine Frist.** Was vor 0.8 archiviert wurde, trägt kein
     Archivierungsdatum und wird nicht angefasst.

Was der Lauf ausgerichtet hat, steht im Protokoll — mit Zahlen, auch für das
Übersprungene:

```bash
docker compose logs cron | grep node_lifecycle
# node_lifecycle archivieren: faellig=3 archiviert=3 dry_run=False
# node_lifecycle loeschen: faellig=4770 geloescht=0 geschuetzt_global=4770 …
```

Vorher ansehen, was er tun würde:

```bash
docker compose exec backend python scripts/node_lifecycle.py --dry-run
```

### Was die Kontolöschung abräumt

`cleanup_inactive_accounts` entfernt **dreizehn** Datenkategorien und macht **drei**
weitere personenbezugsfrei. Die Unterscheidung ist Absicht: Was nur der Person gehört,
fällt; was mit anderen geteilt wurde oder als Beleg gebraucht wird, verliert den
Personenbezug und bleibt.

| Tabelle | Was geschieht |
|---|---|
| `conversations` | gelöscht — samt Nachrichten, erzeugten Bildern und Krisen-Flags |
| `pseudonym_audit` | gelöscht — damit ist die Rückrechnung auf die Person endgültig unmöglich |
| `user_preferences` | gelöscht; darin auch das Stundenplan-Kürzel |
| `calendar_sync_status` | gelöscht — der Abrufstatus des Stundenplans |
| `personal_access_tokens` | gelöscht |
| `jwt_revocations` | gelöscht |
| `budget_accruals` | gelöscht — die Zuteilungshistorie des Wochenmodells |
| `artifacts` | gelöscht, Datenbankzeilen **und** Dateien — die Bibliothek ist strikt privat |
| `node_engagement` | gelöscht — persönlicher Lernzustand; der Zustand je Gruppe bleibt |
| `group_memberships` | gelöscht, alle Herkünfte |
| `teacher_group_exclusions` | gelöscht — die persönlichen Fach-Ausblendungen |
| `sso_group_offers` | gelöscht — offene Angebote betreffen nur diese Lehrkraft |
| `context_nodes` (privat) | gelöscht — `read_scope = private`, siehe unten |
| `context_nodes` (geteilt) | **bleibt**, `owner_pseudonym` wird `NULL` — sonst verschwänden Bausteine, mit denen eine Fachschaft arbeitet |
| `feedback` | **bleibt**, Pseudonym und Kontaktangabe fallen (siehe unten) |
| `group_join_codes.erstellt_von` | auf `NULL` — der Code gehört der Gruppe, nicht der Person |

⚠️ **Diese Tabelle wird geprüft, nicht gepflegt.** `test_pseudonym_deletion_coverage.py`
erzwingt für jede neue Tabelle mit Pseudonym-Spalte eine Entscheidung im **Code**, und
`test_doku_deckt_wirklichkeit.py` hält diese **Beschreibung** dagegen. Bis zum 25.09.2026
nannte sie fünf von dreizehn Kategorien — die Löschung geschah trotzdem vollständig, aber
eine Auskunft, die eine Kategorie verschweigt, ist falsch. Dieselbe Tabelle steht in
ADR-003 Teil 6; sie ist beim Ändern mitzuziehen.

Eine Tabelle behält ihre Zeilen: **Rückmeldungen** (`feedback`). Eine Fehlermeldung ist ein Befund über die Software, kein Kontodatum — sie zu löschen, weil die meldende Person die Schule verlassen hat, nähme der Sichtung die Vorgeschichte einer Regression. Der Personenbezug geht trotzdem: Pseudonym **und** die freiwillige Kontaktangabe werden geleert. Der Eintrag verschwindet damit auch aus „Meine Meldungen“.

> **Ausnahme Krisen-Aufbewahrung:** Hat das Konto eine geflaggte Konversation, die noch
> aufzubewahren ist (offen, in Prüfung, oder abgeschlossen vor weniger als 180 Tagen),
> wird das **gesamte** Konto übersprungen, bis die Frist endet.

### Krisenfälle: Erinnerung und Obergrenze

Ein **offener** Fall schützte die Konversation früher unbefristet. Seit 09/2026 gilt
eine Obergrenze — mit Vorwarnung:

| Frist | Vorgabe | Einstellung |
|---|---|---|
| Erinnerung an unerledigte Fälle | nach 7 Tagen, danach wöchentlich | `CRISIS_REMINDER_DAYS` |
| Letzte Warnung vor der Löschung | 14 Tage vorher | `CRISIS_FINAL_WARNING_DAYS` |
| Obergrenze für offene Fälle | 365 Tage ab Eingang | `CRISIS_MAX_OPEN_DAYS` |

Den Ablauf steuert `scripts/crisis_reminders.py` (täglich, in der Compose bereits
eingetragen). Ein Probelauf zeigt, was verschickt würde, ohne etwas zu ändern:

```bash
docker compose exec backend python scripts/crisis_reminders.py --dry-run
```

> ⚠️ **Läuft dieser Cron nicht, wird nichts gelöscht.** Der Schutz eines offenen
> Flags endet nur, wenn mindestens einmal erinnert wurde — sonst würde ohne jede
> Vorwarnung gelöscht. Die sichere Richtung, aber sie heißt auch: Ein vergessener
> Cron-Eintrag führt still zu wachsendem Bestand. Der Probelauf oben zeigt, ob der
> Lauf greift.

### Benachrichtigung per E-Mail

Ohne Konfiguration wird **nichts versendet**; der Inhalt landet im Log. Für den
Produktivbetrieb ist das zu wenig — `scripts/check_production.py` meldet es deshalb
als Fehler.

```
SMTP_HOST=mail.schule.de
SMTP_PORT=587
SMTP_USER=…
SMTP_PASSWORD=…
SMTP_FROM=ki@schule.de
SMTP_STARTTLS=true
CRISIS_NOTIFY_TO=["krisenteam@schule.de","schulleitung@schule.de"]
CRISIS_REVIEW_NOTIFY_TO=["schulsozialarbeit@schule.de"]
FEEDBACK_NOTIFY_TO=["ki-admin@schule.de"]
```

> `FEEDBACK_NOTIFY_TO` gehört **nicht** zu den Krisenadressen (ADR-020): Eine
> Rückmeldung ist eine Fehlermeldung, kein Hinweis auf eine Notlage. Leer ist hier —
> anders als oben — ein zulässiger Betriebszustand. Was in dieser Mail steht:
> Kategorie, Rolle, Version und die ersten 200 Zeichen; **nicht** Pseudonym,
> Kontaktangabe oder ein angehängter Chat. Siehe [Rückmeldungen sichten](feedback.md).

**Warum die Empfänger in der Konfiguration stehen und nicht in der Datenbank:** Die
Plattform kennt keine E-Mail-Adressen. Nur Pseudonyme verlassen die Anmeldung — es
gibt niemanden nachzuschlagen. Adressiert wird ein gemeinsames Postfach der
Zuständigen; mehrere Adressen, weil ein einzelnes Postfach in den Ferien oder bei
Krankheit niemanden erreicht.

**Was in der Mail steht:** die Zahl der unerledigten Fälle, das Alter des ältesten und
ein Link auf `/flags`. **Nicht** Person, Kategorie oder Inhalt — ein Postfach kennt
keine Zweitfreigabe, und eine weitergeleitete Mail liefe am Vier-Augen-Verfahren
vorbei. Die Adressen stehen in `Bcc`, damit eine Weiterleitung nicht verrät, wer
sonst noch zuständig ist.

Bei vielen Treffern in kurzer Zeit verschickt nur der **erste** eine Nachricht
(Fenster: eine Stunde). Zwanzig Mails an dasselbe Postfach sind keine zwanzigfache
Aufmerksamkeit.

#### Zwei Listen, und warum sie verschieden sein sollten

`CRISIS_NOTIFY_TO` erreicht, wer **Fälle bearbeitet**. `CRISIS_REVIEW_NOTIFY_TO`
erreicht, wer eine Einsicht **zweitfreigibt** — die Personen mit der Rolle `review`.

| Anlass | Geht an | Rhythmus |
|---|---|---|
| neuer Krisenhinweis | `CRISIS_NOTIFY_TO` | höchstens eine je Stunde |
| unerledigte Fälle | `CRISIS_NOTIFY_TO` | ab 7 Tagen, danach wöchentlich |
| Fälle vor der Löschgrenze | `CRISIS_NOTIFY_TO` | 14 Tage vorher |
| neuer Einsicht-Antrag | `CRISIS_REVIEW_NOTIFY_TO` | jeder Antrag |
| wartende Anträge | `CRISIS_REVIEW_NOTIFY_TO` | ab 7 Tagen, danach wöchentlich |

Das Vier-Augen-Prinzip (ADR-008 Teil 6) lebt davon, dass beantragende und freigebende
Person verschieden sind. Landen beide Mails im selben Postfach, ist das technisch
erlaubt — die Startprüfung **warnt** dann, lehnt es aber nicht ab, weil es an einer
kleinen Schule die einzige Möglichkeit sein kann. Bleibt
`CRISIS_REVIEW_NOTIFY_TO` leer, gibt es **keinen** stillen Rückfall auf die andere
Liste; stattdessen meldet `check_production.py` einen Fehler. Ein wartender Antrag
blockiert die Bearbeitung des Falls, und die Zuständigen sähen ihn sonst nur, wenn
sie sich anmelden (Zähler am Avatar).

Der Antrag löst die Mail **ohne** Dämpfung aus: Je Flag lässt die Plattform nur einen
aktiven Antrag zu, und beantragen darf allein die Admin-Rolle — eine Flut kann hier
nicht entstehen, eine Dämpfung verschlucke also echte Fälle.

#### Bausteine: gelöscht oder anonymisiert

Bei den eigenen Wissensbausteinen entscheidet die **Sichtbarkeit**, nicht das Eigentum:

| `read_scope` | Was geschieht |
|---|---|
| `private` | wird mit dem Konto **gelöscht** |
| alles andere (`group`, `subject`, `school`, `global`) | bleibt bestehen, `owner_pseudonym` wird auf `NULL` gesetzt |

Was nie jemand anders sehen konnte, verschwindet: Löschen zerstört dort nichts
Gemeinsames. Ein Arbeitsblatt dagegen, das eine Klasse liest, oder ein Methodenblatt der
Fachschaft verschwinden zu lassen, risse in fremde Planungen Löcher, die niemand mehr
erklären kann. Diese Bausteine bleiben und verlieren nur den Namen — das Arbeitsergebnis
gehört der Schule, der Personenbezug nicht.

> **Folge für die Pflege:** Ein anonymisierter Baustein mit `write_scope = private` hat
> keine Eigentümerin mehr — nur noch Admins können ihn ändern. Der `write_scope` wird
> bewusst **nicht** angehoben, weil das eine stille Rechteausweitung wäre.

#### Die Bibliothek geht mit dem Konto

Artefakte haben eine **eigene** Frist (`expires_at`, bei Lehrkräften bis zu zwei Jahre).
Trotzdem gewinnt die Kontolöschung: Die Bibliothek ist strikt privat — die Liste filtert
auf die Eigentümerin, der Abruf einer fremden Datei wird abgewiesen. Damit gilt dieselbe
Regel wie für einen privaten Baustein. Bis 09/2026 überlebten Artefakte das Konto samt
Pseudonym bis zum Fristende.

Gelöscht werden Zeile **und Datei**. Die Dateien fallen erst nach einem erfolgreichen
Commit; bricht die Löschung ab, bleiben sie liegen und der nächste Lauf nimmt sie mit.

> **Folge für übernommene Bausteine:** Ein Baustein, der aus einem Artefakt entstanden
> ist, trägt dessen ID als Herkunftsnotiz. Ist der Baustein geteilt, bleibt er (ohne
> Namen) bestehen und verweist dann auf ein Artefakt, das es nicht mehr gibt. Das ist
> beabsichtigt — die Herkunft ist eine Notiz, kein Fremdschlüssel.

**Seit 09/2026 gibt es keine ungeklärten Fälle mehr.** Jede Tabelle mit Pseudonym-Spalte
hat eine getroffene Entscheidung; ein Test
(`backend/tests/unit/test_pseudonym_deletion_coverage.py`) hält den Stand fest, verlangt
für jede **neue** Tabelle eine ausdrückliche Entscheidung und schlägt an, sobald wieder
ein Fall als „offen" markiert wird.

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
