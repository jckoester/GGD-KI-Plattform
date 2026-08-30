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
  "assistant_id": 3
}
```

Multimodaler Inhalt (Dateianhänge) wird als Liste in `content` kodiert:
```json
"content": [
  { "type": "text", "text": "Was steht auf dieser Seite?" },
  { "type": "image_url", "image_url": { "url": "data:image/png;base64,..." } }
]
```

## Ablauf im Backend (`app/chat/router.py`)

```
POST /api/chat
  1. JWT prüfen → user: JwtPayload
  2. Falls assistant_id: Assistent laden, Sichtbarkeit prüfen (Rolle/Audience)
  3. Konversation anlegen (neu) oder laden (bestehende conversation_id);
       bei Wechsel von assistant_id / model_id mid-Chat: neue Werte auflösen
  4. Nachrichten-History aus DB laden
  5. System-Prompt des Assistenten vorne einfügen (falls vorhanden)
  6. Neue User-Message an History anhängen
  7. LiteLLM-Request aufbauen:
       model:    user.selectedModel
       messages: [system_prompt, ...history, neue_nachricht]
       user:     user.sub  ← Pseudonym, kein Klarname
       stream:   True
  8. httpx.AsyncClient streamt Antwort von LiteLLM
  9. Backend re-streamt via SSE an Browser
 10. Nach [DONE]:
       - Titel-Task abwarten (max. 3 s)
       - SpendLog aus LiteLLM holen (bis zu 3 Versuche mit Delay)
       - Kosten-Event senden
 11. Konversation + Nachrichten in DB persistieren (asyncio.Task)
```

Drei Response-Header begleiten den Stream:

| Header | Inhalt |
|--------|--------|
| `X-Conversation-Id` | UUID der Konversation (neu oder bestehend) |
| `X-Model-Id` | Tatsächlich verwendetes Modell für diese Antwort |
| `X-Assistant-Id` | ID des aktiven Assistenten (leer wenn keiner) |

Das Frontend kann die URL aktualisieren, bevor der erste Token eintrifft, und den Modell-/Assistent-Wechsel im UI anzeigen.

## SSE-Eventformat

Alle Events folgen dem Standard-SSE-Format (`event: <typ>\ndata: <json>\n\n`).

| Event | Daten | Bedeutung |
|-------|-------|-----------|
| *(kein Event-Typ)* | OpenAI-Delta-JSON | Token vom Modell (direkt durchgeleitet) |
| `title` | `{"title": "Fotosynthese erklärt"}` | Automatisch generierter Gesprächstitel |
| `cost` | `{"cost_usd": 0.000312}` | Kosten nach Stream-Ende |
| *(kein Event-Typ)* | `[DONE]` | Stream beendet |

Der Frontend-Client (`frontend/src/lib/api.js`) verarbeitet die Events als
async generator und liefert vereinheitlichte Objekte:

```js
// Yield-Typen von streamChat():
{ type: 'start', conversationId: '...', model: '...', assistantId: 3 }  // aus Response-Headern
{ type: 'title', title: '...' }
{ type: 'cost',  cost_usd: 0.000312 }
// alle anderen Yields: direkt der Token-String
```

Das `start`-Event enthält neben `conversationId` jetzt auch `model` und `assistantId`.
`+page.svelte` nutzt diese Werte, um bei einem Modell- oder Assistent-Wechsel einen
`role: 'change'`-Trenner in das `messages`-Array einzufügen (gefiltert aus `apiMessages`,
sichtbar im UI als horizontale Linie mit Label).

## SpendLog-Timing

**Ein Chat-Zug besteht aus mehreren LLM-Anfragen:** je Werkzeugrunde eine, dazu die
Titelgenerierung. Alle laufen über den Virtual Key der Nutzer:in und belasten deren
Budget, also werden alle abgerechnet — `_kosten_des_zuges` sammelt eine Request-ID je
Anfrage und summiert ihre SpendLogs.

LiteLLM schreibt diese Logs asynchron. Gemessen am 30.08.2026, wann eine Buchung abrufbar
ist:

| Anfrageart | verfügbar nach |
|---|---|
| ohne Streaming, kurz | 3,0 s |
| mit Streaming, kurz | 12,6 s |
| mit Streaming, lange Antwort | 6,1 s |

Der Chat streamt immer, und die Verzögerung schwankt stark. Deshalb wird **gestaffelt**
nachgefragt — nach 1, 2, 4 und 8 Sekunden — und abgebrochen, sobald alle Anfragen des
Zuges abgerechnet sind. Der Normalfall ist damit nach 1 s erledigt, ein Ausreißer nach
15 s noch erfasst. Ein festes Fenster müsste sich am schlechtesten Fall ausrichten und
wartete dann auch im guten.

⚠️ Die **letzte** Runde ist systematisch am gefährdetsten: Sie endet zuletzt, hat also am
wenigsten Zeit — und trägt als Eingabe den gesammelten Kontext, ist also die teuerste.
Fehlt eine Buchung, fehlt meist die größte.

Was gefunden wurde, steht im Log:

```
INFO Kosten des Zuges: 4 von 4 Anfragen abgerechnet, Summe 0.000951
```

Bleibt es bei einer Teilsumme, ist `3 von 4` der Hinweis darauf — eine Summe allein
verrät nicht, ob sie vollständig ist. Wird gar nichts gefunden, bleibt `cost_usd = null`.

Die Wartezeiten stehen in `_SPEND_LOG_WARTEZEITEN` (`app/chat/router.py`); die frühere
Einstellung `SPEND_LOG_DELAY` ist damit entfallen.

## Konversationstitel

Nach dem ersten Nachrichten-Austausch wird im Hintergrund ein Titel generiert:

```python
asyncio.create_task(_generate_title(conversation_id, first_user_message))
```

Das Titel-Modell (`TITLE_MODEL` in `.env`) bekommt nur die erste Nutzernachricht
und soll einen kurzen Titel zurückgeben. Das Backend wartet beim Senden des
`[DONE]`-Events maximal 3 Sekunden auf den Titel. Kommt er rechtzeitig,
wird er als `event: title` vor `[DONE]` gesendet.
