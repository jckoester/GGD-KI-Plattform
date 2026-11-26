#!/usr/bin/env python3
"""Messung 0.61: Der Jahresplan-Assistent und der Jahresverlaufsplan der Fachschaft.

    python scripts/jahresplan_messung.py --selbsttest
    python scripts/jahresplan_messung.py --trocken
    python scripts/jahresplan_messung.py --modell chat-komplex --laeufe 3 --verlauf b.md --json b.json
    python scripts/jahresplan_messung.py --prompt-rev d5af5202 --nur ohne_plan --nur ohne_bezug --json a.json
    python scripts/jahresplan_messung.py --vergleich a.json b.json
    python scripts/jahresplan_messung.py --bewertung b.md

**Was gemessen wird** (Plan `Jahresplan-Assistent-Verlaufsplan-0.61-Plan.md`, F6): Liest der
Assistent den Plan, wenn es passt, und nur dann; legt er erst nach Zustimmung an; überschreibt er
nichts; nimmt er das Anlegen mit der richtigen Funktion zurück; erfindet er ohne Plan keinen; was
kostet der neue Prompt gegen den alten (Arm A mit `--prompt-rev`, Vergleich mit `--vergleich`).

**Der Assistent** heißt „Jahresplanung (Messung)“: Beschreibung, Fähigkeit und Marke wie die
geseedete „Jahresplanung“, Prompt aus der Repo-Datei (oder mit `--prompt-rev` aus einem Commit),
Modell aus `--modell`. Nach der Messung `disabled`; der geseedete bleibt unberührt.

**Eine eigene Welt je Lauf** (Muster `entfall_messung.py`): Messfach, Curriculum und
Jahresverlaufsplan (ORM), Gruppe, Mitgliedschaft und Termine (SQL), vorhandene Einheiten des
Falls über die echten Endpunkte. Am Ende des Laufs wird alles gelöscht, am Ende der Messung
auch das Messfach. Mess-Knoten tragen `metadata.messung`.

**Bewertet wird an der Datenbank**, je Zug: Einheiten der Gruppe (Titel, Kapitel, Herkunft aus
dem Plan), Termine (Einheit, Kategorie, Thema), Snapshots — dazu die gerufenen Funktionen aus
dem Strom und die Antwort. Ob die Antwort taugt, beurteilt Jan (Kästchen, `--bewertung`).

⚠️ Nur für Entwicklungsinstanzen — eigener Sitzungs-Token, echte Modellaufrufe auf Kosten des
Budgets der Mess-Lehrkraft, schreibt vorübergehend in die Datenbank.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HIER = Path(__file__).resolve().parent
REPO = HIER.parent.parent
DATEI = HIER / "szenarien" / "jahresplan.yaml"

#: Die Funktionen der Fähigkeit `planning`, deren Namen nicht in einer Antwort stehen sollen.
FUNKTIONEN = (
    "get_lesson_slots", "get_curriculum_chapters", "get_plan_balance", "get_verlaufsplan",
    "create_teaching_unit", "assign_slots_to_unit", "set_slot_topics", "set_slot_category",
    "verlaufsplan_einheiten_anlegen", "verlaufsplan_anlegen_zuruecknehmen", "undo_last_change",
    "apply_plan_operations", "get_reflow_context", "get_unit_detail", "create_lessons",
)
BEWERTUNGEN = ("brauchbar", "teilweise", "unbrauchbar")
KENNUNG = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
WOCHENTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


# ── Rein (ohne Datenbank) — Unit-Tests in tests/unit/test_jahresplan_messung.py ──


def platzhalter(text: str, termine: list[date]) -> str:
    """{termin:N} → „Do, 10.12.“ (N-ter Termin, ab 1)."""
    def ersetzen(m):
        d = termine[int(m.group(1)) - 1]
        return f"{WOCHENTAG[d.weekday()]}, {d:%d.%m.}"
    return re.sub(r"\{termin:(\d+)\}", ersetzen, text)


def plan_abschnitte(welt: dict, vergangene_wochen: int, kapitel_ids: list[str]) -> list[dict]:
    """Die Abschnitte des Plans: „Rückblick“ über die vergangenen Wochen, dann die der Datei."""
    aus = []
    if vergangene_wochen:
        aus.append({"id": "rueckblick", "titel": "Rückblick", "wochen": vergangene_wochen,
                    "kapitel_ids": [], "sequenz_ids": [], "notiz": "", "puffer": False})
    for i, a in enumerate(welt["plan"]["abschnitte"], 1):
        aus.append({"id": f"a{i}", "titel": a["titel"], "wochen": a["wochen"],
                    "kapitel_ids": [] if a.get("puffer") else [kapitel_ids[a["kapitel"] - 1]],
                    "sequenz_ids": [], "notiz": a.get("notiz", ""), "puffer": bool(a.get("puffer"))})
    return aus


def geaendert(vorher: dict, nachher: dict) -> bool:
    """Hat ein Zug etwas geschrieben? Einheiten, Termine oder neue Snapshots."""
    return (vorher["einheiten"] != nachher["einheiten"] or vorher["termine"] != nachher["termine"]
            or nachher["snapshots"] > vorher["snapshots"])


def bewerte(fall: dict, zuege: list[dict], ausgang: dict) -> tuple[dict[str, bool], dict]:
    """Kriterien eines Laufs. `zuege[i]` trägt `namen`, `antwort`, `vorher`, `stand`, `fehler`;
    `ausgang` ist der Stand nach dem Aufbau (mit `vorhandene`: IDs der Einheiten des Falls)."""
    k: dict[str, bool] = {}
    berichtet: dict = {}
    for n, (z, d) in enumerate(zip(zuege, fall["zuege"]), 1):
        namen = set(z["namen"])
        if d.get("muss") or d.get("nicht"):
            k[f"Z{n} Aufrufe"] = set(d.get("muss") or []) <= namen and not (set(d.get("nicht") or []) & namen)
        if d.get("schreibt") is False:
            k[f"Z{n} schreibt nicht"] = not geaendert(z["vorher"], z["stand"])
        if d.get("antwort") or d.get("antwort_nicht"):
            k[f"Z{n} Antwort"] = (all(re.search(m, z["antwort"], re.I) for m in d.get("antwort") or [])
                                  and not any(re.search(m, z["antwort"], re.I) for m in d.get("antwort_nicht") or []))
        if z.get("fehler"):
            k[f"Z{n} ohne Abbruch"] = False

    antworten = "\n".join(z["antwort"] for z in zuege)
    k["keine Funktionsnamen"] = not any(f in antworten for f in FUNKTIONEN) and not KENNUNG.search(antworten)

    if not zuege:
        return k, berichtet
    stand = zuege[-1]["stand"]
    e = fall.get("ende") or {}
    aus_plan = [x for x in stand["einheiten"] if x["lauf"]]
    if "aus_plan" in e:
        k[f"Ende {e['aus_plan']} aus dem Plan"] = len(aus_plan) == e["aus_plan"]
    if "aus_plan_min" in e:
        k[f"Ende ≥ {e['aus_plan_min']} aus dem Plan"] = len(aus_plan) >= e["aus_plan_min"]
    if "einheiten_min" in e:
        k[f"Ende ≥ {e['einheiten_min']} Einheiten"] = len(stand["einheiten"]) >= e["einheiten_min"]
    titel = [x["titel"] for x in stand["einheiten"]]
    for t in e.get("titel") or []:
        k[f"Ende Titel {t}"] = t in titel
    for t in e.get("titel_nicht") or []:
        k[f"Ende ohne Titel {t}"] = t not in titel
    if e.get("vorhandene_unveraendert"):
        vorher = {x["id"]: x for x in ausgang["einheiten"]}
        jetzt = {x["id"]: x for x in stand["einheiten"]}
        belegt = {s: v for s, v in ausgang["termine"].items() if v["ue"]}
        k["Ende Vorhandenes unverändert"] = (all(jetzt.get(i) == x for i, x in vorher.items())
                                             and all(stand["termine"].get(s, {}).get("ue") == v["ue"]
                                                     for s, v in belegt.items()))
    if kat := e.get("kategorie"):
        slot = ausgang["reihe"][kat["termin"] - 1]
        k[f"Ende Termin {kat['termin']} {kat['wert']}"] = stand["termine"][slot]["kategorie"] == kat["wert"]
    # Immer: Keine Einheit aus dem Plan steht leer, wenn das Anlegen zurückgenommen wurde —
    # eine Einheit mit Herkunft ohne Termin nach einem `undo_last_change` wäre genau das.
    leer = [x["titel"] for x in aus_plan if not any(v["ue"] == x["id"] for v in stand["termine"].values())]
    if any("undo_last_change" in z["namen"] for z in zuege):
        k["keine leeren Einheiten nach Rücknahme"] = not leer
    if leer:
        berichtet["Einheiten aus dem Plan ohne Termin"] = leer
    return k, berichtet


def kosten_je_zug(laeufe: list[dict]) -> dict[str, list[dict]]:
    """{Fall: [je Zug {ein, aus, usd} gemittelt über die Läufe]} für `--vergleich`."""
    aus: dict[str, list[dict]] = {}
    for fall in sorted({l["fall"] for l in laeufe}):
        eigene = [l["kosten_je_zug"] for l in laeufe if l["fall"] == fall and l.get("kosten_je_zug")]
        if not eigene:
            continue
        n = min(len(x) for x in eigene)
        aus[fall] = [{f: round(mean(x[i][f] for x in eigene), 4) for f in ("ein", "aus", "usd")} for i in range(n)]
    return aus


def vergleich(a: list[dict], b: list[dict]) -> list[str]:
    ka, kb = kosten_je_zug(a), kosten_je_zug(b)
    zeilen = ["Fall               Zug  Token ein A → B        $ A → B"]
    for fall in sorted(set(ka) & set(kb)):
        for i, (x, y) in enumerate(zip(ka[fall], kb[fall]), 1):
            pct = (y["ein"] - x["ein"]) / x["ein"] * 100 if x["ein"] else 0
            zeilen.append(f"{fall:<18} {i:>3}  {x['ein']:>7.0f} → {y['ein']:<7.0f} ({pct:+.0f} %)  "
                          f"{x['usd']:.4f} → {y['usd']:.4f}")
    return zeilen


def bewertungen(markdown: str) -> dict:
    from collections import Counter

    ergebnis: dict[str, Counter] = {}
    for abschnitt in re.split(r"\n(?=## )", markdown):
        kopf = re.match(r"## (\S+) · Lauf \d+", abschnitt)
        if not kopf or "**Bewertung:**" not in abschnitt:
            continue
        unten = abschnitt.rsplit("**Bewertung:**", 1)[1]
        kreuze = re.findall(r"^- \[[xX]\] (" + "|".join(BEWERTUNGEN) + r")\s*$", unten, re.M)
        wert = kreuze[0] if len(kreuze) == 1 else "offen" if not kreuze else "mehrdeutig"
        ergebnis.setdefault(kopf.group(1), Counter())[wert] += 1
    return ergebnis


# ── Datenbank ────────────────────────────────────────────────────────────────


def verbindung():
    import psycopg2

    from app.config import settings

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


def termine_der_welt(welt: dict) -> tuple[list[tuple[date, int, int]], int]:
    """(Termine ab der nächsten Unterrichtswoche, Zahl der Wochen davor im Schuljahr)."""
    from app.budget.schulwochen import unterrichtswochen
    from app.planning.calendar import is_schoolday, load_school_year

    cfg = load_school_year()
    heute = date.today()
    wochen = unterrichtswochen(cfg)
    naechste = [w for w in wochen if w.montag > heute - timedelta(days=heute.weekday())]
    if len(naechste) < welt["wochen"]:
        raise SystemExit(f"Nur noch {len(naechste)} Unterrichtswochen im Schuljahr — zu wenige.")
    liste = []
    for w in naechste[:welt["wochen"]]:
        for t in welt["termine"]:
            tag = w.montag + timedelta(days=t["wochentag"])
            if is_schoolday(tag, cfg):
                liste.append((tag, t["start"], t["stunden"]))
    return liste, naechste[0].index - 1


def abbauen(conn, welt: dict, *, fach_auch: bool = False) -> None:
    """Gruppe samt Konversationen und Einheiten, Mess-Knoten des Messfachs; auf Wunsch das Fach."""
    g = welt["gruppe"]
    name = _eins(conn, "SELECT name FROM groups WHERE id = %s", g["id"])
    if name is not None and name != g["name"]:
        raise SystemExit(f"Gruppe {g['id']} heißt „{name}“, nicht „{g['name']}“ — fremde Gruppe, Abbruch.")
    fach = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", welt["fach"]["slug"])
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE group_id = %s", (g["id"],))
        cur.execute("DELETE FROM context_nodes WHERE write_scope_group_id = %s OR read_scope_group_id = %s",
                    (g["id"], g["id"]))
        cur.execute("DELETE FROM groups WHERE id = %s", (g["id"],))
        if fach is not None:
            cur.execute("DELETE FROM context_nodes WHERE subject_id = %s AND metadata->>'messung' = 'true'", (fach,))
            if fach_auch:
                cur.execute("DELETE FROM subjects WHERE id = %s", (fach,))


async def _knoten_anlegen(welt: dict, fach: int, pseudonym: str, plan_status: str | None,
                          vergangene_wochen: int) -> list[str]:
    """Curriculum mit Kapiteln und (außer `plan_status=None`) den Jahresverlaufsplan — über das ORM."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.context import verlaufsplan as vp
    from app.db.models import ContextEdge, ContextNode

    stufe, cur_def = welt["stufe"], welt["curriculum"]
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            gemeinsam = dict(subject_id=fach, read_scope="school", write_scope="private",
                             owner_pseudonym=pseudonym, status="active")
            cur = ContextNode(category="knowledge", content_type="curriculum", title=f"{welt['fach']['name']} Kl. {stufe}",
                              min_grade=stufe, max_grade=stufe, **gemeinsam,
                              metadata_={"messung": True, "jahrgangsstufe": str(stufe),
                                         "rahmen": {"wochenstunden": {str(stufe): cur_def["wochenstunden"]}}})
            db.add(cur)
            await db.flush()
            kapitel = []
            for i, k in enumerate(cur_def["kapitel"]):
                node = ContextNode(category="knowledge", content_type="kapitel", title=k["titel"], **gemeinsam,
                                   metadata_={"messung": True, "std": k["std"], "reihenfolge": i})
                db.add(node)
                await db.flush()
                db.add(ContextEdge(from_node_id=node.id, to_node_id=cur.id, relation="part_of"))
                kapitel.append(str(node.id))
            if plan_status:
                db.add(ContextNode(
                    category="knowledge", content_type=vp.TYP, title=f"Jahresverlaufsplan Messung Kl. {stufe}",
                    min_grade=stufe, max_grade=stufe,
                    **{**gemeinsam, "status": plan_status},
                    metadata_={"messung": True, "schuljahr": vp.aktuelles_schuljahr(), "planungsart": vp.KAPITEL,
                               "abschnitte": plan_abschnitte(welt, vergangene_wochen, kapitel),
                               **({"beschlossen_am": date.today().isoformat()} if plan_status == "active" else {})}))
            await db.commit()
            return kapitel
    finally:
        await engine.dispose()


def aufbauen(conn, client, welt: dict, fall: dict, pseudonym: str) -> dict:
    """Die Welt eines Laufs; gibt den Ausgangsstand zurück (mit `reihe` = Termin-IDs nach Datum)."""
    from app.planning.calendar import halbjahr_of

    abbauen(conn, welt)
    f, g = welt["fach"], welt["gruppe"]
    fach = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", f["slug"])
    if fach is None:
        fach = _eins(conn, "INSERT INTO subjects (slug, name, sort_order) VALUES (%s, %s, 999) RETURNING id",
                     f["slug"], f["name"])
    termine, vergangen = termine_der_welt(welt)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id, jahrgang) "
                    "VALUES (%s, %s, %s, 'teaching_group', %s, %s)",
                    (g["id"], g["name"], f"messung-jahresplan-{g['id']}", fach, welt["stufe"]))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen')", (g["id"], pseudonym))
        for tag, start, stunden in termine:
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr) "
                        "VALUES (%s, %s, %s, %s, %s)", (g["id"], tag, start, stunden, halbjahr_of(tag)))
    status = {"keiner": None, "entwurf": "draft"}.get(fall.get("plan"), welt["plan"]["status"])
    kapitel = asyncio.run(_knoten_anlegen(welt, fach, pseudonym, status, vergangen))
    for i, e in enumerate(fall.get("einheiten") or []):
        r = client.post(f"/planning/groups/{g['id']}/units",
                        json={"titel": e["titel"], "farbe": i, "kapitel_node_id": kapitel[e["kapitel"] - 1]})
        if r.status_code >= 300:
            raise SystemExit(f"Aufbau: Einheit → {r.status_code} {r.text[:300]}")
    ausgang = stand(conn, g["id"])
    ausgang["reihe"] = [s for s, _ in sorted(ausgang["termine"].items(), key=lambda x: x[1]["datum"])]
    ausgang["daten"] = [ausgang["termine"][s]["datum"] for s in ausgang["reihe"]]
    return ausgang


def stand(conn, gid: int) -> dict:
    einheiten = [{"id": i, "titel": t, "kapitel": k, "lauf": l} for i, t, k, l in _alle(conn, """
        SELECT u.id::text, u.title,
               (SELECT e.to_node_id::text FROM context_edges e JOIN context_nodes k ON k.id = e.to_node_id
                 WHERE e.from_node_id = u.id AND e.relation = 'references' AND k.content_type = 'kapitel' LIMIT 1),
               u.metadata->'aus_verlaufsplan'->>'lauf_id'
        FROM context_nodes u
        WHERE u.content_type = 'unterrichtseinheit' AND u.write_scope_group_id = %s AND u.status = 'active'
        ORDER BY u.title, u.id""", gid)]
    termine = {s: {"datum": d, "ue": u, "kategorie": k, "thema": t} for s, d, u, k, t in _alle(
        conn, "SELECT id::text, date, ue_node_id::text, kategorie, thema FROM lesson_slots WHERE group_id = %s", gid)}
    return {"einheiten": einheiten, "termine": termine,
            "snapshots": _eins(conn, "SELECT count(*) FROM slot_plan_snapshots WHERE group_id = %s", gid)}


def prompt_lesen(cfg: dict, rev: str | None) -> tuple[str, str]:
    """(Prompt, Stand) — aus der Datei oder aus einem Commit (Arm A)."""
    rel = cfg["prompt"]
    if rev:
        text = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{rel}"], capture_output=True, text=True,
                              check=True).stdout
        return text.strip(), f"{rev} (git show)"
    datei = REPO / rel
    inhalt = hashlib.sha256(datei.read_bytes()).hexdigest()[:10]
    status = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", rel],
                            capture_output=True, text=True).stdout.strip()
    letzter = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%h %cs", "--", rel],
                             capture_output=True, text=True).stdout.strip()
    return datei.read_text(encoding="utf-8").strip(), (letzter if not status else
                                                       f"{letzter} + uncommittete Änderungen (sha256 `{inhalt}`)")


def mess_assistent(conn, cfg: dict, prompt: str, modell: str) -> int:
    vorlage = _alle(conn, "SELECT description, tool_groups::text, produces::text FROM assistants WHERE name = %s",
                    cfg["vorlage"])
    if not vorlage:
        raise SystemExit(f"Assistent „{cfg['vorlage']}“ fehlt — erst seeden (scripts/seed_assistants.py).")
    beschreibung, faehigkeiten, produkte = vorlage[0]
    werte = {"name": cfg["name"], "beschreibung": beschreibung, "prompt": prompt, "modell": modell,
             "faehigkeiten": faehigkeiten, "produkte": produkte}
    kennung = _eins(conn, "SELECT id FROM assistants WHERE name = %s", cfg["name"])
    with conn.cursor() as cur:
        if kennung is None:
            cur.execute(
                "INSERT INTO assistants (name, description, system_prompt, model, audience, scope, status, "
                "visibility, tool_groups, produces, tags, created_by, creator_role, created_at, updated_at) VALUES "
                "(%(name)s, %(beschreibung)s, %(prompt)s, %(modell)s, 'teacher', 'teachers', 'active', 'public', "
                "%(faehigkeiten)s::jsonb, %(produkte)s::jsonb, '{}'::text[], '__messung__', 'admin', now(), now()) "
                "RETURNING id", werte)
            kennung = cur.fetchone()[0]
        else:
            cur.execute(
                "UPDATE assistants SET description = %(beschreibung)s, system_prompt = %(prompt)s, model = %(modell)s, "
                "status = 'active', tool_groups = %(faehigkeiten)s::jsonb, produces = %(produkte)s::jsonb, "
                "updated_at = now() WHERE id = %(id)s", werte | {"id": kennung})
    return kennung


def kosten_der_zuege(conn, konversation: str, warten_s: float = 60.0) -> list[dict]:
    ende = time.monotonic() + warten_s
    while True:
        zeilen = _alle(conn, "SELECT tokens_input, tokens_output, cost_usd, cost_status FROM messages "
                             "WHERE conversation_id = %s AND role = 'assistant' ORDER BY created_at", konversation)
        if not any(z[3] == "ausstehend" for z in zeilen) or time.monotonic() > ende:
            break
        time.sleep(2)
    return [{"ein": z[0] or 0, "aus": z[1] or 0, "usd": round(float(z[2] or 0), 4)} for z in zeilen]


def _chat_probe():
    spec = importlib.util.spec_from_file_location("chat_probe", HIER / "chat_probe.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def lauf(client, conn, fall: dict, assistent: int, gid: int, modell: str, daten: list[date]):
    probe = _chat_probe()
    verlauf, konversation, zuege = [], None, []
    vorher = stand(conn, gid)
    for d in fall["zuege"]:
        text = platzhalter(d["text"], daten)
        zug = probe.frage_stellen(client, text, assistent=assistent, gruppe=gid, verlauf=verlauf,
                                  konversation=konversation, modell=modell)
        konversation = zug["konversation"]
        verlauf += [{"role": "user", "content": text}, {"role": "assistant", "content": zug["antwort"]}]
        zug["frage"] = text
        zug["namen"] = [w.get("tool") for w in zug["werkzeuge"]]
        zug["vorher"], zug["stand"] = vorher, stand(conn, gid)
        vorher = zug["stand"]
        zug["zeit"] = datetime.now().strftime("%H:%M:%S")
        zuege.append(zug)
    return zuege, konversation


# ── Verlauf (Markdown) ───────────────────────────────────────────────────────


def _einheiten_text(s: dict) -> str:
    if not s["einheiten"]:
        return "*(keine Einheiten)*"
    return "\n".join(f"- {x['titel']}{' *(aus dem Plan)*' if x['lauf'] else ''} — "
                     f"{sum(1 for v in s['termine'].values() if v['ue'] == x['id'])} Termine" for x in s["einheiten"])


def verlauf_als_markdown(kopf: dict, laeufe: list[dict]) -> str:
    zeilen = [f"# Messung Jahresplanung — {kopf['beginn']}", "",
              f"Modell `{kopf['modell']}` · Assistent „{kopf['assistent_name']}“ (id {kopf['assistent']}) · "
              f"Prompt `{kopf['prompt']}` · Datei `{kopf['datei']}`  ",
              "Je Lauf eine eigene Welt (Messfach, Curriculum, Plan, Gruppe, Termine ab der nächsten Unterrichtswoche).", ""]
    for l in laeufe:
        zeilen += ["---", "", f"## {l['fall']} · Lauf {l['lauf']} · {'✓' if l['bestanden'] else '✗'}", "",
                   "Kriterien: " + " · ".join(f"{n} {'✓' if ok else '✗'}" for n, ok in l["kriterien"].items())]
        if l.get("berichtet"):
            zeilen.append("Berichtet: " + " · ".join(f"{n}: {v}" for n, v in l["berichtet"].items()))
        if l.get("kosten_je_zug"):
            zeilen.append("Kosten je Zug: " + " · ".join(f"{c['ein']} ein / {c['aus']} aus / {c['usd']} $"
                                                         for c in l["kosten_je_zug"]))
        zeilen.append("")
        for z in l["zuege"]:
            zeilen += [f"**Lehrkraft** ({z['zeit']}): {z['frage']}", "",
                       f"*Funktionen:* {' → '.join(z['namen']) or '—'}", ""]
            if z.get("fehler"):
                zeilen += [f"> [!failure] Abbruch\n> {z['fehler']}", ""]
            zeilen += ["> [!quote] Assistent\n" + "\n".join(f"> {x}" for x in (z["antwort"] or "*(leer)*").splitlines()), ""]
        if l.get("ende"):
            zeilen += ["**Einheiten am Ende:**", "", _einheiten_text(l["ende"]), ""]
        if l.get("erwartung"):
            zeilen += ["> [!example] Erwartung", f"> {l['erwartung'].strip()}", "", "**Bewertung:**", ""]
            zeilen += [f"- [ ] {b}" for b in BEWERTUNGEN] + ["", "Notiz: ", ""]
    return "\n".join(zeilen) + "\n"


# ── Selbsttest ───────────────────────────────────────────────────────────────


def selbsttest(daten: dict, conn) -> bool:
    import app.planning.assistant_tools  # noqa: F401 — registriert die Funktionen
    from app.chat.tools import TOOL_REGISTRY

    gut = True

    def pruefe(bedingung: bool, text: str):
        nonlocal gut
        print(f"  {'✓' if bedingung else '✗'} {text}")
        gut &= bool(bedingung)

    print("Instrument:")
    pruefe(platzhalter("am {termin:2}", [date(2026, 11, 30), date(2026, 12, 3)]) == "am Do, 03.12.", "Platzhalter")
    pruefe(plan_abschnitte({"plan": {"abschnitte": [{"titel": "P", "wochen": 1, "puffer": True}]}}, 9, [])[0]["wochen"] == 9,
           "Rückblick über die vergangenen Wochen")
    pruefe(set(FUNKTIONEN) <= set(TOOL_REGISTRY), "Funktionsnamen registriert")

    print("Szenariodatei:")
    welt = daten["welt"]
    try:
        termine, vergangen = termine_der_welt(welt)
        pruefe(len(termine) >= 2 * welt["wochen"] - 6, f"{len(termine)} Termine ab {termine[0][0]:%d.%m.}, "
                                                        f"{vergangen} Wochen davor")
    except SystemExit as e:
        pruefe(False, str(e))
        termine = []
    fremd = _eins(conn, "SELECT name FROM groups WHERE id = %s", welt["gruppe"]["id"])
    pruefe(fremd in (None, welt["gruppe"]["name"]), f"Gruppen-ID {welt['gruppe']['id']} frei")
    pruefe(bool(_eins(conn, "SELECT 1 FROM assistants WHERE name = %s", daten["assistent"]["vorlage"])),
           f"Vorlage „{daten['assistent']['vorlage']}“ (geseedet)")
    pruefe((REPO / daten["assistent"]["prompt"]).exists(), "Promptdatei")
    pruefe(bool(_eins(conn, "SELECT 1 FROM group_memberships WHERE group_id = %s AND role_in_group = 'teacher'",
                      daten["lehrkraft_der_gruppe"])), "Mess-Lehrkraft")
    n_kap = len(welt["curriculum"]["kapitel"])
    for fall in daten["faelle"]:
        namen = {n for d in fall["zuege"] for f in ("muss", "nicht") for n in d.get(f) or []}
        nummern = [int(x) for d in fall["zuege"] for x in re.findall(r"\{termin:(\d+)\}", d["text"])]
        nummern += [fall["ende"]["kategorie"]["termin"]] if (fall.get("ende") or {}).get("kategorie") else []
        pruefe(namen <= set(TOOL_REGISTRY) and all(1 <= n <= len(termine) for n in nummern)
               and all(1 <= e["kapitel"] <= n_kap for e in fall.get("einheiten") or [])
               and fall.get("plan", "beschlossen") in ("beschlossen", "entwurf", "keiner"), f"Fall {fall['id']}")
    return gut


# ── Ablauf ───────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Messung Jahresplan-Assistent und Jahresverlaufsplan (0.61)")
    p.add_argument("--datei", type=Path, default=DATEI)
    p.add_argument("--modell", default="chat-komplex")
    p.add_argument("--prompt-rev", default=None, help="Prompt aus diesem Commit (Arm A)")
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--verlauf", type=Path, default=None)
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--selbsttest", action="store_true", help="Instrument und Szenariodatei prüfen, ohne Schreiben")
    p.add_argument("--trocken", action="store_true", help="Welt je Fall aufbauen, zeigen, abbauen — ohne Modell")
    p.add_argument("--bewertung", type=Path, default=None, help="Kästchen eines Verlaufs auszählen")
    p.add_argument("--vergleich", nargs=2, type=Path, default=None, metavar=("A.json", "B.json"))
    p.add_argument("--trotzdem", action="store_true", help="auch ohne vollständige Vektoren")
    args = p.parse_args()

    if args.bewertung:
        for fall, z in bewertungen(args.bewertung.read_text(encoding="utf-8")).items():
            print(f"{fall:<22} " + "  ".join(f"{s} {z.get(s, 0)}" for s in (*BEWERTUNGEN, "offen", "mehrdeutig")))
        return
    if args.vergleich:
        a, b = (json.loads(x.read_text(encoding="utf-8")) for x in args.vergleich)
        print("\n".join(vergleich(a, b)))
        return

    import httpx

    from app.auth.dependencies import get_jwt_service
    from app.config import settings
    from app.context.embedding import vor_einer_messung

    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")
    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    conn = verbindung()
    if args.selbsttest:
        ok = selbsttest(daten, conn)
        conn.close()
        raise SystemExit(0 if ok else 1)

    welt = daten["welt"]
    pseudonym = _eins(conn, "SELECT pseudonym FROM group_memberships WHERE group_id = %s "
                            "AND role_in_group = 'teacher' LIMIT 1", daten["lehrkraft_der_gruppe"])
    if pseudonym is None:
        raise SystemExit("Keine Mess-Lehrkraft — falsche Instanz?")
    faelle = [f for f in daten["faelle"] if not args.nur or f["id"] in args.nur]
    token, _ = get_jwt_service().issue(pseudonym=pseudonym, roles=["teacher"], grade=None)
    client = httpx.Client(base_url=args.basis, timeout=300.0, headers={"Cookie": f"session={token}"})

    if args.trocken:
        try:
            for fall in faelle:
                ausgang = aufbauen(conn, client, welt, fall, pseudonym)
                print(f"\n## {fall['id']} — Plan {fall.get('plan', welt['plan']['status'])}, "
                      f"{len(ausgang['reihe'])} Termine ab {ausgang['daten'][0]:%d.%m.}, Snapshots {ausgang['snapshots']}")
                print(_einheiten_text(ausgang))
                # Die Vorschau, wie der Assistent sie bekäme — stimmt die Welt für den Fall?
                r = client.get(f"/planning/groups/{welt['gruppe']['id']}/verlaufsplan/vorschau")
                if r.status_code == 200:
                    v = r.json()
                    print(f"   Vorschau ({v['status']}): neu {v['neu']}, {v['stunden']} Stunden — "
                          + "; ".join(f"{x['nr']}. {x['titel']} {'→ neu, ' + str(x['stunden']) + ' Std.' if x['anlegen'] else '(' + str(x['grund']) + ')'}"
                                      for x in v["vorschlaege"]))
                else:
                    print(f"   Vorschau: {r.status_code} {r.json().get('detail')}")
                for z in fall["zuege"]:
                    print(f"   Lehrkraft: {platzhalter(z['text'], ausgang['daten'])}")
        finally:
            abbauen(conn, welt, fach_auch=True)
            client.close()
            conn.close()
        return

    asyncio.run(vor_einer_messung(trotzdem=args.trotzdem))
    prompt, prompt_stand = prompt_lesen(daten["assistent"], args.prompt_rev)
    assistent = mess_assistent(conn, daten["assistent"], prompt, args.modell)
    beginn = _eins(conn, "SELECT now()")
    kopf = {"datei": args.datei.name, "beginn": datetime.now().strftime("%d.%m.%Y, %H:%M"), "modell": args.modell,
            "assistent": assistent, "assistent_name": daten["assistent"]["name"], "prompt": prompt_stand}
    laeufe = []
    try:
        for fall in faelle:
            for nr in range(1, args.laeufe + 1):
                ausgang = aufbauen(conn, client, welt, fall, pseudonym)
                konversation = None
                try:
                    zuege, konversation = lauf(client, conn, fall, assistent, welt["gruppe"]["id"], args.modell,
                                               ausgang["daten"])
                except (httpx.HTTPError, SystemExit) as fehler:
                    print(f"{fall['id']:<22} Lauf {nr}  ✗  abgebrochen — {type(fehler).__name__}: {str(fehler)[:200]}",
                          flush=True)
                    zuege = []
                kriterien, berichtet = bewerte(fall, zuege, ausgang) if zuege else ({"abgebrochen": False}, {})
                kosten = kosten_der_zuege(conn, konversation) if konversation else []
                bestanden = all(kriterien.values())
                fehlt = ", ".join(n for n, ok in kriterien.items() if not ok)
                print(f"{fall['id']:<22} Lauf {nr}  {'✓' if bestanden else '✗'}  "
                      f"[{' | '.join(' → '.join(z['namen']) or '—' for z in zuege)}]"
                      f"{'  fehlt: ' + fehlt if fehlt else ''}  ({sum(c['usd'] for c in kosten):.4f} $)", flush=True)
                laeufe.append({
                    "fall": fall["id"], "lauf": nr, "bestanden": bestanden, "kriterien": kriterien,
                    "berichtet": berichtet, "kosten_je_zug": kosten, "erwartung": fall.get("erwartung"),
                    "ende": zuege[-1]["stand"] if zuege else None, "prompt": prompt_stand, "modell": args.modell,
                    "zuege": [{"frage": z["frage"], "namen": z["namen"], "antwort": z["antwort"], "zeit": z["zeit"],
                               "fehler": z.get("fehler")} for z in zuege],
                })
                abbauen(conn, welt)
                if args.verlauf:
                    args.verlauf.write_text(verlauf_als_markdown(kopf, laeufe), encoding="utf-8")
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE pseudonym = %s AND assistant_id = %s AND created_at >= %s",
                        (pseudonym, assistent, beginn))
            cur.execute("UPDATE assistants SET status = 'disabled' WHERE id = %s", (assistent,))
        abbauen(conn, welt, fach_auch=True)
        client.close()
        conn.close()

    print("\nFall                   bestanden  nicht erfüllt")
    for fall in faelle:
        eigene = [l for l in laeufe if l["fall"] == fall["id"]]
        offen = sorted({n for l in eigene for n, ok in l["kriterien"].items() if not ok})
        print(f"{fall['id']:<22} {sum(l['bestanden'] for l in eigene)}/{len(eigene)}        {', '.join(offen) or '—'}")
    print(f"\nKosten gesamt: {sum(c['usd'] for l in laeufe for c in l['kosten_je_zug']):.4f} $")
    if args.json:
        args.json.write_text(json.dumps(laeufe, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
