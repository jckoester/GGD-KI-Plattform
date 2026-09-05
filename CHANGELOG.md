# Changelog

Alle nennenswerten Änderungen an der GGD-KI-Plattform. Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (0.x = vor dem ersten Stable-Release).

## [Unreleased]

## [0.8.0] – 2026-09-05

Schwerpunkt: **der Wissensgraph**. Die Suche trennt Namenstreffer von thematischen
Treffern und erschließt erstmals eigenes Material. Fünf Bausteinarten bekommen eine
gepflegte Sammlung mit Editor und Verknüpfen-Dialog. Ablaufdatum, Archivieren und Löschen
wirken jetzt tatsächlich. Dazu eine aufgeräumte Taxonomie: 41 statt 47 Bausteinarten.

### Neu

- **Suchseite für den Kontextspeicher** unter *Wissensgraph → Suche*, für alle Rollen.
  Sie trennt Namensträger, ähnlich benannte und thematische Treffer und zählt bei
  gesetzten Filtern („24 insgesamt", nach Fach aufgeschlüsselt). Gibt es keinen Baustein
  dieses Namens, sagt die Seite das ausdrücklich. Treffer lassen sich an den offenen Chat
  anheften oder als Grundlage eines neuen mitnehmen.

### Geändert

- **Sucht ein Assistent im Kontextspeicher, öffnet sich kein Vorschlagsfenster mehr.**
  Die Liste zum Anheften erscheint nur noch bei eigener Suche.

- **Die Suche trennt Namenstreffer von thematischen Treffern.** Beide Gruppen haben
  eigene Plätze; ist die Liste der Namensträger gekürzt, steht die Gesamtzahl dabei.

- **Eigenes Material ist thematisch auffindbar.** 15 weitere Bausteinarten sind für die
  Suche erschlossen, dazu die neue Art **Fachbegriff**. Bei Stundenentwürfen zählt das
  Thema, nicht der Verlaufsplan.

- **Die Suche ordnet Treffer nach Rolle.** Schüler:innen bekommen Lernmaterial etwas
  weiter oben, Lehrkräfte Klausuren und Stundenentwürfe — ein Vorzug, kein Filter.

- **„Was haben wir letzte Woche gemacht?"** beantwortet der Assistent aus dem
  Stundenplan: Zeitraum und Unterrichtsgruppe sind Filter der Aufzählung.

- **Bausteine ohne Embedding sind über ihren Namen auffindbar** — Fachpläne, Curricula,
  Methoden, Leitperspektiven.

- **Bausteine sind über einen Teil ihres Namens auffindbar.** „Anleitung Operator nennen"
  findet „Anleitung zur Verwendung des Operators ‚nennen'". Exakte Namensträger stehen
  vorn, ähnlich benannte in einem eigenen Abschnitt dahinter, eigene vor fremden.

- **Assistenten mit festem Wissensbereich suchen wie alle anderen** und erben damit
  Namens-Nachschlagen und Fachvorzug. Die Bereinigung der Bildungsplan-Fassungen gilt
  jetzt überall: Eine Kompetenz erscheint einmal, bei bekanntem Jahrgang in der für ihn
  geltenden Fassung.

- **Assistenten können den Kontextspeicher auszählen.** „In welchen Fächern gibt es den
  Operator *nennen*?" beantwortet die Plattform mit einer vollständigen, gezählten Liste,
  wahlweise nach Fach oder Bausteinart aufgeschlüsselt. Die Fähigkeit „Kontextsuche"
  bringt das Werkzeug mit; `get_operatoren` bleibt nutzbar.

- **Das Vorschlagsfenster im Chat zeigt die Abschnitte getrennt** und passt auf kleine
  Bildschirme. Vorausgewählt sind höchstens fünf Treffer je Abschnitt; „Alle" wählt die
  ganze Liste. Angeheftete Bausteine klappen ab sechs Stück ein.

- **Der `@`-Shortcode findet mehrwortige Titel.** Anfang oder ein Wort aus der Mitte
  genügen; die Liste bevorzugt das Fach des Chats und schließt mit `esc`.

- **Die Suche ist nicht mehr als experimentell gekennzeichnet.**

- **Die Liste der Bausteinarten ist keine Betreiber-Konfiguration mehr.** Sie gehört zum
  Anwendungsabbild; das Backend prüft sie beim Start gegen den Datenbestand und startet
  bei einer Abweichung nicht.

  ⚠️ **Für Bestandsinstallationen:** Die alte `config/taxonomy.yaml` auf dem Host ist
  wirkungslos und kann gelöscht werden.

- **Bausteinarten ohne Anlege-Weg erscheinen in keiner Auswahl mehr** — Lernplan,
  Schülertext, Feedback-Text, Prüfungsanforderung. Vorhandene bleiben sicht- und
  durchsuchbar, und wer einen bearbeitet, behält seine Art.

- **Zuständigkeiten für neue Bausteine korrigiert.** Prüfungsanforderung, Konvention,
  Themengebiet, Funktion und Bauteil legt die Fachschaft an, Sozialformen die Schule;
  eine Präsentation gehört zur Lerngruppe. Betrifft nur die Vorauswahl beim Anlegen.

- **Schülerartefakte laufen zum Schuljahresende ab statt nach sechs Wochen.**

- **Zwei neue Bausteinarten vorbereitet:** Schülerpräsentation und Gliederung/Mindmap.
  Beide ruhen bis 0.9.

- **Sechs Bausteinarten sind in vier anderen aufgegangen** (41 statt 47):
  *Aufgabenblatt* → **Arbeitsblatt**, *Gliederung* und *Mindmap* →
  **Gliederung/Mindmap**, *Mathematischer Operator* und *Abstraktes Konzept* →
  **Fachbegriff**, *Reflexion* entfällt. Die Migration stellt bestehende Bausteine um;
  Inhalt, Verknüpfungen und Verlaufsdaten bleiben.

- **Die Nachbereitung einer Stunde ist thematisch auffindbar.** „Was habe ich mir zu
  Bindungsenergie notiert?" findet die Stunde über ihre Reflexion.

- **Bausteine, auf die andere aufbauen, lassen sich nicht mehr löschen.** Die Plattform
  zeigt, wer darauf verweist, und bietet Archivieren an. Eigene Verweise halten nicht
  auf; Admins können sich darüber hinwegsetzen.

- **Der Wissensgraph bietet Archivieren und Löschen nur noch dort an, wo es erlaubt ist.**

- **Stundenentwürfe, Unterrichtseinheiten und Schülermaterial bekommen beim Anlegen ein
  Ablaufdatum** — das Ende des laufenden Schuljahres. Ein anderes oder gar keins trägt
  man beim Anlegen ein oder entfernt es später.

- **Das Ablaufdatum wirkt jetzt.** Ein nächtlicher Lauf archiviert abgelaufene Bausteine
  und löscht nach drei Schuljahren im Archiv endgültig — Bildungsplan und importierte
  Inhalte ausgenommen.

- **„Reaktivieren" im Archiv** holt einen abgelaufenen Baustein zurück und setzt ein
  neues Ablaufdatum.

- **Gepflegte Sammlungen für fünf Bausteinarten** — Methodenblatt, Operatorenblatt,
  Methode, Sozialform und Fachbegriff. Jede mit eigenen Spalten und Filtern, einem
  Formular statt eines JSON-Feldes und einem Satz darüber, was hineingehört. In der
  Sidebar unter *Wissensgraph → Sammlungen* stehen Methode, Sozialform und Fachbegriff;
  Methodenblatt und Operatorenblatt im Fachschafts-Abschnitt der Fachseite, aufs Fach
  vorgefiltert.

- **Bausteine lassen sich von Hand verknüpfen.** Die Detailansicht gruppiert die
  Vernetzung nach Beziehungsart und bietet einen **Verknüpfen**-Dialog; die Richtung
  steht als Satz da („‚Oxidation‘ steht in Beziehung zu …"). Entfernen betrifft nur die
  Verknüpfung, nie den Baustein.

- **Fehlende Bausteine entstehen aus dem Dialog heraus.** Findet die Suche nichts
  Passendes, legt der Dialog den Baustein an und verknüpft ihn sofort. Er trägt dann das
  Kennzeichen **„unvollständig"**; die Sammlung zählt und filtert danach.

- **Methode und Fachbegriff verlangen eine Beschreibung.**

- **Die mitgelieferten Methoden und Sozialformen haben eine Kurzbeschreibung.** Wer den
  Ablauf beschreibt („erst allein nachdenken, dann zu zweit austauschen"), findet die
  Methode, ohne ihren Namen zu kennen.

- **Methoden haben ein eigenes Feld „Ablauf in einem Satz".** Es allein entscheidet über
  die thematische Auffindbarkeit; ohne Eintrag zählt die Kurzbeschreibung.

### Migration

`alembic upgrade head` wie gewohnt — die drei Migrationen laufen in einem Zug.

- **`0056`** — Verknüpfungsart „reflektiert" entfernt. Der Lauf bricht ab, falls noch
  solche Verknüpfungen im Bestand liegen.

- **`0055`** — Zusammenlegung der Bausteinarten. Muss **zusammen mit** diesem Release
  eingespielt werden: Das Backend startet nicht, solange Bausteine eine abgeschaffte Art
  tragen. Stunden mit Nachbereitung werden zum Neu-Einbetten vorgemerkt.

- **`0054`** — Trigramm-Index für die Namens-Teilsuche. Legt die PostgreSQL-Erweiterung
  `pg_trgm` an; ohne Superuser-Rechte muss der Betreiber sie vorab freischalten.

### Behoben

- **Der Knopf „Schuljahresende" setzte immer den 31.07.** Das Datum kommt jetzt aus der
  Schuljahres-Einstellung; trägt der Baustein ein anderes Schuljahr als das laufende,
  erscheint der Knopf nicht.

- **Auswahlfelder für Bausteinarten zeigten den technischen Schlüssel**
  (`schuelerpraesentation` statt „Schülerpräsentation") — im Filter des Wissensgraphen,
  im Anlege-Formular und im Editor. Jetzt deutsche Bezeichnungen, alphabetisch sortiert.

- **Assistenten mit Wissensbereich sahen keine fach- oder gruppenweit freigegebenen
  Bausteine.** Gruppenfreigaben gelten weiterhin nur für Mitglieder der Gruppe.

- **Gruppenfreigaben wurden bei der Suche nicht geprüft.** Ein für eine Lerngruppe
  freigegebener Baustein konnte außerhalb erscheinen und ging mitsamt Inhalt ins Modell.

- **Die Fachzuordnung eines neuen Chats wirkte sich erst nach der ersten Nachricht auf
  die Suche aus.**

- **Curriculum-Kapitel lassen sich als Wissensbereich eines Assistenten wählen.** Sie
  fehlten im Assistenten-Editor, während die Knotenliste sie als Einstiegspunkt auswies;
  bei Unterrichtseinheiten war es umgekehrt.

- **Archivieren tat bei fremden Bausteinen nichts, ohne Meldung.** Fehler werden jetzt
  angezeigt, und die Aktion erscheint nur, wo sie erlaubt ist.

- **Archivierte Bausteine trugen kein Archivierungsdatum.**

- **Ein überarbeiteter Baustein blieb thematisch unter seiner alten Fassung auffindbar.**
  Die Suchaufbereitung wird jetzt auch beim Ändern erneuert.

- **Ein Baustein ohne zuständige Gruppe verursachte einen Serverfehler** statt einer
  Meldung, was fehlt.

- **Bausteine mit eigenem Editor führten trotzdem in den allgemeinen.** „Bearbeiten"
  führt bei Stundenentwurf, Unterrichtseinheit und Jahresplan jetzt in den Planer; die
  alte Adresse leitet dorthin weiter. Fehlt die Unterrichtsgruppe, erscheint statt des
  Knopfes ein Hinweis, wo der Baustein gepflegt wird.

- **Über den allgemeinen Editor ließ sich ein kaputter Verlaufsplan speichern.** Das
  Phasen-Schema gilt jetzt auf jedem Schreibweg.

- **Verknüpfungen ließen sich als Administrator nicht anlegen.**

- **Aus einer Sammlung geöffnet, führte „Zurück" in die allgemeine Bausteinliste** und
  verlor die gesetzten Filter. Der Filterzustand steht jetzt in der Adresszeile; eine
  Sammlungsansicht lässt sich verschicken und neu laden.

## [0.7.0] – 2026-08-31

Schwerpunkt: **Anbieterunabhängigkeit**. Modelle heißen nach ihrer Aufgabe statt nach
Produkt, Preise dürfen in Euro geführt werden, der LiteLLM-Proxy gehört zum Stack. Dazu
das Budget-Wochenmodell und ein verbesserter Kontextspeicher.

### Neu

- **Nachvollziehbar, womit eine Antwort erzeugt wurde.** Neben dem schulinternen Alias
  (`chat-standard`) steht jetzt das Anbietermodell (`gpt-oss-120b`), aufgelöst beim
  Schreiben — ein späteres Umhängen des Alias verfälscht alte Antworten nicht.
  Im Chat über den Knopf **„Herkunft"**, in der Bibliothek dauerhaft, für Bilder mit
  eigener Angabe. **„Angaben zum Zitieren kopieren"** legt Werkzeug, Modell, Datum und die
  eigene Eingabe als Textbaustein bereit; der Bild-Prompt ist als *vom Sprachmodell
  formuliert* gekennzeichnet. Optional eine Herkunftszeile in exportierten Dokumenten
  (*Einstellungen → Export-Vorlagen*, Vorgabe aus).
  Für Inhalte von vor diesem Update bleibt die Angabe leer — sie ist nicht rekonstruierbar.

- **Mehrere Bildmodelle gleichzeitig nutzbar.** Eine **Bildart**
  (`config/image_models.yaml`) bündelt Modell, Formate und einen verständlichen Namen;
  Assistenten lassen sich im Editor darauf festlegen. Ohne die Datei entsteht aus den
  bisherigen `IMAGE_*`-Variablen eine einzige Bildart, und nichts ändert sich.
  Bildarten, deren Modell für den Jahrgang nicht freigeschaltet ist, erscheinen gar nicht
  erst; unbekannte Formate werden auf das nächstliegende Seitenverhältnis abgebildet statt
  abgelehnt. Neu am Bild: **noch einmal versuchen** mit derselben Beschreibung.

- **Der Jugendschutz-Guardrail fällt nicht mehr blind offen aus.** Bei Störung des
  Klassifikators greift eine Staffel: Wiederholung, optionaler zweiter Klassifikator, und
  wenn beides nichts liefert, entscheidet das Team (`fail_open_teams`) — Lehrkräfte
  arbeiten weiter, Schüler:innen bekommen die Antwort zurückgehalten. Ein unbekanntes Team
  gilt als schutzbedürftig.
  Sein Betriebszustand steht unter *Einstellungen → Guardrail*; ein liegengebliebener
  Bericht gilt nach `GUARDRAIL_HEALTH_MAX_AGE_H` als veraltet und **nicht** als gesund.
  Benachrichtigungen verschickt die Plattform nicht — `/api/admin/guardrail/health` gehört
  in die Server-Überwachung.

- **`scripts/check_production.py`** prüft die Betriebswerte vor der Inbetriebnahme:
  Secrets, `ALLOWED_HOSTS`, `TRUSTED_PROXIES`, Auth-Adapter und `jwks_url`,
  `AUTH_DEBUG_USERINFO`, Proxy-Adresse, laufendes Schuljahr. Ohne Netz und Datenbank
  ausführbar; nennt am Ende, was es nicht prüfen kann.

- **Vorlage für den EU-Betrieb** (`infra/litellm_config.ionos.example.yaml`) mit fünf
  Chat-Stufen, Systemmodellen, Embedding und Bild — Modell-IDs, Fähigkeiten und Preise
  gegen den IONOS-Katalog gemessen. Dazu zwei Messwerkzeuge: **`scripts/ionos_probe.py`**
  (Katalog, Function-Calling, Vektorbreite, Bildformat) und **`scripts/bildpreis_probe.py`**
  (ob und wie ein Bildmodell abgerechnet wird, inklusive Prüfung der gelieferten Größe).

### Geändert

- **Der LiteLLM-Proxy läuft als Dienst derselben `docker-compose.yml`.** `docker compose
  up -d` startet ihn mit; Config, Guardrail-Module und das `./data`-Volume sind eingehängt,
  die Proxy-Oberfläche nur auf `127.0.0.1` (Port über `LITELLM_PORT`). Die zweite Datenbank
  legt `infra/db-init/` beim ersten Start an. Ein LiteLLM-Update ist jetzt Tag-Wechsel plus
  `docker compose up -d litellm`. Der getrennte Betrieb bleibt unterstützt.

- **Das Budget gilt je Unterrichtswoche und wird nicht mehr zurückgesetzt.** Die
  Obergrenze wächst jede Unterrichtswoche um den eingetragenen Betrag, der Verbrauch läuft
  das Schuljahr durch; Ungenutztes wandert mit, gedeckelt auf `vorsprung_wochen` (Vorgabe 3).
  Welche Wochen zählen, kommt aus `school_year.yaml` — Ferienwochen bekommen nichts.
  Neues Schema in `budget_tiers.yaml`: `wochenbudget_eur`. Neuer Cron
  `weekly_budget_accrual.py` (montags 05:00), `monthly_budget_reconcile.py` heißt jetzt
  `monthly_team_reconcile.py` und gleicht nur noch Teams ab.
  `/budget` zeigt Jahressumme und Hochrechnung; Profil und Seitenleiste nennen Betrag und
  Termin der nächsten Aufstockung. Zurückgesetzt wird allein zum Schuljahreswechsel.

- **Preise können in Euro geführt werden** (`LITELLM_PRICE_CURRENCY=EUR`) — dann rechnet
  die Plattform nicht um, und ein Kursrisiko entsteht nicht. Vorgabe bleibt `USD`.
  `check_litellm_config.py` meldet Modelle, deren Preise nicht zur eingestellten Währung
  passen können.

- **Embeddings entstehen im Stapel** (`EMBEDDING_BATCH_SIZE`, Vorgabe 64) statt einzeln:
  gemessen 0,8 → 33 Knoten/s. Die Drosselung ist konfigurierbar
  (`EMBEDDING_TOKENS_PER_SECOND`, Vorgabe 3000, `0` = aus) und taktet nach abgerechnetem
  Verbrauch. Der **Titel geht ins Embedding ein**, wo er eigene Information trägt — Knoten
  ohne Inhalt (im Bestand 125 Leitideen) waren für die Suche bisher unsichtbar. Ein
  fehlgeschlagener Stapel wird einzeln nachgefasst, statt die übrigen Texte mitzureißen.

### Behoben

- **Die semantische Suche übersah rund die Hälfte der besten Treffer.** Der Vektorindex
  lieferte nicht die ähnlichsten Knoten, sondern eine Auswahl daraus. Er ist entfernt
  (Migration 0052); die Suche durchläuft alle Vektoren. Das richtige Fach steht damit in
  11 von 15 Prüffällen oben statt in 8, der erwartete Knoten wird in 13 statt 6 Fällen
  gefunden. Neuer Prüfsatz: `config/search_eval.yaml` mit `scripts/search_eval.py`.

  - **Benannte Bausteine werden nachgeschlagen statt geschätzt** — wer einen Operator, eine
    Leitidee oder einen Fachbegriff sucht, bekommt ihn, unabhängig von der Frageform.
  - **Das Fach der Konversation zieht passende Treffer nach oben**, ohne fachfremde zu
    filtern.
  - **Assistenten lesen den Wissensgraphen, statt ihn nur aufzulisten:** Treffer tragen
    jetzt Inhalt und Fachnamen. `get_operatoren` nennt bei leerem Ergebnis den Grund,
    statt eine leere Liste zu liefern, die als „nichts vorhanden" gedeutet wurde.
  - **Such- und Anzeigetiefe sind getrennt:** Assistenten durchsuchen
    `ASSISTANT_CONTEXT_LIMIT` Knoten (Vorgabe 20), das Vorschlagsfenster zeigt weiterhin so
    viele, wie im Profil eingestellt sind.
  - Embedding-Modelle mit mehr als 2000 Dimensionen sind nutzbar (die Grenze kam vom
    Index); `--reindex` und alle Index-Rebuild-Schritte entfallen.
  - ⚠️ **Die Suche ist als experimentell gekennzeichnet.** Sie ist besser geworden, aber
    nicht verlässlich, und der Bestand besteht fast nur aus Bildungsplan-Daten
    ([Kontextspeicher](docs/user/kontext.md)).

- **Kosten wurden zu niedrig ausgewiesen.** Ein Chat-Zug besteht aus mehreren Anfragen — je
  Werkzeugrunde eine, dazu die Titelgenerierung. Abgerechnet wurde nur die letzte; bei
  mehreren Runden fehlte die Angabe ganz. Jetzt werden alle Anfragen zusammengezählt,
  **einschließlich der Titelgenerierung**. Nachgefragt wird gestaffelt (1, 2, 4, 8 s);
  `SPEND_LOG_DELAY` entfällt. Vollständigkeit steht im Log
  (`Kosten des Zuges: 4 von 4 Anfragen abgerechnet`).

- **Bildgenerierung lief am Budget vorbei.** LiteLLM löst Bildpreise ausschließlich über
  seine eingebaute Tabelle auf; selbst eingetragene Modelle wurden mit 0,00 abgerechnet.
  Der Callback `guardrails.bildpreise.registrierung` trägt die Preise aus `IMAGE_PRICES`
  beim Proxy-Start dort ein — danach stimmen Kostenheader, SpendLog, Budget und Statistik
  ohne Sonderweg.

- **Ein aufgebrauchtes Budget wurde nicht als solches gemeldet.** Geprüft wurde auf HTTP
  429, LiteLLM meldet je nach Fassung 400 oder 429. Beim echten Budgetende sah die
  Nutzerin den rohen Fehlerkörper, umgekehrt bekam jede Drosselung „Budget erschöpft" zu
  sehen. Erkannt wird es jetzt am Fehlertyp `budget_exceeded` — im Chat, bei der
  Bildgenerierung und beim Variieren.

- **Jugendschutz und Guardrail-Vorlagen:** Der `guardrails:`-Block stand unter
  `litellm_settings`, wo LiteLLM das alte Format erwartet — der Proxy startete damit nicht.
  Kategorien und Schwellen standen unter `guardrail_info.params` und wurden nie gelesen.
  Drogen-Anleitungen prüfte gar nichts, weil der zuständige Guardrail den Typ `regex`
  nutzte, den es seit LiteLLM 1.83.7 nicht mehr gibt; die Kategorie steckt jetzt im
  Klassifikator.

- **Konfigurationsdateien wurden im Container nicht gefunden** — Bild-Blockliste,
  Krisen-Trigger, Hilfe-Ressourcen, pädagogische Leitplanken, Bildarten und der
  Guardrail-Zustandsbericht. Neun Module berechneten ihre Wurzel selbst und landeten im
  Image bei `/` statt `/app`; die Dateien galten als nicht vorhanden, die Schutzfunktionen
  fielen **still** aus. Die Auflösung liegt jetzt zentral in `app/core/paths.py`.

- **Das Backend startete im Container nicht** (`NameError: name 'Any' is not defined`).
  Ein neuer Test prüft `app/`, `scripts/` und `infra/guardrails/` statisch auf undefinierte
  Namen — die Entwicklungsumgebung läuft auf Python 3.14 und wertet Annotationen erst bei
  Bedarf aus, das Container-Image auf 3.12 nicht.

- **Der Gesprächstitel war manchmal die Antwort statt der Titel.** Bei imperativen
  Eingaben befolgte das Titelmodell die Anweisung. Die Nutzernachricht wird jetzt als
  **Zitat** übergeben; über vier Anbieter nachgemessen.

- **Der YAML-Export eines Assistenten verlor seine Fähigkeiten** — weder `tool_groups` noch
  `image_kinds` wurden geschrieben; ein Re-Import kam ohne Unterrichtsplanung,
  Bildgenerierung und Bildart-Auswahl zurück. Zudem scheiterte der Re-Import an der
  Schema-Prüfung (`visibility` war dort nicht vorgesehen). Unbekannte Fähigkeiten und
  Bildarten werden beim Import übergangen und benannt.

- **Der wöchentliche Budgetlauf meldet einen Stichtag außerhalb des Schuljahres.** Bisher
  zählte er ihn wie Ferien — ohne Zuteilung, ohne Hinweis. Führt `school_year.yaml` das
  falsche Jahr, wird nie zugeteilt, und der Jahreswechsel-Reset löst nicht aus.
  `--neuaufbau` weist einen zweiten Lauf ab (`--trotzdem` erzwingt ihn): Er hätte den
  angesparten Vorsprung wieder weggenommen.

- Kleinere Korrekturen: Der Bildpreis-Abgleich nennt die Einheit aus
  `LITELLM_PRICE_CURRENCY` statt immer Dollar und weist auf einen möglichen Währungsmix
  hin · beim Variieren eines Bildes erschienen Fehlertexte, die an das Chat-Modell
  gerichtet waren · `/user/new` legt keinen zweiten, unverzeichneten Virtual Key mehr an ·
  eine gesetzte `embedding_error`-Marke blieb nach erfolgreicher Einbettung stehen · das
  Startskript des Proxys verlangte fest `OPENAI_API_KEY` · auf der Seite *Ferienkalender*
  war die Beschriftung der Knöpfe im Dunkelmodus unlesbar ·
  `infra/litellm_config.example.yaml` verwies auf die Datenbank der Anwendung, und die
  Modellnamen in `.env.example` passten nicht zur mitgelieferten Vorlage.

### Entfernt

- **Der lokale Ollama-Fallback — es gibt keinen Rückfall bei erschöpftem Budget.** Budget
  aufgebraucht heißt: keine Nutzung bis zum nächsten Zeitraum. Entfallen sind
  `ollama-fallback` aus den Vorlagen und `OLLAMA_BASE_URL`. **Bestehende Installationen
  müssen nichts tun**; die Preisprüfung nimmt lokale Modelle weiterhin aus, jetzt anhand
  des Anbieters statt des Modellnamens.

- **Die Redis-Vorlage für den Proxy** (`infra/litellm-redis.example.yml`) samt Doku. Die
  Plattform setzt keine `tpm`/`rpm`-Limits in LiteLLM, und der Verbrauch steht in dessen
  Datenbank — bei einem Proxy-Worker bringt ein gemeinsamer Zähler-Speicher nichts. Die
  Meldung „No Redis configured" ist der erwartete Zustand.

### Dokumentation

- Neue Kapitel: [Vor der Installation](docs/admin/vor-der-installation.md) (gemessene
  Preise, Fähigkeiten und Fallstricke aller vier Anbieter),
  [Modell-Szenarien](docs/admin/modell-szenarien.md) (vollständige Konfigurationen je
  Anbieter samt Abdeckungsmatrix) und [KI-Ergebnisse zitieren](docs/user/zitieren.md).
- Neue Runbooks: [Schuljahreswechsel](docs/runbooks/schuljahreswechsel.md) und
  [LiteLLM-Umzug](docs/runbooks/litellm-in-die-compose.md).
- [Konfiguration](docs/admin/konfiguration.md): neuer Abschnitt **Wann Änderungen wirken**
  — `.env` braucht `docker compose up -d`, `config/*.yaml` dagegen
  `docker compose restart backend cron`; bei falschem Befehl passiert nichts Sichtbares.
  Env-Tabelle vervollständigt (24 Variablen fehlten).
- Neu geschrieben: [Budget-System](docs/admin/budget.md) (Wochenmodell, Währung,
  Hochrechnung) und [Content-Moderation](docs/admin/content-moderation.md) (Klassifikator,
  Verhalten bei Störungen, Überwachung).
- [Installation](docs/admin/installation.md) um Modellkonfiguration und die beiden
  Prüfschritte ergänzt; [Nutzerverwaltung](docs/admin/nutzerverwaltung.md) um „Anmeldung
  fehlgeschlagen!" trotz richtigem Passwort (der OAuth-Client ist für die Gruppe nicht
  freigegeben — in den Logs der Plattform steht dazu nichts).
- Nutzerdoku: „monatliches Budget" durchgängig ersetzt.
### Migration

Reihenfolge: erst Modellnamen und Proxy-Config, dann `.env`, dann Datenbank, dann Budget.

- ⚠️ **Modellnamen auf Aufgabennamen umstellen.** Wer in `infra/litellm_config.yaml` noch
  Produktnamen als `model_name` führt (`gpt-4o-mini`, `text-embedding-3-small`,
  `gpt-image-1`), benennt sie um und zieht die `.env` nach: `CHAT_DEFAULT_MODEL=chat-standard`,
  `TITLE_MODEL=system-titel`, `EMBEDDING_MODEL=embedding-standard`,
  `IMAGE_DEFAULT_MODEL=bild-standard`. Danach prüfen, ob
  `MODEL_PICKER_HIDDEN_PREFIXES` noch zu den neuen Namen passt — sonst steht das
  Titelmodell sichtbar im Modellwähler.

  **Danach die Freigabematrix unter `/settings/models` neu setzen** — die Team-Allowlists
  enthalten die alten Namen und laufen sonst ins Leere. Ebenso Assistenten prüfen, die auf
  einen Modellnamen festgelegt sind. Die Embedding-Vektoren bleiben unberührt, solange
  `litellm_params.model` gleich bleibt. Vorlagen:
  [Modell-Szenarien](docs/admin/modell-szenarien.md). Kontrolle:
  `python scripts/check_litellm_config.py`.

- ⚠️ **Die eigene `infra/litellm_config.yaml` anpassen** — drei Dinge, die nicht griffen
  oder ab LiteLLM 1.83.7 den Start verhindern:

  | Prüfen | Warum |
  |---|---|
  | `guardrails:` steht unter `litellm_settings:` | Proxy startet nicht — Block auf die oberste Ebene heben |
  | `guardrail: regex` | Typ existiert nicht mehr; Drogen-Anleitungen deckt die Kategorie `drug_instructions` ab |
  | Schwellen unter `guardrail_info.params` | Wurden nie gelesen — gehören unter `litellm_params.thresholds` |

- ⚠️ **LiteLLM-Proxy aus dem eigenen Stack übernehmen** —
  [Runbook](docs/runbooks/litellm-in-die-compose.md). Kern: Der Datenbestand des Proxys
  muss mitgenommen werden (Virtual Keys, auf die `pseudonym_audit.litellm_key` verweist,
  dazu Budgets und Verbrauch). `LITELLM_MASTER_KEY` und `LITELLM_SALT_KEY` unverändert
  übernehmen — war der Salt-Key nie gesetzt, gehört dort der alte Master-Key hinein.
  In der `.env` `LITELLM_PROXY_URL=http://litellm:4000` und
  `LITELLM_DATABASE_URL=…@db:5432/litellm`; die Datenbank auf Bestandsinstallationen
  einmalig anlegen:

  ```bash
  docker compose exec db psql -U postgres -c "CREATE DATABASE litellm"
  ```

  Wer getrennt weiterbetreibt, schaltet den neuen Dienst über eine
  `docker-compose.override.yml` ab (Snippet im Runbook).

- **Neue Variablen in der `.env`:**
  - `IMAGE_PRICES` — **Pflicht**, sobald Bildmodelle laufen, die LiteLLM nicht aus seiner
    eingebauten Tabelle kennt; ohne sie kostet jedes Bild 0,00. In **einfachen**
    Anführungszeichen setzen.
  - `GUARDRAIL_HEALTH_FILE` / `GUARDRAIL_HEALTH_MAX_AGE_H` — für die Zustandsanzeige; muss
    auf dieselbe Datei zeigen wie `health_file` in der LiteLLM-Config.
  - `IMAGE_MODELS_PATH` — nur, wenn die Bildarten-Datei woanders liegt; anzulegen aus
    `config/image_models.example.yaml`. Sie löst
    `IMAGE_DEFAULT_MODEL`, `IMAGE_SIZES`, `IMAGE_DEFAULT_FORMAT` und
    `IMAGE_RESPONSE_FORMAT` ab; jedes dort genannte Modell braucht einen Eintrag in
    `IMAGE_PRICES`.

- **`alembic upgrade head`** — Migrationen `0047`–`0052`: `assistants.image_kinds`,
  `generated_images.bildart`, `provider_model` an `messages`, `generated_images` und
  `artifacts`, Tabelle `budget_accrual`, Entfernen des Vektorindex. Bestandsassistenten
  behalten ihr Verhalten; bereits erzeugte Bilder lassen sich mangels gespeicherter Bildart
  nicht variieren.

- ⚠️ **Budget: Umstellung aufs Wochenmodell — drei Schritte, in dieser Reihenfolge.**

  1. `config/budget_tiers.yaml` auf `wochenbudget_eur` umstellen (Vorlage:
     `config/budget_tiers.example.yaml`). Das alte `max_budget_eur` wird nicht mehr gelesen; ohne Umstellung
     gibt es kein Budget.
  2. `python scripts/migrate_budget_duration.py --verbrauch-zuruecksetzen` — entfernt
     `budget_duration: 1mo` aus der Proxy-Datenbank. Solange das steht, setzt LiteLLM den
     Verbrauch weiter monatlich zurück.
  3. `python scripts/weekly_budget_accrual.py --neuaufbau` — ersetzt die Monats-Obergrenzen.

  Die Reihenfolge ist nicht beliebig: `max_budget = NULL` **und** `= 0` bedeuten bei
  LiteLLM *kein Limit*. Deshalb lässt Schritt 2 die Grenzen stehen und erst Schritt 3
  ersetzt sie.

  ⚠️ Schritt 3 wirkt **nur innerhalb einer Unterrichtswoche**. In den Ferien oder außerhalb
  des Schuljahres aus `school_year.yaml` meldet der Lauf `keine Unterrichtswoche` und lässt
  die Monatsgrenzen stehen. Dann zuerst das Schuljahr umstellen
  ([Runbook](docs/runbooks/schuljahreswechsel.md)); die Grenzen setzt der erste
  Montagslauf.

- **Nach dem Update einmal `python scripts/embedding_backfill.py`** — die Titel-Aufnahme
  betrifft Leitideen, Kapitel und PK-Gruppen:

  ```sql
  UPDATE context_nodes SET embedding = NULL
   WHERE status = 'active' AND content_type IN ('leitidee', 'kapitel', 'pk_gruppe');
  ```

- **Zum Schluss `python scripts/check_production.py`** — Secrets, Host-Schutz, Audit-IP,
  Anmeldung und Schuljahr auf einen Blick.

- **Nur bei Anbieterwechsel:** Ein anderes Embedding-Modell heißt fast immer eine andere
  Vektorbreite — dann Spalte umstellen und **alle** Knoten neu einbetten
  ([Runbook Modellwechsel](docs/runbooks/modellwechsel.md)).

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
