"""Export-Funktionen für Stundenentwürfe: Markdown, PDF, DOCX/ODT."""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextEdge, ContextNode, LessonSlot

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def zeitbudget(phasen) -> tuple[int, int]:
    """(Summe der gesetzten Dauern, Zahl der Phasen ohne Dauer) — für beide Exporte.

    Fehlende Dauern zählen nicht als 0 stillschweigend mit: Die Zahl der Phasen ohne
    Dauer wird genannt, sonst sähe „35′ geplant" vollständig aus, obwohl zwei fehlen.

    Gestrichene Phasen zählen gar nicht (0.19, Jan 18.10.2026) — weder ihre Minuten noch
    als „ohne Dauer". „Offen" zählt mit: Sie war geplant, nur nicht fertig.
    """
    zaehlen = [p for p in phasen if not p.gestrichen]
    gesetzt = [p.dauer_min for p in zaehlen if p.dauer_min is not None]
    return sum(gesetzt), len(zaehlen) - len(gesetzt)


def ohne_dauer_zusatz(anzahl: int) -> str:
    """„ · 2 Phasen ohne Dauer" — oder nichts."""
    if not anzahl:
        return ""
    return f" · {anzahl} {'Phase' if anzahl == 1 else 'Phasen'} ohne Dauer"


def zeitspalte(phasen) -> list[str]:
    """Die Zeitangabe je Phase — für die Tabellen in DOCX und PDF.

    Ohne Dauer ist der Beginn bekannt, das Ende nicht — und damit auch nicht der Beginn
    jeder folgenden Phase: Die Uhr steht, statt die fehlende Dauer als 0 weiterzuzählen.
    Dieselbe Regel wie `startzeiten()` im Planer (`frontend/src/lib/phasendauer.js`).
    """
    zeiten = []
    uhr = 0
    for phase in phasen:
        if phase.gestrichen:
            # Keine Zeit, und die Uhr läuft ohne sie weiter (Jan, 18.10.2026).
            zeiten.append("–")
            continue
        if uhr is None:
            zeiten.append("–")
        elif phase.dauer_min is None:
            zeiten.append(f"ab {uhr}′")
        else:
            zeiten.append(f"{uhr}–{uhr + phase.dauer_min}′")
        uhr = None if uhr is None or phase.dauer_min is None else uhr + phase.dauer_min
    return zeiten


@dataclass
class ExportPhase:
    name: str
    dauer_min: Optional[int]  # None = noch nicht festgelegt (0.13)
    beschreibung: str
    prio: str
    sozialform: str  # display string
    methode: str  # display string
    material: list[str]  # display strings
    # Gestrichen (Nachbereitung oder `strike_phase`): bleibt sichtbar, zählt nicht zur Zeit.
    gestrichen: bool = False


@dataclass
class LessonExport:
    titel: str
    titel_slug: str
    stundenziel: str
    gruppe: str
    gruppe_slug: str
    datum: str  # YYYY-MM-DD or ""
    start_period: Optional[int]
    periods: int
    verfuegbare_min: int
    ue_titel: str
    phasen: list[ExportPhase]
    refs: list[dict]  # [{typ, code, titel, partiell}]

    # Seit 0.17 stehen in `refs` auch Begriffe der Stunde (`typ: concept`). Der Export führt
    # sie getrennt: Unter „Kompetenzen" stünde ein Begriff sonst mit seinem Titel neben den
    # Nummern des Bildungsplans.
    @property
    def kompetenzen(self) -> list[dict]:
        return [r for r in self.refs if r.get("typ") != "concept"]

    @property
    def fachbegriffe(self) -> list[dict]:
        return [r for r in self.refs if r.get("typ") == "concept"]


def _slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[äöü]", lambda m: {"ä": "ae", "ö": "oe", "ü": "ue"}[m.group()], s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60] or "stunde"


_YAML_HEIKEL = re.compile(r"[,:\[\]{}#&*!|>'\"%@`]|^\s|\s$|^-")


def kompetenz_kurz(ref: dict) -> str:
    """Eine Kompetenz, wie sie im Export steht: die Nummer, sonst der Titel, „[…]" bei partiell.

    `or` statt Vorgabewert: Ein gespeicherter Eintrag trägt `"code": null`, und
    `get("code", …)` lieferte dann `None` — im Frontmatter stand „None"."""
    return f"{ref.get('code') or ref.get('titel') or ''}{'[…]' if ref.get('partiell') else ''}"


def begriff_mit_aliasen(ref: dict) -> str:
    """Ein Begriff der Stunde, wie er im Export steht: „elektrophile Substitution
    (σ-Komplex, Arenium-Ion)" — mit den Aliasen, unter denen die Stunde ihn nennt."""
    titel = str(ref.get("titel") or "")
    aliase = [str(a) for a in ref.get("aliase") or [] if a]
    return f"{titel} ({', '.join(aliase)})" if aliase else titel


def _yaml_eintrag(text: str) -> str:
    """Ein Eintrag einer Flow-Liste im Frontmatter — in Anführungszeichen, wo YAML ihn sonst
    zerlegte. „Säure, Base" wären ohne sie zwei Einträge; ein Titel mit Doppelpunkt brächte
    die ganze Kopfzeile zu Fall."""
    return json.dumps(text, ensure_ascii=False) if _YAML_HEIKEL.search(text) else text


def _display_linked(item: dict) -> str:
    if not item:
        return ""
    if item.get("typ") == "node":
        return item.get("titel") or item.get("node_id", "")
    return item.get("wert") or ""


async def build_lesson_export(db: AsyncSession, node_id: UUID) -> LessonExport:
    lesson = await db.get(ContextNode, node_id)
    if not lesson:
        raise ValueError(f"Stunde {node_id} nicht gefunden")

    meta = lesson.metadata_ or {}

    # Slot
    slot_result = await db.execute(
        sa.select(LessonSlot).where(LessonSlot.stunde_node_id == node_id)
    )
    slot = slot_result.scalar_one_or_none()

    # UE
    ue_edge = (
        await db.execute(
            sa.select(ContextEdge).where(
                ContextEdge.from_node_id == node_id,
                ContextEdge.relation == "part_of",
            )
        )
    ).scalar_one_or_none()
    ue_titel = ""
    if ue_edge:
        ue_node = await db.get(ContextNode, ue_edge.to_node_id)
        if ue_node:
            ue_titel = ue_node.title

    # Gruppe
    gruppe = ""
    if lesson.write_scope_group_id:
        from app.db.models import Group
        g = await db.get(Group, lesson.write_scope_group_id)
        if g:
            gruppe = g.name

    datum = slot.date.isoformat() if slot else ""
    periods = slot.periods if slot else 1
    start_period = slot.start_period if slot else None

    phasen = [
        ExportPhase(
            name=p.get("name", ""),
            dauer_min=p.get("dauer_min"),
            beschreibung=p.get("beschreibung") or "",
            prio=p.get("prio", "kern"),
            sozialform=_display_linked(p.get("sozialform") or {}),
            methode=_display_linked(p.get("methode") or {}),
            material=[_display_linked(m) for m in (p.get("material") or [])],
            gestrichen=p.get("status") == "gestrichen",
        )
        for p in meta.get("phasen", [])
    ]

    return LessonExport(
        titel=lesson.title,
        titel_slug=_slugify(lesson.title),
        stundenziel=meta.get("stundenziel") or "",
        gruppe=gruppe,
        gruppe_slug=_slugify(gruppe) if gruppe else "gruppe",
        datum=datum,
        start_period=start_period,
        periods=periods,
        verfuegbare_min=periods * 45,
        ue_titel=ue_titel,
        phasen=phasen,
        refs=meta.get("refs", []),
    )


def export_markdown(data: LessonExport) -> str:
    prio_labels = {"kern": "Kern", "uebung": "Übung", "vertiefung": "Vertiefung"}
    lines = [
        "---",
        f"titel: {data.titel}",
        f"datum: {data.datum}",
        f"gruppe: {data.gruppe}",
        f"ue: {data.ue_titel}",
        f"verfuegbar_min: {data.verfuegbare_min}",
    ]
    if data.kompetenzen:
        kompetenzen = [_yaml_eintrag(kompetenz_kurz(r)) for r in data.kompetenzen]
        lines.append(f"kompetenzen: [{', '.join(kompetenzen)}]")
    if data.fachbegriffe:
        fachbegriffe = [_yaml_eintrag(begriff_mit_aliasen(r)) for r in data.fachbegriffe]
        lines.append(f"fachbegriffe: [{', '.join(fachbegriffe)}]")
    lines += ["---", ""]

    if data.stundenziel:
        lines += [f"**Stundenziel:** {data.stundenziel}", ""]

    total, ohne = zeitbudget(data.phasen)
    lines.append(
        f"Zeitbudget: {total}′ geplant / {data.verfuegbare_min}′ verfügbar"
        + (f" (**+{total - data.verfuegbare_min}′ Überhang**)" if total > data.verfuegbare_min else "")
        + ohne_dauer_zusatz(ohne)
    )
    lines.append("")

    for phase in data.phasen:
        prio = prio_labels.get(phase.prio, phase.prio)
        # Ohne Dauer nur die Prio — nie `0′`, nie `None′`.
        dauer = f"{phase.dauer_min}′ · " if phase.dauer_min is not None else ""
        if phase.gestrichen:
            lines.append(f"## ~~{phase.name}~~ ({dauer}{prio}, gestrichen)")
        else:
            lines.append(f"## {phase.name} ({dauer}{prio})")
        if phase.beschreibung:
            lines.append("")
            lines.append(phase.beschreibung)
        if phase.sozialform:
            lines.append(f"- **Sozialform:** {phase.sozialform}")
        if phase.methode:
            lines.append(f"- **Methode:** {phase.methode}")
        if phase.material:
            for m in phase.material:
                if m:
                    lines.append(f"- **Material:** {m}")
        lines.append("")

    return "\n".join(lines)


async def export_pdf(data: LessonExport) -> bytes:
    try:
        import weasyprint
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as e:
        raise RuntimeError(
            f"PDF-Export benötigt 'weasyprint' und 'jinja2' ({e})."
        ) from e

    # Phase 17 (D5): Beschreibungen/Stundenziel als Inline-Markdown mit server-gerenderten
    # Formeln ($…$ → eingebettetes SVG) vor-rendern (kompakte Tabellenzellen → inline).
    from app.render.export import render_markdown_inline_for_pdf

    beschreibungen = [await render_markdown_inline_for_pdf(p.beschreibung or "") for p in data.phasen]
    stundenziel_html = await render_markdown_inline_for_pdf(data.stundenziel or "")

    # Kompetenzen: Meist steht die Nummer (`code`) da, aber ohne sie fällt die Anzeige auf
    # den Titel zurück — und Bildungsplan-Titel tragen Formeln (`… die Zahl \(\pi\) …`).
    # Deshalb derselbe Prärenderer. Der Markdown-Export bleibt bewusst bei der TeX-Quelle:
    # Dort ist sie das richtige Format, nicht eingebettetes SVG.
    refs_html = [
        {
            "html": await render_markdown_inline_for_pdf(
                str(r.get("code") or r.get("titel") or "")
            ),
            "partiell": bool(r.get("partiell")),
        }
        for r in data.kompetenzen
    ]
    # Begriffe mit Titel und Aliasen, durch denselben Prärenderer (Formeln in Titeln).
    begriffe_html = [
        await render_markdown_inline_for_pdf(begriff_mit_aliasen(r)) for r in data.fachbegriffe
    ]

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    # Zeiten und Budget rechnet Python, das Template zeigt sie nur an — bis 0.13.0 rechnete
    # es selbst und brach an einer Phase ohne Dauer mit `int + None` ab.
    total, ohne = zeitbudget(data.phasen)
    template = env.get_template("lesson.html")
    html_str = template.render(
        data=data,
        beschreibungen=beschreibungen,
        stundenziel_html=stundenziel_html,
        refs_html=refs_html,
        begriffe_html=begriffe_html,
        zeiten=zeitspalte(data.phasen),
        total=total,
        ohne_dauer=ohne_dauer_zusatz(ohne),
    )
    return weasyprint.HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()


#: Spaltenanteile der Phasentabelle in DOCX/ODT in Prozent — Zeit, Prio, Phase, Sozialform/Methode,
#: Material. Angelehnt an `templates/lesson.html` (PDF: 12/6/34/23/25), die Prio-Spalte aber 8 statt
#: 6: Word zieht beidseits Zellränder ab, und bei 6 % brach der Kopf „Prio" um.
_SPALTEN_ANTEILE = (12, 8, 34, 23, 23)

_PRIO_KUERZEL = {"kern": "K", "uebung": "Ü", "vertiefung": "V"}
#: Unter der Tabelle. Seit 0.39 ohne Zellfarbe — Pandoc kann keine setzen (Plan F3).
PRIO_LEGENDE = "Prio: K = Kern · Ü = Übung · V = Vertiefung"


async def export_office(
    db: AsyncSession, data: LessonExport, fmt: str, reference_doc: Optional[str] = None
) -> bytes:
    """Stundenentwurf als DOCX oder ODT über Pandoc (seit 0.39; bis dahin `python-docx`).

    Stundenziel, Beschreibungen, Kompetenzen und Fachbegriffe sind Markdown wie in der Werkstatt:
    Formeln werden Word-Formeln, Diagramme Bilder. Inhalt und Reihenfolge wie im PDF.
    """
    from app.export import office as o

    total, ohne = zeitbudget(data.phasen)
    teile: dict[str, str] = {}
    if data.stundenziel:
        teile["ziel"] = f"**Stundenziel:** {data.stundenziel}"
    for i, phase in enumerate(data.phasen):
        teile[f"p{i}"] = phase.beschreibung or ""
    if data.kompetenzen:
        teile["kompetenzen"] = "**Kompetenzen:** " + ", ".join(
            kompetenz_kurz(r) for r in data.kompetenzen)
    if data.fachbegriffe:
        teile["begriffe"] = "**Fachbegriffe:** " + ", ".join(
            begriff_mit_aliasen(r) for r in data.fachbegriffe)
    bloecke, api = await o.markdown_zu_bloecken(db, teile)

    dok = [o.ueberschrift(1, o.text(data.titel))]
    kopf = [t for t in (data.datum, data.gruppe, f"UE: {data.ue_titel}" if data.ue_titel else "") if t]
    if kopf:
        dok.append(o.absatz(o.text(" · ".join(kopf))))
    dok += bloecke.get("ziel", [])

    budget = f"Zeitbudget: {total}′ / {data.verfuegbare_min}′ verfügbar"
    if total > data.verfuegbare_min:
        budget += f" (+{total - data.verfuegbare_min}′ Überhang)"
    dok.append(o.absatz(o.text(budget + ohne_dauer_zusatz(ohne))))

    if data.phasen:
        zeilen = []
        for i, (phase, zeit) in enumerate(zip(data.phasen, zeitspalte(data.phasen))):
            name = [o.fett(o.text(phase.name))]
            if phase.gestrichen:
                name += o.text(" (gestrichen)")
            phase_zelle = [o.schlicht(name), *bloecke[f"p{i}"]]
            if phase.gestrichen:
                phase_zelle = o.durchstreichen(phase_zelle)
            sozial = []
            if phase.sozialform:
                sozial.append(o.schlicht([o.fett(o.text(phase.sozialform))]))
            if phase.methode:
                sozial.append(o.schlicht(o.text(phase.methode)))
            material = [o.schlicht(o.text(m)) for m in phase.material if m]
            zeilen.append([
                [o.schlicht(o.text(zeit))],
                [o.schlicht([o.fett(o.text(_PRIO_KUERZEL.get(phase.prio, "?")))])],
                phase_zelle,
                sozial,
                material,
            ])
        dok.append(o.tabelle(
            ["Zeit", "Prio", "Phase", "Sozialform / Methode", "Material"],
            zeilen,
            [a / 100 for a in _SPALTEN_ANTEILE],
        ))
        dok.append(o.absatz(o.text(PRIO_LEGENDE)))

    dok += bloecke.get("kompetenzen", []) + bloecke.get("begriffe", [])
    return await o.dokument_zu_office(dok, api_version=api, fmt=fmt, reference_doc=reference_doc)
