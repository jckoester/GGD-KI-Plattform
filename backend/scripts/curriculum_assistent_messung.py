#!/usr/bin/env python3
"""Messung des Curriculum-Assistenten (0.46, Päckchen AP Teil B, Schritt 7).

    python scripts/curriculum_assistent_messung.py --datei scripts/szenarien/curriculum_assistent.yaml --selbsttest
    python scripts/curriculum_assistent_messung.py --datei scripts/szenarien/curriculum_assistent.yaml \\
        --modell chat-komplex --laeufe 3 --verlauf lauf1-komplex.md --json lauf1-komplex.json
    python scripts/curriculum_assistent_messung.py --bewertung lauf1-komplex.md

**Der Assistent** heißt „Curriculum-Entwurf (Messung)“: Beschreibung, Fähigkeit und Marke wie
der geseedete „Curriculum-Entwurf“, Prompt aus der Promptdatei im Repo, Modell aus `--modell`.
Er wird angelegt oder auf diesen Stand gebracht und nach der Messung abgeschaltet (`disabled`);
der geseedete bleibt unberührt.

**Je Lauf ein eigenes Curriculum.** Das Skript legt es aus der Vorlage des Falls an — über die
Funktionen des Assistenten selbst (`curriculum_neu`, `rahmen_setzen`, `operationen_anwenden`),
als Mess-Lehrkraft, die dafür vorübergehend in die Fachschaft des Fachs aufgenommen wird —,
löscht die dabei entstandenen Stände des Verlaufs und spielt die Züge in einer neuen
Konversation. Danach werden das Curriculum, Kopien davon und die Konversation gelöscht; am Ende
auch die vorübergehende Mitgliedschaft. Mess-Curricula tragen `metadata.messung`; ein
abgebrochener Lauf wird beim nächsten Start aufgeräumt.

**Was der Strom nicht zeigt:** `tool_status` trägt nur Namen. Argumente und Ergebnisse der
Curriculum-Funktionen kommen über den Messkanal `vorab_debug` (Feld `curriculum`, nur außerhalb
der Produktion). Daran hängen „Prüflauf vor Schreiben“, „frisch gelesen“, „keine alten
Nummern“ und „Stunden belegt“.

**Kriterien** (siehe Kopf der Szenariodatei): je Zug Aufrufe, Antwort, Inhalt und Rahmen; je
Lauf die automatischen Kriterien und `ende`. Ein Lauf ist bestanden, wenn alle zutreffenden
Kriterien erfüllt sind. Ob die Antwort taugt, beurteilt Jan im Verlauf (Kästchen unter jedem
Lauf, `--bewertung` zählt aus).

⚠️ Nur für Entwicklungsinstanzen — eigener Sitzungs-Token, echte Modellaufrufe auf Kosten des
Budgets der Mess-Lehrkraft, schreibt vorübergehend in die Datenbank.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.auth.jwt import JwtPayload
from app.config import settings

HIER = Path(__file__).resolve().parent
REPO = HIER.parent.parent


def _modul(name: str):
    # `scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden.
    spec = importlib.util.spec_from_file_location(name, HIER / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


chat_probe = _modul("chat_probe")

FUNKTIONEN = (
    "get_curriculum_draft", "get_bp_competences", "get_curriculum_coverage", "get_hour_frame",
    "preview_curriculum_operations", "apply_curriculum_operations", "set_curriculum_frame",
    "undo_last_curriculum_change", "finde_curriculum", "waehle_curriculum", "lege_curriculum_an",
    # 0.65 (AY Teil 2 C): Absprachen mit anderen Fächern
    "get_subject_chapters", "get_cross_subject_references",
)
LESEN = {"get_curriculum_draft", "waehle_curriculum", "lege_curriculum_an"}
BEWERTUNGEN = ("brauchbar", "teilweise", "unbrauchbar")
GLEICH, GEAENDERT = "gleich", "geaendert"

#: Eine Kompetenznummer im Text: „3.1.7(3)“, „2.1(4)“, auch „3.1.7 (3)“.
NUMMER = re.compile(r"\b\d(?:\.\d+){1,3}\s?\(\d+\)")
#: Eine Stundenzahl im Text. „Wochenstunden“ trifft nicht (kein Wortanfang vor „Stunden“).
STUNDEN = re.compile(r"(?<![\d.,])(\d+(?:,5)?)\s*(?:Std\b\.?|Stunden\b|Unterrichtsstunden\b)")
#: Eine Frage nach Zustimmung im Text („Soll ich das so anlegen?“, „Passt das?“).
ZUSTIMMUNGSFRAGE = re.compile(r"\b(soll ich|passt (das|dies|der|die|es|so)|einverstanden)\b[^?\n]*"
                              r"\b(anlegen|übernehmen|schreiben|löschen|eintragen|ergänzen|umsetzen|prüfen|erstellen|machen|berechnen|so)\b[^?\n]*\?"
                              r"|\bso (anlegen|übernehmen|schreiben|löschen)\?", re.I)
#: Ein gezeigter Vorschlag: Tabelle oder Liste.
VORSCHLAG = re.compile(r"^\s*(\||[-*]\s|\d+\.\s)", re.M)
#: Feldnamen der Funktionsantworten im Text (0.65) — „`absprachen`“, „behandelt_in“.
FELDNAMEN = re.compile(r"\b(behandelt_in|von_anderen_faechern|eingetragen_in|ziel_kapitel_id|absprachen_an_das_fach)\b"
                       r"|`absprachen`")
KENNUNG = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


# ── Datenbank ────────────────────────────────────────────────────────────────


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


def fach_id(conn, cfg: dict) -> int:
    kennung = _eins(conn, "SELECT id FROM subjects WHERE name = %s OR slug = %s", cfg["fach"], cfg["fach"])
    if kennung is None:
        raise SystemExit(f"Fach „{cfg['fach']}“ gibt es nicht — falsche Instanz?")
    return kennung


def band_nummern(conn, fach: int, cfg: dict) -> set[str]:
    """IK des Bands und PK der Fassung — Nummern ohne Leerzeichen."""
    stufen = [int(s) for s in re.findall(r"\d+", cfg["jahrgangsstufe"])]
    lo, hi = min(stufen), max(stufen)
    zeilen = _alle(conn, """
        SELECT metadata->>'kompetenz_nr' FROM context_nodes
        WHERE subject_id = %s AND bp_version = %s AND status IN ('active', 'upcoming')
          AND ((content_type = 'ik_kompetenz' AND min_grade <= %s AND max_grade >= %s)
               OR content_type = 'pk_kompetenz')""", fach, cfg["bp_version"], hi, lo)
    return {_norm(n) for (n,) in zeilen if n}


def _norm(nr: str) -> str:
    return re.sub(r"\s+", "", nr)


def baum(conn, cid: str) -> dict:
    """Rahmen und Gliederung des Curriculums: Kapitel → Lernsequenzen (Titel, Stunden, Einträge)."""
    meta = _eins(conn, "SELECT metadata FROM context_nodes WHERE id = %s", cid) or {}
    kapitel = []
    for kid, titel, km in _alle(conn, """
            SELECT k.id::text, k.title, k.metadata FROM context_nodes k
            JOIN context_edges e ON e.from_node_id = k.id AND e.relation = 'part_of'
            WHERE e.to_node_id = %s AND k.content_type = 'kapitel'
            ORDER BY (k.metadata->>'reihenfolge')::int NULLS LAST, k.title""", cid):
        lss = [{"titel": t, "std": (m or {}).get("std"), "eintraege": (m or {}).get("eintraege") or []}
               for _, t, m in _alle(conn, """
                SELECT l.id::text, l.title, l.metadata FROM context_nodes l
                JOIN context_edges e ON e.from_node_id = l.id AND e.relation = 'part_of'
                WHERE e.to_node_id = %s AND l.content_type = 'lernsequenz'
                ORDER BY (l.metadata->>'reihenfolge')::int NULLS LAST, l.title""", kid)]
        kapitel.append({"titel": titel, "einleitung": (km or {}).get("einleitung") or "", "lernsequenzen": lss,
                        # 0.65: Absprachen mit anderen Fächern — Fach, Ziel-Kapitel, Art, Text
                        "absprachen": [{"fach": a.get("fach_code"), "ziel": a.get("kapitel_titel"),
                                        "art": a.get("art"), "text": a.get("text") or ""}
                                       for a in (km or {}).get("absprachen") or []]})
    return {"rahmen": meta.get("rahmen") or {}, "kapitel": kapitel}


def mitglied_aufnehmen(conn, fach: int, pseudonym: str) -> int | None:
    """Mitgliedschaft in der Fachschaft, falls nötig — die Gruppe, wenn sie neu ist."""
    gruppe = _eins(conn, "SELECT id FROM groups WHERE type = 'subject_department' AND subject_id = %s "
                         "ORDER BY id LIMIT 1", fach)
    if gruppe is None:
        return None  # ohne Fachschaft prüft `curriculum_anlegen` nicht
    if _eins(conn, "SELECT 1 FROM group_memberships WHERE group_id = %s AND pseudonym = %s", gruppe, pseudonym):
        return None
    with conn.cursor() as cur:
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen')", (gruppe, pseudonym))
    return gruppe


def mitglied_entfernen(conn, gruppe: int | None, pseudonym: str) -> None:
    if gruppe is not None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM group_memberships WHERE group_id = %s AND pseudonym = %s", (gruppe, pseudonym))


def mess_curricula(conn, fach: int, pseudonym: str, seit=None) -> list[str]:
    """Mess-Curricula (`metadata.messung`) und — ab ``seit`` — von der Mess-Lehrkraft angelegte
    Curricula des Fachs (Kopien, `lege_curriculum_an`)."""
    ids = {i for (i,) in _alle(conn, "SELECT id::text FROM context_nodes WHERE content_type = 'curriculum' "
                                     "AND metadata->>'messung' = 'true'")}
    if seit is not None:
        ids |= {i for (i,) in _alle(conn, "SELECT id::text FROM context_nodes WHERE content_type = 'curriculum' "
                                          "AND subject_id = %s AND owner_pseudonym = %s AND created_at >= %s",
                                    fach, pseudonym, seit)}
    return sorted(ids)


def curricula_loeschen(conn, ids: list[str]) -> None:
    """Curriculum, Kapitel, Lernsequenzen — Kanten und Stände folgen per CASCADE."""
    if not ids:
        return
    with conn.cursor() as cur:
        cur.execute("""
            WITH k AS (SELECT n.id FROM context_edges e JOIN context_nodes n ON n.id = e.from_node_id
                       WHERE e.to_node_id::text = ANY(%s) AND e.relation = 'part_of' AND n.content_type = 'kapitel'),
                 l AS (SELECT n.id FROM context_edges e JOIN context_nodes n ON n.id = e.from_node_id
                       WHERE e.to_node_id IN (SELECT id FROM k) AND e.relation = 'part_of'
                         AND n.content_type = 'lernsequenz')
            DELETE FROM context_nodes WHERE id IN (SELECT id FROM l) OR id IN (SELECT id FROM k)
                OR (id::text = ANY(%s) AND content_type = 'curriculum')""", (ids, ids))


def mess_assistent(conn, cfg: dict, modell: str, prompt_rev: str | None = None) -> tuple[int, str]:
    prompt = (REPO / cfg["prompt"]).read_text(encoding="utf-8").strip()
    if prompt_rev:  # Arm A (0.65): der Prompt aus einer früheren Revision
        import subprocess

        prompt = subprocess.run(["git", "-C", str(REPO), "show", f"{prompt_rev}:{cfg['prompt']}"],
                                capture_output=True, text=True, check=True).stdout.strip()
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
    return kennung, prompt


def assistent_abschalten(conn, kennung: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE assistants SET status = 'disabled' WHERE id = %s", (kennung,))


def prompt_stand(datei: Path) -> str:
    import subprocess

    rel = str(datei.relative_to(REPO))

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout.strip()
    status = git("status", "--porcelain", "--", rel)
    inhalt = hashlib.sha256(datei.read_bytes()).hexdigest()[:10]
    if status.startswith("??"):
        return f"unversioniert (sha256 `{inhalt}`)"
    stand = git("log", "-1", "--format=%h %cs", "--", rel)
    return stand if not status else f"{stand} + uncommittete Änderungen (sha256 `{inhalt}`)"


def kosten(conn, konversation: str, warten_s: float = 60.0) -> dict:
    ende = time.monotonic() + warten_s
    while True:
        zeilen = _alle(conn, "SELECT tokens_input, tokens_output, cost_usd, cost_status FROM messages "
                             "WHERE conversation_id = %s AND role = 'assistant'", konversation)
        if not any(z[3] == "ausstehend" for z in zeilen) or time.monotonic() > ende:
            break
        time.sleep(2)
    return {"ein": sum(z[0] or 0 for z in zeilen), "aus": sum(z[1] or 0 for z in zeilen),
            "usd": round(sum(float(z[2] or 0) for z in zeilen), 4)}


# ── Aufbau des Mess-Curriculums (über die Funktionen des Assistenten) ────────


async def _aufbauen(cfg: dict, vorlage: dict, pseudonym: str) -> str:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.context import curriculum_assistent as ca
    from app.context.curriculum_bezug import curriculum_neu
    from app.context.curriculum_verlauf import baum_ids, sichern
    from app.db.models import ContextNode, CurriculumSnapshot

    user = JwtPayload(sub=pseudonym, roles=["teacher"], role="teacher", grade=None, exp=9999999999, iat=0,
                      jti="messung")
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            cur, antwort = await curriculum_neu(db, user, cfg["fach"], cfg["jahrgangsstufe"], cfg["bp_version"])
            if cur is None:
                raise SystemExit(f"Mess-Curriculum nicht angelegt: {antwort}")
            cur.metadata_ = {**(cur.metadata_ or {}), "messung": True}
            partner = await _partner_aufbauen(db, cfg.get("partner"), pseudonym) if cfg.get("partner") else {}
            if vorlage.get("rahmen"):
                r = await ca.rahmen_setzen(db, user, cur, vorlage["rahmen"])
                if not r.get("ok"):
                    raise SystemExit(f"Vorlage, Rahmen: {r}")
            ops = [*(vorlage.get("operationen") or []), *(vorlage.get("extra_operationen") or [])]
            # Absprachen der Vorlage nennen ihr Ziel über den Titel im Partnerfach (0.65)
            ops = [{**{k: v for k, v in o.items() if k != "ziel_kapitel"},
                    **({"ziel_kapitel_id": partner[o["ziel_kapitel"]]} if o.get("ziel_kapitel") else {})}
                   for o in ops]
            if ops:
                r = await ca.operationen_anwenden(db, user, cur, ops)
                if not r.get("ok"):
                    raise SystemExit(f"Vorlage, Operationen: {r.get('fehler')}")
            if vorlage.get("partner_absprachen"):
                await _partner_absprachen(db, cfg["partner"], partner, cur, vorlage["partner_absprachen"])
            await db.execute(sa.delete(CurriculumSnapshot).where(CurriculumSnapshot.curriculum_id == cur.id))
            if vorlage.get("status"):
                await db.execute(sa.update(ContextNode).where(ContextNode.id.in_(await baum_ids(db, cur.id)))
                                 .values(status=vorlage["status"]))
            if aenderung := vorlage.get("editor_aenderung"):
                await sichern(db, cur.id, grund="editor", von=user.sub)
                entwurf = await ca.entwurf_lesen(db, user, cur)
                kap = await db.get(ContextNode, entwurf["kapitel"][aenderung["kapitel"] - 1]["id"])
                kap.title = aenderung["titel"]
            await db.commit()
            return str(cur.id)
    finally:
        await engine.dispose()


async def _partner_aufbauen(db, p: dict, pseudonym: str) -> dict[str, str]:
    """Ein Curriculum eines zweiten Fachs (0.65): veröffentlicht, `messung`, Kapitel mit je einer
    Lernsequenz; `verknuepft` verknüpft sie mit Kompetenzen des Fachs, auf die der Bildungsplan aus
    dem Messfach verweist — so haben die Querverweise eine Fundstelle. Rückgabe: Titel → Kennung."""
    import uuid as _uuid

    import sqlalchemy as sa

    from app.db.models import ContextEdge, ContextNode, Subject

    fach = (await db.execute(sa.select(Subject).where(sa.or_(Subject.name == p["fach"], Subject.slug == p["fach"])))).scalar_one()
    lo, hi = (int(x) for x in re.findall(r"\d+", p["jahrgangsstufe"])[:2]) if "/" in p["jahrgangsstufe"] else \
        (int(p["jahrgangsstufe"]),) * 2

    def knoten(typ, titel, meta):
        return ContextNode(id=_uuid.uuid4(), category="knowledge", content_type=typ, title=titel, status="active",
                           owner_pseudonym=pseudonym, read_scope="school", write_scope="school",
                           subject_id=fach.id, min_grade=lo, max_grade=hi, metadata_=meta)
    cur = knoten("curriculum", f"{p['fach']} {p['jahrgangsstufe']} (Messung)",
                 {"messung": True, "jahrgangsstufe": p["jahrgangsstufe"], "bp_version": p.get("bp_version"),
                  "fach": fach.name, "fach_code": fach.fach_code})
    db.add(cur)
    await db.flush()
    aus = {}
    for i, k in enumerate(p["kapitel"], 1):
        kap = knoten("kapitel", k["titel"], {"reihenfolge": i})
        ls = knoten("lernsequenz", f"{k['titel']} (Sequenz)", {"reihenfolge": 1, "std": 6, "eintraege": []})
        db.add_all([kap, ls])
        await db.flush()
        db.add_all([ContextEdge(from_node_id=kap.id, to_node_id=cur.id, relation="part_of", metadata_={}),
                    ContextEdge(from_node_id=ls.id, to_node_id=kap.id, relation="part_of", metadata_={})])
        for nr in k.get("verknuepft") or []:
            ziel = (await db.execute(sa.select(ContextNode.id).where(
                ContextNode.subject_id == fach.id, ContextNode.content_type == "ik_kompetenz",
                ContextNode.status == "active", ContextNode.metadata_["kompetenz_nr"].astext == nr)
                .order_by(ContextNode.bp_version.desc()).limit(1))).scalar_one_or_none()
            if ziel is None:
                raise SystemExit(f"Partnerfach: Kompetenz {nr} in {p['fach']} gibt es nicht")
            db.add(ContextEdge(from_node_id=ls.id, to_node_id=ziel, relation="references",
                               metadata_={"partiell": "false"}))
        aus[k["titel"]] = str(kap.id)
    await db.flush()
    return aus


async def _partner_absprachen(db, p: dict, partner: dict[str, str], cur, liste: list[dict]) -> None:
    """Absprachen, die das Partnerfach eingetragen hat (von außen): am Partnerkapitel, Ziel ein
    Kapitel des Mess-Curriculums über den Titel."""
    import uuid as _uuid

    import sqlalchemy as sa

    from app.db.models import ContextEdge, ContextNode, Subject

    titel_id = {t: i for i, t in (await db.execute(
        sa.select(ContextNode.id, ContextNode.title).join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(ContextEdge.to_node_id == cur.id, ContextNode.content_type == "kapitel"))).all()}
    fach_code = await db.scalar(sa.select(Subject.fach_code).where(Subject.id == cur.subject_id))
    for a in liste:
        kap = await db.get(ContextNode, _uuid.UUID(partner[a["kapitel"]]))
        ziel = titel_id[a["ziel"]]
        kap.metadata_ = {**(kap.metadata_ or {}), "absprachen": [*(kap.metadata_ or {}).get("absprachen", []), {
            "id": str(_uuid.uuid4()), "fach_code": fach_code, "kapitel_id": str(ziel), "kapitel_titel": a["ziel"],
            "art": a["art"], "text": a.get("text") or ""}]}
    await db.flush()


def aufbauen(cfg: dict, vorlage: dict, pseudonym: str) -> str:
    return asyncio.run(_aufbauen(cfg, vorlage, pseudonym))


# ── Lauf ─────────────────────────────────────────────────────────────────────


def lauf(client, conn, fall: dict, assistent: int, cid: str, modell: str | None = None) -> tuple[list[dict], str | None]:
    verlauf: list[dict] = []
    konversation = None
    zuege = []
    vorher = baum(conn, cid)
    for nr, zug_def in enumerate(fall["zuege"], 1):
        zug = chat_probe.frage_stellen(
            # ``modell`` ausdrücklich (0.51): Die Mess-Lehrkraft kann ein bevorzugtes Modell für
            # Planungs-Assistenten haben (AV), das sonst den ersten Zug übernähme — gemessen
            # 21.11.2026, lauf7 lief im ersten Zug mit der Vorliebe statt mit `--modell`.
            client, zug_def["text"], assistent=assistent, gruppe=None, verlauf=verlauf, konversation=konversation,
            modell=modell,
            curriculum=cid if nr == 1 and fall.get("bezug", True) else None)
        konversation = zug["konversation"]
        verlauf += [{"role": "user", "content": zug_def["text"]}, {"role": "assistant", "content": zug["antwort"]}]
        zug["namen"] = [w.get("tool") for w in zug["werkzeuge"]]
        zug["aufrufe"] = (zug.get("vorab_debug") or {}).get("curriculum") or []
        if set(zug["namen"]) & set(FUNKTIONEN) and not zug["aufrufe"]:
            print(f"  ⚠️ {fall['id']}, Zug {nr}: Funktionen ohne Messkanal (vorab_debug.curriculum) — "
                  "läuft das Backend mit dem Stand dieses Skripts?", flush=True)
        zug["vorher"], zug["stand"] = vorher, baum(conn, cid)
        vorher = zug["stand"]
        zug["zeit"] = datetime.now().strftime("%H:%M:%S")
        zuege.append(zug)
    return zuege, konversation


# ── Kriterien ────────────────────────────────────────────────────────────────


def _inhalt(b: dict) -> list:
    return b["kapitel"]


def _zahlen(wert) -> set[str]:
    """Alle Zahlen in einem Funktionsergebnis (auch in Texten), als Text ohne „.0“."""
    aus: set[str] = set()
    if isinstance(wert, bool):
        return aus
    if isinstance(wert, (int, float)):
        aus.add(_zahl(wert))
    elif isinstance(wert, str):
        aus |= {_zahl(float(z.replace(",", "."))) for z in re.findall(r"\d+(?:[.,]5)?", wert)}
    elif isinstance(wert, dict):
        for v in wert.values():
            aus |= _zahlen(v)
    elif isinstance(wert, list):
        for v in wert:
            aus |= _zahlen(v)
    return aus


def _zahl(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else str(x).replace(".", ",")


#: Stunden ohne Einheit direkt an der Zahl: Bilanz („verplant: 120“), „120 verplanbare Stunden“,
#: Tabellenkopf mit Stundenspalte.
STUNDEN_GENANNT = re.compile(r"\b(verplant|verplanbar|rest)\b\W{0,6}\d|\d+\s+\w+\s+Stunden\b"
                             r"|^\s*\|.*\b(Std|Stunden)\b.*\|", re.I | re.M)


def stunden_genannt(text: str) -> bool:
    """Nennt der Text Stunden — auch ohne Einheit an der Zahl (Kriterium „Vorschlag geprüft“)."""
    return bool(STUNDEN.search(text) or STUNDEN_GENANNT.search(text))


def stunden_im_text(text: str) -> list[str]:
    return [_zahl(float(z.replace(",", "."))) for z in STUNDEN.findall(text)]


def nummern_im_text(text: str) -> set[str]:
    """Kompetenznummern, auch aus Spannen: „3.2.2(4)–(9)“ → 3.2.2(4) … 3.2.2(9)."""
    aus = {_norm(n) for n in NUMMER.findall(text)}
    for basis, von, bis in re.findall(r"\b(\d(?:\.\d+){1,3})\s?\((\d+)\)\s*[–-]\s*\((\d+)\)", text):
        aus |= {f"{basis}({i})" for i in range(int(von), int(bis) + 1)}
    return aus


def _beruehrt_bestehendes(ops) -> bool:
    return bool(KENNUNG.search(json.dumps(ops or [])))


def bewerte(fall: dict, zuege: list[dict], *, band: set[str], ende: dict) -> tuple[dict[str, bool], dict]:
    k: dict[str, bool] = {}
    berichtet: dict = {}
    for n, (z, d) in enumerate(zip(zuege, fall["zuege"]), 1):
        namen = set(z["namen"])
        if d.get("muss") or d.get("nicht") or d.get("muss_eine"):
            k[f"Z{n} Aufrufe"] = (set(d.get("muss") or []) <= namen and not (set(d.get("nicht") or []) & namen)
                                  and (not d.get("muss_eine") or bool(set(d["muss_eine"]) & namen)))
        # Höchstens so viele Aufrufe einer Funktion (0.51, AV Schritt 9): `hoechstens: {apply…: 1}`
        for tool, n_max in (d.get("hoechstens") or {}).items():
            k[f"Z{n} {tool} höchstens {n_max}×"] = z["namen"].count(tool) <= n_max
        # Aufruf mit bestimmten Argumenten (0.50, AT): `muss_mit: [{tool: …, typ: lp}]`
        for i, soll in enumerate(d.get("muss_mit") or [], 1):
            werte = {f: v for f, v in soll.items() if f != "tool"}
            k[f"Z{n} {soll['tool']} mit {werte}"] = any(
                a["tool"] == soll["tool"] and all((a.get("args") or {}).get(f) == v for f, v in werte.items())
                for a in z["aufrufe"])
        if d.get("antwort") or d.get("antwort_nicht"):
            k[f"Z{n} Antwort"] = (all(re.search(m, z["antwort"], re.I) for m in d.get("antwort") or [])
                                  and not any(re.search(m, z["antwort"], re.I) for m in d.get("antwort_nicht") or []))
        if d.get("inhalt"):
            k[f"Z{n} Inhalt {d['inhalt']}"] = (_inhalt(z["vorher"]) == _inhalt(z["stand"])) == (d["inhalt"] == GLEICH)
        if d.get("rahmen"):
            k[f"Z{n} Rahmen {d['rahmen']}"] = (z["vorher"]["rahmen"] == z["stand"]["rahmen"]) == (d["rahmen"] == GLEICH)
        if z.get("fehler"):
            k[f"Z{n} ohne Abbruch"] = False

    # Prüflauf vor jedem Schreiben; derselbe Stapel nur berichtet.
    geprueft, letzter, ok, gleich = None, None, True, []
    frisch = True
    for z in zuege:
        gelesen = False
        for a in z["aufrufe"]:
            ergebnis = a.get("ergebnis") if isinstance(a.get("ergebnis"), dict) else {}
            if a["tool"] in LESEN and not ergebnis.get("error"):
                gelesen = True
            if a["tool"] == "preview_curriculum_operations":
                geprueft = bool(ergebnis.get("ok"))
                letzter = a["args"].get("operations")
            elif a["tool"] == "apply_curriculum_operations" and ergebnis.get("ok"):
                # Nur ein erfolgreiches Schreiben verbraucht den Prüflauf — ein abgewiesenes
                # schreibt nichts (etwa eine geratene Kennung, danach gelesen und neu geschickt).
                ok &= bool(geprueft)
                gleich.append(not a["args"].get("operations") or a["args"].get("operations") == letzter)
                if _beruehrt_bestehendes(a["args"].get("operations")) and not gelesen:
                    frisch = False
                geprueft = None
    if any(a["tool"] == "apply_curriculum_operations" for z in zuege for a in z["aufrufe"]):
        k["Prüflauf vor Schreiben"] = ok
        k["frisch gelesen"] = frisch
        berichtet["gleicher Stapel"] = f"{sum(gleich)}/{len(gleich)}"

    # Ein gezeigter Vorschlag mit Stunden und Frage nach Zustimmung braucht einen bestandenen
    # Prüflauf im selben Zug.
    ungeprueft = [n for n, z in enumerate(zuege, 1)
                  if ZUSTIMMUNGSFRAGE.search(z["antwort"]) and stunden_genannt(z["antwort"])
                  and VORSCHLAG.search(z["antwort"])
                  and not any(a["tool"] == "preview_curriculum_operations"
                              and (a.get("ergebnis") or {}).get("ok") for a in z["aufrufe"])]
    k["Vorschlag geprüft"] = not ungeprueft
    if ungeprueft:
        berichtet["Vorschlag ohne Prüflauf in Zug"] = ungeprueft

    antworten = "\n".join(z["antwort"] for z in zuege)
    lehrkraft = "\n".join(d["text"] for d in fall["zuege"])
    k["keine Funktionsnamen"] = (not any(f in antworten for f in FUNKTIONEN) and not KENNUNG.search(antworten)
                                 and not FELDNAMEN.search(antworten))
    # Nummern anderer Fächer sind belegt, wenn eine Funktion sie geliefert hat (0.65: Querverweise)
    aus_funktionen = set().union(*(nummern_im_text(json.dumps(a.get("ergebnis"), ensure_ascii=False))
                                   for z in zuege for a in z["aufrufe"]
                                   if a["tool"] in ("get_cross_subject_references", "get_subject_chapters")), set())
    fremd = nummern_im_text(antworten) - band - nummern_im_text(lehrkraft) - aus_funktionen
    k["Nummern aus dem Band"] = not fremd
    if fremd:
        berichtet["fremde Nummern"] = sorted(fremd)

    belegt = {"30"} | _zahlen(lehrkraft)
    unbelegt = []
    for z in zuege:
        for a in z["aufrufe"]:
            belegt |= _zahlen(a.get("ergebnis"))
        unbelegt += [s for s in stunden_im_text(z["antwort"]) if s not in belegt]
    k["Stunden belegt"] = not unbelegt
    if unbelegt:
        berichtet["unbelegte Stunden"] = sorted(set(unbelegt), key=float)

    if fall.get("alte_nummern"):
        alt = nummern_im_text(lehrkraft)
        in_aufrufen = _norm(json.dumps([a["args"] for z in zuege for a in z["aufrufe"]], ensure_ascii=False))
        k["keine alten Nummern"] = not any(n in in_aufrufen for n in alt)

    k.update(ende_pruefen(fall, zuege, ende))
    return k, berichtet


def ende_pruefen(fall: dict, zuege: list[dict], ende: dict) -> dict[str, bool]:
    e = fall.get("ende") or {}
    k: dict[str, bool] = {}
    stand = zuege[-1]["stand"] if zuege else None
    if not stand:
        return k
    titel = [x["titel"] for x in stand["kapitel"]]
    if "rahmen_enthaelt" in e:
        k["Ende Rahmen"] = _teilmenge(e["rahmen_enthaelt"], stand["rahmen"])
    if "kapitel_weg" in e:
        k["Ende Kapitel weg"] = e["kapitel_weg"] not in titel
    for pos, t in (e.get("kapitel_titel") or {}).items():
        k[f"Ende Kapitel {pos}"] = len(titel) >= int(pos) and titel[int(pos) - 1] == t
    if "nur_kapitel" in e:
        vorher = {x["titel"]: x for x in zuege[0]["vorher"]["kapitel"]}
        nachher = {x["titel"]: x for x in stand["kapitel"]}
        k["Ende nur dieses Kapitel"] = all(nachher.get(t) == x for t, x in vorher.items() if t != e["nur_kapitel"]) \
            and set(nachher) == set(vorher)
    if "getauscht" in e:
        a, b = e["getauscht"]
        vorschlag = None
        for x in zuege[0]["aufrufe"]:
            if x["tool"] == "preview_curriculum_operations" and (x.get("ergebnis") or {}).get("ok"):
                vorschlag = [g["titel"] for g in x["ergebnis"]["gliederung"]]
        # Ohne führende Nummer vergleichen: Manche Läufe tragen sie in den Titel („2. Akustik“)
        # und zählen nach dem Tausch richtig weiter („3. Akustik“).
        ohne_nr = [re.sub(r"^\s*\d+\.\s*", "", t) for t in titel]
        vorschlag = [re.sub(r"^\s*\d+\.\s*", "", t) for t in vorschlag or []]
        k["Ende getauscht"] = bool(vorschlag) and len(vorschlag) >= max(a, b) and all(
            t in ohne_nr for t in (vorschlag[a - 1], vorschlag[b - 1])) and \
            ohne_nr.index(vorschlag[b - 1]) < ohne_nr.index(vorschlag[a - 1])
    # Verweise in den Hinweisen (0.50, AT): Leitlinien `lb`/`lba`, Leitperspektiven `lp`/`lpa`.
    hinweise = [x.get("hinweise") or "" for kap in stand["kapitel"] for ls in kap["lernsequenzen"]
                for x in ls["eintraege"] if isinstance(x, dict)]
    alle = "\n".join(hinweise)
    for muster in e.get("hinweise_enthaelt") or []:
        k[f"Ende Hinweise enthalten {muster}"] = bool(re.search(muster, alle))
    for muster in e.get("hinweise_nicht") or []:
        k[f"Ende Hinweise ohne {muster}"] = not re.search(muster, alle)
    if e.get("keine_eintraege"):  # (0.51, AV Schritt 9) Gerüst ohne ungefragt gefüllte Kapitel
        k["Ende keine Einträge"] = not any(ls["eintraege"] for kap in stand["kapitel"]
                                           for ls in kap["lernsequenzen"])
    if (anteil := e.get("hinweise_anteil_max")) is not None:
        muster, grenze = anteil["muster"], anteil["anteil"]
        mit = sum(1 for h in hinweise if re.search(muster, h))
        k[f"Ende höchstens {grenze:.0%} der Einträge mit {muster}"] = bool(hinweise) and mit / len(hinweise) <= grenze
    # Absprachen mit anderen Fächern (0.65): eigene des Mess-Curriculums
    eigene = [(kap["titel"], a) for kap in stand["kapitel"] for a in kap.get("absprachen") or []]
    if "absprachen_anzahl" in e:
        k[f"Ende {e['absprachen_anzahl']} Absprachen"] = len(eigene) == e["absprachen_anzahl"]
    for soll in e.get("absprache_mit") or []:
        k[f"Ende Absprache {soll['kapitel']} ↔ {soll['fach']}" + (f" ({soll['art']})" if soll.get("art") else "")] = any(
            t == soll["kapitel"] and a["fach"] == soll["fach"] and (not soll.get("art") or a["art"] == soll["art"])
            and (not soll.get("ziel") or a["ziel"] == soll["ziel"]) for t, a in eigene)
    if "bezug" in e:
        k["Ende Bezug"] = ende["bezug"] == ende["cid"]
    if "kopie" in e:
        k["Ende Kopie"] = bool(ende["kopien"]) == bool(e["kopie"])
    return k


def _teilmenge(soll, ist) -> bool:
    if isinstance(soll, dict):
        return isinstance(ist, dict) and all(_teilmenge(v, ist.get(str(s))) for s, v in soll.items())
    try:
        return float(soll) == float(ist)
    except (TypeError, ValueError):
        return soll == ist


# ── Verlauf (Markdown) ───────────────────────────────────────────────────────


def _kurz(a: dict) -> str:
    """Ein Aufruf in einer Zeile: Name, Kern der Argumente, Kern des Ergebnisses."""
    args, erg = a.get("args") or {}, a.get("ergebnis")
    teile = []
    if ops := args.get("operations"):
        zaehlung: dict[str, int] = {}
        for o in ops if isinstance(ops, list) else []:
            zaehlung[o.get("op", "?")] = zaehlung.get(o.get("op", "?"), 0) + 1
        teile.append(", ".join(f"{n}×{op}" for op, n in zaehlung.items()))
    for f in ("bereich", "typ", "fach", "jahrgangsstufe", "auch_fremde", "als_entwurf_kopieren"):
        if f in args:
            teile.append(f"{f}={args[f]}")
    if a["tool"] == "set_curriculum_frame":
        teile.append(", ".join(f"{f}" for f in args if f != "curriculum_id"))
    aus = f"`{a['tool']}`" + (f" ({'; '.join(teile)})" if teile else "")
    if isinstance(erg, dict):
        if erg.get("error"):
            aus += f" → Fehler: {erg['error']}"
        elif erg.get("fehler"):
            aus += " → abgewiesen: " + " | ".join(erg["fehler"])
        elif erg.get("bestaetigung_noetig"):
            aus += f" → Bestätigung nötig ({erg.get('letzte_aenderung')})"
        else:
            werte = [f"{f}={erg[f]}" for f in ("verplant", "verplanbar", "rest", "geloescht", "zurueckgenommen")
                     if f in erg]
            if werte:
                aus += " → " + ", ".join(werte)
    return aus


def _gliederung(b: dict) -> list[str]:
    zeilen = [f"Rahmen: {json.dumps(b['rahmen'], ensure_ascii=False)}"] if b["rahmen"] else []
    for i, k in enumerate(b["kapitel"], 1):
        std = sum(ls.get("std") or 0 for ls in k["lernsequenzen"])
        zeilen.append(f"{i}. **{k['titel']}** ({std} Std.)")
        for a in k.get("absprachen") or []:
            zeilen.append(f"    - ↔ Absprache {a['fach']} · {a['ziel'] or 'ganzes Fach'} ({a['art']})"
                          + (f": {a['text']}" if a.get("text") else ""))
        for ls in k["lernsequenzen"]:
            nrn = sorted({(r.get("nr") if isinstance(r, dict) else r) or "" for e in ls["eintraege"]
                          for r in (e.get("ik") or [])} - {""})
            zeilen.append(f"    - {ls['titel']} ({ls.get('std') or 0} Std., {len(ls['eintraege'])} Einträge"
                          + (f"; {', '.join(nrn)}" if nrn else "") + ")")
    return zeilen or ["*(leer)*"]


def _zitat(text: str, fehler: str | None) -> str:
    zeilen = [f"> [!failure] Abbruch\n> {fehler}"] if fehler else []
    zeilen.append("> [!quote] Assistent\n" + "\n".join(f"> {z}" for z in text.splitlines())
                  if text.strip() else "> [!warning] Assistent\n> *(leere Antwort)*")
    return "\n\n".join(zeilen)


def verlauf_als_markdown(kopf: dict, laeufe: list[dict]) -> str:
    zeilen = [f"# Verlauf der Messung — {kopf['datei']}", "",
              f"Gemessen am {kopf['beginn']} · Modell `{kopf['modell']}` · Assistent „{kopf['assistent_name']}“ "
              f"(id {kopf['assistent']}) · Prompt `{kopf['prompt']}`  ",
              "Je Fall und Lauf ein eigenes Curriculum aus der Vorlage und eine eigene Konversation.", ""]
    for l in laeufe:
        zeilen += ["---", "", f"## {l['fall']} · Lauf {l['lauf']} · {'✓' if l['bestanden'] else '✗'}", "",
                   "Kriterien: " + " · ".join(f"{n} {'✓' if ok else '✗'}" for n, ok in l["kriterien"].items())]
        if l.get("berichtet"):
            zeilen.append("Berichtet: " + " · ".join(f"{n}: {v}" for n, v in l["berichtet"].items()))
        if l.get("kosten"):
            c = l["kosten"]
            zeilen.append(f"Kosten: {c['ein']} Token ein, {c['aus']} aus, {c['usd']} $")
        zeilen.append("")
        for z in l["zuege"]:
            zeilen += [f"**Lehrkraft** ({z['zeit']}): {z['frage']}", ""]
            zeilen += ([f"- {_kurz(a)}" for a in z["aufrufe"]] or ["- *(keine Funktion)*"]) + [""]
            zeilen += [_zitat(z["antwort"], z.get("fehler")), ""]
        if l.get("vorher") is not None:
            if l["vorher"] == l["nachher"]:
                zeilen += ["**Curriculum unverändert:**", ""] + _gliederung(l["vorher"]) + [""]
            else:
                zeilen += ["**Curriculum vorher:**", ""] + _gliederung(l["vorher"]) + [""]
                zeilen += ["**Curriculum nachher:**", ""] + _gliederung(l["nachher"]) + [""]
        if l.get("erwartung"):
            zeilen += ["> [!example] Erwartung", f"> {l['erwartung'].strip()}", "", "**Bewertung:**", ""]
            zeilen += [f"- [ ] {b}" for b in BEWERTUNGEN] + ["", "Notiz: ", ""]
    return "\n".join(zeilen) + "\n"


# ── Selbsttest (ohne Modellaufrufe, ohne Schreiben) ──────────────────────────


def selbsttest(daten: dict, conn) -> bool:
    gut = True

    def pruefe(bedingung: bool, text: str):
        nonlocal gut
        print(f"  {'✓' if bedingung else '✗'} {text}")
        gut &= bedingung

    print("Instrument:")
    pruefe(nummern_im_text("siehe 3.1.7 (3) und 2.1(4)") == {"3.1.7(3)", "2.1(4)"}, "Nummern im Text")
    pruefe(bool(FELDNAMEN.search("(`behandelt_in` ist leer)")) and bool(FELDNAMEN.search("tragen keine `absprachen`"))
           and not FELDNAMEN.search("Es gibt keine Absprachen mit der Biologie."), "Feldnamen im Text (0.65)")
    pruefe(nummern_im_text("3.2.2(4)–(6)") == {"3.2.2(4)", "3.2.2(5)", "3.2.2(6)"}, "Spannen")
    pruefe(stunden_im_text("8 Std. und 12 Stunden, 2 Wochenstunden, 1,5 Std") == ["8", "12", "1,5"], "Stunden")
    pruefe(not stunden_im_text("Klasse 7 hat 2 Wochenstunden"), "Wochenstunden zählen nicht")
    pruefe(_zahlen({"verplant": 54, "x": [{"std": 8.0}], "t": "rest 66"}) == {"54", "8", "66"}, "Zahlen im Ergebnis")
    pruefe(_teilmenge({"wochenstunden": {"7": 2}}, {"wochenstunden": {"7": 2.0, "8": 2}}), "Teilmenge Rahmen")
    pruefe(bool(ZUSTIMMUNGSFRAGE.search("Soll ich das Gerüst so anlegen?"))
           and bool(ZUSTIMMUNGSFRAGE.search("Soll ich diesen Vorschlag so übernehmen?"))
           and not ZUSTIMMUNGSFRAGE.search("Woran möchtest du arbeiten?"), "Zustimmungsfrage")
    pruefe(stunden_genannt("| Kapitel | Std |\n|---|---|\n| Optik | 20 |")
           and stunden_genannt("- **verplant**: 120") and stunden_genannt("ihr habt 120 verplanbare Stunden")
           and not stunden_genannt("Kapitel 3 vor 2"), "Stunden ohne Einheit")
    pruefe(_beruehrt_bestehendes([{"op": "x", "kapitel_id": "2ee4dad2-fcc9-4b5a-b83d-364318fd3953"}])
           and not _beruehrt_bestehendes([{"op": "kapitel_anlegen", "ref": "k1"}]), "Bestehendes berührt")

    stand = {"rahmen": {}, "kapitel": [{"titel": "Optik", "lernsequenzen": [],
                                        "absprachen": [{"fach": "M", "ziel": "Winkel", "art": "vorher", "text": ""}]}]}
    k = ende_pruefen({"ende": {"absprachen_anzahl": 1, "absprache_mit": [
        {"kapitel": "Optik", "fach": "M", "art": "vorher"}, {"kapitel": "Optik", "fach": "BIO"}]}},
        [{"stand": stand, "vorher": stand, "aufrufe": []}], {})
    pruefe(list(k.values()) == [True, True, False], "Absprachen am Ende (0.65)")

    print("Szenariodatei:")
    cfg = daten["curriculum"]
    fach = fach_id(conn, cfg)
    band = band_nummern(conn, fach, cfg)
    pruefe(len(band) > 0, f"Kompetenzen des Bands: {len(band)}")
    pruefe(bool(_eins(conn, "SELECT 1 FROM context_nodes WHERE content_type = 'fachplan' AND subject_id = %s "
                            "AND bp_version = %s AND status IN ('active', 'upcoming')", fach, cfg["bp_version"])),
           "Fachplan der Fassung")
    pruefe(bool(_eins(conn, "SELECT 1 FROM assistants WHERE name = %s", daten["assistent"]["vorlage"])),
           f"Vorlage „{daten['assistent']['vorlage']}“ (geseedet)")
    pruefe((REPO / daten["assistent"]["prompt"]).exists(), "Promptdatei")
    if p := cfg.get("partner"):
        pf = _eins(conn, "SELECT id FROM subjects WHERE name = %s OR slug = %s", p["fach"], p["fach"])
        pruefe(pf is not None, f"Partnerfach {p['fach']}")
        for kap in p["kapitel"]:
            for nr in kap.get("verknuepft") or []:
                pruefe(bool(_eins(conn, "SELECT 1 FROM context_nodes WHERE subject_id = %s AND content_type = "
                                        "'ik_kompetenz' AND status = 'active' AND metadata->>'kompetenz_nr' = %s",
                                  pf, nr)), f"Partner: Kompetenz {nr}")
        titel = {k["titel"] for k in p["kapitel"]}
        for name, v in (daten.get("vorlagen") or {}).items():
            ziele = {o["ziel_kapitel"] for o in v.get("extra_operationen") or [] if o.get("ziel_kapitel")}
            ziele |= {a["kapitel"] for a in v.get("partner_absprachen") or []}
            if ziele:
                pruefe(ziele <= titel, f"Vorlage {name}: Ziele im Partnerfach")
    pruefe(bool(_eins(conn, "SELECT 1 FROM group_memberships WHERE group_id = %s AND role_in_group = 'teacher'",
                      daten["lehrkraft_der_gruppe"])), "Mess-Lehrkraft")
    vorhanden = [t for (t,) in _alle(
        conn, "SELECT title FROM context_nodes WHERE content_type = 'curriculum' AND subject_id = %s "
              "AND status IN ('draft', 'active', 'upcoming') "
              "AND COALESCE(metadata->>'bp_version', bp_version) = %s AND metadata->>'jahrgangsstufe' = %s "
              "AND COALESCE(metadata->>'messung', '') <> 'true'", fach, cfg["bp_version"], cfg["jahrgangsstufe"])]
    pruefe(not vorhanden, "kein anderes Curriculum für Band und Fassung" + (f" ({vorhanden})" if vorhanden else ""))
    for name, v in (daten.get("vorlagen") or {}).items():
        nrn = {_norm(n) for o in [*(v.get("operationen") or []), *(v.get("extra_operationen") or [])]
               for f in ("ik", "ik_teilweise", "pk")
               for n in o.get(f) or []}
        pruefe(nrn <= band, f"Vorlage {name}: Nummern im Band" + (f" — fremd: {sorted(nrn - band)}" if nrn - band else ""))
    for fall in daten["faelle"]:
        namen = {n for d in fall["zuege"] for f in ("muss", "nicht", "muss_eine") for n in d.get(f) or []}
        namen |= {m["tool"] for d in fall["zuege"] for m in d.get("muss_mit") or []}
        namen |= {t for d in fall["zuege"] for t in d.get("hoechstens") or {}}
        pruefe(fall["vorlage"] in daten["vorlagen"] and namen <= set(FUNKTIONEN)
               and all(d.get(f) in (None, GLEICH, GEAENDERT) for d in fall["zuege"] for f in ("inhalt", "rahmen")),
               f"Fall {fall['id']}")
    if any(f.get("alte_nummern") for f in daten["faelle"]):
        alt = set().union(*(nummern_im_text("\n".join(d["text"] for d in f["zuege"]))
                            for f in daten["faelle"] if f.get("alte_nummern")))
        pruefe(not (alt & band), "alte Nummern liegen außerhalb des Bands")
    return gut


# ── Bewertung auszählen ──────────────────────────────────────────────────────


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


# ── Ablauf ───────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Messung des Curriculum-Assistenten")
    p.add_argument("--datei", type=Path, default=HIER / "szenarien" / "curriculum_assistent.yaml")
    p.add_argument("--modell", default="chat-komplex")
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--verlauf", type=Path, default=None, help="Chatverlauf zum Nachlesen (Markdown)")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--selbsttest", action="store_true", help="nur Instrument und Szenariodatei prüfen")
    p.add_argument("--bewertung", type=Path, default=None, help="Kästchen eines Verlaufs auszählen")
    p.add_argument("--prompt-rev", default=None,
                   help="Arm A: den Prompt aus dieser Git-Revision nehmen (etwa HEAD vor einer Änderung)")
    p.add_argument("--trocken", action="store_true",
                   help="jede Vorlage einmal aufbauen, zeigen und wieder löschen — ohne Modellaufrufe")
    args = p.parse_args()

    if args.bewertung:
        for fall, z in bewertungen(args.bewertung.read_text(encoding="utf-8")).items():
            print(f"{fall:<28} " + "  ".join(f"{s} {z.get(s, 0)}" for s in (*BEWERTUNGEN, "offen", "mehrdeutig")))
        return
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")

    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    conn = verbindung()
    if args.selbsttest:
        ok = selbsttest(daten, conn)
        conn.close()
        raise SystemExit(0 if ok else 1)

    cfg = daten["curriculum"]
    fach = fach_id(conn, cfg)
    band = band_nummern(conn, fach, cfg)
    pseudonym = _eins(conn, "SELECT pseudonym FROM group_memberships WHERE group_id = %s "
                            "AND role_in_group = 'teacher' LIMIT 1", daten["lehrkraft_der_gruppe"])
    if pseudonym is None:
        raise SystemExit("Keine Mess-Lehrkraft — falsche Instanz?")
    faelle = [f for f in daten["faelle"] if not args.nur or f["id"] in args.nur]

    curricula_loeschen(conn, mess_curricula(conn, fach, pseudonym))  # Reste eines Abbruchs
    gruppe = mitglied_aufnehmen(conn, fach, pseudonym)
    if args.trocken:
        try:
            for name, vorlage in daten["vorlagen"].items():
                cid = aufbauen(cfg, vorlage, pseudonym)
                staende = _alle(conn, "SELECT reason FROM curriculum_snapshots WHERE curriculum_id = %s", cid)
                status = _eins(conn, "SELECT status FROM context_nodes WHERE id = %s", cid)
                print(f"\n## {name} — Status {status}, Stände {[r for (r,) in staende]}")
                print("\n".join(_gliederung(baum(conn, cid))))
                if cfg.get("partner"):
                    for kap_titel, absprachen in _alle(conn, """
                            SELECT k.title, k.metadata->'absprachen' FROM context_nodes k
                            JOIN context_edges e ON e.from_node_id = k.id AND e.relation = 'part_of'
                            JOIN context_nodes c ON c.id = e.to_node_id
                            WHERE c.metadata->>'messung' = 'true' AND c.subject_id <> %s""", fach):
                        print(f"   Partner: {kap_titel}" + (f" — Absprachen {absprachen}" if absprachen else ""))
                curricula_loeschen(conn, mess_curricula(conn, fach, pseudonym))
                print(f"   gelöscht: {_eins(conn, 'SELECT count(*) FROM context_nodes WHERE id = %s', cid) == 0}")
        finally:
            curricula_loeschen(conn, mess_curricula(conn, fach, pseudonym))
            mitglied_entfernen(conn, gruppe, pseudonym)
            conn.close()
        return
    assistent, _ = mess_assistent(conn, daten["assistent"], args.modell, args.prompt_rev)
    beginn = _eins(conn, "SELECT now()")
    kopf = {"datei": args.datei.name, "beginn": datetime.now().strftime("%d.%m.%Y, %H:%M"),
            "assistent": assistent, "assistent_name": daten["assistent"]["name"], "modell": args.modell,
            "prompt": (f"Revision {args.prompt_rev}" if args.prompt_rev
                       else prompt_stand(REPO / daten["assistent"]["prompt"]))}
    token, _ = get_jwt_service().issue(pseudonym=pseudonym, roles=["teacher"], grade=None)
    laeufe, ergebnisse = [], []
    try:
        with httpx.Client(base_url=args.basis, timeout=300.0, headers={"Cookie": f"session={token}"}) as client:
            for fall in faelle:
                for nr in range(1, args.laeufe + 1):
                    lauf_beginn = _eins(conn, "SELECT now()")
                    cid = aufbauen(cfg, daten["vorlagen"][fall["vorlage"]], pseudonym)
                    konversation = None
                    try:
                        zuege, konversation = lauf(client, conn, fall, assistent, cid, args.modell)
                    except (httpx.HTTPError, SystemExit) as fehler:
                        grund = f"{type(fehler).__name__}: {str(fehler)[:200]}"
                        print(f"{fall['id']:<28} Lauf {nr}  ✗  abgebrochen — {grund}", flush=True)
                        zuege = []
                    ende = {"cid": cid, "bezug": _eins(conn, "SELECT curriculum_node_id::text FROM conversations "
                                                             "WHERE id = %s", konversation) if konversation else None,
                            # Nur Curricula des Messfachs — das Partnerfach (0.65) ist keine Kopie
                            "kopien": [i for i in mess_curricula(conn, fach, pseudonym, lauf_beginn) if i != cid
                                       and _eins(conn, "SELECT subject_id FROM context_nodes WHERE id = %s", i) == fach]}
                    if zuege:
                        kriterien, berichtet = bewerte(fall, zuege, band=band, ende=ende)
                    else:
                        kriterien, berichtet = {"abgebrochen": False}, {}
                    c = kosten(conn, konversation) if konversation else None
                    bestanden = all(kriterien.values())
                    fehlt = ", ".join(n for n, ok in kriterien.items() if not ok)
                    print(f"{fall['id']:<28} Lauf {nr}  {'✓' if bestanden else '✗'}  "
                          f"[{' | '.join(' → '.join(z['namen']) or '—' for z in zuege)}]"
                          f"{'  fehlt: ' + fehlt if fehlt else ''}"
                          + (f"  ({c['usd']} $)" if c else ""), flush=True)
                    eintrag = {
                        "fall": fall["id"], "lauf": nr, "bestanden": bestanden, "kriterien": kriterien,
                        "berichtet": berichtet, "kosten": c, "erwartung": fall.get("erwartung"),
                        "vorher": zuege[0]["vorher"] if zuege else None,
                        "nachher": zuege[-1]["stand"] if zuege else None,
                        "zuege": [{"frage": z["frage"], "namen": z["namen"], "aufrufe": z["aufrufe"],
                                   "antwort": z["antwort"], "zeit": z["zeit"], "fehler": z.get("fehler"),
                                   "modell": z.get("modell")} for z in zuege],
                    }
                    laeufe.append(eintrag)
                    ergebnisse.append(eintrag)
                    # Auch das Partner-Curriculum (`messung`), sonst stünden im nächsten Lauf zwei da
                    curricula_loeschen(conn, sorted({cid, *ende["kopien"], *mess_curricula(conn, fach, pseudonym)}))
                    if args.verlauf:
                        args.verlauf.write_text(verlauf_als_markdown(kopf, laeufe), encoding="utf-8")
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE pseudonym = %s AND assistant_id = %s AND created_at >= %s",
                        (pseudonym, assistent, beginn))
        curricula_loeschen(conn, mess_curricula(conn, fach, pseudonym, beginn))
        mitglied_entfernen(conn, gruppe, pseudonym)
        assistent_abschalten(conn, assistent)
        conn.close()

    print("\nFall                         bestanden  nicht erfüllt")
    for fall in faelle:
        eigene = [e for e in ergebnisse if e["fall"] == fall["id"]]
        offen = sorted({n for e in eigene for n, ok in e["kriterien"].items() if not ok})
        print(f"{fall['id']:<28} {sum(e['bestanden'] for e in eigene)}/{len(eigene)}        {', '.join(offen) or '—'}")
    gesamt = sum((e["kosten"] or {}).get("usd", 0) for e in ergebnisse)
    print(f"\nKosten gesamt: {gesamt:.4f} $")
    if args.json:
        args.json.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
