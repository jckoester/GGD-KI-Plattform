#!/usr/bin/env python3
"""Messung „Schüler:in fragt nach der letzten Stunde" (0.15, Todo → Chat, Punkt 2).

    python scripts/letzte_stunde_messung.py --datei scripts/szenarien/letzte_stunde.yaml \\
        --json ergebnis.json --verlauf verlauf.md
    python scripts/letzte_stunde_messung.py --datei scripts/szenarien/letzte_stunde.yaml --nur-aufbau

**Die Frage:** Eine Schüler:in schreibt „Letzte Stunde haben wir etwas über XY gelernt, das ich
nicht ganz verstanden habe." Weiß das Modell, was drankam? Der Block „Aktueller Unterricht"
(`student_context.get_current_topic`) nennt nur **nachbereitete** Stunden, und die
Auto-Bestätigung bestätigt eine Stunde erst, wenn die nächste vorbei ist. Zwischen letzter und
nächster Stunde steht dort also die **vorletzte** als „Zuletzt behandelt".

**Das Kriterium** (Jan, 11.10.2026, vor dem ersten Lauf): Plan B wird gebaut, wenn ohne
Nachbereitung in (a) in einem von drei Läufen der Knoten zu XY fehlt **oder** in (a)–(c) in
einem Lauf eine falsche Stunde als die letzte behandelt wird.

* **Knoten zu XY** — steht der Begriffsknoten in den Bausteinen der Antwort
  (`message_context_nodes`, Vorab oder Werkzeug)? Das prüft das Skript. Seit 0.16 zusätzlich:
  Stand er **als Angebot** im Systemtext (Messkanal `vorab_debug`), und wurde er nachgeschlagen?
  Plan „Vorab-Suche-Begriffe" § 7.4 Nr. 8: Angebot 3/3 ist das Ziel, ob nachgeschlagen, wird
  gelesen und protokolliert.
* **Falsche Stunde als die letzte** — die Antwort sagt oder setzt voraus, dass die vorletzte
  Stunde (Thema oder Datum) die letzte war. Das Skript **markiert** Verdachtssätze („letzte"
  oder „zuletzt" zusammen mit Thema oder Datum der vorletzten Stunde); entschieden wird beim
  Lesen jedes Laufs.

**Eine eigene Gruppe** (wie `entfall_messung.py`, dessen Abbau hier mitbenutzt wird): Termine
relativ zu heute, Einheit, Entwürfe mit Begriff und Kompetenz als `refs`, die zwei älteren
Stunden nachbereitet — über die echten Endpunkte. Schüler:in ist ein vorhandenes Dev-Konto mit
vorübergehender Mitgliedschaft; ihr Pseudonym wird nicht ausgegeben. Am Ende ist die Gruppe
samt Konversationen gelöscht.

**Seit 0.20 (Päckchen AC)** auch für `begriffe_im_schuelerchat.yaml`: ältere Stunden außerhalb des
Zwei-Stunden-Fensters (`aeltere`), eine fremde Gruppe derselben Schüler:in (`fremde_gruppe`, Fall mit
`gruppe: fremd`) und der Fachbezug ohne Gruppe (`weg: fach`). `xy` darf eine Liste sein; ein Fall
gilt als „Knoten da", wenn **alle** Titel in den Bausteinen stehen.

⚠️ Nur für Entwicklungsinstanzen — eigene Sitzungs-Token, echte Modellaufrufe auf Kosten des
Budgets der Schüler:in.
"""
import argparse
import asyncio
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings
from app.context.embedding import vor_einer_messung


def _lade(name: str):
    """`scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden."""
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


chat_probe = _lade("chat_probe")
entfall = _lade("entfall_messung")
_alle, _eins = entfall._alle, entfall._eins

STRICH = "′"


# ── Aufbau ───────────────────────────────────────────────────────────────────


def termine(wochentage: list[int], heute: date, vorher: int, nachher: int) -> tuple[list[date], list[date]]:
    """Die letzten ``vorher`` Unterrichtstage vor heute (alt → neu) und die nächsten ``nachher``."""
    vergangen, kommend = [], []
    tag = heute - timedelta(days=1)
    while len(vergangen) < vorher:
        if tag.weekday() in wochentage:
            vergangen.insert(0, tag)
        tag -= timedelta(days=1)
    tag = heute + timedelta(days=1)
    while len(kommend) < nachher:
        if tag.weekday() in wochentage:
            kommend.append(tag)
        tag += timedelta(days=1)
    return vergangen, kommend


#: So viel Budget (USD) muss das Konto noch haben — 18 Läufe kosten mit chat-standard Cent-Beträge.
MINDESTBUDGET_USD = 0.5


def schuelerin(conn, mindestens: float = MINDESTBUDGET_USD) -> tuple[str, str | None]:
    """Ein Dev-Konto mit Schülerrolle, LiteLLM-Schlüssel und Restbudget.

    Ohne Schlüssel antwortet der Chat 503, ohne Budget 429 — der erste Messlauf (11.10.2026)
    nahm das erste Konto und bekam 18-mal „Budget aufgebraucht". Das Budget steht am
    LiteLLM-Nutzer, nicht am Schlüssel; gefragt wird mit dem Master-Key, ausgegeben wird nichts.
    """
    kandidaten = _alle(conn, "SELECT pseudonym, grade FROM pseudonym_audit WHERE roles::text LIKE '%%student%%' "
                             "AND litellm_key IS NOT NULL ORDER BY created_at")
    with httpx.Client(base_url=settings.litellm_proxy_url, timeout=20.0,
                      headers={"Authorization": f"Bearer {settings.litellm_master_key}"}) as litellm:
        for pseudonym, stufe in kandidaten:
            antwort = litellm.get("/user/info", params={"user_id": pseudonym})
            info = antwort.json().get("user_info") or {} if antwort.status_code == 200 else {}
            grenze, ausgaben = info.get("max_budget"), info.get("spend") or 0.0
            if grenze is None or grenze - ausgaben >= mindestens:
                return pseudonym, str(stufe) if stufe is not None else None
    raise SystemExit(f"Kein Schüler:innen-Konto mit Schlüssel und mindestens {mindestens} USD Restbudget.")


def knoten(conn, fach: str, *, begriff: str | None = None, kompetenz: str | None = None) -> tuple[str, str]:
    """(Kennung, Titel) eines Begriffs bzw. einer inhaltsbezogenen Kompetenz im Fach."""
    if begriff:
        zeile = _alle(conn, "SELECT n.id::text, n.title FROM context_nodes n JOIN subjects s ON s.id = n.subject_id "
                            "WHERE n.content_type = 'begriff' AND n.status = 'active' AND n.title = %s "
                            "AND s.slug = %s ORDER BY n.created_at LIMIT 1", begriff, fach)
    else:
        zeile = _alle(conn, "SELECT n.id::text, left(coalesce(n.content, n.title), 160) FROM context_nodes n "
                            "JOIN subjects s ON s.id = n.subject_id WHERE n.content_type = 'ik_kompetenz' "
                            "AND n.status = 'active' AND n.metadata->>'kompetenz_nr' = %s AND s.slug = %s "
                            "ORDER BY n.created_at DESC LIMIT 1", kompetenz, fach)
    if not zeile:
        raise SystemExit(f"Knoten {begriff or kompetenz} im Fach {fach} fehlt — falsche Instanz?")
    return zeile[0]


def aufbauen(conn, lehrkraft: httpx.Client, daten: dict, lehrer: str, schueler: str, heute: date,
             *, mit_begriffen: bool = False) -> dict:
    """Baut die Messgruppe auf; liefert die Termine (vergangen, kommend) als Datum → Slot-ID.

    ``mit_begriffen``: Die Begriffe stehen zusätzlich als `refs` am Entwurf — das bringt erst
    Päckchen A1; heute legt die Oberfläche dort nur Kompetenzen ab. Ohne den Schalter misst
    die Messung also den heutigen Stand, mit ihm eine Vorschau.
    """
    from app.planning.calendar import load_school_year

    gruppe = daten["gruppe"]
    entfall.abbauen(conn, gruppe)
    if daten.get("fremde_gruppe"):
        entfall.abbauen(conn, daten["fremde_gruppe"])
    gid, fach = gruppe["id"], gruppe["fach"]
    fach_id = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", fach)
    vergangen, kommend = termine(gruppe["wochentage"], heute, len(daten["stunden"]), len(daten["kommende"]))
    wechsel = load_school_year().halbjahreswechsel
    aeltere = []
    for alt in daten.get("aeltere") or []:
        tag = heute - timedelta(weeks=alt["wochen_zurueck"])
        while tag.weekday() not in gruppe["wochentage"]:
            tag -= timedelta(days=1)
        aeltere.append((tag, alt))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, 'teaching_group', %s)",
                    (gid, gruppe["name"], f"messung-letzte-{gid}", fach_id))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) VALUES "
                    "(%s, %s, 'teacher', 'eigen'), (%s, %s, 'student', 'manuell')", (gid, lehrer, gid, schueler))
        if daten.get("fremde_gruppe"):
            fremd = daten["fremde_gruppe"]
            cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, 'teaching_group', "
                        "(SELECT id FROM subjects WHERE slug = %s))",
                        (fremd["id"], fremd["name"], f"messung-fremd-{fremd['id']}", fremd["fach"]))
            cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) VALUES "
                        "(%s, %s, 'teacher', 'eigen'), (%s, %s, 'student', 'manuell')",
                        (fremd["id"], lehrer, fremd["id"], schueler))
        for tag in [*(t for t, _ in aeltere), *vergangen, *kommend]:
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr) "
                        "VALUES (%s, %s, 3, 1, %s)", (gid, tag, 1 if tag < wechsel else 2))
    slots = {d: s for s, d in _alle(conn, "SELECT id::text, date FROM lesson_slots WHERE group_id = %s", gid)}

    def ok(resp):
        if resp.status_code >= 300:
            raise SystemExit(f"Aufbau: {resp.request.method} {resp.request.url.path} → "
                             f"{resp.status_code} {resp.text[:300]}")
        return resp.json()

    ue = ok(lehrkraft.post(f"/planning/groups/{gid}/units", json={"titel": gruppe["einheit"], "farbe": 0}))["id"]
    alte_ues = {alt["einheit"]: ok(lehrkraft.post(f"/planning/groups/{gid}/units",
                                                  json={"titel": alt["einheit"], "farbe": 1}))["id"]
                for _, alt in aeltere}

    def entwurf_anlegen(tag, stunde, einheit):
        ok(lehrkraft.patch(f"/planning/slots/{slots[tag]}", json={"ue_node_id": einheit, "thema": stunde["thema"]}))
        entwurf = ok(lehrkraft.post(f"/planning/slots/{slots[tag]}/lesson"))["id"]
        ik_id, ik_text = knoten(conn, fach, kompetenz=stunde["kompetenz"])
        refs = [{"node_id": ik_id, "typ": "ik", "code": stunde["kompetenz"], "titel": ik_text}]
        if mit_begriffen:
            for name in stunde.get("begriffe") or [stunde["begriff"]]:
                begriff_id, begriff_titel = knoten(conn, fach, begriff=name)
                refs.append({"node_id": begriff_id, "typ": "concept", "titel": begriff_titel})
        ok(lehrkraft.patch(f"/planning/lessons/{entwurf}", json={
            "titel": stunde["thema"],
            "phasen": [{"name": "Erarbeitung", "dauer_min": 30}, {"name": "Sicherung", "dauer_min": 10}],
            "refs": refs,
        }))

    for tag, alt in aeltere:
        entwurf_anlegen(tag, alt, alte_ues[alt["einheit"]])
        nachbereiten(lehrkraft, slots[tag])
    for tag, stunde in zip(vergangen, daten["stunden"]):
        entwurf_anlegen(tag, stunde, ue)
    for tag, thema in zip(kommend, daten["kommende"]):
        ok(lehrkraft.patch(f"/planning/slots/{slots[tag]}", json={"ue_node_id": ue, "thema": thema}))
    # Die älteren nachbereiten — die letzte bleibt offen, wie zwischen letzter und nächster Stunde.
    for tag in vergangen[:-1]:
        nachbereiten(lehrkraft, slots[tag])
    return {"vergangen": [(d, slots[d]) for d in vergangen], "kommend": [(d, slots[d]) for d in kommend],
            "aeltere": [(d, alt["thema"]) for d, alt in aeltere]}


def nachbereiten(lehrkraft: httpx.Client, slot: str) -> None:
    resp = lehrkraft.post(f"/planning/slots/{slot}/review", json={})
    if resp.status_code >= 300:
        raise SystemExit(f"Nachbereitung {slot}: {resp.status_code} {resp.text[:300]}")


def block(gid: int) -> str | None:
    """Der Block „Aktueller Unterricht" der Gruppe — mit denselben Funktionen, die ihn für den
    Prompt bauen (`context.service._planning_block`)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.context.service import _group_label
    from app.planning.student_context import get_current_topic, get_exam_scope, render_topic_block

    async def lesen():
        # Eine eigene Engine je Aufruf: `asyncio.run` öffnet jedes Mal einen neuen Loop, und
        # die Verbindungen der gemeinsamen `AsyncSessionLocal` hängen am ersten.
        engine = create_async_engine(settings.database_url)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession)() as db:
                heute = date.today()
                thema = await get_current_topic(db, gid, heute)
                arbeit = await get_exam_scope(db, gid, today=heute)
                if thema is None and arbeit is None:
                    return None
                return render_topic_block(thema, await _group_label(db, gid), arbeit)
        finally:
            await engine.dispose()
    return asyncio.run(lesen())


# ── Ein Lauf und was er zeigt ────────────────────────────────────────────────


def bausteine(conn, konversation: str) -> list[dict]:
    """Was der Antwort vorlag — Vorab-Suche und Werkzeugsuche (`message_context_nodes`)."""
    return [{"titel": t, "art": a, "herkunft": h} for t, a, h in _alle(
        conn, "SELECT n.title, n.content_type, m.herkunft FROM messages msg "
              "JOIN message_context_nodes m ON m.message_id = msg.id "
              "JOIN context_nodes n ON n.id = m.node_id "
              "WHERE msg.conversation_id = %s AND msg.role = 'assistant' ORDER BY m.position",
        konversation)]


#: Satzgrenzen — aber nicht der Punkt in „7.10." (vor einem Punkt steht dort eine Ziffer).
_SATZ = re.compile(r"\n+|(?<=[!?])\s+|(?<=[^\W\d])\.\s+(?=[A-ZÄÖÜ„*])")
_LETZTE = re.compile(r"\b(letzte[nrms]?|zuletzt)\b", re.IGNORECASE)


def _datumsformen(tag: date) -> list[str]:
    return [f"{tag.day}.{tag.month}.", f"{tag.day:02d}.{tag.month:02d}.", f"{tag.day}. {tag.month}."]


def verdachtssaetze(antwort: str, thema_stamm: str, tag: date) -> list[str]:
    """Sätze, die „letzte"/„zuletzt" mit Thema oder Datum der vorletzten Stunde verbinden."""
    treffer = []
    for satz in _SATZ.split(antwort or ""):
        if not _LETZTE.search(satz):
            continue
        if thema_stamm.lower() in satz.lower() or any(f in satz for f in _datumsformen(tag)):
            treffer.append(satz.strip())
    return treffer


def bewerte(fall: dict, antwort: str, vorlagen: list[dict], stunden: list[dict], vorletzte_tag: date,
            vorab_debug: dict | None = None) -> dict:
    """Was ein Lauf zeigt. ``stunden`` von alt nach neu; die vorletzte ist ``stunden[-2]``.

    ``vorab_debug`` ist der Messkanal (0.16); ohne ihn bleiben ``xy_angeboten`` und
    ``xy_nachgeschlagen`` ``None`` — keine Aussage, nicht „nein"."""
    roh = fall.get("xy")
    titel = roh if isinstance(roh, list) else [roh] if roh else []
    xy = " + ".join(titel) or None
    je = {t: sorted({b["herkunft"] for b in vorlagen if b["art"] == "begriff" and b["titel"] == t}) for t in titel}
    stamm = lambda s: s["begriff"][:13]  # „Elektronegativ…" trifft auch „elektronegativer"
    angebot = [a for a in (vorab_debug or {}).get("angebot", []) if a["titel"] in titel]
    nachgeschlagen = set((vorab_debug or {}).get("nachgeschlagen", []))
    mit_kanal = vorab_debug is not None and xy
    return {
        "xy": xy,
        "xy_knoten": all(je.values()) if xy else None,
        "xy_herkunft": [f"{t}: {'/'.join(h) or '—'}" for t, h in je.items()] if len(titel) > 1
                       else (je[titel[0]] if titel else []),
        "xy_je": je,
        "xy_angeboten": bool(angebot) if mit_kanal else None,
        "xy_nachgeschlagen": any(a["node_id"] in nachgeschlagen for a in angebot) if mit_kanal else None,
        "genannt": [s["begriff"] for s in stunden if stamm(s).lower() in (antwort or "").lower()],
        "verdacht": verdachtssaetze(antwort, stamm(stunden[-2]), vorletzte_tag),
        "fragt_nach": "?" in (antwort or ""),
    }


# ── Ausgabe ──────────────────────────────────────────────────────────────────


def _zitat(text: str) -> str:
    return "\n".join(f"> {z}" if z else ">" for z in (text or "*(leer)*").splitlines())


def verlauf_als_markdown(kopf: dict, laeufe: list[dict]) -> str:
    teile = [f"# Messung „letzte Stunde“ — {kopf['beginn']}", "",
             f"Chat ohne Assistent, als Schüler:in, Gruppenbezug · Modell {kopf['modell']} · "
             f"refs: {'Kompetenzen und Begriffe (Vorschau A1)' if kopf.get('mit_begriffen') else 'nur Kompetenzen'} · "
             f"Datei `{kopf['datei']}`. Termine: {kopf['termine']}.", "",
             "**Falsche Stunde als die letzte?** Je Lauf beim Lesen entscheiden — Verdachtssätze sind "
             "markiert, entscheidend ist der ganze Text.", ""]
    for phase, text in kopf["bloecke"].items():
        teile += [f"**Block „Aktueller Unterricht“ {phase}:**", "", "```", text or "(kein Block)", "```", ""]
    for l in laeufe:
        teile += ["---", "", f"## {l['fall']} · Lauf {l['lauf']}", "", f"**Schüler:in:** {l['frage']}", ""]
        if "grund" in l:
            teile += [f"abgebrochen — {l['grund']}", ""]
            continue
        k = l["kriterien"]
        if k["xy"]:
            teile.append(f"- Knoten „{k['xy']}“: {'✓ ' + ', '.join(k['xy_herkunft']) if k['xy_knoten'] else '✗ fehlt'}")
            if k.get("xy_angeboten") is not None:
                teile.append(f"- Als Angebot: {'ja' if k['xy_angeboten'] else 'nein'}"
                             + (f" · nachgeschlagen: {'ja' if k['xy_nachgeschlagen'] else 'nein'}"
                                if k["xy_angeboten"] else ""))
        teile += [f"- Genannt: {', '.join(k['genannt']) or '—'} · Rückfrage: {'ja' if k['fragt_nach'] else 'nein'}",
                  f"- Werkzeuge: {' → '.join(l['werkzeuge']) or '—'}",
                  f"- Bausteine: {', '.join(b['titel'] + ' (' + b['herkunft'] + ')' for b in l['bausteine']) or '—'}"]
        if k["verdacht"]:
            teile.append("- ⚠️ Verdacht: " + " · ".join(f"„{s}“" for s in k["verdacht"]))
        teile += ["", _zitat(l["antwort"]), "", "Falsche Stunde als die letzte: [ ] ja  [ ] nein", ""]
    return "\n".join(teile)


def main() -> None:
    p = argparse.ArgumentParser(description="Messung „letzte Stunde“")
    p.add_argument("--datei", type=Path, required=True)
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--verlauf", type=Path, default=None)
    p.add_argument("--trotzdem", action="store_true", help="auch ohne vollständige Vektoren")
    p.add_argument("--nur-aufbau", action="store_true", help="aufbauen, Plan und Block zeigen, abbauen")
    p.add_argument("--mit-begriffen", action="store_true",
                   help="Begriffe zusätzlich als refs (Vorschau auf Päckchen A1)")
    p.add_argument("--mindestbudget", type=float, default=MINDESTBUDGET_USD,
                   help="Restbudget (USD), das das Schüler:innen-Konto mindestens haben muss")
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--ohne-nachbereitete", action="store_true",
                   help="nur die Fälle ohne Nachbereitung der letzten Stunde (keine Strich-Fälle)")
    args = p.parse_args()
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz (eigene Token, echtes Budget, legt Gruppen an).")

    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    heute = date.today()
    conn = entfall.verbindung()
    lehrer = entfall.lehrkraft_der_gruppe(conn, daten["lehrkraft_der_gruppe"])
    schueler, stufe = schuelerin(conn, args.mindestbudget)
    jwt = get_jwt_service()
    lehrkraft = httpx.Client(base_url=args.basis, timeout=60.0,
                             headers={"Cookie": f"session={jwt.issue(pseudonym=lehrer, roles=['teacher'], grade=None)[0]}"})
    lernende = httpx.Client(base_url=args.basis, timeout=300.0,
                            headers={"Cookie": f"session={jwt.issue(pseudonym=schueler, roles=['student'], grade=stufe)[0]}"})
    gid = daten["gruppe"]["id"]
    fremd_gid = (daten.get("fremde_gruppe") or {}).get("id")
    fach_id = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", daten["gruppe"]["fach"])
    ohne_gruppe: list[str] = []  # Konversationen aus `weg: fach` — `abbauen` erreicht sie nicht
    laeufe: list[dict] = []
    kopf = {"datei": args.datei.name, "beginn": datetime.now().strftime("%d.%m.%Y, %H:%M"), "modell": "?",
            "bloecke": {}, "mit_begriffen": args.mit_begriffen}
    # ⚠️ **Vor dem Aufbau prüfen, nicht danach.** Die Entwürfe der Messgruppe haben in den
    # ersten Sekunden noch keinen Vektor, und die Prüfung brach daran ab (erster Lauf,
    # 11.10.2026). Für die Messung zählen sie nicht: Schüler:innen lesen `group_teachers` nicht.
    if not args.nur_aufbau:
        asyncio.run(vor_einer_messung(trotzdem=args.trotzdem))
    try:
        termin = aufbauen(conn, lehrkraft, daten, lehrer, schueler, heute, mit_begriffen=args.mit_begriffen)
        vergangen = termin["vergangen"]
        kopf["termine"] = " · ".join(
            f"{d:%a %d.%m.} {s['thema']}{' (nachbereitet)' if i < len(vergangen) - 1 else ''}"
            for i, ((d, _), s) in enumerate(zip(vergangen, daten["stunden"])))
        if termin["aeltere"]:
            kopf["termine"] = " · ".join(f"{d:%a %d.%m.} {t} (nachbereitet)" for d, t in termin["aeltere"]) \
                + " · … · " + kopf["termine"]
        if args.nur_aufbau:
            print(kopf["termine"])
            print(block(gid))
            nachbereiten(lehrkraft, vergangen[-1][1])
            print("— nach Nachbereitung der letzten —")
            print(block(gid))
            return
        phasen = (("ohne Nachbereitung der letzten", ""), ("letzte nachbereitet", STRICH))
        for phase, suffix in phasen[:1] if args.ohne_nachbereitete else phasen:
            if suffix:
                nachbereiten(lehrkraft, vergangen[-1][1])
            for fall in [f for f in daten["faelle"] if not args.nur or f["id"] in args.nur]:
                name = fall["id"] + suffix
                for nr in range(1, args.laeufe + 1):
                    try:
                        if fall.get("weg") == "fach":
                            zug = chat_probe.frage_stellen(lernende, fall["frage"], assistent=None, gruppe=None,
                                                           fach=fach_id)
                            ohne_gruppe.append(zug["konversation"])
                        else:
                            zug = chat_probe.frage_stellen(lernende, fall["frage"], assistent=None,
                                                           gruppe=fremd_gid if fall.get("gruppe") == "fremd" else gid)
                    except (httpx.HTTPError, SystemExit) as fehler:
                        grund = f"{type(fehler).__name__}: {str(fehler)[:200]}"
                        print(f"{name:<4} Lauf {nr}  abgebrochen — {grund}", flush=True)
                        laeufe.append({"fall": name, "lauf": nr, "frage": fall["frage"], "grund": grund})
                        continue
                    if phase not in kopf["bloecke"]:
                        kopf["bloecke"][phase] = block(gid)
                    vorlagen = bausteine(conn, zug["konversation"])
                    k = bewerte(fall, zug["antwort"], vorlagen, daten["stunden"], vergangen[-2][0],
                                zug.get("vorab_debug"))
                    kopf["modell"] = zug.get("modell") or kopf["modell"]
                    xy = "" if k["xy"] is None else ("XY ✓ " if k["xy_knoten"] else "XY ✗ ")
                    xy += "Angebot ✓ " if k["xy_angeboten"] else ""
                    print(f"{name:<4} Lauf {nr}  {xy}genannt: {', '.join(k['genannt']) or '—'}"
                          f"{'  ⚠️ Verdacht' if k['verdacht'] else ''}{'  ?' if k['fragt_nach'] else ''}", flush=True)
                    laeufe.append({"fall": name, "lauf": nr, "frage": fall["frage"], "kriterien": k,
                                   "antwort": zug["antwort"], "bausteine": vorlagen,
                                   "werkzeuge": [w["tool"] for w in zug["werkzeuge"]], "modell": zug.get("modell")})
                    if args.verlauf:
                        args.verlauf.write_text(verlauf_als_markdown(kopf, laeufe), encoding="utf-8")
    finally:
        with conn.cursor() as cur:
            for k in ohne_gruppe:
                cur.execute("DELETE FROM conversations WHERE id = %s", (k,))
        entfall.abbauen(conn, daten["gruppe"])
        if daten.get("fremde_gruppe"):
            entfall.abbauen(conn, daten["fremde_gruppe"])
        lehrkraft.close()
        lernende.close()
        conn.close()

    if args.nur_aufbau:
        return
    print("\nFall  XY-Knoten  Angebot  Verdacht  Rückfrage")
    for fall in dict.fromkeys(l["fall"] for l in laeufe):
        eigene = [l["kriterien"] for l in laeufe if l["fall"] == fall and "kriterien" in l]
        xy = sum(1 for k in eigene if k["xy_knoten"]) if eigene and eigene[0]["xy"] else None
        ang = (sum(1 for k in eigene if k["xy_angeboten"])
               if eigene and eigene[0]["xy_angeboten"] is not None else None)
        print(f"{fall:<5} {('%d/%d' % (xy, len(eigene))) if xy is not None else '—':<10} "
              f"{('%d/%d' % (ang, len(eigene))) if ang is not None else '—':<8} "
              f"{sum(1 for k in eigene if k['verdacht'])}/{len(eigene):<7} {sum(k['fragt_nach'] for k in eigene)}/{len(eigene)}")
    if args.json:
        args.json.write_text(json.dumps(laeufe, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
