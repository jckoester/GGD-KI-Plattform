#!/usr/bin/env python3
"""Messung „Antworten an Lehrkräfte" (19.11.2026).

    python scripts/lehrkraft_antwort_messung.py --modelle chat-standard chat-komplex chat-schnell
    python scripts/lehrkraft_antwort_messung.py --basis http://localhost:8002 --etikett neu

Freier Chat als Lehrkraft, Sachfragen aus `scripts/szenarien/lehrkraft_antworten.yaml`, je Fall
und Modell mehrmals (Antworten streuen stark). Geprüft wird:

* **Schlussfrage** — endet die Antwort mit einer Frage (Quizfrage, „Möchtest du …?")?
* **ASCII** — steht eine Formel als Textgrafik da statt im ```smiles-Block?
* **smiles** — sind vorhandene Blöcke lesbar (Prüfung aus `strukturformel_messung.py`)?

Vorher/nachher misst man mit zwei Backend-Instanzen: eine mit dem Stand im Repo, eine mit
``PEDAGOGY_PATH`` auf der geänderten Fassung — so bleibt `config/pedagogy.yaml` unberührt,
bis die Messung entschieden hat.

⚠️ Nur für Entwicklungsinstanzen — eigene Sitzungs-Token, echte Modellaufrufe auf Kosten des
Budgets des verwendeten Lehrkraft-Kontos. Die Konversationen werden am Ende gelöscht.
"""
import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import httpx  # noqa: E402
import yaml  # noqa: E402

from app.auth.dependencies import get_jwt_service  # noqa: E402


def _lade(name: str):
    """`scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden."""
    spec = importlib.util.spec_from_file_location(name, HIER / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


chat_probe = _lade("chat_probe")
entfall = _lade("entfall_messung")
struktur = _lade("strukturformel_messung")

_CODE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.S)
_ATOM = re.compile(r"\b(?:C|H|O|N|OH|CH2|CH3|CH2OH|Br|Cl)\b")
_BINDUNG_IN_ZEILE = re.compile(r"[|/\\]")
_KETTE = re.compile(r"\b(?:C|O|N|H)\s*[-–—=]{1,2}\s*(?:C|O|N|H)\b")


def _grafikzeile(zeile: str) -> bool:
    """Sieht die Zeile aus wie ein Stück Textgrafik einer Formel?"""
    s = zeile.strip()
    if not s:
        return False
    # Markdown-Tabellen sind keine Grafik.
    if s.startswith("|") and s.endswith("|") and (re.search(r"[a-zäöü]{2}", s) or "---" in s):
        return False
    if re.fullmatch(r"[\s|/\\]+", s):
        return True  # reine Bindungszeile („|   |")
    if len(_KETTE.findall(s)) >= 2:
        return True  # „H - C - C = O", „HO—C—C—H"
    return bool(_ATOM.search(s) and _BINDUNG_IN_ZEILE.search(s) and "  " in s)


def ascii_formeln(antwort: str) -> list[str]:
    """Stellen, an denen eine Formel als Textgrafik steht (zum Nachlesen im Protokoll)."""
    funde = []
    for sprache, inhalt in _CODE.findall(antwort):
        if sprache.lower() in ("", "text", "plaintext", "ascii") and _ATOM.search(inhalt):
            if sum(_grafikzeile(z) for z in inhalt.splitlines()) >= 1:
                funde.append(inhalt.strip()[:300])
    ohne_code = _CODE.sub("", antwort)
    zeilen = ohne_code.splitlines()
    for i in range(len(zeilen) - 1):
        if _grafikzeile(zeilen[i]) and _grafikzeile(zeilen[i + 1]):
            funde.append("\n".join(zeilen[i:i + 3])[:300])
            break
    return funde


def schlussfrage(antwort: str) -> str | None:
    """Der letzte Absatz, wenn er eine Frage enthält — sonst ``None``."""
    text = _CODE.sub("", antwort).strip()
    absaetze = [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]
    if not absaetze:
        return None
    letzter = absaetze[-1]
    # Eine Trennlinie oder Quellenzeile zählt nicht als Absatz.
    if re.fullmatch(r"[-*_]{3,}", letzter) and len(absaetze) > 1:
        letzter = absaetze[-2]
    return letzter[:300] if "?" in letzter else None


def pruefe(antwort: str) -> dict:
    bloecke = [b.strip() for b in struktur._BLOCK.findall(antwort)]
    ergebnis = {
        "schlussfrage": schlussfrage(antwort),
        "ascii": ascii_formeln(antwort),
        "smiles_bloecke": len(bloecke),
        "smiles_lesbar": None,
    }
    if bloecke:
        p = struktur.pruefe(antwort, {"block": True})
        ergebnis["smiles_lesbar"] = p["lesbar"]
        ergebnis["lesefehler"] = p.get("lesefehler") or []
    return ergebnis


def _haken(wert, gut_wenn_leer=True) -> str:
    if wert is None:
        return "—"
    leer = not wert
    return "✓" if leer == gut_wenn_leer else "✗"


def protokoll(ergebnisse: list[dict], modelle: list[str], etikett: str) -> str:
    zeilen = [f"# Messung Antworten an Lehrkräfte — {etikett} — {datetime.now():%d.%m.%Y %H:%M}", ""]
    for modell in modelle:
        eigene = [e for e in ergebnisse if e["modell_soll"] == modell and not e.get("abbruch")]
        fragen = sum(bool(e["pruefung"]["schlussfrage"]) for e in eigene)
        ascii_ = sum(bool(e["pruefung"]["ascii"]) for e in eigene)
        smiles = sum(e["pruefung"]["smiles_bloecke"] > 0 for e in eigene)
        kaputt = sum(e["pruefung"]["smiles_lesbar"] is False for e in eigene)
        abbr = sum(1 for e in ergebnisse if e["modell_soll"] == modell and e.get("abbruch"))
        zeilen += [f"## {modell} — {len(eigene)} Antworten"
                   + (f", {abbr} abgebrochen" if abbr else ""), "",
                   f"Schlussfrage {fragen} · ASCII-Formel {ascii_} · mit smiles-Block {smiles}"
                   f" (davon unlesbar {kaputt})", "",
                   "| Fall | Lauf | Schlussfrage | ASCII | smiles | lesbar |", "|---|---|---|---|---|---|"]
        for e in eigene:
            p = e["pruefung"]
            zeilen.append(f"| {e['id']} | {e['lauf']} | {_haken(p['schlussfrage'])} | {_haken(p['ascii'])} | "
                          f"{p['smiles_bloecke']} | {_haken(p['smiles_lesbar'], gut_wenn_leer=False)} |")
        zeilen.append("")
        for e in eigene:
            p = e["pruefung"]
            zeilen += [f"### {e['id']} Lauf {e['lauf']} — {e['titel']} ({e['modell'] or modell})", ""]
            if p["schlussfrage"]:
                zeilen += [f"**Schlussfrage:** {p['schlussfrage']}", ""]
            for fund in p["ascii"]:
                zeilen += ["**ASCII:**", "", "```text", fund, "```", ""]
            zeilen += ["```text", e["antwort"].strip(), "```", ""]
    return "\n".join(zeilen)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelle", nargs="+", default=["chat-standard", "chat-komplex", "chat-schnell"])
    p.add_argument("--szenarien", default=str(HIER / "szenarien" / "lehrkraft_antworten.yaml"))
    p.add_argument("--faelle", nargs="*", help="nur diese Fall-IDs")
    p.add_argument("--wiederholungen", type=int, default=3)
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--etikett", default="vorher", help="Name der Fassung im Protokoll und Dateinamen")
    p.add_argument("--ziel", default="/tmp", help="Verzeichnis für Protokoll (md) und Rohdaten (json)")
    args = p.parse_args()

    faelle = yaml.safe_load(Path(args.szenarien).read_text(encoding="utf-8"))["faelle"]
    if args.faelle:
        faelle = [f for f in faelle if f["id"] in args.faelle]
    conn = entfall.verbindung()
    lehrkraft = struktur.konto(conn, "teacher")
    token = get_jwt_service().issue(pseudonym=lehrkraft, roles=["teacher"], grade=None)[0]

    ergebnisse, konversationen = [], []
    with httpx.Client(base_url=args.basis, timeout=300.0, headers={"Cookie": f"session={token}"}) as client:
        for modell in args.modelle:
            print(f"\n== {modell}", flush=True)
            for fall in faelle:
                for lauf in range(1, args.wiederholungen + 1):
                    eintrag = {"id": fall["id"], "titel": fall["titel"], "frage": fall["frage"], "lauf": lauf,
                               "modell_soll": modell, "modell": None, "antwort": ""}
                    try:
                        r = chat_probe.frage_stellen(client, fall["frage"], assistent=None, gruppe=None,
                                                     modell=modell)
                        eintrag.update(antwort=r["antwort"], modell=r["modell"])
                        if r.get("konversation"):
                            konversationen.append(r["konversation"])
                    except (httpx.HTTPError, SystemExit) as e:
                        eintrag["abbruch"] = f"{type(e).__name__}: {e}"
                    eintrag["pruefung"] = pruefe(eintrag["antwort"])
                    pr = eintrag["pruefung"]
                    print(f"  {fall['id']}/{lauf}: "
                          + (f"ABGEBROCHEN {eintrag['abbruch'][:80]}" if eintrag.get("abbruch") else
                             f"frage={'JA' if pr['schlussfrage'] else 'nein'} "
                             f"ascii={'JA' if pr['ascii'] else 'nein'} smiles={pr['smiles_bloecke']}"),
                          flush=True)
                    ergebnisse.append(eintrag)

    for kennung in konversationen:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (kennung,))

    ziel = Path(args.ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    name = f"lehrkraft_antworten_{args.etikett}_{datetime.now():%Y-%m-%d_%H%M}"
    (ziel / f"{name}.md").write_text(protokoll(ergebnisse, args.modelle, args.etikett), encoding="utf-8")
    (ziel / f"{name}.json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nProtokoll: {ziel / f'{name}.md'}")


if __name__ == "__main__":
    main()
