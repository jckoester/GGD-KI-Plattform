"""Die Werkzeuge des MCP-Servers — nur lesend (0.54, Päckchen AW Schritt 4, F2).

Sieben Werkzeuge über dieselben Lesefunktionen wie Oberfläche und Curriculum-Assistent;
gelesen wird mit den Rechten der Person hinter dem Token (`principal`), also wie im Browser:
Entwürfe für Lehrkräfte sichtbar (seit 0.52), private Curricula nur die eigenen.

**Keine Personen in den Ausgaben (F6).** Weder Pseudonyme noch Namen; `_ohne_personen` nimmt
die bekannten Felder heraus, bevor eine Antwort das Haus verlässt. Kennungen von Curricula,
Kapiteln und Bausteinen bleiben — ein Programm braucht sie für Folgeaufrufe.

**Fehler** fürs Programm als `ToolError` mit lesbarer Meldung, nie als Stacktrace.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import principal

LESEND = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                         open_world_hint=False)

#: Felder, die eine Person bezeichnen — fliegen aus jeder Antwort (F6).
PERSONENFELDER = frozenset({
    "owner_pseudonym", "pseudonym", "created_by", "updated_by", "geaendert_von", "autor",
    "author", "von_mir", "sub",
})


def _ohne_personen(wert: Any) -> Any:
    if isinstance(wert, dict):
        return {k: _ohne_personen(v) for k, v in wert.items() if k not in PERSONENFELDER}
    if isinstance(wert, list):
        return [_ohne_personen(v) for v in wert]
    if isinstance(wert, UUID):
        return str(wert)
    return wert


def _uuid(roh: str, was: str) -> UUID:
    try:
        return UUID(str(roh).strip())
    except ValueError:
        raise ToolError(f"Ungültige Kennung für {was}: „{roh}“.") from None


# ── Die Lesefunktionen `lies_…(db, user, …)` — ohne MCP, einzeln testbar ───────


async def lies_leitlinien(db: AsyncSession, user) -> dict:
    from app.context.leitlinien import alle_leitlinien

    return {"leitlinien": [
        {"kuerzel": l.kuerzel, "titel": l.titel,
         "aspekte": [{"kuerzel": a.kuerzel, "titel": a.titel} for a in l.aspekte]}
        for l in await alle_leitlinien(db)],
        "hinweis": "Wo eine Leitlinie im Unterricht vorkommt: leitlinie_uebersicht mit ihrem Kürzel."}


async def lies_leitperspektiven(db: AsyncSession, user, kuerzel: str | None) -> dict:
    from app.context.curriculum_assistent import leitperspektiven_lesen as lesen

    aus = await lesen(db, kuerzel)
    aus["hinweis"] = ("Wo eine Leitperspektive im Unterricht vorkommt: leitlinie_uebersicht mit "
                      "ihrem Kürzel (etwa BNE oder LFDB).")
    return aus


async def _leitlinie_oder_leitperspektive(db: AsyncSession, kuerzel: str) -> UUID:
    """Kürzel einer Leitlinie der Schule oder einer Leitperspektive → Knoten-ID."""
    from app.context.leitlinien import alle_leitlinien
    from app.context.service import leitperspektive_code, normalize_lp_code
    from app.db.models import ContextNode

    k = kuerzel.strip()
    for l in await alle_leitlinien(db):
        if l.kuerzel.casefold() == k.casefold():
            return l.id
    code = normalize_lp_code(k)
    for knoten in (await db.execute(sa.select(ContextNode).where(
            ContextNode.content_type == "leitperspektive", ContextNode.status == "active"))).scalars():
        if leitperspektive_code(knoten.metadata_) == code:
            return knoten.id
    raise ToolError(f"Keine Leitlinie und keine Leitperspektive mit dem Kürzel „{kuerzel}“. "
                    "Die Kürzel nennen leitlinien und leitperspektiven.")


async def lies_uebersicht(db: AsyncSession, user, kuerzel: str, nur_veroeffentlicht: bool) -> dict:
    from app.context.leitlinien_uebersicht import leitlinien_uebersicht

    aus = await leitlinien_uebersicht(db, await _leitlinie_oder_leitperspektive(db, kuerzel), user,
                                      nur_veroeffentlicht=nur_veroeffentlicht)
    faecher = {str(f["id"]): f["name"] for f in aus.pop("alle_faecher")}
    for a in aus["aspekte"]:  # Fach-ID → Fachname, damit das Programm nicht nachschlagen muss
        a["je_fach"] = {faecher.get(i, i): n for i, n in a["je_fach"].items()}
    aus["faecher_ohne_fundstelle"] = [n for i, n in faecher.items()
                                     if n not in {f["name"] for f in aus["faecher"]}]
    aus["faecher"] = [f["name"] for f in aus["faecher"]]
    return aus


async def lies_curricula(db: AsyncSession, user, fach: str | None, jahrgangsstufe: str | None) -> dict:
    from app.auth.vorschau import eigenes_zaehlt
    from app.context.curriculum_entwurf import ENTWURF, darf_entwurf_lesen
    from app.context.grades import parse_grade_band
    from app.db.models import ContextNode, Subject

    status = ["active", ENTWURF] if darf_entwurf_lesen(user) else ["active"]
    abfrage = (
        sa.select(ContextNode, Subject.name).outerjoin(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.content_type == "curriculum", ContextNode.status.in_(status),
               sa.or_(ContextNode.read_scope.in_(["global", "school", "subject"]),
                      sa.and_(sa.literal(eigenes_zaehlt(user.sub)), ContextNode.owner_pseudonym == user.sub)))
        .order_by(Subject.sort_order, Subject.name, ContextNode.min_grade, ContextNode.title))
    if f := (fach or "").strip():
        muster = f"%{f}%"
        abfrage = abfrage.where(sa.or_(Subject.name.ilike(muster), Subject.slug.ilike(muster),
                                       Subject.fach_code.ilike(f)))
    if j := (jahrgangsstufe or "").strip():
        lo, hi = parse_grade_band(j)
        if lo is None:
            raise ToolError(f"Unbekannte Jahrgangsstufe „{jahrgangsstufe}“ — etwa '7' oder '7/8'.")
        abfrage = abfrage.where(sa.or_(ContextNode.max_grade.is_(None), ContextNode.max_grade >= lo),
                                sa.or_(ContextNode.min_grade.is_(None), ContextNode.min_grade <= (hi or lo)))
    zeilen = (await db.execute(abfrage)).all()
    return {"curricula": [{
        "curriculum_id": str(c.id), "titel": c.title, "fach": name,
        "jahrgangsstufe": (c.metadata_ or {}).get("jahrgangsstufe"),
        "bp_version": (c.metadata_ or {}).get("bp_version") or c.bp_version,
        "status": "entwurf" if c.status == ENTWURF else "veröffentlicht",
        **({"ersetzt_curriculum_id": (c.metadata_ or {})["kopie_von"]}
           if c.status == ENTWURF and (c.metadata_ or {}).get("kopie_von") else {}),
    } for c, name in zeilen],
        "hinweis": "Ein Entwurf mit ersetzt_curriculum_id soll das veröffentlichte Curriculum ablösen."}


async def _curriculum_fuer_werkzeug(db: AsyncSession, user, curriculum_id: str):
    from app.context.router import _lesbares_curriculum

    try:
        return await _lesbares_curriculum(db, _uuid(curriculum_id, "das Curriculum"), user)
    except HTTPException as e:
        raise ToolError(e.detail if isinstance(e.detail, str) else "Kein Zugriff auf dieses Curriculum.") from None


async def lies_curriculum(db: AsyncSession, user, curriculum_id: str) -> dict:
    from app.context.curriculum_assistent import entwurf_lesen

    aus = await entwurf_lesen(db, user, await _curriculum_fuer_werkzeug(db, user, curriculum_id))
    aus["status"] = "entwurf" if aus.get("status") == "draft" else "veröffentlicht"
    return aus


async def lies_abdeckung(db: AsyncSession, user, curriculum_id: str) -> dict:
    from app.context.curriculum_assistent import abdeckung_kompakt

    return await abdeckung_kompakt(db, await _curriculum_fuer_werkzeug(db, user, curriculum_id))


async def lies_kompetenzen(db: AsyncSession, user, fach: str, jahrgangsstufe: str, bp_version: str | None,
                            bereich: str | None, typ: str) -> dict:
    """IK/PK eines Fachs für ein Band — dieselbe Auswahl wie im Curriculum-Assistenten, nur ohne
    Curriculum: ein ungespeicherter Knoten trägt Fach, Fassung und Stufen."""
    from app.context.curriculum_assistent import kompetenzen_lesen as lesen
    from app.context.editions import aktive_bp_version
    from app.context.grades import parse_grade_band
    from app.db.models import ContextNode, Subject

    f = fach.strip()
    faecher = (await db.execute(sa.select(Subject).where(sa.or_(
        Subject.name.ilike(f), Subject.slug.ilike(f), Subject.fach_code.ilike(f))))).scalars().all() or \
        (await db.execute(sa.select(Subject).where(Subject.name.ilike(f"%{f}%")))).scalars().all()
    if len(faecher) != 1:
        namen = ", ".join(s.name for s in faecher)
        raise ToolError(f"Fach „{fach}“ nicht eindeutig: {namen}." if faecher else f"Fach „{fach}“ unbekannt.")
    s = faecher[0]
    lo, hi = parse_grade_band(jahrgangsstufe)
    if lo is None:
        raise ToolError(f"Unbekannte Jahrgangsstufe „{jahrgangsstufe}“ — etwa '7' oder '7/8'.")
    fassungen = set((await db.execute(sa.select(ContextNode.bp_version).where(
        ContextNode.subject_id == s.id, ContextNode.content_type == "ik_kompetenz",
        ContextNode.status == "active", ContextNode.bp_version.isnot(None)).distinct())).scalars())
    bp = (bp_version or "").strip() or aktive_bp_version(lo, fassungen)
    if not bp or bp not in fassungen:
        raise ToolError(f"Keine Kompetenzen für {s.name} in der Fassung „{bp or '?'}“. "
                        f"Vorhanden: {', '.join(sorted(fassungen)) or 'keine'}.")
    band = ContextNode(subject_id=s.id, min_grade=lo, max_grade=hi or lo, bp_version=bp,
                       metadata_={"fach": s.name, "bp_version": bp, "jahrgangsstufe": jahrgangsstufe.strip()})
    aus = await lesen(db, band, bereich, "pk" if typ == "pk" else "ik")
    aus["fassungen"] = sorted(fassungen)
    return aus


# ── Registrierung ─────────────────────────────────────────────────────────────


def registrieren(server: MCPServer, sitzung: Callable[[], AsyncSession] | None = None) -> None:
    """Registriert alle Werkzeuge; ``sitzung`` ist die Fabrik für Datenbanksitzungen."""
    if sitzung is None:
        from app.db.session import AsyncSessionLocal

        sitzung = AsyncSessionLocal

    async def ausfuehren(lesen, *args) -> dict:
        user = principal()
        async with sitzung() as db:  # ohne commit: Die Sitzung schließt, nichts bleibt
            aus = await lesen(db, user, *args)
        return _ohne_personen(aus)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Die Leitlinien der Schule (etwa Nachhaltigkeitsziele, Weltethos) mit Kürzeln und Aspekten."))
    async def leitlinien() -> dict:
        return await ausfuehren(lies_leitlinien)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Die Leitperspektiven des Bildungsplans Baden-Württemberg (BNE, BTV, PG, BO, MB, VB) und der "
        "Leitfaden Demokratiebildung (LFDB) mit ihren Aspekten bzw. Bausteinen, Themenblöcken und "
        "Kompetenzen."))
    async def leitperspektiven(
        kuerzel: Annotated[str | None, Field(description="Nur diese, etwa 'BNE' oder 'LFDB'; leer = alle.")] = None,
    ) -> dict:
        return await ausfuehren(lies_leitperspektiven, kuerzel)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Wo eine Leitlinie der Schule oder eine Leitperspektive in den Curricula vorkommt: je Aspekt die "
        "Fundstellen (Fach, Klassenstufen, Curriculum, Kapitel, Lernsequenz; Entwürfe gekennzeichnet), "
        "die Zahl je Fach und die Aspekte ohne Fundstelle."))
    async def leitlinie_uebersicht(
        kuerzel: Annotated[str, Field(description="Kürzel der Leitlinie oder Leitperspektive, etwa 'BNE', 'LFDB' oder 'SDG'.")],
        nur_veroeffentlicht: Annotated[bool, Field(description="Nur veröffentlichte Curricula; sonst zählen Entwürfe mit.")] = False,
    ) -> dict:
        return await ausfuehren(lies_uebersicht, kuerzel, nur_veroeffentlicht)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Die Curricula der Schule mit Kennung, Fach, Jahrgangsstufe, Bildungsplan-Fassung und Status "
        "(veröffentlicht oder Entwurf)."))
    async def curricula_finden(
        fach: Annotated[str | None, Field(description="Fachname oder Kürzel; ein Teil genügt.")] = None,
        jahrgangsstufe: Annotated[str | None, Field(description="Stufe oder Band, etwa '7' oder '7/8'.")] = None,
    ) -> dict:
        return await ausfuehren(lies_curricula, fach, jahrgangsstufe)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Ein Curriculum mit Rahmenangaben, Kapiteln, Lernsequenzen und Einträgen: Kompetenzen als Nummern "
        "(ik, ik_teilweise, pk), Begriffe, Hinweise mit Verweisen auf Leitperspektiven und Leitlinien als "
        "Kürzel. Die Texte der Kompetenzen liefert bildungsplan_kompetenzen."))
    async def curriculum_lesen(
        curriculum_id: Annotated[str, Field(description="Kennung aus curricula_finden.")],
    ) -> dict:
        return await ausfuehren(lies_curriculum, curriculum_id)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Abdeckung eines Curriculums: wie viele inhaltsbezogene Kompetenzen des Bands verknüpft, nur "
        "teilweise oder gar nicht sind (fehlende mit Hinweis auf andere Curricula), ungenutzte "
        "prozessbezogene Kompetenzen und welche Aspekte der Leitlinien vorkommen."))
    async def curriculum_abdeckung(
        curriculum_id: Annotated[str, Field(description="Kennung aus curricula_finden.")],
    ) -> dict:
        return await ausfuehren(lies_abdeckung, curriculum_id)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Kompetenzen des Bildungsplans für ein Fach und eine Jahrgangsstufe. Ohne bereich: Übersicht der "
        "Bereiche mit Anzahl und Nummern. Mit bereich: die Kompetenzen mit Nummer und Text."))
    async def bildungsplan_kompetenzen(
        fach: Annotated[str, Field(description="Fachname oder Kürzel, etwa 'Mathematik' oder 'M'.")],
        jahrgangsstufe: Annotated[str, Field(description="Stufe oder Band, etwa '7' oder '7/8'.")],
        bereich: Annotated[str | None, Field(description="Name eines Bereichs aus der Übersicht, ein Nummernpräfix wie '3.2.1' oder 'alle'.")] = None,
        typ: Annotated[str, Field(description="ik = inhaltsbezogen (Vorgabe), pk = prozessbezogen.")] = "ik",
        bp_version: Annotated[str | None, Field(description="Fassung des Bildungsplans; leer = die für die Stufe geltende.")] = None,
    ) -> dict:
        return await ausfuehren(lies_kompetenzen, fach, jahrgangsstufe, bp_version, bereich, typ)
