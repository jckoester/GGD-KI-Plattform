# Bildgenerierung (Phase 16)

Bildgenerierung ist als **Chat-Funktion** umgesetzt (`generate_image`, Fähigkeit
`image_generation`) — **kein** eigener Bild-Modus und **kein** Bild-Modell im
Modell-Selektor. Der Chat-Tool-Loop, SSE, Kosten und der Virtual-Key-Pfad werden
unverändert mitgenutzt. Die Datenschutz-Invariante bleibt gewahrt: nur der
LiteLLM-Proxy spricht mit Providern, und es werden **nur Base64-Bilder** verarbeitet
(keine extern gehosteten Bild-URLs).

## Tool-Architektur

- **Registrierung:** `generate_image` wird wie die übrigen Chat-Tools über
  `register_tool()` in die `TOOL_REGISTRY` eingetragen (`app/chat/router.py`).
  `ChatTool.group = "image_generation"`.
- **Freischaltung:** `tools_for()` (`app/chat/tools.py`) nimmt das Tool nur auf, wenn
  `"image_generation"` in `assistant.tool_groups` steht. Kein Gruppen-/Lehrkraft-Bezug
  nötig; die Team-Bild-Freigabe greift zusätzlich am Proxy.
- **Kontextabhängiges Schema:** `ChatTool.definition` darf ein **Callable** sein
  (`(SchemaContext) -> dict`); `tools_for()` löst es auf und gibt fertige Dicts zurück, per
  `dataclasses.replace` — die prozessweit geteilte Registry bleibt unverändert. Der
  `SchemaContext` trägt Assistent **und** die Modell-Allowlist der Nutzer:in als *Daten*,
  damit der Schema-Bau synchron und netzfrei bleibt (die Allowlist lädt der Router vorab).
- **Handler `_exec_generate_image`:** moderiert den Prompt (siehe unten), löst die
  **Bildart** auf, ruft `LiteLLMClient.generate_image()` über den **User-Virtual-Key** aus
  `ToolContext.litellm_key` (nicht Master-Key → Spend/Budget beim User), persistiert die
  Bytes und gibt `{status, image_id, bildart, format, size, cost_usd, note}` zurück.
- **Tool-Loop (`generate()`):** Der `elif _tc_name == "generate_image"`-Zweig sammelt die
  `image_id` und die Kosten, **entfernt `cost_usd`/`image_id` aus der LLM-sichtbaren**
  Tool-Antwort (der LLM soll Interna/Kosten nicht sehen) und sendet ein SSE-Event
  `event: image {image_id, size}`. Die Bild-Kosten werden vor dem finalen `cost`-Event zur
  Gesamtsumme addiert (`cost_usd += _image_cost_total`).

## Bildarten (Mehrmodell)

Eine **Bildart** ist die Nutzersicht auf „welches Bildmodell mit welchen Formaten".
Konfiguration und Laden: `app/chat/image_models.py`, Datei `config/image_models.yaml`.
Fehlt sie, wird aus den `IMAGE_*`-Variablen genau eine Bildart `standard` synthetisiert —
Aufwärtspfad für Bestandsinstallationen, ohne Datenmigration.

Die Datei wird **fail-closed** beim Start geladen (`main.py`-Lifespan): Ein Tippfehler
bricht den Start, statt beim ersten Bildwunsch aufzufallen. `response_format: url` wird
dabei abgewiesen — der Client verarbeitet ausschließlich Base64, die Datenschutzgrenze
steht damit schon in der Konfigurationsprüfung.

**Auflösungskette** (`bildarten_fuer` → `_resolve_bildart` → `_resolve_image_format`):

1. Alle konfigurierten Bildarten
2. ∩ Auswahl des Assistenten (`Assistant.image_kinds`, JSONB, Alembic `0047`;
   **leer = alle**)
3. ∩ Modell-Allowlist des Teams (`app/litellm/team_models.py`, TTL-Cache 300 s)
4. Bildart-ID aus dem Werkzeugaufruf, sonst `standard_unter(...)`
5. Formatname → Pixelgröße **innerhalb** der Bildart

Schritt 3 liefert `None` bei nicht erreichbarem Proxy — das heißt **unbekannt**, nicht
„nichts erlaubt", und filtert deshalb nicht. Ebenso, wenn nach dem Filter nichts übrig
bliebe: Ein Werkzeug ohne wählbare Bildart wäre die schlechtere Auskunft als die Ablehnung
des Proxys, die `_bild_fehlertext()` in einen lesbaren Satz übersetzt (401/403 → nicht
freigeschaltet, 429 → Budget). Dafür trägt `ImageGenerationError` den HTTP-Status.

Der Handler filtert mit denselben Regeln wie das Schema (`ToolContext.assistant` und
`.erlaubte_modelle`) — was das Schema verbirgt, muss er auch ablehnen, sonst wäre die
Beschränkung Kosmetik.

**Formatnäherung** (§ `_resolve_image_format`): Exakter Treffer gewinnt. Kennt die Bildart
den Namen nicht, aber eine andere, wird auf das nächstliegende Seitenverhältnis
ausgewichen — verglichen wird der Abstand der **Logarithmen**, weil ein linearer Vergleich
Hochformate systematisch bevorzugte (sie drängen sich zwischen 0 und 1, Querformate
verteilen sich bis unendlich). Bei Gleichstand gewinnt das Standardformat. Ein nirgends
konfigurierter Name (oder eine rohe Pixelangabe aus der alten Schnittstelle) fällt stumm
auf das Standardformat: Ohne erkennbare Absicht gibt es nichts zu nähern.

## Client

`LiteLLMClient.generate_image()` (`app/litellm/client.py`):

- `POST /images/generations`, `Authorization: Bearer {user_virtual_key}`, eigenes,
  großzügigeres Timeout (`settings.image_generation_timeout`, kein Streaming).
- `response_format`: `"b64_json"` erzwingt Base64 bei URL-fähigen Modellen; für Modelle,
  die den Parameter ablehnen und ohnehin nur Base64 liefern (`gpt-image-1`), `None`
  übergeben (`IMAGE_DEFAULT_MODEL` konfiguriert den Default).
- **Parser-Grenze:** akzeptiert nur `data[0].b64_json` → `base64.b64decode`. Eine `url` in der
  Antwort → `RuntimeError` (Datenschutz: keine externen Bild-URLs).
- **Kosten:** aus dem `x-litellm-response-cost`-Header (kein zweiter Spend-Log-Roundtrip);
  fehlt er, ist `cost_usd = None` (Budget greift trotzdem, nur die Anzeige unterzählt).
- Ergebnis: `ImageGenerationResult(image_bytes, cost_usd)`.

`get_image_model_ids()` liest `GET /model/info` und liefert die IDs mit
`model_info.mode == "image_generation"` — Grundlage der Bild-Modell-Matrix.

## Persistenz & Lifecycle

- **Speicher:** Bytes auf Disk unter `settings.image_storage_dir`; Referenz in der Tabelle
  `generated_images` (Alembic `0035`, FK auf `conversations`/`messages` mit
  `ON DELETE CASCADE`, `message_id` nullable). Modul `app/chat/image_store.py`
  (`save_generated_image` / `read_image_bytes` / `get_image_record` / `list_message_images` /
  `link_images_to_message`).
- **Streaming-Timing:** Das Bild wird mitten im Stream mit `message_id = NULL` persistiert;
  in `_persist` wird die Assistant-`Message` geflusht (→ `message_id`) und
  `link_images_to_message` in derselben Transaktion nachgezogen.
- **Auslieferung:** `GET /images/{image_id}` liefert die Bytes mit korrektem MIME-Type,
  **Pseudonym-authentifiziert** — kein `data:`/Markdown-Pfad. Das Frontend rendert
  `<img src="/api/images/{id}">` in `MessageBubble` **außerhalb** von DOMPurify/Markdown
  (vertrauenswürdige eigene Quelle).
- **Löschung:** Dateien werden an den Konversations-Lifecycle gehängt —
  `collect_*_image_paths` (vor dem Row-Delete) + `unlink_paths` (nach Commit) in
  `delete_conversation` und beiden Aufräum-Crons. Backstop-Cron
  `scripts/cleanup_generated_images.py` (`cleanup_generated_images`): verwaiste Dateien mit
  1h-Grace + Dateien über `settings.image_max_retention_days`.
- Die konversationsübergreifende **Artefaktbibliothek** ist bewusst **Phase 17**; das
  Referenzmodell ist dafür nicht konversations-exklusiv verdrahtet.

## Moderations-Schichten

`app/chat/image_moderation.py`, `image_prompt_block_reason(prompt)`:

1. **Krisen-Scan** (`crisis.detector.scan`) — für Bilder **blockierend** (Abweichung von
   ADR-008 Teil 3: der Text-Chat blockiert nicht; das Hilfe-Banner kommt weiter aus dem
   Router-Scan der Nutzernachricht).
2. **Kuratierte Bild-Blockliste** `config/image_blocklist.yaml`. Fehlt die Datei →
   `FileNotFoundError` beim Start (fail-closed, wie `crisis_triggers.yaml`; Live-Config
   gitignored, aus `.example` provisioniert). `invalidate_image_blocklist_cache()` erlaubt
   Hot-Reload.
3. **LiteLLM `pre_call`-Content-Filter** (Proxy, optional, Defense-in-Depth) +
   **provider-seitige Moderation**.

Der Bild-Prompt wird **vom LLM** beim Tool-Call gebildet und umgeht das Frontend-PII-Gate →
die serverseitige Moderation im Handler ist die tragende Schicht.

## Freischaltung & Jugendschutz-Prüfpunkt

- **Bild-Modell-Matrix:** `app/api/admin/image_models.py` (`GET/POST
  /admin/image-models/matrix`), analog zur Chat-Matrix. Beide schreiben in **dieselbe**
  LiteLLM-Team-Allowlist und **mergen** die jeweils andere Modell-Klasse beim Speichern
  (Chat-Matrix bewahrt Bild-Freigaben und umgekehrt). Frontend: zweiter Abschnitt auf
  `/settings/models` über die wiederverwendbare Komponente `ModelMatrixTable.svelte`.
- **Werkzeug-Übersicht `/tools`** (dort heißt „Werkzeug" der *Assistent*, nicht die
  Funktion): rein Frontend (`lib/tools.js`, `MEDIA_TOOL_GROUPS`,
  `isToolAssistant()`) — filtert die bereits in `AssistantSummary` enthaltenen `tool_groups`.
- **Prüfpunkt:** `_initial_status()` (`app/api/assistants.py`) zwingt schulweite,
  schülersichtbare Bild-Assistenten in `pending_review` (Helferin
  `_is_student_visible_image_assistant`), überschreibt den allgemeinen
  Schulweit-Sharing-Schalter. Editor-Warnung + statischer Nutzer-Hinweis unter dem Bild.

## Konfiguration (`app/config.py`)

| Setting | Bedeutung |
|---|---|
| `image_models_path` (`IMAGE_MODELS_PATH`) | Bildarten-Datei; fehlt sie, greift die Synthese |
| `image_default_model` (`IMAGE_DEFAULT_MODEL`) | Nur noch Quelle der Synthese — von den Bildarten abgelöst |
| `image_default_size` | Standard-Bildgröße (abgerechnete Standardwerte erzwingen) |
| `image_generation_timeout` | Timeout des Bild-Aufrufs (Sekunden) |
| `image_blocklist_path` | Pfad zur Bild-Blockliste |
| `image_storage_dir` | Verzeichnis der gespeicherten Bilder |
| `image_max_retention_days` | Max. Aufbewahrung (Aufräum-Cron) |

LiteLLM-Config: Bild-Modelle mit `model_info.mode: image_generation` markieren
(`infra/litellm_config.example.yaml`), lokaler Bild-Fallback analog Ollama.
