# Chat & Streaming

## Request-Struktur

Der Frontend-Client sendet `POST /api/chat` mit JSON-Body. Der Endpunkt
gibt eine `StreamingResponse` mit `Content-Type: text/event-stream` zurück.

**Request (Frontend → Backend):**
```json
{
  "messages": [
    { "role": "user", "content": "Erkläre mir die Fotosynthese." }
  ],
  "conversation_id": "uuid-oder-null",
  "model_id": "chat-standard",   // Name aus der LiteLLM-Config, nicht die Anbieter-ID
  "assistant_id": 3,
  "is_test": false,              // Testchat aus dem Assistenten-Editor
  "subject_id": 6,               // nur bei neuer Konversation
  "group_id": 12,                // nur bei neuer Konversation; nur eigene Gruppen
  "stunde_node_id": "uuid"       // nur bei neuer Konversation: Stundenbezug (0.15)
}
```

`messages` enthält den **ganzen Verlauf**, wie ihn die Oberfläche zeigt — das Backend lädt
ihn nicht aus der Datenbank. Die letzte Nachricht ist die neue Frage; nur sie wird
gespeichert.

Multimodaler Inhalt (Dateianhänge) wird als Liste in `content` kodiert:
```json
"content": [
  { "type": "text", "text": "Was steht auf dieser Seite?" },
  { "type": "image_url", "image_url": { "url": "data:image/png;base64,..." } }
]
```

## Ablauf im Backend (`app/chat/router.py`)

```
POST /chat
  1. JWT prüfen, Drossel (`rate_limit("chat")`), Anhang-Limit je Nachricht
  2. Neue Konversation: Assistent laden und Sichtbarkeit prüfen, Gruppe und Stundenbezug
       prüfen, Konversation anlegen.
     Bestehende: laden (nur eigene); Assistenten- oder Modellwechsel auflösen.
  3. Krisen-Erkennung auf der neuen Nachricht (lokal, blockiert nicht; ADR-008 Teil 3)
  4. Kontext aus dem Kontextspeicher (`kontext_fuer_frage`)
  5. Systemnachrichten zusammensetzen: schulweiter Guardrail-Prompt, Hintergrund-
       dokumente des Assistenten, `compose_system_content` (Präambel, Stufe, Stundenbezug,
       Kontext, Assistenten-Prompt), Ausgabeformat, ggf. Hausversuchs- und Krisen-Anweisung
  6. Verlauf aus der Anfrage anhängen
  7. Werkzeuge ermitteln (`tools_for`) — nur, wenn das Modell Function-Calling kann
  8. Erste Anfrage an LiteLLM (stream=True, `user` = Pseudonym, Virtual Key der Person).
       Abgelehnt → HTTPException (Budget: 429 mit lesbarem Satz), stumm → 504.
  9. Neue Konversation committen, Titelgenerierung parallel starten
 10. Strom an den Browser weiterreichen — mit Werkzeugrunden (s. u.)
 11. Titel abwarten (max. 3 s) → `event: title`
 12. Konversation und Nachrichten speichern (`_persist`) → `event: kontext`, `event: message`
 13. Kostennachtrag im Hintergrund starten (`kosten_nachtrag`), dann ggf. `event: fehler`,
       zuletzt `[DONE]`
```

Drei Response-Header begleiten den Stream:

| Header | Inhalt |
|--------|--------|
| `X-Conversation-Id` | UUID der Konversation (neu oder bestehend) |
| `X-Model-Id` | Tatsächlich verwendetes Modell für diese Antwort |
| `X-Assistant-Id` | ID des aktiven Assistenten (leer wenn keiner) |

Das Frontend kann die URL aktualisieren, bevor der erste Token eintrifft, und den Modell-/Assistent-Wechsel im UI anzeigen.

## SSE-Eventformat

Alle Events folgen dem Standard-SSE-Format (`event: <typ>\ndata: <json>\n\n`). Die
Ereignisgrenze ist die Leerzeile: Ein Block ohne `event:`-Zeile ist ein Token.

| Event | Daten | Wann |
|-------|-------|------|
| `crisis` | fertige Hilfe-Kontakte aus `help_resources.yaml` | als Erstes, wenn die Krisen-Erkennung ein Banner verlangt |
| *(kein Event-Typ)* | OpenAI-Delta-JSON | Token vom Modell (durchgeleitet) |
| `tool_status` | `{"tool": "finde_stunde", "round": 1}` | vor jedem Werkzeugaufruf; die Oberfläche wertet es nicht aus |
| `image` | `{"image_id", "size", "bildart", "provider_model", "prompt"}` | ein Werkzeug hat ein Bild erzeugt |
| `bezug` | `{"group_id", "subject_id", "stunde_node_id"}` | ein Werkzeug hat Stunde oder Gruppe gesetzt (`waehle_stunde`) |
| `title` | `{"title": "Fotosynthese erklärt"}` | neuer Titel, sofern er binnen 3 s kam |
| `kontext` | `{"bausteine": [...]}` | nach dem Speichern: die Bausteine, die beim Antworten vorlagen |
| `message` | `{"message_id": "uuid"}` | nach dem Speichern — belegt später die Herkunft gespeicherter Diagramme |
| `fehler` | `{"detail": "Der KI-Dienst hat zu lange …"}` | Strom abgerissen oder Folgeanfrage abgelehnt (s. u.) |
| *(kein Event-Typ)* | `[DONE]` | Stream beendet; alles ist gespeichert |

Ein Ereignis `cost` sendet das Backend nicht mehr (seit 09/2026, s. „Kosten").

Der Frontend-Client (`frontend/src/lib/api.js`) verarbeitet die Events als
async generator und liefert vereinheitlichte Objekte:

```js
// Yield-Typen von streamChat():
{ type: 'start',   conversationId: '...', model: '...', assistantId: 3 }  // aus Response-Headern
{ type: 'crisis',  crisis: {...} }
{ type: 'image',   image_id, size, bildart, provider_model, prompt }
{ type: 'bezug',   groupId, subjectId, stundeId }
{ type: 'title',   title: '...' }
{ type: 'kontext', bausteine: [...] }
{ type: 'message', message_id: '...' }
// alle anderen Yields: direkt der Token-String
// `fehler` wirft ApiError(504, detail) — Text und Nachrichten-ID sind dann schon da
```

Das `start`-Event enthält neben `conversationId` auch `model` und `assistantId`.
`+page.svelte` nutzt diese Werte, um bei einem Modell- oder Assistent-Wechsel einen
`role: 'change'`-Trenner in das `messages`-Array einzufügen (gefiltert aus `apiMessages`,
sichtbar im UI als horizontale Linie mit Label).

## Werkzeugrunden, Rundenlimit, Abbruch

Ruft das Modell ein Werkzeug, führt der Router es aus und schickt das Ergebnis in einer neuen
Anfrage zurück — höchstens `_MAX_TOOL_ROUNDS` (6) Mal je Zug.

**Rundenlimit.** Die Anfrage nach dem letzten erlaubten Aufruf geht mit
`tool_choice: "none"` hinaus und endet mit einer eigenen `user`-Nachricht
(`_RUNDENLIMIT_HINWEIS`): antworten mit dem, was da ist, und sagen, was offen blieb.

- Der Hinweis ist nötig, weil gpt-oss-120b `tool_choice: "none"` übergeht — ebenso einen
  Hinweis im Werkzeugergebnis.
- `tools` bleibt in der Anfrage: Ohne sie lehnt LiteLLM für Anthropic jeden Verlauf mit
  Werkzeugaufrufen ab.
- Als `system`-Nachricht lehnt Qwen die Anfrage ab.
- Ruft das Modell trotzdem ein Werkzeug (gpt-oss: etwa einer von acht Fällen), wird nichts
  ausgeführt und dieselbe Anfrage **einmal** wiederholt.

Die Messwerte stehen im Kommentar am Hinweis.

**Text aus mehreren Runden.** Schreibt das Modell schon vor einem Werkzeugaufruf Text
(Anthropic tut das: „Ich suche deine Chemie-Stunde …"), beginnt der Text der nächsten Runde
als eigener Absatz (`_rundentrenner`). Der Trenner geht als gewöhnliches Token hinaus und
steht ebenso in der gespeicherten Nachricht.

**Erfundener Werkzeugname.** Nennt das Modell ein Werkzeug, das es nicht gibt (gemessen:
`find_stunde` statt `finde_stunde`), bekommt es als Ergebnis die verfügbaren Namen und kann
sich verbessern (`_unbekanntes_werkzeug`). Die Runde zählt gegen das Limit.

**Lese-Timeout.** `_LITELLM_TIMEOUT` begrenzt die Pause zwischen zwei Teilen des Stroms
(`read`, 60 s), nicht die Dauer der Antwort. Gemessen lag die längste Pause unter 1 s, auch
bei denkenden Modellen — das Denken kommt gestreamt.

**Abbruch.** Reißt der Strom (Timeout, Verbindungsabbruch) oder lehnt LiteLLM eine
Folgeanfrage ab (etwa Budget mitten im Zug erschöpft), endet der Zug mit dem, was bis dahin
da ist: Text, Werkzeugergebnisse und Kosten werden wie sonst gespeichert, die ID einer
abgerissenen Runde geht mit in den Kostennachtrag. Danach folgt `event: fehler` mit einem
lesbaren Satz — bei erschöpftem Budget mit demselben wie vor dem Strom. Den Fehlerkörper des
Proxys gibt es nur im Log. Fällt der Timeout schon vor dem ersten Byte, antwortet
`POST /chat` mit 504 und demselben Satz.

## Kosten

**Ein Chat-Zug besteht aus mehreren LLM-Anfragen:** je Werkzeugrunde eine, dazu die
Titelgenerierung. Alle laufen über den Virtual Key der Nutzer:in und belasten deren
Budget, also werden alle abgerechnet — der Router sammelt eine Request-ID je Anfrage,
`_kosten_des_zuges` summiert ihre SpendLogs.

**Der Stream wartet darauf nicht.** Die Nachricht wird mit `cost_status = 'ausstehend'`
gespeichert; `kosten_nachtrag.nachtragen` holt die Beträge im Hintergrund und schreibt sie
nach. Die Oberfläche fragt nach 3 und 10 Sekunden `GET /conversations/{id}/costs` ab.
Bildkosten stehen im Antwortkopf und gehen sofort mit in die Nachricht.

LiteLLM schreibt die SpendLogs asynchron. Gemessen am 30.08.2026, wann eine Buchung
abrufbar ist:

| Anfrageart | verfügbar nach |
|---|---|
| ohne Streaming, kurz | 3,0 s |
| mit Streaming, kurz | 12,6 s |
| mit Streaming, lange Antwort | 6,1 s |

Deshalb fragt der Nachtrag **gestaffelt** nach — nach 1, 2, 4 und 8 Sekunden
(`_SPEND_LOG_WARTEZEITEN`) — und hört auf, sobald alle Anfragen des Zuges abgerechnet sind.

⚠️ Die **letzte** Runde ist systematisch am gefährdetsten: Sie endet zuletzt, hat also am
wenigsten Zeit — und trägt als Eingabe den gesammelten Kontext, ist also die teuerste.
Fehlt eine Buchung, fehlt meist die größte.

Was gefunden wurde, steht im Log:

```
INFO Kosten nachgetragen für Nachricht …: 4 von 4 Anfragen, Summe 0.000951 (vollstaendig)
```

Bleibt es bei einer Teilsumme, ist `3 von 4` der Hinweis darauf, und `cost_status` wird
`unvollstaendig` — eine Summe allein verrät nicht, ob sie vollständig ist.

## Konversationstitel

Bei einer **neuen** Konversation, deren erste Nachricht länger als 20 Zeichen ist, startet
parallel zum Stream eine Titelgenerierung (`_generate_title`) mit dem Modell aus
`TITLE_MODEL`. Sie schreibt den Titel selbst in die Datenbank. Das Backend wartet nach dem
Antworttext höchstens 3 Sekunden darauf; kommt er rechtzeitig, geht er als `event: title`
hinaus, sonst erscheint er beim nächsten Laden der Seitenleiste.
