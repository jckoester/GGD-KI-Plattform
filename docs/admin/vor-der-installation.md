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
   Bildgenerierung ersatzlos aus. Das Modell antwortet freundlich, ruft aber nie ein
   Werkzeug auf. Zu erkennen nur daran, dass Antworten auffällig allgemein bleiben.
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

| Modell | $/M ein | $/M aus | Werkzeuge | Erfahrung |
|---|---|---|---|---|
| **gpt-oss-120b** | 0,17 | 0,71 | ✅ | **Empfehlung als Arbeitspferd.** Befolgte Anweisungen am zuverlässigsten (4/4 bei Titeln, 3/3 bei Werkzeugen). Denkt immer, Umfang über `reasoning_effort: low/medium/high` steuerbar — `none` lehnt es ab. |
| Mistral Small 24B | 0,11 | 0,33 | ✅ | Günstig, antwortet ohne Denkspur sofort, versteht Bildeingaben. Bei knappen Vorgaben unbeständig (4 bis 13 Wörter). Gute Wahl für die schnelle Stufe. |
| Qwen3-Coder-Next | 0,17 | 0,89 | ✅ | Für Programmieraufgaben. |
| Qwen3.5-9B | 0,11 | 0,17 | ✅ | Billigstes Chat-Modell. **Hält knappe Vorgaben nicht ein** (15–22 Wörter statt 6). Für Aufgaben mit Formatvorgabe ungeeignet. |
| Qwen3.8-27B | 0,45 | 2,70 | ✅ | Antwortet direkt. Die Ausgabe kostet das Vierfache von gpt-oss-120b — vor dem Einsatz rechnen. |
| Qwen3.5-397B-A17B | 0,67 | 4,00 | ✅ | Stärkstes Modell, teuerste Ausgabe, denkt ausgiebig. Nur für Lehrkräfte freischalten. |
| Llama 3.3 70B | 0,71 | 0,71 | ✅ | Nicht näher erprobt. |
| ~~Mistral Nemo~~ | 0,17 | 0,17 | ❌ | **Nicht verwenden, wo Werkzeuge gebraucht werden.** Der Werkzeugaufruf zerfiel im Test in mehrsprachigen Textbrei statt in ein `tool_calls`-Feld. |
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
liefert aber rund dreißigmal größere Dateien, was bei vielen Nutzer:innen auf den
Speicherplatz durchschlägt.

> ⚠️ **Bildkosten werden derzeit nicht erfasst.** LiteLLM 1.83.7 löst Bildpreise nur über
> seine eingebaute Preistabelle auf und zieht die Preisangabe des eigenen Eintrags nicht
> heran. Bildgenerierung läuft damit am EUR-Budget vorbei. Wer sie breit freigibt, sollte
> das wissen und die Nutzung anderweitig begrenzen (Freigabematrix je Jahrgang).

### Andere Anbieter

Hier steht nur, wofür es belastbare eigene Erfahrung gibt. **Für Anthropic liegen keine
eigenen Messungen vor**; LiteLLM bringt für die gängigen Modelle Preise mit, sodass die
Kostenerfassung ohne eigene Einträge funktioniert.

**OpenAI** (bis August 2026 im Entwicklungsbetrieb genutzt):

- `text-embedding-3-small` liefert 1536 Dimensionen und unterstützt als eines der wenigen
  Modelle den `dimensions`-Parameter zum Kürzen (`EMBEDDING_SEND_DIMENSIONS=true`).
  BGE-M3 lehnt diesen Parameter ab.
- Leere Eingaben nimmt OpenAI beim Embedding klaglos an, BGE-M3 quittiert sie mit einem
  Fehler. Wer von OpenAI wechselt, sieht deshalb plötzlich Fehler an Knoten, die vorher
  unauffällig waren.
- `gpt-image-1` rechnet **pro Bild-Token** ab, nicht pro Bild, und kennt Hoch-, Quer- und
  Quadratformat.
- Die Ratenbegrenzung hängt an der Kontostufe. Sie ist der Grund, warum
  `EMBEDDING_TOKENS_PER_SECOND` einstellbar ist: Der passende Wert steht im eigenen Konto,
  nicht im Code.

---

## Weiter

- [Modelle & Assistenten](modelle-und-assistenten.md) — Freischaltung je Jahrgang, Assistenten
- [Konfigurationsdateien](konfiguration.md) — `.env` und LiteLLM-Config im Detail
- [Runbook Modellwechsel](../runbooks/modellwechsel.md) — Wechsel im laufenden Betrieb
