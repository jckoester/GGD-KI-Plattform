"""Methodenblatt finden und befolgen — Variante 1 (Plan „Rückfall-Assistenten“, ursprünglicher
Schritt 9). Szenario und Ablauf: ``scripts/szenarien/methodenblatt.yaml``.

    venv/bin/python scripts/methodenblatt_messung.py anlegen      # drei Testblätter auf Dev, eingebettet
    venv/bin/python scripts/methodenblatt_messung.py finden  [--ziel …]   # nur Embeddings
    venv/bin/python scripts/methodenblatt_messung.py chat    [--ziel …]   # ein Zug je Nachricht, echte Kosten
    venv/bin/python scripts/methodenblatt_messung.py aufraeumen

**finden:** je Nachricht die Vorab-Suche (`kontext_fuer_frage`) wie im Chat einer Schüler:in ohne
Unterrichtsgruppe, im Assistenten der Nachricht — liegt das Blatt unter den sicheren Bausteinen
(im Prompt) oder nur im Angebot (das Modell müsste nachschlagen)?

**chat:** dieselben Nachrichten als erster Zug im Assistenten; ob die Antwort ein Merkmal des
Blatts nennt (etwa „Sanduhr“), dazu wo das Blatt lag.

⚠️ Nur für Entwicklungsinstanzen. Die Blätter sind Testmaterial (`metadata.messung`), sie werden
nicht ausgeliefert.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
MARKE = "methodenblatt"
SZENARIO = HIER / "szenarien/methodenblatt.yaml"


def _szenario() -> dict:
    return yaml.safe_load(SZENARIO.read_text(encoding="utf-8"))


async def anlegen() -> None:
    import sqlalchemy as sa

    from app.context.taxonomy import CONTENT_TYPE_TO_CATEGORY
    from app.db.models import ContextNode, Subject
    from app.db.session import AsyncSessionLocal

    s = _szenario()
    async with AsyncSessionLocal() as db:
        await _loeschen(db)
        faecher = {slug: i for i, slug in (await db.execute(sa.select(Subject.id, Subject.slug))).all()}
        neu = []
        for b in s["blaetter"]:
            knoten = ContextNode(
                category=CONTENT_TYPE_TO_CATEGORY["methodenblatt"], content_type="methodenblatt",
                title=b["titel"], content=b["content"].strip(), status="active",
                metadata_={"messung": MARKE}, read_scope="school", write_scope="school",
                subject_id=faecher[b["fach"]])
            db.add(knoten)
            neu.append(knoten)
        await db.commit()
    # Einbetten wie im Betrieb: über den Backfill, der den Embedding-Text des Typs kennt.
    import subprocess
    subprocess.run([sys.executable, str(HIER / "embedding_backfill.py"), "--content-type", "methodenblatt"],
                   check=True, cwd=HIER.parent)
    print(f"{len(neu)} Testblätter angelegt und eingebettet: {', '.join(b['titel'] for b in s['blaetter'])}")


async def _loeschen(db) -> int:
    import sqlalchemy as sa

    from app.db.models import ContextNode
    r = await db.execute(sa.delete(ContextNode).where(ContextNode.metadata_["messung"].astext == MARKE))
    return r.rowcount or 0


async def aufraeumen() -> None:
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        n = await _loeschen(db)
        await db.commit()
    print(f"{n} Testblätter entfernt.")


async def _kontext_je_nachricht():
    import sqlalchemy as sa

    from app.context.service import kontext_fuer_frage
    from app.db.models import Assistant, ContextNode
    from app.db.session import AsyncSessionLocal

    s = _szenario()
    async with AsyncSessionLocal() as db:
        blaetter = {t: str(i) for i, t in (await db.execute(
            sa.select(ContextNode.id, ContextNode.title).where(ContextNode.metadata_["messung"].astext == MARKE))).all()}
        if len(blaetter) != len(s["blaetter"]):
            raise SystemExit("Testblätter fehlen — zuerst `anlegen`.")
        ids = {n: i for i, n in (await db.execute(sa.select(Assistant.id, Assistant.name))).all()}
        titel = {b["schluessel"]: b["titel"] for b in s["blaetter"]}
        zeilen = []
        for n in s["nachrichten"]:
            k = await kontext_fuer_frage(assistant_id=ids[n["assistent"]], pseudonym="methodenblatt-messung",
                                         query_text=n["text"], chat_id=None, db=db, rollen=["student"],
                                         jwt_stufe=str(n["stufe"]))
            ziel = blaetter[titel[n["blatt"]]]
            sicher = any(str(b.node_id) == ziel for b in k.bausteine)
            angebot = any(str(a.node_id) == ziel for a in k.angebot)
            fremd = [t for t, i in blaetter.items() if i != ziel and (
                any(str(b.node_id) == i for b in k.bausteine) or any(str(a.node_id) == i for a in k.angebot))]
            zeilen.append({**n, "sicher": sicher, "angebot": angebot, "fremd": fremd})
        return zeilen


def _bericht_finden(zeilen) -> str:
    t = [f"# Methodenblatt finden — Variante 1 ({datetime.now(timezone.utc).astimezone():%d.%m.%Y, %H:%M})", "",
         "| Blatt | nennt Methode | sicher (im Prompt) | nur Angebot | nicht gefunden | fremdes Blatt |", "|---|---|---|---|---|---|"]
    for blatt in dict.fromkeys(z["blatt"] for z in zeilen):
        for nennt in (True, False):
            g = [z for z in zeilen if z["blatt"] == blatt and z["nennt"] == nennt]
            t.append(f"| {blatt} | {'ja' if nennt else 'nein'} | {sum(z['sicher'] for z in g)}/{len(g)} "
                     f"| {sum(z['angebot'] and not z['sicher'] for z in g)}/{len(g)} "
                     f"| {sum(not z['sicher'] and not z['angebot'] for z in g)}/{len(g)} | {sum(bool(z['fremd']) for z in g)} |")
    t += ["", "## Je Nachricht", ""]
    for z in zeilen:
        wo = "sicher" if z["sicher"] else ("Angebot" if z["angebot"] else "—")
        t.append(f"- {z['blatt']} · {'nennt' if z['nennt'] else 'nennt nicht'} · {wo}"
                 f"{' · fremd: ' + ', '.join(z['fremd']) if z['fremd'] else ''} — {z['text'][:80]}")
    return "\n".join(t) + "\n"


def _chat(zeilen) -> str:
    import httpx
    import psycopg2

    from app.auth.dependencies import get_jwt_service
    from app.config import settings
    spec = __import__("importlib.util", fromlist=["util"])
    modul = spec.spec_from_file_location("chat_probe", HIER / "chat_probe.py")
    cp = spec.module_from_spec(modul)
    modul.loader.exec_module(cp)
    s = _szenario()
    merkmale = {b["schluessel"]: b["merkmale"] for b in s["blaetter"]}
    conn = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    cur = conn.cursor()
    cur.execute("SELECT pseudonym FROM pseudonym_audit WHERE pseudonym LIKE %s", (KONTO + "%",))
    schueler = cur.fetchone()[0]
    cur.execute("SELECT id, name FROM assistants")
    ids = {n: i for i, n in cur.fetchall()}
    jwt = get_jwt_service()
    t = ["## Befolgen (ein Zug je Nachricht)", "", "| Blatt | nennt Methode | Blatt im Kontext | Merkmal in der Antwort |", "|---|---|---|---|"]
    details = []
    for z in zeilen:
        token = jwt.issue(pseudonym=schueler, roles=["student"], grade=str(z["stufe"]))[0]
        with httpx.Client(base_url="http://localhost:8000", timeout=300, headers={"Cookie": f"session={token}"}) as cl:
            r = cp.frage_stellen(cl, z["text"], assistent=ids[z["assistent"]], gruppe=None, verlauf=[], konversation=None)
        antwort = r["antwort"] or ""
        treffer = [m for m in merkmale[z["blatt"]] if m.lower() in antwort.lower()]
        wo = "sicher" if z["sicher"] else ("Angebot" if z["angebot"] else "—")
        t.append(f"| {z['blatt']} | {'ja' if z['nennt'] else 'nein'} | {wo} | {', '.join(treffer) or '—'} |")
        details += [f"### {z['blatt']} · {'nennt' if z['nennt'] else 'nennt nicht'} · {wo}", "",
                    f"**Schüler:in:** {z['text']}", "", "> " + antwort.replace("\n", "\n> "), "",
                    f"- Werkzeuge: {', '.join(w.get('tool', '') for w in r['werkzeuge']) or '—'}", ""]
        if r.get("konversation"):
            cur.execute("DELETE FROM conversations WHERE id = %s AND pseudonym = %s", (r["konversation"], schueler))
            conn.commit()
    conn.close()
    return "\n".join(t + ["", *details]) + "\n"


KONTO = "e9e62c8de4c6"


def main() -> None:
    p = argparse.ArgumentParser(description="Methodenblatt finden und befolgen (Variante 1)")
    p.add_argument("befehl", choices=["anlegen", "finden", "chat", "aufraeumen"])
    p.add_argument("--ziel", type=Path)
    args = p.parse_args()
    if args.befehl == "anlegen":
        asyncio.run(anlegen())
        return
    if args.befehl == "aufraeumen":
        asyncio.run(aufraeumen())
        return
    zeilen = asyncio.run(_kontext_je_nachricht())
    text = _bericht_finden(zeilen)
    if args.befehl == "chat":
        text += "\n" + _chat(zeilen)
    if args.ziel:
        args.ziel.mkdir(parents=True, exist_ok=True)
        (args.ziel / f"methodenblatt-{args.befehl}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
