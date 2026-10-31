"""Schwellen der Zug-Auslöser bestimmen — offline, nur Embeddings (Rückfall Schritt 10, B3).

    cd backend && venv/bin/python scripts/druck_schwellen.py [--korpus ../config/druck_korpus.yaml] \\
        [--ziel "<Vault>/Plaene/Messungen-Ausloeser"]

Für jede Art (`druck`, `lehrkraft`) und eine Reihe von Schwellen: wie oft der Auslöser auf den
**Positiven** greift und wie oft auf den **Negativen** — mit Mustern und Korpus ODER-verknüpft, wie
im Chat (`app/pedagogy/druck.py`).

- **Nachsetzen, positiv:** die 25 Züge mit zweitem Nachsetzen aus Schritt 9 (:data:`NACHSETZ_ZUEGE`).
  Gezählt wird, ob die *Anweisung* gesetzt würde — der Zug trifft und einer der beiden davor auch.
- **Lehrkraft, positiv:** alle Züge der Fälle, in denen die Schüler:in behauptet, Lehrkraft zu sein
  (:data:`LEHRKRAFT_FAELLE`).
- **Negativ, beide:** die Texte des Vorschlags-Prüfsatzes (erste Nachrichten im freien Chat) und
  alle übrigen Schülerzüge der zwölf Szenarien; für Lehrkraft ausdrücklich die Fälle „die Lehrerin
  hat gesagt …“. Die Gegensätze im Korpus (`kein_*`) liegen bei Abstand 0 zu sich selbst und zählen
  deshalb nicht.

⚠️ **Der Korpus wird nicht an diesen Fällen nachgeschliffen** (Arbeitsanweisung Schritt 10, B3):
Die Sätze stammen von einem Agenten, der die Fälle nicht kannte; die Fälle sind die Kontrolle.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

SZENARIEN = ["rechnen_groessen", "mathe_aufgaben", "versuche", "lernen", "ueberarbeiten", "diagramme",
             "analysieren", "argumentieren", "grammatik", "recherche", "projekte", "programmieren"]
#: (Szenario, Fall-Präfix, Zug) — die zweiten Nachsetzer aus Schritt 9 (Befunde D1 groß/klein).
NACHSETZ_ZUEGE = [
    ("rechnen_groessen", "D1-", 2), ("rechnen_groessen", "NS1-", 3),
    ("mathe_aufgaben", "S1-", 2), ("mathe_aufgaben", "NS1-", 3),
    ("versuche", "S1-", 2), ("versuche", "NS1-", 3),
    ("lernen", "S1-", 2), ("lernen", "NS1-", 3),
    ("ueberarbeiten", "N1-", 2), ("ueberarbeiten", "NS1-", 3),
    *[(n, p, z) for n in ("diagramme", "analysieren", "argumentieren", "grammatik", "recherche",
                          "projekte", "programmieren") for p, z in (("D1-", 2), ("NS1-", 3))],
    ("argumentieren", "N1-", 2),
]
#: Fälle mit eigener Lehrkraft-Behauptung (alle Züge positiv).
LEHRKRAFT_FAELLE = [*[(n, "LK1-") for n in SZENARIEN],
                    ("analysieren", "L1-"), ("argumentieren", "L1-"), ("programmieren", "L1-")]
SCHWELLEN = [round(0.20 + 0.02 * i, 2) for i in range(16)]       # 0,20 … 0,50


def _fall(faelle: list[dict], praefix: str) -> dict:
    treffer = [f for f in faelle if f["id"].startswith(praefix)]
    if len(treffer) != 1:
        raise SystemExit(f"Fall {praefix!r} nicht eindeutig: {[f['id'] for f in treffer]}")
    return treffer[0]


async def main_async(args) -> None:
    from app.context.embedding import generate_embeddings
    from app.pedagogy import druck as D

    konfig = D.Druckausloeser.model_validate(
        yaml.safe_load((HIER.parent.parent / "config/druck_triggers.example.yaml").read_text(encoding="utf-8")))
    korpus = D.Korpus.model_validate(yaml.safe_load(args.korpus.read_text(encoding="utf-8")))
    szen = {n: yaml.safe_load((HIER / f"szenarien/{n}.yaml").read_text(encoding="utf-8"))["faelle"]
            for n in SZENARIEN}

    # Nachsetzen: je positivem Zug der Zug selbst und die beiden davor.
    pos_druck = []
    for n, p, z in NACHSETZ_ZUEGE:
        zuege = [x["schueler"] for x in _fall(szen[n], p)["zuege"]]
        pos_druck.append((f"{n} {p}Z{z}", zuege[z - 1], zuege[max(0, z - 1 - D.FENSTER):z - 1]))
    pos_lk = [(f"{n} {p}Z{i}", z["schueler"]) for n, p in LEHRKRAFT_FAELLE
              for i, z in enumerate(_fall(szen[n], p)["zuege"], 1)]
    positiv_ids = {(n, p) for n, p, _ in NACHSETZ_ZUEGE} | set(LEHRKRAFT_FAELLE)
    neg_szen = []
    for n, faelle in szen.items():
        for f in faelle:
            for i, z in enumerate(f["zuege"], 1):
                if any(n == pn and f["id"].startswith(pp) for pn, pp in positiv_ids):
                    continue
                neg_szen.append((f"{n} {f['id']} Z{i}", z["schueler"]))
    vorschlag = yaml.safe_load((HIER / "szenarien/assistent_vorschlag.yaml").read_text(encoding="utf-8"))["faelle"]
    neg_vorschlag = [(f"vorschlag {i}", f["text"]) for i, f in enumerate(vorschlag) if f.get("text")]
    lehrerin_sagt = [(k, t) for k, t in neg_szen if "lehrer" in t.lower()]

    texte = sorted({t for _, t, v in pos_druck for t in [t, *v]} | {t for _, t in pos_lk}
                   | {t for _, t in neg_szen} | {t for _, t in neg_vorschlag} | {s.text for s in korpus.saetze})
    vek = dict(zip(texte, (await generate_embeddings(texte)).vektoren))
    kv: dict[str, list[list[float]]] = {}
    for s in korpus.saetze:
        kv.setdefault(s.art, []).append(vek[s.text])

    def trifft(art, text, schwelle):
        a = konfig.nachsetzen if art == "druck" else konfig.lehrkraft
        return D.urteil(art, text, vek[text], a, kv, schwelle)

    t = ["# Zug-Auslöser: Schwellen offline (Schritt 10, B3)", "",
         f"- **Korpus:** {len(korpus.saetze)} Sätze "
         + ", ".join(f"{a} {sum(1 for s in korpus.saetze if s.art == a)}" for a in [*D.ARTEN, *D.ARTEN.values()]),
         f"- **Positive:** Nachsetzen {len(pos_druck)} Züge, Lehrkraft {len(pos_lk)} Züge",
         f"- **Negative:** übrige Szenario-Züge {len(neg_szen)}, Vorschlags-Prüfsatz {len(neg_vorschlag)}, "
         f"davon „Lehrer…“ erwähnt {len(lehrerin_sagt)}", ""]
    for art, pos in (("druck", pos_druck), ("lehrkraft", pos_lk)):
        t += [f"## {art}", "", "| Schwelle | Positive | Fehltreffer Szenarien | Fehltreffer Vorschlag | Fehltreffer gesamt |",
              "|---|---|---|---|---|"]
        for s in [None, *SCHWELLEN]:
            if art == "druck":
                ok = sum(trifft(art, x, s).treffer and any(trifft(art, v, s).treffer for v in vor) for _, x, vor in pos)
            else:
                ok = sum(trifft(art, x, s).treffer for _, x in pos)
            fs = sum(trifft(art, x, s).treffer for _, x in neg_szen)
            fv = sum(trifft(art, x, s).treffer for _, x in neg_vorschlag)
            n_neg = len(neg_szen) + len(neg_vorschlag)
            t.append(f"| {'nur Muster' if s is None else f'{s:.2f}'} | {ok}/{len(pos)} ({ok / len(pos):.0%}) "
                     f"| {fs}/{len(neg_szen)} | {fv}/{len(neg_vorschlag)} | {(fs + fv) / n_neg:.1%} |".replace(".", ","))
        t += ["", "Abstände der Positiven zum nächsten Satz der Art (Gegensatz in Klammern):", ""]
        for k, x, *_ in pos:
            e = trifft(art, x, None)
            t.append(f"- {k}: {e.abstand:.3f} ({e.gegen:.3f}){' · Muster' if e.quelle == 'regex' else ''} — {x[:70]}")
        nah = sorted(((trifft(art, x, None).abstand, k, x) for k, x in neg_szen + neg_vorschlag
                      if trifft(art, x, None).abstand < trifft(art, x, None).gegen))[:8]
        t += ["", "Nächste Negative (mit Gegenbeispiel-Regel erfüllt):", ""]
        t += [f"- {d:.3f} {k} — {x[:70]}" for d, k, x in nah]
        t.append("")
    text = "\n".join(t) + "\n"
    if args.ziel:
        args.ziel.mkdir(parents=True, exist_ok=True)
        (args.ziel / "schwellen.md").write_text(text, encoding="utf-8")
    print(text)


def main() -> None:
    p = argparse.ArgumentParser(description="Schwellen der Zug-Auslöser offline bestimmen")
    p.add_argument("--korpus", type=Path, default=HIER.parent.parent / "config/druck_korpus.example.yaml")
    p.add_argument("--ziel", type=Path)
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
