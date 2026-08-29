# Modell-Szenarien: welcher Anbieter, welche Konfiguration

Die Plattform schreibt keinen Anbieter vor. Dieses Kapitel zeigt für die gängigen Fälle,
**wie beide Seiten der Konfiguration zusammenpassen müssen** — die `.env` der Anwendung und
die `model_list` des LiteLLM-Proxys — und welche Fallen je Anbieter lauern. Fast alle davon
scheitern still: Es bricht nichts ab, es passiert nur nicht das Gewünschte.

Die Auswahl der Modelle selbst (Preise, Erfahrungswerte, Empfehlungen) steht in
[Vor der Installation](vor-der-installation.md). Was die einzelnen Stufen bedeuten, in
[Modelle & Assistenten](modelle-und-assistenten.md).

---

## Zwei Seiten, eine Zuordnung

Die `.env` benennt **Aufgaben**, die LiteLLM-Config benennt **Modelle**. Dazwischen steht
der Aliasname:

```
.env                      LiteLLM-Config                    Anbieter
CHAT_DEFAULT_MODEL=  ───▶  model_name: chat-standard  ───▶  model: openai/openai/gpt-oss-120b
  chat-standard              litellm_params:                  api_base: …ionos…
```

**Das ist der Grund, warum die `.env` zwischen den Szenarien fast gleich bleibt.** Ein
Anbieterwechsel ändert die rechte Spalte — nicht die Aufgabenzuordnung, nicht die
Assistenten-Datensätze, nicht die Team-Allowlists. Es gibt genau **zwei** Ausnahmen:

| Variable | Warum sie doch anbieterabhängig ist |
|---|---|
| `EMBEDDING_DIMENSIONS` | Muss zur Vektorbreite des Modells **und** zur Datenbankspalte passen. Ein Wechsel verlangt Schemaänderung + vollständiges Re-Embedding ([Runbook](../runbooks/modellwechsel.md)). |
| `IMAGE_PRICES` | Enthält Anbieter-Modell-IDs. Für Bilder ist das die **einzige** wirksame Preisquelle. |

Alles andere — Guardrails, Callbacks, `litellm_settings`, Team-Allowlists — ist zwischen
allen Szenarien identisch. Die vollständig kommentierte Fassung dieser Blöcke steht in
`infra/litellm_config.ionos.example.yaml`; die Szenarien unten zeigen nur die `model_list`.

---

## Was jeder Anbieter abdeckt

Die wichtigste Tabelle des Kapitels. Sie entscheidet mehr als der Preis, weil eine fehlende
Modalität nicht durch Geld zu lösen ist.

| Anbieter | Chat | Embedding | Bild | In LiteLLM |
|---|---|---|---|---|
| **IONOS** | ✅ | ✅ BGE-M3, **1024** | ✅ FLUX | `openai/<id>` + `api_base` — **Preise von Hand** |
| **Mistral** | ✅ | ✅ `mistral-embed`, **1024** | ❌ **keines** | `mistral/<id>` — Preise eingebaut |
| **OpenAI** | ✅ | ✅ `text-embedding-3-*`, **1536** (kürzbar) | ✅ `gpt-image-1` | `<id>` — Preise eingebaut |
| **Anthropic** | ✅ | ❌ **keines** | ❌ **keines** | `anthropic/<id>` — Preise eingebaut |

Daraus folgen zwei harte Aussagen:

- **Anthropic allein ist nicht möglich.** Ohne Embedding-Modell gibt es keinen
  Kontextspeicher, keine semantische Suche und keinen Bildungsplan-Bezug. Anthropic kommt
  nur im Mischbetrieb infrage.
- **Mistral allein bedeutet keine Bildgenerierung.** Das ist tragbar — aber es ist eine
  Entscheidung, die vor dem Zuschnitt der Assistenten fallen muss, nicht danach.

> **Zur Preisquelle.** Bei Mistral, OpenAI und Anthropic kennt LiteLLM die Preise aus seiner
> eingebauten Tabelle; man muss nichts eintragen. Der Abgleich gegen
> [mistral.ai/pricing/api](https://mistral.ai/pricing/api/) am 28.08.2026 ergab **exakte
> Übereinstimmung** bei allen dort gelisteten Modellen. Es bleibt trotzdem eine Quelle, die
> man nicht kontrolliert: Sie wird mit der Bibliothek ausgeliefert und altert, wenn der
> Anbieter die Preise ändert. Beim Aufsetzen einmal gegenprüfen — danach ist es Routine
> beim Bibliotheks-Update.
>
> Bei IONOS stellt sich die Frage nicht: Dort **muss** jeder Preis in die Config, weil
> LiteLLM `openai/<id>` mit eigener `api_base` nicht kennt. Fehlt er, meldet der SpendLog 0
> — Budgets, 429-Sperre und Kostenstatistik laufen ins Leere.

---

## Szenario A — IONOS (Referenzfall)

EU-Anbieter, alle drei Modalitäten, vollständig gemessen. **Vollständige Vorlage:**
`infra/litellm_config.ionos.example.yaml` — die hier gezeigten Einträge sind daraus gekürzt.

```yaml
model_list:
  - model_name: chat-standard
    litellm_params:
      model: openai/openai/gpt-oss-120b     # doppeltes `openai/`: Provider + Anbieter-ID
      api_base: os.environ/IONOS_API_BASE
      api_key: os.environ/IONOS_API_KEY
      reasoning_effort: low                 # gpt-oss lehnt `none` ab
      allowed_openai_params: ["reasoning_effort"]
    model_info:
      supports_function_calling: true       # PFLICHT — sonst fallen alle Funktionen aus
      input_cost_per_token: 0.00000017      # PFLICHT — sonst Spend 0
      output_cost_per_token: 0.00000071

  - model_name: embedding-standard
    litellm_params:
      model: openai/BAAI/bge-m3
      api_base: os.environ/IONOS_API_BASE
      api_key: os.environ/IONOS_API_KEY
      encoding_format: float                # PFLICHT — sonst base64 und der Speicher ist tot
    model_info:
      mode: embedding
      input_cost_per_token: 0.00000002

  - model_name: bild-standard
    litellm_params:
      model: openai/black-forest-labs/FLUX.1-schnell
      api_base: os.environ/IONOS_API_BASE
      api_key: os.environ/IONOS_API_KEY
    model_info:
      mode: image_generation
      input_cost_per_image: 0.032           # dokumentierend; wirksam ist IMAGE_PRICES
```

```bash
EMBEDDING_DIMENSIONS=1024
EMBEDDING_SEND_DIMENSIONS=false            # BGE-M3 lehnt den Parameter ab
IMAGE_PRICES='{"black-forest-labs/FLUX.1-schnell":0.032}'
```

---

## Szenario B — Mistral

EU-Anbieter (Frankreich), eigener LiteLLM-Provider. **Kein Bildmodell.**

Der Unterschied zu IONOS ist die Anbindung, nicht die Modellqualität: `mistral/<id>` ohne
`api_base` — damit kommen Preise, Kontextfenster, Function-Calling und Vision aus LiteLLMs
Tabelle. Der gesamte Preispflege-Aufwand entfällt.

```yaml
model_list:
  - model_name: chat-schnell
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY
    # kein model_info nötig — Preise und Fähigkeiten kennt LiteLLM

  - model_name: chat-standard
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: chat-code
    litellm_params:
      model: mistral/codestral-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: chat-komplex
    litellm_params:
      model: mistral/mistral-large-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: system-titel
    litellm_params:
      model: mistral/mistral-small-latest   # NICHT ministral — siehe unten
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: embedding-standard
    litellm_params:
      model: mistral/mistral-embed
      api_key: os.environ/MISTRAL_API_KEY
    model_info:
      mode: embedding                        # einziges Pflichtfeld
```

```bash
EMBEDDING_DIMENSIONS=1024                   # wie BGE-M3 — aber trotzdem Re-Embedding!
EMBEDDING_SEND_DIMENSIONS=false
# IMAGE_* entfällt: keine Bildgenerierung
```

> ⚠️ **Nicht das billigste Modell zum Titelmodell machen.** Gemessen mit dem echten
> Titel-Prompt („maximal 6 Wörter"): `ministral-8b` traf **0 von 4** (7–33 Wörter),
> `ministral-3b` 2 von 4. Ab `mistral-small` sitzt es (4/4, 3–4 Wörter). Ein zu langer
> Titel wird in der Historie mitten im Wort abgeschnitten — dauerhaft sichtbar.

> **Reasoning verhält sich umgekehrt zu IONOS.** Die Magistral-Reihe denkt **nicht von
> allein**: „antworte knapp" ergab 5–12 Tokens, „denke Schritt für Schritt" 386–461. Ein
> `reasoning_effort`-Parameter ist hier also weder nötig noch wirksam — eine denkende Stufe
> entsteht über den **System-Prompt des Assistenten**.

---

## Szenario C — OpenAI

Alle drei Modalitäten, in LiteLLM ohne Präfix ansprechbar, Preise eingebaut.

```yaml
model_list:
  - model_name: chat-schnell
    litellm_params:
      model: gpt-4o-mini            # billigstes, schnellstes UND formattreu (gemessen)
      api_key: os.environ/OPENAI_API_KEY

  - model_name: chat-standard
    litellm_params:
      model: gpt-4.1-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: chat-komplex
    litellm_params:
      model: gpt-5                  # spürbar langsamer (≈7,8 s) — nur für Lehrkräfte
      api_key: os.environ/OPENAI_API_KEY

  - model_name: system-titel
    litellm_params:
      model: gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: embedding-standard
    litellm_params:
      model: text-embedding-3-small
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      mode: embedding

  - model_name: bild-standard
    litellm_params:
      model: gpt-image-1
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      mode: image_generation
```

```bash
EMBEDDING_DIMENSIONS=1536
EMBEDDING_SEND_DIMENSIONS=true              # text-embedding-3-* kann kürzen
IMAGE_RESPONSE_FORMAT=                      # gpt-image-1 lehnt den Parameter ab
IMAGE_PRICES='{"gpt-image-1":<Preis je Bild>}'
```

Gemessen am 28.08.2026: **alle vier geprüften Chat-Modelle** riefen Funktionen korrekt auf
und hielten die 6-Wörter-Grenze des Titel-Prompts ein — anders als bei IONOS und Mistral,
wo jeweils das billigste Modell daran scheitert. Preise und Antwortzeiten in
[Vor der Installation](vor-der-installation.md#openai).

Zwei Eigenheiten aus dem Betrieb bis August 2026:

- `text-embedding-3-*` unterstützt als eines der wenigen Modelle den `dimensions`-Parameter
  zum Kürzen. Wer ihn nutzt, kann die Spaltenbreite frei wählen — bei allen anderen
  Anbietern ist sie vorgegeben.
- **Leere Eingaben** nimmt OpenAI beim Embedding klaglos an, BGE-M3 quittiert sie mit einem
  Fehler. Wer von OpenAI wegwechselt, sieht deshalb plötzlich Fehler an Knoten, die vorher
  unauffällig waren — kein neuer Defekt, sondern eine vorher verdeckte Lücke.

---

## Szenario D — Anthropic

**Nur im Mischbetrieb möglich.** Anthropic bietet weder Embeddings noch Bildgenerierung;
beides muss von einem zweiten Anbieter kommen.

```yaml
model_list:
  - model_name: chat-komplex
    litellm_params:
      model: anthropic/claude-sonnet-4-5
      api_key: os.environ/ANTHROPIC_API_KEY
      # Nur bei einem *identity-linked* Schlüssel nötig — siehe unten.
      # extra_headers: {"anthropic-workspace-id": "wrkspc_…"}
```

> ⚠️ **Anthropic kennt zwei Sorten API-Schlüssel, und eine davon braucht einen zusätzlichen
> Header.** Ein an eine Identität gebundener Schlüssel (*identity-linked*) weist **jeden**
> Aufruf ab, solange `anthropic-workspace-id` fehlt:
>
> ```
> 400 invalid_request_error — anthropic-workspace-id is required when
> authenticating with an identity-linked API key
> ```
>
> Das betrifft nicht nur Sonderfälle, sondern auch die einfachste Chat-Anfrage (geprüft am
> 28.08.2026). Die Workspace-ID steht in der Anthropic Console unter *Settings →
> Workspaces*; in LiteLLM wird sie über `extra_headers` mitgegeben. Wer sich das ersparen
> will, legt stattdessen einen Schlüssel an, der nicht identitätsgebunden ist — dann
> genügt `api_key`.

Gemessen am 28.08.2026 (Preise und Erfahrungswerte in
[Vor der Installation](vor-der-installation.md#anthropic)): Alle drei geprüften Modelle
beherrschen Funktionsaufrufe. **Anthropic ist der teuerste der vier Anbieter** — schon das
kleinste Modell kostet mehr als `mistral-large`. Als Stufe für alle ist das schwer zu
rechtfertigen, als `chat-komplex` für Lehrkräfte kann es sich lohnen.

---

## Szenario E — Mischbetrieb

Der Regelfall für Schulen, die eine Modalität nicht beim Hauptanbieter bekommen — oder die
bewusst abstufen wollen. Die Aufgaben-Aliase machen das ohne jede Codeänderung möglich:
Jede Stufe zeigt auf einen eigenen Anbieter.

```yaml
model_list:
  - model_name: chat-schnell              # EU, günstig, für alle
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY

  - model_name: chat-komplex              # nur Lehrkräfte
    litellm_params:
      model: anthropic/claude-sonnet-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: embedding-standard        # EU, 1024 Dimensionen
    litellm_params:
      model: mistral/mistral-embed
      api_key: os.environ/MISTRAL_API_KEY
    model_info:
      mode: embedding

  - model_name: bild-standard             # dort, wo es Bilder gibt
    litellm_params:
      model: openai/black-forest-labs/FLUX.1-schnell
      api_base: os.environ/IONOS_API_BASE
      api_key: os.environ/IONOS_API_KEY
    model_info:
      mode: image_generation
      input_cost_per_image: 0.032
```

Drei Fragen, die dabei zu beantworten sind:

**Datenschutz.** Jeder zusätzliche Anbieter ist ein weiterer Auftragsverarbeiter — mit
eigenem AVV, eigenem Serverstandort und eigenem Eintrag im Verarbeitungsverzeichnis. Die
Pseudonymisierung gilt für alle gleichermaßen (es verlässt nie ein Klarname das Schulnetz),
aber die Zahl der Verträge wächst.

**Welche Stufe wohin.** Faustregel: Was **alle** nutzen (`chat-schnell`,
`embedding-standard`, `system-titel`), gehört zum günstigsten EU-Anbieter — dort entsteht
das Volumen. Was **nur Lehrkräfte** nutzen (`chat-komplex`), darf teurer und außereuropäisch
sein, weil die Menge klein und die Zielgruppe volljährig ist.

**Wer fällt aus, wenn einer ausfällt.** Ein Anbieterausfall trifft nur die Stufen, die auf
ihm liegen. Fällt `embedding-standard` aus, bleibt der Chat nutzbar, aber ohne
Bildungsplan-Bezug; fällt `chat-standard` aus, steht der Kern still. Der lokale
Ollama-Fallback ist die Antwort darauf — er gehört in jedes Szenario.

---

## Was gespeichert wird — und was zitierfähig ist

Zu jeder Antwort werden **zwei** Modellnamen abgelegt, und die Unterscheidung ist der Grund
für dieses Kapitel:

| Feld | Beispiel | Wofür |
|---|---|---|
| `model` | `chat-standard` | Der **Aliasname**. Sagt, welche Aufgabe gemeint war. Nützlich für Betrieb, Statistik und Fehlersuche. |
| `provider_model` | `openai/openai/gpt-oss-120b` | Das **Anbietermodell**, das tatsächlich geantwortet hat. Das ist die zitierfähige Angabe. |

Der Alias allein genügt für eine Quellenangabe nicht: `chat-standard` ist ein Hausname, den
außerhalb der Schule niemand kennt und der morgen auf ein anderes Modell zeigen kann.

**Aufgelöst wird beim Schreiben, nicht bei der Anzeige.** Hängt jemand `chat-standard`
später auf ein anderes Modell um, bleibt die Angabe an einer drei Monate alten Antwort
korrekt. Die Auflösung nutzt den Antwort-Header `x-litellm-model-id`, der das konkrete
Deployment benennt — genauer als der Alias, wenn dieser auf mehrere Deployments zeigt
(Lastverteilung, Fallback).

> **LiteLLM liefert das Anbietermodell nirgends von selbst mit** (gemessen 28.08.2026):
> `response.model` und `x-litellm-model-group` geben beide den Alias zurück,
> `x-litellm-model-id` ist ein Hash. Erst der Abgleich mit `/model/info` macht daraus einen
> Namen.

Gespeichert wird die Angabe an der Nachricht, am erzeugten Bild und — beim Übernehmen in
die Bibliothek — am Artefakt. Letzteres ist kein Luxus: Ein Artefakt überlebt die
Konversation bewusst, die Bildzeile stirbt mit ihr; ohne die Kopie wäre die Herkunft nach
spätestens 93 Tagen weg.

**Was nicht geht:** Für Inhalte von **vor** dem 29.08.2026 lässt sich die Angabe nicht
nachtragen. Welcher Alias damals auf welches Modell zeigte, ist nicht rekonstruierbar.
Deshalb gibt es dafür bewusst keinen Backfill — eine geratene Angabe wäre schlimmer als
eine Leerstelle.

Was Nutzer:innen davon sehen und wie sie es übernehmen:
[KI-Ergebnisse zitieren](../user/zitieren.md).

---

## Anbieterspezifische Fallen

Alle folgenden Punkte sind an der eigenen Installation gemessen (27./28.08.2026). Sie eint,
dass sie **still** scheitern.

| Falle | Betrifft | Symptom | Abhilfe |
|---|---|---|---|
| `reasoning_effort` ohne `allowed_openai_params` | IONOS (alle) | `UnsupportedParamsError`, Eintrag komplett unbenutzbar | `allowed_openai_params: ["reasoning_effort"]`. **Nicht** `drop_params: true` — das entfernt den Parameter still, das Reasoning bleibt an, und man merkt es an der Rechnung |
| Gültige `reasoning_effort`-Werte sind modellabhängig | IONOS | HTTP 400 („Harmony does not support…") | Qwen versteht `none`, gpt-oss nur `low`/`medium`/`high` — nachmessen |
| Fehlendes `encoding_format: float` | IONOS-Embedding | LiteLLM schickt base64, der Anbieter lehnt ab — Kontextspeicher tot | Parameter setzen |
| Preise in `model_info` bei **Bildern** | alle | Jedes Bild kostet 0,00 $, läuft am Budget vorbei | Nur `IMAGE_PRICES` + Callback `guardrails.bildpreise` wirkt |
| `guardrails:` unter `litellm_settings` | alle | Proxy startet nicht (`GuardrailItem() … must be a mapping`) | Block auf die oberste Ebene |
| Guardrail-Modulpfade | alle | Proxy startet nicht oder Guardrail greift nicht | Werden **relativ zum Arbeitsverzeichnis** des Proxys aufgelöst — Proxy aus `infra/` starten |
| Billiges Modell als Titelmodell | Mistral, IONOS | Titel zu lang, in der Historie abgeschnitten | Titeltreue messen, nicht raten (siehe Szenario B) |
| *Identity-linked* API-Schlüssel ohne Workspace-Header | Anthropic | **Jeder** Aufruf endet mit HTTP 400 | `extra_headers: {"anthropic-workspace-id": "wrkspc_…"}` oder einen nicht identitätsgebundenen Schlüssel verwenden |
| Eingebaute Preistabelle altert | Mistral, OpenAI, Anthropic | Kostenstatistik weicht von der Rechnung ab | Beim Aufsetzen und nach LiteLLM-Updates gegen die Preisliste prüfen (am 28.08.2026 stimmte sie) |
| Modellname als Preishinweis gelesen | Mistral | Fünffache Kosten | `mistral-medium` ist teurer als `mistral-large` — Preisliste schlägt Intuition |

---

## Prüfen

Vor dem Produktivbetrieb und nach jeder Änderung an der `model_list`:

```bash
cd backend && python scripts/check_litellm_config.py
```

Das Skript gleicht `.env` und Proxy ab und meldet genau die Dinge aus der Tabelle oben, die
ohne Live-Aufruf prüfbar sind: unbekannte Modellnamen, fehlende Preise, fehlendes
`supports_function_calling`, falsche `mode`-Angaben, Bildarten ohne Modell und Bildmodelle
ohne Preis.

Was es **nicht** prüfen kann, weil es einen echten Aufruf braucht:

```bash
python scripts/ionos_probe.py --chat <id> --embedding <id> --image <id>
```

Function-Calling, Vektorbreite und ob ein Bildmodell Base64 statt einer URL liefert. Für
Bildpreise zusätzlich `python scripts/bildpreis_probe.py <bildart-modell>` — es misst über
einen eigens angelegten Virtual Key, ob das Budget tatsächlich belastet wird.

> Beide Probe-Skripte tragen „ionos" im Namen, sind aber nicht anbieterspezifisch: Sie
> sprechen jeden OpenAI-kompatiblen Endpunkt an. Für einen anderen Anbieter genügt es,
> `IONOS_API_BASE` und `IONOS_API_KEY` in der Umgebung darauf zu zeigen.

---

## Weiter

- [Vor der Installation](vor-der-installation.md) — Modellauswahl mit Messwerten
- [Modelle & Assistenten](modelle-und-assistenten.md) — Bedeutung der Stufen, Freischaltung
- [Konfigurationsdateien](konfiguration.md) — alle `.env`-Variablen im Detail
- [Runbook Modellwechsel](../runbooks/modellwechsel.md) — Embedding-Modell im Betrieb wechseln
