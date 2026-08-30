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

### In welcher Währung die Preise eingetragen werden

**Das ist keine Formsache, sondern die Stelle, an der ein Budget dauerhaft danebenliegen
kann — ohne dass irgendetwas fehlschlägt.**

LiteLLM ist die Währung gleichgültig: `input_cost_per_token` ist eine Zahl, „USD" nur ein
Etikett. Entscheidend ist, dass **Preise und Budget dieselbe Einheit** haben. Dafür gibt es
die Variable `LITELLM_PRICE_CURRENCY`:

| Wert | Bedeutung | Wann |
|---|---|---|
| `EUR` | Die Preise in der Proxy-Config sind Euro. **Es wird nicht umgerechnet** (Faktor 1,0). | Anbieter rechnet in Euro ab — z. B. IONOS |
| `USD` *(Vorgabe)* | Die Preise sind Dollar. EUR-Budgets werden mit dem EZB-Kurs umgerechnet. | OpenAI, Anthropic, Mistral |

> ⚠️ **Euro-Preise in Dollar umzurechnen und einzutragen ist der Fehler, den man nicht
> sieht.** Dabei friert man den Tageskurs in der Config ein, während das Budget mit dem
> *aktuellen* EZB-Kurs umgerechnet wird. Beide kürzen sich nur, solange die Kurse gleich
> sind — wertet der Euro auf, überschreitet die Schule ihr Budget genau um diesen Faktor,
> Monat für Monat. Budgets greifen weiter, Statistiken sehen plausibel aus, die Rechnung
> ist trotzdem zu hoch.
>
> Mit `LITELLM_PRICE_CURRENCY=EUR` entfällt die Umrechnung ganz. Das Risiko ist dann nicht
> abgepuffert, sondern **nicht vorhanden**.

**Im Mischbetrieb ist eine Einheit zu wählen**, und die andere Seite muss umgerechnet
werden — das Kursrisiko bleibt dann für diesen Anteil bestehen und ist beim Kurswechsel
nachzuziehen. `python scripts/check_litellm_config.py` meldet Einträge, deren Preise nicht
zur eingestellten Währung passen können.

> **Woran der Check das erkennt:** Ein Deployment **ohne** eigene `api_base` spricht den
> Endpunkt des Anbieters an — dafür bringt LiteLLM eigene Preise mit, und seine eingebaute
> Tabelle ist durchgängig **USD** (bei Mistral nachgeprüft). Ein Eintrag **mit** `api_base`
> (IONOS, OVH, lokale Server) ist immer selbst bepreist; dort gilt, was in der Config steht.

### IONOS AI Model Hub

EU-Anbieter (Deutschland), OpenAI-kompatibel.

> **IONOS listet ausschließlich Euro-Preise**
> ([Preisübersicht](https://cloud.ionos.de/managed/ai-model-hub), geprüft 29.08.2026).
> Die Werte also **unverändert in Euro** eintragen und `LITELLM_PRICE_CURRENCY=EUR` setzen —
> nicht umrechnen.
>
> Alle Preise in diesem Abschnitt sind am **29.08.2026** gegen die Preisliste abgeglichen —
> Chat, Code, Embedding und Bild.


#### Chat

| Modell | €/M ein | €/M aus | Funktionen | Erfahrung |
|---|---|---|---|---|
| **gpt-oss-120b** | 0,15 | 0,65 | ✅ | **Empfehlung als Arbeitspferd.** Befolgte Anweisungen am zuverlässigsten (4/4 bei Titeln, 3/3 bei Funktionsaufrufen). Denkt immer, Umfang über `reasoning_effort: low/medium/high` steuerbar — `none` lehnt es ab. |
| Mistral Small 24B | 0,10 | 0,30 | ✅ | Günstig, antwortet ohne Denkspur sofort, versteht Bildeingaben. Bei knappen Vorgaben unbeständig (4 bis 13 Wörter, **alte Prompt-Fassung**). Gute Wahl für die schnelle Stufe. |
| Qwen3-Coder-Next | 0,15 | 0,80 | ✅ | Für Programmieraufgaben. |
| Qwen3.5-9B | 0,10 | 0,15 | ✅ | Billigstes Chat-Modell. Hielt knappe Vorgaben nicht ein (15–22 Wörter statt 6) — **gemessen mit der alten Prompt-Fassung**, mit der heutigen nicht nachgeprüft. Vor dem Einsatz als Titelmodell selbst messen. |
| Qwen3.8-27B | 0,40 | 2,70 | ✅ | Antwortet direkt. Die Ausgabe kostet das Vierfache von gpt-oss-120b — vor dem Einsatz rechnen. |
| Qwen3.5-397B-A17B | 0,60 | 3,60 | ✅ | Stärkstes Modell, teuerste Ausgabe, denkt ausgiebig. Nur für Lehrkräfte freischalten. |
| Llama 3.3 70B | 0,65 | 0,65 | ✅ | Nicht näher erprobt. |
| ~~Mistral Nemo~~ | 0,15 | 0,15 | ❌ | **Nicht verwenden, wo Funktionen gebraucht werden.** Der Funktionsaufruf zerfiel im Test in mehrsprachigen Textbrei statt in ein `tool_calls`-Feld. |
| ~~Llama 3.1 8B / 405B~~ | — | — | ✅ | **Abgekündigt** (01.10. bzw. 15.09.2026) und in keiner Preisliste geführt. Ein Assistent darauf bricht binnen Wochen und läuft bis dahin mit Spend 0. |

> **Reasoning kostet Ausgabe-Tokens, und zwar erheblich.** Die Qwen3.5-Modelle denken auch
> bei Trivialem mehrere hundert Tokens lang; bei knappem `max_tokens` kommt gar keine
> Antwort, nur eine leere Nachricht. Abschaltbar ist das über `reasoning_effort` — die
> gültigen Werte sind aber **modellabhängig** (Qwen versteht `none`, gpt-oss nur
> `low`/`medium`/`high`). LiteLLM braucht dafür zusätzlich
> `allowed_openai_params: ["reasoning_effort"]`, sonst weist es die Anfrage ganz ab.

> **Zur Spalte „Titel".** Vier imperativ formulierte Eingaben („Erkläre mir …", „Erzeuge
> ein Bild: …", „Fasse … zusammen", „Schreibe mir …") gegen den echten Titel-Prompt der
> Anwendung; gezählt wird, wie oft die Antwort im 6-Wörter-Limit blieb. Gemessen mit der
> **aktuellen** Prompt-Fassung, die den Nutzertext als Zitat übergibt — mit der früheren
> Fassung fielen dieselben Modelle teils deutlich schlechter aus (Details unten).

#### Embeddings

| Modell | Dimensionen | €/M | Erfahrung |
|---|---|---|---|
| **BAAI/bge-m3** | 1024 | 0,02 | **Empfehlung.** Mehrsprachig, für deutsche Fachtexte geeignet. Braucht `encoding_format: float` — sonst schickt LiteLLM base64 und IONOS antwortet mit einem Fehler. |
| paraphrase-multilingual-mpnet | 768 | 0,01 | Kleiner und billiger, nicht erprobt. |
| bge-large-en-v1.5 | 1024 | 0,015 | Englisch — für einen deutschen Bildungsplan die falsche Wahl. |
| Qwen3-VL-Embedding-8B | 4096 | 0,11 | Technisch nutzbar, aber teuer in doppelter Hinsicht: fünfeinhalbfacher Preis und **viermal so lange Suchzeiten** wie bei 1024 Dimensionen (siehe unten). Nicht erprobt. |

> ⚠️ **Die Vektorbreite ist keine Einstellung, die man später ändert.** Sie muss zu
> `EMBEDDING_DIMENSIONS` *und* zur Datenbankspalte passen; ein Wechsel verlangt eine
> Schemaänderung und ein vollständiges Re-Embedding aller Knoten. Deshalb vor dem ersten
> Import entscheiden. Ablauf: [Runbook Modellwechsel](../runbooks/modellwechsel.md).

> **Zur Trefferqualität:** BGE-M3 trennt Bedeutungen zuverlässiger, als es lange den
> Anschein hatte. Hier stand bis 08/2026 der Vorwurf, es verwechsle Wortformen mit
> Bedeutung („Flächeninhalt eines **Kreis**es" finde den Wasser**kreis**lauf). Das war
> falsch: Der Mathematik-Treffer war die ganze Zeit der ähnlichere (0,581 gegen 0,495) —
> nur lieferte ihn der damalige Vektorindex nicht aus. Er ist inzwischen entfernt.
>
> Wer die Suche intensiv nutzt, prüft sie trotzdem an eigenen Beispielen gegen:
> `python scripts/search_eval.py` mit eigenen Fällen in `config/search_eval.yaml`.

#### Wie viele Knoten trägt die Suche?

Die semantische Suche durchläuft **alle** Vektoren; einen Index gibt es bewusst nicht (er
lieferte nur rund die Hälfte der ähnlichsten Knoten — Begründung in Migration 0052).
Gemessen an 14.244 Knoten mit 1024 Dimensionen:

| | Zeit je Suche | Durchsatz (4-Kern-Server) |
|---|---|---|
| 14.000 Knoten | 35–55 ms | ~110/s |
| 50.000 Knoten (hochgerechnet) | ~120 ms | ~30/s |

Zum Vergleich: 100 gleichzeitig aktive Nutzer:innen erzeugen etwa 2–3 Suchen/s. Die Suche
trägt damit bis grob **150.000 Knoten**; ein vollständiger Bildungsplan liegt bei rund
14.000. Drei Dinge sind zu beachten:

- **Die Zeit wächst linear mit der Vektorbreite.** Ein Modell mit 4096 statt 1024
  Dimensionen sucht viermal so lange.
- **`shared_buffers` muss zum Bestand passen.** Bei 50.000 Knoten liegen rund 370 MB
  Vektordaten im Umlauf; die PostgreSQL-Vorgabe von 128 MB reicht dafür nicht.
- **PostgreSQL parallelisiert diese Abfrage nicht** — der Durchsatz entspricht der
  Kernzahl.

#### Bildgenerierung

| Modell | Preis | Formate | Dateigröße |
|---|---|---|---|
| **FLUX.1-schnell** | **0,0288 €/Bild**, unabhängig von der Größe | **nur 1024×1024** | ~150 KB |
| FLUX.2-klein-4B | **Megapixel-Staffel:** 0,013 € erstes MP, 0,001 € je weiterem | alle | ~3–4,7 MB |

> **Was die Staffel praktisch bedeutet.** Die drei angebotenen Formate (1024², 768×1344,
> 1344×768) liegen alle bei rund 1,03–1,05 MP und kosten damit **0,0130 €** — kaum mehr als
> FLUX.1. Der Unterschied wächst erst mit der Größe: bei 1536² (2,36 MP) sind es 0,0144 €.
> In `IMAGE_PRICES` steht deshalb ein Pauschalwert (0,0131 € — 0,4 % über dem tatsächlichen
> Preis, also auf der sicheren Seite). **Wer größere Formate freigibt, muss ihn nachrechnen**;
> `IMAGE_PRICES` kann auch je Größe geführt werden.
>
> Eingabebilder kosten zusätzlich 0,001 €/MP. Für die Plattform ohne Belang: Das Werkzeug
> `generate_image` erzeugt Bilder aus Text, nicht aus Bildern.

FLUX.1-schnell hat den einfacheren Preis und schlanke Dateien, kann aber ausschließlich
quadratisch — hoch- und Querformat entfallen. FLUX.2-klein beherrscht alle Formate,
liefert aber rund **vierzigmal** größere Dateien (1024²: 3,0 MB gegen 73 KB, gemessen
28.08.2026), was bei vielen Nutzer:innen auf den Speicherplatz durchschlägt.

> ⚠️ **Bildpreise brauchen einen Extraschritt.** Für Chat und Embedding greift der Preis
> aus der LiteLLM-Config; für **Bilder nicht** — LiteLLM 1.83.7 löst sie ausschließlich über
> seine eingebaute Preistabelle auf. Ein selbst eingetragenes Bildmodell kostet dort 0,00 $
> und läuft am Budget vorbei, ohne dass etwas fehlschlägt. Abhilfe: `IMAGE_PRICES` in
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
| `ministral-3b-latest` | 0,10 | 0,10 | ✅ | **3/4** (3–7) | Billigstes Modell, reißt die Grenze knapp. Als Titelmodell grenzwertig. |
| `ministral-8b-latest` | 0,15 | 0,15 | ✅ | **2/4** (5–35) | Trotz höherem Preis **schlechter** als das 3B. Für Aufgaben mit Formatzwang ungeeignet — auch mit der verbesserten Prompt-Fassung. |
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
> Mistral (`ministral-8b`) reißt das günstige Modell die 6-Wörter-Grenze auch mit der
> verbesserten Prompt-Fassung; bei OpenAI trafen **alle vier** Modelle sie. Die
> Anweisungstreue ist also keine Frage des Preises, sondern des Modells — deshalb ist sie
> zu messen und nicht zu schätzen.

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
| claude-haiku-4-5 | 1,00 | 5,00 | ✅ | 4/4 (4–5) | 3,4 s |
| **claude-sonnet-5** | 2,00 | 10,00 | ✅ | 4/4 (4–5) | 2,9 s |
| claude-opus-5 | 5,00 | 25,00 | ✅ | 4/4 (4–6) | 3,2 s |

Alle drei beherrschen Funktionsaufrufe und Bildeingaben.

> ⚠️ **Anthropic ist mit Abstand der teuerste der vier geprüften Anbieter.** Schon das
> kleinste Modell (Haiku, 1,00/5,00 $/M) kostet mehr als `mistral-large` (0,50/1,50) und
> rund das Sechsfache von `gpt-4o-mini` (0,15/0,60). Für Stufen, die **alle** nutzen, ist
> das schwer zu rechtfertigen; als `chat-komplex` für Lehrkräfte kann es sich lohnen.

> **Haiku war der lehrreichste Fund der ganzen Messreihe — und ist inzwischen behoben.**
> Mit der **früheren** Prompt-Fassung antwortete es auf „Erkläre mir bitte den
> Wasserkreislauf für eine Klassenarbeit" mit einer **168 Wörter langen Erklärung samt
> Überschriften** statt eines Titels; auf „Erzeuge ein Bild: …" mit „Ich kann keine Bilder
> generieren". Bei neutral formulierten Fragen traf es dagegen 4 und 6 Wörter.
>
> Das Muster war nicht „Modell hält sich nicht an Vorgaben", sondern präziser: **Eine
> imperativ formulierte Nutzernachricht gewinnt gegen den System-Prompt.** Das Modell
> befolgte die Anweisung der Schülerin, statt sie zu betiteln — dasselbe zuvor bei IONOS
> mit gpt-oss-120b. Kein Anbieterproblem, sondern eines der Prompt-Bauweise.
>
> Seit dem 28.08.2026 übergibt die Anwendung den Nutzertext als **Zitat** statt als
> Anweisung. Haiku liegt damit bei 4/4 (Wortzahlen von `[153, 58, 5, 228]` auf
> `[4, 5, 4, 5]`).

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
