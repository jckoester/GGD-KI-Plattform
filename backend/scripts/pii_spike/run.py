"""PII-NER-Engine-Spike-Harness (Phase 14, Schritt 1).

Misst pro Engine Recall (Name/Wohnort), Rauschen (Over-Warning) und CPU-Latenz auf dem
gelabelten Eval-Set. Engine-Adapter sind pluggable.

Aufruf:
    python run.py spacy de_core_news_md
    python run.py spacy de_core_news_lg
    python run.py hf <hf-model-id>
"""

import statistics
import sys
import time

from eval_set import CASES

# Labels → unsere Kategorien
_NAME_LABELS = {"PER", "PERSON", "PER_PERSON"}
_LOC_LABELS = {"LOC", "GPE", "LOCATION", "LOC_LOCATION"}


def _overlap(gold: str, pred: str) -> bool:
    g, p = gold.lower().strip(), pred.lower().strip()
    return g in p or p in g


# ── Engine-Adapter: geben [(label, text)] zurück ────────────────────────────

def make_spacy(model: str):
    import spacy
    nlp = spacy.load(model)

    def run(text):
        return [(ent.label_, ent.text) for ent in nlp(text).ents]
    return run, nlp


def make_hf(model: str):
    from transformers import pipeline
    ner = pipeline("ner", model=model, aggregation_strategy="simple")

    def run(text):
        out = ner(text)
        return [(e["entity_group"], e["word"]) for e in out]
    return run, ner


def score(engine_fn, label: str):
    total_gold = 0
    hits = 0
    noise = 0
    missed = []
    noise_examples = []
    latencies = []

    for case in CASES:
        t0 = time.perf_counter()
        ents = engine_fn(case["text"])
        latencies.append((time.perf_counter() - t0) * 1000)

        preds = []
        for lab, etext in ents:
            up = lab.upper()
            if up in _NAME_LABELS:
                preds.append(("name", etext))
            elif up in _LOC_LABELS:
                preds.append(("wohnort", etext))

        gold = case["gold"]
        total_gold += len(gold)
        matched = set()
        for gcat, gsub in gold:
            found = False
            for i, (pcat, ptext) in enumerate(preds):
                if i in matched:
                    continue
                if pcat == gcat and _overlap(gsub, ptext):
                    found = True
                    matched.add(i)
                    break
            if found:
                hits += 1
            else:
                missed.append((gcat, gsub, case["text"][:50]))

        for i, (pcat, ptext) in enumerate(preds):
            if i not in matched:
                noise += 1
                noise_examples.append((pcat, ptext, case["text"][:50]))

    recall = hits / total_gold if total_gold else 0.0
    print(f"\n=== {label} ===")
    print(f"Recall (Name+Wohnort): {hits}/{total_gold} = {recall:.0%}")
    print(f"Rauschen (Over-Warning-Predictions): {noise}")
    print(f"Latenz/Prompt: median {statistics.median(latencies):.1f} ms, "
          f"max {max(latencies):.1f} ms")
    if missed:
        print("Verpasst:")
        for cat, sub, ctx in missed:
            print(f"  - [{cat}] '{sub}'  ←  {ctx!r}")
    if noise_examples:
        print("Rauschen (Beispiele):")
        for cat, sub, ctx in noise_examples[:12]:
            print(f"  - [{cat}] '{sub}'  ←  {ctx!r}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    kind, model = sys.argv[1], sys.argv[2]
    t0 = time.perf_counter()
    if kind == "spacy":
        fn, _ = make_spacy(model)
    elif kind == "hf":
        fn, _ = make_hf(model)
    else:
        print("Unbekannte Engine:", kind)
        sys.exit(1)
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"Modell '{model}' geladen in {load_ms:.0f} ms")
    score(fn, f"{kind}:{model}")


if __name__ == "__main__":
    main()
