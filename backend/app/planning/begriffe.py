"""Begriffe der Stunde — was Leiste, Werkzeug und Vorschlag gemeinsam brauchen (0.18).

Bis 0.17 lag der Abgleich allein im Werkzeugmodul (`assistant_tools.py`). Mit der Leiste,
die Aliase einzeln bearbeitet, und dem Vorschlag aus den Phasentexten braucht ihn mehr als
ein Weg (Plan „Begriffe aus den Phasentexten", Schritte 3 und 5):

* **Abgleich** — ein Name zu einem Knoten (`begriff_zum_titel`), Aliase in der Schreibweise
  des Speichers (`aliase_des_begriffs`, `nur_aliase_des_knotens`).
* **Vorschlag** — ein eigener kleiner Modellaufruf bestimmt die Begriffe aus den
  Phasentexten (`begriffe_vorschlagen`). Anleitung, Nachrichtenformat und Kandidatenzahl
  sind die des Vorlaufs, der bestand (`chat-schnell`, 5 Kandidaten; Plan § 9). Wer sie
  ändert, misst neu.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.context import aliase as aliase_modul
from app.db.models import ContextNode, LessonSlot, NodeAlias, Subject, ohne_aenderungsstempel
from app.planning.schemas import BEGRIFF_TYPEN, LessonRefItem

logger = logging.getLogger(__name__)

#: Bindestriche, die ein Modell statt „-" schreibt. `gpt-oss-120b` setzt durchweg den
#: geschützten Bindestrich U+2011 („Arenium‑Ion") — in Messung 3 (0.17) scheiterten daran
#: alle Begriffe zweier Läufe, obwohl sie als Alias bestanden. Nur auf der Seite des Modells
#: ersetzt: Die Normalisierung der Datenbankseite ist die des Index (`titel_normalisiert_sql`)
#: und muss es bleiben. Das weiche Trennzeichen U+00AD fällt weg.
BINDESTRICHE = str.maketrans({"‐": "-", "‑": "-", "­": None})


# ── Abgleich ─────────────────────────────────────────────────────────────────


async def begriff_zum_titel(db: AsyncSession, user, titel: str, fassung: str | None,
                            stunde: ContextNode) -> tuple[ContextNode | None, str | None]:
    """Ein Begriff der Stunde über seinen Titel oder Alias. → (Knoten, Grund, warum keiner)

    Gesucht wird im Fach der Stunde und seinen Bezugsfächern, normalisiert wie die
    Namenssuche (`normalisiere_titel`, derselbe Ausdruck wie ihr Index), nur unter dem, was
    `user` lesen darf. Gibt es den Namen in beiden, gilt das eigene Fach; gibt es ihn in
    mehreren Fassungen, entscheidet `fassung`.

    Trifft der Name nichts, gilt eine Einzahlform (`einzahlformen`: „Blattfarbstoffe" →
    Alias „Blattfarbstoff") — aber nur, wenn sie genau einen Begriff trifft.
    """
    from app.context.aliase import ALIAS_NORMALISIERT
    from app.context.filters import TITEL_NORMALISIERT
    from app.context.lookup import einzahlformen, normalisiere_titel
    from app.context.service import bezugsfaecher_von
    from app.context.visibility import read_scope_clause

    if stunde.subject_id is None:
        return None, f"„{titel}“: Die Stunde hat kein Fach."
    faecher = (stunde.subject_id, *await bezugsfaecher_von(db, stunde.subject_id))

    async def suche(schluessel: list[str]) -> list[ContextNode]:
        treffer = list((await db.execute(
            sa.select(ContextNode).where(
                ContextNode.content_type.in_(BEGRIFF_TYPEN),
                ContextNode.status == "active",
                read_scope_clause(user.sub, getattr(user, "roles", None) or ()),
                ContextNode.subject_id.in_(faecher),
                sa.or_(
                    TITEL_NORMALISIERT.in_(schluessel),
                    ContextNode.id.in_(sa.select(NodeAlias.node_id).where(ALIAS_NORMALISIERT.in_(schluessel))),
                ),
            ).order_by(ContextNode.id)
        )).scalars())
        if fassung:
            gewuenscht = fassung.translate(BINDESTRICHE).strip().casefold()
            treffer = [t for t in treffer
                       if str((t.metadata_ or {}).get("fassung") or "").strip().casefold() == gewuenscht]
        if len(treffer) > 1:
            eigene = [t for t in treffer if t.subject_id == stunde.subject_id]
            if len(eigene) == 1:
                treffer = eigene
        return treffer

    schluessel = normalisiere_titel(titel.translate(BINDESTRICHE))
    treffer = await suche([schluessel])
    if not treffer and (formen := einzahlformen(schluessel)):
        einzahl = await suche(formen)
        if len(einzahl) == 1:
            return einzahl[0], None
    if len(treffer) == 1:
        return treffer[0], None
    if not treffer:
        return None, (f"„{titel}“ gibt es im Wissensspeicher des Fachs nicht — nicht eingetragen. "
                      "Die Fachschaft kann den Begriff anlegen.")
    fassungen = ", ".join(sorted({str((t.metadata_ or {}).get("fassung") or "ohne Fassung") for t in treffer}))
    return None, f"„{titel}“ gibt es mehrfach ({fassungen}) — mit fassung angeben, welcher gemeint ist."


async def aliase_des_begriffs(db: AsyncSession, knoten: ContextNode, namen: list[str]) -> list[str]:
    """Welche der Namen Aliase dieses Begriffs sind — in der Schreibweise des Speichers.

    Der Titel selbst zählt nicht, ebenso wenig ein Name, der zu keinem Alias passt: Das
    Modell kann keinen Alias erfinden, der dann in der Leiste stünde. Wie beim Nachschlagen
    gilt im Zweifel die Einzahl („Blattfarbstoffe" → „Blattfarbstoff").
    """
    from app.context.aliase import ALIAS_NORMALISIERT
    from app.context.lookup import einzahlformen, normalisiere_titel

    titel = normalisiere_titel(knoten.title or "")
    gesucht = [s for s in (normalisiere_titel(str(n).translate(BINDESTRICHE)) for n in namen if n)
               if s and s != titel]
    if not gesucht:
        return []
    alle = list(dict.fromkeys(f for s in gesucht for f in (s, *einzahlformen(s))))
    gefunden = dict((await db.execute(
        sa.select(ALIAS_NORMALISIERT, NodeAlias.alias)
        .where(NodeAlias.node_id == knoten.id, ALIAS_NORMALISIERT.in_(alle))
    )).all())
    aliase = []
    for s in gesucht:
        if s in gefunden:
            aliase.append(gefunden[s])
            continue
        formen = einzahlformen(s)
        if titel in formen:                  # „Chromatografien" — der Titel in der Mehrzahl
            continue
        aliase += [gefunden[f] for f in formen if f in gefunden][:1]
    return list(dict.fromkeys(aliase))


async def nur_aliase_des_knotens(db: AsyncSession, refs: list[LessonRefItem]) -> list[LessonRefItem]:
    """Aliase an Begriffen auf die beschränken, die der Knoten wirklich hat — in dessen
    Schreibweise; Kompetenzen tragen keine.

    `PATCH /planning/lessons` übernahm bis 0.18 `aliase` ungeprüft vom Client. Die Leiste
    schickt nur gespeicherte Schreibweisen (entfernen, oder das Alias, über das die Suche
    traf) — alles andere wäre ein erfundener Name, der dann in Leiste, Export und
    Klassenarbeits-Umfang stünde. Strenger als der Abgleich des Werkzeugs: kein
    Einzahl-Rückfall, denn den braucht nur ein Modell, das frei formuliert.
    """
    mit_aliasen = [r.node_id for r in refs if r.typ == "concept" and r.aliase]
    bekannt = await aliase_modul.lade_viele(db, mit_aliasen)
    ergebnis = []
    for ref in refs:
        if not ref.aliase:
            ergebnis.append(ref)
            continue
        if ref.typ != "concept":
            ergebnis.append(ref.model_copy(update={"aliase": []}))
            continue
        je_form = {aliase_modul.normalisiere(a): a for a in bekannt.get(ref.node_id, [])}
        geprueft = [je_form[f] for f in (aliase_modul.normalisiere(a) for a in ref.aliase) if f in je_form]
        ergebnis.append(ref.model_copy(update={"aliase": list(dict.fromkeys(geprueft))}))
    return ergebnis


# ── Begriffe früherer Stunden (F1) ───────────────────────────────────────────

#: Was Leiste und Assistent zu den Begriffen früherer Stunden sagen (Plan F1, Jan 18.10.2026):
#: eine Planungshilfe, kein Lernstand. Nirgends „bekannt".
HINWEIS_FRUEHER = (
    "Nur, was in früheren Stunden dieser Gruppe auf der Plattform eingetragen ist — kein "
    "Lernstand: Fehlt ein Begriff hier, kann die Klasse ihn trotzdem kennen."
)


async def fruehere_begriffe(db: AsyncSession, stunde: ContextNode) -> list[dict]:
    """Die Begriffe, die in früheren Stunden der Gruppe eingetragen sind — je Knoten einmal,
    mit dem Datum der ersten Stunde, in der er steht.

    „Früher" heißt: ein Termin der Gruppe vor dem Termin dieser Stunde (Plan F1 b — die
    Gruppe, nicht die Einheit: Am Schuljahresanfang hat kaum eine Stunde eine Einheit). Ohne
    Termin gibt es kein „früher".
    """
    gruppe = stunde.write_scope_group_id
    if gruppe is None:
        return []
    eigener = (await db.execute(
        sa.select(LessonSlot.date).where(LessonSlot.stunde_node_id == stunde.id)
        .order_by(LessonSlot.date).limit(1)
    )).scalar_one_or_none()
    if eigener is None:
        return []
    zeilen = (await db.execute(
        sa.select(LessonSlot.date, ContextNode.metadata_)
        .join(ContextNode, ContextNode.id == LessonSlot.stunde_node_id)
        .where(LessonSlot.group_id == gruppe, LessonSlot.date < eigener,
               ContextNode.status == "active", ContextNode.id != stunde.id)
        .order_by(LessonSlot.date)
    )).all()
    gesehen: dict[str, dict] = {}
    for datum, meta in zeilen:
        for ref in (meta or {}).get("refs") or []:
            if ref.get("typ") == "concept" and ref.get("node_id") and str(ref["node_id"]) not in gesehen:
                gesehen[str(ref["node_id"])] = {"node_id": str(ref["node_id"]), "titel": ref.get("titel"),
                                                "datum": datum.isoformat()}
    return list(gesehen.values())


# ── Vorschlag aus den Phasentexten ───────────────────────────────────────────

#: Unter diesem Schlüssel liegt der Vorschlag in den Metadaten der Stunde (Plan F3 a).
SCHLUESSEL = "begriffe_vorschlag"
#: Kandidaten aus dem Wissensspeicher als Schreibhilfe — 5 hat den Vorlauf bestanden, 15 nicht
#: (Plan § 9: Chemie 15/18), ohne Liste fand das Modell die Schreibweise des Speichers nicht.
KANDIDATEN_ANZAHL = 5

#: Die Anleitung des Vorlaufs (Plan § 9, `Messungen-0.18/vorlauf/ergebnisse.json`), wörtlich.
ANLEITUNG = """Du bestimmst die Fachbegriffe einer Unterrichtsstunde aus ihrem Entwurf. Du antwortest nur mit JSON.

Was ein Fachbegriff ist: ein Wort, das die Fachschaft in ein Glossar des Fachs aufnehmen würde und das Schüler:innen am Ende der Einheit erklären oder korrekt verwenden sollen — Größen, Gesetze, Stoffe, Verfahren, Geräte, Modelle („Dichte“, „Mesomerie“, „Bürette“, „Hebelgesetz“). Keine Fachbegriffe sind Sozialformen, Methoden und Unterrichtsvokabular („Gruppenpuzzle“, „Merksatz“, „Arbeitsblatt“) sowie Alltagswörter ohne fachliche Bedeutung. Chemikalien, Geräte und Material zählen nur, wenn die Stunde ihren Begriff oder ihr Prinzip selbst zum Gegenstand macht: „Katalysator“ ja, wenn erklärt wird, was er tut; „Brom“ und „FeBr₃“ nicht, wenn sie nur im Reagenzglas sind. Auch Grundbegriffe zählen — gerade die werden leicht als selbstverständlich übergangen.

Welche Begriffe: alle, die in dieser Stunde zum ersten Mal auftreten — gleich ob die Stunde sie einführt (definiert, erarbeitet, gesichert) oder nur anspricht (fällt im Gespräch, steht in einer Aufgabe oder im Material, wird aber nicht erklärt). Nicht dazu gehören Begriffe, die die Schüler:innen aus früheren Stunden kennen und hier nur wiederholen oder anwenden: Steht in einer Phase „Wiederholung“, „wiederholen“ oder „bekannt“, sind ihre Begriffe nicht neu. Unter „Begriffe früherer Stunden“ steht, was in früheren Stunden dieser Gruppe auf der Plattform eingetragen ist; diese Begriffe sind nicht neu. Das ist nicht alles, was die Klasse kennt — was dort fehlt, beurteilst du nach dem Entwurf.

Vorgehen: Geh Phase für Phase durch, in der Reihenfolge des Entwurfs. Notiere jeden Fachbegriff, der dort vorkommt oder den die Schüler:innen brauchen, um die Aufgabe zu lösen. Ein Begriff zählt bei der Phase, in der er zuerst auftritt. Steht ein Begriff unter den Kandidaten — als Titel oder Alias —, übernimm diese Schreibweise. Was nicht in der Stunde vorkommt, nennst du nicht, auch wenn es unter den Kandidaten steht. Unterbegriffe nennst du einzeln („σ-Komplex“, „mobile Phase“).

Antwortformat: {"begriffe": [{"name": "…", "phase": "…", "art": "eingeführt" | "angesprochen"}]}"""


def phase_kurz(p: dict) -> str:
    """Eine Phase in einer Zeile, wie im Vorlauf: „Name (10′, kern, PA) — Beschreibung"."""
    def eintrag(feld):
        e = p.get(feld) or {}
        return e.get("titel") or e.get("wert") or ""
    teile = [f"{p.get('dauer_min')}′" if p.get("dauer_min") is not None else "ohne Dauer",
             p.get("prio") or "kern"]
    teile += [t for t in (eintrag("sozialform"), eintrag("methode")) if t]
    zeile = f"{p.get('name')} ({', '.join(teile)})"
    beschreibung = " / ".join(z.strip() for z in (p.get("beschreibung") or "").splitlines() if z.strip())
    return zeile + (f" — {beschreibung}" if beschreibung else "")


def entwurfstext(titel: str, meta: dict) -> str:
    """Der Entwurf als Text — Eingabe des Aufrufs, Vergleichstext der Kandidaten und Grundlage
    der Prüfsumme."""
    zeilen = [f"Stunde: „{titel}“", f"Stundenziel: {meta.get('stundenziel') or '—'}", "Phasen:"]
    return "\n".join(zeilen + [f"- {phase_kurz(p)}" for p in meta.get("phasen") or []])


def pruefsumme(text: str) -> str:
    """Woran die Leiste erkennt, dass sich der Entwurf seit dem Vorschlag geändert hat."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def nachricht(kontext: str, frueher: list[str], kandidaten: list[dict], text: str) -> str:
    """Die Nachricht an das Modell — dasselbe Format wie im Vorlauf."""
    teile = [kontext, f"Begriffe früherer Stunden dieser Gruppe: {', '.join(frueher) or 'keine eingetragen'}", ""]
    if kandidaten:
        teile += ["Kandidaten aus dem Wissensspeicher (Schreibhilfe, keine Auswahl):",
                  *(f"- {k['titel']}" + (f" (Aliase: {', '.join(k['aliase'])})" if k["aliase"] else "")
                    for k in kandidaten), ""]
    return "\n".join(teile + [text])


def lies_antwort(inhalt: str) -> list[dict] | None:
    """Die Begriffe aus der Antwort — oder `None`, wenn sie kein lesbares JSON ist."""
    treffer = re.search(r"\{.*\}", inhalt or "", re.S)
    if not treffer:
        return None
    try:
        daten = json.loads(treffer.group(0))
    except json.JSONDecodeError:
        return None
    begriffe = daten.get("begriffe") if isinstance(daten, dict) else None
    if not isinstance(begriffe, list):
        return None
    return [b for b in begriffe if isinstance(b, dict) and str(b.get("name") or "").strip()]


async def kandidaten(db: AsyncSession, user, text: str, faecher: tuple[int, ...]) -> list[dict]:
    """Die nächsten Begriffe zum Entwurf nach Vektor — wie im Vorlauf, aber nur Lesbares.
    Ohne Vektor (Einbettungsdienst weg) keine Kandidaten; der Aufruf läuft trotzdem."""
    from app.context.search import vektor_oder_none
    from app.context.visibility import read_scope_clause

    vektor = await vektor_oder_none(text)
    if vektor is None:
        return []
    treffer = (await db.execute(
        sa.select(ContextNode.id, ContextNode.title).where(
            ContextNode.content_type.in_(BEGRIFF_TYPEN), ContextNode.status == "active",
            read_scope_clause(user.sub, getattr(user, "roles", None) or ()),
            ContextNode.subject_id.in_(faecher), ContextNode.embedding.is_not(None),
        ).order_by(ContextNode.embedding.cosine_distance(vektor), ContextNode.id).limit(KANDIDATEN_ANZAHL)
    )).all()
    je_knoten = await aliase_modul.lade_viele(db, [t[0] for t in treffer])
    return [{"titel": t, "aliase": sorted(je_knoten.get(i, []))} for i, t in treffer]


async def _kontext(db: AsyncSession, stunde: ContextNode) -> str:
    from app.planning.curriculum_resolver import group_grade

    fach = await db.get(Subject, stunde.subject_id) if stunde.subject_id else None
    teile = [f"Fach: {fach.name}" if fach else "Fach: —"]
    if stunde.write_scope_group_id and (stufe := await group_grade(db, stunde.write_scope_group_id)):
        teile.append(f"Jahrgang: Klasse {stufe}")
    return " · ".join(teile)


async def vorschlag_ablegen(db: AsyncSession, stunde_id: UUID, vorschlag: dict) -> None:
    """Nur den eigenen Schlüssel schreiben — per `jsonb_set`, ohne `updated_at` zu berühren.

    Der Aufruf dauert Sekunden. Schriebe er die ganzen Metadaten zurück, überschriebe er,
    was die Lehrkraft inzwischen gespeichert hat; ein neuer Änderungsstempel ließe ihren
    nächsten Speichervorgang am optimistischen Sperren scheitern (409). Ein Vorschlag ist
    keine Änderung der Stunde (`ohne_aenderungsstempel`).
    """
    await db.execute(
        sa.update(ContextNode).where(ContextNode.id == stunde_id).values(
            metadata_=sa.func.jsonb_set(
                sa.func.coalesce(ContextNode.metadata_, sa.text("'{}'::jsonb")),
                sa.text(f"ARRAY['{SCHLUESSEL}']"),
                sa.cast(sa.literal(json.dumps(vorschlag, ensure_ascii=False)), JSONB),
            ),
            **ohne_aenderungsstempel(),
        )
    )
    await db.commit()


#: Ein Lauf je Stunde gleichzeitig — der Knopf und der automatische Lauf nach dem Schreiben
#: treffen sich sonst und zahlen doppelt.
_SPERREN: dict[UUID, asyncio.Lock] = {}


async def begriffe_vorschlagen(db: AsyncSession, stunde_id: UUID, user, *, erzwingen: bool = False) -> dict:
    """Bestimmt die Begriffe der Stunde aus ihren Phasentexten und legt den Vorschlag ab.

    Rückgabe: ``{"vorschlag": {...}}`` oder ``{"fehler": "...", "vorschlag": <bisheriger>}``.
    Ist der abgelegte Vorschlag noch aktuell (gleiche Prüfsumme), läuft ohne ``erzwingen``
    kein neuer Aufruf.

    Der Vorschlag: ``eintraege`` (neu, mit Knoten — `node_id`, `titel`, `content_type`,
    `aliase`, `phase`, `art`), ``frueher`` (in früheren Stunden eingetragen, F1 — getrennt,
    nicht verworfen), ``ohne_knoten`` (Namen, die der Speicher nicht kennt). Was schon in
    `refs` steht oder verworfen wurde (`refs_dismissed`), fehlt.
    """
    from app.context.service import bezugsfaecher_von
    from app.litellm.einzelaufruf import einzelaufruf, schluessel_fuer

    sperre = _SPERREN.setdefault(stunde_id, asyncio.Lock())
    async with sperre:
        stunde = await db.get(ContextNode, stunde_id, populate_existing=True)
        if stunde is None or stunde.content_type != "unterrichtsstunde":
            return {"fehler": "keine_stunde"}
        meta = dict(stunde.metadata_ or {})
        bisher = meta.get(SCHLUESSEL)
        if stunde.subject_id is None:
            return {"fehler": "kein_fach", "vorschlag": bisher}
        if not settings.begriffe_model:
            return {"fehler": "kein_modell", "vorschlag": bisher}

        text = entwurfstext(stunde.title, meta)
        summe = pruefsumme(text)
        if bisher and bisher.get("pruefsumme") == summe and not erzwingen:
            return {"vorschlag": bisher}

        faecher = (stunde.subject_id, *await bezugsfaecher_von(db, stunde.subject_id))
        frueher = await fruehere_begriffe(db, stunde)
        antwort = await einzelaufruf(
            await schluessel_fuer(db, user.sub), user.sub, settings.begriffe_model,
            [{"role": "system", "content": ANLEITUNG},
             {"role": "user", "content": nachricht(await _kontext(db, stunde), [f["titel"] for f in frueher],
                                                    await kandidaten(db, user, text, faecher), text)}],
            json_antwort=True, max_tokens=2000, zeitlimit=45.0,
        )
        if not antwort.ok:
            return {"fehler": antwort.fehler, "vorschlag": bisher}
        begriffe = lies_antwort(antwort.inhalt)
        if begriffe is None:
            logger.warning("Begriffsvorschlag %s: Antwort ohne lesbares JSON: %r", stunde_id, antwort.inhalt[:300])
            return {"fehler": "antwort", "vorschlag": bisher}

        vorhanden = {str(r.get("node_id")) for r in meta.get("refs") or []}
        vorhanden |= {str(r) for r in meta.get("refs_dismissed") or []}
        frueher_je = {f["node_id"]: f for f in frueher}
        eintraege: dict[str, dict] = {}
        frueher_genannt: dict[str, dict] = {}
        ohne: list[dict] = []
        for b in begriffe:
            name = str(b["name"]).strip()
            knoten, _ = await begriff_zum_titel(db, user, name, None, stunde)
            angabe = {"phase": b.get("phase"), "art": b.get("art")}
            if knoten is None:
                if name.casefold() not in {o["name"].casefold() for o in ohne}:
                    ohne.append({"name": name, **angabe})
                continue
            kennung = str(knoten.id)
            if kennung in vorhanden:
                continue
            if kennung in frueher_je:
                frueher_genannt.setdefault(kennung, frueher_je[kennung])
                continue
            aliase = await aliase_des_begriffs(db, knoten, [name])
            if kennung in eintraege:
                eintraege[kennung]["aliase"] = list(dict.fromkeys([*eintraege[kennung]["aliase"], *aliase]))
                continue
            eintraege[kennung] = {"node_id": kennung, "titel": knoten.title, "content_type": knoten.content_type,
                                  "aliase": aliase, **angabe}

        vorschlag = {
            "erstellt_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pruefsumme": summe,
            "eintraege": list(eintraege.values()),
            "frueher": list(frueher_genannt.values()),
            "ohne_knoten": ohne,
        }
        await vorschlag_ablegen(db, stunde_id, vorschlag)
        logger.info("Begriffsvorschlag %s: %d neu, %d früher, %d ohne Knoten (%.5f $)", stunde_id,
                    len(eintraege), len(frueher_genannt), len(ohne), antwort.kosten_usd)
        return {"vorschlag": vorschlag}


def vorschlag_zur_anzeige(titel: str, meta: dict) -> dict[str, Any] | None:
    """Der abgelegte Vorschlag samt `aktuell` — ob der Entwurf seither gleich geblieben ist —,
    ohne was inzwischen eingetragen oder verworfen wurde."""
    vorschlag = (meta or {}).get(SCHLUESSEL)
    if not vorschlag:
        return None
    weg = {str(r.get("node_id")) for r in meta.get("refs") or []} | {str(r) for r in meta.get("refs_dismissed") or []}
    return {
        **vorschlag,
        "eintraege": [e for e in vorschlag.get("eintraege") or [] if e.get("node_id") not in weg],
        "frueher": [f for f in vorschlag.get("frueher") or [] if f.get("node_id") not in weg],
        "aktuell": vorschlag.get("pruefsumme") == pruefsumme(entwurfstext(titel, meta)),
        "hinweis_frueher": HINWEIS_FRUEHER,
    }
