# PII-NER-Engine — Entscheidung (Phase 14, Schritt 1)

**Datum:** 2026-06-22 · **Entscheidung:** spaCy `de_core_news_md` + Cue-Patterns + Themen-Schwelle.

## Vorgehen
Gelabeltes Eval-Set (`eval_set.py`, 29 dt. Schüler:innen-/Lehrkraft-Prompts, 24 Gold-PII
für Name/Wohnort inkl. kleingeschriebener/informeller Fälle + False-Positive-Fallen) gegen
drei Engines (`run.py`), gemessen Recall, Rauschen (Over-Warning) und CPU-Latenz.

## Ergebnis

| Engine | Deploy-Größe | Latenz (Median) | Recall (Name+Wohnort) | Kleingeschr. Namen | torch |
|---|---|---|---|---|---|
| **spaCy `de_core_news_md`** | **~45 MB** | **2,6 ms** | **88 %** (21/24) | verpasst | nein |
| spaCy `de_core_news_lg` | ~567 MB | 2,3 ms | 75 % (18/24) | schlechter | nein |
| `Davlan/bert-base-multilingual-cased-ner-hrl` | ~709 MB | 10 ms (warmup 1,3 s) | 71 % (17/24) | gleiche Schwäche | ja (~+1 GB) |

## Begründung
- spaCy **`md`** hat den **höchsten Recall** bei minimaler Größe/Latenz und ohne torch.
- spaCy `lg` ist trotz 12× Größe **schlechter** (NER-Komponente nicht besser).
- Der (cased) Transformer **löst das Kernproblem nicht**: dieselbe Schwäche bei
  kleingeschriebenen Namen (`tim`, `jonas`, `lena`, `sophie müller`), insgesamt geringerer
  Recall, dazu torch (~+1 GB) und höhere Latenz. Ursache: **Groß-/Kleinschreibung** ist
  das dominante NER-Signal — ein *cased* Modell (egal ob spaCy oder BERT) hängt daran.
- `flair/ner-german-large` (XLM-R, case-robuster) wurde **bewusst nicht** getestet: ~2,2 GB
  + flair wären für einen Schutz-Nudge unverhältnismäßig.

## Konsequenz für die Umsetzung (Schritt 2 ff.)
1. **NER:** spaCy `de_core_news_md` (`PER`→name, `LOC`→wohnort).
2. **Cue-Patterns (case-unabhängig):** Selbst-Identifikation (`„ich heiße …"`,
   `„ich bin der/die …"`, `„mein name ist …"`) fängt den riskantesten Fall (eigener Name),
   den die cased NER bei Kleinschreibung verpasst — ohne Transformer.
3. **Themen-Schwelle (engine-unabhängig):** bloße Prominenten-/Sach-/Geografie-Nennung
   (Paris, Goethe, Merkel, Schwarzwald) **nicht** warnen; Schwerpunkt Wohnort/Adresse +
   Selbst-Bezug. (Offene Entscheidung #3 aus dem Plan.)

## Restunsicherheit
Kleingeschriebene Namen **ohne** Cue (z. B. „kannst du lena fragen") bleiben eine Lücke —
risikoärmer (fremder Vorname, kein Selbst-PII), und der Schutz ist ohnehin ein Nudge.

## Reproduzieren
```
venv/bin/pip install spacy
venv/bin/pip install "https://github.com/explosion/spacy-models/releases/download/de_core_news_md-3.8.0/de_core_news_md-3.8.0-py3-none-any.whl"
cd backend/scripts/pii_spike && ../../venv/bin/python run.py spacy de_core_news_md
```
