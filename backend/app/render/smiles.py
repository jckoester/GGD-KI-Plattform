"""Strukturformeln (0.30, Päckchen AH, ```smiles).

SMILES → SVG mit RDKit, **in-process** wie die Funktionsgraphen. Ein Block hat eine Zeile je
Reihe; Moleküle stehen zwischen Operatoren, die von Leerzeichen umgeben sind::

    darstellung: skelett                      (optional, erste Zeile; Vorgabe: valenzstrich)
    [O-]c1ccccc1 <-> O=C1C=CC=C[CH-]1
    Essigsäure: CC(=O)O + Ethanol: OCC <=> CC(=O)OCC + O

Operatoren: ``+``, ``->``, ``<=>`` (Gleichgewicht), ``<->`` (Mesomerie); die Unicode-Pfeile
→ ⇌ ↔ gelten auch. ``Name: SMILES`` beschriftet ein Molekül. In SMILES selbst kommt kein
Leerzeichen vor — deshalb trennen Leerzeichen eindeutig, auch bei ``[NH3+]``.

**Freie Elektronenpaare** zeichnet RDKit nicht. Sie werden hier **berechnet** — Außenelektronen
minus Ladung minus Bindungen (Wasserstoff eingeschlossen) minus Radikalelektronen, halbiert —
und als Striche in die größten freien Winkel um das Atom gesetzt (Entscheidung Jan, 03.11.2026:
Striche, wie in der Valenzstrichformel der Schule). Das Modell schreibt nur das SMILES mit
Ladungen; wo und wie viele Paare stehen, folgt aus der Chemie und ist damit immer vollständig.
In der Valenzstrichformel (Vorgabe) stehen sie an allen Atomen, in der Skelettformel an
Heteroatomen und geladenen Atomen.

Gebogene Elektronenpfeile (Mechanismen) gibt es nicht — Todo „Mechanismuspfeile“.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from html import escape

from app.config import settings
from app.render.errors import RenderError

logger = logging.getLogger(__name__)

# ── Grenzen (begrenzen Arbeit und Bildgröße) ────────────────────────────────────
MAX_QUELLE = 2000
MAX_REIHEN = 4
MAX_MOLEKUELE_JE_REIHE = 6
MAX_SMILES = 300
MAX_ATOME = 120          # schwere Atome je Molekül
MAX_BESCHRIFTUNG = 40

BINDUNGSLAENGE = 48      # Bildpunkte — gleicher Maßstab für alle Moleküle einer Reihe
RAND = 16                # um jedes Molekül, Platz für Elektronenpaare
OPERATOR_BREITE = 44
ZEILEN_ABSTAND = 18
BESCHRIFTUNG_HOEHE = 16
FARBE = "#000000"

_OPERATOREN = {
    "+": "plus", "->": "pfeil", "→": "pfeil",
    "<=>": "gleichgewicht", "⇌": "gleichgewicht",
    "<->": "mesomerie", "↔": "mesomerie",
}
_DARSTELLUNG = re.compile(r"^darstellung\s*:\s*(\S+)\s*$", re.IGNORECASE)
_DARSTELLUNGEN = {"skelett": "skelett", "skelettformel": "skelett",
                  "valenzstrich": "valenzstrich", "valenzstrichformel": "valenzstrich"}


class SmilesError(RenderError):
    """Ungültige Eingabe im ```smiles-Block."""


@dataclass
class Molekuel:
    smiles: str
    name: str | None = None


@dataclass
class Reihe:
    teile: list = field(default_factory=list)   # Molekuel | str (Operator)


@dataclass
class Block:
    darstellung: str
    reihen: list[Reihe]


# ── Lesen ────────────────────────────────────────────────────────────────────

def lies(quelle: str) -> Block:
    """Die Schreibweise in Reihen aus Molekülen und Operatoren zerlegen. Wirft SmilesError."""
    if len(quelle) > MAX_QUELLE:
        raise SmilesError(f"Der Block ist zu lang (höchstens {MAX_QUELLE} Zeichen).")
    zeilen = [z.strip() for z in quelle.splitlines() if z.strip()]
    # Vorgabe Valenzstrichformel (Jan, 03.11.2026): so lernen es Schüler:innen, und so
    # erwartet man es meist auch als Lehrkraft; die Skelettformel nur auf ausdrücklichen
    # Wunsch. Die erste Fassung hatte es umgekehrt (Plan F2).
    darstellung = "valenzstrich"
    if zeilen and (m := _DARSTELLUNG.match(zeilen[0])):
        wert = m.group(1).lower()
        if wert not in _DARSTELLUNGEN:
            raise SmilesError(f"Unbekannte Darstellung „{m.group(1)}“ (skelett oder valenzstrich).")
        darstellung = _DARSTELLUNGEN[wert]
        zeilen = zeilen[1:]
    if not zeilen:
        raise SmilesError("Der Block enthält keine Formel.")
    if len(zeilen) > MAX_REIHEN:
        raise SmilesError(f"Zu viele Zeilen (höchstens {MAX_REIHEN}).")
    return Block(darstellung, [_lies_zeile(z, nr) for nr, z in enumerate(zeilen, 1)])


def _lies_zeile(zeile: str, nr: int) -> Reihe:
    """Erst an den Operatoren trennen, dann je Stück: ``Name: SMILES`` oder ``SMILES``.

    Der Name darf Leerzeichen enthalten („Essigsäure Ethylester: …“); getrennt wird am
    letzten „: “. SMILES selbst enthält kein Leerzeichen — ein Stück mit mehreren Wörtern
    ohne Namen sind zwei Formeln ohne Zeichen dazwischen.
    """
    reihe = Reihe()
    stueck: list[str] = []

    def abschliessen():
        text = " ".join(stueck)
        if not text:
            raise SmilesError(f"Zeile {nr}: Vor oder nach einem Zeichen (+, ->, <=>, <->) fehlt die Formel.")
        name = None
        if ": " in text or text.endswith(":"):
            name, _, text = text.rpartition(":")
            name, text = name.strip(), text.strip()
            if not text:
                raise SmilesError(f"Zeile {nr}: Nach „{name}:“ fehlt die Formel.")
        if " " in text:
            raise SmilesError(f"Zeile {nr}: Zwischen zwei Formeln fehlt ein Zeichen (+, ->, <=>, <->).")
        if len(text) > MAX_SMILES:
            raise SmilesError(f"Zeile {nr}: Eine Formel ist zu lang (höchstens {MAX_SMILES} Zeichen).")
        reihe.teile.append(Molekuel(text, (name or None) and name[:MAX_BESCHRIFTUNG]))
        stueck.clear()

    for wort in zeile.split():
        if wort in _OPERATOREN:
            abschliessen()
            reihe.teile.append(_OPERATOREN[wort])
        else:
            stueck.append(wort)
    abschliessen()
    if sum(isinstance(t, Molekuel) for t in reihe.teile) > MAX_MOLEKUELE_JE_REIHE:
        raise SmilesError(f"Zeile {nr}: Zu viele Formeln (höchstens {MAX_MOLEKUELE_JE_REIHE}).")
    return reihe


# ── Zeichnen ─────────────────────────────────────────────────────────────────

@dataclass
class Bild:
    """Ein gezeichnetes Molekül: SVG ohne Hülle, Größe, Striche der Elektronenpaare."""
    inhalt: str
    breite: float
    hoehe: float
    striche: list[tuple[float, float, float, float]]
    name: str | None = None


def freie_paare(atom) -> int:
    """Zahl der freien Elektronenpaare eines Atoms (nach RDKit-Bindungen und -Ladung)."""
    from rdkit import Chem

    if atom.GetAtomicNum() <= 1:
        return 0
    aussen = Chem.GetPeriodicTable().GetNOuterElecs(atom.GetAtomicNum())
    # Valenz statt aufsummierter Bindungsordnungen: Sie zählt H mit und stimmt auch bei
    # aromatischen Bindungen (1,5), wo die Summe nicht ganzzahlig wäre.
    bindungen = atom.GetTotalValence()
    frei = aussen - atom.GetFormalCharge() - bindungen - atom.GetNumRadicalElectrons()
    return max(0, int(round(frei)) // 2)


def _zeigt_paare(atom, darstellung: str) -> bool:
    if darstellung == "valenzstrich":
        return True
    return atom.GetSymbol() != "C" or atom.GetFormalCharge() != 0


def _richtungen(belegt: list[float], anzahl: int) -> list[float]:
    """``anzahl`` Richtungen in die größten Lücken zwischen den belegten Winkeln."""
    if not belegt:
        # Freies Atom (Wasser als Ion, Halogenid): gleichmäßig, oben beginnend.
        return [-math.pi / 2 + k * 2 * math.pi / anzahl for k in range(anzahl)]
    belegt = sorted(w % (2 * math.pi) for w in belegt)
    luecken = []
    for i, w0 in enumerate(belegt):
        w1 = belegt[(i + 1) % len(belegt)] + (2 * math.pi if i == len(belegt) - 1 else 0)
        luecken.append([w0, w1 - w0, 0])
    for _ in range(anzahl):
        max(luecken, key=lambda l: l[1] / (l[2] + 1))[2] += 1
    return [w0 + groesse * (j + 1) / (k + 1) for w0, groesse, k in luecken for j in range(k)]


def zeichne(molekuel: Molekuel, darstellung: str) -> Bild:
    """Ein Molekül mit RDKit zeichnen und die Elektronenpaare berechnen. Wirft SmilesError."""
    from rdkit import Chem, RDLogger
    from rdkit.Chem.Draw import rdMolDraw2D

    RDLogger.DisableLog("rdApp.*")
    # ⚠️ **Ohne Aromatizitäts-Erkennung.** Sonst erklärt RDKit einen Ring wie in
    # `O=C1C=CC=C[CH-]1` für aromatisch und legt die Doppelbindungen beim Zeichnen neu —
    # bei Grenzformeln ist aber genau ihre Lage (und die der Ladung) die Aussage. Was als
    # Einfach- und Doppelbindung geschrieben ist, bleibt so; nur ausdrücklich aromatisch
    # (klein) geschriebene Ringe werden unten in eine Kekulé-Form gebracht.
    mol = Chem.MolFromSmiles(molekuel.smiles, sanitize=False)
    if mol is not None:
        try:
            Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL
                             ^ Chem.SanitizeFlags.SANITIZE_SETAROMATICITY)
        except Exception:
            mol = None
    if mol is None:
        raise SmilesError(f"„{molekuel.smiles[:60]}“ ist kein gültiges SMILES.")
    if mol.GetNumHeavyAtoms() > MAX_ATOME:
        raise SmilesError(f"Das Molekül ist zu groß (höchstens {MAX_ATOME} Atome ohne Wasserstoff).")
    if darstellung == "valenzstrich":
        mol = Chem.AddHs(mol)
    # Kekulé-Schreibweise: Doppelbindungen statt Kreis im Ring, wie in der Schule.
    Chem.Kekulize(mol, clearAromaticFlags=True)

    d = rdMolDraw2D.MolDraw2DSVG(-1, -1)
    o = d.drawOptions()
    # Bildpunkte je Ångström; eine Bindung ist ~1,5 Å. `fixedBondLength` wirkt bei
    # anpassbarer Zeichenfläche (-1, -1) nicht — die richtet sich nach `scalingFactor`.
    o.scalingFactor = BINDUNGSLAENGE / 1.5
    o.clearBackground = False
    o.addStereoAnnotation = False
    if darstellung == "valenzstrich":
        for a in mol.GetAtoms():
            if a.GetSymbol() == "C":
                o.atomLabels[a.GetIdx()] = "C"
    rdMolDraw2D.PrepareAndDrawMolecule(d, mol, kekulize=True)
    d.FinishDrawing()
    schrift = d.FontSize()

    svg = d.GetDrawingText()
    zeichen = _beschriftung(svg)
    striche = []
    for atom in mol.GetAtoms():
        anzahl = freie_paare(atom)
        if not anzahl or not _zeigt_paare(atom, darstellung):
            continue
        p = d.GetDrawCoords(atom.GetIdx())
        belegt = [math.atan2(d.GetDrawCoords(n.GetIdx()).y - p.y, d.GetDrawCoords(n.GetIdx()).x - p.x)
                  for n in atom.GetNeighbors()]
        # ⚠️ **Gelesen, nicht geschätzt.** Die Beschriftung steht im SVG als ein Pfad je
        # Zeichen (Klasse `atom-<n>`). Was nah an der Atommitte liegt, ist das Symbol; was
        # weiter weg liegt — angehängtes H („OH“), Ladungszeichen, Ziffer —, belegt seine
        # Richtung. Bis 03.11.2026 wurde die H-Seite geschätzt (den Bindungen abgewandt);
        # bei der Carboxygruppe der Benzoesäure stand ein Elektronenpaar dadurch im H.
        symbol: list[tuple[float, float, float, float]] = []
        for x0, y0, x1, y1 in zeichen.get(atom.GetIdx(), []):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if math.dist((mx, my), (p.x, p.y)) < schrift * 0.45:
                symbol.append((x0, y0, x1, y1))
            else:
                belegt.append(math.atan2(my - p.y, mx - p.x))
        luft = schrift * 0.3
        halb = schrift * 0.36
        for phi in _richtungen(belegt, anzahl):
            r = _bis_zum_rand(p.x, p.y, phi, symbol, schrift) + luft
            cx, cy = p.x + r * math.cos(phi), p.y + r * math.sin(phi)
            dx, dy = -math.sin(phi) * halb, math.cos(phi) * halb
            striche.append((cx - dx, cy - dy, cx + dx, cy + dy))

    return Bild(inhalt=svg[svg.find("<svg"):], breite=d.Width(), hoehe=d.Height(),
                striche=striche, name=molekuel.name)


_PFAD = re.compile(r"<path class='atom-(\d+)' d='([^']*)'")
_ZAHL = re.compile(r"-?\d+(?:\.\d+)?")


def _beschriftung(svg: str) -> dict[int, list[tuple[float, float, float, float]]]:
    """Umriss (x0, y0, x1, y1) jedes Beschriftungszeichens, je Atom — aus dem RDKit-SVG."""
    umrisse: dict[int, list[tuple[float, float, float, float]]] = {}
    for treffer in _PFAD.finditer(svg):
        zahlen = [float(z) for z in _ZAHL.findall(treffer.group(2))]
        xs, ys = zahlen[0::2], zahlen[1::2]
        if xs and ys:
            umrisse.setdefault(int(treffer.group(1)), []).append((min(xs), min(ys), max(xs), max(ys)))
    return umrisse


def _bis_zum_rand(cx: float, cy: float, phi: float, kaesten, schrift: float) -> float:
    """Abstand von der Atommitte bis zum Rand des Symbols in Richtung ``phi``.

    Ohne Beschriftung (Kohlenstoff in der Skelettformel) ein halber Schriftgrad.
    """
    if not kaesten:
        return schrift * 0.5
    x0 = min(k[0] for k in kaesten); y0 = min(k[1] for k in kaesten)
    x1 = max(k[2] for k in kaesten); y1 = max(k[3] for k in kaesten)
    dx, dy = math.cos(phi), math.sin(phi)
    t = []
    if dx > 1e-9:
        t.append((x1 - cx) / dx)
    elif dx < -1e-9:
        t.append((x0 - cx) / dx)
    if dy > 1e-9:
        t.append((y1 - cy) / dy)
    elif dy < -1e-9:
        t.append((y0 - cy) / dy)
    return max(0.0, min(t)) if t else schrift * 0.5


def _operator(art: str, x: float, y: float) -> str:
    """Operator als Linien — keine Schrift, damit der Export ohne Glyphen auskommt."""
    s = f'stroke="{FARBE}" stroke-width="1.4" fill="none"'
    m = x + OPERATOR_BREITE / 2
    if art == "plus":
        return (f'<line x1="{m-6:.1f}" y1="{y:.1f}" x2="{m+6:.1f}" y2="{y:.1f}" {s}/>'
                f'<line x1="{m:.1f}" y1="{y-6:.1f}" x2="{m:.1f}" y2="{y+6:.1f}" {s}/>')
    a, b = x + 6, x + OPERATOR_BREITE - 6
    if art == "pfeil":
        return (f'<line x1="{a:.1f}" y1="{y:.1f}" x2="{b:.1f}" y2="{y:.1f}" {s}/>'
                f'<polyline points="{b-6:.1f},{y-4:.1f} {b:.1f},{y:.1f} {b-6:.1f},{y+4:.1f}" {s}/>')
    if art == "mesomerie":
        return (f'<line x1="{a:.1f}" y1="{y:.1f}" x2="{b:.1f}" y2="{y:.1f}" {s}/>'
                f'<polyline points="{b-6:.1f},{y-4:.1f} {b:.1f},{y:.1f} {b-6:.1f},{y+4:.1f}" {s}/>'
                f'<polyline points="{a+6:.1f},{y-4:.1f} {a:.1f},{y:.1f} {a+6:.1f},{y+4:.1f}" {s}/>')
    # Gleichgewicht: zwei Halbpfeile übereinander
    return (f'<line x1="{a:.1f}" y1="{y-3:.1f}" x2="{b:.1f}" y2="{y-3:.1f}" {s}/>'
            f'<polyline points="{b-6:.1f},{y-7:.1f} {b:.1f},{y-3:.1f}" {s}/>'
            f'<line x1="{a:.1f}" y1="{y+3:.1f}" x2="{b:.1f}" y2="{y+3:.1f}" {s}/>'
            f'<polyline points="{a+6:.1f},{y+7:.1f} {a:.1f},{y+3:.1f}" {s}/>')


def setze(block: Block) -> str:
    """Den ganzen Block zu einem SVG zusammensetzen."""
    reihen = [[zeichne(t, block.darstellung) if isinstance(t, Molekuel) else t for t in r.teile]
              for r in block.reihen]
    teile_svg: list[str] = []
    gesamt_breite = 0.0
    y = 0.0
    for reihe in reihen:
        bilder = [t for t in reihe if isinstance(t, Bild)]
        mit_namen = any(b.name for b in bilder)
        hoehe = max(b.hoehe for b in bilder) + 2 * RAND + (BESCHRIFTUNG_HOEHE if mit_namen else 0)
        mitte = y + (max(b.hoehe for b in bilder) + 2 * RAND) / 2
        x = 0.0
        for t in reihe:
            if isinstance(t, str):
                teile_svg.append(_operator(t, x, mitte))
                x += OPERATOR_BREITE
                continue
            ox, oy = x + RAND, mitte - t.hoehe / 2
            innen = t.inhalt.replace("<svg ", f'<svg x="{ox:.1f}" y="{oy:.1f}" overflow="visible" ', 1)
            teile_svg.append(innen)
            for x1, y1, x2, y2 in t.striche:
                teile_svg.append(
                    f'<line x1="{ox+x1:.1f}" y1="{oy+y1:.1f}" x2="{ox+x2:.1f}" y2="{oy+y2:.1f}" '
                    f'stroke="{FARBE}" stroke-width="1.5" stroke-linecap="round"/>'
                )
            if t.name:
                teile_svg.append(
                    f'<text x="{ox + t.breite / 2:.1f}" y="{y + hoehe - 4:.1f}" text-anchor="middle" '
                    f'font-family="sans-serif" font-size="12" fill="{FARBE}">{escape(t.name)}</text>'
                )
            x += t.breite + 2 * RAND
        gesamt_breite = max(gesamt_breite, x)
        y += hoehe + ZEILEN_ABSTAND
    gesamt_hoehe = y - ZEILEN_ABSTAND
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{gesamt_breite:.0f}" '
        f'height="{gesamt_hoehe:.0f}" viewBox="0 0 {gesamt_breite:.1f} {gesamt_hoehe:.1f}" '
        f'role="img" aria-label="Strukturformel">' + "".join(teile_svg) + "</svg>"
    )


async def render_smiles(source: str) -> str:
    """Registry-Renderer für kind='smiles'. Wirft RenderError."""
    block = lies(source)  # schnelle Prüfung außerhalb des Threads
    try:
        return await asyncio.wait_for(asyncio.to_thread(setze, block),
                                      timeout=settings.smiles_render_timeout)
    except asyncio.TimeoutError:
        raise RenderError("Strukturformel: Zeitlimit überschritten")
    except SmilesError:
        raise
    except Exception as e:
        logger.exception("Strukturformel-Render fehlgeschlagen")
        raise RenderError(f"Strukturformel konnte nicht gezeichnet werden: {str(e)[:150]}")
