#!/usr/bin/env python3
"""Fachbegriffe und Stoffsteckbriefe aus einem Obsidian-Ordner in den Wissensgraph.

    python scripts/seed_fachbegriffe.py --quelle "<Vault>/Projekte/Fachbegriffe Chemie/Fachbegriffe Ch Pilot"
    python scripts/seed_fachbegriffe.py --quelle "<Pfad>" --dry-run
    python scripts/seed_fachbegriffe.py --quelle "<Pfad>" --ueberschreiben

Das Format beschreibt `_Format.md` im Quellordner; eine Datei ist ein Knoten. Gelesen
werden `.md`-Dateien mit `knotentyp: begriff` oder `stoffsteckbrief`; Dateien mit
führendem `_` bleiben liegen (`_Format.md`, `_Abb/`).

⚠️ **Während des Pilots ist der Vault die Quelle der Wahrheit** — anders als bei
`seed_methodik.py`, das Lücken füllt und nichts überschreibt. Hier gilt: Ein Lauf setzt
den Knoten auf den Stand der Datei, **solange in der Oberfläche niemand daran gearbeitet
hat**. Dafür merkt sich der Knoten in `metadata.seed_hash`, wie er den letzten Seed
verlassen hat. Weicht sein heutiger Stand davon ab, hat ihn jemand bearbeitet — dann
überspringt der Lauf ihn und sagt es. `--ueberschreiben` setzt sich darüber hinweg.

**Kanten des Seeds tragen `{"seed": true}`** und werden bei jedem Lauf neu gesetzt. Von
Hand angelegte Kanten bleiben unberührt: Wer im Verknüpfen-Dialog etwas ergänzt, soll es
beim nächsten Import nicht verlieren.

**Zwei Durchläufe, und das muss so sein:** Erst alle Knoten, dann alle Kanten. Ein
Wikilink zeigt auf eine **Datei**, nicht auf einen Titel — gleichnamige Fassungen
(„Oxidation") haben denselben Titel und wären über ihn nicht zu unterscheiden. Die
Zuordnung Datei → Knoten-ID steht erst fest, wenn alle Knoten geschrieben sind.

**Nicht auflösbare Wikilinks erzeugen keine Kante** (Entscheidung E3, 26.09.2026): Rund
achtzig Ziele gibt es im Pilot noch nicht. Sie als Stub anzulegen flutete die Sammlung
„Fachbegriffe", die Schüler:innen sehen. Der Bericht listet sie nach Häufigkeit — das
ist die Arbeitsliste für die Breite, und ein erneuter Lauf schließt die Kanten, sobald
die Ziele da sind.

Geänderte Knoten verlieren ihr Embedding (`embedding = NULL`) und bekommen beim nächsten
Backfill ein neues — der Seed selbst braucht keinen laufenden LiteLLM-Proxy:

    python scripts/embedding_backfill.py --content-type begriff --content-type stoffsteckbrief
"""
# Bewusst **ohne** `from __future__ import annotations`: Die Testhilfe lädt dieses
# Skript über `spec_from_file_location`, ohne es in `sys.modules` einzutragen
# (`backend/scripts/` ist kein Paket, siehe CLAUDE.md). `@dataclass` löst
# Zeichenketten-Annotationen dann gegen ein Modul auf, das es dort nicht gibt, und
# scheitert mit einem `AttributeError`, der nach allem aussieht außer nach der Ursache.
import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.context import aliase as alias_dienst
from app.context.metadata import STUB_MARKIERUNG, validate_node_metadata
from app.context.taxonomy import (
    CONTENT_TYPE_TO_CATEGORY,
    EMBEDDING_CONTENT_TYPES,
    feld_schema,
)
from app.db.models import ContextEdge, ContextNode, Group, Subject

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

#: Knotentypen, die dieser Seed schreibt. Andere `knotentyp:`-Werte sind ein Tippfehler
#: in der Datei und werden gemeldet, nicht stillschweigend übergangen.
TYPEN = ("begriff", "stoffsteckbrief")

#: Metadatenschlüssel, die **nicht** im Feldschema stehen und trotzdem mitgeschrieben
#: werden. Die Feldtypen (`int|text|auswahl|liste`) tragen keine verschachtelten
#: Objekte; `eigenschaften` ist genau das (Entscheidung AP2b). `illustrationen` ebenso.
FREIE_METADATEN = ("eigenschaften", "ghs", "illustrationen")

#: Wird an den Knoten geschrieben, damit ein zweiter Lauf ihn wiederfindet und erkennt,
#: ob seither jemand in der Oberfläche daran gearbeitet hat.
SEED_QUELLE = "seed_quelle"
SEED_HASH = "seed_hash"


# ── Teil 1: Lesen — ohne Datenbank, damit prüfbar ────────────────────────────

# `![[EN_H2O.svg]]` → `{{abbildung:EN_H2O.svg}}`: derselbe Platzhalter, den `_fuer_modell`
# zur Bildbeschreibung macht (AP3) und den die Oberfläche durch das SVG ersetzt (AP6).
_EINBETTUNG = re.compile(r"!\[\[([^\[\]]+?)\]\]")
# `[[Ziel]]` oder `[[Ziel|Anzeigetext]]` im Fließtext — **keine** Kante (nur Frontmatter
# und `## Abgrenzung` erzeugen welche), sondern Klartext.
_WIKILINK = re.compile(r"\[\[([^\[\]]+?)\]\]")
#: Eine Zeile aus `## Abgrenzung`, die ausdrücklich keine ist.
OHNE_ABGRENZUNG = "(keine)"
# `CH.V2 3.2.1.3 (3)` · `CH.V3 3.1.1 (2)` · `CH.V2 3.2.1.1 Einl.` · `CH 3.2.1.1 (1)`
_FUNDSTELLE = re.compile(
    r"^(?P<fach>[A-Za-zÄÖÜäöü]+)(?P<suffix>\.[A-Z0-9]+)?\s+"
    r"(?P<nr>\d+(?:\.\d+)*)\s+(?:\((?P<teil>\d+)\)|Einl\.)$"
)

#: Der Abschnitt, dessen Text **ohne Überschrift** an den Anfang von `content` kommt.
#: Die Taxonomie nennt das Feld selbst „Definition" — eine Überschrift gleichen Namens
#: darüber wäre eine Dopplung. Alles Weitere bekommt eine.
DEFINITION = "Definition"
#: Abschnitte, die in `content` gehören, in der Reihenfolge der Datei.
ABSCHNITTE_CONTENT = (DEFINITION, "Erklärung", "Beispiele")
#: Abschnitte, die nicht in `content` landen, weil sie woanders hingehören.
ABSCHNITT_METADATA = "Fehlvorstellungen"
ABSCHNITT_KANTEN = "Abgrenzung"
ABSCHNITT_VERWORFEN = "Offene Fragen"


@dataclass
class Kante:
    """Eine geplante Kante — das Ziel ist noch ein **Dateiname**, keine Knoten-ID."""

    relation: str
    ziel_datei: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Quelldatei:
    datei: str                      # Dateiname ohne `.md` — der Schlüssel für Wikilinks
    knotentyp: str
    titel: str
    fach: str
    content: str
    aliase: list[str]
    metadata: dict[str, Any]
    fundstellen: list[str]          # Rohform, aufgelöst wird erst gegen die Datenbank
    kanten: list[Kante]
    warnungen: list[str]


def _ziel(wikilink: str) -> str:
    """`[[Ziel|Anzeigetext]]` → `Ziel`.

    Nimmt den Link **mit oder ohne** eckige Klammern: Aus dem Fließtext kommt er schon
    zerlegt (die Klammern hat der Ausdruck gefressen), aus dem Frontmatter als ganzer
    String `"[[Salz]]"`. Beides hier abzufangen ist billiger, als es an jeder
    Aufrufstelle zu unterscheiden — und ein `[[` im Titel wäre ohnehin ein Fehler.
    """
    roh = (wikilink or "").strip()
    if roh.startswith("[[") and roh.endswith("]]"):
        roh = roh[2:-2]
    return roh.split("|", 1)[0].strip()


def _anzeigetext(wikilink: str) -> str:
    """`[[Ziel|Anzeigetext]]` → `Anzeigetext`, sonst das Ziel selbst."""
    teile = (wikilink or "").split("|", 1)
    return (teile[1] if len(teile) == 2 else teile[0]).strip()


def _als_liste(wert) -> list[str]:
    """Ein Feld, das ein Wikilink oder eine Liste davon sein darf, als Liste.

    `stoffklasse` ist genau einer, `teilchen` und `verwandt` sind mehrere — und YAML
    macht aus `"[[Salz]]"` einen String, aus `["[[Salz]]"]` eine Liste. Beides hier
    einzufangen ist billiger, als es an fünf Aufrufstellen zu unterscheiden.
    """
    if wert is None or wert == "":
        return []
    if isinstance(wert, str):
        return [wert]
    return [w for w in wert if isinstance(w, str) and w.strip()]


def _abschnitte(rumpf: str) -> list[tuple[str, str]]:
    """Den Textteil in `(Überschrift, Text)` zerlegen, Reihenfolge wie in der Datei."""
    teile: list[tuple[str, str]] = []
    name, zeilen = "", []
    for zeile in rumpf.splitlines():
        if zeile.startswith("## "):
            if name or any(z.strip() for z in zeilen):
                teile.append((name, "\n".join(zeilen).strip()))
            name, zeilen = zeile[3:].strip(), []
        else:
            zeilen.append(zeile)
    if name or any(z.strip() for z in zeilen):
        teile.append((name, "\n".join(zeilen).strip()))
    return teile


def _aufzaehlung(text: str) -> list[str]:
    """Die Punkte einer Markdown-Aufzählung als Liste — Zeilen ohne `-` fallen weg."""
    return [
        zeile.lstrip("-*").strip()
        for zeile in text.splitlines()
        if zeile.lstrip().startswith(("-", "*")) and zeile.lstrip("-* \t").strip()
    ]


def _fliesstext(text: str) -> str:
    """Einbettungen zu Platzhaltern, Wikilinks zu Klartext.

    ⚠️ **Einbettungen zuerst.** `![[x.svg]]` enthält ein `[[x.svg]]`; andersherum bliebe
    ein verwaistes `!` vor dem Dateinamen stehen.
    """
    text = _EINBETTUNG.sub(lambda m: "{{abbildung:%s}}" % _ziel(m.group(1)), text)
    return _WIKILINK.sub(lambda m: _anzeigetext(m.group(1)), text)


#: Welche Art gewinnt, wenn dieselbe Kante mehrfach genannt wird — absteigend.
#:
#: ⚠️ **Die Reihenfolge ist eine Entscheidung, keine Aufzählung.** Ganz oben steht, was
#: eine **Traversierung** verfolgen würde: Die Vertiefung ist der Lernpfad zwischen zwei
#: Fassungen und der Grund, warum ADR-013 Kanten überhaupt nach Art trennt. Die
#: Abgrenzung steht unten — sie erklärt, sie verbindet nicht. Ihr Hinweistext geht
#: trotzdem nicht verloren (siehe `vereinige`).
ART_RANG = ("vertiefung", "teilchen", "ghs", "abgrenzung")


def vereinige(kanten: list[Kante]) -> list[Kante]:
    """Mehrfach genannte Ziele zu **einer** Kante zusammenziehen.

    ⚠️ **Der Zusammenzug ist erzwungen, nicht gewählt.** Auf `context_edges` liegt ein
    eindeutiger Index über `(from_node_id, to_node_id, relation)`: Zwei
    `related_to`-Kanten zwischen denselben Knoten kann die Datenbank gar nicht halten.
    Zu entscheiden ist also nur, **welche** Aussage die Kante trägt.

    Der Regelfall ist harmlos: „Wasser" nennt „Wasserstoff" unter `verwandt` *und* in
    der Abgrenzung — dasselbe zweimal, die aussagekräftigere gewinnt.

    ⚠️ **Der Grenzfall war es nicht.** „Redoxreaktion (Sauerstoffübertragung)" nennt die
    Elektronenfassung als **Abgrenzung** *und* als **Vertiefung**; beides stimmt, und es
    sind zwei verschiedene Aussagen. Die erste Fassung entschied nach der Zahl der
    Metadatenschlüssel — damit gewann die Abgrenzung (sie trägt einen Hinweistext), und
    die Vertiefung fiel lautlos weg: ausgerechnet die Kantenart, für die es die
    Unterscheidung gibt. Jetzt entscheidet :data:`ART_RANG`, und die Angaben der
    unterlegenen Nennung **wandern mit** — der Hinweistext bleibt, und `arten` hält
    fest, dass die Kante mehr als eine Lesart hat.
    """
    gruppen: dict[tuple[str, str], list[Kante]] = {}
    for kante in kanten:
        gruppen.setdefault((kante.relation, kante.ziel_datei), []).append(kante)

    def rang(kante: Kante) -> tuple[int, int]:
        art = kante.metadata.get("art", "")
        # Ohne Art ganz nach hinten: „verwandt" sagt nichts, was „grenzt sich ab von"
        # nicht auch sagt. Bei gleichem Rang gewinnt die reichhaltigere Nennung.
        platz = ART_RANG.index(art) if art in ART_RANG else len(ART_RANG)
        return (platz, -len(kante.metadata))

    vereint: list[Kante] = []
    for (relation, ziel), gruppe in gruppen.items():
        gruppe.sort(key=rang)
        gewinner, rest = gruppe[0], gruppe[1:]
        metadata = dict(gewinner.metadata)
        for andere in rest:
            for schluessel, wert in andere.metadata.items():
                metadata.setdefault(schluessel, wert)
        arten = [k.metadata["art"] for k in gruppe if k.metadata.get("art")]
        if len(set(arten)) > 1:
            metadata["arten"] = sorted(set(arten))
        vereint.append(Kante(relation, ziel, metadata))
    return vereint


def _abgrenzungszeile(zeile: str, warnungen: list[str]) -> list[Kante]:
    """`- [[Ziel]] – Hinweis` → Kante(n). Eine Zeile darf **mehrere** Ziele nennen.

    ⚠️ **Mehrere, nicht eines.** „[[Natrium]] und [[Chlor]] – die Elemente, aus denen
    es entsteht" steht so im Pilot; ein Ausdruck, der nur den ersten Link nimmt,
    verliert die Hälfte der Aussage. Beide bekommen denselben Hinweistext — er gilt
    ihnen gemeinsam.

    Der Hinweis ist alles **nach dem letzten** `]]`, nicht alles nach dem ersten
    Gedankenstrich: Hinweise enthalten selbst welche („die O–H-Bindungen").

    ⚠️ **Eine Zeile ohne Wikilink erzeugt keine Kante und geht auch nicht in den Text.**
    `## Abgrenzung` bleibt aus `content` heraus, aus demselben Grund wie die
    Fehlvorstellungen: Sie sagt, was der Begriff **nicht** ist, und zöge im Vektor
    genau die Fragen an, die sie abgrenzen soll. Der Bericht nennt solche Zeilen —
    sie gehören im Vault in die dokumentierte Form gebracht.
    """
    zeile = zeile.strip()
    if not zeile or zeile == OHNE_ABGRENZUNG:
        return []
    ziele = _WIKILINK.findall(zeile)
    if not ziele:
        warnungen.append(f"Abgrenzung ohne Wikilink, keine Kante: {zeile[:70]}")
        return []
    hinweis = _fliesstext(zeile.rsplit("]]", 1)[1]).lstrip(" –—-\t").strip()
    metadata = {"art": "abgrenzung"}
    if hinweis:
        metadata["hinweis"] = hinweis
    return [Kante("related_to", _ziel(z), dict(metadata)) for z in ziele]


def lies_datei(pfad: Path) -> Quelldatei | None:
    """Eine Vault-Datei einlesen. ``None``, wenn sie nicht hierher gehört.

    Wirft ``ValueError`` bei kaputtem Frontmatter — das ist ein Fehler in der Datei und
    kein Grund, sie zu überspringen.
    """
    roh = pfad.read_text(encoding="utf-8")
    if not roh.startswith("---"):
        raise ValueError("kein Frontmatter")
    kopf, rumpf = roh[3:].split("\n---", 1)
    kopf_daten = yaml.safe_load(kopf) or {}
    if not isinstance(kopf_daten, dict):
        raise ValueError("Frontmatter ist kein Zuordnungsblock")

    knotentyp = (kopf_daten.get("knotentyp") or "").strip()
    if knotentyp not in TYPEN:
        return None

    warnungen: list[str] = []
    absaetze: list[str] = []
    metadata: dict[str, Any] = {}
    kanten: list[Kante] = []

    for name, text in _abschnitte(rumpf):
        if not text:
            continue
        if name == DEFINITION or not name:
            absaetze.append(_fliesstext(text))
        elif name in ABSCHNITTE_CONTENT:
            absaetze.append(f"### {name}\n\n{_fliesstext(text)}")
        elif name == ABSCHNITT_METADATA:
            metadata["fehlvorstellungen"] = [_fliesstext(p) for p in _aufzaehlung(text)]
        elif name == ABSCHNITT_KANTEN:
            for zeile in _aufzaehlung(text):
                kanten += _abgrenzungszeile(zeile, warnungen)
        elif name == ABSCHNITT_VERWORFEN:
            continue
        else:
            # ⚠️ **Unbekannte Abschnitte gehen mit, statt zu verschwinden.** Im Pilot
            # ist das `## Darstellung` (Wasserstoffbrücken) — von Hand geschriebener
            # Fachtext, den `_Format.md` nicht kennt. Ihn stillschweigend fallen zu
            # lassen wäre der schlimmere Fehler; der Bericht nennt ihn, damit das
            # Format nachgezogen werden kann.
            warnungen.append(f"Abschnitt „{name}“ steht nicht in _Format.md")
            absaetze.append(f"### {name}\n\n{_fliesstext(text)}")

    # Frontmatter → Metadata: nur, was das Feldschema kennt, plus die ausdrücklich
    # freigegebenen Schlüssel. Alles andere ist Steuerinformation für diesen Seed
    # (`knotentyp`, `bildungsplan`, `verwandt`, …) und gehört nicht an den Knoten.
    erlaubt = set(feld_schema(knotentyp)) | set(FREIE_METADATEN)
    for schluessel in erlaubt:
        wert = kopf_daten.get(schluessel)
        if wert in (None, "", [], {}):
            continue
        if schluessel == "fehlvorstellungen":
            continue          # kommt aus dem Textteil, nicht aus dem Frontmatter
        metadata[schluessel] = wert

    for feld, relation, extra in (
        ("oberbegriff", "is_a", {}),
        ("stoffklasse", "is_a", {}),
        ("verwandt", "related_to", {}),
        ("voraussetzung", "requires", {}),
        # ⚠️ Nur `vertieft_in`, nicht `vertieft`. Beide Seiten tragen die Beziehung im
        # Vault, damit man sie in jeder Datei sieht; eine Kante je Richtung wäre
        # dieselbe Aussage zweimal. Die Richtung ist die des Lernwegs: frühere Fassung
        # → spätere.
        ("vertieft_in", "related_to", {"art": "vertiefung"}),
        # `teilchen` und `ghs` sind keine eigene Relation: Der Knotentyp führt
        # `is_a`, `related_to` und `references` (AP2b) — mehr zu erfinden hieße, die
        # Typentscheidung im Seed zu überstimmen. `art` unterscheidet sie, wie bei
        # `abgrenzung` und `vertiefung`.
        ("teilchen", "related_to", {"art": "teilchen"}),
    ):
        for link in _als_liste(kopf_daten.get(feld)):
            kanten.append(Kante(relation, _ziel(link), dict(extra)))

    for eintrag in kopf_daten.get("ghs") or []:
        if isinstance(eintrag, str):
            kanten.append(Kante("related_to", _ziel(eintrag), {"art": "ghs"}))
        elif isinstance(eintrag, dict) and eintrag.get("piktogramm"):
            kanten_meta = {"art": "ghs"}
            # Die Einstufung hängt an Form oder Konzentration („ab 0,1 mol/L"). Das ist
            # eine Eigenschaft der **Beziehung**, nicht des Piktogramms — sonst stünde
            # an GHS05 die Konzentration der Salzsäure.
            if eintrag.get("gilt_fuer"):
                kanten_meta["gilt_fuer"] = str(eintrag["gilt_fuer"])
            kanten.append(Kante("related_to", _ziel(eintrag["piktogramm"]), kanten_meta))
        else:
            warnungen.append(f"GHS-Eintrag weder Wikilink noch Objekt: {eintrag!r}")

    return Quelldatei(
        datei=pfad.stem,
        knotentyp=knotentyp,
        titel=(kopf_daten.get("titel") or pfad.stem).strip(),
        fach=(kopf_daten.get("fach") or "").strip(),
        content="\n\n".join(a for a in absaetze if a).strip(),
        aliase=alias_dienst.bereinige(_als_liste(kopf_daten.get("aliase"))),
        metadata=metadata,
        fundstellen=[f for f in _als_liste(kopf_daten.get("bildungsplan"))],
        kanten=vereinige(kanten),
        warnungen=warnungen,
    )


def lade_svg(metadata: dict[str, Any], wurzel: Path) -> list[str]:
    """SVG-Dateien der `illustrationen` einlesen und inline ablegen.

    Gibt die Namen zurück, die **nicht** gefunden wurden. Der Inhalt geht in
    `illustrationen[].svg`; das Modell bekommt ihn nicht zu sehen (`_ohne_svg`, AP3),
    die Oberfläche setzt ihn sanitisiert an die Stelle des Platzhalters (AP6).

    `tex` bleibt eine Pfadangabe in den Vault: Die Quelle einer Strukturformel ist ein
    Arbeitsmittel des Autors, kein Inhalt des Wissensgraphen.
    """
    fehlend: list[str] = []
    for abb in metadata.get("illustrationen") or []:
        if not isinstance(abb, dict) or not abb.get("datei"):
            continue
        pfad = wurzel / str(abb["datei"])
        if pfad.is_file():
            abb["svg"] = pfad.read_text(encoding="utf-8")
        else:
            fehlend.append(str(abb["datei"]))
    return fehlend


def pruefe_abbildungen(quelle: Quelldatei) -> list[str]:
    """Platzhalter im Text ohne Eintrag unter `illustrationen` — und umgekehrt nicht.

    Nur die eine Richtung ist ein Fehler: Ein Platzhalter ohne Eintrag zeigt in der
    Oberfläche nichts und dem Modell nichts (AP3 macht daraus ein nacktes
    `[Abbildung]`). Eine Illustration ohne Einbettung dagegen ist zulässig — sie steht
    am Ende der Detailansicht.
    """
    bekannt = {
        str(abb["datei"]).rsplit("/", 1)[-1]
        for abb in quelle.metadata.get("illustrationen") or []
        if isinstance(abb, dict) and abb.get("datei")
    }
    im_text = set(re.findall(r"\{\{abbildung:([^{}]+)\}\}", quelle.content))
    return sorted(name for name in im_text if name.rsplit("/", 1)[-1] not in bekannt)


@dataclass
class Fundstelle:
    """`CH.V2 3.2.1.3 (3)` zerlegt. ``teil is None`` heißt: die Einleitung des Abschnitts."""

    roh: str
    fach_code: str
    suffix: str
    nr: str
    teil: str | None

    @property
    def content_type(self) -> str:
        return "ik_kompetenz" if self.teil else "leitidee"

    @property
    def schluessel(self) -> str:
        """Der Wert, unter dem der Bildungsplan-Import die Nummer abgelegt hat.

        ⚠️ **Gegen `metadata`, nicht gegen den Titel.** Ein Titel-Präfix `3.2.1.1(1)`
        trifft auch `3.2.1.1(10)` bis `(12)` — im Pilot gibt es beide.
        """
        return f"{self.nr}({self.teil})" if self.teil else self.nr


def lies_fundstelle(roh: str) -> Fundstelle | None:
    treffer = _FUNDSTELLE.match(roh.strip())
    if not treffer:
        return None
    return Fundstelle(
        roh=roh.strip(),
        fach_code=treffer.group("fach"),
        suffix=treffer.group("suffix") or "",
        nr=treffer.group("nr"),
        teil=treffer.group("teil"),
    )


def bereinige_metadata(knotentyp: str, metadata: dict) -> list[str]:
    """Felder, die das Schema nicht annimmt, **entfernen** und benennen.

    ⚠️ **Feld weg, Knoten bleibt.** Der erste Entwurf ließ `validate_node_metadata`
    über den ganzen Knoten laufen — ein `genus: "der (Stoff)"` in einer von
    sechsunddreißig Dateien brach damit den kompletten Lauf ab. Über einen Artikel die
    Definition, die Aliase und elf Kanten zu verlieren, steht in keinem Verhältnis.

    Still ist das trotzdem nicht: Jedes verworfene Feld steht im Bericht, und **das**
    ist der Zweck des Pilots — das Format an echten Daten zu prüfen. Wer die Datei
    korrigiert, bekommt das Feld beim nächsten Lauf zurück.
    """
    warnungen: list[str] = []
    for name in list(metadata):
        try:
            validate_node_metadata(knotentyp, {name: metadata[name]})
        except ValueError as fehler:
            warnungen.append(f"Feld `{name}` verworfen — {fehler}")
            del metadata[name]
    return warnungen


def stand_hash(titel: str, content: str, metadata: dict, aliase: list[str]) -> str:
    """Fingerabdruck dessen, was der Seed am Knoten verantwortet.

    Die Seed-Schlüssel selbst bleiben draußen — sonst hinge der Hash von sich selbst ab.
    """
    ohne_seed = {k: v for k, v in (metadata or {}).items() if k not in (SEED_QUELLE, SEED_HASH)}
    roh = json.dumps(
        [titel, content, ohne_seed, list(aliase)], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:32]


# ── Teil 2: Schreiben ────────────────────────────────────────────────────────


@dataclass
class Bilanz:
    neu: int = 0
    aktualisiert: int = 0
    unveraendert: int = 0
    uebersprungen: list[str] = field(default_factory=list)
    neu_einzubetten: int = 0
    kanten: int = 0
    kanten_geaendert: int = 0
    warnungen: list[str] = field(default_factory=list)
    #: Wikilink-Ziele ohne Knoten, nach Häufigkeit — die Arbeitsliste für die Breite.
    offene_ziele: Counter = field(default_factory=Counter)
    #: Fundstellen, zu denen es keinen Bildungsplan-Knoten gibt.
    offene_fundstellen: Counter = field(default_factory=Counter)
    #: Fundstellen, deren Knoten **archiviert** ist — die Kante entsteht, wirkt
    #: in der Oberfläche aber nicht (die Nachbarschaft zeigt nur Aktives).
    archivierte_ziele: Counter = field(default_factory=Counter)


async def _faecher(db: AsyncSession) -> dict[str, Subject]:
    """Fächer unter allen Namen, unter denen eine Datei sie nennen kann."""
    schluessel: dict[str, Subject] = {}
    for fach in (await db.execute(sa.select(Subject))).scalars():
        for name in (fach.name, fach.slug, fach.fach_code):
            if name:
                schluessel[name.strip().casefold()] = fach
    return schluessel


async def _editionen(db: AsyncSession, subject_id: int) -> dict[str, str]:
    """Suffix → `bp_version`, abgelesen am **Bestand** des Fachs.

    ⚠️ Nicht geraten: `bp_version` ist Basisjahr + Suffix (`2016.V3`), und welches
    Basisjahr ein Fach führt, steht nur in den Daten. Fehlt eine Edition im Dev-System,
    soll das als „nicht auflösbar" im Bericht auftauchen und nicht als stiller Griff
    zur falschen Fassung.
    """
    werte = (await db.execute(
        sa.select(sa.distinct(ContextNode.bp_version)).where(
            ContextNode.subject_id == subject_id,
            ContextNode.bp_version != "",
        )
    )).scalars().all()
    karte: dict[str, str] = {}
    for wert in werte:
        basis, _, suffix = (wert or "").partition(".")
        karte["." + suffix if suffix else ""] = wert
    return karte


async def _bp_knoten(db: AsyncSession, subject_id: int) -> dict[tuple[str, str, str], Any]:
    """`(bp_version, content_type, Nummer)` → Knoten-ID für Leitideen und IK-Kompetenzen."""
    nummer = sa.func.coalesce(
        ContextNode.metadata_["kompetenz_nr"].astext,
        ContextNode.metadata_["nr"].astext,
    )
    zeilen = (await db.execute(
        sa.select(
            ContextNode.id, ContextNode.bp_version, ContextNode.content_type,
            nummer, ContextNode.status,
        ).where(
            ContextNode.subject_id == subject_id,
            ContextNode.content_type.in_(("ik_kompetenz", "leitidee")),
            nummer.isnot(None),
        )
    )).all()
    # Der Status wandert mit: Eine Kante auf einen **archivierten** Knoten entsteht
    # zwar, wirkt in der Oberfläche aber nicht — die Nachbarschaft zeigt nur Aktives.
    # Angelegt wird sie trotzdem (sie trägt, sobald die Edition wieder gilt); gezählt
    # wird sie im Bericht.
    return {(v, ct, nr): (knoten_id, status) for knoten_id, v, ct, nr, status in zeilen}


def _ist_zustand(node: ContextNode, aliase: list[str]) -> dict[str, Any]:
    metadata = dict(node.metadata_ or {})
    return {
        "titel": node.title,
        "content": node.content or "",
        "metadata": metadata,
        "aliase": list(aliase),
        "hash": stand_hash(node.title, node.content or "", metadata, aliase),
        "embedding_vorhanden": node.embedding is not None,
    }


async def _schreibe_knoten(
    db: AsyncSession,
    quelle: Quelldatei,
    fach: Subject,
    gruppe_id: int,
    bilanz: Bilanz,
    *,
    ueberschreiben: bool,
) -> Any:
    """Einen Knoten anlegen oder nachziehen. Gibt die Knoten-ID zurück (oder ``None``)."""
    vorhanden = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.subject_id == fach.id,
            ContextNode.metadata_[SEED_QUELLE].astext == quelle.datei,
        )
    )).scalars().first()

    metadata = dict(quelle.metadata)
    metadata[SEED_QUELLE] = quelle.datei
    # Ohne Text ist ein Eintrag ein Titel: `content` ist bei beiden Typen Pflicht, und
    # `traegt_substanz()` hielte den Vektor ohnehin zurück. Die Markierung ist dieselbe
    # wie beim Verknüpfen-Dialog (UI-Notiz A8).
    if not quelle.content:
        metadata[STUB_MARKIERUNG] = True
    bilanz.warnungen += [
        f"{quelle.datei}: {w}" for w in bereinige_metadata(quelle.knotentyp, metadata)
    ]
    # Der Hash **nach** der Bereinigung: Er soll den Stand beschreiben, der wirklich
    # geschrieben wird — sonst gälte der Knoten beim nächsten Lauf als von Hand geändert.
    metadata[SEED_HASH] = stand_hash(
        quelle.titel, quelle.content, metadata, quelle.aliase
    )

    if vorhanden is None:
        knoten = ContextNode(
            category=CONTENT_TYPE_TO_CATEGORY[quelle.knotentyp],
            content_type=quelle.knotentyp,
            title=quelle.titel,
            content=quelle.content,
            subject_id=fach.id,
            status="active",
            metadata_=metadata,
            # Das Zielbild aus ADR-019: Fachschaftsgut, alle lesen.
            read_scope="school",
            write_scope="subject",
            read_scope_group_id=None,
            write_scope_group_id=gruppe_id,
        )
        db.add(knoten)
        await db.flush()
        await alias_dienst.setze(db, knoten.id, quelle.aliase)
        bilanz.neu += 1
        return knoten.id

    ist = _ist_zustand(vorhanden, await alias_dienst.lade(db, vorhanden.id))
    if ist["hash"] == metadata[SEED_HASH]:
        bilanz.unveraendert += 1
        return vorhanden.id

    # ⚠️ **Der Kern der Idempotenz.** `seed_hash` ist der Stand, den der letzte Lauf
    # hinterlassen hat. Stimmt der heutige Stand damit überein, hat seither niemand in
    # der Oberfläche gearbeitet — dann darf der Vault gewinnen. Stimmt er nicht, gäbe
    # ein Überschreiben fremde Arbeit lautlos preis.
    gemerkt = (vorhanden.metadata_ or {}).get(SEED_HASH)
    if gemerkt and ist["hash"] != gemerkt and not ueberschreiben:
        bilanz.uebersprungen.append(quelle.datei)
        return vorhanden.id

    vorhanden.title = quelle.titel
    vorhanden.content = quelle.content
    vorhanden.metadata_ = metadata
    vorhanden.read_scope = "school"
    vorhanden.write_scope = "subject"
    vorhanden.write_scope_group_id = gruppe_id
    await alias_dienst.setze(db, vorhanden.id, quelle.aliase)
    if ist["embedding_vorhanden"] and quelle.knotentyp in EMBEDDING_CONTENT_TYPES:
        vorhanden.embedding = None
        bilanz.neu_einzubetten += 1
    bilanz.aktualisiert += 1
    return vorhanden.id


async def _schreibe_kanten(
    db: AsyncSession,
    quelle: Quelldatei,
    von_id: Any,
    nach_datei: dict[str, Any],
    bp: dict[tuple[str, str, str], Any],
    editionen: dict[str, str],
    bilanz: Bilanz,
) -> None:
    """Die Kanten eines Knotens neu setzen — nur die des Seeds.

    Von Hand angelegte Kanten bleiben stehen: Wer im Verknüpfen-Dialog etwas ergänzt,
    soll es beim nächsten Import nicht verlieren. Erkennbar sind die eigenen an
    `metadata.seed`.
    """
    geplant: list[tuple[str, Any, dict]] = []
    for kante in quelle.kanten:
        ziel_id = nach_datei.get(kante.ziel_datei)
        if ziel_id is None:
            bilanz.offene_ziele[kante.ziel_datei] += 1
            continue
        if ziel_id == von_id:
            bilanz.warnungen.append(f"{quelle.datei}: Kante auf sich selbst, ausgelassen")
            continue
        geplant.append((kante.relation, ziel_id, dict(kante.metadata)))

    for roh in quelle.fundstellen:
        fundstelle = lies_fundstelle(roh)
        if fundstelle is None:
            bilanz.warnungen.append(f"{quelle.datei}: Fundstelle unlesbar — {roh!r}")
            continue
        version = editionen.get(fundstelle.suffix)
        treffer = bp.get(
            (version, fundstelle.content_type, fundstelle.schluessel)
        ) if version else None
        if treffer is None:
            bilanz.offene_fundstellen[fundstelle.roh] += 1
            continue
        ziel_id, status = treffer
        if status != "active":
            bilanz.archivierte_ziele[f"{fundstelle.fach_code}{fundstelle.suffix}"] += 1
        geplant.append(("references", ziel_id, {"fundstelle": fundstelle.roh}))

    soll: dict[tuple[str, Any], dict] = {}
    for relation, ziel_id, metadata in geplant:
        soll.setdefault((relation, ziel_id), {**metadata, "seed": True})

    vorhanden = (await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == von_id,
            ContextEdge.metadata_["seed"].astext == "true",
        )
    )).scalars().all()
    ist = {(k.relation, k.to_node_id): dict(k.metadata_ or {}) for k in vorhanden}

    bilanz.kanten += len(soll)
    # ⚠️ **Nur bei Unterschied anfassen.** Löschen und Neuanlegen bei jedem Lauf gäbe
    # jeder Kante eine neue `id` und ein neues `created_at` — und der Bericht meldete
    # 262 Kanten neben „0 aktualisiert", was sich liest wie 262 Änderungen. Ein
    # unveränderter Lauf soll ein unveränderter Lauf sein, auch in der Datenbank.
    if ist == soll:
        return

    await db.execute(
        sa.delete(ContextEdge).where(
            ContextEdge.from_node_id == von_id,
            ContextEdge.metadata_["seed"].astext == "true",
        )
    )
    for (relation, ziel_id), metadata in soll.items():
        db.add(ContextEdge(
            from_node_id=von_id, to_node_id=ziel_id, relation=relation, metadata_=metadata
        ))
    bilanz.kanten_geaendert += len(soll) + len(ist)


def lies_ordner(quellordner: Path, bilanz: "Bilanz", fach_vorgabe: str | None = None):
    """Alle Dateien eines Ordners lesen; Fehler landen im Bericht, nicht im Abbruch.

    Eine unlesbare Datei stoppt den Lauf nicht: Von sechsunddreißig Dateien soll eine
    kaputte nicht die anderen fünfunddreißig verhindern. Sie steht im Bericht, und der
    ist die Arbeitsliste.
    """
    gelesen: list[Quelldatei] = []
    for pfad in sorted(p for p in quellordner.glob("*.md") if not p.name.startswith("_")):
        try:
            quelle = lies_datei(pfad)
        except (ValueError, yaml.YAMLError) as fehler:
            bilanz.warnungen.append(f"{pfad.name}: nicht lesbar — {fehler}")
            continue
        if quelle is None:
            continue
        if not quelle.fach and fach_vorgabe:
            quelle.fach = fach_vorgabe
        bilanz.warnungen += [
            f"{quelle.datei}: SVG nicht gefunden — {name}"
            for name in lade_svg(quelle.metadata, quellordner)
        ]
        bilanz.warnungen += [
            f"{quelle.datei}: Abbildung im Text ohne Eintrag unter illustrationen — {name}"
            for name in pruefe_abbildungen(quelle)
        ]
        bilanz.warnungen += [f"{quelle.datei}: {w}" for w in quelle.warnungen]
        gelesen.append(quelle)
    return gelesen


async def seed_in_session(
    db: AsyncSession,
    gelesen: list[Quelldatei],
    bilanz: "Bilanz",
    *,
    ueberschreiben: bool = False,
) -> None:
    """Der Schreibteil — mit einer **übergebenen** Sitzung.

    Getrennt von :func:`seed`, damit der Integrationstest gegen die Testdatenbank
    laufen kann, ohne `settings.database_url` umzubiegen. Committet nicht: Wer die
    Sitzung mitbringt, entscheidet über die Transaktion.
    """
    faecher = await _faecher(db)
    nach_datei: dict[str, Any] = {}
    zu_verkanten: list[tuple[Quelldatei, Any, Subject]] = []

    for quelle in gelesen:
        fach = faecher.get(quelle.fach.casefold())
        if fach is None:
            bilanz.warnungen.append(f"{quelle.datei}: Fach „{quelle.fach}“ unbekannt")
            continue
        gruppe_id = (await db.execute(
            sa.select(Group.id).where(
                Group.subject_id == fach.id, Group.type == "subject_department"
            ).order_by(Group.id).limit(1)
        )).scalar_one_or_none()
        if gruppe_id is None:
            # `write_scope = subject` **verlangt** eine Gruppe (CHECK
            # `check_context_nodes_write_group_id`). Auf `school` auszuweichen wäre kein
            # Notbehelf, sondern eine andere Zusage: Dann dürfte jede Lehrkraft den
            # Eintrag ändern, nicht die Fachschaft.
            bilanz.warnungen.append(
                f"{quelle.datei}: Fach „{fach.name}“ hat keine Fachschaftsgruppe — "
                "übersprungen"
            )
            continue
        knoten_id = await _schreibe_knoten(
            db, quelle, fach, gruppe_id, bilanz, ueberschreiben=ueberschreiben
        )
        if knoten_id is not None:
            nach_datei[quelle.datei] = knoten_id
            zu_verkanten.append((quelle, knoten_id, fach))

    bp_je_fach: dict[int, dict] = {}
    editionen_je_fach: dict[int, dict] = {}
    for quelle, knoten_id, fach in zu_verkanten:
        if fach.id not in bp_je_fach:
            bp_je_fach[fach.id] = await _bp_knoten(db, fach.id)
            editionen_je_fach[fach.id] = await _editionen(db, fach.id)
        await _schreibe_kanten(
            db, quelle, knoten_id, nach_datei,
            bp_je_fach[fach.id], editionen_je_fach[fach.id], bilanz,
        )


async def seed(
    quellordner: Path,
    *,
    fach_vorgabe: str | None = None,
    dry_run: bool = False,
    ueberschreiben: bool = False,
) -> Bilanz:
    bilanz = Bilanz()
    gelesen = lies_ordner(quellordner, bilanz, fach_vorgabe)

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        await seed_in_session(db, gelesen, bilanz, ueberschreiben=ueberschreiben)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    await engine.dispose()
    return bilanz


def _berichte(bilanz: Bilanz, *, dry_run: bool) -> None:
    logger.info(
        "Fachbegriff-Seed%s: %d neu, %d aktualisiert, %d unverändert; "
        "%d Kanten, davon %s.",
        " (Probelauf, nichts geschrieben)" if dry_run else "",
        bilanz.neu, bilanz.aktualisiert, bilanz.unveraendert, bilanz.kanten,
        f"{bilanz.kanten_geaendert} angefasst" if bilanz.kanten_geaendert
        else "keine geändert",
    )
    if bilanz.uebersprungen:
        logger.warning(
            "%d Knoten seit dem letzten Seed in der Oberfläche geändert und deshalb "
            "nicht überschrieben (mit --ueberschreiben erzwingen): %s",
            len(bilanz.uebersprungen), ", ".join(bilanz.uebersprungen),
        )
    for zeile in bilanz.warnungen:
        logger.warning("%s", zeile)
    if bilanz.offene_fundstellen:
        logger.warning(
            "%d Fundstellen ohne Bildungsplan-Knoten (%d verschieden):",
            sum(bilanz.offene_fundstellen.values()), len(bilanz.offene_fundstellen),
        )
        for roh, anzahl in bilanz.offene_fundstellen.most_common():
            logger.warning("    %2dx  %s", anzahl, roh)
    if bilanz.archivierte_ziele:
        # ⚠️ Kein Fehler des Imports, aber eine Lücke in der Wirkung: In der
        # Detailansicht taucht eine Kante auf einen archivierten Knoten nicht auf.
        logger.warning(
            "%d Fundstellen zeigen auf **archivierte** Bildungsplan-Knoten — die "
            "Kanten entstehen, sind in der Oberfläche aber unsichtbar. Je Edition: %s",
            sum(bilanz.archivierte_ziele.values()),
            ", ".join(f"{k}: {n}" for k, n in bilanz.archivierte_ziele.most_common()),
        )
    if bilanz.offene_ziele:
        logger.info(
            "%d Verweise auf noch nicht vorhandene Bausteine (%d verschieden) — "
            "die Arbeitsliste für die Breite:",
            sum(bilanz.offene_ziele.values()), len(bilanz.offene_ziele),
        )
        for ziel, anzahl in bilanz.offene_ziele.most_common():
            logger.info("    %2dx  %s", anzahl, ziel)
    if bilanz.neu_einzubetten:
        logger.info(
            "%d Vektoren verworfen — ihre Eingabe hat sich geändert.", bilanz.neu_einzubetten
        )
    if bilanz.neu or bilanz.neu_einzubetten:
        logger.info(
            "Nächster Schritt: python scripts/embedding_backfill.py "
            "--content-type begriff --content-type stoffsteckbrief"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fachbegriffe und Stoffsteckbriefe aus einem Obsidian-Ordner einspielen"
    )
    parser.add_argument("--quelle", required=True, type=Path, help="Der Ordner mit den .md-Dateien")
    parser.add_argument(
        "--fach",
        default=None,
        help="Fach für Dateien **ohne** `fach:`-Angabe (Kürzel, Slug oder Name). "
             "Die Angabe in der Datei hat Vorrang.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen, nichts schreiben")
    parser.add_argument(
        "--ueberschreiben",
        action="store_true",
        help="Auch Knoten ersetzen, die seit dem letzten Seed in der Oberfläche "
             "geändert wurden",
    )
    args = parser.parse_args()

    if not args.quelle.is_dir():
        parser.error(f"Kein Verzeichnis: {args.quelle}")

    bilanz = asyncio.run(seed(
        args.quelle,
        fach_vorgabe=args.fach,
        dry_run=args.dry_run,
        ueberschreiben=args.ueberschreiben,
    ))
    _berichte(bilanz, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
