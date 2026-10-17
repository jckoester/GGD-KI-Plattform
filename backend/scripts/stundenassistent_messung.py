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

**Die Kriterien prüfen den Ablauf, nicht die Brauchbarkeit** — in Messung 3 bestand
„Rückfrage ohne Schreibwunsch" 3/3 und war unbrauchbar. Deshalb trägt jeder Fall eine
inhaltliche `erwartung`; sie steht im Verlauf unter jedem Lauf, mit drei Kästchen zum
Ankreuzen (brauchbar / teilweise / unbrauchbar). Ausgezählt wird mit

    python scripts/stundenassistent_messung.py --bewertung verlauf.md

Die Abnahme schließt diese Bewertung ein.

⚠️ Nur für Entwicklungsinstanzen — wie `chat_probe.py`: eigener Sitzungs-Token, echte
Modellaufrufe auf Kosten des Budgets der Lehrkraft.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import re
import sys
import uuid
from collections import Counter
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
from app.context.lookup import normalisiere_titel

# `scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden.
_spec = importlib.util.spec_from_file_location("chat_probe", Path(__file__).with_name("chat_probe.py"))
chat_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chat_probe)

LESEN, SUCHEN, SCHREIBEN = "get_lesson_detail", "finde_stunde", "update_lesson_phases"
KONTEXTSUCHE = ("search_context_nodes", "list_context_nodes")
BEWERTUNGEN = ("brauchbar", "teilweise", "unbrauchbar")


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


def vektoren(conn, entwuerfe) -> dict[str, str | None]:
    """Die Vektoren der Entwürfe als Text — für das Zurücksetzen, nicht für die Kriterien.

    Seit 0.17 verwirft jedes Schreiben, das Titel, `refs` oder Reflexion ändert, den Vektor
    der Stunde und bettet neu ein (`vektor_veraltet`). Setzte die Messung nur Titel und
    Metadaten zurück, stünden die Dev-Stunden danach ohne oder mit fremdem Vektor da.
    """
    return dict(_alle(conn, "SELECT id::text, embedding::text FROM context_nodes WHERE id::text = ANY(%s)",
                      list(entwuerfe)))


def zuruecksetzen(conn, ausgang: dict, gruppen: list[int], ausgang_vektoren: dict | None = None) -> None:
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
        for kennung, vektor in (ausgang_vektoren or {}).items():
            cur.execute("UPDATE context_nodes SET embedding = %s::vector WHERE id = %s "
                        "AND embedding IS DISTINCT FROM %s::vector", (vektor, kennung, vektor))


def kompetenznummern_des_fachs(conn, stunde: str) -> set[str]:
    """Alle Kompetenznummern im Fach der Stunde — aktiv wie archiviert (ein Curriculum
    verweist teils auf Knoten eines älteren Imports). Für D2: Gibt es die Nummer überhaupt?"""
    return {nr for (nr,) in _alle(conn, """
        SELECT DISTINCT k.metadata->>'kompetenz_nr' FROM context_nodes k
        JOIN context_nodes s ON s.id::text = %s
        WHERE k.content_type IN ('ik_kompetenz', 'pk_kompetenz') AND k.subject_id = s.subject_id
          AND k.metadata ? 'kompetenz_nr'""", stunde)}


def kompetenznummern_des_kapitels(conn, stunde: str) -> set[str]:
    """Die IK-Nummern aus den Lernsequenzen des Kapitels, auf das die Einheit der Stunde
    verweist (Stunde → Einheit → Kapitel → Lernsequenz → IK) — das, was A1 mitliefert."""
    return {nr for (nr,) in _alle(conn, """
        SELECT DISTINCT ik.metadata->>'kompetenz_nr' FROM context_edges teil
        JOIN context_edges ref ON ref.from_node_id = teil.to_node_id AND ref.relation = 'references'
        JOIN context_nodes k ON k.id = ref.to_node_id AND k.content_type = 'kapitel'
        JOIN context_edges seq ON seq.to_node_id = k.id AND seq.relation = 'part_of'
        JOIN context_nodes l ON l.id = seq.from_node_id AND l.content_type = 'lernsequenz'
        JOIN context_edges r ON r.from_node_id = l.id AND r.relation = 'references'
        JOIN context_nodes ik ON ik.id = r.to_node_id AND ik.content_type = 'ik_kompetenz'
        WHERE teil.from_node_id::text = %s AND teil.relation = 'part_of'""", stunde)}


def aufbau_fehler(fall: dict, kapitel: bool) -> str | None:
    """Passt die Instanz zum Fall? `kompetenzen.kapitel: true` verlangt eine Stunde mit
    Curriculum-Kapitel, `false` eine ohne — sonst misst der Fall still den anderen Weg."""
    soll = (fall.get("kompetenzen") or {}).get("kapitel")
    if soll is None or soll == kapitel:
        return None
    return (f"{fall['id']}: Die Stunde {'braucht' if soll else 'darf kein'} ein Curriculum-Kapitel "
            f"über ihre Einheit{'' if soll else ' haben'} — Jahresplan und Curriculum prüfen.")


def hat_kapitel(conn, stunde: str) -> bool:
    """Bringt der Entwurf ein Curriculum-Kapitel mit (Stunde → Einheit → Kapitel, A1)?"""
    return bool(_eins(conn, """
        SELECT 1 FROM context_edges teil
        JOIN context_edges ref ON ref.from_node_id = teil.to_node_id AND ref.relation = 'references'
        JOIN context_nodes k ON k.id = ref.to_node_id AND k.content_type = 'kapitel'
        WHERE teil.from_node_id::text = %s AND teil.relation = 'part_of' LIMIT 1""", stunde))


# ── Messgruppen und vorbelegte Einträge (0.17, Fachbegriffe der Stunde) ─────


def messgruppe_abbauen(conn, gruppe: dict) -> None:
    """Die Messgruppe samt Konversationen und Knoten — wie `entfall_messung.abbauen`.

    Konversationen und Knoten zuerst: Ihre Gruppenspalten stehen auf `SET NULL`. Termine,
    Snapshots und Mitgliedschaften gehen per `CASCADE` mit der Gruppe.
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


def messgruppe_aufbauen(conn, gruppe: dict, pseudonym: str) -> None:
    """Eine Unterrichtsgruppe der Mess-Lehrkraft mit einem Termin und seinem Entwurf."""
    messgruppe_abbauen(conn, gruppe)
    fach = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", gruppe["fach"])
    if fach is None:
        raise SystemExit(f"Fach „{gruppe['fach']}“ gibt es nicht — falsche Instanz?")
    gid, st = gruppe["id"], gruppe["stunde"]
    phasen = [{"id": str(uuid.uuid4()), "prio": "kern", **p} for p in st["phasen"]]
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, 'teaching_group', %s)",
                    (gid, gruppe["name"], f"messung-begriffe-{gid}", fach))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen')", (gid, pseudonym))
        cur.execute("INSERT INTO context_nodes (category, content_type, title, metadata, owner_pseudonym, "
                    "read_scope, write_scope, read_scope_group_id, write_scope_group_id, subject_id, status) "
                    "VALUES ('artifact', 'unterrichtsstunde', %s, %s, %s, 'group_teachers', 'group_teachers', "
                    "%s, %s, %s, 'active') RETURNING id",
                    (st["titel"], psycopg2.extras.Json({"phasen": phasen, "refs": [],
                                                        "stundenziel": st.get("stundenziel", "")}),
                     pseudonym, gid, gid, fach))
        knoten = cur.fetchone()[0]
        cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr, stunde_node_id) "
                    "VALUES (%s, %s, 1, %s, 1, %s)", (gid, st["datum"], st.get("stunden", 1), knoten))


def refs_aufloesen(conn, stunde: str, eintraege: list[dict]) -> list[dict]:
    """`refs_vorher` eines Falls → Einträge, wie der Planer sie speichert.

    Eine Kompetenz über ihre Nummer — zuerst aus dem Kapitel der Einheit, sonst im Fach
    (aktive vor archivierten); ein Begriff über seinen Titel im Fach oder einem Bezugsfach.
    """
    refs = []
    for e in eintraege:
        if e["typ"] == "concept":
            zeile = _alle(conn, """
                SELECT n.id::text, n.title, n.content_type FROM context_nodes n
                JOIN context_nodes s ON s.id::text = %s JOIN subjects f ON f.id = s.subject_id
                JOIN subjects nf ON nf.id = n.subject_id
                WHERE n.content_type IN ('begriff', 'stoffsteckbrief') AND n.status = 'active'
                  AND n.title = %s AND (nf.id = f.id OR nf.slug = ANY(f.bezugsfaecher))
                ORDER BY n.created_at LIMIT 1""", stunde, e["titel"])
            if not zeile:
                raise SystemExit(f"Begriff „{e['titel']}“ fehlt im Fach der Stunde — falsche Instanz?")
            kennung, titel, art = zeile[0]
            refs.append({"node_id": kennung, "typ": "concept", "code": None, "titel": titel,
                         "partiell": False, "content_type": art})
        else:
            art = "ik_kompetenz" if e["typ"] == "ik" else "pk_kompetenz"
            zeile = _alle(conn, """
                SELECT k.id::text, k.title FROM context_nodes k JOIN context_nodes s ON s.id::text = %s
                WHERE k.content_type = %s AND k.subject_id = s.subject_id
                  AND k.metadata->>'kompetenz_nr' = %s
                ORDER BY (k.id::text = ANY(%s)) DESC, (k.status = 'active') DESC, k.created_at DESC
                LIMIT 1""", stunde, art, e["kompetenz_nr"], list(_kapitel_ik_kennungen(conn, stunde)))
            if not zeile:
                raise SystemExit(f"Kompetenz {e['kompetenz_nr']} fehlt im Fach der Stunde — falsche Instanz?")
            refs.append({"node_id": zeile[0][0], "typ": e["typ"], "code": e["kompetenz_nr"],
                         "titel": zeile[0][1], "partiell": False})
    return refs


def _kapitel_ik_kennungen(conn, stunde: str) -> set[str]:
    return {k for (k,) in _alle(conn, """
        SELECT DISTINCT ik.id::text FROM context_edges teil
        JOIN context_edges ref ON ref.from_node_id = teil.to_node_id AND ref.relation = 'references'
        JOIN context_nodes k ON k.id = ref.to_node_id AND k.content_type = 'kapitel'
        JOIN context_edges seq ON seq.to_node_id = k.id AND seq.relation = 'part_of'
        JOIN context_nodes l ON l.id = seq.from_node_id AND l.content_type = 'lernsequenz'
        JOIN context_edges r ON r.from_node_id = l.id AND r.relation = 'references'
        JOIN context_nodes ik ON ik.id = r.to_node_id AND ik.content_type = 'ik_kompetenz'
        WHERE teil.from_node_id::text = %s AND teil.relation = 'part_of'""", stunde)}


def refs_vorbelegen(conn, stunde: str, refs: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE context_nodes SET metadata = jsonb_set(metadata, '{refs}', %s) WHERE id = %s",
                    (psycopg2.extras.Json(refs), stunde))


def begriffe_info(conn, stunde: str) -> dict:
    """Was die Begriffs-Kriterien über die Knoten wissen müssen — ohne Datenbank in `bewerte`.

    ``fach``: Fach der Stunde; ``erlaubt``: Fach und Bezugsfächer; ``knoten``: jeder
    Fachbegriff und Stoffsteckbrief mit Titel, Aliasen, Fach und ob er aktiv ist.
    """
    fach, bezug = _alle(conn, "SELECT s.id, s.bezugsfaecher FROM context_nodes n JOIN subjects s "
                              "ON s.id = n.subject_id WHERE n.id::text = %s", stunde)[0]
    erlaubt = {fach} | {i for (i,) in _alle(conn, "SELECT id FROM subjects WHERE slug = ANY(%s)", list(bezug or []))}
    knoten = {}
    for kennung, titel, fach_id, aktiv, aliase in _alle(conn, """
            SELECT n.id::text, n.title, n.subject_id, n.status = 'active',
                   coalesce(array_agg(a.alias) FILTER (WHERE a.alias IS NOT NULL), '{}')
            FROM context_nodes n LEFT JOIN node_aliases a ON a.node_id = n.id
            WHERE n.content_type IN ('begriff', 'stoffsteckbrief') GROUP BY 1, 2, 3, 4"""):
        knoten[kennung] = {"titel": titel, "aliase": list(aliase), "subject_id": fach_id, "aktiv": aktiv}
    return {"fach": fach, "erlaubt": erlaubt, "knoten": knoten}


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


# Eine Kompetenznummer: „3.4.5(4)", „3.4.5 (4)", „2.1(1)" — oder eine prozessbezogene ohne
# Klammer mit drei Stufen („2.3.11", so in Chemie). Eine bloße Abschnittsnummer („3.4.5")
# ist keine; ebenso wenig ein Datum („13.10.2026") — davor steht keine Ziffer.
_NUMMER = re.compile(r"(?<![\d.])([123](?:\.\d{1,2}){1,3})(?:[\s  ]*\((\d{1,2})\))?")
# Andere Länder und Länderpläne. Baden-Württemberg fehlt absichtlich.
_FREMDER_PLAN = re.compile(
    r"österreich|schweiz|lehrplan\s*21|bayer|nordrhein|niedersachs|hessen|hessisch|sachsen|"
    r"thüring|brandenburg|berlin|rheinland|saarland|hamburg|bremen|schleswig|mecklenburg",
    re.IGNORECASE,
)


def kompetenznummern(text: str) -> list[str]:
    """Die Kompetenznummern einer Antwort, vereinheitlicht wie `kompetenz_nr` („3.4.5(4)")."""
    gefunden = []
    for basis, klammer in _NUMMER.findall(text):
        if klammer:
            gefunden.append(f"{basis}({klammer})")
        elif basis.startswith("2.") and basis.count(".") == 2:
            gefunden.append(basis)
    return list(dict.fromkeys(gefunden))


def bewerte(fall: dict, ausgang: dict, zuege: list[dict], *, stunde: str | None,
            ziel: str | None = None, nummern: set[str] | None = None,
            kapitel: bool = False, kapitel_nummern: set[str] | None = None,
            begriffe: dict | None = None) -> dict[str, bool]:
    """Die Kriterien aus dem Plan — je Fall nur die, die auf ihn zutreffen.

    ``stunde`` ist die Bezugsstunde des Falls (oder None), ``ziel`` der Entwurf des Termins
    aus ``waehlt``. Für Fälle mit ``kompetenzen``: ``nummern`` sind die Kompetenznummern,
    die es im Fach der Stunde gibt, ``kapitel`` sagt, ob der Entwurf ein Curriculum-Kapitel
    mitbringt. ``begriffe`` (0.17) kommt aus :func:`begriffe_info`. Ohne Datenbank, damit
    sich prüfen lässt, dass die Kriterien Fehlgriffe überhaupt erkennen
    (`tests/unit/test_stundenassistent_messung.py`).
    """
    k: dict[str, bool] = {}

    # 0. Jede Antwort hat Text, kein Zug endete mit einem Abbruch (D1).
    k["antwort_nicht_leer"] = all(z["antwort"].strip() and not z.get("fehler") for z in zuege)

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
            # Verlust heißt: Eine alte Phase fehlt, und eine gleichnamige steht ohne ihre
            # Kennung da — sie wurde neu geschrieben statt übernommen (D1). Bis Messung 3
            # zählte jede neue Kennung; damit schlug auch ein gewolltes Zusammenlegen an.
            alte_ids = {p.get("id") for p in _phasen(vorher)}
            neue_ids = {p.get("id") for p in _phasen(nachher)}
            neu_geschrieben = {_name(p) for p in _phasen(nachher) if p.get("id") not in alte_ids}
            verloren = [p for p in _phasen(vorher)
                        if p.get("id") not in neue_ids and _name(p) in neu_geschrieben]
            k["kennungen_erhalten"] = not verloren
            offen = {p.get("id") for p in _phasen(vorher) if p.get("dauer_min") is None}
            k["skizze_ohne_dauer"] = all(p.get("dauer_min") is None
                                         for p in _phasen(nachher) if p.get("id") in offen)

    # Ohne Bezug: der richtige Termin gewählt — oder nachgefragt, ohne zu wählen. Ob und wie
    # gut gefragt wird, beurteilt Jan im Verlauf; ein Fragezeichen zu zählen sagte nichts (D1).
    if "waehlt" in fall:
        k["waehlt_den_termin"] = ziel is not None and zuege[0]["bezug"] == ziel
    if fall.get("nachfrage"):
        k["fragt_nach"] = zuege[0]["bezug"] is None

    # Kompetenzen (D2): aus einer Quelle, nicht aus dem Gedächtnis; jede genannte Nummer gibt
    # es im Fach und sie gehört zur Stufe; kein anderer Plan.
    if "kompetenzen" in fall:
        text = "\n".join(z["antwort"] for z in zuege)
        genannt = kompetenznummern(text)
        praefixe = tuple(fall["kompetenzen"]["praefixe"])
        k["kompetenz_aus_quelle"] = kapitel or any(
            w in KONTEXTSUCHE for z in zuege for w in _werkzeuge(z))
        k["kompetenzen_genannt"] = bool(genannt)
        k["kompetenzen_der_stufe"] = all(
            n.startswith(praefixe) and (nummern is None or n in nummern) for n in genannt)
        k["kein_fremder_plan"] = not _FREMDER_PLAN.search(text)
        # A4: Hat die Stunde ein Kapitel, stammen die inhaltsbezogenen Kompetenzen von dort —
        # nicht aus einem späteren Thema derselben Stufe (3.4.1(6) Entropie statt Aromaten).
        # Die Präfixe allein sähen das nicht. Prozessbezogene (2.x) bleiben frei.
        if fall["kompetenzen"].get("kapitel"):
            ik = [n for n in genannt if n.startswith("3.")]
            k["kompetenzen_aus_dem_kapitel"] = bool(ik) and all(
                n in (kapitel_nummern or set()) for n in ik)

    k.update(_begriffs_kriterien(fall, ausgang, zuege, stunde=stunde, info=begriffe))
    return k


# „Begriffe dieser Stunde" — der eigene Absatz, den der Prompt verlangt (Plan F4).
_BEGRIFFSABSATZ = re.compile(r"begriffe\s+dieser\s+stunde", re.IGNORECASE)
# Woran man erkennt, dass die Antwort einen Begriff als fehlend benennt (F6).
_FEHLT = re.compile(r"fehlt|fehlen|nicht im wissensspeicher|gibt es (?:dort |im wissensspeicher )?(?:noch )?nicht|"
                    r"nicht vorhanden|nicht gefunden|nicht angelegt|fachschaft", re.IGNORECASE)


def _genannt(namen: list[str], text: str) -> bool:
    """Steht einer der Namen im Text — auch gebeugt? Jedes Wort mit gekürzter Endung
    („elektrophile Substitution" trifft „der elektrophilen Substitution")."""
    t = text.casefold()
    for name in namen:
        woerter = [w for w in re.split(r"[\s\-]+", name.casefold()) if w]
        if woerter and all(w[: max(4, len(w) - 2)] in t for w in woerter):
            return True
    return False


def _refs(entwurf) -> list[dict]:
    return list((entwurf or {}).get("metadata", {}).get("refs") or [])


# ── Begriffe zählen: genannt → im Speicher → eingetragen (Plan § 26) ─────────
#
# Fables Vorschlag nach Messung 9: Erst die Zählung je Lauf trennt den Wissensspeicher vom
# Modell. „3 · 3 · 3 eingetragen" sah nach genauer Auswahl aus; genannt waren 6 · 7 · 6, die
# Aliase im Speicher bündelten sie auf drei Knoten.

# Wie `_BINDESTRICHE` im Werkzeug (`app/planning/assistant_tools.py`).
_BINDESTRICHE = str.maketrans({"‐": "-", "‑": "-", "­": None})
_UNSICHTBAR = re.compile(r"[*_`​  ]+")
# Was in einem Absatz kein Begriff ist: leere Phasen, „bekannt" und „wiederholt" markierte.
_LEER = re.compile(r"^[—–\-]*$")
_NICHT_NEU = re.compile(r"\((?:[^)]*\b(?:bekannt|wiederholt|wiederholung)\b[^)]*)\)", re.IGNORECASE)


def _begriff_bereinigen(roh: str) -> str:
    t = _UNSICHTBAR.sub(" ", roh)
    t = re.sub(r"\([^)]*\)", "", t)                  # „(Erarbeitung)", „(eingeführt)"
    return " ".join(t.split()).strip(" .:;?!-–—")


def begriffsabsatz(antwort: str) -> tuple[list[str], list[str]] | None:
    """Die Begriffe aus dem Absatz „Begriffe dieser Stunde" → (eingeführt, angesprochen).

    Drei Formen kamen in M7–M9 vor: eine Kommazeile („A (Erarbeitung), B (Einstieg)."), eine
    Liste je Begriff und — seit Fables Fassung — eine Zeile je Phase mit „Gesamt". Steht
    „Gesamt" da, zählt nur sie; „· nur angesprochen:" trennt dort die beiden Gruppen. Sonst
    zählt jede Zeile, ohne Phasennamen, ohne als bekannt oder wiederholt markierte Begriffe.
    None: kein Absatz.
    """
    treffer = _BEGRIFFSABSATZ.search(antwort or "")
    if not treffer:
        return None
    zeilen: list[str] = []
    rest = antwort[treffer.end():].split("\n")
    kopf = re.sub(r"^[\s*:]*(?:\([^)]*\))?[\s*:]*", "", rest[0])
    if kopf.strip():
        zeilen.append(kopf)
    for nr, zeile in enumerate(rest[1:], 1):
        if not zeile.strip():
            # Eine Leerzeile beendet den Absatz — außer vor der Zeile „Gesamt" (M8, Lauf 1).
            folgt = next((z for z in rest[nr + 1:] if z.strip()), "")
            if zeilen and not re.search(r"\bgesamt\b", folgt, re.IGNORECASE):
                break
            continue
        zeilen.append(zeile)

    def liste(text: str) -> list[str]:
        # Eine Kommazeile endet mit dem Satz: „…, Elektrophil (Erarbeitung). Soll ich …?"
        text = re.split(r"(?<=[\w)])[.?!]\s+(?=[A-ZÄÖÜ])", text)[0]
        namen = []
        for teil in re.split(r",(?![^()]*\))|\s/\s", text):
            if _NICHT_NEU.search(teil):
                continue
            name = _begriff_bereinigen(teil)
            if name and not _LEER.match(name) and len(name) <= 60:
                namen.append(name)
        return namen

    eingefuehrt: list[str] = []
    angesprochen: list[str] = []
    gesamt = next((z for z in zeilen if re.search(r"\bgesamt\b", z, re.IGNORECASE)), None)
    if gesamt:
        inhalt = re.split(r"gesamt\W*", gesamt, maxsplit=1, flags=re.IGNORECASE)[1]
        for teil in inhalt.split("·"):
            if re.match(r"\s*nur angesprochen", teil, re.IGNORECASE):
                angesprochen += liste(re.sub(r"^\s*nur angesprochen\s*:?", "", teil, flags=re.IGNORECASE))
            else:
                eingefuehrt += liste(teil)
    else:
        for zeile in zeilen:
            zeile = re.sub(r"^\s*(?:[-*•]|\d+\.)\s*", "", zeile)
            # „Erarbeitung (1): A (eingeführt), B (angesprochen)" — der Phasenname gehört nicht dazu.
            # M10: auch mit Gedankenstrich statt Doppelpunkt („**Erarbeitung** – A, B").
            zeile = re.sub(r"^\W*[\w ()0-9.]{1,40}?[*\s]*(?::|\s[–—-]\s)[*\s]*", "", zeile, count=1)
            for teil in re.split(r",(?![^()]*\))", zeile):
                ziel = angesprochen if re.search(r"\(angesprochen\)", teil, re.IGNORECASE) else eingefuehrt
                ziel += liste(teil)
    return list(dict.fromkeys(eingefuehrt)), [n for n in dict.fromkeys(angesprochen) if n not in eingefuehrt]


def _knoten_zum_namen(name: str, info: dict) -> str | None:
    """Wie `_begriff_zum_titel` im Werkzeug: Titel oder Alias, aktiv, im Fach oder einem
    Bezugsfach; gibt es ihn in beiden, das eigene Fach."""
    schluessel = normalisiere_titel(name.translate(_BINDESTRICHE))
    treffer = [k for k, n in (info.get("knoten") or {}).items()
               if n.get("aktiv", True) and n.get("subject_id") in info.get("erlaubt", set())
               and schluessel in {normalisiere_titel(t) for t in [n["titel"], *n.get("aliase", [])]}]
    if len(treffer) > 1:
        eigene = [k for k in treffer if info["knoten"][k].get("subject_id") == info.get("fach")]
        treffer = eigene if len(eigene) == 1 else treffer
    return treffer[0] if len(treffer) == 1 else None


def begriffs_zaehlung(fall: dict, ausgang: dict, zuege: list[dict], *, stunde, info) -> dict | None:
    """Je Lauf: was das Modell nennt, was davon im Speicher steht und was eingetragen ist.

    Nur für Fälle mit Absatz (``begriffe.absatz``). ``vorhanden_nicht_eingetragen``: genannt,
    im Speicher, aber nach dem Lauf nicht in `refs` — das Modell hat es verloren.
    ``fehlt_im_speicher``: genannt, aber weder Titel noch Alias eines Begriffs im Fach.
    """
    if not (fall.get("begriffe") or {}).get("absatz") or not zuege or not info:
        return None
    absatz = begriffsabsatz(zuege[0]["antwort"])
    eingefuehrt, angesprochen = absatz or ([], [])
    genannt = eingefuehrt + angesprochen
    zuordnung = {n: _knoten_zum_namen(n, info) for n in genannt}
    vorher = {str(r.get("node_id")) for r in _refs(ausgang["entwuerfe"].get(stunde)) if r.get("typ") == "concept"}
    nachher = [r for r in _refs(zuege[-1]["stand"]["entwuerfe"].get(stunde)) if r.get("typ") == "concept"]
    da = {str(r.get("node_id")) for r in nachher}
    knoten = {k for k in zuordnung.values() if k}
    neu = [r for r in nachher if str(r.get("node_id")) not in vorher]
    return {
        "absatz": absatz is not None,
        "eingefuehrt": eingefuehrt,
        "angesprochen": angesprochen,
        "knoten": len(knoten),
        "genannte_knoten": sorted(knoten),
        "eingetragen": len(neu),
        "aliase": sum(len(r.get("aliase") or []) for r in neu),
        "fehlt_im_speicher": [n for n, k in zuordnung.items() if k is None],
        "vorhanden_nicht_eingetragen": [n for n, k in zuordnung.items() if k and k not in da],
        "eingetragen_nicht_genannt": [r.get("titel") for r in neu if str(r.get("node_id")) not in knoten],
    }


def zaehlung_kurz(z: dict | None) -> str:
    """„genannt 6+1 → 3 Knoten → 3 eingetragen (2 Aliase) · fehlt: Startlinie" — eine Zeile."""
    if not z:
        return ""
    if not z["absatz"]:
        return f"kein Absatz → {z['eingetragen']} eingetragen"
    teile = [f"genannt {len(z['eingefuehrt'])}+{len(z['angesprochen'])} → {z['knoten']} Knoten → "
             f"{z['eingetragen']} eingetragen" + (f" ({z['aliase']} Aliase)" if z["aliase"] else "")]
    for feld, name in (("fehlt_im_speicher", "fehlt"), ("vorhanden_nicht_eingetragen", "verloren"),
                       ("eingetragen_nicht_genannt", "ungenannt")):
        if z[feld]:
            teile.append(f"{name}: {', '.join(z[feld])}")
    return " · ".join(teile)


def _begriffs_kriterien(fall: dict, ausgang: dict, zuege: list[dict], *, stunde, info) -> dict[str, bool]:
    """Die Kriterien zu Begriffen der Stunde (Plan „Fachbegriffe der Stunde", Schritt 5).

    ``fall["begriffe"]``:
    - ``absatz``: true — die erste Antwort hat den Absatz „Begriffe dieser Stunde";
      false — sie hat ihn nicht (Kürzen, Fragen).
    - ``geschrieben``: Nach der Zustimmung steht mindestens ein neuer Begriff in `refs`; jeder
      stammt aus dem Fach oder einem Bezugsfach; mit ``absatz`` steht jeder neue auch in der
      ersten Antwort.
    - ``aus_bezugsfach``: Mindestens ein neuer Begriff stammt aus einem Bezugsfach.
    - ``nur``: Titel, die eingetragen werden sollen — genau diese, kein anderer.
    - ``fehlt``: ein Begriff, den es nicht gibt — die Antwort sagt, dass er fehlt.
    - ``unveraendert``: `refs` nach dem Schreiben gleich denen davor.
    - ``deckt_ab`` (seit M10): Titel, die die genannten Begriffe abdecken müssen — direkt oder
      über einen Alias.
    - ``nicht_eingefuehrt`` (seit M10): Titel, die nicht als eingeführt genannt sein dürfen —
      die Stunde wiederholt sie.
    Dazu immer, wenn vorher Kompetenzen eingetragen waren und geschrieben wurde: Sie sind noch da.
    Mit ``absatz`` und ``geschrieben`` (seit M10, aus :func:`begriffs_zaehlung`):
    ``nichts_verloren`` — jeder genannte Begriff, den es gibt, steht danach in `refs`;
    ``fehlende_genannt`` — jeden genannten, den es nicht gibt, nennt die Antwort nach der
    Zustimmung als fehlend.
    """
    b = fall.get("begriffe") or {}
    k: dict[str, bool] = {}
    if "absatz" in b:
        hat = bool(_BEGRIFFSABSATZ.search(zuege[0]["antwort"]))
        k["begriffsabsatz" if b["absatz"] else "kein_begriffsabsatz"] = hat == b["absatz"]
    if "fehlt" in b:
        text = "\n".join(z["antwort"] for z in zuege)
        k["fehlen_gesagt"] = _genannt([b["fehlt"]], text) and bool(_FEHLT.search(text))
    zaehlung = begriffs_zaehlung(fall, ausgang, zuege, stunde=stunde, info=info)
    if zaehlung and b.get("deckt_ab"):
        gedeckt = set(zaehlung["genannte_knoten"])
        k["deckt_ab"] = all(_knoten_zum_namen(t, info) in gedeckt for t in b["deckt_ab"])
    if zaehlung and b.get("nicht_eingefuehrt"):
        verboten = {normalisiere_titel(t) for t in b["nicht_eingefuehrt"]}
        verboten_knoten = {_knoten_zum_namen(t, info) for t in b["nicht_eingefuehrt"]} - {None}
        k["wiederholtes_nicht_eingefuehrt"] = not any(
            normalisiere_titel(n.translate(_BINDESTRICHE)) in verboten or _knoten_zum_namen(n, info) in verboten_knoten
            for n in zaehlung["eingefuehrt"])

    ab = fall.get("zustimmung_ab")
    if not (ab and stunde):
        return k
    if zaehlung and b.get("geschrieben"):
        k["nichts_verloren"] = not zaehlung["vorhanden_nicht_eingetragen"]
        danach = "\n".join(z["antwort"] for z in zuege[ab - 1:])
        fehlt = zaehlung["fehlt_im_speicher"]
        k["fehlende_genannt"] = all(_genannt([n], danach) for n in fehlt) and (not fehlt or bool(_FEHLT.search(danach)))
    vorher = _refs(ausgang["entwuerfe"].get(stunde))
    nachher = _refs(zuege[-1]["stand"]["entwuerfe"].get(stunde))
    kompetenzen_vorher = {r.get("node_id") for r in vorher if r.get("typ") != "concept"}
    if kompetenzen_vorher:
        k["kompetenzen_erhalten"] = kompetenzen_vorher <= {r.get("node_id") for r in nachher}
    begriffe_vorher = {r.get("node_id") for r in vorher if r.get("typ") == "concept"}
    neu = [r for r in nachher if r.get("typ") == "concept" and r.get("node_id") not in begriffe_vorher]
    knoten = (info or {}).get("knoten", {})

    def fach(r):
        return knoten.get(r.get("node_id"), {}).get("subject_id")

    if b.get("geschrieben"):
        k["begriffe_geschrieben"] = bool(neu)
        k["begriffe_aus_fach"] = all(fach(r) in (info or {}).get("erlaubt", set()) for r in neu)
        if b.get("absatz"):
            k["begriffe_wie_genannt"] = all(
                _genannt([r.get("titel") or ""] + knoten.get(r.get("node_id"), {}).get("aliase", []),
                         zuege[0]["antwort"]) for r in neu)
    if b.get("aus_bezugsfach"):
        k["begriff_aus_bezugsfach"] = any(fach(r) not in (None, (info or {}).get("fach")) for r in neu)
    if "nur" in b:
        titel = {knoten.get(r.get("node_id"), {}).get("titel") for r in neu}
        k["nur_vorhandene_eingetragen"] = titel <= set(b["nur"])
        k["vorhandene_eingetragen"] = set(b["nur"]) <= titel
    if b.get("unveraendert"):
        k["refs_unveraendert"] = ([(r.get("node_id"), r.get("typ")) for r in nachher]
                                  == [(r.get("node_id"), r.get("typ")) for r in vorher])
    return k


def _name(phase: dict) -> str:
    return (phase.get("name") or "").strip().rstrip(":").casefold()


# ── Verlauf zum Nachlesen ────────────────────────────────────────────────────


def _phase_kurz(p: dict) -> str:
    """Eine Phase in einer Zeile — die Beschreibung **vollständig**.

    Bis Messung 3 stand hier nur die erste Zeile, auf 90 Zeichen gekürzt. In „Skizze ohne
    Dauer" las sich das wie eine unvollständig gespeicherte Phase, nachprüfen ließ es sich
    nicht mehr: Die Messung setzt den Stand zurück (D7). Zeilenumbrüche werden zu „ / ".
    """
    def eintrag(feld):
        e = p.get(feld) or {}
        return e.get("titel") or e.get("wert") or ""
    teile = [f"{p.get('dauer_min')}′" if p.get("dauer_min") is not None else "ohne Dauer",
             p.get("prio") or "kern"]
    teile += [t for t in (eintrag("sozialform"), eintrag("methode")) if t]
    zeile = f"{p.get('name')} ({', '.join(teile)})"
    beschreibung = " / ".join(z.strip() for z in (p.get("beschreibung") or "").splitlines() if z.strip())
    return zeile + (f" — {beschreibung}" if beschreibung else "")


def _refs_kurz(refs) -> str:
    """`refs` in einer Zeile: Kompetenzen mit Nummer, Begriffe mit Titel und „(B)"."""
    if not refs:
        return "—"
    def begriff(r):
        aliase = f" [{', '.join(r['aliase'])}]" if r.get("aliase") else ""
        return f"{r.get('titel')}{aliase} (B)"
    return ", ".join(begriff(r) if r.get("typ") == "concept" else (r.get("code") or r.get("titel") or "?")
                     for r in refs)


def _zitat(text: str, fehler: str | None = None) -> str:
    zeilen = []
    if fehler:
        zeilen.append(f"> [!failure] Abbruch\n> {fehler}")
    if not text.strip():
        zeilen.append("> [!warning] Assistent\n> *(leere Antwort)*")
    else:
        zeilen.append("> [!quote] Assistent\n" + "\n".join(f"> {z}" for z in text.splitlines()))
    return "\n\n".join(zeilen)


def _bewertungsblock(erwartung: str) -> list[str]:
    """Erwartung und drei Kästchen — in Obsidian anklickbar, ausgezählt von `bewertungen`."""
    return (["> [!example] Erwartung", f"> {erwartung.strip()}", "", "**Bewertung:**", ""]
            + [f"- [ ] {b}" for b in BEWERTUNGEN] + ["", "Notiz: ", ""])


def bewertungen(markdown: str) -> dict[str, Counter]:
    """Zählt die angekreuzten Bewertungen eines Verlaufs je Fall.

    Je Lauf zählt genau ein Kreuz; keines heißt „offen", mehrere „mehrdeutig".
    """
    ergebnis: dict[str, Counter] = {}
    for abschnitt in re.split(r"\n(?=## )", markdown):
        kopf = re.match(r"## (\S+) · Lauf \d+", abschnitt)
        if not kopf or "**Bewertung:**" not in abschnitt:
            continue
        kreuze = re.findall(r"^- \[[xX]\] (" + "|".join(BEWERTUNGEN) + r")\s*$", abschnitt, re.M)
        wert = kreuze[0] if len(kreuze) == 1 else "offen" if not kreuze else "mehrdeutig"
        ergebnis.setdefault(kopf.group(1), Counter())[wert] += 1
    return ergebnis


def notizen(markdown: str) -> list[tuple[str, str]]:
    """Die Notizen eines Verlaufs: (Fall · Lauf, Text) — nur ausgefüllte.

    Die Notiz steht unter „Notiz:", in derselben Zeile oder darunter, bis zum Ende des Laufs.
    """
    gefunden = []
    for abschnitt in re.split(r"\n(?=## )", markdown):
        kopf = re.match(r"## (\S+ · Lauf \d+)", abschnitt)
        if not kopf or "**Bewertung:**" not in abschnitt:
            continue
        # Die Notiz steht unter der Bewertung — nicht beim ersten „Notiz:" im Abschnitt: Das
        # kann im Text des Assistenten stehen (Messung 4 zu 0.17, eine Tabelle mit „Notiz:").
        unten = abschnitt.rsplit("**Bewertung:**", 1)[1]
        if "Notiz:" not in unten:
            continue
        text = unten.split("Notiz:", 1)[1].split("\n---", 1)[0].strip()
        if text:
            gefunden.append((kopf.group(1), " ".join(text.split())))
    return gefunden


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
                       "", _zitat(z["antwort"], z.get("fehler")), ""]
        if l.get("vorher") is not None and l.get("nachher") != l.get("vorher"):
            zeilen += ["**Entwurf vorher:**", ""] + [f"{i}. {_phase_kurz(p)}" for i, p in enumerate(l["vorher"], 1)]
            zeilen += ["", "**Entwurf nachher:**", ""] + [f"{i}. {_phase_kurz(p)}" for i, p in enumerate(l["nachher"] or [], 1)]
            if l.get("ziel_nachher") != l.get("ziel_vorher"):
                zeilen += ["", f"Stundenziel: „{l.get('ziel_vorher') or ''}“ → „{l.get('ziel_nachher') or ''}“"]
            zeilen.append("")
        # Eigens, nicht nur bei geänderten Phasen: Ein Lauf kann allein `refs` schreiben (0.17).
        if l.get("refs_nachher") != l.get("refs_vorher"):
            zeilen += [f"**Kompetenzen und Begriffe:** {_refs_kurz(l.get('refs_vorher'))} → "
                       f"{_refs_kurz(l.get('refs_nachher'))}", ""]
        if l.get("zaehlung"):
            zeilen += [f"**Begriffe gezählt:** {zaehlung_kurz(l['zaehlung'])}", ""]
        if l.get("erwartung"):
            zeilen += _bewertungsblock(l["erwartung"])
    return "\n".join(zeilen) + "\n"


# ── Ablauf ───────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Messung zum Stundenassistenten")
    p.add_argument("--datei", type=Path, help="Szenariendatei (nicht nötig mit --bewertung)")
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--assistent", type=int, default=None)
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--json", type=Path, default=None, help="Ergebnis mit allen Antworten hierhin")
    p.add_argument("--verlauf", type=Path, default=None, help="Chatverlauf zum Nachlesen (Markdown)")
    p.add_argument("--trotzdem", action="store_true", help="auch ohne vollständige Vektoren")
    p.add_argument("--bewertung", type=Path, default=None,
                   help="angekreuzte Bewertungen eines Verlaufs auszählen und beenden")
    args = p.parse_args()

    if args.bewertung:
        tabelle = bewertungen(args.bewertung.read_text(encoding="utf-8"))
        spalten = (*BEWERTUNGEN, "offen", "mehrdeutig")
        print(f"{'Fall':<30} " + " ".join(f"{s:>11}" for s in spalten))
        for fall, zaehler in tabelle.items():
            print(f"{fall:<30} " + " ".join(f"{zaehler.get(s, 0):>11}" for s in spalten))
        notiert = notizen(args.bewertung.read_text(encoding="utf-8"))
        if notiert:
            print("\nNotizen:")
            for wo, text in notiert:
                print(f"  {wo}: {text}")
        return
    if not args.datei:
        p.error("--datei fehlt")

    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz (eigener Token, echtes Budget, schreibt Entwürfe).")

    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    if daten.get("heute") and daten["heute"] != date.today():
        raise SystemExit(f"Die Fälle sind auf {daten['heute']} geschnitten, heute ist {date.today()}.")
    faelle = [f for f in daten["faelle"] if not args.nur or f["id"] in args.nur]

    asyncio.run(vor_einer_messung(trotzdem=args.trotzdem))
    conn = verbindung()
    pseudonym = lehrkraft_der_gruppe(conn, daten["lehrkraft_der_gruppe"])
    # Eigene Messgruppen (0.17) vor allem anderen: Ihre Entwürfe gehören zum Ausgangsstand.
    messgruppen = daten.get("messgruppen") or []
    for gruppe in messgruppen:
        messgruppe_aufbauen(conn, gruppe, pseudonym)
    gruppen = gruppen_der_lehrkraft(conn, pseudonym)
    assistent = args.assistent or stundenassistent(conn)
    vorbelegt: dict[str, list[dict]] = {}
    for fall in faelle:
        if "stunde" in fall and stunde_am(conn, **fall["stunde"]) is None:
            raise SystemExit(f"{fall['id']}: kein Entwurf am {fall['stunde']} — falsche Instanz?")
        if "stunde" in fall and (fehler := aufbau_fehler(fall, hat_kapitel(conn, stunde_am(conn, **fall["stunde"])))):
            raise SystemExit(fehler)
        if fall.get("refs_vorher"):
            vorbelegt[fall["id"]] = refs_aufloesen(conn, stunde_am(conn, **fall["stunde"]), fall["refs_vorher"])

    ausgang = stand(conn, gruppen)
    ausgang_vektoren = vektoren(conn, ausgang["entwuerfe"])
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
                    zuruecksetzen(conn, ausgang, gruppen, ausgang_vektoren)
                    # Vorbelegte `refs` (0.17): Ausgang dieses Laufs ist der Stand **mit** ihnen.
                    lauf_ausgang = ausgang
                    if fall["id"] in vorbelegt:
                        refs_vorbelegen(conn, stunde_am(conn, **fall["stunde"]), vorbelegt[fall["id"]])
                        lauf_ausgang = stand(conn, gruppen)
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
                    bezug = stunde_am(conn, **fall["stunde"]) if "stunde" in fall else None
                    kriterien = bewerte(
                        fall, lauf_ausgang, zuege, stunde=bezug,
                        ziel=stunde_am(conn, **fall["waehlt"]) if "waehlt" in fall else None,
                        nummern=kompetenznummern_des_fachs(conn, bezug) if bezug and "kompetenzen" in fall else None,
                        kapitel=bool(bezug) and hat_kapitel(conn, bezug),
                        kapitel_nummern=kompetenznummern_des_kapitels(conn, bezug) if bezug else None,
                        begriffe=begriffe_info(conn, bezug) if bezug and "begriffe" in fall else None,
                    )
                    bestanden = all(kriterien.values())
                    zaehlung = begriffs_zaehlung(
                        fall, lauf_ausgang, zuege, stunde=bezug,
                        info=begriffe_info(conn, bezug) if bezug and "begriffe" in fall else None)
                    werkzeuge = " | ".join(" → ".join(_werkzeuge(z)) or "—" for z in zuege)
                    fehlend = ", ".join(n for n, ok in kriterien.items() if not ok)
                    print(f"{fall['id']:<30} Lauf {nr}  {'✓' if bestanden else '✗'}  "
                          f"[{werkzeuge}]{'  fehlt: ' + fehlend if fehlend else ''}", flush=True)
                    if zaehlung:
                        print(f"{'':<30} Begriffe: {zaehlung_kurz(zaehlung)}", flush=True)
                    ergebnisse.append({
                        "fall": fall["id"], "lauf": nr, "bestanden": bestanden, "kriterien": kriterien,
                        "zaehlung": zaehlung,
                        # Zum Nachbewerten ohne neuen Lauf (seit M10).
                        "refs_vorher": _refs(lauf_ausgang["entwuerfe"].get(bezug)) if bezug else None,
                        "refs_nachher": _refs(zuege[-1]["stand"]["entwuerfe"].get(bezug)) if bezug else None,
                        "modell": zuege[0].get("modell"), "erwartung": fall.get("erwartung"),
                        "kompetenznummern": kompetenznummern("\n".join(z["antwort"] for z in zuege))
                        if "kompetenzen" in fall else None,
                        "zuege": [{"frage": z["frage"], "werkzeuge": _werkzeuge(z),
                                   "antwort": z["antwort"], "fehler": z.get("fehler")} for z in zuege],
                    })
                    kopf["modell"] = zuege[0].get("modell") or kopf["modell"]
                    stunde = stunde_am(conn, **fall["stunde"]) if "stunde" in fall else None
                    vorher = lauf_ausgang["entwuerfe"].get(stunde) if stunde else None
                    nachher = zuege[-1]["stand"]["entwuerfe"].get(stunde) if stunde else None
                    laeufe.append({
                        "fall": fall["id"], "lauf": nr, "bestanden": bestanden, "kriterien": kriterien,
                        "bezugsstunde": (f"Gruppe {fall['stunde']['gruppe']}, {fall['stunde']['datum']:%d.%m.%Y}"
                                         f" — „{vorher['titel']}“") if vorher else None,
                        "vorher": _phasen(vorher) if vorher else None,
                        "nachher": _phasen(nachher) if nachher else None,
                        "ziel_vorher": (vorher or {}).get("metadata", {}).get("stundenziel"),
                        "ziel_nachher": (nachher or {}).get("metadata", {}).get("stundenziel"),
                        "refs_vorher": _refs(vorher), "refs_nachher": _refs(nachher),
                        "zaehlung": zaehlung,
                        "zuege": [{"frage": z["frage"], "werkzeuge": _werkzeuge(z), "antwort": z["antwort"],
                                   "zeit": z["zeit"], "fehler": z.get("fehler")} for z in zuege],
                        "erwartung": fall.get("erwartung"),
                    })
                    if args.verlauf:
                        args.verlauf.write_text(verlauf_als_markdown(kopf, laeufe), encoding="utf-8")
    finally:
        zuruecksetzen(conn, ausgang, gruppen, ausgang_vektoren)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE (id::text = ANY(%s)) OR (pseudonym = %s "
                        "AND assistant_id = %s AND created_at >= %s)",
                        (konversationen, pseudonym, assistent, beginn))
        for gruppe in messgruppen:
            messgruppe_abbauen(conn, gruppe)
        conn.close()

    print("\nFall                           bestanden  nicht erfüllt")
    for fall in faelle:
        eigene = [e for e in ergebnisse if e["fall"] == fall["id"]]
        gut = sum(e["bestanden"] for e in eigene)
        offen = sorted({n for e in eigene for n, ok in e["kriterien"].items() if not ok})
        print(f"{fall['id']:<30} {gut}/{len(eigene)}        {', '.join(offen) or '—'}")
    gezaehlt = [e for e in ergebnisse if e.get("zaehlung")]
    if gezaehlt:
        print("\nBegriffe je Lauf            genannt (eingef.+angespr.) · Knoten · eingetragen · fehlt im Speicher · verloren")
        for fall in faelle:
            eigene = [e["zaehlung"] for e in gezaehlt if e["fall"] == fall["id"]]
            if not eigene:
                continue
            spalten = [
                " · ".join(f"{len(z['eingefuehrt'])}+{len(z['angesprochen'])}" if z["absatz"] else "–" for z in eigene),
                " · ".join(str(z["knoten"]) for z in eigene),
                " · ".join(str(z["eingetragen"]) for z in eigene),
                " · ".join(str(len(z["fehlt_im_speicher"])) for z in eigene),
                " · ".join(str(len(z["vorhanden_nicht_eingetragen"])) for z in eigene),
            ]
            print(f"{fall['id']:<27} " + "  |  ".join(spalten))
    if args.json:
        args.json.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
