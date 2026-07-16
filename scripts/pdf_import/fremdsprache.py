"""Fremdsprachen-Assembler: neutrale Struktur → JSONL-Knoten (KS-Plan C3, Schritt 3).

Deterministisch — erzeugt EXAKT die bp_id-/Parent-/Content-Struktur, die der HTML-Scraper
für ein reguläres Fach produziert (`scripts/scraper/parsers.py`), damit der bestehende Import
(`scripts/import_bildungsplan.py`) sie unverändert frisst und in die vorhandene
Fachplan-/Curriculum-/Frontier-Anzeige einordnet.

bp_id-Baukasten (aus der Scraper-Kartierung):
    Fachplan     {BASE}                              parent=None
      Leitidee   {BASE}_IK_{JG}_{LI}                 parent=Fachplan       (Kompetenzbereich)
        Leitidee {BASE}_IK_{JG}_{LI}_{NR}            parent=2-seg-Leitidee (Teilbereich)
          IK     {Leitidee}_{n:02d}                  parent=Leitidee
      PK-Gruppe  {BASE}_PK_{g:02d}                   parent=Fachplan
        PK-Komp. {PKGruppe}_{n:02d}                  parent=PK-Gruppe

BASE = {bp_basis}_ALLG_{schulart}_{fach_code}{suffix}, z. B. BP2016BW_ALLG_GYM_E1.V2.
{JG} = Jahrgangsband (z. B. 5-6, 11-12-LF); min/max_grade/niveau werden zusätzlich explizit
gesetzt (nicht aus der bp_id abgeleitet). Querverweise auf Leitperspektiven → `relations`
(`references`), analog `scripts/scraper/references.py`.
"""
from __future__ import annotations

import re

from scripts.pdf_import.nodes import build_node
from scripts.scraper.parsers import expand_operator_title

# Leitperspektiven-Verweise → `references`-Kanten. Die Fremdsprachen-BPs nennen (anders als
# die MINT-Fächer) meist das bloße Kürzel ohne Aspektnummer → Kante auf den LP-ÜBERSICHTS-
# knoten (BP2016BW_ALLG_LP_<KÜRZEL>). Mit Aspektnummer → Kante auf den Aspektknoten
# (<KÜRZEL>_NN), wie beim HTML-Scraper (vgl. references._LP_PATTERN). Beide Ziele existieren
# als Knoten; unauflösbare Ziele erzeugen beim Import nur eine Warnung (kein Abbruch).
_LP_REF_RE = re.compile(r"^\s*(BNE|BTV|PG|BO|MB|VB|LFDB)[\s:_.\-]*(\d{1,2})?", re.IGNORECASE)
_LP_OVERVIEW_PREFIX = "BP2016BW_ALLG_LP_"


_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")


def _clean_text(s: str | None) -> str:
    """Normalisiert PDF-Typografie: Leerzeichen vor Satzzeichen entfernen (die Quell-PDFs
    setzen `Wort .` statt `Wort.`), Mehrfach-Leerzeichen kollabieren. Konservativ — trifft
    nur Leerzeichen DIREKT vor .,;:!? (lässt Abkürzungen wie „z. B." unangetastet)."""
    s = _SPACE_BEFORE_PUNCT.sub(r"\1", (s or "").strip())
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def _last_num(nummer: str) -> int:
    """Letzte Gliederungszahl einer Abschnittsnummer: '3.1.1' → 1, '2.10' → 10."""
    return int(str(nummer).strip().split(".")[-1])


def _band_segment(von: int, bis: int, niveau: str | None) -> str:
    """Jahrgangsband-Segment der bp_id: '5-6', '11-12', mit Niveau '11-12-BF'/'-LF'."""
    grades = f"{von}" if von == bis else f"{von}-{bis}"
    if niveau == "basis":
        grades += "-BF"
    elif niveau == "leistung":
        grades += "-LF"
    return grades


def _lp_relations(verweise: list[str]) -> list[dict]:
    """Leitperspektiven-Verweise → `references`-Kanten (dedupliziert).

    Kürzel mit Aspektnummer → Aspektknoten `KUERZEL_NN`; bloßes Kürzel → LP-Übersichtsknoten
    `BP2016BW_ALLG_LP_KUERZEL`.
    """
    rels: list[dict] = []
    seen: set[str] = set()
    for v in verweise:
        m = _LP_REF_RE.match(str(v))
        if not m:
            continue
        kuerzel = m.group(1).upper()
        target = f"{kuerzel}_{int(m.group(2)):02d}" if m.group(2) else f"{_LP_OVERVIEW_PREFIX}{kuerzel}"
        if target not in seen:
            seen.add(target)
            rels.append({"target_bp_id": target, "type": "references"})
    return rels


def _emit_ik(
    nodes: list[dict], kompetenzen: list[dict], *, parent_bpid: str, leitidee_nr: str,
    von: int, bis: int, niveau: str, crumb: list[str], source_url: str | None,
) -> None:
    """Hängt die inhaltsbezogenen Kompetenzen (`ik_kompetenz`) an eine Leitidee an."""
    for k in kompetenzen:
        n = int(k["nummer"])
        text = _clean_text(k.get("text"))
        kompetenz_nr = f"{leitidee_nr}({n})"            # z. B. "3.1.1.1(1)"
        verweise = [str(v).strip() for v in (k.get("verweise") or []) if str(v).strip()]
        nodes.append(build_node(
            bp_id=f"{parent_bpid}_{n:02d}",
            content_type="ik_kompetenz",
            title=f"{kompetenz_nr} {text}"[:200],
            content=f"({n}) {text}",                     # gehashter String inkl. (n)-Präfix
            parent_bp_id=parent_bpid,
            min_grade=von, max_grade=bis, niveau=niveau,
            relations=_lp_relations(verweise),
            source_url=source_url,
            extra_metadata={
                "standard_nr": n,
                "kompetenz_nr": kompetenz_nr,
                "breadcrumb": crumb,
                "verweise": verweise,
            },
        ))


def build_operator_nodes(operatoren: list[dict], *, base_bp_id: str, source_url: str | None = None) -> list[dict]:
    """Operatoren (Abschnitt 4) → `operator`-Knoten, direkt am Fachplan (wie der HTML-Scraper).

    bp_id `{base}_OP_{nr:02d}`; Titelzelle via `expand_operator_title` in Titel + Synonyme
    (`metadata.aliase`); AFB als Liste; content_hash zusammengesetzt aus title|content|afb|aliase
    (identisch zu `parse_operator_list`). `nr` zählt nur gültige Zeilen (mit Titel + Beschreibung)."""
    nodes: list[dict] = []
    nr = 0
    for op in operatoren:
        title, aliase = expand_operator_title(str(op.get("operator") or ""))
        content = _clean_text(op.get("beschreibung"))
        afb = [str(a).strip() for a in (op.get("afb") or []) if str(a).strip()]
        if not title or not content:
            continue
        nr += 1
        bp_id = f"{base_bp_id}_OP_{nr:02d}"
        nodes.append(build_node(
            bp_id=bp_id,
            content_type="operator",
            title=title,
            content=content,
            parent_bp_id=base_bp_id,
            hash_input=f"{title}|{content}|{','.join(afb)}|{','.join(aliase)}",
            source_url=source_url,
            extra_metadata={"afb": afb, "aliase": aliase, "operator_nr": nr},
        ))
    return nodes


def build_fremdsprache_nodes(
    structure: dict, *, fach_code: str, suffix: str = "", schulart: str = "GYM",
    bp_basis: str = "BP2016BW", source_url: str | None = None,
) -> list[dict]:
    """Baut alle Knoten eines Fremdsprachen-Fachs aus der neutralen Struktur."""
    base = f"{bp_basis}_ALLG_{schulart}_{fach_code}{suffix}"
    fach = structure["fach"]
    fach_titel = str(fach["titel"]).strip()
    nodes: list[dict] = []

    # Fachplan (Wurzel)
    nodes.append(build_node(
        bp_id=base,
        content_type="fachplan",
        title=fach_titel,
        content=(_clean_text(fach.get("leitgedanken")) or fach_titel),
        parent_bp_id=None,
        source_url=source_url,
        extra_metadata={"breadcrumb": [fach_titel]},
    ))

    # Abschnitt 2 — prozessbezogene Kompetenzen
    for g in structure["prozessbezogene_kompetenzbereiche"]:
        g_nr = str(g["nummer"]).strip()                  # "2.1"
        g_bpid = f"{base}_PK_{_last_num(g_nr):02d}"       # ..._PK_01
        g_titel = _clean_text(g["titel"])
        g_title = f"{g_nr} {g_titel}"
        g_crumb = [fach_titel, "Prozessbezogene Kompetenzen", g_title]
        nodes.append(build_node(
            bp_id=g_bpid, content_type="pk_gruppe",
            title=g_title, content=(_clean_text(g.get("beschreibung")) or g_titel),
            parent_bp_id=base, source_url=source_url,
            extra_metadata={"breadcrumb": g_crumb},
        ))
        for k in g["kompetenzen"]:
            n = int(k["nummer"])
            text = _clean_text(k.get("text"))
            kompetenz_nr = f"{g_nr}.{n}"                  # "2.1.1"
            nodes.append(build_node(
                bp_id=f"{g_bpid}_{n:02d}", content_type="pk_kompetenz",
                title=f"{kompetenz_nr} {text}"[:200], content=f"{n}. {text}",
                parent_bp_id=g_bpid, source_url=source_url,
                extra_metadata={"standard_nr": n, "kompetenz_nr": kompetenz_nr, "breadcrumb": g_crumb},
            ))

    # Abschnitt 3 — inhaltsbezogene Kompetenzen je Jahrgangsstufe
    for s in structure["jahrgangsstufen"]:
        von, bis = int(s["klasse_von"]), int(s["klasse_bis"])
        niveau = s.get("niveau") or None                 # None|"basis"|"leistung"
        node_niveau = niveau or "regulär"
        band = _band_segment(von, bis, niveau)
        s_title = f"{str(s['nummer']).strip()} {str(s.get('titel', '')).strip()}".strip()
        s_crumb = [fach_titel, s_title]
        for b in s["kompetenzbereiche"]:
            b_nr = str(b["nummer"]).strip()               # "3.1.1"
            b_bpid = f"{base}_IK_{band}_{_last_num(b_nr):02d}"   # 2-seg Leitidee
            b_titel = _clean_text(b["titel"])
            b_title = f"{b_nr} {b_titel}"
            b_crumb = s_crumb + [b_title]
            nodes.append(build_node(
                bp_id=b_bpid, content_type="leitidee",
                title=b_title, content=(_clean_text(b.get("beschreibung")) or b_titel),
                parent_bp_id=base,                        # 2-seg → Fachplan
                min_grade=von, max_grade=bis, niveau=node_niveau,
                source_url=source_url, extra_metadata={"breadcrumb": b_crumb},
            ))
            teilbereiche = b.get("teilbereiche") or []
            if teilbereiche:
                for t in teilbereiche:
                    t_nr = str(t["nummer"]).strip()       # "3.1.1.1"
                    t_bpid = f"{b_bpid}_{_last_num(t_nr):02d}"   # 3-seg Leitidee
                    t_titel = _clean_text(t["titel"])
                    t_title = f"{t_nr} {t_titel}"
                    t_crumb = b_crumb + [t_title]
                    nodes.append(build_node(
                        bp_id=t_bpid, content_type="leitidee",
                        title=t_title, content=(_clean_text(t.get("beschreibung")) or t_titel),
                        parent_bp_id=b_bpid,              # 3-seg → 2-seg Leitidee
                        min_grade=von, max_grade=bis, niveau=node_niveau,
                        source_url=source_url, extra_metadata={"breadcrumb": t_crumb},
                    ))
                    _emit_ik(nodes, t.get("kompetenzen") or [], parent_bpid=t_bpid,
                             leitidee_nr=t_nr, von=von, bis=bis, niveau=node_niveau,
                             crumb=t_crumb, source_url=source_url)
            else:
                _emit_ik(nodes, b.get("kompetenzen") or [], parent_bpid=b_bpid,
                         leitidee_nr=b_nr, von=von, bis=bis, niveau=node_niveau,
                         crumb=b_crumb, source_url=source_url)

    # Abschnitt 4 — Operatoren (direkt am Fachplan)
    nodes.extend(build_operator_nodes(
        structure.get("operatoren") or [], base_bp_id=base, source_url=source_url,
    ))
    return nodes


def render_fremdsprache_report(structure: dict) -> str:
    """Menschenlesbarer Markdown-Baum zur Review (Vollständigkeit/Nummerierung/Bänder prüfen)."""
    js = structure["jahrgangsstufen"]
    pk = structure["prozessbezogene_kompetenzbereiche"]
    n_pk_g = len(pk)
    n_pk_k = sum(len(g["kompetenzen"]) for g in pk)
    n_leitidee = sum(
        len(s["kompetenzbereiche"])
        + sum(len(b.get("teilbereiche") or []) for b in s["kompetenzbereiche"])
        for s in js
    )
    n_ik = 0
    for s in js:
        for b in s["kompetenzbereiche"]:
            teil = b.get("teilbereiche") or []
            if teil:
                n_ik += sum(len(t.get("kompetenzen") or []) for t in teil)
            else:
                n_ik += len(b.get("kompetenzen") or [])

    operatoren = structure.get("operatoren") or []
    lines = [f"# {structure['fach']['titel']} — Extraktions-Review", ""]
    lines.append(
        f"**{n_pk_g} PK-Bereiche · {n_pk_k} PK-Kompetenzen · {len(js)} Jahrgangsstufen · "
        f"{n_leitidee} Leitideen/Bereiche · {n_ik} IK-Kompetenzen · {len(operatoren)} Operatoren**"
    )
    lines += ["", "## 2. Prozessbezogene Kompetenzen", ""]
    for g in pk:
        lines.append(f"### {g['nummer']} {g['titel']}")
        for k in g["kompetenzen"]:
            lines.append(f"- ({k['nummer']}) {str(k.get('text', '')).strip()}")
        lines.append("")

    lines += ["## 3. Inhaltsbezogene Kompetenzen", ""]
    for s in js:
        niv = f" · Niveau: {s['niveau']}" if s.get("niveau") else ""
        lines.append(f"### {s['nummer']} {s.get('titel', '')} (Klassen {s['klasse_von']}–{s['klasse_bis']}{niv})")
        for b in s["kompetenzbereiche"]:
            lines.append(f"#### {b['nummer']} {b['titel']}")
            teil = b.get("teilbereiche") or []
            if teil:
                for t in teil:
                    lines.append(f"- **{t['nummer']} {t['titel']}**")
                    for k in t.get("kompetenzen") or []:
                        _render_kompetenz(lines, k)
            else:
                for k in b.get("kompetenzen") or []:
                    _render_kompetenz(lines, k)
        lines.append("")

    if operatoren:
        lines += ["## 4. Operatoren", ""]
        for op in operatoren:
            afb = f"  · AFB: {', '.join(str(a) for a in op.get('afb') or [])}" if op.get("afb") else ""
            lines.append(f"- **{str(op.get('operator', '')).strip()}**{afb}")
            lines.append(f"  - {str(op.get('beschreibung', '')).strip()}")
        lines.append("")
    return "\n".join(lines)


def _render_kompetenz(lines: list[str], k: dict) -> None:
    verweise = ", ".join(str(v).strip() for v in (k.get("verweise") or []) if str(v).strip())
    suffix = f"  _[{verweise}]_" if verweise else ""
    lines.append(f"  - ({k['nummer']}) {str(k.get('text', '')).strip()}{suffix}")
