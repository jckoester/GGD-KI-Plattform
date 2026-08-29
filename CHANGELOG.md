# Changelog

Alle nennenswerten Änderungen an der GGD-KI-Plattform. Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (0.x = vor dem ersten Stable-Release).

## [Unreleased]

### Geändert

- **Zu einem erzeugten Bild wird das tatsächlich genutzte Modell gespeichert**, nicht mehr
  das global eingestellte.

- **Embeddings werden im Stapel erzeugt** (`EMBEDDING_BATCH_SIZE`, Default 64) statt eine
  Anfrage je Knoten. Gemessen gegen BGE-M3: 0,8 → 33 Knoten/s.
- **Der Titel geht ins Embedding ein, wo er eigene Information trägt.** Knoten ohne
  Inhalt wurden bisher übersprungen und waren für die semantische Suche unsichtbar
  (im Bestand 125 Leitideen). Bei Kompetenzen, deren Titel nur der Inhalt plus
  Gliederungsnummer ist, ändert sich nichts.
- **Die Drosselung des Backfills ist konfigurierbar** (`EMBEDDING_TOKENS_PER_SECOND`,
  Default 3000, `0` = aus) und taktet nach dem abgerechneten Verbrauch statt nach einer
  festen Schätzung von 150 Tokens je Knoten. Die lag bei langen Knoten um Faktor 30
  daneben (15.000 Zeichen = 4500 Tokens).
- **Der Embedding-Backfill zählt Anfragen statt Knoten**, bevor er abbricht: drei
  vollständig fehlgeschlagene Stapel in Folge statt zehn Knoten.
- Scheitert ein Stapel mit `400`, fasst der Backfill die Texte einzeln nach — ein
  unbrauchbarer Text reißt die übrigen nicht mehr mit.

### Neu

- **Nachvollziehbar, womit eine Antwort erzeugt wurde.** Bisher speicherte die Plattform nur
  den schulinternen Aliasnamen (`chat-standard`) — für eine Quellenangabe in GFS,
  Seminarkurs oder Facharbeit wertlos. Jetzt steht daneben das Anbietermodell
  (`gpt-oss-120b`), aufgelöst **beim Schreiben**: Ein späteres Umhängen des Alias
  verfälscht alte Antworten nicht mehr.

  - Im Chat unter jeder Antwort der Knopf **„Herkunft"** — standardmäßig verborgen, für alle
    erreichbar. Bilder haben eine eigene Angabe; sie stammen aus einem anderen Modell.
  - **„Angaben zum Zitieren kopieren"** legt Werkzeug, Modell, Datum und die eigene Eingabe
    als Textbaustein bereit. Der Bild-Prompt ist ausdrücklich als *vom Sprachmodell
    formuliert* gekennzeichnet — als eigene Eingabe zitiert wäre er eine Falschangabe.
  - In der **Bibliothek** dauerhaft sichtbar, mit eigenem „Zitieren"-Knopf. Die Angabe wandert
    beim Speichern mit und überlebt die Konversation.
  - Optional eine **Herkunftszeile am Ende exportierter Dokumente** (PDF/Word/ODT),
    schulweit unter *Einstellungen → Export-Vorlagen* schaltbar. Vorgabe: aus.

  Für Inhalte von vor diesem Update bleibt die Angabe leer — welcher Alias damals auf welches
  Modell zeigte, ist nicht rekonstruierbar, und ein geratener Wert wäre in einer
  Quellenangabe schlimmer als eine Lücke.

- **Mehrere Bildmodelle gleichzeitig nutzbar.** Eine **Bildart** (`config/image_models.yaml`)
  bündelt ein Bildmodell mit den Formaten, die es beherrscht, und einem Namen, den Menschen
  verstehen. Assistenten lassen sich im Editor auf einzelne Bildarten festlegen; ohne Auswahl
  gelten alle. Fehlt die Datei, entsteht aus den bisherigen `IMAGE_*`-Variablen eine einzige
  Bildart und nichts ändert sich.

  - Führt ein Assistent genau eine Bildart, hat das Werkzeug **keinen** Auswahlparameter.
    Bei mehreren wählt das Chat-Modell anhand von Bezeichnung und Beschreibung.
  - Bildarten, deren Modell für den Jahrgang nicht freigeschaltet ist, erscheinen im Werkzeug
    gar nicht erst. Ist der Freigabestand nicht abrufbar, wird nicht gefiltert.
  - Der Assistenten-Editor warnt beim Bearbeiten, wenn eine gewählte Bildart für die
    Zielgruppe nicht freigeschaltet ist.
  - Ein Format, das die gewählte Bildart nicht kennt, wird auf das nächstliegende
    Seitenverhältnis abgebildet statt abgelehnt; das Chat-Modell nennt die Abweichung.
  - Lehnt der Proxy ab, erscheint statt „Bildgenerierung fehlgeschlagen" ein Satz, der die
    Ursache nennt (nicht freigeschaltet / Budget aufgebraucht).
  - **Noch einmal versuchen:** Ein Symbol am Bild erzeugt einen neuen Versuch mit derselben
    Beschreibung und Bildart, ohne den Chat erneut zu bemühen. Lehrkräfte sehen zusätzlich,
    welche Bildart verwendet wurde.

- **Vorlage für den EU-Betrieb:** `infra/litellm_config.ionos.example.yaml` mit fünf
  Chat-Stufen, Systemmodellen, Embedding und Bild — Modell-IDs, Fähigkeiten und Preise
  gegen den IONOS-Katalog gemessen.
- **`scripts/ionos_probe.py`** fragt Katalog, Function-Calling, Vektorbreite und Bildformat
  direkt beim Anbieter ab — die vier Angaben, die sich nicht der Dokumentation entnehmen
  lassen.
- **`scripts/bildpreis_probe.py`** misst über einen eigens angelegten Virtual Key, ob und
  wie ein Bildmodell abgerechnet wird: gebuchter Betrag je Größe, Header gegen SpendLog,
  Belastung des Budgets, Vergleich mit dem Tarif des Anbieters. Prüft zusätzlich anhand
  der Bildbytes, ob die bestellte Größe geliefert wurde.
- **Der Jugendschutz-Guardrail fällt nicht mehr blind offen aus.** Bei Störung des
  Klassifikators greift eine Staffel: Wiederholung (`classifier_retries`), optionaler
  zweiter Klassifikator (`fallback_classifier_model`), und wenn beides nichts liefert,
  entscheidet das Team — Lehrkräfte arbeiten weiter, Schüler:innen bekommen die Antwort
  zurückgehalten (`fail_open_teams`). Ein unbekanntes Team gilt als schutzbedürftig.
- **Betriebszustand des Klassifikators sichtbar.** Der Guardrail schreibt einen
  Zählerstand (`health_file`), das Backend liefert ihn unter `/api/admin/guardrail/health`,
  die Seite *Einstellungen → Guardrail* zeigt ihn an. Erfolgreiche Wiederholungen werden
  getrennt gezählt und geloggt — sie deuten auf Latenz hin, nicht auf einen Ausfall.
  Ein liegengebliebener Bericht (Proxy gestoppt, gemeinsame Ablage weg) gilt nach
  `GUARDRAIL_HEALTH_MAX_AGE_H` als veraltet und **nicht** mehr als gesund.
  **Benachrichtigungen verschickt die Plattform nicht**; der Endpunkt gehört in die
  Server-Überwachung — auf `available: false`, `stale: true` und steigende Ausfallzahlen.

  > Der Proxy läuft in einem eigenen Compose-Stack: Beide Seiten müssen dasselbe
  > **Host**-Verzeichnis einbinden. Auf getrennten Hosts entfällt die Datei; dann über das
  > Proxy-Log überwachen (siehe `docs/admin/content-moderation.md`).

### Entfernt

- **Der lokale Ollama-Fallback entfällt — es gibt keinen Rückfall bei erschöpftem Budget.**
  Budget aufgebraucht heißt: keine Nutzung bis zum nächsten Zeitraum. Ein Klassensatz
  gleichzeitiger Anfragen verlangt grob 800 Token/s, ein Server ohne GPU liefert für ein
  8B-Modell 10–20 — als Zusage an alle Schulen war das nicht haltbar.

  Entfallen sind `ollama-fallback` aus den LiteLLM-Vorlagen und `OLLAMA_BASE_URL` aus der
  `.env`. **Bestehende Installationen müssen nichts tun:** Wer den Eintrag behalten will,
  behält ihn, und die Preisprüfung nimmt lokale Modelle weiterhin von der Preispflicht aus —
  jetzt anhand des Anbieters statt des Modellnamens. Schulen mit passender Hardware tragen
  ein lokales Modell also weiterhin selbst ein; mitgeliefert und versprochen wird keins.

### Behoben

- **Der Gesprächstitel war manchmal die Antwort statt der Titel.** Bei imperativ
  formulierten Eingaben („Erkläre mir …", „Erzeuge ein Bild: …") befolgte das Titelmodell
  die Anweisung, statt sie zu betiteln — im schlimmsten gemessenen Fall mit einer 168
  Wörter langen Erklärung, die die Historie abschnitt. Die Nutzernachricht wird jetzt als
  **Zitat** übergeben, nicht als Anweisung. Über vier Anbieter nachgemessen: drei Modelle
  deutlich besser (Claude Haiku 1/4 → 4/4), keines schlechter.

- **Bildgenerierung lief am EUR-Budget vorbei.** LiteLLM löst Bildpreise ausschließlich über
  seine eingebaute Preistabelle auf und ignoriert das `model_info` des Deployments — selbst
  eingetragene Bildmodelle wurden mit 0,00 $ abgerechnet. Der neue Callback
  `guardrails.bildpreise.registrierung` trägt die Preise aus `IMAGE_PRICES` beim Proxy-Start
  in ebendiese Tabelle ein; danach rechnet LiteLLM selbst, und Kostenheader, SpendLog,
  Budget-Durchsetzung und Statistik stimmen ohne Sonderweg im Backend zusammen.
- **Jugendschutz: Drogen-Anleitungen wurden von nichts geprüft.** Der zuständige Guardrail
  nutzte den Typ `regex`, den es seit LiteLLM 1.83.7 nicht mehr gibt — der Proxy startete
  damit nicht einmal. Ersetzt durch die Kategorie `drug_instructions` im LLM-Klassifikator;
  Chemieunterricht, Suchtprävention und Pharmakologie bleiben unbeanstandet.
- **Die Guardrail-Vorlagen starteten nicht.** Der `guardrails:`-Block stand unter
  `litellm_settings`, wo LiteLLM das alte Format erwartet. Jetzt auf oberster Ebene.
- **Kategorien und Schwellen der Guardrails waren wirkungslos.** Sie standen unter
  `guardrail_info.params`, das kein Guardrail-Typ liest. Der Klassifikator liest sie aus
  `litellm_params.thresholds`.
- **Startskript des LiteLLM-Proxys** verlangte fest `OPENAI_API_KEY`. Es prüft jetzt die
  Variablen, die die gewählte Config referenziert, und startet aus `infra/` — Guardrail-
  Module und Pattern-Dateien werden relativ zum Arbeitsverzeichnis aufgelöst.
- **Eine einmal gesetzte `embedding_error`-Marke blieb stehen**, auch nachdem der Knoten
  längst eingebettet war. Die Diagnoseabfrage zählte dadurch erledigte Fälle mit.
- **`infra/litellm_config.example.yaml` verwies den Proxy auf die Datenbank der Anwendung**
  (`DATABASE_URL` statt `LITELLM_DATABASE_URL`). Jetzt korrekt, dazu `store_model_in_db`.
- **Die Modell-Vorgaben in `.env.example` passten nicht zur mitgelieferten LiteLLM-Vorlage:**
  `EMBEDDING_MODEL` und `IMAGE_DEFAULT_MODEL` standen auf Produktnamen, die Vorlage führt
  Aufgabennamen. Wer beide Dateien kopierte, bekam bei Einbettung und Bildgenerierung
  „model not found".

### Dokumentation

- Neues Kapitel [Vor der Installation](docs/admin/vor-der-installation.md) — schulische
  Vorüberlegungen, bisher gefüllt mit **Modellempfehlungen**: gemessene Preise und
  Fähigkeiten je IONOS-Modell, dazu die drei Anforderungen, die still scheitern
  (Function-Calling, Preis in der Config, Anweisungstreue).
- [Konfiguration](docs/admin/konfiguration.md): Env-Tabelle nach Themen gegliedert und
  vervollständigt — 24 Variablen fehlten, `STUDENT_GRADES` hieß längst
  `PUBLIC_STUDENT_GRADES`. LiteLLM-Abschnitt auf das Namensschema umgestellt.
- [Modelle & Assistenten](docs/admin/modelle-und-assistenten.md): Stufenschema
  (`chat-schnell` … `chat-komplex`, `system-*`) mit Zweck und empfohlener Freigabe.
- [Content-Moderation](docs/admin/content-moderation.md): Klassifikator statt
  `openai_moderation`, Verhalten bei Störungen, Überwachung, Ablage des Zustandsberichts.
- **`infra/litellm_config.example.yaml` auf das Aufgaben-Namensschema umgestellt.** Die
  Vorlage führte rohe Produktnamen (`gpt-4o-mini`, `gpt-image-1`) als `model_name` —
  wer sie kopierte, hatte `MODEL_PICKER_HIDDEN_PREFIXES` wirkungslos und das
  Titelmodell sichtbar im Dropdown der Schüler:innen. Jetzt `chat-schnell` …
  `system-titel`, `embedding-standard`, `bild-standard`, mit Begründung im Kopf.
- Neues Kapitel [Modell-Szenarien](docs/admin/modell-szenarien.md) — vollständige
  Konfigurationen für IONOS, Mistral, OpenAI, Anthropic und Mischbetrieb, dazu eine
  Abdeckungsmatrix (welcher Anbieter kann Chat, Embedding, Bild) und die acht
  anbieterspezifischen Fallen, die still scheitern.
- Neues Nutzerkapitel [KI-Ergebnisse zitieren](docs/user/zitieren.md) — welche Angaben eine
  Quellenangabe braucht und wo sie in der Oberfläche stehen.
- [Modell-Szenarien](docs/admin/modell-szenarien.md): Abschnitt *Was gespeichert wird — und
  was zitierfähig ist* (Alias gegen Anbietermodell).
- [Vor der Installation](docs/admin/vor-der-installation.md): Messwerte für **Mistral**
  (acht Modelle), **OpenAI** (vier) und **Anthropic** (drei) — Preise, Funktionsaufrufe,
  Titeltreue und Antwortzeiten. Damit sind alle vier Anbieter geprüft; die Empfehlungen
  beruhen nirgends mehr auf Annahmen.
- [Dev-Setup](docs/dev/dev-setup.md): Beispiel-`.env` und `curl` auf Aufgaben-Namen.
- [Installation](docs/admin/installation.md) um die Modellkonfiguration ergänzt: neuer
  **Schritt 3** (Anbieter wählen, `model_list` befüllen, Namen in die `.env`) und
  **Schritt 9** (`check_litellm_config.py` gegen den laufenden Proxy). Die Kopierliste in
  Schritt 2 nennt jetzt alle `config/*.yaml` — `subjects.yaml` fehlte, obwohl das
  Fächer-Seed sie braucht. Schrittnummern durchgezählt (es gab keinen Schritt 6).

### Migration

- **`alembic upgrade head`** — Migrationen `0047`–`0050`: `assistants.image_kinds`,
  `generated_images.bildart`, sowie `provider_model` an `messages`, `generated_images` und
  `artifacts`. Bestandsassistenten behalten mit dem
  Standardwert ihr bisheriges Verhalten; bereits erzeugte Bilder lassen sich mangels
  gespeicherter Bildart nicht variieren.

- ⚠️ **Modellnamen auf Aufgabennamen umstellen.** Wer in `infra/litellm_config.yaml` noch
  rohe Produktnamen als `model_name` führt (`gpt-4o-mini`, `text-embedding-3-small`,
  `gpt-image-1`), benennt sie um; anschließend die `.env` nachziehen:

  | `.env` | Wert |
  |---|---|
  | `CHAT_DEFAULT_MODEL` | `chat-standard` |
  | `TITLE_MODEL` | `system-titel` |
  | `EMBEDDING_MODEL` | `embedding-standard` |
  | `IMAGE_DEFAULT_MODEL` | `bild-standard` |

  **Danach die Freigabematrix unter `/settings/models` neu setzen** — die Team-Allowlists
  in LiteLLM enthalten die alten Namen und laufen sonst ins Leere. Ebenso prüfen:
  Assistenten, die auf einen expliziten Modellnamen festgelegt sind. Ein reiner
  Namenswechsel berührt die Embedding-Vektoren **nicht**, solange `litellm_params.model`
  gleich bleibt.

  Fertige `model_list`-Blöcke je Anbieter: [Modell-Szenarien](docs/admin/modell-szenarien.md).
  Begründung und Stufenschema: [Modelle & Assistenten](docs/admin/modelle-und-assistenten.md).
  Kontrolle: `python scripts/check_litellm_config.py`.

- ⚠️ **Die eigene `infra/litellm_config.yaml` muss angepasst werden.** Drei Dinge, die
  bisher stillschweigend nicht griffen oder ab LiteLLM 1.83.7 den Proxy-Start verhindern:

  | Prüfen | Warum |
  |---|---|
  | `guardrails:` steht unter `litellm_settings:` | Proxy startet nicht (`GuardrailItem() argument after ** must be a mapping`) — Block auf die oberste Ebene heben |
  | `guardrail: regex` | Typ existiert nicht mehr, Proxy startet nicht — Drogen-Anleitungen deckt jetzt die Kategorie `drug_instructions` des Klassifikators ab |
  | Kategorien/Schwellen unter `guardrail_info.params` | Wurden nie gelesen — gehören unter `litellm_params.thresholds` |

  Vorlagen: `infra/litellm_config.example.yaml` (allgemein) und
  `infra/litellm_config.ionos.example.yaml` (EU-Betrieb).

- **Neue Variablen in der `.env`** — beide optional, aber empfohlen:
  - `IMAGE_PRICES` — **Pflicht**, sobald Bildmodelle im Einsatz sind, die LiteLLM nicht aus
    seiner eingebauten Preistabelle kennt. Ohne sie kostet jedes Bild 0,00 $. In
    **einfachen** Anführungszeichen setzen.
  - `GUARDRAIL_HEALTH_FILE` / `GUARDRAIL_HEALTH_MAX_AGE_H` — für die Zustandsanzeige. Muss
    auf dieselbe Datei zeigen wie `health_file` in der LiteLLM-Config.
  - `IMAGE_MODELS_PATH` — nur nötig, wenn die Bildarten-Datei woanders liegt. Wer mehr als
    ein Bildmodell nutzen will, legt sie aus `config/image_models.example.yaml` an; sie löst
    `IMAGE_DEFAULT_MODEL`, `IMAGE_SIZES`, `IMAGE_DEFAULT_FORMAT` und `IMAGE_RESPONSE_FORMAT`
    ab. Jedes dort genannte Modell braucht einen Eintrag in `IMAGE_PRICES`.

- **Nach dem Update einmal `python scripts/embedding_backfill.py` laufen lassen.** Die
  Titel-Aufnahme betrifft Leitideen, Kapitel und PK-Gruppen; Kompetenzknoten behalten
  ihren bisherigen Vektor. Betroffene Knoten neu einbetten:

  ```sql
  UPDATE context_nodes SET embedding = NULL
   WHERE status = 'active' AND content_type IN ('leitidee', 'kapitel', 'pk_gruppe');
  ```

- **Nur bei Anbieterwechsel:** Ein anderes Embedding-Modell heißt fast immer eine andere
  Vektorbreite — dann Spalte umstellen und **alle** Knoten neu einbetten.
  Ablauf: [Runbook Modellwechsel](docs/runbooks/modellwechsel.md).

## [0.6.2] – 2026-08-26

### Behoben

- **Formeln in Kompetenztiteln blieben Quelltext.** Bildungsplan-Kompetenzen führen ihre
  Formeln im Titel (`… die Zahl \(\pi\) …`); angezeigt wurde die TeX-Notation. Betrifft
  Bildungsplanansicht, Knotenansicht, IK-/PK-Auswahl, Knotenliste und die
  Kontextknoten im Chat.
- **PDF-Export rendert `\(…\)` und `\[…\]`.** Die Export-Pipeline kannte nur `$…$`; bei der Klammer-Notation verschwand zusätzlich der Backslash, sodass `(\pi)` im PDF stand.
  Betrifft Curriculum-, Stunden- und Dokument-Export.
- **Kompetenztitel im Curriculum- und Stunden-PDF** liefen am Formel-Rendering vorbei.
    
## [0.6.1] – 2026-08-26
    
### Behoben
    
- **Embeddings: `429` und `503` werden wiederholt** statt als endgültiger Fehler behandelt. Wartezeit nach `Retry-After`, sonst exponentiell; begrenzt durch `EMBEDDING_MAX_RETRIES` und `EMBEDDING_RETRY_MAX_WAIT_S`. Andere Fehler werden weiterhin sofort gemeldet.
- **Der Embedding-Backfill bricht nach zehn Fehlschlägen in Folge ab** (`ABBRUCH:` im
  Log) statt bei gestörtem Modellzugang alle offenen Knoten durchzuarbeiten. Nicht
  versuchte Knoten bleiben ohne Vektor und kommen im nächsten Lauf wieder dran.

### Dokumentation

- [Updates & Wartung](docs/admin/updates-und-wartung.md): neue Abschnitte **Redis für
  LiteLLM** (Vorlage: `infra/litellm-redis.example.yml`) und **Embeddings: Knoten ohne
  Vektor** — Fehlertext abfragen und deuten.
- Klarstellung: Der LiteLLM-Proxy läuft in einem eigenen Compose-Stack.
  `docker compose … litellm` gehört ins LiteLLM-Verzeichnis,
  `docker compose exec db psql -d ggd_ki` ins Anwendungsverzeichnis.

### Migration

- Keine Datenbank-Migration nötig.
- `EMBEDDING_MAX_RETRIES` (3) und `EMBEDDING_RETRY_MAX_WAIT_S` (5.0) sind optional; ohne
  `.env`-Änderung ändert sich nichts. `EMBEDDING_MAX_RETRIES=0` = bisheriges Verhalten.
- Nach dem Update prüfen, ob Knoten ohne Vektor liegengeblieben sind:

  ```bash
  docker compose exec db psql -U postgres -d ggd_ki -c \
    "SELECT count(*) FILTER (WHERE embedding IS NULL)            AS ohne_vektor,
            count(*) FILTER (WHERE metadata ? 'embedding_error') AS mit_fehlermarke
       FROM context_nodes WHERE status = 'active';"
  ```

  Deutung des Fehlertexts: [Updates & Wartung](docs/admin/updates-und-wartung.md),
  Abschnitt *Embeddings: Knoten ohne Vektor*.

## [0.6.0] – 2026-08-26

Schwerpunkt: **Bildungsplan V3.** Sie gilt ab August 2026 in den Klassen 5–7 und wächst
jahrgangsweise nach oben; die Klassen darüber bleiben auf der Vorgängerfassung. Beide
Fassungen liegen dafür gleichzeitig vor. Der Produktiv-Rollout ist nicht Teil des Updates
(siehe *Migration*).

### Neu

- **Scraper und Import für die neue Seitengeneration (GEN2X)**, unter der der V3-Plan
  liegt. Welche Generation ein Fach hat, steht in `config/subjects.yaml`
  (`seitengeneration: gen2x`, `quell_version`). Ein Lauf holt Basis-, V2- und V3-Fassung.
- **Operatoren und Leitperspektiven** werden aus den neuen Seiten mitgelesen.
- **Der Scraper prüft die geladene Fassung** und weist die Seite ab, wenn die Adresse
  eine andere liefert. **Doppelte Kennungen brechen den Import ab.**
- **Die geltende Fassung wird berechnet** aus Editions-Fahrplan (`subjects.yaml`),
  Schuljahr (`school_year.yaml`) und importiertem Bestand. Fehlt eine Fassung für ein
  Fach, gilt die vorige weiter; die Umstellung geschieht selbsttätig.
- **Die semantische Suche im Chat unterscheidet die Fassungen.** Mit Gruppenbezug zählt
  die Klassenstufe, ohne ihn bleibt je Kompetenz der ähnlichste Treffer.
- **Auswahllisten ohne Jahrgangsbezug nennen die Fassung**, wo dieselbe Nummer mehrfach
  vorkommt.
- **Kontextknoten im Chat zeigen das Fach** statt des Knotentyps; der Typ steht im
  Tooltip und bleibt sichtbar, wo es kein Fach gibt. Erwähnungsliste, Vorschläge und
  Chips sind vereinheitlicht, der rohe Schlüssel (`ik_kompetenz`) ist durch die lesbare
  Bezeichnung ersetzt.

### Geändert

- **Englisch und Französisch laufen ab V3 über den normalen Scrape**; die Basisfassung
  kommt dabei mit. Nur die V2-Fassung bleibt PDF-basiert.

  > Solange `bildungsplan_pdf_url` gesetzt ist, überspringt der Scraper das Fach — als
  > INFO, nicht als Warnung. Ein `bildungsplan_suffix: ".V3"` bleibt dann wirkungslos.

- **Der Import meldet Ausgabedateien zu Fächern, die nicht in `subjects.yaml` stehen**
  (Warnung mit Dateinamen, kein Abbruch).
- **Das Warnungs-Log entsteht je Lauf** statt über den Tag zu wachsen.
- **Englisch, Musik, Sport und ev. Religion enden bei Klasse 12** statt 13. Klasse 13
  hielt sonst die Ausgangsfassung schulweit aktiv.

### Behoben

- Vierstufige Kompetenznummern (`3.2.1.1`) gingen verloren — betraf Physik, Chemie,
  Geographie.
- Physik: Die beiden Basisfach-Züge der Kursstufe überschrieben einander.
- Fächer ohne V2-Fassung wurden ganz übersprungen; eine fehlende Zwischenfassung ist
  jetzt eine Warnung.
- Querverweise zwischen Fächern liefen ins Leere (vier Ursachen: vierteilige
  Sprungmarken, Verweise ohne Sprungmarke, fehlgedeutete Fachzuordnung, Verweise auf
  prozessbezogene Kompetenzen).
- Verweise auf prozessbezogene Kompetenzen zeigten auf ein fremdes Fach — die Auflösung
  filterte nicht nach Fach. Ein erneuter Import räumt den Altbestand auf.

### Dokumentation

- [Bildungsplan-Import (Runbook)](docs/runbooks/bildungsplan-import.md): neue Abschnitte
  zur Seitengeneration, zum Log je Lauf und zu den Fremdsprachen.
- [Bildungsplan-Import (Admin)](docs/admin/bildungsplan-import.md): **Mehrere Fassungen
  gleichzeitig — der Normalfall**; Gründe für nicht auflösbare Querverweise.
- `config/subjects.example.yaml` zeigt die V3-Konfiguration vollständig.

### Migration

- Keine Datenbank-Migration nötig.
- **Der V3-Rollout ist ein eigener Vorgang.** Nötig: `config/subjects.yaml` um die
  V3-Angaben ergänzen (Vorlage: `subjects.example.yaml`), `config/school_year.yaml` auf
  `2026/27`, dann Scrape und Import — vorher mit `--dry-run` prüfen.
- **Erwartet:** Ein Fach, das erst oberhalb der V3-Klassen beginnt (etwa Chemie ab
  Klasse 8), bekommt seinen V3-Plan sofort wieder archiviert. Er kommt beim Import des
  Folgejahres zurück.
- **`E1_V2.jsonl`/`F2_V2.jsonl` bleiben gültig** — kein erneuter PDF-Lauf nötig. Der
  Scraper überschreibt sie nicht; erwartete Meldung: `E1: Zwischenedition '.V2' nicht
  vorhanden`. Zwei Bedingungen: Die Dateien liegen in `scripts/scraper/output/`, und das
  Ausgabeverzeichnis wird vor dem Scrape **nicht geleert**.
- **Auch ohne V3-Rollout lohnt ein Neu-Import der bestehenden Fassungen** — er korrigiert
  die fachfremden Verweise auf prozessbezogene Kompetenzen.

## [0.5.5] – 2026-08-25

Fehlerbehebung: Kompetenzverweise mit Klammer in der Nummer gingen beim Re-Import verloren.

### Behoben

- **Cross-Fach-Verweise auf Nummern wie `3.4.3(2)` wurden nicht aufgelöst.** Die
  Token-Erkennung im Feld „Hinweise" endete an der **inneren** Klammer: Gesucht wurde
  `3.4.3(2`, gefunden nichts — und im Text blieb eine verwaiste `)` stehen. Betroffen war
  jeder Verweis auf Mathematik und Physik, wo diese Schreibweise der Normalfall ist; ein
  Curriculum der Klassenstufe 10 verlor so sieben von sieben Querverweisen. Fächer mit
  klammerfreien Nummern (Ethik, Geografie …) funktionierten unverändert und haben den
  Fehler damit verdeckt.
- Der Import meldete die Verweise zwar als „nicht gefunden", legte aber die Vermutung
  nahe, der Bildungsplan des Zielfachs fehle in der Instanz. Tatsächlich war er
  vorhanden — die Nummer kam nur unvollständig an.

> Betrifft ausschließlich den **Re-Import** exportierter Curricula. In der Oberfläche
> gesetzte Verweise arbeiten mit Knoten-IDs statt Nummern und waren nie betroffen.
> Bereits importierte Curricula holen die Verweise beim nächsten Import nach.

### Dokumentation

- [Updates & Wartung](docs/admin/updates-und-wartung.md): neuer Abschnitt **Speicherplatz
  freigeben**. Jedes `--no-cache`-Update lässt das vorherige Image als `<none>` zurück und
  füllt den Build-Zwischenspeicher; nach einigen Updates sind das mehrere Gigabyte. Mit
  Abgrenzung, was gefahrlos entfernt werden kann und welche Befehle das Volume
  `postgres_data` — die gesamte Datenbank — mitnehmen würden. Dazu ein Hinweis auf die
  unbegrenzt wachsenden Container-Logs.

## [0.5.4] – 2026-08-25

### Geändert

- **Curriculum-Editor: „Fertig" statt „Abbrechen", sobald gespeichert ist.** Die
  Schaltfläche führt immer zurück zur Leseansicht, bedeutet aber je nach Stand etwas
  anderes. Nach dem Speichern gibt es nichts zu verwerfen — „Abbrechen" las sich dort, als
  nähme man die eben gespeicherte Arbeit zurück, und es war nicht erkennbar, dass dies der
  Weg aus dem Bearbeitungsmodus ist. Bei ungespeicherten Änderungen bleibt es
  „Abbrechen"; der Tooltip benennt in dem Fall ausdrücklich, dass Änderungen verloren
  gehen. Gilt für die obere Leiste und den mitlaufenden Fußbereich.

## [0.5.3] – 2026-08-25

Fehlerbehebung: Kompetenz-Auswahl zeigte zwei Bildungsplan-Fassungen nebeneinander.

### Behoben

- **PK- und IK-Auswahl mischten zwei Editionen.** Gleiche Nummer, anderer Text, doppelt
  in der Liste — ohne Hinweis, welcher Eintrag zu welcher Fassung gehört. Ursache war ein
  Wettlauf: Steht die geltende Edition noch nicht fest, wurde zuerst **ungefiltert**
  geladen und gleich darauf gefiltert nachgeladen. Welche der beiden Antworten zuletzt
  eintraf, entschied über den Inhalt der Liste. Jetzt wird gewartet, bis die Edition
  feststeht; überholte Antworten werden verworfen.
- **Der Curriculum-Editor kennt jetzt die Edition seines Curriculums.** Er reichte
  `bp_version` nicht an die Auswahlfelder weiter, obwohl ein Curriculum seit 0.5.0 fest an
  seine Edition gebunden ist. Stattdessen wurde aus Fach und Klassenstufe neu abgeleitet,
  was die geltende Fassung *heute* wäre — beim Bearbeiten eines älteren Curriculums also
  womöglich eine andere als die, auf der es beruht. Der Umweg entfällt; die Edition steht
  ohne Rückfrage beim Server fest.
- Prozessbezogene Kompetenzen traf das besonders, weil sie **keine Klassenstufe** tragen:
  Anders als bei den inhaltsbezogenen konnte auch der Stufenfilter die Fassungen nicht
  auseinanderhalten.

> Mehrere gleichzeitig aktive Editionen sind kein Fehlzustand, sondern der Normalfall
> während eines Editionswechsels — der Fahrplan in `subjects.yaml` weist verschiedenen
> Klassenstufen verschiedene Fassungen zu. Die Auswahl muss damit umgehen können.

## [0.5.2] – 2026-08-25

Fehlerbehebung: Fachübergreifende Kompetenzverweise waren für ein knappes Drittel der
Fächer nicht eingebbar.

### Behoben

- **`#`-Autovervollständigung übersprang 8 von 27 Fächern.** Im Feld „Hinweise" des
  Curriculum-Editors erkannte die Eingabehilfe nur Fach-Kürzel aus zwei bis sechs
  Großbuchstaben. Damit ließ sich auf **Deutsch (D), Geschichte (G), Mathematik (M)**
  sowie **Englisch (E1), Französisch (F2), Latein (L2) und Spanisch (SPA3)** nicht
  verweisen — einbuchstabige Kürzel und solche mit Ziffer fielen durch das Muster. Es
  gab keine Fehlermeldung, das Auswahlfeld erschien schlicht nicht.
- Die Trigger-Erkennung liegt jetzt als reine Textfunktion in `frontend/src/lib/hinweise.js`
  und ist damit prüfbar; ein Test führt **jedes** vergebene Fach-Kürzel einzeln auf.
  Welche Kürzel es wirklich gibt, entscheidet weiterhin der Server.

> Bereits gespeicherte Hinweise sind nicht betroffen — die Einschränkung lag allein in
> der Eingabehilfe, nicht in Speicherung, Export oder Anzeige.

## [0.5.1] – 2026-08-25

Fehlerbehebung: Der Bildungsplan-Import brach im Produktivsystem ab.

### Behoben

- **Bildungsplan-Import im Container abgebrochen** (`ModuleNotFoundError: No module
  named 'app'`). Das Skript suchte das `app`-Paket nur unter `<Wurzel>/backend` — das
  Repo-Layout. Im Betrieb ist `scripts/` aber nach `/app/import-scripts` gemountet und
  das Paket liegt direkt unter `/app`; ein `backend/`-Verzeichnis gibt es dort nicht.
  Statt zu raten, wird jetzt geprüft, wo `app/context/editions.py` tatsächlich liegt.
  Nur der 0.5.0-Neuzugang „Archivierung nach Editions-Fahrplan" braucht das Paket,
  darum trat der Fehler vorher nicht auf.
- **Ein fehlendes `app`-Paket bricht den Import nicht mehr ab.** Die Archivierung
  überholter Editionen ist der letzte Schritt vor dem Commit — eine Ausnahme dort
  verwarf den vollständigen, bereits erledigten Import. Sie wird nun übersprungen und
  protokolliert; der Hinweis erscheint zusätzlich zu Beginn des Laufs, nicht erst am
  Ende. Überholte Knoten bleiben dann aktiv, was sich jederzeit nachholen lässt.

> **Datenlage:** Der Abbruch geschah vor `conn.commit()`; die Transaktion wurde beim
> Schließen der Verbindung verworfen. In der Datenbank ist nichts gelandet — der Import
> muss lediglich wiederholt werden.

## [0.5.0] – 2026-08-25

Schwerpunkt: **Curricula werden übertragbar.** Ein Schulcurriculum lässt sich exportieren
und in einer anderen Instanz einspielen — für promptLab und Entwicklungsumgebungen bisher
die größte Hürde, weil man dort realistische Curricula von Hand nachbauen musste.

Auf dem Weg dorthin kamen mehrere Fehler zutage, die sich gegenseitig verdeckt hatten. Zwei
davon betrafen **Bestandsdaten**: Englisch und Französisch waren im Wissensgraph
vollständig stillgelegt, und Kompetenzverweise wurden in Export wie Import an einem Feld
gesucht, das reale Daten nie tragen.

Dazu mehrere Nacharbeiten am Bildungsplan-Import — und ein Befund aus dem V3-Test: Die
dritte Bildungsplan-Fassung liegt unter einer **neuen Seitengeneration**, die der Scraper
nicht lesen kann. Sie bekommt ein eigenes Release; hier ist vorbereitet, was dafür
ohnehin richtig sein muss.

### Neu

**Curricula übertragen**
- **Wiederimport exportierter Curricula** (`scripts/import_curriculum.py`) — ein
  Admin-Vorgang auf der Kommandozeile, mit `--dry-run` zum Vorabprüfen und einem Bericht
  über alles, was sich in der Zielinstanz nicht auflösen ließ.
- Runbook [Curricula übertragen](docs/runbooks/curriculum-transfer.md): Export durch die
  Lehrkraft, Voraussetzungen, Import, Deutung der Warnungen, Grenzen.
- `--bp-version` überschreibt die Bildungsplan-Edition aus der Datei — für den Fall, dass
  Quell- und Zielinstanz verschiedene Editionen aktiv haben.

**Curriculum-Editor**
- **Titel und Jahrgangsband sind änderbar.** Bisher bedeutete ein Vertipper: neu anlegen
  und die Inhalte übertragen. Das Jahrgangsband zieht dabei die strukturellen Felder und
  die Importschlüssel des ganzen Baums nach.
- Die **Bildungsplan-Edition** bleibt ausdrücklich unveränderlich — an ihr hängen alle
  Kompetenzverweise. Der geprüfte Weg ist „Bildungsplan aktualisieren".

**Dokumentation**
- [Schulcurriculum](docs/user/curriculum.md) — die erste Anleitung für Lehrkräfte zu einem
  der zentralen Werkzeuge: Aufbau, Kompetenzen verknüpfen, Fassungswechsel, Export.

### Behoben

- **Die Editions-Archivierung hätte beim V3-Rollout die Vorgänger-Fassung gelöscht.** Sie
  folgte der Regel „ein Fach steht als Ganzes auf einer Edition" — die stammt aus der Zeit
  vor dem Editions-Fahrplan. Ab 2026/27 stehen die Klassen 5–7 auf der neuen Fassung, die
  Klassen 8–12 weiter auf der vorigen; die alte Regel hätte in Mathematik **778 Knoten
  archiviert**, die noch gebraucht werden. Besonders unauffällig wäre das gewesen, weil die
  Fachplan-Knoten aktiv geblieben wären: Die Anzeige hätte für Klasse 8 korrekt die
  Vorgänger-Fassung gewählt und einen **leeren** Bildungsplan geladen — ohne Fehlermeldung.
  Archiviert wird jetzt nur, was **keine Klassenstufe mehr braucht**.
- **Englisch und Französisch waren vollständig stillgelegt** (959 Knoten, kein einziger
  aktiv). Beide werden aus PDFs importiert und lagen in einem anderen Ausgabeverzeichnis;
  ein Voll-Import über das Scraper-Verzeichnis behandelte sie deshalb wie entfernte
  Knoten. Die Archivierung greift jetzt nur noch innerhalb der Fächer, die der Import
  tatsächlich gesehen hat; die JSONL beider Pipelines landen in derselben Ablage. Nach
  einem erneuten Import sind beide Fächer wieder vollständig da.
- **Kompetenzverweise wurden am falschen Feld gesucht.** Import und Export lasen `nr`
  bzw. `pk_id`, reale Knoten führen die Nummer aber als `kompetenz_nr` (5141 gegen 0).
  Ein Curriculum verlor dadurch beim Wiedereinspielen **in dieselbe Instanz** 69 Verweise.
- **Leitperspektiven-Verweise waren nicht übertragbar.** Beide Seiten hingen an einem
  `code`-Feld, das kein einziger der 55 Knoten trägt. Das Kürzel wird jetzt aus der
  vorhandenen `bp_id` abgeleitet — das wirkt sofort auf Bestandsdaten, ohne erneutes
  Scrapen. Schreibweisen wie „(L) BO" werden dabei vereinheitlicht.
- **Aus dem YAML gelöschte Kapitel überlebten jeden Wiederimport.** Sie werden jetzt
  abgeräumt — begrenzt auf das betroffene Curriculum und auf Knoten, die der Import selbst
  angelegt hat. Im Editor erstellte Kapitel bleiben unberührt.
- **Ein einzelner nicht übersetzbarer Verweis brach den gesamten Import ab.** Solche
  Verweise werden übersprungen und gemeldet, statt das ganze Curriculum unimportierbar zu
  machen.
- Fehlt der passende Bildungsplan, nennt die Meldung jetzt, **welche Edition tatsächlich
  aktiv ist** — statt pauschal zu fragen, ob der Plan importiert sei.

### Geändert

- **Material-Verknüpfung eingegrenzt.** Die `@`-Suche im Curriculum-Editor und im
  Stundenentwurf bot bisher *alle* Knotentypen an. Auswählbar sind jetzt Dokumente,
  Artefakte und fachliche Konzepte — ohne Planungsobjekte und ohne personenbezogene Texte.
  Bildungsplan-Kompetenzen, Methoden, Sozialformen und Operatoren haben eigene
  Auswahlfelder. Die Liste wird aus `config/taxonomy.yaml` abgeleitet, ein neuer Typ ist
  also automatisch dabei.
- **Ein Fach stilllegen ist jetzt eine benannte Aktion.** Fehlt es in `subjects.yaml`,
  meldet der Import das; archiviert wird nur mit `--prune-subjects`. Vorher war es eine
  Nebenwirkung („Datei weglassen") — genau die hatte Englisch und Französisch getroffen.
- **Der Scraper legt vollständige Schnappschüsse ab.** Bisher schrieb er nur die
  *geänderten* Knoten in eine datierte Datei — erst alle Dateien zusammen ergaben den Plan
  (Physik lag vierfach im Verzeichnis, die jüngste mit zwei Knoten). Jetzt: **eine Datei je
  Fach und Edition** mit allem darin; datierte Vorgänger räumt der Scraper selbst weg.
  Damit entfällt die Regel, vor einem Re-Scrape erst alle alten Dateien zu löschen.
- **Warnungs-Log an der Projektwurzel verankert** (`--log-dir` überschreibt). Vorher war der
  Pfad arbeitsverzeichnis-relativ, sodass Testläufe und echte Importe in gleichnamige
  Dateien an verschiedenen Orten schrieben — beim Auswerten eine sichere Quelle für
  Missverständnisse.
- `POST /context/curricula` **entfernt**: Der Endpunkt schrieb nichts (kein Commit), wurde
  von keiner Seite aufgerufen und doppelte den Admin-Weg über das CLI.

### Migration

- Keine Datenbank-Migration nötig.
- **Empfohlen:** Bildungsplan-Import einmal laufen lassen (`python
  scripts/import_bildungsplan.py`) — er reaktiviert Fächer, die von der fehlerhaften
  Archivierung betroffen waren. Vorher mit `--dry-run` prüfen.
- Wer den PDF-Import nutzt: Die JSONL landen jetzt in `scripts/scraper/output/`. Alte
  Kopien in `scripts/pdf_import/output/` können entfernt werden.
- Die Scraper-Ablage darf gemischt sein (datierte Altbestände neben neuen Schnappschüssen);
  ein vollständiger Scrape bereinigt sie. Bis dahin arbeitet der Import korrekt weiter.

## [0.4.0] – 2026-08-08

Zwei Schwerpunkte: die Plattform wird **anbieterunabhängig** — kein Modellname steht mehr
im Code, ein Wechsel ist Konfigurationsarbeit — und sie liest erstmals den **Stundenplan**,
sodass Wochenmuster, Ferien und Vertretungsplan nicht länger von Hand in die
Unterrichtsplanung übertragen werden müssen.

Dazu kommen die zuvor auf einem eigenen Zweig entwickelten Modalitäten: **Bildgenerierung**,
**Server-Rendering** (Schaltpläne, Funktionsgraphen, Mathematik in PDFs), die
**Artefaktbibliothek** und die **Material-Werkstatt** mit Export nach PDF, Word und ODT.

### Neu

**Stundenplan-Integration (WebUntis)**
- **Wochenmuster aus dem Stundenplan übernehmen** statt eintippen — inklusive Doppelstunden
  (erkannt am lückenlosen Zeitraster, nicht geraten) und 14-tägigem Rhythmus. Der Vorschlag
  füllt den vorhandenen Editor; gespeichert wird erst nach Prüfung durch die Lehrkraft.
- **Ferien, Feiertage und bewegliche Ferientage** einmal je Schuljahr übernehmen
  (`/settings/holidays`). Der Vorschlag **ergänzt** die vorhandene Konfiguration, statt sie
  zu ersetzen — beide Seiten kennen Tage, die die andere nicht hat.
- **Entfall, Vertretung und Verlegung** fließen in die Jahresplanung: als Cron werktags um
  5:30 Uhr und als Handabgleich im Jahresplan und im Profil. Der Handabgleich ist der
  Hauptweg — Vertretungspläne werden vielerorts erst Minuten vor Unterrichtsbeginn gepflegt.
- **Vertretung gilt nicht als gehaltene Stunde.** Die vertretende Lehrkraft beaufsichtigt;
  das geplante Stundenziel bleibt offen, der Slot wird zum Anpassen vorgemerkt.
- **Verlegungen erscheinen als Vorschlag**, nicht als Änderung, und öffnen den vorhandenen
  Verschiebe-Assistenten. Ein Paar (Ursprung + Ziel) ergibt eine Meldung, eine verlegte
  Doppelstunde ebenfalls.
- Adapter-Schnittstelle wie beim Auth-Adapter: WebUntis ist die erste Quelle, nicht die
  einzig mögliche. **Ohne `WEBUNTIS_SERVER` bleibt die Integration unsichtbar** — die
  Unterrichtsplanung funktioniert unverändert mit Handpflege.
- Dokumentation: [Stundenplan-Integration](docs/admin/stundenplan-integration.md) (Admin),
  [Stundenplan übernehmen](docs/user/stundenplan.md) (Lehrkräfte), Eintrag fürs
  Verarbeitungsverzeichnis in [Datenschutz & Betrieb](docs/admin/datenschutz-betrieb.md).

**Bildgenerierung**
- Bild-Werkzeug im Chat mit eigener Modell-Freischaltungsmatrix, Kostenerfassung und
  Anzeige im Verlauf.
- **Jugendschutz-Prüfpunkt:** Ein schulweiter, schülersichtbarer Bild-Assistent geht nicht
  ohne ausdrückliche Freigabe live. Mehrschichtige Moderation mit fail-closed Blockliste.
- Werkzeugübersicht unter `/tools`; Aufräum-Cron für erzeugte Bilder.

**Server-Rendering**
- **Schaltpläne (CircuiTikZ)** und **Funktionsgraphen** werden serverseitig als SVG
  gerendert und im Chat sowie im Wissensgraph angezeigt. Plot-Ausdrücke werden über eine
  Whitelist geparst und ohne `eval` ausgewertet.
- **Mathematik in PDF-Exporten** (MathJax-SVG) — im Browser rendert KaTeX, das aber kein
  SVG erzeugt und daher für Exporte nicht taugt.
- Eigener Sidecar-Dienst (`render-sidecar/`), Ergebnis-Cache, Aufräum-Cron.

**Artefaktbibliothek**
- Bilder, Diagramme, Schaltpläne und Graphen aus dem Chat dauerhaft speichern
  (`/library`), herunterladen, als PNG oder Quelltext exportieren.
- **GeoGebra-Export** für Funktionsgraphen (`.ggb`).
- Aufbewahrungsfrist je Artefakt, Aufräum-Cron, gemeinsames Ablage-Volume.

**Material-Werkstatt**
- Markdown-Dokumente aus dem Chat in einen Editor übernehmen („In Werkstatt öffnen"),
  bearbeiten und mit Live-Vorschau prüfen.
- **Export nach PDF, Word (DOCX) und ODT** — Mathematik wird zu OMML, Diagramme werden
  vorgerendert eingebettet.
- **Schulweite Vorlagen** für Layout und Schrift (`/settings/export`).

**Anbieterwechsel vorbereitet**
- **Kein Modellname mehr im Code.** Chat-, Titel-, Embedding- und Bildmodell kommen
  vollständig aus der `.env`; die Werte sind die Namen aus der LiteLLM-Config, nicht die
  Produkt-IDs der Anbieter. Ein Anbieterwechsel bleibt damit auf die Proxy-Config beschränkt.
- **Assistenten müssen kein Modell mehr festlegen.** Ohne Angabe gilt das Standardmodell —
  vorher machte ein fest eingetragenes Modell einen Assistenten bei jedem Setup-Wechsel
  unbrauchbar.
- **Warnung bei verschwundenen Modellen:** Verweist ein Assistent auf ein Modell, das der
  Proxy nicht mehr führt, meldet das die Assistenten-Verwaltung, statt es beim ersten
  Chat scheitern zu lassen.
- **Modellwähler-Filter** (`MODEL_PICKER_HIDDEN_PREFIXES`): interne Modelle (Titel,
  Moderation) und andere Modalitäten verschwinden aus dem Dropdown. Rein kosmetisch,
  Freigaben bleiben unberührt.
- **Bildgenerierung modellunabhängig:** Formate über `IMAGE_SIZES` konfigurierbar,
  `IMAGE_RESPONSE_FORMAT` für Modelle, die Base64 statt URLs liefern.
- **Moderation ohne OpenAI-Zugang:** LLM-gestützter Guardrail als Ersatz für die
  OpenAI-Moderation-API, die nicht jeder Anbieter hat.
- `backend/scripts/check_litellm_config.py` prüft die Proxy-Konfiguration vor der
  Inbetriebnahme; Vorlage `infra/litellm_config.ionos.example.yaml` für einen EU-Anbieter.

**Werkzeuge und Dokumentation**
- [Runbook: Embedding-Modell wechseln](docs/runbooks/modellwechsel.md) — Schema angleichen,
  Re-Embedding, Verifikation, Rollback.
- `backend/scripts/resize_embedding_column.py` für den Wechsel der Vektorbreite im
  laufenden Betrieb.
- ESLint im Frontend erstmals einsatzfähig — `npm run lint` lief vorher ins Leere.

### Geändert
- **Embedding-Modell ist konfigurierbar.** Modellname, Vektorbreite, Input-Cap und der
  optionale `dimensions`-Parameter kommen aus der `.env` (`EMBEDDING_MODEL`,
  `EMBEDDING_DIMENSIONS`, `EMBEDDING_MAX_CHARS`, `EMBEDDING_SEND_DIMENSIONS`) statt aus
  Literalen im Code. Die Defaults entsprechen dem bisherigen Stand
  (`text-embedding-3-small`, 1536) — **bestehende Installationen brauchen keine Änderung.**
- Passt die Vektorbreite des Modells nicht zur Konfiguration, bricht die Embedding-Generierung
  mit einer `EmbeddingDimensionError` ab, die beide Breiten und den Modellnamen nennt (vorher:
  unverständlicher pgvector-Fehler beim Schreiben). Ein Startup-Check meldet die Abweichung
  schon beim Hochfahren.
- Die **Kontolöschung nach 90 Tagen** räumt zusätzlich den Stundenplan-Abrufstatus ab. Ein
  Strukturtest verlangt für jede neue Tabelle mit Pseudonym-Spalte eine ausdrückliche
  Entscheidung — die Lücke war zuvor nur zufällig aufgefallen.
- `alembic revision --autogenerate` erzeugt wieder brauchbare Migrationen: 21 Altlasten
  zwischen Modellen und Schema beseitigt (fehlende `Text`-Typen und Indizes in
  `app/db/models.py`, Migration `0042` für zwei DB-seitige Abweichungen). Vorher hätte
  `--autogenerate` eine Migration erzeugt, die sechs Indizes löscht.
- `pytest tests/` läuft wieder vollständig durch: `alembic/env.py` deaktivierte über
  `fileConfig` sämtliche `app.*`-Logger, wodurch ein Test im kombinierten Lauf fehlschlug.

### Behoben
- **Wochenmuster: einmalige Klassenarbeiten verfälschten das Muster.** Reichte eine Klausur
  in die Folgestunde, verschmolz die davorliegende **wöchentliche** Stunde mit ihr zu einer
  „Doppelstunde, 1× gesehen" — falsche Länge und verlorene Sicherheit. Verschmolzen wird
  jetzt nur noch, wenn die Stunden auch tatsächlich gemeinsam auftraten. Gefunden bei der
  Abnahme gegen die Pläne aller 90 Lehrkräfte.
- Bildungsplan-Import: fehlende Abhängigkeit `bs4` im Container, LFDB-Import im Runbook.

### Migration
- `alembic upgrade head` einspielen (`0038`–`0046`).
- `0043` ist **idempotent**: Bei unverändertem `EMBEDDING_DIMENSIONS` passiert nichts und
  vorhandene Embeddings bleiben erhalten. Nur wer die Breite ändert, braucht anschließend ein
  vollständiges Re-Embedding (`scripts/embedding_backfill.py`) — bis dahin liefert die
  semantische Suche keine Treffer. Ablauf im Runbook oben.
- `python scripts/seed_subjects.py` ausführen — die Fächer tragen jetzt die Fachkürzel des
  Stundenplans (`untis_codes`).
- **Optional:** Wer den Stundenplan anbinden möchte, ergänzt die `WEBUNTIS_*`-Zeilen in der
  `.env`. Ohne sie ändert sich für Nutzer:innen nichts.
- Neue Dienste in `docker-compose.yml`: Render-Sidecar sowie Cron-Einträge für
  Stundenplan-Abgleich und das Aufräumen von Bildern, Artefakten und Render-Cache.

## [0.3.0] – 2026-07-16

Schwerpunkte: Unterrichtsplanung, pädagogische und rechtliche Leitplanken
(Krisenerkennung, PII-Warnung, Jugendschutz), Bildungsplan-Editionen samt
PDF-Import (Fremdsprachen und Leitfaden Demokratiebildung) sowie ein
Sicherheits-Audit.

### Neu
- **Unterrichtsplanung:** Jahresplanung mit Planungs-Assistent, Stundenentwurf und
  Nachbereitung/Engagement; Methoden und Sozialformen als eigene Wissens-Knotentypen;
  Export (Markdown/PDF/DOCX).
- **Bildungsplan-Editionen:** editionsbewusste Versionierung (`bp_version`, `.V2`/`.V3`)
  mit jahrgangsweiser Frontier und Curriculum-Migration auf neue Editionen.
- **Operatoren:** handlungsleitende Verben (AFB I–III) als content_type `operator` –
  Scraper/Import, Darstellung im Bildungsplan, Chat-Werkzeug, Embeddings.
- **PDF-Bildungsplan-Import:** neue Pipeline `scripts/pdf_import/` für nur als PDF
  veröffentlichte Pläne – **Leitfaden Demokratiebildung (LFDB)** sowie die
  **Fremdsprachen (Englisch, Französisch)** inklusive Operatoren. LLM-gestützte
  Extraktion mit menschlicher Review, deterministische Assemblierung, dieselben
  Knotentypen wie der HTML-Scraper (keine UI-Sonderwege).
- **Krisenerkennung (ADR-008):** lokale Trigger-Erkennung parallel zum Chat,
  nicht-alarmierende Hilfe-Banner, pseudonyme Flags, Soft-Delete geflaggter Konversationen.
- **Krisen-Einsicht (4-Augen-Prinzip):** Rolle `review`, Flag-Dashboard,
  Step-up-Authentifizierung, Zweitfreigabe und protokollierte Reader-Ansicht.
- **Pädagogische Leitplanken:** zielgruppengerechte Präambeln, Lernverhalten-Augmentierungen
  und Jugendschutz-Prüfpunkte für Assistenten.
- **PII-Eingabewarnung:** Datensparsamkeit-Gate vor dem Senden (Server-NER + Client-Regex),
  fail-open, pro Konversation unterdrückbar.
- **Rich-Rendering:** KaTeX + mhchem (Mathematik/Chemie) und Mermaid-Diagramme in Chat,
  Wissensgraph, Curriculum und Hilfe.
- **Wissensgraph:** getrennte Lese- und Bearbeitungsansicht, Knoten-Aliase, paginierte Listen.

### Sicherheit
- **Sicherheits-Audit (18 Funde behoben):** PKCE und Browser-Bindung im OAuth-Login,
  ID-Token-Verifikation gegen JWKS, Rate-Limiting, Härtung der Step-up-Authentifizierung,
  4-Augen-Prinzip gegen Doppelrollen-Nutzer, Magic-Byte-Prüfung bei Uploads, explizite
  URL-Allowlist in DOMPurify, Erzwingen von Mindest-Secret-Längen, Upload-Limits,
  korrekte Kostenabrechnung der Titelgenerierung, Leserechte-Prüfung im Wissensgraph.

### Behoben
- Bildungsplan: fachweiser Fehlerabfang im Scraper, NWT-BF-Kursstufe, Reaktivierung
  zuvor archivierter Knoten, editierbare Knotentitel (Admin), Performance der
  Wissensgraph-Liste (Paginierung), Rollenwechsel ohne Neu-Login, u. a.

Ältere Versionen: siehe Git-Tags (`0.2.0`, `0.1.3`, `v0.1.2`, …).
