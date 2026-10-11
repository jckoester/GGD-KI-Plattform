#!/usr/bin/env python3
"""Messung zu Päckchen A, Schritt 8: Trägt der Jahresplanungs-Assistent einen Entfall ein?

    python scripts/entfall_messung.py --datei scripts/szenarien/entfall.yaml \\
        --json ergebnis.json --verlauf verlauf.md
    python scripts/entfall_messung.py --datei scripts/szenarien/entfall.yaml --nur-aufbau

**Anlass:** „Diese Stunde fällt aus" verlangt vom Modell `set_category{…,'ausfall'}` — und
soll der Stoff weiter, zusätzlich `move_content`. Am 24.09.2026 kam nur das Verschieben; der
Quelltermin blieb `unterricht` und zählte weiter in der Stundenbilanz. Eine Operation
`cancel_lesson` wird gebaut, wenn das noch vorkommt (Plan, Schritt 8).

**Die Kriterien** (vor dem ersten Lauf festgelegt, Plan Schritt 8):

* **Fehlgriff** — der Assistent hat den Plan geändert, aber der Quelltermin ist danach noch
  `unterricht`. Das entscheidet: ab einem Fehlgriff in 15 Läufen wird gebaut.
* **nicht geschrieben** — nach beiden Zügen ist am Plan nichts geändert (etwa, weil der
  Assistent noch fragt). Kein Fehlgriff, aber gezählt: Häufen sich solche Läufe, sagt die
  Messung über den Fehlgriff nichts.
* Zur Einordnung, nicht entscheidend: Ausfall eingetragen (`ausfall`, Herkunft `assistent`);
  vor der Zustimmung geschrieben; wohin Thema und Entwurf des Quelltermins gewandert sind;
  die gerufenen Werkzeuge.

**Eine eigene Gruppe.** Vor jedem Lauf baut das Skript die Gruppe aus der Szenariendatei neu
auf — Termine, Einheiten mit Themen, Entwürfe — und löscht sie am Ende samt Snapshots und
Konversationen. Bestehende Gruppen der Instanz bleiben unberührt. Die Einheiten und Entwürfe
entstehen über die echten Endpunkte (wie in der Oberfläche); nur Gruppe, Mitgliedschaft und
Termine schreibt das Skript selbst.

⚠️ Nur für Entwicklungsinstanzen — wie `chat_probe.py`: eigener Sitzungs-Token, echte
Modellaufrufe auf Kosten des Budgets der Lehrkraft.
"""
import argparse
import asyncio
import importlib.util
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import psycopg2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings
from app.context.embedding import vor_einer_messung

# `scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden.
_spec = importlib.util.spec_from_file_location("chat_probe", Path(__file__).with_name("chat_probe.py"))
chat_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chat_probe)

#: Was ein Termin trägt und ein Lauf ändern kann.
SPALTEN = ("kategorie", "thema", "ue_node_id", "stunde_node_id", "anpassung_noetig",
           "ausfall_herkunft", "ausfall_vorher")


# ── Datenbank ────────────────────────────────────────────────────────────────


def verbindung():
    conn = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    conn.autocommit = True
    return conn


def _alle(conn, sql, *werte):
    with conn.cursor() as cur:
        cur.execute(sql, werte)
        return cur.fetchall()


def _eins(conn, sql, *werte):
    zeilen = _alle(conn, sql, *werte)
    return zeilen[0][0] if zeilen else None


def lehrkraft_der_gruppe(conn, gruppe: int) -> str:
    pseudonym = _eins(conn, "SELECT pseudonym FROM group_memberships WHERE group_id = %s "
                            "AND role_in_group = 'teacher' LIMIT 1", gruppe)
    if pseudonym is None:
        raise SystemExit(f"Gruppe {gruppe} hat keine Lehrkraft — falsche Instanz?")
    return pseudonym


def planungsassistent(conn) -> int:
    kennung = _eins(conn, "SELECT id FROM assistants WHERE status = 'active' "
                          "AND tool_groups::jsonb ? 'planning' ORDER BY sort_order, id LIMIT 1")
    if kennung is None:
        raise SystemExit("Kein aktiver Assistent mit planning — erst seeden (scripts/seed_assistants.py).")
    return kennung


def abbauen(conn, gruppe: dict) -> None:
    """Die Messgruppe und alles, was an ihr hängt.

    Konversationen und Knoten zuerst: Ihre Gruppenspalten stehen auf `SET NULL` — mit der
    Gruppe gelöscht würden sie nicht, sondern blieben herrenlos zurück. Termine, Snapshots,
    Mitgliedschaften und geparkte Inhalte gehen per `CASCADE` mit der Gruppe.
    """
    gid = gruppe["id"]
    name = _eins(conn, "SELECT name FROM groups WHERE id = %s", gid)
    if name is not None and name != gruppe["name"]:
        raise SystemExit(f"Gruppe {gid} heißt „{name}“, nicht „{gruppe['name']}“ — fremde Gruppe, Abbruch.")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE group_id = %s", (gid,))
        cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = %s OR read_scope_group_id = %s",
                    (gid, gid))
        cur.execute("DELETE FROM groups WHERE id = %s", (gid,))


def termine(gruppe: dict) -> list[tuple[date, int, int]]:
    """(Datum, erste Stunde, Länge) je Termin, nach Datum."""
    tag, ende, liste = gruppe["von"], gruppe["bis"], []
    while tag <= ende:
        for t in gruppe["termine"]:
            if tag.weekday() == t["wochentag"]:
                liste.append((tag, t["start"], t["stunden"]))
        tag += timedelta(days=1)
    return liste


def aufbauen(conn, client: httpx.Client, gruppe: dict, pseudonym: str) -> dict[date, str]:
    """Baut die Messgruppe neu auf und liefert {Datum: Termin-ID}."""
    abbauen(conn, gruppe)
    gid = gruppe["id"]
    fach = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", gruppe["fach"])
    if fach is None:
        raise SystemExit(f"Fach „{gruppe['fach']}“ gibt es nicht — falsche Instanz?")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, 'teaching_group', %s)",
                    (gid, gruppe["name"], f"messung-entfall-{gid}", fach))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen')", (gid, pseudonym))
        for tag, start, stunden in termine(gruppe):
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr) "
                        "VALUES (%s, %s, %s, %s, 1)", (gid, tag, start, stunden))
    slots = {d: s for s, d in _alle(conn, "SELECT id::text, date FROM lesson_slots WHERE group_id = %s "
                                          "ORDER BY date", gid)}

    def ok(resp):
        if resp.status_code >= 300:
            raise SystemExit(f"Aufbau: {resp.request.method} {resp.request.url.path} → "
                             f"{resp.status_code} {resp.text[:300]}")
        return resp.json()

    reihe = iter(sorted(slots))
    for farbe, einheit in enumerate(gruppe["einheiten"]):
        ue = ok(client.post(f"/planning/groups/{gid}/units", json={"titel": einheit["titel"], "farbe": farbe}))["id"]
        for thema in einheit["themen"]:
            ok(client.patch(f"/planning/slots/{slots[next(reihe)]}", json={"ue_node_id": ue, "thema": thema}))
    for tag in gruppe["entwuerfe"]:
        ok(client.post(f"/planning/slots/{slots[tag]}/lesson"))
    return slots


def plan(conn, gid: int) -> dict[str, dict]:
    zeilen = _alle(conn, f"SELECT id::text, date, {', '.join(SPALTEN)} FROM lesson_slots "
                         "WHERE group_id = %s ORDER BY date", gid)
    return {z[0]: {"datum": z[1], **{s: (str(v) if v is not None else None)
                                     for s, v in zip(SPALTEN, z[2:])}} for z in zeilen}


def snapshots(conn, gid: int) -> int:
    return _eins(conn, "SELECT count(*) FROM slot_plan_snapshots WHERE group_id = %s", gid)


# ── Ein Lauf und seine Kriterien ─────────────────────────────────────────────


def lauf(client, conn, fall: dict, assistent: int, gid: int) -> list[dict]:
    verlauf: list[dict] = []
    konversation = None
    zuege = []
    for text in fall["zuege"]:
        zug = chat_probe.frage_stellen(client, text, assistent=assistent, gruppe=gid,
                                       verlauf=verlauf, konversation=konversation)
        konversation = zug["konversation"]
        verlauf += [{"role": "user", "content": text}, {"role": "assistant", "content": zug["antwort"]}]
        zug["plan"] = plan(conn, gid)
        zug["snapshots"] = snapshots(conn, gid)
        zug["zeit"] = datetime.now().strftime("%H:%M:%S")
        zuege.append(zug)
    return zuege


def _geaendert(ausgang: dict, jetzt: dict) -> bool:
    return ausgang != jetzt


def wohin(ausgang: dict, jetzt: dict, quelle: str) -> str:
    """Wo Thema und Entwurf des Quelltermins nach dem Lauf stehen."""
    def ort(feld):
        wert = ausgang[quelle][feld]
        if wert is None:
            return "—"
        treffer = [s for s, z in jetzt.items() if z[feld] == wert]
        if not treffer:
            return "weg"
        return ", ".join(f"{jetzt[s]['datum']:%d.%m.}" if s != quelle else "geblieben" for s in treffer)
    return f"Thema → {ort('thema')} · Entwurf → {ort('stunde_node_id')}"


def bewerte(ausgang: dict, ausgang_snapshots: int, zuege: list[dict], quelle: str) -> dict:
    """⚠️ Snapshots **gegen den Stand nach dem Aufbau** zählen: Schon der Aufbau legt welche an
    (jedes Thema über `PATCH /planning/slots` einen). Mit „mehr als null" galt im ersten
    Probelauf jeder Lauf als geschrieben — ein Lauf ohne Änderung wäre als Fehlgriff gezählt
    worden."""
    nachher = zuege[-1]["plan"]
    geschrieben = _geaendert(ausgang, nachher) or zuege[-1]["snapshots"] > ausgang_snapshots
    q = nachher[quelle]
    return {
        "geschrieben": geschrieben,
        "fehlgriff": geschrieben and q["kategorie"] == "unterricht",
        "ausfall": q["kategorie"] == "ausfall",
        "herkunft_assistent": q["ausfall_herkunft"] == "assistent",
        "vor_zustimmung": _geaendert(ausgang, zuege[0]["plan"]) or zuege[0]["snapshots"] > ausgang_snapshots,
        "kategorie": q["kategorie"],
        "wohin": wohin(ausgang, nachher, quelle),
        "werkzeuge": [[w["tool"] for w in z["werkzeuge"]] for z in zuege],
    }


# ── Ausgabe ──────────────────────────────────────────────────────────────────


def _zitat(text: str) -> str:
    return "\n".join(f"> {zeile}" if zeile else ">" for zeile in (text or "*(leer)*").splitlines())


def verlauf_als_markdown(kopf: dict, laeufe: list[dict]) -> str:
    teile = [f"# Messung Entfall — {kopf['beginn']}", "",
             f"Assistent {kopf['assistent']} „{kopf['assistent_name']}“ · Modell {kopf['modell']} · "
             f"Quelltermin {kopf['quelle']:%d.%m.%Y} · Datei `{kopf['datei']}`. "
             "Vor jedem Lauf wurde die Messgruppe neu aufgebaut. Kriterien: Plan, Schritt 8.", ""]
    for l in laeufe:
        k = l["kriterien"]
        marke = "abgebrochen" if "grund" in l else ("✗ Fehlgriff" if k["fehlgriff"] else
                                                    "– nicht geschrieben" if not k["geschrieben"] else "✓")
        teile += ["---", "", f"## {l['fall']} · Lauf {l['lauf']} — {marke}", ""]
        if "grund" in l:
            teile += [l["grund"], ""]
            continue
        teile += [f"Quelltermin danach: `{k['kategorie']}`"
                  f"{' (Herkunft assistent)' if k['herkunft_assistent'] else ''} · {k['wohin']}"
                  f"{' · **vor der Zustimmung geschrieben**' if k['vor_zustimmung'] else ''}", ""]
        for z in l["zuege"]:
            teile += [f"**Lehrkraft** ({z['zeit']}): {z['frage']}", "",
                      f"*Werkzeuge:* {' → '.join(z['werkzeuge']) or '—'}", "", _zitat(z["antwort"]), ""]
            if z.get("fehler"):
                teile += [f"*Fehler:* {z['fehler']}", ""]
    return "\n".join(teile)


def main() -> None:
    p = argparse.ArgumentParser(description="Messung Entfall (Päckchen A, Schritt 8)")
    p.add_argument("--datei", type=Path, required=True)
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--assistent", type=int, default=None)
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--verlauf", type=Path, default=None)
    p.add_argument("--trotzdem", action="store_true", help="auch ohne vollständige Vektoren")
    p.add_argument("--nur-aufbau", action="store_true",
                   help="Gruppe aufbauen, Plan zeigen, wieder abbauen — ohne Modellaufruf")
    args = p.parse_args()
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz (eigener Token, echtes Budget, schreibt Pläne).")

    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    gruppe, quelltag = daten["gruppe"], daten["quelle"]
    faelle = [f for f in daten["faelle"] if not args.nur or f["id"] in args.nur]

    conn = verbindung()
    pseudonym = lehrkraft_der_gruppe(conn, daten["lehrkraft_der_gruppe"])
    token, _ = get_jwt_service().issue(pseudonym=pseudonym, roles=["teacher"], grade=None)
    client = httpx.Client(base_url=args.basis, timeout=300.0, headers={"Cookie": f"session={token}"})

    if args.nur_aufbau:
        try:
            aufbauen(conn, client, gruppe, pseudonym)
            for z in plan(conn, gruppe["id"]).values():
                print(f"{z['datum']:%a %d.%m.}  {z['kategorie']:<10} {z['thema'] or '—':<42} "
                      f"{'Einheit' if z['ue_node_id'] else '':<8} {'Entwurf' if z['stunde_node_id'] else ''}")
        finally:
            abbauen(conn, gruppe)
            client.close()
        return

    asyncio.run(vor_einer_messung(trotzdem=args.trotzdem))
    assistent = args.assistent or planungsassistent(conn)
    name = _eins(conn, "SELECT name FROM assistants WHERE id = %s", assistent)
    kopf = {"datei": args.datei.name, "beginn": datetime.now().strftime("%d.%m.%Y, %H:%M"),
            "assistent": assistent, "assistent_name": name, "modell": "?", "quelle": quelltag}
    laeufe: list[dict] = []
    try:
        for fall in faelle:
            for nr in range(1, args.laeufe + 1):
                slots = aufbauen(conn, client, gruppe, pseudonym)
                quelle = slots[quelltag]
                ausgang = plan(conn, gruppe["id"])
                ausgang_snapshots = snapshots(conn, gruppe["id"])
                try:
                    zuege = lauf(client, conn, fall, assistent, gruppe["id"])
                except (httpx.HTTPError, SystemExit) as fehler:
                    grund = f"{type(fehler).__name__}: {str(fehler)[:200]}"
                    print(f"{fall['id']:<30} Lauf {nr}  abgebrochen — {grund}", flush=True)
                    laeufe.append({"fall": fall["id"], "lauf": nr, "grund": grund,
                                   "kriterien": {"fehlgriff": False, "geschrieben": False}})
                    continue
                k = bewerte(ausgang, ausgang_snapshots, zuege, quelle)
                kopf["modell"] = zuege[0].get("modell") or kopf["modell"]
                marke = "✗ FEHLGRIFF" if k["fehlgriff"] else ("– nicht geschrieben" if not k["geschrieben"] else "✓")
                werkzeuge = " | ".join(" → ".join(w) or "—" for w in k["werkzeuge"])
                print(f"{fall['id']:<30} Lauf {nr}  {marke:<20} {k['kategorie']:<10} "
                      f"{k['wohin']}{'  [vor Zustimmung]' if k['vor_zustimmung'] else ''}  [{werkzeuge}]",
                      flush=True)
                laeufe.append({
                    "fall": fall["id"], "lauf": nr, "stoff_weiter": fall["stoff_weiter"], "kriterien": k,
                    "modell": zuege[0].get("modell"),
                    "zuege": [{"frage": z["frage"], "werkzeuge": [w["tool"] for w in z["werkzeuge"]],
                               "antwort": z["antwort"], "zeit": z["zeit"], "fehler": z.get("fehler")}
                              for z in zuege],
                })
                if args.verlauf:
                    args.verlauf.write_text(verlauf_als_markdown(kopf, laeufe), encoding="utf-8")
    finally:
        abbauen(conn, gruppe)
        client.close()
        conn.close()

    gezaehlt = [l for l in laeufe if "grund" not in l]
    fehlgriffe = sum(l["kriterien"]["fehlgriff"] for l in gezaehlt)
    ohne = sum(not l["kriterien"]["geschrieben"] for l in gezaehlt)
    print(f"\nFehlgriffe: {fehlgriffe} von {len(gezaehlt)} · nicht geschrieben: {ohne} · "
          f"abgebrochen: {len(laeufe) - len(gezaehlt)}")
    kategorien = Counter(l["kriterien"]["kategorie"] for l in gezaehlt if l["kriterien"]["geschrieben"])
    print("Quelltermin danach (geschriebene Läufe): "
          + ", ".join(f"{k} {n}" for k, n in kategorien.most_common()))
    print("→ cancel_lesson bauen" if fehlgriffe else "→ kein Fehlgriff")
    if args.json:
        args.json.write_text(json.dumps(laeufe, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
