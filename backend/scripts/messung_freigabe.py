#!/usr/bin/env python3
"""Modelle für eine Messung vorübergehend freischalten — und den alten Stand zurückschreiben.

    python scripts/messung_freigabe.py setzen mistral-large mistral-small ionos-qwen3.8-27b
    python scripts/messung_freigabe.py zuruecknehmen

Für die Teams der Messkonten: Lehrkräfte und die Schüler-Teams der Stufen 5–12 (die Szenarien
nutzen Stufen 5–12; das Team leitet `get_target_team_id` aus Rolle und Stufe ab). `setzen` sichert
die bisherigen Listen in ``--sicherung`` und weigert sich, eine vorhandene Sicherung zu
überschreiben — sonst ginge beim zweiten Aufruf der echte Ausgangsstand verloren.
`zuruecknehmen` schreibt sie zurück und löscht die Sicherung.

⚠️ Das Backend hält die Freigaben bis zu 5 Minuten im Speicher (`app/litellm/team_models.py`,
`TTL_SEKUNDEN`). Nach `setzen` also 5 Minuten warten oder das Backend neu starten, bevor die Messung
beginnt. Nur auf Dev (Mistral-Messung, 17.11.2026).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.litellm.client import LiteLLMClient  # noqa: E402
from app.litellm.teams import get_target_team_id  # noqa: E402

STUFEN = range(5, 13)


def teams() -> list[str]:
    ids = [get_target_team_id(["teacher"], None)]
    for stufe in STUFEN:
        t = get_target_team_id(["student"], stufe)
        if t not in ids:
            ids.append(t)
    return ids


async def setzen(modelle: list[str], sicherung: Path) -> None:
    if sicherung.exists():
        raise SystemExit(f"Sicherung {sicherung} gibt es schon — erst zurücknehmen.")
    client = LiteLLMClient()
    vorher: dict[str, list[str]] = {}
    for t in teams():
        info = await client.get_team_info(t)
        if info is None:
            print(f"  {t}: Team fehlt im Proxy — übersprungen")
            continue
        vorher[t] = list(info.get("models") or [])
    sicherung.write_text(json.dumps(vorher, indent=2), encoding="utf-8")
    for t, alt in vorher.items():
        neu = sorted(set(alt) | set(modelle))
        await client.update_team_models(t, neu)
        print(f"  {t}: + {', '.join(sorted(set(modelle) - set(alt))) or '—'}")
    print(f"Gesichert in {sicherung}. Backend-Cache: 5 Minuten warten oder Backend neu starten.")


async def zuruecknehmen(sicherung: Path) -> None:
    if not sicherung.exists():
        raise SystemExit(f"Keine Sicherung {sicherung} — nichts zurückzunehmen.")
    client = LiteLLMClient()
    vorher = json.loads(sicherung.read_text(encoding="utf-8"))
    for t, alt in vorher.items():
        await client.update_team_models(t, alt)
        print(f"  {t}: zurück auf {len(alt)} Modelle")
    sicherung.unlink()
    print("Zurückgenommen.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("aktion", choices=["setzen", "zuruecknehmen", "zeigen"])
    p.add_argument("modelle", nargs="*")
    p.add_argument("--sicherung", type=Path, default=Path("/tmp/messung_freigabe.json"))
    args = p.parse_args()
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz.")
    if args.aktion == "zeigen":
        print("Teams:", ", ".join(teams()))
        return
    if args.aktion == "setzen":
        if not args.modelle:
            p.error("setzen braucht mindestens ein Modell.")
        asyncio.run(setzen(args.modelle, args.sicherung))
    else:
        asyncio.run(zuruecknehmen(args.sicherung))


if __name__ == "__main__":
    main()
