"""Bänder des Bildungsplans und die Zuordnung eines Curriculums (0.46, Päckchen AP Teil B, Schritt 8).

**Woher die Bänder kommen.** Aus dem Plan selbst: Jede inhaltsbezogene Kompetenz (IK) trägt im
`breadcrumb` die Überschrift ihres Bands — „3.1 Klassen 5/6“, „3.3 Klasse 10“, „3.4 Klassen 12/13
(Leistungsfach)“ (geprüft 17.11.2026: alle 10 098 geltenden und kommenden IK). Der Schlüssel eines
Bands ist diese Überschrift ohne Nummer; die Nummer wechselt zwischen den Fassungen (3.4 → 3.5).

**Stufen eines Bands.** Aus `min_grade`/`max_grade` der IK, sonst aus der Überschrift — Physik V2
führt die Basisfach-Bänder 11/12 ohne Stufen.

**Parallele Bänder.** In der Oberstufe gibt es zu denselben Stufen zwei oder drei Bänder
(Basis- und Leistungsfach, Physik zwei Basisfach-Schwerpunkte). Über die Stufen allein lässt sich
ein Curriculum dort nicht zuordnen; es trägt dann das Feld `band` (Metadaten, Schlüssel). Fehlt
es, ist das Curriculum „nicht zugeordnet“, und seine Abdeckung misst wie bis 0.45 gegen alle
Bänder seiner Stufen (mit Hinweis).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Bandüberschrift im `breadcrumb`: „3.1 Klassen 5/6“, „3.3 Klasse 10“.
_UEBERSCHRIFT = re.compile(r"^\s*\d+\.\d+\s+Klassen?\s+\d")
_NUMMER = re.compile(r"^\s*\d+(?:\.\d+)*\s+")


@dataclass(frozen=True)
class Band:
    schluessel: str        # Überschrift ohne Nummer, z. B. „Klassen 12/13 (Leistungsfach)“
    min_grade: int | None
    max_grade: int | None
    reihenfolge: str       # Nummer der Überschrift („3.4“) — nur zum Sortieren

    def als_dict(self) -> dict:
        return {"schluessel": self.schluessel, "min_grade": self.min_grade, "max_grade": self.max_grade}


def band_ueberschrift(meta: dict | None) -> str | None:
    """Die Bandüberschrift einer IK, wie sie im Pfad steht (mit Nummer)."""
    for teil in (meta or {}).get("breadcrumb") or []:
        if _UEBERSCHRIFT.match(str(teil)):
            return str(teil).strip()
    return None


def band_schluessel(meta: dict | None) -> str | None:
    """Der Schlüssel des Bands einer IK: die Überschrift ohne Nummer."""
    u = band_ueberschrift(meta)
    return _NUMMER.sub("", u, count=1) if u else None


def _stufen_aus_ueberschrift(schluessel: str) -> tuple[int | None, int | None]:
    zahlen = [int(z) for z in re.findall(r"\d+", schluessel.split("(")[0])]
    return (min(zahlen), max(zahlen)) if zahlen else (None, None)


def _sortschluessel(nr: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", nr)]


def baender_aus(iks) -> list[Band]:
    """Die Bänder einer Fassung aus ihren IK (ContextNodes), sortiert wie im Plan."""
    gesammelt: dict[str, dict] = {}
    for k in iks:
        u = band_ueberschrift(k.metadata_)
        if not u:
            continue
        s = _NUMMER.sub("", u, count=1)
        b = gesammelt.setdefault(s, {"nr": u[: len(u) - len(s)].strip(), "min": None, "max": None})
        if k.min_grade is not None:
            b["min"] = k.min_grade if b["min"] is None else min(b["min"], k.min_grade)
        if k.max_grade is not None:
            b["max"] = k.max_grade if b["max"] is None else max(b["max"], k.max_grade)
    baender = []
    for s, b in gesammelt.items():
        lo, hi = (b["min"], b["max"]) if b["min"] is not None else _stufen_aus_ueberschrift(s)
        baender.append(Band(s, lo, hi, b["nr"]))
    return sorted(baender, key=lambda b: (b.min_grade or 0, _sortschluessel(b.reihenfolge)))


def _beruehrt(b: Band, lo: int | None, hi: int | None) -> bool:
    if lo is None or hi is None or b.min_grade is None or b.max_grade is None:
        return True
    return b.min_grade <= hi and b.max_grade >= lo


def band_zuordnen(baender: list[Band], min_grade: int | None, max_grade: int | None,
                  gewaehlt: str | None) -> tuple[Band | None, list[Band]]:
    """Das Band eines Curriculums und die Bänder, die nach seinen Stufen in Frage kommen.

    Gewählt (`metadata.band`) und unter den Kandidaten → dieses. Sonst genau ein Kandidat → der.
    Sonst keins: parallele Bänder ohne Wahl, oder Stufen über mehrere Bänder.
    """
    kandidaten = [b for b in baender if _beruehrt(b, min_grade, max_grade)]
    if gewaehlt:
        for b in kandidaten:
            if b.schluessel == gewaehlt:
                return b, kandidaten
    return (kandidaten[0] if len(kandidaten) == 1 else None), kandidaten
