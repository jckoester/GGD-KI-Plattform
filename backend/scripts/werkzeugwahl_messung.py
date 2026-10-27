#!/usr/bin/env python3
"""Werkzeugwahl-Messung: Welches Werkzeug wählt das Modell für eine Frage?

    python scripts/werkzeugwahl_messung.py --modell chat-komplex --arm mit --lauf 1-ck-mit \\
        --ziel "<PKM>/Plaene/Messungen-Werkzeugwahl"

Gebaut für Kriterium 1 aus ``docs/admin/updates-und-wartung.md`` („Wann `get_operatoren`
entfällt“). Die Fälle stehen in ``scripts/szenarien/werkzeugwahl_operatoren.yaml``. Es gibt
zwei Arme: das Backend wie ausgeliefert (``--arm mit``) und das Backend mit
``WERKZEUGE_AUS=get_operatoren`` (``--arm ohne``). Den Schalter setzt man beim Start des
Backends. Das Skript sieht ihn nicht, ``--arm`` ist nur die Beschriftung im Protokoll.

Gefragt wird als **Lehrkraft** im freien Chat, ohne Gruppe und ohne Assistenten. Den
Fachbezug setzt ``subject_id`` der neuen Konversation. Jede Frage läuft in einer eigenen
Konversation, die danach gelöscht wird.

Ausgewertet werden die Werkzeuge aus dem Rohstrom (``tool_status``). Bei
``list_context_nodes`` kommt dazu, ob es alles geliefert hat (``vorab_debug.aufzaehlungen``,
geliefert = gesamt). Ob die Antwort die Liste auch vollständig wiedergibt, liest Jan im
Protokoll.

⚠️ Nur für Entwicklungsinstanzen: eigener Sitzungs-Token, echtes Budget.
"""
import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings

HIER = Path(__file__).resolve().parent
SZENARIEN = HIER / "szenarien" / "werkzeugwahl_operatoren.yaml"


def _lade(name: str):
    """`scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt“) — über den Pfad laden."""
    spec = importlib.util.spec_from_file_location(name, HIER / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def bewerten(fall: dict, werkzeuge: list[str], aufzaehlungen: list[dict]) -> list[str]:
    """Verstöße gegen ``eins_von``, ``nicht`` und ``vollstaendig``. Leer heißt: wie erwartet."""
    befund = []
    eins_von = fall.get("eins_von") or []
    if eins_von and not set(eins_von) & set(werkzeuge):
        befund.append(f"keines von {', '.join(eins_von)}")
    for w in fall.get("nicht") or []:
        if w in werkzeuge:
            befund.append(f"{w} aufgerufen")
    if fall.get("vollstaendig"):
        for a in aufzaehlungen:
            if a.get("gesamt") is not None and a.get("geliefert") is not None \
                    and a["geliefert"] < a["gesamt"]:
                befund.append(f"Aufzählung gekürzt ({a['geliefert']} von {a['gesamt']})")
    return befund


def _selbsttest() -> None:
    fall = {"eins_von": ["list_context_nodes", "get_operatoren"], "nicht": ["search_context_nodes"],
            "vollstaendig": True}
    assert bewerten(fall, ["get_operatoren"], []) == []
    assert bewerten(fall, ["search_context_nodes"], []) == [
        "keines von list_context_nodes, get_operatoren", "search_context_nodes aufgerufen"]
    assert bewerten(fall, ["list_context_nodes"], [{"gesamt": 20, "geliefert": 12}]) == [
        "Aufzählung gekürzt (12 von 20)"]
    assert bewerten({}, [], []) == []


def protokoll(kopf: dict, ergebnisse: list[dict]) -> str:
    t = [f"# Werkzeugwahl `get_operatoren` — Lauf {kopf['lauf']}", "",
         f"- **Datum:** {kopf['datum']}",
         f"- **Modell:** {kopf['modell']}",
         f"- **Arm:** {kopf['arm']} `get_operatoren`"
         + (" (Backend mit `WERKZEUGE_AUS=get_operatoren`)" if kopf["arm"] == "ohne" else ""),
         "- **Rolle:** Lehrkraft, freier Chat, ohne Gruppe und Assistent, ohne Stufe",
         f"- **Szenarien:** `{kopf['szenarien']}`", ""]
    ok = sum(1 for e in ergebnisse if not e["befund"])
    t += [f"**Wie erwartet:** {ok} von {len(ergebnisse)}", "",
          "| Fall | Fach | Werkzeuge | Befund | USD |", "|---|---|---|---|---|"]
    for e in ergebnisse:
        usd = sum(k["usd"] for k in e["kosten"] if k.get("usd") is not None) if e["kosten"] else None
        t.append(f"| {e['id']} | {e['fach'] or '—'} | {', '.join(e['werkzeuge']) or '—'} | "
                 f"{'; '.join(e['befund']) or 'ok'} | {f'{usd:.4f}' if usd is not None else '?'} |")
    gesamt = [k["usd"] for e in ergebnisse for k in e["kosten"] if k.get("usd") is not None]
    t += ["", f"**Kosten:** {sum(gesamt):.4f} USD für {len(gesamt)} Antworten", ""]
    for e in ergebnisse:
        t += ["---", "", f"## {e['id']}", "", f"**Frage:** {e['frage']}", "",
              f"*Soll:* {e.get('soll') or '—'}", "",
              f"- **Werkzeuge:** {', '.join(e['werkzeuge']) or '—'}"]
        for a in e["aufzaehlungen"]:
            t.append(f"  - `list_context_nodes`: titel={a.get('titel')!r}, content_type={a.get('content_type')!r}, "
                     f"subject={a.get('subject')!r} → gesamt {a.get('gesamt')}, geliefert {a.get('geliefert')}")
        t.append(f"- **Befund:** {'; '.join(e['befund']) or 'wie erwartet'}")
        if e.get("fehler"):
            t.append(f"- ⚠️ **Abbruch:** {e['fehler']}")
        t += ["", "\n".join(f"> {z}" if z else ">" for z in (e["antwort"] or "*(leer)*").splitlines()), "",
              "- [ ] Antwort vollständig bzw. wie *Soll*", ""]
    return "\n".join(t)


def main() -> None:
    p = argparse.ArgumentParser(description="Werkzeugwahl-Messung (get_operatoren)")
    p.add_argument("--szenarien", type=Path, default=SZENARIEN)
    p.add_argument("--modell", required=False)
    p.add_argument("--arm", choices=["mit", "ohne"], required=False,
                   help="Beschriftung: Backend mit oder ohne get_operatoren (WERKZEUGE_AUS)")
    p.add_argument("--lauf", required=False)
    p.add_argument("--ziel", type=Path, help="Verzeichnis für Protokoll (.md) und Rohdaten (.json)")
    p.add_argument("--konto", default="", help="Anfang des Pseudonyms einer Lehrkraft mit LiteLLM-Schlüssel")
    p.add_argument("--nur", action="append", help="Nur diese Fall-ID (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--behalten", action="store_true", help="Konversationen nicht löschen")
    p.add_argument("--selbsttest", action="store_true")
    args = p.parse_args()

    faelle = yaml.safe_load(args.szenarien.read_text(encoding="utf-8"))["faelle"]
    _selbsttest()
    if args.selbsttest:
        print(f"Selbsttest bestanden ({len(faelle)} Fälle gelesen)")
        return
    for pflicht in ("modell", "arm", "lauf", "ziel"):
        if not getattr(args, pflicht):
            p.error(f"--{pflicht} fehlt")
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz (eigener Token, echtes Budget).")
    if args.nur:
        faelle = [f for f in faelle if f["id"] in args.nur]

    chat_probe = _lade("chat_probe")
    entfall = _lade("entfall_messung")
    messung = _lade("assistent_messung")
    conn = entfall.verbindung()
    zeile = entfall._alle(conn, "SELECT pseudonym FROM pseudonym_audit WHERE roles::text LIKE '%%teacher%%' "
                                "AND litellm_key IS NOT NULL AND pseudonym LIKE %s ORDER BY created_at LIMIT 1",
                          args.konto + "%")
    if not zeile:
        raise SystemExit("Kein Lehrkraft-Konto mit LiteLLM-Schlüssel gefunden.")
    lehrkraft = zeile[0][0]
    fach_ids = dict(entfall._alle(conn, "SELECT slug, id FROM subjects"))
    token, _ = get_jwt_service().issue(pseudonym=lehrkraft, roles=["teacher"], grade=None)

    ergebnisse = []
    try:
        with httpx.Client(base_url=args.basis, timeout=300.0,
                          headers={"Cookie": f"session={token}"}) as client:
            for fall in faelle:
                fach = fall.get("fach")
                if fach and fach not in fach_ids:
                    raise SystemExit(f"{fall['id']}: Fach {fach!r} unbekannt")
                try:
                    r = chat_probe.frage_stellen(client, fall["frage"], assistent=None, gruppe=None,
                                                 modell=args.modell, fach=fach_ids.get(fach) if fach else None)
                except SystemExit as fehler:     # HTTP-Fehler: Fall festhalten, weiter
                    r = {"werkzeuge": [], "antwort": "", "fehler": str(fehler), "konversation": None,
                         "vorab_debug": None}
                werkzeuge = [w["tool"] for w in r["werkzeuge"]]
                aufz = (r.get("vorab_debug") or {}).get("aufzaehlungen") or []
                befund = bewerten(fall, werkzeuge, aufz)
                if r.get("fehler"):
                    befund.append("abgebrochen")
                ergebnisse.append({**fall, "werkzeuge": werkzeuge, "aufzaehlungen": aufz, "befund": befund,
                                   "antwort": r["antwort"], "fehler": r.get("fehler"),
                                   "konversation": r.get("konversation"), "kosten": []})
                print(f"{fall['id']:<28} {', '.join(werkzeuge) or '—':<50} {'; '.join(befund) or 'ok'}")
        for e in ergebnisse:
            if e["konversation"]:
                e["kosten"] = messung.kosten(conn, e["konversation"])
    finally:
        if not args.behalten:
            with conn.cursor() as cur:
                for e in ergebnisse:
                    if e["konversation"]:
                        cur.execute("DELETE FROM conversations WHERE id = %s AND pseudonym = %s",
                                    (e["konversation"], lehrkraft))
            conn.commit()
        conn.close()

    kopf = {"lauf": args.lauf, "datum": datetime.now().strftime("%d.%m.%Y, %H:%M"), "modell": args.modell,
            "arm": args.arm, "szenarien": args.szenarien.name}
    args.ziel.mkdir(parents=True, exist_ok=True)
    md = args.ziel / f"werkzeugwahl-{args.lauf}.md"
    md.write_text(protokoll(kopf, ergebnisse), encoding="utf-8")
    (args.ziel / f"werkzeugwahl-{args.lauf}.json").write_text(
        json.dumps({"kopf": kopf, "ergebnisse": ergebnisse}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Protokoll: {md}")


if __name__ == "__main__":
    main()
