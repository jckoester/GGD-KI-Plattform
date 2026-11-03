#!/usr/bin/env python3
"""Messung „Strukturformeln im Chat" (0.30, Päckchen AH, Plan Schritt 5).

    python scripts/strukturformel_messung.py --modelle chat-standard chat-komplex
    python scripts/strukturformel_messung.py --modelle chat-standard --ziel "<Vault>/Plaene/Messungen-Strukturformeln"

Gemessen wird der Prompt-Satz zu Strukturformeln in `config/pedagogy.yaml`: Benutzt das Modell
den ```smiles-Block, ist er lesbar, stimmen die Moleküle (kanonisches SMILES gegen die
Erwartung), die Darstellung und die Pfeile — und steht nirgends mehr TikZ oder Mermaid für eine
Strukturformel? Die Fälle stehen in `scripts/szenarien/strukturformeln.yaml`.

Je Modell und Fall eine neue Konversation im freien Chat, als Lehrkraft oder als Schüler:in mit
der Stufe des Falls. Die Konversationen werden am Ende gelöscht; die Antworten stehen im
Protokoll (Markdown zum Lesen, JSON zum Vergleichen).

⚠️ Nur für Entwicklungsinstanzen — eigene Sitzungs-Token, echte Modellaufrufe auf Kosten der
Budgets der verwendeten Konten.
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
from rdkit import Chem, RDLogger  # noqa: E402

from app.auth.dependencies import get_jwt_service  # noqa: E402
from app.render.smiles import Molekuel, SmilesError, lies, setze, zeichne  # noqa: E402

RDLogger.DisableLog("rdApp.*")


def _lade(name: str):
    """`scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden."""
    spec = importlib.util.spec_from_file_location(name, HIER / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


chat_probe = _lade("chat_probe")
entfall = _lade("entfall_messung")

_BLOCK = re.compile(r"```smiles[ \t]*\n(.*?)```", re.S)
_TIKZ = re.compile(r"\\begin\{tikzpicture\}|```(?:tikz|circuitikz)\b", re.I)
_MERMAID = re.compile(r"```mermaid\b", re.I)


def kanonisch(smiles: str) -> str | None:
    """Kanonisches SMILES zum Vergleichen — mit Aromatizität, damit Kekulé und klein gleich sind."""
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol is not None else None


def pruefe(antwort: str, fall: dict) -> dict:
    """Die automatischen Prüfungen eines Falls an einer Antwort."""
    bloecke = [b.strip() for b in _BLOCK.findall(antwort)]
    ergebnis = {
        "bloecke": bloecke,
        "tikz": bool(_TIKZ.search(antwort)),
        "mermaid": bool(_MERMAID.search(antwort)),
    }
    soll_block = fall.get("block", True)
    ergebnis["block_ok"] = bool(bloecke) == soll_block
    if not bloecke:
        ergebnis.update(lesbar=None, molekuele_ok=None, operator_ok=None, darstellung_ok=None)
        ergebnis["bestanden"] = ergebnis["block_ok"] and not ergebnis["tikz"] and not ergebnis["mermaid"]
        return ergebnis

    molekuele, operatoren, darstellungen, fehler = [], set(), set(), []
    for quelle in bloecke:
        try:
            block = lies(quelle)
            setze(block)
        except SmilesError as e:
            fehler.append(str(e))
            continue
        # Je Molekül zeichnen: Der Block zeigt ein unmögliches Molekül seit dem 03.11.2026
        # als Platzhalter — für die Messung bleibt es ein Fehler.
        for reihe in block.reihen:
            for teil in reihe.teile:
                if isinstance(teil, Molekuel):
                    try:
                        zeichne(teil, block.darstellung)
                    except SmilesError as e:
                        fehler.append(str(e))
        darstellungen.add(block.darstellung)
        for reihe in block.reihen:
            for teil in reihe.teile:
                if isinstance(teil, Molekuel):
                    molekuele.append(teil.smiles)
                else:
                    operatoren.add(teil)
    ergebnis["lesbar"] = not fehler
    ergebnis["lesefehler"] = fehler
    ergebnis["darstellung"] = sorted(darstellungen)

    erwartet = {kanonisch(s) for s in fall.get("erwartet") or []}
    gefunden = [kanonisch(s) for s in molekuele]
    ergebnis["molekuele"] = molekuele
    unerwartet = [s for s, k in zip(molekuele, gefunden) if k not in erwartet]
    ergebnis["unerwartet"] = unerwartet
    ok = bool(gefunden) and not unerwartet
    if fall.get("alle"):
        ok = ok and erwartet <= set(gefunden)
    if fall.get("mindestens"):
        ok = ok and len(gefunden) >= fall["mindestens"]
    ergebnis["molekuele_ok"] = ok if erwartet else None

    soll_op = fall.get("operator")
    ergebnis["operator_ok"] = bool(set(soll_op) & operatoren) if soll_op else None
    soll_d = fall.get("darstellung")
    ergebnis["darstellung_ok"] = (darstellungen == {soll_d}) if soll_d else None

    teile = [ergebnis["block_ok"], ergebnis["lesbar"], not ergebnis["tikz"], not ergebnis["mermaid"]]
    teile += [v for v in (ergebnis["molekuele_ok"], ergebnis["operator_ok"], ergebnis["darstellung_ok"])
              if v is not None]
    ergebnis["bestanden"] = all(teile)
    return ergebnis


def konto(conn, rolle: str) -> str:
    """Das Konto dieser Rolle mit Proxy-Schlüssel und dem **größten Rest** im Budget.

    ⚠️ Der erste Lauf (03.11.2026) nahm das zuletzt angemeldete Schüler:innen-Konto — dessen
    Budget war aufgebraucht, alle Schülerfälle endeten mit HTTP 429 und sahen im Protokoll aus
    wie „kein Block“. Aufgebucht wird hier nichts.
    """
    import asyncio

    from app.litellm.client import LiteLLMClient

    zeilen = entfall._alle(
        conn, "SELECT pseudonym FROM pseudonym_audit WHERE roles::text LIKE %s "
              "AND litellm_key IS NOT NULL", f"%{rolle}%")
    if not zeilen:
        raise SystemExit(f"Kein Konto mit Rolle {rolle} und LiteLLM-Schlüssel gefunden.")

    async def rest(pseudonym: str) -> float:
        client = LiteLLMClient()
        try:
            info = await client.get_user(pseudonym) or {}
        finally:
            await client.close()
        return (info.get("max_budget") or 0.0) - (info.get("spend") or 0.0)

    reste = {p: asyncio.run(rest(p)) for (p,) in zeilen}
    bestes = max(reste, key=reste.get)
    print(f"Konto {rolle}: {bestes[:12]}… (Rest {reste[bestes]:.4f} USD)")
    return bestes


def _haken(wert) -> str:
    return "—" if wert is None else ("✓" if wert else "✗")


def protokoll(ergebnisse: list[dict], modelle: list[str]) -> str:
    zeilen = [f"# Messung Strukturformeln — {datetime.now():%d.%m.%Y %H:%M}", "",
              "Prompt-Satz: `config/pedagogy.yaml`, Abschnitt Grafiken (0.30).", ""]
    for modell in modelle:
        eigene = [e for e in ergebnisse if e["modell_soll"] == modell]
        gemessen = [e for e in eigene if not e.get("abbruch")]
        bestanden = sum(e["pruefung"]["bestanden"] for e in gemessen)
        abgebrochen = len(eigene) - len(gemessen)
        zeilen += [f"## {modell} — {bestanden} von {len(gemessen)} bestanden"
                   + (f", {abgebrochen} abgebrochen (nicht gewertet)" if abgebrochen else ""), "",
                   "| Fall | Block | lesbar | Moleküle | Pfeil | Darstellung | TikZ | Mermaid | Abbruch |",
                   "|---|---|---|---|---|---|---|---|---|"]
        for e in eigene:
            p = e["pruefung"]
            zeilen.append(
                f"| {e['id']} {e['titel']} | {_haken(p['block_ok'])} | {_haken(p['lesbar'])} | "
                f"{_haken(p['molekuele_ok'])} | {_haken(p['operator_ok'])} | {_haken(p['darstellung_ok'])} | "
                f"{'✗' if p['tikz'] else '✓'} | {'✗' if p['mermaid'] else '✓'} | "
                f"{(e.get('abbruch') or '')[:60]} |")
        zeilen.append("")
        for e in eigene:
            p = e["pruefung"]
            zeilen += [f"### {e['id']} — {e['titel']} ({e['modell'] or modell})", "",
                       f"**Frage:** {e['frage']}", ""]
            if p.get("unerwartet"):
                zeilen.append(f"**Nicht erwartet:** `{'`, `'.join(p['unerwartet'])}`  ")
            if p.get("lesefehler"):
                zeilen.append(f"**Nicht lesbar:** {'; '.join(p['lesefehler'])}  ")
            zeilen += ["", "```text", e["antwort"].strip() or e.get("abbruch", ""), "```", ""]
    return "\n".join(zeilen)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelle", nargs="+", default=["chat-standard", "chat-komplex"])
    p.add_argument("--szenarien", default=str(HIER / "szenarien" / "strukturformeln.yaml"))
    p.add_argument("--faelle", nargs="*", help="nur diese Fall-IDs")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--ziel", default="/tmp", help="Verzeichnis für Protokoll (md) und Rohdaten (json)")
    args = p.parse_args()

    faelle = yaml.safe_load(Path(args.szenarien).read_text(encoding="utf-8"))["faelle"]
    if args.faelle:
        faelle = [f for f in faelle if f["id"] in args.faelle]
    conn = entfall.verbindung()
    lehrkraft, schueler = konto(conn, "teacher"), konto(conn, "student")
    jwt = get_jwt_service()

    ergebnisse, konversationen = [], []
    for modell in args.modelle:
        print(f"\n== {modell}")
        for fall in faelle:
            if fall["rolle"] == "teacher":
                token = jwt.issue(pseudonym=lehrkraft, roles=["teacher"], grade=None)[0]
            else:
                token = jwt.issue(pseudonym=schueler, roles=["student"], grade=str(fall["stufe"]))[0]
            eintrag = {"id": fall["id"], "titel": fall["titel"], "frage": fall["frage"],
                       "modell_soll": modell, "modell": None, "antwort": ""}
            with httpx.Client(base_url=args.basis, timeout=300.0,
                              headers={"Cookie": f"session={token}"}) as client:
                try:
                    r = chat_probe.frage_stellen(client, fall["frage"], assistent=None, gruppe=None,
                                                 modell=modell)
                    eintrag.update(antwort=r["antwort"], modell=r["modell"])
                    if r.get("konversation"):
                        konversationen.append(r["konversation"])
                except (httpx.HTTPError, SystemExit) as e:
                    eintrag["abbruch"] = f"{type(e).__name__}: {e}"
            eintrag["pruefung"] = pruefe(eintrag["antwort"], fall)
            if eintrag.get("abbruch"):
                print(f"  {fall['id']}: ABGEBROCHEN — {eintrag['abbruch'][:100]}", flush=True)
                ergebnisse.append(eintrag)
                continue
            print(f"  {fall['id']}: {'bestanden' if eintrag['pruefung']['bestanden'] else 'NICHT bestanden'}"
                  f" — {eintrag['pruefung'].get('molekuele') or eintrag['pruefung']['bloecke'] or '(kein Block)'}",
                  flush=True)
            ergebnisse.append(eintrag)

    for kennung in konversationen:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (kennung,))

    ziel = Path(args.ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    stempel = f"{datetime.now():%Y-%m-%d_%H%M}"
    (ziel / f"strukturformeln_{stempel}.md").write_text(protokoll(ergebnisse, args.modelle), encoding="utf-8")
    (ziel / f"strukturformeln_{stempel}.json").write_text(
        json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nProtokoll: {ziel / f'strukturformeln_{stempel}.md'}")


if __name__ == "__main__":
    main()
