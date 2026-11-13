"""Titelvorschlag beim Speichern in der Werkstatt (0.41, Päckchen AN, Schritt 2).

Bis 0.40 hieß jedes gespeicherte Bild „Bild“ und jedes Diagramm nach seiner Art — in einer vollen
Werkstatt ist so nichts wiederzufinden. Der Titel wird **still gesetzt** und ist danach änderbar
(Plan F6); ein Dialog bei jedem Speichern bremste den Chat. Der Bestand wird nicht umbenannt.

Reihenfolge je Art:

- **Bild:** der Bild-Prompt.
- **Diagramm:** ein Titel aus dem Quelltext, wo die Art einen kennt (Mermaid `title`; beim
  Funktionsgraphen die erste Funktion); sonst die Frage, die das Diagramm ausgelöst hat.
- **Zuletzt:** Art und Datum („Schaltplan vom 13.11.2026“).

Reine Funktionen — die Datenbank fragt `promote.py`.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

#: Länge eines Titels in der Werkstatt-Karte; länger wird an einer Wortgrenze gekürzt.
LAENGE = 60

ART = {
    "image": "Bild",
    "circuit": "Schaltplan",
    "plot": "Funktionsgraph",
    "smiles": "Strukturformel",
    "mermaid": "Diagramm",
}


def kuerzen(text: Optional[str], laenge: int = LAENGE) -> str:
    """Erste Zeile, Leerraum zusammengezogen, an einer Wortgrenze auf ``laenge`` gekürzt („…“).

    Ein einzelnes überlanges Wort wird hart geschnitten — sonst bliebe nichts übrig.
    """
    zeile = next((z for z in (text or "").splitlines() if z.strip()), "")
    zeile = re.sub(r"\s+", " ", zeile).strip().strip("\"'„“”")
    if len(zeile) <= laenge:
        return zeile
    schnitt = zeile[: laenge - 1]
    if " " in schnitt:
        schnitt = schnitt[: schnitt.rfind(" ")]
    return schnitt.rstrip(" ,;:.-–") + "…"


def mit_datum(kind: str, heute: date) -> str:
    return f"{ART.get(kind, 'Produkt')} vom {heute:%d.%m.%Y}"


# `title: …` im Front-Matter (alle Diagrammarten) und `title …` als Anweisung
# (pie, gantt, journey, timeline, xychart, quadrantChart) — auch `pie title …` in einer Zeile.
_MERMAID_FRONTMATTER = re.compile(r"\A\s*---\s*\n(.*?)\n\s*---", re.S)
_MERMAID_YAML_TITEL = re.compile(r"^\s*title\s*:\s*(.+?)\s*$", re.M)
# Nur `title` am Zeilenanfang (oder nach `pie`/`xychart`) — `classDef title …` ist kein Titel.
_MERMAID_ANWEISUNG = re.compile(r"^\s*(?:(?:pie|xychart-beta|xychart)\s+)?title\s+(.+?)\s*$", re.M | re.I)


def titel_aus_mermaid(source: str) -> Optional[str]:
    kopf = _MERMAID_FRONTMATTER.match(source or "")
    if kopf:
        treffer = _MERMAID_YAML_TITEL.search(kopf.group(1))
        if treffer:
            return treffer.group(1).strip("\"'")
    treffer = _MERMAID_ANWEISUNG.search(source or "")
    return treffer.group(1).strip("\"'") if treffer else None


def titel_aus_plot(source: str) -> Optional[str]:
    """Die erste Funktion, ab zwei Funktionen mit „u. a.“ — eine Spec kennt keinen Titel."""
    from app.render.plot import parse_plot_spec   # lokal: numpy/matplotlib nur bei Bedarf

    try:
        funktionen = parse_plot_spec(source).functions
    except Exception:   # noqa: BLE001 — ein unlesbarer Quelltext heißt nur: kein Titel daraus
        return None
    if not funktionen:
        return None
    erste = funktionen[0].strip()
    return f"Graph von {erste}" + (" u. a." if len(funktionen) > 1 else "")


def bild(prompt: Optional[str], heute: date) -> str:
    return kuerzen(prompt) or mit_datum("image", heute)


def diagramm(kind: str, source: str, frage: Optional[str], heute: date) -> str:
    aus_quelle = {"mermaid": titel_aus_mermaid, "plot": titel_aus_plot}.get(kind)
    for kandidat in (aus_quelle(source) if aus_quelle else None, frage):
        titel = kuerzen(kandidat)
        if titel:
            return titel
    return mit_datum(kind, heute)
