#!/usr/bin/env python3
"""Messung „Produkte im Chat“ (0.41, Päckchen AN, Schritt 10; Plan F2: Bedingung).

    python scripts/produkt_im_chat_messung.py --modell chat-standard --modell ionos-mistral-small-24b \\
        --laeufe 2 --protokoll ../../PKM/.../Messungen-0.41/produkte-im-chat.md

**Die Frage:** Greift das Modell ein angehängtes Produkt aus der Werkstatt auf? Das Produkt liegt im
Abschnitt „Explizit hinzugefügter Kontext“ des Systemtexts (`app/artifacts/im_chat.py`).

**Fälle** (je Modell und Lauf):

* ``neu`` — neuer Chat, Dokument mit der ersten Nachricht (`produkt_ids`, wie „Im Chat verwenden“).
* ``nachtraeglich`` — erste Frage ohne Anhang, dann `@` (POST `/artifacts/chats/{id}`), zweite Frage.
* ``diagramm`` — neuer Chat mit einem Mermaid-Flussdiagramm.
* ``ohne`` — Kontrolle: dieselbe Frage wie ``neu``, ohne Anhang. Hier darf das Modell das Blatt
  **nicht** kennen; sonst sagt ``neu`` nichts.
* ``schueler`` — wie ``neu`` mit einem Schüler:innen-Konto (Vorgabemodell), einmal.

**Kriterium „aufgegriffen“:** Die Antwort nennt mindestens ein Kennwort, das nur im Produkt steht
(ausgedachte Namen und Zahlen), und für ``ohne``: keins. Das Skript zählt; gelesen wird jede Antwort
(sie stehen gekürzt im Protokoll).

⚠️ Nur für Entwicklungsinstanzen — eigene Sitzungs-Token, echte Modellaufrufe. Legt Produkte und
Konversationen an und löscht sie am Ende wieder. Pseudonyme werden nicht ausgegeben.
"""
import argparse
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings


def _lade(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


chat_probe = _lade("chat_probe")

ARBEITSBLATT = """# Arbeitsblatt Säuren und Basen — Klasse 9c

Name: ____________  Datum: ____________

**Aufgabe 1:** Familie Wolkenstein reinigt ihren Wasserkocher mit Zitronensäure. Erkläre, warum
sich der Kalk dabei auflöst.

**Aufgabe 2:** Im Labor von Frau Quendel stehen drei Flaschen mit den pH-Werten 2,4 — 7,0 — 11,8.
Ordne die Begriffe „sauer“, „neutral“ und „alkalisch“ zu.

**Aufgabe 3:** Berechne die Masse von 2,5 mol Natriumhydrogencarbonat (Natron).
"""
KENNWORTE_BLATT = ["Wolkenstein", "Quendel", "Natriumhydrogencarbonat", "Natron", "2,5 mol", "11,8",
                   "Zitronensäure", "Wasserkocher"]
KENNWORTE_AUFGABE2 = ["Quendel", "2,4", "11,8", "7,0"]

FLUSSDIAGRAMM = """flowchart TD
    A[Bürette mit Natronlauge füllen] --> B[Vorlage: 20 ml Salzsäure + Bromthymolblau]
    B --> C[Lauge zutropfen und schwenken]
    C --> E[Verbrauch ablesen und notieren]"""
KENNWORTE_DIAGRAMM = ["Bromthymolblau", "Bürette", "Farbumschlag", "Umschlag", "grün", "20 ml"]

FRAGE_BLATT = "Ergänze in meinem Arbeitsblatt eine passende vierte Aufgabe."
FRAGE_AUFGABE2 = "Ist Aufgabe 2 in meinem Arbeitsblatt für eine 9. Klasse zu leicht?"
FRAGE_DIAGRAMM = "Welcher Schritt fehlt in meinem Flussdiagramm zur Titration?"


def _verbindung():
    return psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))


def _konto(conn, rolle: str) -> tuple[str, str | None]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pseudonym, grade FROM pseudonym_audit WHERE roles::text LIKE %s AND litellm_key IS NOT NULL "
            "ORDER BY last_login_at DESC LIMIT 1", (f"%{rolle}%",))
        zeile = cur.fetchone()
    if zeile is None:
        raise SystemExit(f"Kein Dev-Konto mit Rolle {rolle} und LiteLLM-Schlüssel.")
    return zeile[0], (str(zeile[1]) if zeile[1] is not None else None)


def _client(basis, pseudonym, rolle, stufe):
    token = get_jwt_service().issue(pseudonym=pseudonym, roles=[rolle], grade=stufe)[0]
    return httpx.Client(base_url=basis, timeout=300.0, headers={"Cookie": f"session={token}"})


def _dokument(client) -> str:
    r = client.post("/artifacts/document", json={"title": "Arbeitsblatt Säuren und Basen", "markdown": ARBEITSBLATT})
    r.raise_for_status()
    return r.json()["id"]


def _diagramm(conn, pseudonym) -> str:
    """Ein Mermaid-Produkt direkt in der Tabelle — `/from-diagram` will ein gerendertes SVG."""
    pid = str(uuid.uuid4())
    jetzt = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO artifacts (id, owner_pseudonym, kind, mime_type, byte_size, title, source, created_at,"
            " updated_at, expires_at) VALUES (%s, %s, 'mermaid', 'image/svg+xml', 1, 'Ablauf Titration', %s, %s, %s, %s)",
            (pid, pseudonym, FLUSSDIAGRAMM, jetzt, jetzt, jetzt + timedelta(days=1)))
    conn.commit()
    return pid


def _treffer(antwort: str, kennworte: list[str]) -> list[str]:
    klein = antwort.lower()
    return [k for k in kennworte if k.lower() in klein]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--modell", action="append", required=True, help="zweimal: zwei Modelle")
    p.add_argument("--laeufe", type=int, default=2)
    p.add_argument("--protokoll", type=Path, required=True)
    args = p.parse_args()
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")

    conn = _verbindung()
    lk_pseudo, _ = _konto(conn, "teacher")
    sch_pseudo, sch_stufe = _konto(conn, "student")
    lehrkraft = _client(args.basis, lk_pseudo, "teacher", None)
    schueler = _client(args.basis, sch_pseudo, "student", sch_stufe)

    produkte = {"lk": [], "sch": []}
    chats = {"lk": [], "sch": []}
    zeilen: list[dict] = []
    try:
        dok = _dokument(lehrkraft)
        diagramm = _diagramm(conn, lk_pseudo)
        produkte["lk"] += [dok, diagramm]
        sch_dok = _dokument(schueler)
        produkte["sch"].append(sch_dok)

        def lauf(fall, modell, client, wer, frage, kennworte, *, produkt=None, nachtraeglich=None):
            if nachtraeglich:
                erst = chat_probe.frage_stellen(client, "Ich arbeite gerade an einem Arbeitsblatt zu Säuren und Basen.",
                                                assistent=None, gruppe=None, modell=modell)
                chats[wer].append(erst["konversation"])
                r = client.post(f"/artifacts/chats/{erst['konversation']}", json={"artifact_id": nachtraeglich})
                r.raise_for_status()
                verlauf = [{"role": "user", "content": erst["frage"]}, {"role": "assistant", "content": erst["antwort"]}]
                zug = chat_probe.frage_stellen(client, frage, assistent=None, gruppe=None, modell=modell,
                                               verlauf=verlauf, konversation=erst["konversation"])
            else:
                zug = chat_probe.frage_stellen(client, frage, assistent=None, gruppe=None, modell=modell,
                                               produkte=[produkt] if produkt else None)
                chats[wer].append(zug["konversation"])
            gefunden = _treffer(zug["antwort"], kennworte)
            zeilen.append({"fall": fall, "modell": zug.get("modell") or modell or "Vorgabe",
                           "treffer": gefunden, "fehler": zug.get("fehler"), "antwort": zug["antwort"]})
            print(f"{fall:<14} {modell or 'Vorgabe':<26} Kennworte: {gefunden or '—'}", flush=True)

        for modell in args.modell:
            for _ in range(args.laeufe):
                lauf("neu", modell, lehrkraft, "lk", FRAGE_BLATT, KENNWORTE_BLATT, produkt=dok)
                lauf("nachtraeglich", modell, lehrkraft, "lk", FRAGE_AUFGABE2, KENNWORTE_AUFGABE2, nachtraeglich=dok)
                lauf("diagramm", modell, lehrkraft, "lk", FRAGE_DIAGRAMM, KENNWORTE_DIAGRAMM, produkt=diagramm)
                lauf("ohne", modell, lehrkraft, "lk", FRAGE_BLATT, KENNWORTE_BLATT)
        lauf("schueler", None, schueler, "sch", FRAGE_BLATT, KENNWORTE_BLATT, produkt=sch_dok)
    finally:
        for wer, client in (("lk", lehrkraft), ("sch", schueler)):
            for cid in chats[wer]:
                if cid:
                    client.delete(f"/conversations/{cid}")
            for pid in produkte[wer]:
                client.delete(f"/artifacts/{pid}")
        conn.close()

    _protokoll(args, zeilen)


def _protokoll(args, zeilen):
    def ok(z):
        return (not z["treffer"]) if z["fall"] == "ohne" else bool(z["treffer"])

    teile = [f"# Messung Produkte im Chat — {datetime.now():%d.%m.%Y %H:%M}", "",
             f"Modelle: {', '.join(args.modell)} · Läufe je Fall: {args.laeufe} · Skript "
             "`backend/scripts/produkt_im_chat_messung.py`", "",
             "„erwartet“: Kennwort aus dem Produkt genannt — bei `ohne` keins.", "",
             "| Fall | Modell | erwartet | Kennworte |", "|---|---|---|---|"]
    for z in zeilen:
        teile.append(f"| {z['fall']} | {z['modell']} | {'ja' if ok(z) else '**nein**'} | "
                     f"{', '.join(z['treffer']) or '—'}{' · Fehler: ' + z['fehler'] if z['fehler'] else ''} |")
    teile += ["", "## Antworten (gekürzt)", ""]
    for z in zeilen:
        text = z["antwort"].strip().replace("\n", " ")
        teile += [f"**{z['fall']} · {z['modell']}:** {text[:700]}{' …' if len(text) > 700 else ''}", ""]
    args.protokoll.parent.mkdir(parents=True, exist_ok=True)
    args.protokoll.write_text("\n".join(teile), encoding="utf-8")
    print(f"Protokoll: {args.protokoll}")
    print(json.dumps({"erwartet": sum(ok(z) for z in zeilen), "von": len(zeilen)}))


if __name__ == "__main__":
    main()
