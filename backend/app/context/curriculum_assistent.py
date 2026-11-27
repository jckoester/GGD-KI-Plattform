"""Was der Curriculum-Assistent liest und schreibt (0.46, Päckchen AP Teil B, Schritt 5).

Die Funktionen (`app/context/curriculum_tools.py`) sind dünn; hier steht die Arbeit:

- **Zugang** (`zugang`): dieselbe Regel wie im Editor (`_require_curriculum_write`, Teil A) —
  keine eigene daneben. Schreiben zusätzlich nur in Entwürfe (E17).
- **Lesen**: `entwurf_lesen` (Baum mit Einträgen, Kompetenzen als Nummern, Begriffe mit
  Zustand), `kompetenzen_lesen` (Übersicht des Bands oder die Texte eines Bereichs),
  `abdeckung_kompakt` (Zahlen und Nummern aus der Abdeckung, Teil A), `stundenrahmen`
  (30 × Wochenstunden aus den Rahmenangaben, E19).
- **Prüfen**: `operationen_pruefen` — derselbe Stapel wie beim Schreiben, im Speicher
  angewandt (`_planen`), danach Schluss: kein Sichern, kein Schreiben. Prüflauf und Schreiben
  antworten gleich (`_ergebnis`: Gliederung, `verplant`/`verplanbar`/`rest`, `geloescht`).
- **Schreiben**: `operationen_anwenden` — ein Stapel, **ganz oder gar nicht**. Erst wird der
  ganze Stapel im Speicher angewandt und geprüft (Kompetenznummern nur aus dem Band, sonst
  abgewiesen und genannt); nur wenn alles passt, wird der Stand gesichert (Rückgängig, Grund
  `assistant`) und geschrieben. `rahmen_setzen` ebenso mit Sicherung.

Das Modell rechnet nicht: Stunden, Rahmen und Abdeckung kommen aus diesem Modul.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.curriculum_abdeckung import (
    FEHLT, PARTIELL, _sortschluessel, _text, abdeckung, bereich_von, kompetenzen_des_bands,
)
from app.context.leitlinien import (
    Verweisziele,
    kuerzel_der_tokens,
    leitlinien_tokens,
    leitperspektiven_tokens,
    tokens_trennen,
    tokens_zusammen,
    verweisziele,
)
from app.context.curriculum_begriffe import begriffe_aufloesen, eintrag_felder, namen_normalisieren
from app.context.curriculum_entwurf import ENTWURF
from app.context.curriculum_rahmen import (
    STUNDEN_JE_WOCHENSTUNDE, TEXTFELDER, rahmen_normalisieren, stufen, verplanbar,
)
from app.context.curriculum_verlauf import sichern
from app.context.service import _normalize_ref, load_curriculum_tree
from app.context.stunden import als_stundenzahl
from app.db.models import ContextEdge, ContextNode, Subject

NUR_ENTWUERFE = ("Der Assistent schreibt nur in Entwürfe. Für ein veröffentlichtes Curriculum: "
                 "„Als Entwurf kopieren“ in der Curriculum-Ansicht.")


# ── Zugang ───────────────────────────────────────────────────────────────────


async def zugang(db: AsyncSession, user, curriculum_id: UUID, *, schreiben: bool) -> ContextNode | str:
    """Das Curriculum oder eine Fehlermeldung fürs Modell.

    Grundsätzlich das Schreibrecht des Editors: Der Assistent arbeitet für die Fachschaft an
    ihrem Curriculum. Ein **veröffentlichtes** Curriculum darf dagegen nur der Fachvorsitz ändern
    (E9) — lesen, als Bezug wählen und als Entwurf kopieren darf es die ganze Fachschaft, dieselbe
    Regel wie „Als Entwurf kopieren“ im Editor (`darf_entwurf_bearbeiten`). Geschrieben wird ohnehin nur in
    Entwürfe (E17).
    """
    from app.context.curriculum_entwurf import LESBARE_STATUS, darf_entwurf_bearbeiten
    from app.context.router import _require_curriculum_write

    try:
        cur = await _require_curriculum_write(db, curriculum_id, user)
    except HTTPException as e:
        cur = await db.get(ContextNode, curriculum_id) if e.status_code == 403 else None
        if not (cur is not None and cur.content_type == "curriculum" and cur.status != ENTWURF
                and cur.status in LESBARE_STATUS and await darf_entwurf_bearbeiten(db, cur.subject_id, user)):
            return str(e.detail) if isinstance(e.detail, str) else "Kein Zugriff auf dieses Curriculum."
    if schreiben and cur.status != ENTWURF:
        return NUR_ENTWUERFE
    return cur


# ── Lesen ────────────────────────────────────────────────────────────────────


def _nr(ref: dict, nr_feld: str) -> str | None:
    return ref.get(nr_feld) if isinstance(ref, dict) else (ref if isinstance(ref, str) else None)


def _fassungen(kandidaten: list[dict]) -> list[str]:
    """Die wählbaren Fassungen eines mehrdeutigen Begriffs, zum Nennen (gewählt wird im Editor)."""
    return [f"{k.get('fassung') or k.get('titel')}{f' ({k['fach']})' if k.get('fach') else ''}"
            for k in kandidaten]


def _eintrag_kompakt(e: dict, i: int, zustand: dict, kandidaten: dict | None = None,
                     ziele: Verweisziele | None = None) -> dict:
    ik = [r for r in (e.get("ik") or []) if isinstance(r, (dict, str))]
    aus: dict[str, Any] = {"eintrag": i}
    if voll := [n for r in ik if not (isinstance(r, dict) and r.get("partiell")) and (n := _nr(r, "nr"))]:
        aus["ik"] = voll
    if teil := [n for r in ik if isinstance(r, dict) and r.get("partiell") and (n := _nr(r, "nr"))]:
        aus["ik_teilweise"] = teil
    if pk := [n for r in (e.get("pk") or []) if (n := _nr(r, "pk_id"))]:
        aus["pk"] = pk
    for f in ("konkretisierung", "hinweise", "material"):
        if e.get(f):
            aus[f] = e[f]
    # Leitlinien und Leitperspektiven (0.50, AT): als Kürzel, nicht als Token im Text.
    if ziele is not None and e.get("hinweise"):
        text, lb, lp = tokens_trennen(e["hinweise"])
        if lb or lp:
            if text:
                aus["hinweise"] = text
            else:
                aus.pop("hinweise", None)
            if lb:
                aus["leitlinien"] = kuerzel_der_tokens(lb, ziele)
            if lp:
                aus["leitperspektiven"] = kuerzel_der_tokens(lp, ziele)
    if b := namen_normalisieren(e.get("begriffe")):
        aus["begriffe"] = []
        for x in b:
            schluessel = (x["name"], x.get("fassung"))
            z = zustand.get(schluessel, "fehlt")
            aus["begriffe"].append({
                "name": x["name"], **({"fassung": x["fassung"]} if x.get("fassung") else {}), "zustand": z,
                **({"fassungen": _fassungen(kandidaten[schluessel])}
                   if z == "mehrdeutig" and (kandidaten or {}).get(schluessel) else {})})
    if f := namen_normalisieren(e.get("fachmethoden"), mit_fassung=False):
        aus["fachmethoden"] = [x["name"] for x in f]
    return aus


def _verplant(tree: dict) -> int:
    return sum(als_stundenzahl((ls.get("metadata") or {}).get("std")) or 0
               for k in tree.get("kapitel") or [] for ls in k.get("lernsequenzen") or [])


async def entwurf_lesen(db: AsyncSession, user, cur: ContextNode) -> dict:
    from app.context.absprachen import absprachen_des_curriculums, fach_kompakt, kapitel_kompakt

    tree = await load_curriculum_tree(db, cur.id)
    # Absprachen mit anderen Fächern (0.65, AY Teil 2 C): je Kapitel, nur wo es welche gibt
    abspr = await absprachen_des_curriculums(db, cur, user)
    ziele = await verweisziele(db)
    aufl = await begriffe_aufloesen(db, tree, user)
    zustand = {(a["name"], a.get("fassung")): a["zustand"] for a in aufl}
    kandidaten = {(a["name"], a.get("fassung")): a["kandidaten"] for a in aufl if a.get("kandidaten")}
    meta = tree.get("metadata") or {}
    kapitel = []
    for k_pos, k in enumerate(tree.get("kapitel") or [], 1):
        lss = []
        for l_pos, ls in enumerate(k.get("lernsequenzen") or [], 1):
            lm = ls.get("metadata") or {}
            lss.append({"id": str(ls["id"]), "position": l_pos, "titel": ls.get("title") or "",
                        "std": als_stundenzahl(lm.get("std")),
                        "eintraege": [_eintrag_kompakt(e, i, zustand, kandidaten, ziele)
                                      for i, e in enumerate(lm.get("eintraege") or [], 1) if isinstance(e, dict)]})
        km = k.get("metadata") or {}
        kapitel.append({"id": str(k["id"]), "position": k_pos, "titel": k.get("title") or "",
                        "std": sum(x["std"] or 0 for x in lss),
                        **({"einleitung": km["einleitung"]} if km.get("einleitung") else {}),
                        **({"absprachen": a} if (a := kapitel_kompakt(abspr["kapitel"].get(str(k["id"]), {})))
                           else {}),
                        "lernsequenzen": lss})
    return {
        "curriculum_id": str(cur.id), "titel": tree.get("title"), "status": tree.get("status"),
        "fach": meta.get("fach") or (await db.scalar(sa.select(Subject.name).where(Subject.id == cur.subject_id))
                                     if cur.subject_id else None),
        "jahrgangsstufe": meta.get("jahrgangsstufe"),
        "bp_version": meta.get("bp_version"), "rahmen": meta.get("rahmen") or {},
        "verplant": _verplant(tree), "kapitel": kapitel,
        **({"absprachen_an_das_fach": f} if (f := fach_kompakt(abspr)) else {}),
        # Worauf Einträge verweisen können (0.50, AT): Kürzel für `leitperspektiven` und
        # `leitlinien` der Operationen. Leitlinien nur, wenn die Schule welche hat.
        # Nur die Köpfe; ihre Aspekte („BNE_03“) holt das Modell mit get_bp_competences, typ='lp'.
        "leitperspektiven": [{"kuerzel": e["kuerzel"], "titel": e["titel"], "aspekte": len(e["aspekte"])}
                             for e in ziele.lp_liste],
        **({"leitlinien_der_schule": [
            {"kuerzel": l.kuerzel, "titel": l.titel,
             "aspekte": [{"kuerzel": a.kuerzel, "titel": a.titel} for a in l.aspekte]}
            for l in ziele.liste]} if ziele.liste else {}),
    }


async def leitperspektiven_lesen(db: AsyncSession, bereich: str | None) -> dict:
    """Leitperspektiven mit ihren Aspekten (0.50, AT) — Kürzel für das Feld `leitperspektiven`.

    Mit `bereich` (Kürzel oder Teil des Titels) nur die passenden; sonst alle.
    """
    ziele = await verweisziele(db)
    liste = ziele.lp_liste
    if b := (bereich or "").strip():
        if b.lower() != "alle":
            liste = [e for e in liste if e["kuerzel"] == b.upper() or b.casefold() in e["titel"].casefold()]
    return {"leitperspektiven": liste,
            "hinweis": "Im Eintrag als Kürzel in leitperspektiven: die Leitperspektive (BNE) oder, "
                       "meist treffender, ein Aspekt (BNE_03); beim LFDB ein Themenblock (LFDB_B1_T2) "
                       "oder eine Kompetenz (LFDB_B1_T2_K3)."}


def _bereich_von_bis(nrs: list[str]) -> str:
    nrs = sorted((n for n in nrs if n), key=_sortschluessel)
    if not nrs:
        return ""
    return nrs[0] if len(nrs) == 1 else f"{nrs[0]} – {nrs[-1]}"


def _gruppen(knoten: list[ContextNode]) -> dict[str, list[ContextNode]]:
    gruppen: dict[str, list[ContextNode]] = {}
    for k in sorted(knoten, key=lambda k: _sortschluessel((k.metadata_ or {}).get("kompetenz_nr"))):
        gruppen.setdefault(bereich_von(k.metadata_ or {}) or "ohne Bereich", []).append(k)
    return gruppen


def _kompetenz(k: ContextNode) -> dict:
    nr = (k.metadata_ or {}).get("kompetenz_nr")
    return {"nr": nr, "text": _text(k.title, nr)}


async def kompetenzen_lesen(db: AsyncSession, cur: ContextNode, bereich: str | None, typ: str) -> dict:
    """Ohne `bereich`: Übersicht (Bereiche mit Anzahl und Nummern, ohne Texte). Mit `bereich`
    (Name eines Bereichs, Nummernpräfix wie „3.2.1“ oder „alle“): die Kompetenzen mit Text."""
    iks, pks = await kompetenzen_des_bands(db, cur)
    kopf = {"fach": (cur.metadata_ or {}).get("fach"), "bp_version": (cur.metadata_ or {}).get("bp_version"),
            "jahrgangsstufe": (cur.metadata_ or {}).get("jahrgangsstufe")}
    if not iks and not pks:
        return {**kopf, "hinweis": "Für Fach, Fassung und Stufen dieses Curriculums sind im Bildungsplan "
                                   "keine Kompetenzen hinterlegt. Schreibe keine Kompetenzen."}
    if not bereich:
        return {**kopf,
                "ik": {"gesamt": len(iks), "bereiche": [
                    {"bereich": g, "anzahl": len(ks), "nummern": _bereich_von_bis(
                        [(k.metadata_ or {}).get("kompetenz_nr") for k in ks])} for g, ks in _gruppen(iks).items()]},
                "pk": {"gesamt": len(pks), "bereiche": [
                    {"bereich": g, "anzahl": len(ks), "nummern": _bereich_von_bis(
                        [(k.metadata_ or {}).get("kompetenz_nr") for k in ks])} for g, ks in _gruppen(pks).items()]},
                "hinweis": "Texte mit bereich (Name oder Nummernpräfix) abrufen; PK mit typ='pk'."}
    knoten = pks if typ == "pk" else iks
    b = bereich.strip()
    if b.lower() == "alle":
        treffer = {g: ks for g, ks in _gruppen(knoten).items()}
    elif re.fullmatch(r"[\d.()\s]+", b):
        praefix = _normalize_ref(b).rstrip(".")
        treffer = {}
        for g, ks in _gruppen(knoten).items():
            if sel := [k for k in ks if _normalize_ref((k.metadata_ or {}).get("kompetenz_nr") or "").startswith(praefix)]:
                treffer[g] = sel
    else:
        treffer = {g: ks for g, ks in _gruppen(knoten).items() if b.lower() in g.lower()}
    if not treffer:
        return {**kopf, "typ": typ, "bereich": b, "kompetenzen": [],
                "hinweis": "Kein Bereich passt — rufe die Übersicht ohne bereich ab."}
    return {**kopf, "typ": typ, "bereiche": [
        {"bereich": g, "kompetenzen": [_kompetenz(k) for k in ks]} for g, ks in treffer.items()]}


async def abdeckung_kompakt(db: AsyncSession, cur: ContextNode) -> dict:
    """Zahlen und Nummern der Abdeckung — Texte liefert `get_bp_competences`."""
    a = await abdeckung(db, await load_curriculum_tree(db, cur.id))
    ik = a["ik"]
    ks = [k for g in ik["gruppen"] for k in g["kompetenzen"]]
    pks = [k for g in a["pk"]["gruppen"] for k in g["kompetenzen"]]
    return {
        "bp_version": a["bp_version"],
        "ik": {"gesamt": ik["gesamt"], "verknuepft": ik["verknuepft"], "teilweise": ik[PARTIELL],
               "fehlt": ik[FEHLT],
               "fehlende": [{"nr": k["nr"], **({"in_anderem_curriculum": k["anderswo"]} if k.get("anderswo") else {})}
                            for k in ks if k["zustand"] == FEHLT],
               "nur_teilweise": [k["nr"] for k in ks if k["zustand"] == PARTIELL]},
        "pk": {"gesamt": a["pk"]["gesamt"], "genutzt": a["pk"]["genutzt"],
               "ungenutzt": [k["nr"] for k in pks if not k["anzahl"]]},
        **({"ausserhalb_des_bands": [k["nr"] for k in a["ausserhalb"]]} if a["ausserhalb"] else {}),
        **({"fremdes_fach": len(a["fremdes_fach"])} if a["fremdes_fach"] else {}),
        **({"hinweis": a["hinweis"]} if a["hinweis"] else {}),
        # Leitlinien der Schule (0.50, AT): je Leitlinie, welche Aspekte vorkommen und welche nicht.
        **({"leitlinien": [
            {"kuerzel": l["kuerzel"], "aspekte_gesamt": len(l["aspekte"]), "vorkommend": l["vorkommend"],
             "nicht_vorkommend": [x["kuerzel"] for x in l["aspekte"] if not x["lernsequenzen"]]}
            for l in a["leitlinien"]]} if a["leitlinien"] else {}),
    }


def _bilanz(cur: ContextNode, verplant: int) -> dict:
    """`verplant`, `verplanbar`, `rest` — und `fehlende_stufen`, solange Wochenstunden fehlen
    (dann sind `verplanbar` und `rest` null). Dieselbe Rechnung für Stundenrahmen, Prüflauf und
    Schreiben."""
    meta = cur.metadata_ or {}
    rahmen = meta.get("rahmen") or {}
    jg = meta.get("jahrgangsstufe")
    ws = rahmen.get("wochenstunden") or {}
    v = verplanbar(rahmen, jg)
    aus: dict[str, Any] = {"verplant": verplant, "verplanbar": v, "rest": None if v is None else v - verplant}
    if fehlt := [s for s in stufen(jg) if str(s) not in ws]:
        aus["fehlende_stufen"] = fehlt
    return aus


async def stundenrahmen(db: AsyncSession, cur: ContextNode) -> dict:
    meta = cur.metadata_ or {}
    bilanz = _bilanz(cur, _verplant(await load_curriculum_tree(db, cur.id)))
    aus = {"jahrgangsstufe": meta.get("jahrgangsstufe"),
           "wochenstunden": (meta.get("rahmen") or {}).get("wochenstunden") or {},
           "regel": f"{STUNDEN_JE_WOCHENSTUNDE} Stunden je Wochenstunde", **bilanz}
    if bilanz.get("fehlende_stufen"):
        aus["hinweis"] = "Wochenstunden für diese Stufen fehlen — frage die Lehrkraft und halte sie mit set_curriculum_frame fest."
    return aus


# ── Schreiben: Arbeitsmodell ─────────────────────────────────────────────────


@dataclass
class _Ls:
    id: UUID | None
    titel: str
    meta: dict
    neu: bool = False
    geaendert: bool = False


@dataclass
class _Kap:
    id: UUID | None
    titel: str
    meta: dict
    lss: list[_Ls] = field(default_factory=list)
    neu: bool = False
    geaendert: bool = False
    #: Absprachen mit anderen Fächern geändert (0.65) — Ziele prüft `_planen` danach gegen die DB
    absprachen_geaendert: bool = False


class _Fehler(Exception):
    pass


def _position(liste: list, pos) -> int:
    """1-basierte Position → Index; ohne Angabe ans Ende."""
    if pos is None:
        return len(liste)
    try:
        p = int(pos)
    except (TypeError, ValueError):
        raise _Fehler(f"position muss eine Zahl sein, nicht „{pos}“") from None
    return max(0, min(len(liste), p - 1))


def _std(wert) -> int | None:
    if wert is None or wert == "":
        return None
    s = als_stundenzahl(wert)
    if s is None:
        raise _Fehler(f"std muss eine ganze Zahl ab 0 sein, nicht „{wert}“")
    return s


class _Plan:
    def __init__(self, tree: dict, iks: list[ContextNode], pks: list[ContextNode],
                 ziele: Verweisziele | None = None, fach_code: str | None = None):
        self.ziele = ziele
        self.fach_code = fach_code
        self.kapitel = [
            _Kap(id=UUID(str(k["id"])), titel=k.get("title") or "", meta=dict(k.get("metadata") or {}),
                 lss=[_Ls(id=UUID(str(ls["id"])), titel=ls.get("title") or "", meta=dict(ls.get("metadata") or {}))
                      for ls in k.get("lernsequenzen") or []])
            for k in tree.get("kapitel") or []]
        self.alt_kap = {k.id for k in self.kapitel}
        self.alt_ls = {ls.id for k in self.kapitel for ls in k.lss}
        # Einträge des Stands vorher, per Identität (für `geloescht`). `_halten` hält die
        # Objekte am Leben, damit keine `id()` neu vergeben wird.
        self._halten = [e for k in self.kapitel for ls in k.lss for e in ls.meta.get("eintraege") or []]
        self.alt_eintraege = {id(e) for e in self._halten}
        self.eintraege_vorher = len(self._halten)
        self.refs: dict[str, object] = {}
        self.ik = {_normalize_ref((k.metadata_ or {}).get("kompetenz_nr") or ""): k for k in iks}
        self.pk = {_normalize_ref((k.metadata_ or {}).get("kompetenz_nr") or ""): k for k in pks}

    # Finden
    def kap(self, kennung) -> _Kap:
        if isinstance(kennung, str) and kennung in self.refs and isinstance(self.refs[kennung], _Kap):
            return self.refs[kennung]
        for k in self.kapitel:
            if k.id is not None and str(k.id) == str(kennung):
                return k
        raise _Fehler(f"Kapitel „{kennung}“ gibt es nicht")

    def ls(self, kennung) -> tuple[_Kap, _Ls]:
        ziel = self.refs.get(kennung) if isinstance(kennung, str) else None
        for k in self.kapitel:
            for ls in k.lss:
                if ls is ziel or (ls.id is not None and str(ls.id) == str(kennung)):
                    return k, ls
        raise _Fehler(f"Lernsequenz „{kennung}“ gibt es nicht")

    def merke(self, ref, obj):
        if ref:
            if ref in self.refs:
                raise _Fehler(f"ref „{ref}“ ist schon vergeben")
            self.refs[str(ref)] = obj

    # Kompetenzen
    def _iks(self, nrs, partiell: bool) -> list[dict]:
        aus = []
        for nr in nrs or []:
            k = self.ik.get(_normalize_ref(str(nr)))
            if k is None:
                raise _Fehler(f"IK {nr} gehört nicht zu den Kompetenzen dieses Bands (get_bp_competences)")
            aus.append({"node_id": str(k.id), "nr": (k.metadata_ or {}).get("kompetenz_nr"), "partiell": partiell})
        return aus

    def _pks(self, nrs) -> list[dict]:
        aus = []
        for nr in nrs or []:
            k = self.pk.get(_normalize_ref(str(nr)))
            if k is None:
                raise _Fehler(f"PK {nr} gehört nicht zu den prozessbezogenen Kompetenzen des Fachs (get_bp_competences, typ='pk')")
            aus.append({"node_id": str(k.id), "pk_id": (k.metadata_ or {}).get("kompetenz_nr")})
        return aus

    def eintrag(self, op: dict, alt: dict | None = None) -> dict:
        e = dict(alt or {})
        if "ik" in op or "ik_teilweise" in op:
            ik_alt = [r for r in e.get("ik") or [] if isinstance(r, dict)]
            voll = self._iks(op["ik"], False) if "ik" in op else [r for r in ik_alt if not r.get("partiell")]
            teil = self._iks(op["ik_teilweise"], True) if "ik_teilweise" in op else [r for r in ik_alt if r.get("partiell")]
            e["ik"] = voll + teil
        if "pk" in op:
            e["pk"] = self._pks(op["pk"])
        for f in ("konkretisierung", "hinweise", "material"):
            if f in op:
                if op[f] is not None and not isinstance(op[f], str):
                    raise _Fehler(f"{f} muss Text sein")
                e[f] = op[f] or ""
        if self.ziele is not None and any(f in op for f in ("hinweise", "leitlinien", "leitperspektiven")):
            # Genannte Felder ersetzen, andere bleiben: Wer nur `hinweise` schreibt, behält die
            # Verweise; wer `leitlinien` schreibt, ersetzt nur diese (0.50, AT).
            _, alt_lb, alt_lp = tokens_trennen((alt or {}).get("hinweise"))
            text, im_text_lb, im_text_lp = tokens_trennen(e.get("hinweise"))
            try:
                lb = (leitlinien_tokens(op["leitlinien"], self.ziele) if "leitlinien" in op
                      else alt_lb + [t for t in im_text_lb if t not in alt_lb])
                lp = (leitperspektiven_tokens(op["leitperspektiven"], self.ziele) if "leitperspektiven" in op
                      else alt_lp + [t for t in im_text_lp if t not in alt_lp])
            except ValueError as fehler:
                raise _Fehler(str(fehler))
            e["hinweise"] = tokens_zusammen(text, lp + lb)
        if "begriffe" in op or "fachmethoden" in op:
            felder = eintrag_felder(op.get("begriffe", e.get("begriffe")), op.get("fachmethoden", e.get("fachmethoden")))
            e = {k: v for k, v in e.items() if k not in ("begriffe", "fachmethoden")} | felder
        e.setdefault("ik", [])
        e.setdefault("pk", [])
        return e

    # Operationen
    def anwenden(self, op: dict) -> None:
        art = op.get("op")
        if art == "kapitel_anlegen":
            titel = (op.get("titel") or "").strip()
            if not titel:
                raise _Fehler("titel fehlt")
            k = _Kap(id=None, titel=titel, meta={"einleitung": op.get("einleitung") or ""}, neu=True)
            self.kapitel.insert(_position(self.kapitel, op.get("position")), k)
            self.merke(op.get("ref"), k)
        elif art == "kapitel_aendern":
            k = self.kap(op.get("kapitel_id"))
            if "titel" in op:
                if not (op["titel"] or "").strip():
                    raise _Fehler("titel darf nicht leer sein")
                k.titel = op["titel"].strip()
            if "einleitung" in op:
                k.meta["einleitung"] = op["einleitung"] or ""
            if "position" in op:
                self.kapitel.remove(k)
                self.kapitel.insert(_position(self.kapitel, op["position"]), k)
            k.geaendert = True
        elif art == "kapitel_loeschen":
            self.kapitel.remove(self.kap(op.get("kapitel_id")))
        elif art == "lernsequenz_anlegen":
            k = self.kap(op.get("kapitel_id"))
            titel = (op.get("titel") or "").strip()
            if not titel:
                raise _Fehler("titel fehlt")
            ls = _Ls(id=None, titel=titel, meta={"std": _std(op.get("std")) or 0, "eintraege": [],
                                                  "bp_leitidee": ""}, neu=True)
            k.lss.insert(_position(k.lss, op.get("position")), ls)
            k.geaendert = True
            self.merke(op.get("ref"), ls)
        elif art == "lernsequenz_aendern":
            k, ls = self.ls(op.get("lernsequenz_id"))
            if "titel" in op:
                if not (op["titel"] or "").strip():
                    raise _Fehler("titel darf nicht leer sein")
                ls.titel = op["titel"].strip()
            if "std" in op:
                ls.meta["std"] = _std(op["std"]) or 0
            if "kapitel_id" in op or "position" in op:
                ziel = self.kap(op["kapitel_id"]) if "kapitel_id" in op else k
                k.lss.remove(ls)
                ziel.lss.insert(_position(ziel.lss, op.get("position")), ls)
                k.geaendert = ziel.geaendert = True
            ls.geaendert = True
            k.geaendert = True
        elif art == "lernsequenz_loeschen":
            k, ls = self.ls(op.get("lernsequenz_id"))
            k.lss.remove(ls)
            k.geaendert = True
        elif art in ("eintrag_anlegen", "eintrag_aendern", "eintrag_loeschen"):
            k, ls = self.ls(op.get("lernsequenz_id"))
            eintraege = list(ls.meta.get("eintraege") or [])
            if art == "eintrag_anlegen":
                eintraege.insert(_position(eintraege, op.get("position")), self.eintrag(op))
            else:
                try:
                    i = int(op.get("eintrag")) - 1
                except (TypeError, ValueError):
                    raise _Fehler("eintrag (Nummer ab 1) fehlt") from None
                if not 0 <= i < len(eintraege):
                    raise _Fehler(f"Eintrag {op.get('eintrag')} gibt es in dieser Lernsequenz nicht")
                if art == "eintrag_loeschen":
                    eintraege.pop(i)
                else:
                    alt = eintraege[i]
                    eintraege[i] = self.eintrag(op, alt)
                    if id(alt) in self.alt_eintraege:  # geändert, aber nicht neu
                        self._halten.append(eintraege[i])
                        self.alt_eintraege.add(id(eintraege[i]))
            ls.meta["eintraege"] = eintraege
            ls.geaendert = True
        elif art in ("absprache_anlegen", "absprache_aendern", "absprache_loeschen"):
            self.absprache(art, op)
        else:
            raise _Fehler(f"unbekannte Operation „{art}“")

    # Absprachen mit anderen Fächern (0.65, AY Teil 2 C)
    def absprache(self, art: str, op: dict) -> None:
        """Ändert `metadata.absprachen` des Kapitels im Speicher und prüft die Form (wie im Editor).
        Ob das Ziel-Kapitel zum genannten Fach gehört, prüft `_planen` danach gegen die Datenbank."""
        from app.context.absprachen import normalisieren

        k = self.kap(op.get("kapitel_id"))
        liste = [dict(a) for a in k.meta.get("absprachen") or []]
        if art == "absprache_anlegen":
            liste.append({"fach_code": op.get("fach"), "kapitel_id": op.get("ziel_kapitel_id"),
                          "art": op.get("art"), "text": op.get("text") or ""})
        else:
            try:
                i = int(op.get("absprache")) - 1
            except (TypeError, ValueError):
                raise _Fehler("absprache (Nummer ab 1) fehlt") from None
            if not 0 <= i < len(liste):
                raise _Fehler(f"Absprache {op.get('absprache')} gibt es an diesem Kapitel nicht")
            if art == "absprache_loeschen":
                liste.pop(i)
            else:
                a = liste[i]
                if "fach" in op:
                    a["fach_code"] = op["fach"]
                if "ziel_kapitel_id" in op:
                    a["kapitel_id"], a["kapitel_titel"] = op["ziel_kapitel_id"], None
                for f in ("art", "text"):
                    if f in op:
                        a[f] = op[f]
        try:
            k.meta["absprachen"] = normalisieren(liste, self.fach_code)
        except ValueError as e:
            raise _Fehler(str(e)) from None
        k.geaendert = k.absprachen_geaendert = True

    # Ergebnis
    def geloescht(self) -> dict[str, int]:
        """Was der Stapel gegenüber dem Stand vorher entfernt — Lernsequenzen und Einträge
        gelöschter Kapitel mitgezählt, Verschobenes nicht."""
        bleibt_ls = [ls for k in self.kapitel for ls in k.lss]
        eintraege_da = sum(1 for ls in bleibt_ls for e in ls.meta.get("eintraege") or []
                           if id(e) in self.alt_eintraege)
        return {"kapitel": len(self.alt_kap - {k.id for k in self.kapitel if k.id}),
                "lernsequenzen": len(self.alt_ls - {ls.id for ls in bleibt_ls if ls.id}),
                "eintraege": self.eintraege_vorher - eintraege_da}

    def gliederung(self) -> list[dict]:
        """Neue Teile haben vor dem Schreiben noch keine Kennung (`id: null`)."""
        return [{"id": str(k.id) if k.id else None, "titel": k.titel,
                 "std": sum(als_stundenzahl(ls.meta.get("std")) or 0 for ls in k.lss),
                 "lernsequenzen": [{"id": str(ls.id) if ls.id else None, "titel": ls.titel,
                                    "std": als_stundenzahl(ls.meta.get("std")),
                                    "eintraege": len(ls.meta.get("eintraege") or [])} for ls in k.lss]}
                for k in self.kapitel]

    def absprachen(self) -> list[dict]:
        """Die Absprachen der Kapitel, die der Stapel ändert — für Vorschau und Antwort."""
        return [{"kapitel": k.titel, "absprachen": [
            {"nr": i, "fach_code": a["fach_code"], "ziel_kapitel": a.get("kapitel_titel") or "ganzes Fach",
             "art": a["art"], **({"text": a["text"]} if a.get("text") else {})}
            for i, a in enumerate(k.meta.get("absprachen") or [], 1)]}
            for k in self.kapitel if k.absprachen_geaendert]


# ── Schreiben: Kanten wie im Editor ──────────────────────────────────────────

# Leitperspektiven (`lp`/`lpa`), Leitlinien der Schule (`lb`/`lba`, 0.50) und fremde IK.
_HINWEIS_TOKEN = re.compile(r"(?:@\[[^\]]*\]\((?:lpa|lp|lba|lb)|#\[[^\]]*\]\(ik):([0-9a-f-]{36})\)")
_MATERIAL_TOKEN = re.compile(r"@\[[^\]]*\]\(node:([0-9a-f-]{36})\)")


def _soll_kanten(eintraege: list[dict]) -> set[tuple[UUID, str, str]]:
    """(Ziel, Relation, partiell) aus den Einträgen — wie `deriveRefsFromEntries` im Editor:
    IK → references (partiell; voll schlägt teilweise), PK → develops, Verweise in den Hinweisen
    → references, Material → used_with."""
    ik: dict[str, bool] = {}
    andere: set[tuple[UUID, str, str]] = set()
    for e in eintraege:
        for r in e.get("ik") or []:
            if isinstance(r, dict) and r.get("node_id"):
                ik[r["node_id"]] = ik.get(r["node_id"], True) and bool(r.get("partiell"))
        for r in e.get("pk") or []:
            if isinstance(r, dict) and r.get("node_id"):
                andere.add((UUID(r["node_id"]), "develops", ""))
        for m in _HINWEIS_TOKEN.finditer(e.get("hinweise") or ""):
            andere.add((UUID(m.group(1)), "references", ""))
        for m in _MATERIAL_TOKEN.finditer(e.get("material") or ""):
            andere.add((UUID(m.group(1)), "used_with", ""))
    return {(UUID(n), "references", "true" if p else "false") for n, p in ik.items()} | andere


async def _kanten_abgleichen(db: AsyncSession, ls_id: UUID, eintraege: list[dict]) -> None:
    soll = _soll_kanten(eintraege)
    # Wie im Editor nur die verwalteten Relationen; `part_of` bleibt.
    await db.execute(sa.delete(ContextEdge).where(
        ContextEdge.from_node_id == ls_id,
        sa.or_(ContextEdge.relation.in_(("references", "develops")),
               sa.and_(ContextEdge.relation == "used_with", ContextEdge.metadata_["via"].astext == "material"))))
    ziele = {z for z, _, _ in soll}
    vorhanden = set((await db.execute(sa.select(ContextNode.id).where(
        ContextNode.id.in_(ziele), ContextNode.status != "deleted"))).scalars().all()) if ziele else set()
    ik_ziele = {z for z, r, p in soll if p}
    for ziel, relation, partiell in soll:
        if ziel not in vorhanden or (relation == "references" and not partiell and ziel in ik_ziele):
            continue
        meta = {"partiell": partiell} if partiell else {"via": "material"} if relation == "used_with" else {}
        db.add(ContextEdge(from_node_id=ls_id, to_node_id=ziel, relation=relation, metadata_=meta))


# ── Schreiben ────────────────────────────────────────────────────────────────


def _neuer_knoten(cur: ContextNode, typ: str, titel: str, meta: dict, content: str | None, user) -> ContextNode:
    return ContextNode(category="knowledge", content_type=typ, title=titel, content=content, status=ENTWURF,
                       read_scope="school", write_scope="subject", write_scope_group_id=cur.write_scope_group_id,
                       subject_id=cur.subject_id, owner_pseudonym=user.sub, metadata_=meta)


async def _planen(db: AsyncSession, cur: ContextNode, ops) -> _Plan | list[str]:
    """Den ganzen Stapel im Speicher anwenden — der Plan oder die Liste der Fehler.
    Gemeinsam für Prüflauf und Schreiben; schreibt nichts."""
    if not isinstance(ops, list) or not ops:
        return ["operations ist leer"]
    tree = await load_curriculum_tree(db, cur.id)
    iks, pks = await kompetenzen_des_bands(db, cur)
    fach_code = await db.scalar(sa.select(Subject.fach_code).where(Subject.id == cur.subject_id)) \
        if cur.subject_id else None
    plan = _Plan(tree, iks, pks, await verweisziele(db), fach_code)
    fehler = []
    for i, op in enumerate(ops, 1):
        if not isinstance(op, dict):
            fehler.append(f"Operation {i}: kein Objekt")
            continue
        try:
            plan.anwenden(op)
        except _Fehler as e:
            fehler.append(f"Operation {i} ({op.get('op')}): {e}")
    if not fehler:
        # Absprachen (0.65): Ziel-Kapitel gegen die Datenbank, Titel aus der Datenbank
        from app.context.absprachen import ziele_pruefen

        for k in plan.kapitel:
            if not k.absprachen_geaendert:
                continue
            try:
                k.meta["absprachen"] = await ziele_pruefen(db, k.meta.get("absprachen") or [])
            except ValueError as e:
                fehler.append(f"Absprachen am Kapitel „{k.titel}“: {e}")
                continue
            if not k.meta["absprachen"]:
                k.meta.pop("absprachen", None)
    return fehler or plan


def _ergebnis(cur: ContextNode, plan: _Plan, ops: list, *, geschrieben: bool) -> dict:
    """Antwort von Prüflauf und Schreiben: Gliederung, Stundenbilanz, Gelöschtes."""
    gliederung = plan.gliederung()
    aus: dict[str, Any] = {"ok": True, "geschrieben": geschrieben, "angewandt": len(ops),
                           "gliederung": gliederung, **_bilanz(cur, sum(k["std"] for k in gliederung))}
    geloescht = plan.geloescht()
    if any(geloescht.values()):
        aus["geloescht"] = geloescht
    if leer := [k["titel"] for k in gliederung if not k["lernsequenzen"]]:
        aus["hinweis"] = f"Kapitel ohne Lernsequenz: {', '.join(leer)}"
    if abspr := plan.absprachen():
        aus["absprachen"] = abspr
    return aus


async def operationen_pruefen(db: AsyncSession, cur: ContextNode, ops: list[dict]) -> dict:
    """Prüflauf: derselbe Stapel wie beim Schreiben, ohne Sichern und ohne Schreiben."""
    plan = await _planen(db, cur, ops)
    if isinstance(plan, list):
        return {"ok": False, "fehler": plan,
                "hinweis": "Korrigiere den Stapel, bevor du ihn der Lehrkraft zeigst."}
    return _ergebnis(cur, plan, ops, geschrieben=False)


async def operationen_anwenden(db: AsyncSession, user, cur: ContextNode, ops: list[dict]) -> dict:
    """Ein Stapel, ganz oder gar nicht. Kein Commit (der Chat committet am Ende der Antwort)."""
    plan = await _planen(db, cur, ops)
    if isinstance(plan, list):
        return {"ok": False, "fehler": plan, "hinweis": "Nichts geschrieben — korrigiere und schicke den ganzen Stapel neu."}

    await sichern(db, cur.id, grund="assistant", von=user.sub)

    meta_cur = cur.metadata_ or {}
    brot = f"{meta_cur.get('schulart', '')} | {meta_cur.get('fach', '')} | Kl. {meta_cur.get('jahrgangsstufe', '')}"
    # Gelöschtes zuerst (Kanten folgen per CASCADE).
    bleibt_kap = {k.id for k in plan.kapitel if k.id}
    bleibt_ls = {ls.id for k in plan.kapitel for ls in k.lss if ls.id}
    weg = (plan.alt_kap - bleibt_kap) | (plan.alt_ls - bleibt_ls)
    if weg:
        await db.execute(sa.delete(ContextNode).where(ContextNode.id.in_(weg)))

    for k_pos, k in enumerate(plan.kapitel, 1):
        k_std = sum(als_stundenzahl(ls.meta.get("std")) or 0 for ls in k.lss)
        if k.neu:
            node = _neuer_knoten(cur, "kapitel", k.titel, {}, k.meta.get("einleitung") or "", user)
            db.add(node)
            await db.flush()
            k.id = node.id
            db.add(ContextEdge(from_node_id=node.id, to_node_id=cur.id, relation="part_of", metadata_={}))
        else:
            node = await db.get(ContextNode, k.id)
        meta_neu = {**k.meta, "std": k_std, "reihenfolge": k_pos, "breadcrumb": f"{brot}: {k.titel}"}
        if k.neu or node.title != k.titel or (node.metadata_ or {}) != meta_neu:
            if node.title != k.titel or (node.metadata_ or {}).get("einleitung") != meta_neu.get("einleitung"):
                node.embedding = None
            node.title, node.metadata_, node.content = k.titel, meta_neu, meta_neu.get("einleitung") or ""
        for l_pos, ls in enumerate(k.lss, 1):
            if ls.neu:
                ls_node = _neuer_knoten(cur, "lernsequenz", ls.titel, {}, None, user)
                db.add(ls_node)
                await db.flush()
                ls.id = ls_node.id
                db.add(ContextEdge(from_node_id=ls_node.id, to_node_id=k.id, relation="part_of", metadata_={}))
            else:
                ls_node = await db.get(ContextNode, ls.id)
                umgehaengt = (await db.execute(sa.select(ContextEdge).where(
                    ContextEdge.from_node_id == ls.id, ContextEdge.relation == "part_of"))).scalar_one_or_none()
                # Fehlt die Kante, hing die Lernsequenz an einem Kapitel, das dieser Stapel
                # gelöscht hat (CASCADE) — sie wurde vorher verschoben.
                if umgehaengt is None or umgehaengt.to_node_id != k.id:
                    if umgehaengt is not None:
                        await db.delete(umgehaengt)
                        await db.flush()
                    db.add(ContextEdge(from_node_id=ls.id, to_node_id=k.id, relation="part_of", metadata_={}))
            ls_meta = {**ls.meta, "reihenfolge": l_pos}
            if ls.neu or ls_node.title != ls.titel or (ls_node.metadata_ or {}) != ls_meta:
                ls_node.embedding = None
                ls_node.title, ls_node.metadata_ = ls.titel, ls_meta
            if ls.neu or ls.geaendert:
                await _kanten_abgleichen(db, ls.id, ls_meta.get("eintraege") or [])
    await db.flush()
    aus = _ergebnis(cur, plan, ops, geschrieben=True)
    if neu_ids := {ref: str(obj.id) for ref, obj in plan.refs.items() if obj.id is not None}:
        aus["neue_kennungen"] = neu_ids
    return aus


async def rahmen_setzen(db: AsyncSession, user, cur: ContextNode, angaben: dict) -> dict:
    """Ergänzt die Rahmenangaben: genannte Felder ersetzen, Wochenstunden je Stufe; leerer Text löscht."""
    alt = (cur.metadata_ or {}).get("rahmen") or {}
    neu = dict(alt)
    if "wochenstunden" in angaben:
        if not isinstance(angaben["wochenstunden"], dict):
            return {"ok": False, "fehler": ["wochenstunden als Objekt je Klassenstufe, etwa {\"7\": 2}"]}
        neu["wochenstunden"] = {**(alt.get("wochenstunden") or {}), **angaben["wochenstunden"]}
    for feld, _ in TEXTFELDER:
        if feld in angaben:
            neu[feld] = angaben[feld]
    try:
        neu = rahmen_normalisieren(neu)
    except ValueError as e:
        return {"ok": False, "fehler": [str(e)]}
    if neu == alt:
        return {"ok": True, "rahmen": neu, "hinweis": "Keine Änderung."}
    await sichern(db, cur.id, grund="assistant", von=user.sub)
    cur.metadata_ = {**(cur.metadata_ or {}), "rahmen": neu}
    await db.flush()
    return {"ok": True, "rahmen": neu,
            "verplanbar": verplanbar(neu, (cur.metadata_ or {}).get("jahrgangsstufe"))}
