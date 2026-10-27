#!/usr/bin/env python3
"""Messung „Assistent für stöchiometrische Berechnungen" (Plan `Plaene/Stoechiometrie-Assistent-Plan.md`).

    python scripts/stoechiometrie_messung.py --selbsttest
    python scripts/stoechiometrie_messung.py --lauf 1 --ziel "<Vault>/Plaene/Messungen-Stoechiometrie"

Seit 26.10.2026 eine Hülle um `assistent_messung.py` mit `scripts/szenarien/stoechiometrie.yaml`
als Vorgabe; Einrichtung (Prompt, Stufen, Modell, Augmentierungen) steht im Kopf der Szenariodatei.
Alle Optionen wie dort.

Dazu, nach dem Lauf: `stoechiometrie_zusatz.py <verlauf.json> <verlauf.md> [Kopfzeile …]` hängt
Frageform, fremde Zahlen (D1/D4/D5) und den E1-Verlauf an das Protokoll an.
"""
import importlib.util
from pathlib import Path

HIER = Path(__file__).resolve().parent

# `scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt“) — über den Pfad laden.
_spec = importlib.util.spec_from_file_location("assistent_messung", HIER / "assistent_messung.py")
assistent_messung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(assistent_messung)

if __name__ == "__main__":
    assistent_messung.hauptprogramm(HIER / "szenarien/stoechiometrie.yaml")
