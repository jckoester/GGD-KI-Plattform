"""Bildungsplan-Editionen — Fahrplan-Loader und Editions-Modell.

Liest den Editions-Fahrplan aus ``subjects.yaml`` (``bildungsplan_default.editionen``)
und stellt ihn als geordnete Liste von :class:`Edition` bereit.

Kernidee der Versionierung: Welche Edition für eine Stufe gilt, wird aus diesem
Fahrplan **plus dem aktuellen Schuljahr berechnet** — keine jährliche Pflege der
``subjects.yaml``. Dieser Loader liefert nur die Stammdaten; die schuljahres-
abhängige Auswahl (``aktive_edition``) baut darauf auf (Folgeschritt).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Edition:
    """Eine Bildungsplan-Edition aus dem Fahrplan.

    - ``suffix``       : "" (Basis/V1) | ".V2" | ".V3" …
    - ``bp_version``   : Wert in ``context_nodes.bp_version`` (= Basisjahr + suffix,
      z. B. "2016" oder "2016.V2").
    - ``ab_jahr``      : Startjahr des ``ab_schuljahr`` (``None`` = Basis, immer gültig).
    - ``einstieg_min`` / ``einstieg_max`` : Stufenspanne der ersten Geltung
      (``None`` = unbeschränkt / Basis-Fallback).
    - ``wachstum``     : "nach_oben" (Obergrenze +1 Stufe je Schuljahr) | "keine".
    """

    suffix: str
    bp_version: str
    ab_jahr: int | None
    einstieg_min: int | None
    einstieg_max: int | None
    wachstum: str


_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]+")
_YEAR_RE = re.compile(r"(\d{4})")


def parse_schuljahr_start(schuljahr: str) -> int:
    """'2026/27' → 2026 (das Startjahr des Schuljahres)."""
    m = _YEAR_RE.match((schuljahr or "").strip())
    if not m:
        raise ValueError(f"Ungültiges Schuljahr: {schuljahr!r}")
    return int(m.group(1))


def _basis_jahr(bp_basis: str) -> str:
    """'BP2016BW' → '2016'."""
    m = _YEAR_RE.search(bp_basis or "")
    return m.group(1) if m else ""


def load_edition_schedule(cfg: dict) -> list[Edition]:
    """Parst ``bildungsplan_default.editionen`` aus der subjects.yaml-Config.

    Rückgabe: Editionen sortiert von alt → neu (Basis/``ab_jahr=None`` zuerst,
    danach aufsteigend nach ``ab_jahr``). Validiert Suffix-Form und Stufenangaben.
    Fehlt der Fahrplan, wird rückwärtskompatibel nur die globale ``suffix``-Basis
    zurückgegeben.
    """
    default = (cfg or {}).get("bildungsplan_default", {}) or {}
    basis_jahr = _basis_jahr(default.get("bp_basis", "BP2016BW"))

    raw = default.get("editionen")
    if not raw:
        raw = [{"suffix": default.get("suffix", "")}]

    seen_suffixes: set[str] = set()
    editions: list[Edition] = []
    for entry in raw:
        suffix = entry.get("suffix", "")
        if suffix and not _SUFFIX_RE.fullmatch(suffix):
            raise ValueError(f"Ungültiger Editions-Suffix: {suffix!r}")
        if suffix in seen_suffixes:
            raise ValueError(f"Doppelter Editions-Suffix im Fahrplan: {suffix!r}")
        seen_suffixes.add(suffix)

        ab = entry.get("ab_schuljahr")
        ab_jahr = parse_schuljahr_start(ab) if ab else None

        stufen = entry.get("einstieg_stufen")
        emin = emax = None
        if stufen is not None:
            if len(stufen) != 2 or int(stufen[0]) > int(stufen[1]):
                raise ValueError(
                    f"einstieg_stufen muss [min, max] mit min<=max sein: {stufen!r}"
                )
            emin, emax = int(stufen[0]), int(stufen[1])

        wachstum = entry.get("wachstum", "keine")
        if wachstum not in ("keine", "nach_oben"):
            raise ValueError(f"Unbekanntes wachstum: {wachstum!r}")

        editions.append(
            Edition(
                suffix=suffix,
                bp_version=basis_jahr + suffix,
                ab_jahr=ab_jahr,
                einstieg_min=emin,
                einstieg_max=emax,
                wachstum=wachstum,
            )
        )

    editions.sort(key=lambda e: (e.ab_jahr is not None, e.ab_jahr or 0))
    return editions


def obergrenze(edition: Edition, schuljahr_start: int) -> int | None:
    """Höchste Stufe, die ``edition`` im gegebenen Schuljahr abdeckt.

    ``None`` = unbeschränkt (Basis/keine Stufengrenze). Bei ``wachstum=nach_oben``
    wandert die Obergrenze ab dem Einführungsjahr jahrgangsweise nach oben.
    """
    if edition.einstieg_max is None:
        return None
    if edition.wachstum == "nach_oben" and edition.ab_jahr is not None:
        return edition.einstieg_max + max(0, schuljahr_start - edition.ab_jahr)
    return edition.einstieg_max


def _deckt_ab(edition: Edition, stufe: int, schuljahr_start: int) -> bool:
    """Gilt ``edition`` im Schuljahr für diese Stufe (in Kraft + Stufenabdeckung)?"""
    if edition.ab_jahr is not None and schuljahr_start < edition.ab_jahr:
        return False
    if edition.einstieg_min is not None and stufe < edition.einstieg_min:
        return False
    og = obergrenze(edition, schuljahr_start)
    if og is not None and stufe > og:
        return False
    return True


def aktive_edition(
    editions: list[Edition],
    stufe: int,
    schuljahr_start: int,
    verfuegbare_bp_versions: set[str] | None = None,
) -> Edition | None:
    """Die für (Stufe, Schuljahr) geltende Edition.

    Auswahl: die **neueste** Edition, die (a) im Schuljahr in Kraft ist, (b) die
    Stufe abdeckt und (c) — falls ``verfuegbare_bp_versions`` gesetzt — tatsächlich
    importiert ist; sonst die nächstältere; sonst ``None``.

    ``verfuegbare_bp_versions`` realisiert den **Inhalts-Fallback**: Ist eine
    Edition laut Fahrplan zwar in Kraft, aber für dieses Fach noch nicht importiert
    (z. B. V3-BP noch nicht veröffentlicht), fällt die Auswahl automatisch auf die
    vorige Edition zurück und schaltet selbsttätig um, sobald die Knoten da sind.
    ``None`` = Verfügbarkeit nicht prüfen (rein fahrplanbasiert).
    """
    kandidaten = [
        e
        for e in editions
        if _deckt_ab(e, stufe, schuljahr_start)
        and (verfuegbare_bp_versions is None or e.bp_version in verfuegbare_bp_versions)
    ]
    if not kandidaten:
        return None
    # neueste gewinnt: höchstes ab_jahr; Basis (ab_jahr None) ist die älteste.
    return max(kandidaten, key=lambda e: (e.ab_jahr is not None, e.ab_jahr or 0))
