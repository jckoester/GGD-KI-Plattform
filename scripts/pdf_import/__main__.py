"""CLI für den PDF→JSONL-Import (KS-Plan C3/C4).

Modi:
  Text-Dump (Standard, zum Inspizieren der Quellseiten):
      python -m scripts.pdf_import --source <url|pfad> [--pages "24-33"] [--output text.txt]

  LFDB-Pipeline (PDF → LLM → 3-Ebenen-JSONL + Review-Report):
      python -m scripts.pdf_import --lfdb --source <url> --pages "24-33"
      # Re-Run ohne LLM (aus gespeicherter Struktur):
      python -m scripts.pdf_import --lfdb --structure-json output/lfdb_struktur.json --source <url>

  Fremdsprachen-Pipeline (PDF → LLM → Fachplan/Leitidee/IK/PK-JSONL + Report):
      python -m scripts.pdf_import --fremdsprache --fach E1
      # PDF-URL/Suffix kommen aus config/subjects.yaml (Feld bildungsplan_pdf_url);
      # --source überschreibt die Quelle, --structure-json überspringt den LLM-Aufruf.

Ausgabe standardmäßig nach scripts/pdf_import/output/ (gitignored, E1).
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

from scripts.pdf_import.extract import (
    DEFAULT_MODEL,
    extract_fremdsprache_chunked,
    extract_lfdb_structure,
)
from scripts.pdf_import.fremdsprache import build_fremdsprache_nodes, render_fremdsprache_report
from scripts.pdf_import.lfdb import build_lfdb_nodes, render_lfdb_report
from scripts.pdf_import.nodes import write_jsonl
from scripts.pdf_import.pdf_text import extract_text, load_pdf_bytes, parse_page_spec, split_pages


def _run_dump(args) -> None:
    data = load_pdf_bytes(args.source)
    text = extract_text(data, parse_page_spec(args.pages))
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"{len(text)} Zeichen → {args.output}", file=sys.stderr)
    else:
        print(text)


def _run_lfdb(args) -> None:
    if args.structure_json:
        structure = json.loads(Path(args.structure_json).read_text(encoding="utf-8"))
    else:
        data = load_pdf_bytes(args.source)
        text = extract_text(data, parse_page_spec(args.pages))
        structure = extract_lfdb_structure(text, model=args.model)

    nodes = build_lfdb_nodes(structure, source_url=args.source)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(nodes, out / "lfdb.jsonl")
    (out / "lfdb_report.md").write_text(render_lfdb_report(structure), encoding="utf-8")
    (out / "lfdb_struktur.json").write_text(
        json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{len(nodes)} Knoten → {out / 'lfdb.jsonl'}\n"
        f"Review-Report → {out / 'lfdb_report.md'}\n"
        f"Struktur (für Re-Runs) → {out / 'lfdb_struktur.json'}",
        file=sys.stderr,
    )


def _load_subject(subjects_path: str, fach_code: str) -> tuple[dict, str, str, str]:
    """Sucht ein Fach per fach_code in subjects.yaml; liefert (fach, schulart, bp_basis, default_suffix)."""
    cfg = yaml.safe_load(Path(subjects_path).read_text(encoding="utf-8"))
    schulart = cfg.get("schulart", "GYM")
    default = cfg.get("bildungsplan_default", {}) or {}
    bp_basis = default.get("bp_basis", "BP2016BW")
    default_suffix = default.get("suffix", "")
    for fach in cfg.get("subjects", []):
        fc = fach.get("fach_code")
        if fc and str(fc).strip().upper() == fach_code.upper():
            return fach, schulart, bp_basis, default_suffix
    raise ValueError(f"Kein Fach mit fach_code={fach_code!r} in {subjects_path}")


def _run_fremdsprache(args) -> None:
    fach_cfg, schulart, bp_basis, default_suffix = _load_subject(args.subjects, args.fach)
    fach_code = str(fach_cfg["fach_code"]).strip()
    suffix = args.suffix if args.suffix is not None else fach_cfg.get("bildungsplan_suffix", default_suffix)
    source = args.source or fach_cfg.get("bildungsplan_pdf_url")

    if args.structure_json:
        structure = json.loads(Path(args.structure_json).read_text(encoding="utf-8"))
    else:
        if not source:
            raise ValueError(
                f"Keine PDF-Quelle für {fach_code}: weder --source noch bildungsplan_pdf_url in subjects.yaml"
            )
        fach_titel = str(fach_cfg.get("name") or fach_code)
        data = load_pdf_bytes(source)
        pages = split_pages(data)                       # band-weise Erkennung braucht Seitengrenzen
        structure = extract_fremdsprache_chunked(
            pages, fach_titel=fach_titel, model=args.model,
            log=lambda msg: print(msg, file=sys.stderr),
        )

    nodes = build_fremdsprache_nodes(
        structure, fach_code=fach_code, suffix=suffix or "",
        schulart=schulart, bp_basis=bp_basis, source_url=source,
    )
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    label = f"{fach_code}{suffix or ''}".replace(".", "_")   # z. B. E1_V2
    write_jsonl(nodes, out / f"{label}.jsonl")
    (out / f"{label}_report.md").write_text(render_fremdsprache_report(structure), encoding="utf-8")
    (out / f"{label}_struktur.json").write_text(
        json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{len(nodes)} Knoten → {out / f'{label}.jsonl'}\n"
        f"Review-Report → {out / f'{label}_report.md'}\n"
        f"Struktur (für Re-Runs) → {out / f'{label}_struktur.json'}",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF→JSONL-Import (Bildungsplan-PDFs)")
    parser.add_argument("--source", default=None, help="PDF-URL oder lokaler Pfad")
    parser.add_argument("--pages", default=None, help="Seiten (1-indexiert), z. B. '24-33'")
    parser.add_argument("--output", default=None, help="Text-Dump-Datei; ohne → stdout")
    parser.add_argument("--lfdb", action="store_true", help="LFDB-Pipeline statt Text-Dump")
    parser.add_argument("--fremdsprache", action="store_true",
                        help="Fremdsprachen-Pipeline (braucht --fach)")
    parser.add_argument("--fach", default=None, help="Fach-Code für --fremdsprache (z. B. E1, F2)")
    parser.add_argument("--suffix", default=None,
                        help="Editions-Suffix überschreiben (Default: subjects.yaml/bildungsplan_default)")
    parser.add_argument("--subjects", default="config/subjects.yaml",
                        help="Pfad zu subjects.yaml (Fach-Codes/PDF-URLs)")
    parser.add_argument("--structure-json", default=None,
                        help="Vor-extrahierte Struktur (überspringt den LLM-Aufruf)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM-Modell für die Extraktion")
    parser.add_argument("--output-dir", default="scripts/pdf_import/output",
                        help="Ausgabeverzeichnis (JSONL/Report/Struktur)")
    args = parser.parse_args()

    try:
        if args.fremdsprache:
            if not args.fach:
                parser.error("--fremdsprache braucht --fach (z. B. E1)")
            _run_fremdsprache(args)
        elif args.lfdb:
            if not args.source and not args.structure_json:
                parser.error("--lfdb braucht --source oder --structure-json")
            _run_lfdb(args)
        else:
            if not args.source:
                parser.error("--source ist erforderlich")
            _run_dump(args)
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
