"""CLI für den PDF→JSONL-Import (KS-Plan C3/C4).

Modi:
  Text-Dump (Standard, zum Inspizieren der Quellseiten):
      python -m scripts.pdf_import --source <url|pfad> [--pages "24-33"] [--output text.txt]

  LFDB-Pipeline (PDF → LLM → 3-Ebenen-JSONL + Review-Report):
      python -m scripts.pdf_import --lfdb --source <url> --pages "24-33"
      # Re-Run ohne LLM (aus gespeicherter Struktur):
      python -m scripts.pdf_import --lfdb --structure-json output/lfdb_struktur.json --source <url>

Ausgabe standardmäßig nach scripts/pdf_import/output/ (gitignored, E1).
"""
import argparse
import json
import sys
from pathlib import Path

from scripts.pdf_import.extract import DEFAULT_MODEL, extract_lfdb_structure
from scripts.pdf_import.lfdb import build_lfdb_nodes, render_lfdb_report
from scripts.pdf_import.nodes import write_jsonl
from scripts.pdf_import.pdf_text import extract_text, load_pdf_bytes, parse_page_spec


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


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF→JSONL-Import (Bildungsplan-PDFs)")
    parser.add_argument("--source", default=None, help="PDF-URL oder lokaler Pfad")
    parser.add_argument("--pages", default=None, help="Seiten (1-indexiert), z. B. '24-33'")
    parser.add_argument("--output", default=None, help="Text-Dump-Datei; ohne → stdout")
    parser.add_argument("--lfdb", action="store_true", help="LFDB-Pipeline statt Text-Dump")
    parser.add_argument("--structure-json", default=None,
                        help="Vor-extrahierte Struktur (überspringt den LLM-Aufruf)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM-Modell für die Extraktion")
    parser.add_argument("--output-dir", default="scripts/pdf_import/output",
                        help="Ausgabeverzeichnis (JSONL/Report/Struktur)")
    args = parser.parse_args()

    try:
        if args.lfdb:
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
