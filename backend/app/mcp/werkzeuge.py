"""Die Werkzeuge des MCP-Servers — nur lesend (0.54, Päckchen AW Schritt 4, F2).

Elf Werkzeuge über dieselben Lesefunktionen wie Oberfläche und Curriculum-Assistent;
gelesen wird mit den Rechten der Person hinter dem Token (`principal`), also wie im Browser:
Entwürfe für Lehrkräfte sichtbar (seit 0.52), private Curricula nur die eigenen.

**Keine Personen in den Ausgaben (F6).** Weder Pseudonyme noch Namen; `_ohne_personen` nimmt
die bekannten Felder heraus, bevor eine Antwort das Haus verlässt. Kennungen von Curricula,
Kapiteln und Bausteinen bleiben — ein Programm braucht sie für Folgeaufrufe.

**Fehler** fürs Programm als `ToolError` mit lesbarer Meldung, nie als Stacktrace.

**Curricula entwerfen (0.56, BA):** `curriculum_yaml` liefert ein Curriculum als YAML (der
Export), `curriculum_yaml_pruefen` prüft einen Entwurf mit derselben Logik wie der Import in der
Oberfläche — der echte Import in einem Savepoint, der **immer** verworfen wird
(`curriculum_yaml.durchlauf(…, speichern=False)`; der Wächter `test_mcp_nur_lesend` hält das
fest). Anlegen tut die Lehrkraft selbst, in der Plattform, nach der Vorschau.

**Jahresverlaufspläne (0.60, BD Teil B Schritt 6):** `verlaufsplaene_finden` und
`verlaufsplan_lesen` — die Pläne der Fachschaften, wie sie Lehrkräfte in der Bibliothek lesen
(auch Entwürfe und frühere Schuljahre), kompakt über `verlaufsplan.kompakt`.
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
        # Erst genau, dann als Teil (0.60): „M“ traf sonst auch Musik, Chemie und Informatik
        abfrage = abfrage.where(Subject.id.in_(await _faecher(db, f)))
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

    from app.context.querverweise import ik_ids_im_baum, querverweise, verweise_kompakt
    from app.context.service import load_curriculum_tree

    cur = await _curriculum_fuer_werkzeug(db, user, curriculum_id)
    aus = await entwurf_lesen(db, user, cur)
    aus["status"] = "entwurf" if aus.get("status") == "draft" else "veröffentlicht"
    # Querverweise des Bildungsplans in andere Fächer (AY Teil 1, F7) — nur hier, nicht im
    # Curriculum-Assistenten: Dort wären sie eine neue Bedingung für den gemessenen Prompt.
    tree = await load_curriculum_tree(db, cur.id)
    nr_je_id = {str(ik["node_id"]): ik.get("nr")
                for kap in tree.get("kapitel") or [] for ls in kap.get("lernsequenzen") or []
                for e in (ls.get("metadata") or {}).get("eintraege") or [] if isinstance(e, dict)
                for ik in e.get("ik") or [] if isinstance(ik, dict) and ik.get("node_id")}
    qv = await querverweise(db, ik_ids_im_baum(tree), user)
    if qv:
        aus["querverweise"] = [{"ik": nr_je_id.get(kid), "verweise": verweise_kompakt(liste)}
                               for kid, liste in qv.items()]
    # Absprachen mit anderen Fächern (seit 0.63) stehen seit 0.65 je Kapitel (`absprachen`) und als
    # `absprachen_an_das_fach` schon in `entwurf_lesen`.
    return aus


async def lies_abdeckung(db: AsyncSession, user, curriculum_id: str) -> dict:
    from app.context.curriculum_assistent import abdeckung_kompakt

    return await abdeckung_kompakt(db, await _curriculum_fuer_werkzeug(db, user, curriculum_id))


async def lies_verlaufsplaene(db: AsyncSession, user, fach: str | None, jahrgangsstufe: str | None,
                              schuljahr: str | None) -> dict:
    from app.context import verlaufsplan as vp
    from app.context.grades import parse_grade_band
    from app.db.models import ContextNode, Subject

    _nur_lehrkraefte(user)
    abfrage = (sa.select(ContextNode, Subject).join(Subject, Subject.id == ContextNode.subject_id)
               .where(ContextNode.content_type == vp.TYP, ContextNode.status.in_(vp.LESBAR))
               .order_by(Subject.sort_order, Subject.name, ContextNode.min_grade,
                         ContextNode.metadata_["schuljahr"].as_string().desc()))
    if f := (fach or "").strip():
        abfrage = abfrage.where(Subject.id.in_(await _faecher(db, f)))
    if j := (jahrgangsstufe or "").strip():
        lo, hi = parse_grade_band(j)
        if lo is None:
            raise ToolError(f"Unbekannte Jahrgangsstufe „{jahrgangsstufe}“ — etwa '7' oder '7/8'.")
        abfrage = abfrage.where(ContextNode.min_grade >= lo, ContextNode.min_grade <= (hi or lo))
    if sj := (schuljahr or "").strip():
        abfrage = abfrage.where(ContextNode.metadata_["schuljahr"].as_string() == sj)
    zeilen = (await db.execute(abfrage)).all()
    return {"verlaufsplaene": [{
        "verlaufsplan_id": str(p.id), "titel": k["titel"], "fach": k["fach"], "stufe": k["stufe"],
        "schuljahr": k["schuljahr"], "status": "entwurf" if p.status == "draft" else "beschlossen",
        "beschlossen_am": k["beschlossen_am"], "wochen": k["wochen"],
        "planungsart": "sequenzgenau" if k["planungsart"] == vp.SEQUENZ else "kapitelgenau",
        "archiviert": k["archiviert"],
    } for p, fachzeile in zeilen for k in [vp.kurz(p, fachzeile)]],
        "laufendes_schuljahr": vp.aktuelles_schuljahr()}


async def _faecher(db: AsyncSession, f: str) -> list[int]:
    """Fächer zu einer Angabe: erst genau (Name, Slug, Kürzel), nur ohne Treffer als Teil des Namens
    oder Slugs — sonst träfe das Kürzel „M“ auch Musik und Chemie (wie `lies_kompetenzen`)."""
    from app.db.models import Subject

    genau = (await db.execute(sa.select(Subject.id).where(sa.or_(
        Subject.name.ilike(f), Subject.slug.ilike(f), Subject.fach_code.ilike(f))))).scalars().all()
    if genau:
        return list(genau)
    muster = f"%{f}%"
    return list((await db.execute(sa.select(Subject.id).where(sa.or_(
        Subject.name.ilike(muster), Subject.slug.ilike(muster))))).scalars().all())


async def lies_verlaufsplan(db: AsyncSession, user, verlaufsplan_id: str) -> dict:
    from app.context import verlaufsplan as vp

    _nur_lehrkraefte(user)
    plan = await vp.lade(db, _uuid(verlaufsplan_id, "den Jahresverlaufsplan"))
    if plan is None:
        raise ToolError("Diesen Jahresverlaufsplan gibt es nicht.")
    voll = await vp.voll(db, plan, user)
    titel_alt, kapitel_alt = await vp.alte_titel(db, voll)
    return vp.kompakt(voll, titel_alt=titel_alt, kapitel_alt=kapitel_alt)


def _nur_lehrkraefte(user) -> None:
    """Pläne lesen Lehrkräfte und Admins (wie `/context/verlaufsplaene`). Zugangstoken gibt es nur
    für sie (`tokens.ERLAUBTE_ROLLEN`); die Prüfung steht trotzdem hier, falls sich das ändert."""
    if not {"teacher", "admin"} & set(user.roles or []):
        raise ToolError("Jahresverlaufspläne lesen nur Lehrkräfte.")


#: Das Format für `curriculum_yaml_pruefen` — kurz, das Programm hat die Vorlage aus `curriculum_yaml`.
YAML_FORMAT = (
    "Oben: schule, fach_code (Kürzel, etwa 'M'), fach, schulart, jahrgangsstufe (etwa '7/8'), bp_version, "
    "bp_id, vorwort, quelle, rahmen, kapitel. quelle: eine Zeile, woraus der Entwurf entstand, wenn er auf "
    "einer Vorlage beruht (etwa 'Beispielcurriculum Physik Gymnasium Klassen 7–8 (ZSL, Fassung V3.0 vom "
    "08.04.2026)'), höchstens 300 Zeichen; Erläuterungen gehören ins vorwort. Kapitel: titel, reihenfolge, std, hinweis, konkretisierung (Liste), "
    "lernsequenzen, absprachen (Liste von {fach_code, kapitel, jahrgangsstufe, art, text}: Absprachen mit "
    "anderen Fächern; art vorher = das Kapitel des anderen Fachs kommt zuerst, gleichzeitig, nachher, "
    "abgestimmt = inhaltlich ohne Zeit; vorher/gleichzeitig/nachher brauchen kapitel, abgestimmt braucht "
    "text; kapitel = Titel eines Kapitels im Curriculum des anderen Fachs). Lernsequenz: bp_titel, bp_leitidee, reihenfolge, std, eintraege. Eintrag: ik (Liste "
    "von {nr, partiell}), pk (Liste von {id}), konkretisierung, hinweise, material, begriffe, fachmethoden. "
    "Verweise in hinweise: @[Text](lp:BNE), @[Text](lb:<Kürzel der Leitlinie>), @[Text](lba:<Kürzel des "
    "Aspekts>), #[Text](ik:<Fachkürzel>:<Nr>). Keine YAML-Anker (&, *)."
)


async def lies_curriculum_yaml(db: AsyncSession, user, curriculum_id: str) -> dict:
    import yaml

    from app.context.curriculum_export import build_curriculum_export_dict
    from app.context.service import load_curriculum_tree

    node = await _curriculum_fuer_werkzeug(db, user, curriculum_id)
    daten = await build_curriculum_export_dict(db, await load_curriculum_tree(db, node.id))
    return {"yaml": yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            "hinweis": "Vorlage für einen Entwurf. Geändertes YAML mit curriculum_yaml_pruefen prüfen; "
                       "importieren kann es die Lehrkraft in der Plattform (Curricula des Fachs → "
                       "„Aus YAML importieren“). Es entsteht immer ein Entwurf."}


async def lies_yaml_pruefung(db: AsyncSession, user, text: str, ersetzen: str | None) -> dict:
    from app.context.curriculum_yaml import KeinRecht, durchlauf

    ziel = _uuid(ersetzen, "das zu ersetzende Curriculum") if ersetzen else None
    try:
        # Nur lesend: Der Import läuft im Savepoint und wird verworfen (speichern=False, Wächter).
        aus = await durchlauf(db, text, user, ersetzen=ziel, speichern=False)
    except KeinRecht as e:
        aus = {"ok": False, "fehler": [str(e) + " Die Datei kann eine Lehrkraft dieser Fachschaft importieren."],
               "warnungen": []}
    aus["hinweis"] = ("Geprüft, nichts gespeichert. Ohne Fehler kann die Lehrkraft die Datei in der Plattform "
                      "importieren; es entsteht ein Entwurf.")
    return aus


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
    if typ != "pk" and aus.get("bereiche"):
        await _querverweise_an_kompetenzen(db, user, band, aus)
    return aus


async def _querverweise_an_kompetenzen(db: AsyncSession, user, band, aus: dict) -> None:
    """An jede gezeigte Kompetenz ihre Querverweise in andere Fächer (AY Teil 1, F7)."""
    from app.context.curriculum_assistent import kompetenzen_des_bands
    from app.context.querverweise import querverweise, verweise_kompakt

    iks, _ = await kompetenzen_des_bands(db, band)
    id_je_nr = {(k.metadata_ or {}).get("kompetenz_nr"): k.id for k in iks}
    gezeigt = [k for b in aus["bereiche"] for k in b.get("kompetenzen") or []]
    qv = await querverweise(db, [id_je_nr[k["nr"]] for k in gezeigt if k.get("nr") in id_je_nr], user)
    for k in gezeigt:
        if liste := qv.get(str(id_je_nr.get(k.get("nr")))):
            k["querverweise"] = verweise_kompakt(liste)


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
        "Kürzel. Die Texte der Kompetenzen liefert bildungsplan_kompetenzen. Unter querverweise: wo der "
        "Bildungsplan an den verknüpften Kompetenzen auf ein anderes Fach verweist (Kompetenz oder Bereich) "
        "und in welchem Curriculum dieses Fach die Stelle behandelt. Je Kapitel unter absprachen: was die "
        "Fachschaft mit anderen Fächern vereinbart hat (eigene und von anderen Fächern eingetragene; art aus "
        "Sicht dieses Kapitels: vorher = das andere Kapitel kommt zuerst), absprachen_an_das_fach ohne Kapitel."))
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
        "Ein Curriculum als YAML — die Vorlage, um einen Entwurf zu schreiben (Format der Plattform). "
        "Speichern kann das Programm nichts; die Lehrkraft importiert das YAML selbst."))
    async def curriculum_yaml(
        curriculum_id: Annotated[str, Field(description="Kennung aus curricula_finden.")],
    ) -> dict:
        return await ausfuehren(lies_curriculum_yaml, curriculum_id)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Prüft einen Curriculum-Entwurf als YAML mit derselben Logik wie der Import der Plattform, ohne "
        "zu speichern: Fehler und Warnungen mit Stelle, Gliederung mit Stunden, vorhandene Curricula "
        "gleichen Fachs, Jahrgangs und Fassung. Format: " + YAML_FORMAT))
    async def curriculum_yaml_pruefen(
        yaml: Annotated[str, Field(description="Der YAML-Text, höchstens 200 000 Zeichen.", max_length=200_000)],
        ersetzen: Annotated[str | None, Field(description="Kennung eines veröffentlichten Curriculums aus "
                                                           "'vorhanden', das der Entwurf ersetzen soll.")] = None,
    ) -> dict:
        return await ausfuehren(lies_yaml_pruefung, yaml, ersetzen)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Die Jahresverlaufspläne der Fachschaften: je Fach, Klassenstufe und Schuljahr höchstens einer, mit "
        "Kennung, Status (beschlossen oder Entwurf), verplanten Wochen und Planungsart. Frühere Schuljahre "
        "sind archiviert. laufendes_schuljahr nennt das aktuelle."))
    async def verlaufsplaene_finden(
        fach: Annotated[str | None, Field(description="Fachname oder Kürzel; ein Teil genügt.")] = None,
        jahrgangsstufe: Annotated[str | None, Field(description="Klassenstufe oder Band, etwa '9' oder '7/8'.")] = None,
        schuljahr: Annotated[str | None, Field(description="Etwa '2026/27'; leer = alle.")] = None,
    ) -> dict:
        return await ausfuehren(lies_verlaufsplaene, fach, jahrgangsstufe, schuljahr)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Ein Jahresverlaufsplan: die Abschnitte in Reihenfolge mit Dauer in Unterrichtswochen, Woche von–bis, "
        "erstem und letztem Schultag, Ferien darin, Thema, Notiz und den Kapiteln bzw. Lernsequenzen des "
        "Curriculums (Titel mit Kennung; puffer = bewusst freie Wochen). Dazu die Ferien des Schuljahrs, "
        "freie Wochen, die Stundenbilanz je Kapitel (Soll aus dem Curriculum, geplant = Wochen × "
        "Wochenstunden) und Kapitel ohne Abschnitt."))
    async def verlaufsplan_lesen(
        verlaufsplan_id: Annotated[str, Field(description="Kennung aus verlaufsplaene_finden.")],
    ) -> dict:
        return await ausfuehren(lies_verlaufsplan, verlaufsplan_id)

    @server.tool(annotations=LESEND, structured_output=False, description=(
        "Kompetenzen des Bildungsplans für ein Fach und eine Jahrgangsstufe. Ohne bereich: Übersicht der "
        "Bereiche mit Anzahl und Nummern. Mit bereich: die Kompetenzen mit Nummer und Text, dazu "
        "querverweise, wo der Bildungsplan auf ein anderes Fach verweist."))
    async def bildungsplan_kompetenzen(
        fach: Annotated[str, Field(description="Fachname oder Kürzel, etwa 'Mathematik' oder 'M'.")],
        jahrgangsstufe: Annotated[str, Field(description="Stufe oder Band, etwa '7' oder '7/8'.")],
        bereich: Annotated[str | None, Field(description="Name eines Bereichs aus der Übersicht, ein Nummernpräfix wie '3.2.1' oder 'alle'.")] = None,
        typ: Annotated[str, Field(description="ik = inhaltsbezogen (Vorgabe), pk = prozessbezogen.")] = "ik",
        bp_version: Annotated[str | None, Field(description="Fassung des Bildungsplans; leer = die für die Stufe geltende.")] = None,
    ) -> dict:
        return await ausfuehren(lies_kompetenzen, fach, jahrgangsstufe, bp_version, bereich, typ)
