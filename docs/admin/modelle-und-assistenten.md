# Modelle & Assistenten

## Welche Modelle es geben sollte

Die Plattform schreibt keine Modelle vor, aber die Namen, unter denen sie in der
LiteLLM-Config stehen, sind **Nutzertext**: Sie erscheinen im Modellwähler, auch bei
Schüler:innen. Deshalb Aufgaben benennen statt Produkte — `chat-standard` statt
`gpt-4o-mini`. Ein Anbieterwechsel bleibt dann eine Zeile in der Proxy-Config; `.env`,
Assistenten und Freigaben bleiben unberührt.

Bewährt hat sich diese Staffel:

| Name | Wofür | Freigabe |
|---|---|---|
| `chat-schnell` | Kurze Fragen, Vokabeln, Textvereinfachung. Günstig, antwortet sofort | alle |
| `chat-standard` | Arbeitspferd: Erklärungen, Hausaufgabenhilfe, Feedback | alle |
| `chat-code` | Programmieraufgaben | alle |
| `chat-reasoning` | Denkt vor der Antwort — mehrschrittige Aufgaben, Herleitungen | höhere Jahrgänge |
| `chat-komplex` | Analyse, lange Texte, Unterrichtsplanung. Deutlich teurer | nur Lehrkräfte |
| `system-titel` | Gesprächstitel — **muss in jeder Allowlist stehen**, s. u. | alle (ausgeblendet) |
| `system-moderation` | Jugendschutz-Klassifikator | — (ausgeblendet) |
| `embedding-standard` | Kontextspeicher, semantische Suche | — (ausgeblendet) |
| `bild-standard` | Bildgenerierung | nach Bedarf |

`chat-standard` und `chat-reasoning` dürfen dasselbe Modell sein — bei Modellen mit
regelbarer Denktiefe unterscheidet sie nur `reasoning_effort`. Didaktisch lässt sich das
gut erklären: derselbe Assistent, aber er denkt erst nach.

Wer **einzelne Modelle** namentlich anbieten will (etwa damit Lehrkräfte einen Assistenten
bewusst binden können), stellt einen Anbieter-Präfix voran: `ionos-gpt-oss-120b`. Solche
Einträge nur für Lehrkräfte freischalten — sonst stünden Alias und expliziter Name desselben
Modells nebeneinander im Schüler-Dropdown. Und: Ein Assistent auf einem expliziten Namen
folgt einem schulweiten Modellwechsel **nicht** und bricht, wenn der Eintrag entfällt (s.
[Assistenten mit verschwundenem Modell](#assistenten-mit-verschwundenem-modell)).

Welche Modelle sich wofür eignen — mit gemessenen Preisen und Fallstricken —, steht in
[Vor der Installation](vor-der-installation.md#modellwahl).

## Modelle freischalten (`/settings/models`)

Die Modell-Freischaltungsmatrix legt fest, welche KI-Modelle welchen
Nutzergruppen zur Verfügung stehen. Zeilen entsprechen den in LiteLLM
konfigurierten Modellen, Spalten den Nutzergruppen (Jahrgänge und Rollen).

**Solange die Matrix leer ist, können Nutzer:innen keine Anfragen stellen.**
Nach jeder Erstinstallation und nach dem Anlegen neuer LiteLLM-Teams daher
immer zuerst die Matrix befüllen.

**Empfohlene Vorgehensweise:**

1. `/settings/models` aufrufen.
2. Für jede Nutzergruppe mindestens ein Modell aktivieren.
3. Speichern — die Änderungen sind sofort wirksam.

Als Einstiegspunkt empfiehlt es sich, zunächst ein einzelnes,
kostengünstiges Modell für alle Gruppen freizuschalten und die Matrix
später gezielt zu erweitern.

### Interne Modelle aus dem Modellwähler ausblenden

Neben den Chat-Modellen stehen in LiteLLM auch Modelle, die **niemand manuell wählen soll**:
das Modell für die Gesprächstitel, ein etwaiger Moderations-Klassifikator sowie Embedding-
und Bildmodelle. Ohne Filter erscheinen sie alle im Modellwähler, den Schüler:innen bei
jedem freien Chat sehen.

`MODEL_PICKER_HIDDEN_PREFIXES` (Default `["system-","embedding-","bild-"]`) blendet sie aus.
Die Empfehlung ist daher, solche Modelle in der LiteLLM-Config entsprechend zu benennen —
etwa `system-titel` statt `gpt-4o-mini`.

> **Der Filter ist rein kosmetisch.** Er ändert **keine** Freigabe. Das Titelmodell muss
> weiterhin in **jeder** Team-Allowlist stehen: Die Titelgenerierung läuft über den
> persönlichen Virtual Key der Nutzer:innen, nicht über den Master-Key — LiteLLM prüft
> also deren Allowlist. Genau deshalb filtert die Freischaltungsmatrix oben **nicht**;
> dort muss das Modell sichtbar bleiben, damit es sich überhaupt freischalten lässt.

## Bildgenerierung: Bild-Modelle & Bild-Assistenten

Bildgenerierung ist an **zwei Schlüssel** gebunden — beide müssen gesetzt sein, damit
im Chat tatsächlich Bilder entstehen:

1. **Bild-Modell für die Gruppe freigeschaltet.** Auf `/settings/models` gibt es unter
   den Chat-Modellen einen zweiten Abschnitt **„Bild-Modelle"**. Er erscheint nur, wenn
   in LiteLLM ein Bild-Modell mit `model_info.mode: image_generation` konfiguriert ist.
   Beide Matrizen schreiben in dieselbe LiteLLM-Team-Allowlist — die Freigaben werden
   gegenseitig **bewahrt** (das Speichern der Chat-Matrix wischt Bild-Freigaben nicht weg
   und umgekehrt).
2. **Assistent mit der Fähigkeit `image_generation`.** Im Assistenten-Editor unter
   *Fähigkeiten* die Checkbox **„Bildgenerierung"** aktivieren
   (siehe [Fähigkeiten](#fähigkeiten-tool_groups)).

**Nutzerseitige Auffindbarkeit:** Assistenten mit Bildgenerierung erscheinen zusätzlich
unter dem Seitenleisten-Menüpunkt **„Werkzeuge"** (`/tools`), der alle
artefakterzeugenden Assistenten bündelt.

**Jugendschutz-Prüfpunkt:** Ein **schulweiter**, für Schüler:innen sichtbarer
Bild-Assistent geht **immer** in die Admin-Freigabe (`pending_review`) — auch wenn der
allgemeine Schalter für schulweites Teilen aus ist. Details in
[Content-Moderation → Bild-Assistenten](content-moderation.md).

**Lokaler Bild-Server (sensibler Pfad):** Ein lokaler, OpenAI-kompatibler Bild-Server
(z. B. vLLM-Omni) lässt sich als Bild-Modell in LiteLLM eintragen
(`infra/litellm_config.yaml`, `model_info.mode: image_generation`). Es werden **keine**
extern gehosteten Bild-URLs verarbeitet, die Bytes bleiben im Schulnetz.

> Das ist eine **Datenschutz**-Option für Schulen, die die Hardware haben — kein Ersatz bei
> erschöpftem Budget und keine Zusage der Plattform. Bildmodelle brauchen eine GPU; ohne sie
> ist der Weg nicht gangbar. Vor dem Produktivbetrieb end-to-end testen.

### Bildarten festlegen (`config/image_models.yaml`)

Eine **Bildart** bündelt ein Bildmodell mit den Formaten, die es beherrscht, und einem
Namen, den Menschen verstehen. Sie ist das, was ein Assistent anbietet und was das
Chat-Modell wählt — der Modellname taucht in der Oberfläche nirgends auf.

```yaml
bildarten:
  - id: standard
    label: "Standard (quadratisch)"
    beschreibung: >
      Für alle üblichen Bilder. Schnell und speicherschonend; erzeugt
      ausschließlich quadratische Bilder.
    modell: bild-standard          # `model_name` aus der LiteLLM-Config
    formate:
      quadratisch: "1024x1024"     # Name → Pixelgröße
    standardformat: quadratisch
    response_format: ""            # leer = Parameter weglassen

standard_bildart: standard
```

Die Datei ist **optional**. Fehlt sie, entsteht aus `IMAGE_DEFAULT_MODEL`, `IMAGE_SIZES`,
`IMAGE_DEFAULT_FORMAT` und `IMAGE_RESPONSE_FORMAT` genau eine Bildart `standard`, und alles
verhält sich wie zuvor. Wer sie anlegt, löst diese vier Variablen ab. Vorlage:
`config/image_models.example.yaml`.

> **Eine Bildart je Assistent ist der Regelfall.** Führt ein Assistent genau eine, hat das
> Werkzeug **keinen** Auswahlparameter: Verhalten und Kosten sind vorhersagbar, und es gibt
> nichts, was ein Chat-Modell falsch wählen könnte. Mehrere Bildarten sind die Ausbaustufe —
> dann entscheidet das Chat-Modell anhand von `label` und `beschreibung`, und das ist nur so
> verlässlich wie dessen Function-Calling. Bei schwächeren Modellen lieber zwei Assistenten
> anlegen als eine Auswahl anbieten.

**Benennung.** Eine Bildart bestimmt Modell und Formate — **nicht den Stil**; der entsteht
aus dem System-Prompt des Assistenten. Ein Stilname wie „Comic" ist deshalb nur ehrlich,
wenn das *Modell* darauf spezialisiert ist. Unterscheiden sich zwei Modelle nur in
Formatfähigkeit, Tempo oder Dateigröße, benennt man genau das.

**Formate.** Links steht der Name, den das Chat-Modell wählt; rechts die Pixelgröße, die an
den Anbieter geht. Ein Anbieterwechsel ändert nur die rechte Seite — die Namen bleiben, und
damit bleibt auch das Vokabular stabil, das in Gesprächsverläufen steht. Zusätzliche
Formate sind frei ergänzbar (`"panorama": "1344x768"` fürs Tafelbild).

Kennt die gewählte Bildart ein gewünschtes Format nicht, wird auf das **nächstliegende
Seitenverhältnis** ausgewichen statt abgelehnt: „hoch" bei einem Modell, das nur quadratisch
kann, wird quadratisch — und das Chat-Modell nennt die Abweichung. Nur Größen eintragen, die
das Modell wirklich beherrscht; sonst scheitert der Aufruf beim Anbieter.

**Auswahl je Assistent.** Sind mehrere Bildarten konfiguriert, erscheint im
Assistenten-Editor unter *Fähigkeiten → Bildgenerierung* eine Auswahl. Nichts angehakt =
alle. Der Editor warnt, wenn eine gewählte Bildart für die Zielgruppe des Assistenten gar
nicht freigeschaltet ist.

**Zur Laufzeit** bietet das Werkzeug nur Bildarten an, deren Modell für den Jahrgang der
Nutzer:in freigeschaltet ist — was der Proxy ohnehin abweisen würde, sieht das Chat-Modell
gar nicht erst. Ist der Freigabestand nicht abrufbar, wird nicht gefiltert; die Durchsetzung
bleibt beim Proxy, und dessen Ablehnung erscheint als lesbarer Satz statt als Fehlercode.

> ⚠️ **Jedes in einer Bildart genannte Modell braucht einen Eintrag in `IMAGE_PRICES`.**
> Ohne ihn kostet jedes Bild 0,00 $ und läuft am EUR-Budget vorbei, ohne dass etwas
> fehlschlägt. `cd backend && python scripts/check_litellm_config.py` prüft das — zusammen
> mit der Frage, ob das Modell im Proxy überhaupt existiert und `mode: image_generation`
> trägt. Fehler in der Datei selbst (unbekanntes Standardformat, doppelte ID) verhindern
> den Start des Backends mit einer Meldung, die die gültigen Werte nennt.

### Base64 erzwingen (`response_format`)

| Wert | Wann |
|---|---|
| *(leer)* | Modelle, die den Parameter ablehnen und ohnehin nur Base64 liefern — **gpt-image-1**, **FLUX.1-schnell**, **FLUX.2-klein** |
| `b64_json` | Modelle, die sonst eine extern gehostete URL liefern würden |

Der zweite Fall ist kein Feinschliff, sondern Voraussetzung: Liefert der Anbieter eine URL,
bricht das Backend bewusst ab, statt die Bytes über einen zweiten Request beim Anbieter
abzuholen. `url` ist als Wert deshalb nicht zulässig und wird beim Start abgewiesen.

**Kosten:** Bildgenerierung läuft über das **bestehende** USD-Budget der Nutzer:innen
(kein separates Kontingent). Siehe [Budget-System → Bildgenerierung](budget.md).

## Assistenten anlegen (`/assistants/manage/new`)

Assistenten sind vorkonfigurierte Chat-Umgebungen mit einer bestimmten Rolle
oder Aufgabe. Admins und Lehrkräfte können Assistenten anlegen.

**Felder beim Anlegen:**

| Feld | Beschreibung |
|------|-------------|
| Name | Wird Nutzer:innen angezeigt |
| Beschreibung | Kurze Erklärung des Zwecks |
| System-Prompt | Anweisung an die KI — legt Verhalten und Rolle fest |
| Modell | Leer („Schulweiter Standard"): nutzt `CHAT_DEFAULT_MODEL` und folgt einem Modellwechsel automatisch. Gesetzt: fix an dieses Modell gebunden |
| Icon / Farbe | Optische Unterscheidung in der Übersicht |

**Test-Chat:** Beim Bearbeiten eines Assistenten steht direkt ein Test-Chat
zur Verfügung. Änderungen am System-Prompt können so ausprobiert werden,
bevor sie gespeichert werden.

## Unterrichtsplanung-Assistent einrichten

Der Jahresplan-Assistent ermöglicht es Lehrkräften, ihren Jahresplan per
Konversation zu erstellen. Er liest Lehrplan und Slot-Angebot, schlägt eine
UE-Verteilung vor und schreibt den Plan nach Bestätigung direkt in die
Plattform.

**Voraussetzung:** UP-Phase-1 und UP-Phase-2 müssen aktiv sein (Datenmodell
und Planer-UI), der Bildungsplan muss für die betreffenden Fächer importiert
sein.

**Einmalige Einrichtung (Seed-Skript):**

```bash
cd backend
python scripts/seed_assistants.py
```

Das Skript liest `config/assistants.yaml` (bzw. `config/assistants.example.yaml`)
und legt alle darin definierten Assistenten an, sofern noch kein Assistent
gleichen Namens existiert. Mit `--dry-run` kann man vorab prüfen, was angelegt
würde.

Danach ist der Assistent einsatzbereit — er nutzt das schulweite Standardmodell
(`CHAT_DEFAULT_MODEL`). Nur wenn er an ein **bestimmtes** Modell gebunden sein soll:

1. `/assistants/manage` aufrufen.
2. „Jahresplanung" in der Liste anklicken.
3. Im Feld **Modell** das gewünschte Modell wählen. Für die Planungswerkzeuge muss es
   Function-Calling beherrschen (im Auswahlfeld mit ⚙ markiert).
4. Speichern.

> **Standard oder gebunden?** Bleibt das Feld auf „Schulweiter Standard", folgt der
> Assistent einem späteren Modellwechsel automatisch. Ein fest gewähltes Modell bindet
> ihn daran — er funktioniert nicht mehr, sobald dieses Modell aus der LiteLLM-Config
> fällt. Für die meisten Assistenten ist der Standard die wartungsärmere Wahl.

**Verhalten in der UI:** Öffnet eine Lehrkraft die Planungsansicht einer
Unterrichtsgruppe und klickt auf „Assistent", wird der Chat mit diesem
Assistenten automatisch vorausgewählt. Existieren mehrere Assistenten mit
aktivierter Unterrichtsplanung, wird der erste in der Sortierreihenfolge
verwendet.

### Fähigkeiten (`tool_groups`)

Eine **Fähigkeit** ist das, was ein Assistent im Chat kann. Gesteuert wird sie über das
Feld `tool_groups`; im Editor ist es der Abschnitt *Fähigkeiten*.

> **Nicht verwechseln:** Ein **Werkzeug** ist ein *Assistent*, der etwas herstellt — die
> Sammlung dieser Assistenten steht für Nutzer:innen unter `/tools`. Eine **Funktion**
> ist die technische Schnittstelle, die das Chat-Modell aufruft (`generate_image`).
> Diese drei Begriffe hießen früher alle „Werkzeug".

| Fähigkeit | Funktionen | Freischaltung |
|---|---|---|
| `planning` | Plan lesen/schreiben: Slots, UE-Zuordnung, Themen, Kategorien sowie der **Verschiebe-Dialog** (`get_reflow_context`, `apply_plan_operations`, `undo_last_change`) | nur **Lehrkräfte** der Gruppe, Chat mit Gruppenbezug |
| `student_planning` | nur lesend `get_exam_scope` (Termin + Umfang der nächsten Klassenarbeit) | jede:r mit Gruppenbezug — auch **Schüler:innen** |
| `image_generation` | Bildgenerierung im Chat (`generate_image`) | Assistent führt die Gruppe **und** ein Bild-Modell ist fürs Team freigeschaltet; schülersichtbare schulweite Bild-Assistenten erst nach Admin-Freigabe |

Schreibende Planungs-Funktionen bleiben damit strikt an die Lehrkraft-Rolle gebunden;
für Lernplan-/Prüfungsvorbereitungs-Assistenten von Schüler:innen genügt
`student_planning`.

### Verschiebe-Assistent einrichten

Der Verschiebe-Assistent hilft Lehrkräften, den Plan bei Ausfall, Verschiebungen
oder offenen Phasen neu zu ordnen. Er nutzt **dieselbe** Fähigkeit `planning`
wie der Jahresplan-Assistent, aber einen eigenen System-Prompt:

1. Einen Assistenten anlegen (oder den bestehenden Planungs-Assistenten erweitern).
2. `tool_groups` enthält **`planning`**.
3. Als System-Prompt den Inhalt von `config/prompts/verschiebe_assistent.md` setzen.
4. Das Modell auf „Schulweiter Standard" belassen oder eines mit ⚙ (Function-Calling) wählen.

Die Auslöser in der Planungs-UI (Ausfall-Banner, Drag & Drop einer geplanten Stunde,
Halbjahres-Hinweis, Überhang-Hinweisleiste) öffnen jeweils einen Chat mit
Gruppenbezug und vorbefülltem Anliegen — ein freigeschalteter Assistent mit
`planning` ist Voraussetzung, damit die Funktionen greifen.

## Assistenten freigeben (`/settings/assistants`)

Neu angelegte Assistenten sind zunächst nicht öffentlich sichtbar. Die
Freigabe erfolgt unter `/settings/assistants`:

- **Aktiviert:** Der Assistent ist für Nutzer:innen sichtbar und startbar.
- **Deaktiviert:** Der Assistent ist nur für Admins und Lehrkräfte sichtbar
  (z. B. für Assistenten in Entwicklung).

Die Sichtbarkeit kann pro Assistent gesteuert werden. Eine granulare
Freigabe nach Rolle oder Jahrgang ist in einer späteren Version geplant.

## Assistenten mit verschwundenem Modell

Ein Assistent kann fest an ein Modell gebunden sein (Feld **Modell** gesetzt statt
„Schulweiter Standard"). Fällt dieses Modell später aus der LiteLLM-Config — Anbieterwechsel,
abgekündigtes Modell, Tippfehler beim Umbenennen — schlägt der Assistent beim Chatten fehl,
**ohne dass die Ursache erkennbar wäre**.

Die Plattform gleicht das daher automatisch ab und warnt an zwei Stellen:

- **`/assistants/manage`** — ein Banner über der Liste nennt die betroffenen Assistenten, und
  die jeweilige Zeile ist markiert.
- **`/settings/models`** — derselbe Hinweis, weil hier die Ursache entsteht: Wer die
  Freischaltung oder die LiteLLM-Config ändert, sieht sofort, was dadurch bricht.

**Behebung:** Im Assistenten ein verfügbares Modell wählen — oder das Feld leeren, damit er
dem schulweiten Standard folgt und künftige Wechsel automatisch mitmacht.

> Es wird **nichts automatisch umgestellt.** Welches Modell fachlich passt, entscheidet die
> Schule; ein stiller Austausch könnte einen Assistenten auf ein Modell ohne Function-Calling
> setzen und seine Funktionen lahmlegen.
>
> Ist LiteLLM nicht erreichbar, erscheint **kein** Hinweis — dann ist der Zustand ungeprüft,
> nicht unauffällig. Eine leere Liste bedeutet in dem Fall also keine Entwarnung.

## Konfiguration prüfen (`check_litellm_config.py`)

Mehrere Fehlkonfigurationen des Proxys brechen **still** — man merkt sie erst Wochen später
an einer Kostenstatistik, die auf 0 steht, oder an Funktionen, die nicht mehr greifen.
Das Skript gleicht den laufenden Proxy mit der `.env` ab:

```bash
cd backend && python scripts/check_litellm_config.py
```

Geprüft wird:

| Fund | Warum es sonst unbemerkt bleibt |
|---|---|
| Modellname aus der `.env` existiert im Proxy nicht | 400er ohne erkennbare Ursache |
| Kein `input_cost_per_token` / `output_cost_per_token` | SpendLog bleibt 0 → EUR-Budgets, 429-Enforcement, `/budget` und `/statistics/costs` laufen ins Leere |
| `supports_function_calling` nicht gesetzt | Funktionen fallen stumm aus oder gehen an ein Modell, das sie nicht kann |
| Bildmodell ohne `mode: image_generation` | erscheint nicht in der Bild-Freigabe-Matrix |
| `TITLE_MODEL` im Modellwähler sichtbar | Schüler:innen sehen ein Modell, das nicht zur Auswahl gedacht ist |
| Platzhalter aus der Vorlage (`<…>`, `TODO`) | die Config wurde nur halb ausgefüllt |

> **Modelle, die LiteLLM kennt, brauchen keine eigenen Preise.** Der Proxy reichert
> `/model/info` aus seiner eingebauten Preistabelle an (rund 2650 Einträge). Preise
> eintragen muss man nur für Modelle, die als `openai/<id>` mit eigener `api_base` laufen —
> also alles bei IONOS, OVH oder auf lokalen Servern.

Exit-Code 0 heißt: alles in Ordnung, soweit sich das ohne echten Aufruf feststellen lässt.
Offen bleibt danach nur der Praxistest — eine Chat-Antwort erzeugen und prüfen, dass die
SpendLog-Zeile einen Betrag **> 0** trägt.
