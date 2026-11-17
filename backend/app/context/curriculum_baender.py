"""Curricula nach Fassung und Band, Abdeckung über das Band (0.46, Päckchen AP Teil B, Schritt 8).

**Übersicht** (`uebersicht`): je Fach die Fassungen des Bildungsplans — erst die geltenden, dann
die kommenden, danach ältere, für die es noch Curricula gibt —, darin die Bänder aus dem Plan
(`bp_baender`) und je Band die Curricula. Curricula, die sich keinem Band zuordnen lassen
(parallele Bänder der Oberstufe ohne Wahl), stehen gesondert.

**Abdeckung über das Band** (`band_abdeckung`): Ein Curriculum gilt oft für eine Stufe, ein Band
für zwei oder drei. Je IK des Bands der Zustand über alle Curricula, die dem Band zugeordnet sind:
verknüpft, sobald eines sie voll verknüpft; partiell, wenn keines voll, aber eines teilweise;
sonst fehlt. Mit Entwürfen ersetzt ein Entwurf, der ein veröffentlichtes Curriculum ersetzen
soll (`metadata.kopie_von`), dieses — der Stand nach dem Veröffentlichen (F3, Jan 17.11.2026).

Welche Curricula jemand sieht, entscheidet der Aufrufer (Leseregel der Liste).
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.bp_baender import Band, band_schluessel, band_zuordnen, baender_aus
from app.context.curriculum_abdeckung import (
    FEHLT, PARTIELL, VERKNUEPFT, _sortschluessel, _text, bereich_von, kompetenzen_der_fassung,
    verknuepfungen,
)
from app.context.editions import KUENFTIG
from app.db.models import ContextNode

ENTWURF = "draft"
GELTEND, KOMMEND, AELTER = "geltend", "kommend", "aelter"


def fassung_von(cur: ContextNode) -> str | None:
    return (cur.metadata_ or {}).get("bp_version") or cur.bp_version


def _kurz(cur: ContextNode, titel_je_id: dict[str, str]) -> dict:
    meta = cur.metadata_ or {}
    aus = {"id": str(cur.id), "title": cur.title, "status": cur.status,
           "jahrgangsstufe": meta.get("jahrgangsstufe"), "schulart": meta.get("schulart"),
           "darf_schreiben": getattr(cur, "darf_schreiben", False)}
    if (z := getattr(cur, "zuletzt_geaendert", None)) is not None:
        aus["zuletzt_geaendert"] = z
    if (k := meta.get("kopie_von")) and cur.status == ENTWURF:
        aus["ersetzt"] = {"id": str(k), "title": titel_je_id.get(str(k))}
    return aus


async def _fassungen(db: AsyncSession, subject_id: int) -> dict[str, str]:
    """Fassungen mit geltenden oder kommenden Kompetenzen des Fachs → geltend/kommend."""
    zeilen = (await db.execute(
        sa.select(ContextNode.bp_version, ContextNode.status).distinct().where(
            ContextNode.subject_id == subject_id,
            ContextNode.content_type.in_(("ik_kompetenz", "pk_kompetenz")),
            ContextNode.status.in_(("active", KUENFTIG)),
            ContextNode.bp_version.is_not(None)))).all()
    art: dict[str, str] = {}
    for bp, status in zeilen:
        if status == "active" or bp not in art:
            art[bp] = GELTEND if status == "active" else KOMMEND
    return art


def _sortiert(art: dict[str, str]) -> list[str]:
    rang = {GELTEND: 0, KOMMEND: 1, AELTER: 2}
    return sorted(art, key=lambda bp: (rang[art[bp]], _sortschluessel(bp)))


async def uebersicht(db: AsyncSession, subject_id: int, curricula: list[ContextNode]) -> dict:
    art = await _fassungen(db, subject_id)
    for c in curricula:
        if (bp := fassung_von(c)) and bp not in art:
            art[bp] = AELTER
    titel_je_id = {str(c.id): c.title for c in curricula}
    ohne_fassung = [_kurz(c, titel_je_id) for c in curricula if not fassung_von(c)]

    fassungen = []
    for bp in _sortiert(art):
        baender = baender_aus(await kompetenzen_der_fassung(db, subject_id, bp))
        je_band: dict[str, list[dict]] = {b.schluessel: [] for b in baender}
        offen = []
        for c in sorted((c for c in curricula if fassung_von(c) == bp),
                        key=lambda c: (c.min_grade or 0, c.title or "")):
            band, kandidaten = band_zuordnen(baender, c.min_grade, c.max_grade, (c.metadata_ or {}).get("band"))
            if band is not None:
                je_band[band.schluessel].append(_kurz(c, titel_je_id))
            else:
                offen.append({**_kurz(c, titel_je_id), "baender": [b.schluessel for b in kandidaten]})
        fassungen.append({
            "bp_version": bp, "art": art[bp],
            "baender": [{**b.als_dict(), "curricula": je_band[b.schluessel]} for b in baender],
            "nicht_zugeordnet": offen,
        })
    return {"fassungen": fassungen, "ohne_fassung": ohne_fassung}


def _ohne_ersetzte(beteiligt: list[ContextNode]) -> list[ContextNode]:
    """Ein Entwurf, der ein beteiligtes veröffentlichtes Curriculum ersetzen soll, tritt an dessen
    Stelle (F3). Sortiert nach Stufe und Titel."""
    ersetzt = {str((c.metadata_ or {}).get("kopie_von")) for c in beteiligt
               if c.status == ENTWURF and (c.metadata_ or {}).get("kopie_von")}
    return sorted((c for c in beteiligt if str(c.id) not in ersetzt),
                  key=lambda c: (c.min_grade or 0, c.title or ""))


async def band_abdeckung(db: AsyncSession, subject_id: int, bp: str, schluessel: str,
                         curricula: list[ContextNode], mit_entwuerfen: bool) -> dict | None:
    """Abdeckung der IK eines Bands über die zugeordneten Curricula. `None`, wenn es das Band in
    der Fassung nicht gibt."""
    from app.context.service import load_curriculum_tree

    alle = await kompetenzen_der_fassung(db, subject_id, bp)
    band: Band | None = next((b for b in baender_aus(alle) if b.schluessel == schluessel), None)
    if band is None:
        return None
    iks = [k for k in alle if band_schluessel(k.metadata_) == schluessel]

    titel_je_id = {str(c.id): c.title for c in curricula}
    beteiligt: list[ContextNode] = []
    offen: list[dict] = []
    for c in curricula:
        if fassung_von(c) != bp or (c.status == ENTWURF and not mit_entwuerfen):
            continue
        b, kandidaten = band_zuordnen(baender_aus(alle), c.min_grade, c.max_grade, (c.metadata_ or {}).get("band"))
        if b is not None and b.schluessel == schluessel:
            beteiligt.append(c)
        elif b is None and any(k.schluessel == schluessel for k in kandidaten):
            offen.append(_kurz(c, titel_je_id))
    beteiligt = _ohne_ersetzte(beteiligt)

    # Je IK: welche Curricula sie voll oder partiell verknüpfen.
    traeger: dict[UUID, list[dict]] = {}
    for c in beteiligt:
        tree = await load_curriculum_tree(db, c.id)
        if not tree:
            continue
        voll, teil, _ = verknuepfungen(tree)
        for k_id in set(voll) | set(teil):
            traeger.setdefault(k_id, []).append(
                {"id": str(c.id), "title": c.title, "partiell": k_id not in voll})

    zaehler = {VERKNUEPFT: 0, PARTIELL: 0, FEHLT: 0}
    gruppen: dict[str, list[dict]] = {}
    for k in sorted(iks, key=lambda k: _sortschluessel((k.metadata_ or {}).get("kompetenz_nr"))):
        meta = k.metadata_ or {}
        nr = meta.get("kompetenz_nr")
        t = traeger.get(k.id, [])
        zustand = (VERKNUEPFT if any(not x["partiell"] for x in t) else PARTIELL if t else FEHLT)
        zaehler[zustand] += 1
        gruppen.setdefault(bereich_von(meta), []).append(
            {"node_id": str(k.id), "nr": nr, "titel": _text(k.title, nr), "zustand": zustand,
             "curricula": t})

    return {
        "bp_version": bp, "band": band.als_dict(), "mit_entwuerfen": mit_entwuerfen,
        "curricula": [_kurz(c, titel_je_id) for c in beteiligt],
        "nicht_zugeordnet": offen,
        "ik": {"gesamt": len(iks), **zaehler,
               "gruppen": [{"titel": t, "kompetenzen": ks} for t, ks in gruppen.items()]},
    }


async def pk_abdeckung(db: AsyncSession, subject_id: int, bp: str, curricula: list[ContextNode],
                      mit_entwuerfen: bool) -> dict:
    """Abdeckung der PK einer Fassung über **alle** Curricula des Fachs in dieser Fassung
    (0.46, Schritt 9): Die PK gelten für die ganze Fassung; ein einzelnes Curriculum fördert nie
    alle. Je PK die Curricula und die Zahl ihrer Lernsequenzen, die sie fördern."""
    from app.context.service import load_curriculum_tree

    pks = await kompetenzen_der_fassung(db, subject_id, bp, "pk_kompetenz")
    titel_je_id = {str(c.id): c.title for c in curricula}
    beteiligt = _ohne_ersetzte([c for c in curricula if fassung_von(c) == bp
                                and (c.status != ENTWURF or mit_entwuerfen)])

    traeger: dict[UUID, list[dict]] = {}
    for c in beteiligt:
        tree = await load_curriculum_tree(db, c.id)
        if not tree:
            continue
        _, _, gefoerdert = verknuepfungen(tree)
        for k_id, lss in gefoerdert.items():
            traeger.setdefault(k_id, []).append({"id": str(c.id), "title": c.title, "anzahl": len(lss)})

    gruppen: dict[str, list[dict]] = {}
    for k in sorted(pks, key=lambda k: _sortschluessel((k.metadata_ or {}).get("kompetenz_nr"))):
        meta = k.metadata_ or {}
        nr = meta.get("kompetenz_nr")
        t = traeger.get(k.id, [])
        gruppen.setdefault(bereich_von(meta), []).append(
            {"node_id": str(k.id), "nr": nr, "titel": _text(k.title, nr),
             "zustand": GEFOERDERT if t else FEHLT, "anzahl": sum(x["anzahl"] for x in t), "curricula": t})

    return {
        "bp_version": bp, "mit_entwuerfen": mit_entwuerfen,
        "curricula": [_kurz(c, titel_je_id) for c in beteiligt],
        "pk": {"gesamt": len(pks), GEFOERDERT: sum(1 for k in pks if traeger.get(k.id)),
               FEHLT: sum(1 for k in pks if not traeger.get(k.id)),
               "gruppen": [{"titel": t, "kompetenzen": ks} for t, ks in gruppen.items()]},
    }


GEFOERDERT = "gefoerdert"
ZUSTAENDE = {VERKNUEPFT: "verknüpft", PARTIELL: "partiell", FEHLT: "fehlt", GEFOERDERT: "gefördert"}


def abdeckung_pdf(a: dict, fach: str, nur_luecken: bool = False) -> bytes:
    """Abdeckung über das Band (IK, `a["ik"]`) oder über die Fassung (PK, `a["pk"]`) als PDF —
    die Liste wie auf der Seite (weasyprint, Vorlage `abdeckung_pdf.html`)."""
    import os
    from datetime import date

    import weasyprint
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from app.config import settings

    ik = "ik" in a
    teil = a["ik"] if ik else a["pk"]

    def traeger(k: dict) -> str:
        if ik:
            return ", ".join(c["title"] + (" (partiell)" if c["partiell"] else "") for c in k["curricula"])
        return ", ".join(f"{c['title']} ({c['anzahl']} LS)" for c in k["curricula"])

    gut = VERKNUEPFT if ik else GEFOERDERT
    gruppen = []
    for g in teil["gruppen"]:
        zeilen = [{**k, "zustand_text": ZUSTAENDE[k["zustand"]], "traeger": traeger(k)}
                  for k in g["kompetenzen"] if not nur_luecken or k["zustand"] != gut]
        if zeilen:
            gruppen.append({"titel": g["titel"], "kompetenzen": zeilen})
    if ik:
        titel = "IK-Abdeckung im Band"
        ort = f"BP {a['bp_version']} · {a['band']['schluessel']}"
        bilanz = f"{teil['verknuepft']} von {teil['gesamt']} IK verknüpft" + (
            f" · {teil['partiell']} partiell" if teil["partiell"] else "") + (
            f" · {teil['fehlt']} fehlen" if teil["fehlt"] else "")
    else:
        titel = "PK-Abdeckung der Fassung"
        ort = f"BP {a['bp_version']}"
        bilanz = f"{teil[GEFOERDERT]} von {teil['gesamt']} PK gefördert" + (
            f" · {teil['fehlt']} ohne Lernsequenz" if teil["fehlt"] else "")
    zusatz = (" · mit Entwürfen" if a["mit_entwuerfen"] else "") + (" · nur Lücken" if nur_luecken else "")

    vorlagen = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(vorlagen), autoescape=select_autoescape(["html"]))
    html = env.get_template("abdeckung_pdf.html").render(
        titel=titel, school_name=settings.export_school_name or "",
        unterzeile=f"{fach} · {ort} · Stand {date.today().strftime('%d.%m.%Y')}{zusatz}",
        a=a, bilanz=bilanz, gruppen=gruppen,
        leer="Alle Kompetenzen sind abgedeckt." if teil["gesamt"] else "Keine Kompetenzen hinterlegt.")
    return weasyprint.HTML(string=html, base_url=vorlagen).write_pdf()
