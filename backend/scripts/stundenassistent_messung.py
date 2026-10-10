#!/usr/bin/env python3
"""Messung zum Stundenassistenten (0.15, Päckchen A Schritt 6).

    python scripts/stundenassistent_messung.py --datei scripts/szenarien/stundenentwurf.yaml
    python scripts/stundenassistent_messung.py --datei scripts/szenarien/stunde_finden.yaml \\
        --laeufe 3 --json ergebnis.json --verlauf verlauf.md

Je Fall und Lauf eine eigene Konversation mit dem Stundenassistenten (dem ersten aktiven
Assistenten mit `lesson_planning`, oder `--assistent`), als Lehrkraft der Gruppe aus der
Szenariendatei. Die Fälle und ihr Format stehen in den Dateien unter `szenarien/`.

**Vor jedem Lauf wird der Ausgangsstand wiederhergestellt** — Entwürfe, Slot-Zuordnung,
Kanten — und am Ende noch einmal: Ein Lauf, der schreibt, verfälschte sonst den nächsten,
und die Entwürfe der Instanz blieben verändert zurück. Am Ende werden alle Konversationen
gelöscht, die der Mess-Login seit Messbeginn mit diesem Assistenten angelegt hat — auch die
abgebrochener Läufe; sie stünden sonst im Verlauf der Lehrkraft. (Wer währenddessen in der
Oberfläche mit demselben Login und Assistenten chattet, verliert diese Chats mit.)

**Ein abgebrochener Lauf** (Zeitüberschreitung, HTTP-Fehler) zählt als nicht bestanden, mit
dem Grund im Ergebnis; die Messung läuft weiter. Am 10.10.2026 stockte ein Antwortstrom nach
dem Lesen 300 Sekunden lang und riss bis dahin die ganze Messung mit.

**Der Verlauf** (`--verlauf`) ist der reine Chat zum Nachlesen, als Markdown: je Fall und Lauf
die Züge der Lehrkraft, die gerufenen Werkzeuge, die Antworten des Assistenten im Wortlaut und —
wo geschrieben wurde — der Entwurf vorher und nachher. Dazu die Kriterien des Laufs.

**Die Kriterien** (Plan, Schritt 6, vor dem ersten Lauf festgelegt) stehen in `bewerte`.
Ein Lauf ist bestanden, wenn jedes zutreffende Kriterium erfüllt ist; ein Fall, wenn alle
Läufe bestanden sind.

⚠️ Nur für Entwicklungsinstanzen — wie `chat_probe.py`: eigener Sitzungs-Token, echte
Modellaufrufe auf Kosten des Budgets der Lehrkraft.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings
from app.context.embedding import vor_einer_messung

# `scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden.
_spec = importlib.util.spec_from_file_location("chat_probe", Path(__file__).with_name("chat_probe.py"))
chat_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chat_probe)

LESEN, SUCHEN, SCHREIBEN = "get_lesson_detail", "finde_stunde", "update_lesson_phases"


# ── Datenbank: Stand festhalten und wiederherstellen ─────────────────────────


def verbindung():
    conn = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    conn.autocommit = True
    return conn


def _eins(conn, sql, *werte):
    with conn.cursor() as cur:
        cur.execute(sql, werte)
        zeile = cur.fetchone()
    return zeile[0] if zeile else None


def _alle(conn, sql, *werte):
    with conn.cursor() as cur:
        cur.execute(sql, werte)
        return cur.fetchall()


def lehrkraft_der_gruppe(conn, gruppe: int) -> str:
    pseudonym = _eins(conn, "SELECT pseudonym FROM group_memberships WHERE group_id = %s "
                            "AND role_in_group = 'teacher' LIMIT 1", gruppe)
    if pseudonym is None:
        raise SystemExit(f"Gruppe {gruppe} hat keine Lehrkraft — falsche Instanz?")
    return pseudonym


def gruppen_der_lehrkraft(conn, pseudonym: str) -> list[int]:
    return [g for (g,) in _alle(conn, "SELECT group_id FROM group_memberships WHERE pseudonym = %s "
                                      "AND role_in_group = 'teacher'", pseudonym)]


def stunde_am(conn, gruppe: int, datum: date) -> str | None:
    wert = _eins(conn, "SELECT stunde_node_id::text FROM lesson_slots WHERE group_id = %s AND date = %s "
                       "ORDER BY start_period NULLS LAST LIMIT 1", gruppe, datum)
    return wert


def stundenassistent(conn) -> int:
    kennung = _eins(conn, "SELECT id FROM assistants WHERE status = 'active' "
                          "AND tool_groups::jsonb ? 'lesson_planning' ORDER BY id LIMIT 1")
    if kennung is None:
        raise SystemExit("Kein aktiver Assistent mit lesson_planning — erst seeden "
                         "(scripts/seed_assistants.py).")
    return kennung


def stand(conn, gruppen: list[int]) -> dict:
    """Was ein Lauf verändern kann: Entwürfe, die Zuordnung der Termine, Kanten der Entwürfe."""
    entwuerfe = {
        i: {"titel": t, "metadata": m or {}}
        for i, t, m in _alle(conn, "SELECT id::text, title, metadata FROM context_nodes "
                                   "WHERE content_type = 'unterrichtsstunde' "
                                   "AND write_scope_group_id = ANY(%s)", gruppen)
    }
    slots = dict(_alle(conn, "SELECT id::text, stunde_node_id::text FROM lesson_slots "
                             "WHERE group_id = ANY(%s)", gruppen))
    kanten = {k for (k,) in _alle(conn, "SELECT id::text FROM context_edges "
                                        "WHERE from_node_id::text = ANY(%s)", list(entwuerfe))}
    return {"entwuerfe": entwuerfe, "slots": slots, "kanten": kanten}


def zuruecksetzen(conn, ausgang: dict, gruppen: list[int]) -> None:
    jetzt = stand(conn, gruppen)
    with conn.cursor() as cur:
        for slot, stunde in jetzt["slots"].items():
            if ausgang["slots"].get(slot) != stunde:
                cur.execute("UPDATE lesson_slots SET stunde_node_id = %s WHERE id = %s",
                            (ausgang["slots"].get(slot), slot))
        neue = sorted(set(jetzt["entwuerfe"]) - set(ausgang["entwuerfe"]))
        if neue:
            cur.execute("DELETE FROM context_nodes WHERE id::text = ANY(%s)", (neue,))
        for kennung, alt in ausgang["entwuerfe"].items():
            if jetzt["entwuerfe"].get(kennung) != alt:
                cur.execute("UPDATE context_nodes SET title = %s, metadata = %s WHERE id = %s",
                            (alt["titel"], psycopg2.extras.Json(alt["metadata"]), kennung))
        neue_kanten = sorted(stand(conn, gruppen)["kanten"] - ausgang["kanten"])
        if neue_kanten:
            cur.execute("DELETE FROM context_edges WHERE id::text = ANY(%s)", (neue_kanten,))


# ── Ein Lauf und seine Bewertung ─────────────────────────────────────────────


def lauf(client, conn, fall: dict, assistent: int, gruppen: list[int]) -> tuple[list[dict], str | None]:
    stunde = stunde_am(conn, **fall["stunde"]) if "stunde" in fall else None
    verlauf: list[dict] = []
    konversation = None
    zuege = []
    for nr, text in enumerate(fall["zuege"], 1):
        zug = chat_probe.frage_stellen(
            client, text, assistent=assistent, gruppe=None,
            stunde=stunde if nr == 1 else None, verlauf=verlauf, konversation=konversation,
        )
        konversation = zug["konversation"]
        verlauf += [{"role": "user", "content": text}, {"role": "assistant", "content": zug["antwort"]}]
        zug["stand"] = stand(conn, gruppen)
        zug["bezug"] = _eins(conn, "SELECT stunde_node_id::text FROM conversations WHERE id = %s", konversation)
        zug["zeit"] = datetime.now().strftime("%H:%M:%S")
        zuege.append(zug)
    return zuege, konversation


def _werkzeuge(zug) -> list[str]:
    return [w["tool"] for w in zug["werkzeuge"]]


def _phasen(entwurf) -> list[dict]:
    return list((entwurf or {}).get("metadata", {}).get("phasen") or [])


def bewerte(fall: dict, ausgang: dict, zuege: list[dict], *, stunde: str | None,
            ziel: str | None = None) -> dict[str, bool]:
    """Die Kriterien aus dem Plan — je Fall nur die, die auf ihn zutreffen.

    ``stunde`` ist die Bezugsstunde des Falls (oder None), ``ziel`` der Entwurf des Termins
    aus ``waehlt``. Ohne Datenbank, damit sich prüfen lässt, dass die Kriterien Fehlgriffe
    überhaupt erkennen (`tests/unit/test_stundenassistent_messung.py`).
    """
    k: dict[str, bool] = {}

    # 1. Zuerst gelesen (mit Bezug) bzw. gesucht (ohne).
    erste = _werkzeuge(zuege[0])
    k["zuerst_gelesen"] = bool(erste) and erste[0] == (LESEN if stunde else SUCHEN)

    # 2. Ohne Zustimmung weder geschrieben noch ein Entwurf angelegt.
    ab = fall.get("zustimmung_ab")
    vorher_zuege = zuege[: ab - 1] if ab else zuege
    zu_frueh = any(SCHREIBEN in _werkzeuge(z) or z["stand"]["entwuerfe"] != ausgang["entwuerfe"]
                   for z in vorher_zuege)
    angelegt = any(set(z["stand"]["entwuerfe"]) - set(ausgang["entwuerfe"]) for z in zuege)
    k["nicht_ohne_zustimmung"] = not zu_frueh and not angelegt

    # 3.–5. Nach der Zustimmung: geschrieben, Kennungen erhalten, Skizzen ohne Dauer.
    if ab:
        vorher = ausgang["entwuerfe"][stunde]
        nachher = zuege[-1]["stand"]["entwuerfe"].get(stunde)
        geschrieben = (any(SCHREIBEN in _werkzeuge(z) for z in zuege[ab - 1:])
                       and nachher != vorher)
        k["schreibt_nach_zustimmung"] = geschrieben
        if geschrieben:
            alte = {p.get("id") for p in _phasen(vorher)}
            neu = [p for p in _phasen(nachher) if p.get("id") not in alte]
            k["kennungen_erhalten"] = len(neu) <= fall.get("neue_phasen_hoechstens", 0)
            offen = {p.get("id") for p in _phasen(vorher) if p.get("dauer_min") is None}
            k["skizze_ohne_dauer"] = all(p.get("dauer_min") is None
                                         for p in _phasen(nachher) if p.get("id") in offen)

    # Ohne Bezug: der richtige Termin gewählt — oder nachgefragt, ohne zu wählen.
    if "waehlt" in fall:
        k["waehlt_den_termin"] = ziel is not None and zuege[0]["bezug"] == ziel
    if fall.get("nachfrage"):
        k["fragt_nach"] = zuege[0]["bezug"] is None and "?" in zuege[0]["antwort"]
    return k


# ── Verlauf zum Nachlesen ────────────────────────────────────────────────────


def _phase_kurz(p: dict) -> str:
    def eintrag(feld):
        e = p.get(feld) or {}
        return e.get("titel") or e.get("wert") or ""
    teile = [f"{p.get('dauer_min')}′" if p.get("dauer_min") is not None else "ohne Dauer",
             p.get("prio") or "kern"]
    teile += [t for t in (eintrag("sozialform"), eintrag("methode")) if t]
    zeile = f"{p.get('name')} ({', '.join(teile)})"
    beschreibung = (p.get("beschreibung") or "").strip().splitlines()
    return zeile + (f" — {beschreibung[0][:90]}" if beschreibung else "")


def _zitat(text: str) -> str:
    if not text.strip():
        return "> [!warning] Assistent\n> *(leere Antwort)*"
    return "> [!quote] Assistent\n" + "\n".join(f"> {z}" for z in text.splitlines())


def verlauf_als_markdown(kopf: dict, laeufe: list[dict]) -> str:
    zeilen = [
        f"# Verlauf der Messung — {kopf['datei']}", "",
        f"Gemessen am {kopf['beginn']} · Modell `{kopf['modell']}` · Assistent „{kopf['assistent_name']}“ "
        f"(id {kopf['assistent']}) · Prompt-Stand `{kopf['prompt']}`  ",
        "Je Fall und Lauf eine eigene Konversation; vor jedem Lauf ist der Ausgangsstand "
        "wiederhergestellt. Kriterien: siehe Plan, Schritt 6.", "",
    ]
    for l in laeufe:
        zeilen += ["---", "", f"## {l['fall']} · Lauf {l['lauf']} · {'✓' if l['bestanden'] else '✗'}", ""]
        if l.get("bezugsstunde"):
            zeilen.append(f"Bezugsstunde: {l['bezugsstunde']}  ")
        zeilen += ["Kriterien: " + " · ".join(f"{n} {'✓' if ok else '✗'}" for n, ok in l["kriterien"].items()), ""]
        for z in l["zuege"]:
            werkzeuge = " → ".join(z["werkzeuge"]) or "—"
            zeilen += [f"**Lehrkraft** ({z['zeit']}): {z['frage']}", "",
                       f"*Werkzeuge:* {werkzeuge}" + (" ⚠️ Rundenlimit erreicht" if len(z["werkzeuge"]) >= 6 else ""),
                       "", _zitat(z["antwort"]), ""]
        if l.get("vorher") is not None and l.get("nachher") != l.get("vorher"):
            zeilen += ["**Entwurf vorher:**", ""] + [f"{i}. {_phase_kurz(p)}" for i, p in enumerate(l["vorher"], 1)]
            zeilen += ["", "**Entwurf nachher:**", ""] + [f"{i}. {_phase_kurz(p)}" for i, p in enumerate(l["nachher"] or [], 1)]
            if l.get("ziel_nachher") != l.get("ziel_vorher"):
                zeilen += ["", f"Stundenziel: „{l.get('ziel_vorher') or ''}“ → „{l.get('ziel_nachher') or ''}“"]
            zeilen.append("")
    return "\n".join(zeilen) + "\n"


# ── Ablauf ───────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Messung zum Stundenassistenten")
    p.add_argument("--datei", type=Path, required=True)
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--assistent", type=int, default=None)
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--json", type=Path, default=None, help="Ergebnis mit allen Antworten hierhin")
    p.add_argument("--verlauf", type=Path, default=None, help="Chatverlauf zum Nachlesen (Markdown)")
    p.add_argument("--trotzdem", action="store_true", help="auch ohne vollständige Vektoren")
    args = p.parse_args()

    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz (eigener Token, echtes Budget, schreibt Entwürfe).")

    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    if daten.get("heute") and daten["heute"] != date.today():
        raise SystemExit(f"Die Fälle sind auf {daten['heute']} geschnitten, heute ist {date.today()}.")
    faelle = [f for f in daten["faelle"] if not args.nur or f["id"] in args.nur]

    asyncio.run(vor_einer_messung(trotzdem=args.trotzdem))
    conn = verbindung()
    pseudonym = lehrkraft_der_gruppe(conn, daten["lehrkraft_der_gruppe"])
    gruppen = gruppen_der_lehrkraft(conn, pseudonym)
    assistent = args.assistent or stundenassistent(conn)
    for fall in faelle:
        if "stunde" in fall and stunde_am(conn, **fall["stunde"]) is None:
            raise SystemExit(f"{fall['id']}: kein Entwurf am {fall['stunde']} — falsche Instanz?")

    ausgang = stand(conn, gruppen)
    beginn = _eins(conn, "SELECT now()")
    name, prompt = _alle(conn, "SELECT name, system_prompt FROM assistants WHERE id = %s", assistent)[0]
    kopf = {"datei": args.datei.name, "beginn": datetime.now().strftime("%d.%m.%Y, %H:%M"),
            "assistent": assistent, "assistent_name": name, "modell": "?",
            "prompt": hashlib.sha256(prompt.encode()).hexdigest()[:10]}
    laeufe: list[dict] = []
    token, _ = get_jwt_service().issue(pseudonym=pseudonym, roles=["teacher"], grade=None)
    konversationen: list[str] = []
    ergebnisse = []
    try:
        with httpx.Client(base_url=args.basis, timeout=300.0,
                          headers={"Cookie": f"session={token}"}) as client:
            for fall in faelle:
                for nr in range(1, args.laeufe + 1):
                    zuruecksetzen(conn, ausgang, gruppen)
                    try:
                        zuege, konversation = lauf(client, conn, fall, assistent, gruppen)
                    except (httpx.HTTPError, SystemExit) as fehler:
                        grund = f"{type(fehler).__name__}: {str(fehler)[:200]}"
                        print(f"{fall['id']:<30} Lauf {nr}  ✗  abgebrochen — {grund}", flush=True)
                        ergebnisse.append({"fall": fall["id"], "lauf": nr, "bestanden": False,
                                           "kriterien": {"abgebrochen": False}, "grund": grund})
                        laeufe.append({"fall": fall["id"], "lauf": nr, "bestanden": False,
                                       "kriterien": {"abgebrochen": False}, "zuege": [],
                                       "bezugsstunde": f"abgebrochen — {grund}"})
                        continue
                    if konversation:
                        konversationen.append(konversation)
                    kriterien = bewerte(
                        fall, ausgang, zuege,
                        stunde=stunde_am(conn, **fall["stunde"]) if "stunde" in fall else None,
                        ziel=stunde_am(conn, **fall["waehlt"]) if "waehlt" in fall else None,
                    )
                    bestanden = all(kriterien.values())
                    werkzeuge = " | ".join(" → ".join(_werkzeuge(z)) or "—" for z in zuege)
                    fehlend = ", ".join(n for n, ok in kriterien.items() if not ok)
                    print(f"{fall['id']:<30} Lauf {nr}  {'✓' if bestanden else '✗'}  "
                          f"[{werkzeuge}]{'  fehlt: ' + fehlend if fehlend else ''}", flush=True)
                    ergebnisse.append({
                        "fall": fall["id"], "lauf": nr, "bestanden": bestanden, "kriterien": kriterien,
                        "modell": zuege[0].get("modell"),
                        "zuege": [{"frage": z["frage"], "werkzeuge": _werkzeuge(z),
                                   "antwort": z["antwort"]} for z in zuege],
                    })
                    kopf["modell"] = zuege[0].get("modell") or kopf["modell"]
                    stunde = stunde_am(conn, **fall["stunde"]) if "stunde" in fall else None
                    vorher = ausgang["entwuerfe"].get(stunde) if stunde else None
                    nachher = zuege[-1]["stand"]["entwuerfe"].get(stunde) if stunde else None
                    laeufe.append({
                        "fall": fall["id"], "lauf": nr, "bestanden": bestanden, "kriterien": kriterien,
                        "bezugsstunde": (f"Gruppe {fall['stunde']['gruppe']}, {fall['stunde']['datum']:%d.%m.%Y}"
                                         f" — „{vorher['titel']}“") if vorher else None,
                        "vorher": _phasen(vorher) if vorher else None,
                        "nachher": _phasen(nachher) if nachher else None,
                        "ziel_vorher": (vorher or {}).get("metadata", {}).get("stundenziel"),
                        "ziel_nachher": (nachher or {}).get("metadata", {}).get("stundenziel"),
                        "zuege": [{"frage": z["frage"], "werkzeuge": _werkzeuge(z), "antwort": z["antwort"],
                                   "zeit": z["zeit"]} for z in zuege],
                    })
                    if args.verlauf:
                        args.verlauf.write_text(verlauf_als_markdown(kopf, laeufe), encoding="utf-8")
    finally:
        zuruecksetzen(conn, ausgang, gruppen)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE (id::text = ANY(%s)) OR (pseudonym = %s "
                        "AND assistant_id = %s AND created_at >= %s)",
                        (konversationen, pseudonym, assistent, beginn))
        conn.close()

    print("\nFall                           bestanden  nicht erfüllt")
    for fall in faelle:
        eigene = [e for e in ergebnisse if e["fall"] == fall["id"]]
        gut = sum(e["bestanden"] for e in eigene)
        offen = sorted({n for e in eigene for n, ok in e["kriterien"].items() if not ok})
        print(f"{fall['id']:<30} {gut}/{len(eigene)}        {', '.join(offen) or '—'}")
    if args.json:
        args.json.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
