# Vor der Installation

> **Notiz-Stand, wächst zum Kapitel.** Bisher gefüllt ist der Abschnitt *Modellwahl*.
> Vorgesehen sind außerdem: Datenschutz und Auftragsverarbeitung, Budgetbemessung,
> Rollen- und Gruppenzuschnitt, Betriebsmodell (wer betreut was), Elterninformation und
> Nutzungsordnung. Wer hier etwas ergänzt: Entscheidungen mit ihrer **Begründung**
> festhalten, nicht nur das Ergebnis — der Sinn dieses Kapitels ist, dass die Nachfolgerin
> in zwei Jahren versteht, warum etwas so eingestellt ist.

Dieses Kapitel sammelt die Überlegungen, die **vor** der technischen Installation
anstehen und die jede Schule für sich beantworten muss. Sie sind nicht technisch
schwierig, aber teuer zu korrigieren, wenn man sie überspringt.

---

## Modellwahl

Die Plattform schreibt kein Modell vor. Welches Modell wofür eingesetzt wird, entscheidet
die Schule — die Software ist so gebaut, dass ein Wechsel eine Zeile in der LiteLLM-Config
ist (siehe [Modelle & Assistenten](modelle-und-assistenten.md) und das
[Runbook Modellwechsel](../runbooks/modellwechsel.md)).

Die folgenden Angaben stammen aus eigenen Messungen am **27./28.08.2026**. Sie sind
Momentaufnahmen: Anbieter ändern Kataloge und Preise, und ein Modell, das heute eine
Anweisung befolgt, kann das nach einem Update anders tun. **Vor einer Entscheidung
nachmessen** — `python scripts/ionos_probe.py` fragt Katalog, Function-Calling,
Vektorbreite und Bildformat direkt beim Anbieter ab.

### Was ein Modell können muss

Drei Anforderungen sind nicht verhandelbar, und alle drei scheitern **still** — nichts
stürzt ab, es passiert nur nicht das Gewünschte:

1. **Function-Calling.** Ohne das fallen Wissensgraph, Unterrichtsplanung und
   Bildgenerierung ersatzlos aus. Das Modell antwortet freundlich, ruft aber nie eine
   Funktion auf. Zu erkennen nur daran, dass Antworten auffällig allgemein bleiben.
2. **Ein Preis in der LiteLLM-Config.** Fehlt er, meldet der SpendLog 0 — Budgets,
   429-Sperre und Kostenstatistik laufen ins Leere, ohne Fehlermeldung.
3. **Anweisungstreue bei kurzen Aufgaben.** Klingt nebensächlich, ist es nicht: Das
   Titelmodell bekommt „maximal 6 Wörter" vorgegeben. Ein Modell, das stattdessen einen
   Satz schreibt, produziert Gesprächstitel, die die Oberfläche mitten im Wort abschneidet
   — dauerhaft sichtbar in der Historie jeder Nutzerin.

### IONOS AI Model Hub

EU-Anbieter (Deutschland), OpenAI-kompatibel. Preise in **USD** eintragen — LiteLLM
rechnet in USD, die EUR-Budgets werden über den EZB-Kurs umgerechnet.

#### Chat

| Modell | $/M ein | $/M aus | Funktionen | Erfahrung |
|---|---|---|---|---|
| **gpt-oss-120b** | 0,17 | 0,71 | ✅ | **Empfehlung als Arbeitspferd.** Befolgte Anweisungen am zuverlässigsten (4/4 bei Titeln, 3/3 bei Funktionsaufrufen). Denkt immer, Umfang über `reasoning_effort: low/medium/high` steuerbar — `none` lehnt es ab. |
| Mistral Small 24B | 0,11 | 0,33 | ✅ | Günstig, antwortet ohne Denkspur sofort, versteht Bildeingaben. Bei knappen Vorgaben unbeständig (4 bis 13 Wörter). Gute Wahl für die schnelle Stufe. |
| Qwen3-Coder-Next | 0,17 | 0,89 | ✅ | Für Programmieraufgaben. |
| Qwen3.5-9B | 0,11 | 0,17 | ✅ | Billigstes Chat-Modell. **Hält knappe Vorgaben nicht ein** (15–22 Wörter statt 6). Für Aufgaben mit Formatvorgabe ungeeignet. |
| Qwen3.8-27B | 0,45 | 2,70 | ✅ | Antwortet direkt. Die Ausgabe kostet das Vierfache von gpt-oss-120b — vor dem Einsatz rechnen. |
| Qwen3.5-397B-A17B | 0,67 | 4,00 | ✅ | Stärkstes Modell, teuerste Ausgabe, denkt ausgiebig. Nur für Lehrkräfte freischalten. |
| Llama 3.3 70B | 0,71 | 0,71 | ✅ | Nicht näher erprobt. |
| ~~Mistral Nemo~~ | 0,17 | 0,17 | ❌ | **Nicht verwenden, wo Funktionen gebraucht werden.** Der Funktionsaufruf zerfiel im Test in mehrsprachigen Textbrei statt in ein `tool_calls`-Feld. |
| ~~Llama 3.1 8B / 405B~~ | — | — | ✅ | **Abgekündigt** (01.10. bzw. 15.09.2026) und in keiner Preisliste geführt. Ein Assistent darauf bricht binnen Wochen und läuft bis dahin mit Spend 0. |

> **Reasoning kostet Ausgabe-Tokens, und zwar erheblich.** Die Qwen3.5-Modelle denken auch
> bei Trivialem mehrere hundert Tokens lang; bei knappem `max_tokens` kommt gar keine
> Antwort, nur eine leere Nachricht. Abschaltbar ist das über `reasoning_effort` — die
> gültigen Werte sind aber **modellabhängig** (Qwen versteht `none`, gpt-oss nur
> `low`/`medium`/`high`). LiteLLM braucht dafür zusätzlich
> `allowed_openai_params: ["reasoning_effort"]`, sonst weist es die Anfrage ganz ab.

#### Embeddings

| Modell | Dimensionen | $/M | Erfahrung |
|---|---|---|---|
| **BAAI/bge-m3** | 1024 | 0,02 | **Empfehlung.** Mehrsprachig, für deutsche Fachtexte geeignet. Braucht `encoding_format: float` — sonst schickt LiteLLM base64 und IONOS antwortet mit einem Fehler. |
| paraphrase-multilingual-mpnet | 768 | 0,01 | Kleiner und billiger, nicht erprobt. |
| bge-large-en-v1.5 | 1024 | 0,015 | Englisch — für einen deutschen Bildungsplan die falsche Wahl. |
| Qwen3-VL-Embedding-8B | 4096 | 0,11 | **Nicht nutzbar:** 4096 Dimensionen überschreiten die Obergrenze des HNSW-Index (2000). |

> ⚠️ **Die Vektorbreite ist keine Einstellung, die man später ändert.** Sie muss zu
> `EMBEDDING_DIMENSIONS` *und* zur Datenbankspalte passen; ein Wechsel verlangt eine
> Schemaänderung und ein vollständiges Re-Embedding aller Knoten. Deshalb vor dem ersten
> Import entscheiden. Ablauf: [Runbook Modellwechsel](../runbooks/modellwechsel.md).

> **Zur Trefferqualität:** BGE-M3 liefert bei Naturwissenschaften gute Treffer, greift aber
> auch schon mal auf Wortformen statt Bedeutung zu („Flächeninhalt eines **Kreis**es"
> findet den Wasser**kreis**lauf). Wer die semantische Suche intensiv nutzt, sollte sie an
> eigenen Beispielen gegenprüfen und einen Reranker erwägen (IONOS führt
> `Qwen3-VL-Reranker-8B`, 0,045 $/M).

#### Bildgenerierung

| Modell | Preis | Formate | Dateigröße |
|---|---|---|---|
| **FLUX.1-schnell** | 0,032 $/Bild | **nur 1024×1024** | ~150 KB |
| FLUX.2-klein-4B | pro Megapixel (0,014 $ erstes, 0,001 $ weitere) | alle | ~3–4,7 MB |

FLUX.1-schnell hat den einfacheren Preis und schlanke Dateien, kann aber ausschließlich
quadratisch — hoch- und Querformat entfallen. FLUX.2-klein beherrscht alle Formate,
liefert aber rund **vierzigmal** größere Dateien (1024²: 3,0 MB gegen 73 KB, gemessen
28.08.2026), was bei vielen Nutzer:innen auf den Speicherplatz durchschlägt.

> ⚠️ **Bildpreise brauchen einen Extraschritt.** Für Chat und Embedding greift der Preis
> aus der LiteLLM-Config; für **Bilder nicht** — LiteLLM 1.83.7 löst sie ausschließlich über
> seine eingebaute Preistabelle auf. Ein selbst eingetragenes Bildmodell kostet dort 0,00 $
> und läuft am EUR-Budget vorbei, ohne dass etwas fehlschlägt. Abhilfe: `IMAGE_PRICES` in
> der `.env` setzen und den Callback `guardrails.bildpreise.registrierung` in der
> LiteLLM-Config eintragen — beides in den mitgelieferten Vorlagen vorbereitet. Danach
> rechnet LiteLLM wieder selbst, und Budget, 429-Sperre und Statistik stimmen zusammen.

### Mistral (eigene API)

EU-Anbieter (Frankreich). Der wichtigste Unterschied zu IONOS ist **keine Frage der
Modelle, sondern der Anbindung**: Mistral ist ein eigener LiteLLM-Provider. Der Eintrag
lautet `model: mistral/<id>` ohne `api_base` — und damit kommen **Preise, Kontextfenster,
Function-Calling und Vision aus LiteLLMs eingebauter Tabelle**. Bei IONOS (`openai/<id>`
plus eigener `api_base`) muss all das von Hand gepflegt werden; ein vergessener Preis
bedeutet dort Spend 0 und wirkungslose Budgets. Dieser Aufwand entfällt hier vollständig.

> **Die eingebauten Preise stimmten.** Am 28.08.2026 gegen
> [mistral.ai/pricing/api](https://mistral.ai/pricing/api/) abgeglichen: Alle sieben dort
> gelisteten Modelle deckten sich exakt mit LiteLLMs Tabelle. Trotzdem bleibt es eine
> Kostenquelle, die man nicht selbst kontrolliert — sie wird mit der Bibliothek
> ausgeliefert und kann bei einer Preisänderung des Anbieters altern. Beim Aufsetzen
> einmal gegenprüfen.
>
> ⚠️ **`mistral-medium` ist tatsächlich rund fünfmal teurer als `mistral-large`** (1,50/7,50
> gegen 0,50/1,50 $/M) — das sieht nach einem Fehler aus, ist aber der reguläre Tarif:
> Medium ist das neuere Premium-Modell, „large" hier kein Hinweis auf den Preis. Wer nach
> Namen statt nach Preisliste konfiguriert, greift hier fünffach daneben.

Gemessen am 28.08.2026 über den Proxy (Titeltreue: viermal der echte Titel-Prompt der
Anwendung, „maximal 6 Wörter"):

| Modell (`mistral/…`) | $/M ein | $/M aus | Funktionen | Titel | Erfahrung |
|---|---|---|---|---|---|
| `ministral-3b-latest` | 0,10 | 0,10 | ✅ | **2/4** (4–21 Wörter) | Billigstes Modell. **Hält knappe Vorgaben nicht ein** — als Titelmodell ungeeignet. |
| `ministral-8b-latest` | 0,15 | 0,15 | ✅ | **0/4** (7–33 Wörter) | Trotz höherem Preis **schlechter** als das 3B bei Formatvorgaben. Nicht für Aufgaben mit Formatzwang. |
| **`mistral-small-latest`** | 0,15 | 0,60 | ✅ | 4/4 (3–4) | **Empfehlung als Arbeitspferd.** Schnell (≈2,9 s), formattreu, Vision. |
| `mistral-medium-latest` | 1,50 | 7,50 | ✅ | 4/4 (3–4) | Schnell (≈1,8 s), aber **das teuerste Modell der Reihe** — fünfmal `mistral-large`. |
| `mistral-large-latest` | 0,50 | 1,50 | ✅ | 4/4 (4–6) | Deutlich **langsamer** (≈9,4 s) — für eine Chat-Antwort spürbar. |
| `magistral-small-latest` | 0,50* | 1,50* | ✅ | 4/4 (3–4) | Reasoning-Reihe, siehe unten. |
| `magistral-medium-latest` | 2,00* | 5,00* | ✅ | 4/4 (3–4) | dito, teurer. |

\* Von LiteLLM gemeldet, auf der öffentlichen Preisseite nicht gelistet — vor dem
Einsatz beim Anbieter erfragen.
| `codestral-latest` | 0,30 | 0,90 | ✅ | 4/4 (3–5) | Für Programmieraufgaben. |
| `mistral-embed` | 0,10 | — | — | — | **1024 Dimensionen** — dieselbe Breite wie BGE-M3. |

**Alle acht Chat-Modelle riefen das Testwerkzeug korrekt auf.** Function-Calling ist bei
Mistral also kein Auswahlkriterium — anders als bei IONOS, wo Mistral NeMo daran scheiterte.

> **Reasoning verhält sich hier genau umgekehrt zu IONOS.** Die Qwen-Modelle bei IONOS
> denken von sich aus und müssen über `reasoning_effort` gebremst werden, sonst kostet
> jede Trivialität hunderte Ausgabe-Tokens. Die Magistral-Reihe denkt **nicht von allein**:
> Auf „antworte knapp" kamen 5–12 Tokens und eine falsche Antwort, auf „denke Schritt für
> Schritt" 386–461 Tokens und eine richtige. Ein separates `reasoning`-Feld liefert sie
> nicht. Wer eine denkende Stufe (`chat-reasoning`) anbietet, muss das also im
> **System-Prompt des Assistenten** verankern — der Modellname allein bewirkt nichts.
>
> *(Eine Rechenaufgabe ist kein Maßstab für Qualität; belastbar ist hier das Verhalten,
> nicht die Trefferquote.)*

> ⚠️ **Mistral hat kein Text-zu-Bild-Modell** (Katalog vom 28.08.2026: 56 Modelle, keines
> mit Bildausgabe). Eine reine Mistral-Schule hat **keine Bildgenerierung** — wer sie will,
> braucht einen zweiten Anbieter. Das ist beim Zuschnitt der Assistenten vorher zu klären.

### OpenAI

Alle drei Modalitäten, in LiteLLM ohne Präfix ansprechbar, Preise eingebaut. Gemessen am
28.08.2026 mit demselben Titel-Prompt wie oben:

| Modell | $/M ein | $/M aus | Funktionen | Titel | Antwortzeit |
|---|---|---|---|---|---|
| **gpt-4o-mini** | 0,15 | 0,60 | ✅ | 4/4 (3–5) | 2,0 s |
| gpt-4.1-mini | 0,40 | 1,60 | ✅ | 4/4 (5) | 2,2 s |
| gpt-5-mini | 0,25 | 2,00 | ✅ | 4/4 (4–5) | 5,9 s |
| gpt-5 | 1,25 | 10,00 | ✅ | 4/4 (4–5) | 7,8 s |
| text-embedding-3-small | 0,02 | — | — | — | 1536 Dimensionen |

**`gpt-4o-mini` ist hier die auffällige Empfehlung:** das billigste, das schnellste **und**
formattreu. Für die schnelle Stufe und das Titelmodell gleichermaßen geeignet.

> **Die Regel „billige Modelle halten knappe Vorgaben nicht ein" gilt hier nicht.** Bei
> IONOS (Qwen3.5-9B) und Mistral (ministral-8b) scheitert genau das billigste Modell an der
> 6-Wörter-Grenze; bei OpenAI trafen **alle vier** Modelle sie. Die Anweisungstreue ist
> also keine Frage des Preises, sondern des Modells — deshalb ist sie zu messen und nicht
> zu schätzen.

> Die beiden gpt-5-Modelle sind spürbar **langsamer** (5,9 bzw. 7,8 s gegen 2,0 s). Für
> eine Chat-Antwort merkt man das; fürs Titelmodell, das im Hintergrund läuft, nicht.

Weitere Eigenheiten aus dem Betrieb bis August 2026:

- `text-embedding-3-small` unterstützt als eines der wenigen
  Modelle den `dimensions`-Parameter zum Kürzen (`EMBEDDING_SEND_DIMENSIONS=true`).
  BGE-M3 und `mistral-embed` lehnen ihn ab. Nur hier ist die Vektorbreite also frei
  wählbar — bei allen anderen Anbietern ist sie vorgegeben.
- Leere Eingaben nimmt OpenAI beim Embedding klaglos an, BGE-M3 quittiert sie mit einem
  Fehler. Wer von OpenAI wechselt, sieht deshalb plötzlich Fehler an Knoten, die vorher
  unauffällig waren.
- `gpt-image-1` rechnet **pro Bild-Token** ab, nicht pro Bild, und kennt Hoch-, Quer- und
  Quadratformat.
- Die Ratenbegrenzung hängt an der Kontostufe. Sie ist der Grund, warum
  `EMBEDDING_TOKENS_PER_SECOND` einstellbar ist: Der passende Wert steht im eigenen Konto,
  nicht im Code.

### Anthropic

Nur Chat — **weder Embedding- noch Bildmodell**. Ein reiner Anthropic-Betrieb ist damit
unmöglich: Ohne Embeddings gibt es keinen Kontextspeicher und keine semantische Suche.
Anthropic kommt nur im Mischbetrieb infrage; siehe [Modell-Szenarien](modell-szenarien.md).
LiteLLM bringt die Preise mit, eigene Einträge sind nicht nötig.

Gemessen am 28.08.2026:

| Modell | $/M ein | $/M aus | Funktionen | Titel | Antwortzeit |
|---|---|---|---|---|---|
| claude-haiku-4-5 | 1,00 | 5,00 | ✅ | **2/4** (4–168 Wörter) | 3,4 s |
| **claude-sonnet-5** | 2,00 | 10,00 | ✅ | 4/4 (4–5) | 2,9 s |
| claude-opus-5 | 5,00 | 25,00 | ✅ | 4/4 (4–6) | 3,2 s |

Alle drei beherrschen Funktionsaufrufe und Bildeingaben.

> ⚠️ **Anthropic ist mit Abstand der teuerste der vier geprüften Anbieter.** Schon das
> kleinste Modell (Haiku, 1,00/5,00 $/M) kostet mehr als `mistral-large` (0,50/1,50) und
> rund das Sechsfache von `gpt-4o-mini` (0,15/0,60). Für Stufen, die **alle** nutzen, ist
> das schwer zu rechtfertigen; als `chat-komplex` für Lehrkräfte kann es sich lohnen.

> **Haiku ist als Titelmodell ungeeignet — und zeigt dabei den lehrreichsten Fehler der
> ganzen Messreihe.** Auf „Erkläre mir bitte den Wasserkreislauf für eine Klassenarbeit"
> antwortete es mit einer **168 Wörter langen Erklärung samt Überschriften**, statt einen
> Titel zu bilden; auf „Erzeuge ein Bild: …" mit „Ich kann keine Bilder generieren". Bei
> den beiden neutral formulierten Fragen traf es dagegen 4 und 6 Wörter.
>
> Das Muster ist also nicht „Modell hält sich nicht an Vorgaben", sondern präziser: **Eine
> imperativ formulierte Nutzernachricht gewinnt gegen den System-Prompt.** Das Modell
> befolgt die Anweisung der Schülerin, statt sie zu betiteln. Dasselbe wurde bei IONOS mit
> gpt-oss-120b beobachtet — es ist kein Anbieterproblem, sondern eines der Prompt-Bauweise.
> Die Gegenmaßnahme (Nutzertext als Zitat statt als Anweisung übergeben) ist gemessen und
> in der Todo unter *Backend / Prompts* festgehalten.

> **Ein Hinweis zum Schlüsseltyp:** Ein *identity-linked* API-Schlüssel weist **jeden**
> Aufruf ab, solange der Header `anthropic-workspace-id` fehlt (HTTP 400, am 28.08.2026
> erlebt). Details und Konfiguration in
> [Modell-Szenarien](modell-szenarien.md#szenario-d--anthropic).

---

## Weiter

- [Modell-Szenarien](modell-szenarien.md) — fertige Konfigurationen je Anbieter und die
  Fallen, die dabei still scheitern
- [Modelle & Assistenten](modelle-und-assistenten.md) — Freischaltung je Jahrgang, Assistenten
- [Konfigurationsdateien](konfiguration.md) — `.env` und LiteLLM-Config im Detail
- [Runbook Modellwechsel](../runbooks/modellwechsel.md) — Wechsel im laufenden Betrieb
