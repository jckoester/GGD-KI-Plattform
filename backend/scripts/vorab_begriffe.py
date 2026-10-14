#!/usr/bin/env python3
"""Prüfsatz „Begriff im Satz" für die Vorab-Suche (0.16, Schritt 1).

    cd backend && venv/bin/python scripts/vorab_begriffe.py --datei scripts/szenarien/vorab_begriffe.yaml \\
        --protokoll vorab-protokoll.md --json vorab.json
    cd backend && venv/bin/python scripts/vorab_begriffe.py --datei scripts/szenarien/vorab_begriffe.yaml \\
        --chats --verlauf chats.md --json chats.json

**Die Frage:** Findet die Vorab-Suche einen Begriff, den eine Schüler:in in einem Satz nennt?
Bis 0.15 nur, wenn die Nachricht kurz ist („Was ist X?"); im Erzählsatz („Letzte Stunde haben
wir etwas über X gelernt …") verwässert der Vektor, und der Begriff rutscht über die Schwelle.

**Was gemessen wird, ist, was läuft:** Das Skript ruft das echte `vorab()` mit einem
Schülerprofil (Stufe aus der Szenariodatei) — ohne Fach und mit Fach, wie im Chat
(`context.service._grundschicht`). „Ohne Fach" heißt hier freier Chat ohne
Unterrichtsgruppen; `eigene_faecher` bleibt leer.

**Die Schwelle abtasten:** Je Nachricht **ein** Embedding; danach läuft `vorab()` je Schwelle
von 0,40 bis 0,52 mit diesem Vektor. Dafür wird `search.VORAB_SCHWELLE` vorübergehend
umgesetzt — `vorab()` liest den Wert bei jedem Aufruf aus dem Modul. Zwei Selbstprüfungen
sichern das ab: Bei der geltenden Schwelle muss dasselbe herauskommen wie ohne Umsetzen, und
über den ganzen Prüfsatz muss sich zwischen 0,40 und 0,52 etwas ändern — sonst bindet
`vorab()` die Schwelle inzwischen anders, und die Abtastung wäre wirkungslos.

**Ausgewertet** (Kriterien abgestimmt mit Jan am 12./13.10.2026, Plan Schritt 1):

* Fachliche Nachrichten: Ist der erwartete Knoten unter den Vorab-Treffern, über welchen Weg
  (Name oder Distanz), mit welcher Distanz — je Form (Stichwort, Frage, Ich-Satz, Erzählsatz).
  Alle weiteren Treffer sind **Nebentreffer**; ob einer stört, entscheidet das Lesen.
* Gegenproben: **Jeder** Treffer ist ein Fehltreffer, nicht nur der nächste. Mit Fachbonus
  steht vorn in der Reihenfolge nicht unbedingt der rohe nächste Treffer.
* Über Fachgrenzen: Begriffe eines **Bezugsfachs** im Chat eines anderen Fachs; bei den
  Gegenproben getrennt ausgewiesen, welche Fehltreffer aus einem Fach **ohne** Bezug kommen.
  Die Bezugsfächer kommen aus der Datenbank (`subjects.bezugsfaecher`, geseedet aus
  `subjects.yaml`) — wie im Chat. Passt ein Fall der Szenariodatei (`bezug`) nicht zu ihnen,
  bricht das Skript ab, statt still etwas anderes zu messen.
* Zeit: `vorab()` bei der geltenden Schwelle, ohne Embedding; das Embedding getrennt.

**Test-Chats** (``--chats``): die Erzählsätze (je Begriff einer, Rahmen reihum), die schulnahen
und die Alltags-Gegenproben als echte Chats in vorübergehenden Messgruppen ohne Stunden — je
Chat Nachricht, Bausteine (vorab/werkzeug), Werkzeugaufrufe, Antwort. Sie werden gelesen, sie
sind kein eigenes Kriterium. Schüler:in ist ein vorhandenes Dev-Konto mit Restbudget und
vorübergehender Mitgliedschaft; ihr Pseudonym wird nicht ausgegeben. Am Ende sind die Gruppen
samt Konversationen gelöscht.

⚠️ Nur für Entwicklungsinstanzen — die Test-Chats stellen eigene Sitzungs-Token aus und
kosten echtes Budget.
"""
import argparse
import asyncio
import importlib.util
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FORMEN = ("stichwort", "frage", "ich", "erzaehlung")
FORM_NAMEN = {"stichwort": "Stichwort", "frage": "Frage", "ich": "Ich-Satz", "erzaehlung": "Erzählsatz"}
GEGENPROBEN = ("beilaeufig", "schulnah", "alltag", "anderes_fach")
SCHWELLEN = tuple(round(0.40 + 0.01 * i, 2) for i in range(13))
PSEUDONYM = "pruefsatz-vorab"
#: Erste Kennung der Messgruppen — daneben liegt die Gruppe der Messung „letzte Stunde" (98016).
GRUPPEN_BASIS = 98160


@dataclass(frozen=True)
class Nachricht:
    text: str
    art: str                         # fachlich | fachgrenze | umschreibung | gegenprobe | grenzfall
    form: str                        # FORMEN, die Art der Gegenprobe, „umschreibung", „grenzfall"
    faecher: tuple                   # Profile: Fach-Slug je Lauf, None = ohne Fach
    erwartet: tuple | None = None    # (Fach-Slug, Titel)
    gruppe: str = ""                 # was der Fall prüft: einwort, alias, mehrdeutig …
    rahmen: int | None = None        # Erzählsatz: Nummer des Rahmens (1–4)
    wort: str = ""                   # Gegenprobe: das reizende Wort aus Titel oder Alias
    bezug: bool = True               # Fachgrenze: hat das Chat-Fach das Begriffsfach als Bezug?
    chat: str | None = None          # Fach der Messgruppe im Test-Chat, None = kein Test-Chat


@dataclass(frozen=True)
class Treffer:
    titel: str
    fach: str | None                 # Slug, None = fachlos
    weg: str                         # name | distanz
    distanz: float | None            # roh — bei Namenstreffern nachgeschlagen


# ── Szenario ─────────────────────────────────────────────────────────────────


def _formen(eintrag: dict, daten: dict) -> list[tuple[str, int | None, str]]:
    """(Form, Rahmen, Text) eines Begriffs — Erzählsätze in **jedem** Rahmen."""
    akk = eintrag["akk"]
    formen = [("stichwort", None, eintrag["stichwort"]), ("frage", None, eintrag["frage"]),
              ("ich", None, eintrag.get("ich") or daten["ich"].format(akk=akk))]
    formen += [("erzaehlung", i, r.format(akk=akk)) for i, r in enumerate(daten["rahmen"], start=1)]
    return formen


def nachrichten(daten: dict) -> list[Nachricht]:
    """Die Szenariodatei als Liste von Nachrichten.

    Im Test-Chat (``chat``) steht je Begriff **ein** Erzählsatz, die Rahmen reihum — die
    Vorab-Messung nimmt alle vier, damit nichts auf einen Satzbau abgestimmt wird.
    """
    liste: list[Nachricht] = []
    n_rahmen = len(daten["rahmen"])
    for fach, eintraege in daten["begriffe"].items():
        for i, e in enumerate(eintraege):
            for form, rahmen, text in _formen(e, daten):
                im_chat = form == "erzaehlung" and rahmen == i % n_rahmen + 1
                liste.append(Nachricht(text, "fachlich", form, (None, fach), (fach, e["titel"]),
                                       e["art"], rahmen, chat=fach if im_chat else None))
    for i, e in enumerate(daten.get("fachgrenzen") or []):
        for form, rahmen, text in _formen(e, daten):
            im_chat = form == "erzaehlung" and rahmen == i % n_rahmen + 1
            liste.append(Nachricht(text, "fachgrenze", form, (e["chat"],), (e["fach"], e["titel"]),
                                   e["art"], rahmen, bezug=e.get("bezug", True),
                                   chat=e["chat"] if im_chat else None))
    for e in daten.get("umschreibungen") or []:
        liste.append(Nachricht(e["satz"], "umschreibung", "umschreibung", (None, e["fach"]),
                               (e["fach"], e["titel"]), chat=e["fach"]))
    proben = daten["gegenproben"]
    for art in ("beilaeufig", "schulnah"):
        faecher = tuple(proben[art]["faecher"])
        for i, satz in enumerate(proben[art]["saetze"]):
            # Beiläufiges misst `vorab_schwelle.py` schon; im Chat nur das Schulnahe, Fach reihum.
            chat = faecher[i % len(faecher)] if art == "schulnah" else None
            liste.append(Nachricht(satz, "gegenprobe", art, (None, *faecher), chat=chat))
    for art in ("alltag", "anderes_fach"):
        for e in proben[art]:
            profile = (None, e["fach"]) if art == "alltag" else (e["fach"],)
            liste.append(Nachricht(e["satz"], "gegenprobe", art, profile, wort=e["wort"], chat=e["fach"]))
    for e in daten.get("grenzfaelle") or []:
        liste.append(Nachricht(e["satz"], "grenzfall", "grenzfall", (None, e["fach"]), wort=e["wort"],
                               chat=e["fach"]))
    return liste


# ── Bewertung — rein, ohne Datenbank ─────────────────────────────────────────


def ist_erwartet(n: Nachricht, t: Treffer) -> bool:
    """Fach **und** Titel: „Ion" aus NwT ist nicht „Ion" aus Chemie. Mehrere Fassungen
    desselben Begriffs im selben Fach (Oxidation, Redoxreaktion) zählen alle."""
    return n.erwartet is not None and (t.fach, t.titel) == n.erwartet


def gefunden(n: Nachricht, treffer: list[Treffer]) -> Treffer | None:
    """Der erwartete Knoten **unter allen** Vorab-Treffern, nicht nur dem ersten."""
    return next((t for t in treffer if ist_erwartet(n, t)), None)


def nebentreffer(n: Nachricht, treffer: list[Treffer]) -> list[Treffer]:
    """Bei Nachrichten mit erwartetem Knoten: alles außer ihm."""
    if n.erwartet is None:
        return []
    return [t for t in treffer if not ist_erwartet(n, t)]


def fehltreffer(n: Nachricht, treffer: list[Treffer]) -> list[Treffer]:
    """Bei Gegenproben ist **jeder** Treffer ein Fehltreffer — über alle bis zu fünf."""
    return list(treffer) if n.art == "gegenprobe" else []


def ohne_bezug(chat_fach: str | None, treffer: list[Treffer], bezug: dict) -> list[Treffer]:
    """Treffer aus einem Fach, das weder das Chat-Fach noch eines seiner Bezugsfächer ist.

    Fachlose Treffer (Methodenblätter) gehören keinem Fach an und zählen nicht; ohne Fach im
    Profil gibt es keinen Bezug, also auch nichts „ohne Bezug"."""
    if chat_fach is None:
        return []
    erlaubt = {chat_fach, *bezug.get(chat_fach, ())}
    return [t for t in treffer if t.fach is not None and t.fach not in erlaubt]


def bezug_abweichungen(liste: list[Nachricht], bezug: dict) -> list[str]:
    """Fälle über Fachgrenzen, deren Angabe `bezug` nicht zu den Bezugsfächern der Instanz
    passt — dann zählte Kriterium 7 einen Grenzfall mit oder ließe einen echten Fall weg."""
    faelle = {(n.faecher[0], n.erwartet, n.bezug) for n in liste if n.art == "fachgrenze"}
    return [f"{titel} ({fach}) im {chat}-Chat: Szenario sagt {'mit' if mit else 'ohne'} Bezug, "
            f"die Instanz {'ohne' if mit else 'mit'}"
            for chat, (fach, titel), mit in sorted(faelle)
            if (fach in bezug.get(chat, ())) != mit]


def _schluessel(t: Treffer) -> tuple:
    return (t.fach, t.titel)


def zaehle(laeufe: list[dict], schwelle: float, bezug: dict) -> dict:
    """Die Kennzahlen einer Schwelle. Ein Lauf ist eine Nachricht in einem Profil."""
    z = {"formen": {f: [0, 0] for f in FORMEN}, "fachgrenze": [0, 0], "umschreibung": [0, 0],
         "gegenproben": [0, 0], "fehltreffer": 0, "ohne_bezug": 0, "nebentreffer": 0}
    for lauf in laeufe:
        n, treffer = lauf["nachricht"], lauf["treffer"][schwelle]
        if n.art == "fachlich":
            z["formen"][n.form][0] += gefunden(n, treffer) is not None
            z["formen"][n.form][1] += 1
        elif n.art == "fachgrenze" and n.bezug:
            z["fachgrenze"][0] += gefunden(n, treffer) is not None
            z["fachgrenze"][1] += 1
        elif n.art == "umschreibung":
            z["umschreibung"][0] += gefunden(n, treffer) is not None
            z["umschreibung"][1] += 1
        elif n.art == "gegenprobe":
            falsch = fehltreffer(n, treffer)
            z["gegenproben"][0] += bool(falsch)
            z["gegenproben"][1] += 1
            z["fehltreffer"] += len(falsch)
            z["ohne_bezug"] += len(ohne_bezug(lauf["profil"], falsch, bezug))
        if n.art in ("fachlich", "fachgrenze"):
            z["nebentreffer"] += len(nebentreffer(n, treffer))
    return z


def neu_hinzu(laeufe: list[dict], vorher: float, nachher: float) -> list[tuple[dict, Treffer, str]]:
    """Was bei ``nachher`` dazukommt, das bei ``vorher`` fehlte: (Lauf, Treffer, Rolle).

    Rolle: „erwartet", „Fehltreffer" (Gegenprobe), „Nebentreffer" (fachlich), sonst „Treffer"
    (Umschreibung, Grenzfall)."""
    neu = []
    for lauf in laeufe:
        n = lauf["nachricht"]
        alt = {_schluessel(t) for t in lauf["treffer"][vorher]}
        for t in lauf["treffer"][nachher]:
            if _schluessel(t) in alt:
                continue
            if ist_erwartet(n, t):
                rolle = "erwartet"
            elif n.art == "gegenprobe":
                rolle = "Fehltreffer"
            elif n.art in ("fachlich", "fachgrenze"):
                rolle = "Nebentreffer"
            else:
                rolle = "Treffer"
            neu.append((lauf, t, rolle))
    return neu


def abtastung_wirkungslos(laeufe: list[dict]) -> bool:
    """Ändert sich zwischen der kleinsten und der größten Schwelle **nirgends** etwas, liest
    `vorab()` die umgesetzte Schwelle nicht mehr — die Abtastung hätte nichts gemessen."""
    return all([_schluessel(t) for t in l["treffer"][SCHWELLEN[0]]]
               == [_schluessel(t) for t in l["treffer"][SCHWELLEN[-1]]] for l in laeufe)


# ── Messung ──────────────────────────────────────────────────────────────────


async def _bestand(db, faecher_im_szenario: set[str]) -> tuple[dict, dict, dict]:
    """Fächer (Slug ↔ ID) und die Vorab-Knoten der Szenariofächer: (Slug, Titel) → IDs."""
    import sqlalchemy as sa

    from app.context.taxonomy import VORAB_TYPEN
    from app.db.models import ContextNode, Subject

    slug_zu_id = {s: i for i, s in (await db.execute(sa.select(Subject.id, Subject.slug))).all()}
    unbekannt = sorted(faecher_im_szenario - set(slug_zu_id))
    if unbekannt:
        raise SystemExit(f"Fächer fehlen auf dieser Instanz: {', '.join(unbekannt)}")
    knoten: dict[tuple, list] = {}
    for kennung, slug, titel in (await db.execute(
        sa.select(ContextNode.id, Subject.slug, ContextNode.title)
        .join(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.status == "active", ContextNode.content_type.in_(VORAB_TYPEN),
               Subject.slug.in_(faecher_im_szenario))
    )).all():
        knoten.setdefault((slug, titel), []).append(kennung)
    return slug_zu_id, {i: s for s, i in slug_zu_id.items()}, knoten


async def _distanzen(db, vektor, kennungen: set) -> dict:
    import sqlalchemy as sa

    from app.db.models import ContextNode

    if not kennungen:
        return {}
    d = ContextNode.embedding.cosine_distance(vektor)
    return {str(k): float(x) for k, x in (await db.execute(
        sa.select(ContextNode.id, d).where(ContextNode.id.in_(kennungen))
    )).all() if x is not None}


async def messen(liste: list[Nachricht], stufe: int) -> tuple[list[dict], dict]:
    import sqlalchemy as sa

    from app.context import search
    from app.context.search import Suchprofil, vektor_oder_none, vorab
    from app.context.service import bezugsfaecher_von
    from app.db.models import Subject
    from app.db.session import AsyncSessionLocal

    geltend = search.VORAB_SCHWELLE
    if geltend not in SCHWELLEN:
        raise SystemExit(f"VORAB_SCHWELLE {geltend} liegt nicht im abgetasteten Bereich.")
    faecher = {f for n in liste for f in n.faecher if f} | {n.erwartet[0] for n in liste if n.erwartet}
    laeufe, vektoren = [], {}
    async with AsyncSessionLocal() as db:
        slug_zu_id, id_zu_slug, knoten = await _bestand(db, faecher)
        fehlend = sorted({n.erwartet for n in liste if n.erwartet} - set(knoten))
        if fehlend:
            raise SystemExit("Erwartete Knoten fehlen: " + ", ".join(f"{t} ({f})" for f, t in fehlend))
        bezug = {s: list(b) for s, b in (await db.execute(
            sa.select(Subject.slug, Subject.bezugsfaecher).order_by(Subject.slug))).all() if b}
        abweichend = bezug_abweichungen(liste, bezug)
        if abweichend:
            raise SystemExit("Bezugsfächer passen nicht zum Szenario:\n  " + "\n  ".join(abweichend))
        bezug_ids = {f: await bezugsfaecher_von(db, slug_zu_id[f]) for f in faecher}

        def als_treffer(t: dict, distanzen: dict) -> Treffer:
            weg = "distanz" if "distanz" in t else "name"
            return Treffer(t["title"], id_zu_slug.get(t.get("subject_id")), weg,
                           t.get("distanz", distanzen.get(t["node_id"])))

        for nr, n in enumerate(liste, start=1):
            if n.text not in vektoren:
                beginn = time.perf_counter()
                v = await vektor_oder_none(n.text)
                if v is None:
                    raise SystemExit(f"Kein Embedding für „{n.text}“ — LiteLLM erreichbar?")
                vektoren[n.text] = (v, (time.perf_counter() - beginn) * 1000)
            v, emb_ms = vektoren[n.text]
            for fach in n.faecher:
                profil = Suchprofil(pseudonym=PSEUDONYM, rollen=("student",),
                                    subject_id=slug_zu_id[fach] if fach else None,
                                    bezugsfaecher=bezug_ids[fach] if fach else (),
                                    grade=stufe, mit_metadaten=True)
                beginn = time.perf_counter()
                heute = await vorab(n.text, profil, db, vektor=v)
                zeit_ms = (time.perf_counter() - beginn) * 1000
                roh = {}
                try:
                    for s in SCHWELLEN:
                        search.VORAB_SCHWELLE = s
                        roh[s] = await vorab(n.text, profil, db, vektor=v)
                finally:
                    search.VORAB_SCHWELLE = geltend
                if [t["node_id"] for t in roh[geltend]] != [t["node_id"] for t in heute]:
                    raise SystemExit(f"Selbstprüfung: Bei {geltend} weicht die Abtastung vom "
                                     f"normalen Aufruf ab („{n.text}“).")
                erwartet_ids = set(knoten.get(n.erwartet, ())) if n.erwartet else set()
                distanzen = await _distanzen(
                    db, v, {t["node_id"] for ts in roh.values() for t in ts} | erwartet_ids)
                laeufe.append({
                    "nachricht": n, "profil": fach,
                    "treffer": {s: [als_treffer(t, distanzen) for t in ts] for s, ts in roh.items()},
                    "d_erwartet": min((distanzen[str(k)] for k in erwartet_ids if str(k) in distanzen),
                                      default=None),
                    "zeit_ms": zeit_ms, "emb_ms": emb_ms,
                })
            if nr % 25 == 0:
                print(f"  {nr}/{len(liste)} Nachrichten", flush=True)
    if abtastung_wirkungslos(laeufe):
        raise SystemExit("Selbstprüfung: Zwischen 0,40 und 0,52 ändert sich nichts — liest "
                         "vorab() die Schwelle noch aus dem Modul?")
    return laeufe, {"schwelle": geltend, "bezug": bezug}


# ── Protokoll ────────────────────────────────────────────────────────────────


def _d(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}".replace(".", ",")


def _anteil(paar: list[int]) -> str:
    gef, ges = paar
    return f"{gef}/{ges}" + (f" ({100 * gef / ges:.0f} %)" if ges else "")


def _treffer_text(t: Treffer) -> str:
    return f"{t.titel} ({t.fach or 'fachlos'}, {'Name' if t.weg == 'name' else _d(t.distanz)})"


def _profil(p: str | None) -> str:
    return p or "ohne Fach"


def protokoll_als_markdown(kopf: dict, laeufe: list[dict], bezug: dict) -> str:
    s0 = kopf["schwelle"]
    z = zaehle(laeufe, s0, bezug)
    zeiten = [l["zeit_ms"] for l in laeufe]
    emb = list({l["nachricht"].text: l["emb_ms"] for l in laeufe}.values())
    teile = [
        f"# Vorab-Prüfsatz „Begriff im Satz“ — {kopf['beginn']}", "",
        f"Datei `{kopf['datei']}` · `VORAB_SCHWELLE` {_d(s0)} · Profil Schüler:in, Stufe {kopf['stufe']}, "
        f"ohne Fach und mit Fach · {len({l['nachricht'].text for l in laeufe})} Nachrichten, {len(laeufe)} Läufe.",
        "", "**Bestand (Vorab-Typen je Fach):** " + kopf["bestand"], "",
        "**Bezugsfächer (`subjects.bezugsfaecher` der Instanz):** "
        + "; ".join(f"{f} → {', '.join(b)}" for f, b in bezug.items()), "",
        f"**Zeit:** `vorab()` ohne Embedding Median {statistics.median(zeiten):.1f} ms "
        f"(90. Perzentil {statistics.quantiles(zeiten, n=10)[-1]:.1f} ms); Embedding Median "
        f"{statistics.median(emb):.0f} ms.", "",
        f"## Ausgangswerte bei {_d(s0)}", "",
        "| Kriterium | Wert |", "|---|---|",
        f"| 1 Erzählsätze — erwarteter Knoten unter den Treffern | {_anteil(z['formen']['erzaehlung'])} |",
        *[f"| 2 {FORM_NAMEN[f]} — gefunden (je Fall, Liste unten) | {_anteil(z['formen'][f])} |"
          for f in ("stichwort", "frage", "ich")],
        f"| 3 Gegenproben mit Treffer · Fehltreffer gesamt | {_anteil(z['gegenproben'])} · {z['fehltreffer']} |",
        f"| 4 Nebentreffer bei fachlichen Nachrichten | {z['nebentreffer']} |",
        f"| 6 Zeit `vorab()` Median | {statistics.median(zeiten):.1f} ms |",
        f"| 7 Fachgrenze mit Bezug — gefunden | {_anteil(z['fachgrenze'])} |",
        f"| 7 Fehltreffer aus einem Fach ohne Bezug | {z['ohne_bezug']} |",
        f"| — Umschreibungen (keinem Kriterium zugeordnet) | {_anteil(z['umschreibung'])} |", "",
        "## Abtastung", "",
        "| Schwelle | Stichwort | Frage | Ich-Satz | Erzählsatz | Fachgrenze | Umschreibung "
        "| Gegenproben mit Treffer | Fehltreffer | davon ohne Bezug | Nebentreffer |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in SCHWELLEN:
        zs = zaehle(laeufe, s, bezug)
        f = zs["formen"]
        teile.append(
            f"| {'**' + _d(s) + '**' if s == s0 else _d(s)} | {_anteil(f['stichwort'])} | {_anteil(f['frage'])} "
            f"| {_anteil(f['ich'])} | {_anteil(f['erzaehlung'])} | {_anteil(zs['fachgrenze'])} "
            f"| {_anteil(zs['umschreibung'])} | {_anteil(zs['gegenproben'])} | {zs['fehltreffer']} "
            f"| {zs['ohne_bezug']} | {zs['nebentreffer']} |")
    teile += ["", "### Was je Schwelle dazukommt", "",
              "Gegenüber der nächstkleineren Schwelle; bei 0,40 alles, was dort schon trifft. "
              "Ob ein Nebentreffer stört oder passt, entscheidet das Lesen.", ""]
    for i, s in enumerate(SCHWELLEN):
        if i == 0:
            neu = [(l, t, r) for l in laeufe for t, r in
                   ((t, "erwartet" if ist_erwartet(l["nachricht"], t) else
                     "Fehltreffer" if l["nachricht"].art == "gegenprobe" else
                     "Nebentreffer" if l["nachricht"].art in ("fachlich", "fachgrenze") else "Treffer")
                    for t in l["treffer"][s])]
        else:
            neu = neu_hinzu(laeufe, SCHWELLEN[i - 1], s)
        teile.append(f"**{_d(s)}**" + (" (geltend)" if s == s0 else ""))
        teile.append("")
        for rolle in ("Fehltreffer", "Nebentreffer", "erwartet", "Treffer"):
            gesammelt: dict[tuple, list] = {}
            for lauf, t, r in neu:
                if r == rolle:
                    gesammelt.setdefault((lauf["nachricht"].text, _treffer_text(t)), []).append(
                        _profil(lauf["profil"]))
            if not gesammelt:
                continue
            if rolle == "erwartet":
                teile.append(f"- erwartet gefunden: {len(gesammelt)} Nachricht(en)")
                continue
            teile.append(f"- {rolle}:")
            teile += [f"  - „{text}“ → {tt} — {', '.join(p)}" for (text, tt), p in gesammelt.items()]
        teile.append("")

    teile += [f"## Alle Nachrichten bei {_d(s0)}", ""]
    abschnitte = [("fachlich", "Fachliche Nachrichten"), ("fachgrenze", "Über Fachgrenzen"),
                  ("umschreibung", "Umschreibungen"), ("gegenprobe", "Gegenproben"),
                  ("grenzfall", "Grenzfälle")]
    for art, titel in abschnitte:
        eigene = [l for l in laeufe if l["nachricht"].art == art]
        if not eigene:
            continue
        teile += [f"### {titel}", ""]
        if art == "gegenprobe" or art == "grenzfall":
            teile += ["| Art | Nachricht | Wort | Profil | Treffer |", "|---|---|---|---|---|"]
            for l in eigene:
                n = l["nachricht"]
                teile.append(f"| {n.form} | {n.text} | {n.wort or '—'} | {_profil(l['profil'])} | "
                             f"{' · '.join(_treffer_text(t) for t in l['treffer'][s0]) or '—'} |")
        else:
            teile += ["| Erwartet | Was | Form | Nachricht | Profil | gefunden | d(erwartet) | weitere Treffer |",
                      "|---|---|---|---|---|---|---|---|"]
            for l in eigene:
                n = l["nachricht"]
                treffer = l["treffer"][s0]
                g = gefunden(n, treffer)
                was = n.gruppe + ("" if n.bezug else ", ohne Bezug")
                form = FORM_NAMEN.get(n.form, n.form) + (f" {n.rahmen}" if n.rahmen else "")
                teile.append(
                    f"| {n.erwartet[1]} ({n.erwartet[0]}) | {was} | {form} | {n.text} | {_profil(l['profil'])} "
                    f"| {('✓ ' + ('Name' if g.weg == 'name' else 'Distanz')) if g else '✗'} | {_d(l['d_erwartet'])} "
                    f"| {' · '.join(_treffer_text(t) for t in nebentreffer(n, treffer)) or '—'} |")
        teile.append("")
    return "\n".join(teile)


def als_json(laeufe: list[dict]) -> list[dict]:
    return [{
        "text": l["nachricht"].text, "art": l["nachricht"].art, "form": l["nachricht"].form,
        "gruppe": l["nachricht"].gruppe, "rahmen": l["nachricht"].rahmen,
        "erwartet": l["nachricht"].erwartet, "bezug": l["nachricht"].bezug, "wort": l["nachricht"].wort,
        "profil": l["profil"], "d_erwartet": l["d_erwartet"], "zeit_ms": l["zeit_ms"], "emb_ms": l["emb_ms"],
        "treffer": {f"{s:.2f}": [t.__dict__ for t in ts] for s, ts in l["treffer"].items()},
    } for l in laeufe]


async def _bestand_text() -> str:
    import sqlalchemy as sa

    from app.context.taxonomy import VORAB_TYPEN
    from app.db.models import ContextNode, Subject
    from app.db.session import AsyncSessionLocal

    fach = sa.func.coalesce(Subject.slug, "fachlos").label("fach")
    async with AsyncSessionLocal() as db:
        zeilen = (await db.execute(
            sa.select(fach, ContextNode.content_type, sa.func.count())
            .outerjoin(Subject, Subject.id == ContextNode.subject_id)
            .where(ContextNode.status == "active", ContextNode.content_type.in_(VORAB_TYPEN),
                   ContextNode.content_type != "operator")
            .group_by(fach, ContextNode.content_type).order_by(fach, ContextNode.content_type))).all()
        operatoren = (await db.execute(sa.select(sa.func.count()).where(
            ContextNode.status == "active", ContextNode.content_type == "operator"))).scalar()
    return ", ".join(f"{f} {t} {n}" for f, t, n in zeilen) + f"; Operatoren {operatoren}"


# ── Test-Chats ───────────────────────────────────────────────────────────────


def _lade(name: str):
    """`scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden."""
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _zitat(text: str) -> str:
    return "\n".join(f"> {z}" if z else ">" for z in (text or "*(leer)*").splitlines())


def verlauf_als_markdown(kopf: dict, chats: list[dict]) -> str:
    teile = [f"# Test-Chats „Begriff im Satz“ — {kopf['beginn']}", "",
             f"Chat ohne Assistent, als Schüler:in Stufe {kopf['stufe']}, in einer Messgruppe des Fachs · "
             f"Modell {kopf['modell']} · Datei `{kopf['datei']}`. Gelesen, kein eigenes Kriterium.", ""]
    for c in chats:
        n = c["nachricht"]
        kopfzeile = (f"{n.erwartet[1]} ({n.erwartet[0]}) · {n.gruppe}" if n.erwartet
                     else f"Gegenprobe {n.form} · Wort „{n.wort}“" if n.wort else f"Gegenprobe {n.form}")
        teile += ["---", "", f"## {c['nr']}. {kopfzeile} · Gruppe {c['fach']}", "",
                  f"**Schüler:in:** {n.text}", ""]
        if "grund" in c:
            teile += [f"abgebrochen — {c['grund']}", ""]
            continue
        if n.erwartet:
            herkunft = sorted({b["herkunft"] for b in c["bausteine"] if b["titel"] == n.erwartet[1]})
            teile.append(f"- Erwarteter Knoten: {'✓ ' + ', '.join(herkunft) if herkunft else '✗ fehlt'}")
        teile += [f"- Werkzeuge: {' → '.join(c['werkzeuge']) or '—'}",
                  f"- Bausteine: {', '.join(b['titel'] + ' (' + b['herkunft'] + ')' for b in c['bausteine']) or '—'}",
                  "", _zitat(c["antwort"]), ""]
    return "\n".join(teile)


def chats_fahren(args, daten: dict, liste: list[Nachricht]) -> list[dict]:
    import httpx

    from app.auth.dependencies import get_jwt_service
    from app.config import settings
    from app.context.embedding import vor_einer_messung
    from app.context.taxonomy import VORAB_TYPEN

    letzte = _lade("letzte_stunde_messung")
    entfall, chat_probe = letzte.entfall, letzte.chat_probe
    auswahl = [n for n in liste if n.chat]
    faecher = sorted({n.chat for n in auswahl})
    gruppen = {f: {"id": GRUPPEN_BASIS + i, "name": f"Messung Vorab {f}"} for i, f in enumerate(faecher)}
    conn = entfall.verbindung()
    schueler, _ = letzte.schuelerin(conn, mindestens=args.mindestbudget)
    token = get_jwt_service().issue(pseudonym=schueler, roles=["student"], grade=str(daten["stufe"]))[0]
    client = httpx.Client(base_url=args.basis, timeout=300.0, headers={"Cookie": f"session={token}"})
    kopf = {"datei": args.datei.name, "beginn": datetime.now().strftime("%d.%m.%Y, %H:%M"),
            "stufe": daten["stufe"], "modell": "?"}
    ergebnisse: list[dict] = []
    asyncio.run(vor_einer_messung(VORAB_TYPEN, trotzdem=args.trotzdem))
    try:
        for fach, g in gruppen.items():
            entfall.abbauen(conn, g)
            fach_id = entfall._eins(conn, "SELECT id FROM subjects WHERE slug = %s", fach)
            with conn.cursor() as cur:
                cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                            "VALUES (%s, %s, %s, 'teaching_group', %s)",
                            (g["id"], g["name"], f"messung-vorab-{g['id']}", fach_id))
                cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                            "VALUES (%s, %s, 'student', 'manuell')", (g["id"], schueler))
        for nr, n in enumerate(auswahl, start=1):
            eintrag = {"nr": nr, "nachricht": n, "fach": n.chat}
            try:
                zug = chat_probe.frage_stellen(client, n.text, assistent=None, gruppe=gruppen[n.chat]["id"])
            except (httpx.HTTPError, SystemExit) as fehler:
                eintrag["grund"] = f"{type(fehler).__name__}: {str(fehler)[:200]}"
                print(f"{nr:>3}  abgebrochen — {eintrag['grund']}", flush=True)
                ergebnisse.append(eintrag)
                continue
            kopf["modell"] = zug.get("modell") or kopf["modell"]
            eintrag.update(antwort=zug["antwort"], bausteine=letzte.bausteine(conn, zug["konversation"]),
                           werkzeuge=[w["tool"] for w in zug["werkzeuge"]], fehler=zug.get("fehler"))
            treffer = ""
            if n.erwartet:
                treffer = "✓" if any(b["titel"] == n.erwartet[1] for b in eintrag["bausteine"]) else "✗"
            print(f"{nr:>3}  {treffer:<2}{n.text[:60]:<62} {len(eintrag['bausteine'])} Bausteine, "
                  f"{len(eintrag['werkzeuge'])} Werkzeuge", flush=True)
            ergebnisse.append(eintrag)
            if args.verlauf:
                args.verlauf.write_text(verlauf_als_markdown(kopf, ergebnisse), encoding="utf-8")
    finally:
        for g in gruppen.values():
            entfall.abbauen(conn, g)
        client.close()
        conn.close()
    if args.verlauf:
        args.verlauf.write_text(verlauf_als_markdown(kopf, ergebnisse), encoding="utf-8")
    return ergebnisse


# ── Aufruf ───────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Prüfsatz „Begriff im Satz“ für die Vorab-Suche")
    p.add_argument("--datei", type=Path, required=True)
    p.add_argument("--protokoll", type=Path, default=None, help="Vorab-Protokoll als Markdown")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--chats", action="store_true", help="Test-Chats statt Vorab-Messung")
    p.add_argument("--verlauf", type=Path, default=None, help="Test-Chats als Markdown")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--mindestbudget", type=float, default=1.5,
                   help="Restbudget (USD), das das Konto für die Test-Chats noch haben muss")
    p.add_argument("--trotzdem", action="store_true", help="auch ohne vollständige Vektoren")
    args = p.parse_args()

    from app.config import settings
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")

    daten = yaml.safe_load(args.datei.read_text(encoding="utf-8"))
    liste = nachrichten(daten)

    if args.chats:
        ergebnisse = chats_fahren(args, daten, liste)
        if args.json:
            args.json.write_text(json.dumps(
                [{**{k: v for k, v in e.items() if k != "nachricht"}, "text": e["nachricht"].text,
                  "art": e["nachricht"].art, "form": e["nachricht"].form, "erwartet": e["nachricht"].erwartet}
                 for e in ergebnisse], ensure_ascii=False, indent=2), encoding="utf-8")
        return

    from app.context.embedding import vor_einer_messung
    from app.context.taxonomy import VORAB_TYPEN

    async def lauf():
        await vor_einer_messung(VORAB_TYPEN, trotzdem=args.trotzdem)
        laeufe, kopf = await messen(liste, daten["stufe"])
        kopf["bestand"] = await _bestand_text()
        return laeufe, kopf

    laeufe, kopf = asyncio.run(lauf())
    kopf.update(datei=args.datei.name, beginn=datetime.now().strftime("%d.%m.%Y, %H:%M"), stufe=daten["stufe"])
    bezug = kopf["bezug"]
    z = zaehle(laeufe, kopf["schwelle"], bezug)
    print(f"\nbei {_d(kopf['schwelle'])}: " + " · ".join(
        f"{FORM_NAMEN[f]} {_anteil(z['formen'][f])}" for f in FORMEN))
    print(f"Fachgrenze {_anteil(z['fachgrenze'])} · Umschreibung {_anteil(z['umschreibung'])} · "
          f"Gegenproben mit Treffer {_anteil(z['gegenproben'])}, Fehltreffer {z['fehltreffer']} "
          f"(ohne Bezug {z['ohne_bezug']}) · Nebentreffer {z['nebentreffer']}")
    if args.protokoll:
        args.protokoll.write_text(protokoll_als_markdown(kopf, laeufe, bezug), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps({"kopf": kopf, "laeufe": als_json(laeufe)}, ensure_ascii=False,
                                        indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
