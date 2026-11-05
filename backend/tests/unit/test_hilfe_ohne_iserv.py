"""Die Hilfe nennt kein Produkt des Schulkontos (0.34).

Die Plattform soll auch an Schulen laufen, die ihr Schulkonto nicht über IServ führen
(`AuthAdapter`, docs/dev/neuer-auth-adapter.md). In der Hilfe für Schüler:innen und Lehrkräfte
heißt es deshalb „Schulkonto“ bzw. „SSO“, nicht „IServ“ — auch in den Neuigkeiten.

Nicht geprüft: `docs/admin` und `docs/dev`. Dort ist der Name fachlich nötig
(Konfigurationsvariablen wie `AUTH_ISERV_CLIENT_SECRET`, Eigenheiten dieses Providers).
"""
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[3]
ORTE = [WURZEL / "docs" / "user", WURZEL / "backend" / "app" / "neuigkeiten"]


def test_hilfe_und_neuigkeiten_ohne_iserv():
    treffer = []
    for ort in ORTE:
        for datei in sorted(ort.rglob("*")):
            if datei.suffix not in {".md", ".yaml"}:
                continue
            for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
                if "iserv" in zeile.lower():
                    treffer.append(f"{datei.relative_to(WURZEL)}:{nr}: {zeile.strip()[:80]}")
    assert not treffer, "„IServ“ in der Hilfe — „Schulkonto“ schreiben:\n" + "\n".join(treffer)
