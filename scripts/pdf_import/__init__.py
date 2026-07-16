"""PDF→JSONL-Import für nur als PDF veröffentlichte Bildungspläne (KS-Plan C3/C4).

Erzeugt dasselbe JSONL-Format wie der HTML-Scraper (`scripts/scraper/`), damit der
bestehende Import (`scripts/import_bildungsplan.py`) es unverändert frisst. Ablauf:
PDF laden → Text (seiten-bewusst) → LLM-Struktur-Extraktion → deterministische
Node-Assemblierung → JSONL + Review-Report.
"""
