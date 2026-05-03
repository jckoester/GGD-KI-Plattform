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
  "model_id": "gpt-4o-mini",
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
  3. Konversation anlegen (neu) oder laden (bestehende conversation_id)
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

Der Response-Header `X-Conversation-Id` enthält die UUID der Konversation —
damit kann das Frontend die URL aktualisieren, bevor der erste Token eintrifft.

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
{ type: 'start',  conversationId: '...' }   // aus X-Conversation-Id-Header
{ type: 'token',  content: '...' }           // extrahiert aus Delta-JSON
{ type: 'title',  title: '...' }
{ type: 'cost',   cost_usd: 0.000312 }
```

## SpendLog-Timing

LiteLLM schreibt Kosten asynchron nach dem Stream. Das Backend wartet nach
dem `[DONE]`-Signal eine konfigurierbare Zeit (`SPEND_LOG_DELAY`, Default 1,0 s)
und fragt dann bis zu dreimal das SpendLog ab. Liefert LiteLLM in diesem
Zeitfenster keine Daten, wird `cost_usd = null` in der DB gespeichert.

Dieses Verhalten ist ein bekannter Kompromiss zwischen Latenz und Vollständigkeit
der Kostenerfassung.

## Konversationstitel

Nach dem ersten Nachrichten-Austausch wird im Hintergrund ein Titel generiert:

```python
asyncio.create_task(_generate_title(conversation_id, first_user_message))
```

Das Titel-Modell (`TITLE_MODEL` in `.env`) bekommt nur die erste Nutzernachricht
und soll einen kurzen Titel zurückgeben. Das Backend wartet beim Senden des
`[DONE]`-Events maximal 3 Sekunden auf den Titel. Kommt er rechtzeitig,
wird er als `event: title` vor `[DONE]` gesendet.
