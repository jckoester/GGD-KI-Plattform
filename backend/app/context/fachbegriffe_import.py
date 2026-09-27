"""Fachbegriffe und Stoffsteckbriefe aus Markdown-Dateien in den Wissensgraph.

**Der Kern, den zwei Wege benutzen** (Paket 10, AP1): das Admin-Skript
`backend/scripts/seed_fachbegriffe.py` und — ab AP3 — der Upload-Dialog der Fachschaft.
Bis zum 27.09.2026 lag alles im Skript; ein zweiter Aufrufer hätte es entweder importiert
(`backend/scripts/` ist bewusst **kein** Paket, siehe CLAUDE.md) oder nachgebaut.

**Die Eingabe ist ein Bündel, kein Ordner.** `dateien` bildet einen Pfad innerhalb des
Bündels auf seinen Inhalt ab — `"Oxidation.md" -> b"---\nknotentyp: begriff\n…"`. Wo die
Bytes herkommen, ist die Sache des Aufrufers: Das Skript liest einen Ordner, der Endpunkt
entpackt ein Zip. Diese Schicht kennt kein Dateisystem.

⚠️ **Bytes, nicht Text.** Eine Datei mit kaputter Kodierung soll im Bericht stehen und
nicht den Lauf abbrechen — genauso wie kaputtes Frontmatter. Aus einem Zip kommt ohnehin
nichts anderes.

**Das Format** beschreibt `_Format.md` im Vault der Fachschaft; die Schnittstelle —
gelesene Schlüssel, Idempotenz, Bericht — steht in `docs/dev/fachbegriffe-import.md`.

⚠️ **Während des Pilots ist die Quelle die Wahrheit** — anders als bei
`seed_methodik.py`, das Lücken füllt und nichts überschreibt. Ein Lauf setzt den Knoten
auf den Stand der Datei, **solange in der Oberfläche niemand daran gearbeitet hat**.
Dafür merkt sich der Knoten in `metadata.seed_hash`, wie er den letzten Lauf verlassen
hat. Weicht sein heutiger Stand davon ab, hat ihn jemand bearbeitet — dann überspringt
der Lauf ihn und sagt es. `ueberschreiben=True` setzt sich darüber hinweg.

**Kanten des Imports tragen `{"seed": true}`** und werden bei jedem Lauf neu gesetzt. Von
Hand angelegte Kanten bleiben unberührt: Wer im Verknüpfen-Dialog etwas ergänzt, soll es
beim nächsten Import nicht verlieren.

**Woran ein Knoten wiedererkannt wird: an seiner `id`** (AP2, Entscheidung D3), einer
Kleinbuchstaben-Kennung im Frontmatter, die je Fach eindeutig ist. Bis Paket 9 war es
der **Dateiname** (`metadata.seed_quelle`) — eine umbenannte Datei ergab einen zweiten
Knoten, und beim Pflegen im Vault ist Umbenennen keine Ausnahme. Fehlt die `id`, leitet
der Lauf sie aus Fachkürzel und Dateiname ab (`ch-oxidation-sauerstoffaufnahme`), legt
sie am Knoten ab und meldet sie; der Export (AP5) schreibt sie in die Datei zurück.
Gesucht wird erst nach `id`, dann — für den Übergang — nach `seed_quelle`.

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
Backfill ein neues — der Import selbst braucht keinen laufenden LiteLLM-Proxy.
"""
# Bewusst **ohne** `from __future__ import annotations`: Das Admin-Skript lädt in Tests
# über `spec_from_file_location`, ohne sich in `sys.modules` einzutragen. `@dataclass`
# löst Zeichenketten-Annotationen dann gegen ein Modul auf, das es dort nicht gibt, und
# scheitert mit einem `AttributeError`, der nach allem aussieht außer nach der Ursache.
import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping

import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.context import aliase as alias_dienst
from app.context.metadata import STUB_MARKIERUNG, validate_node_metadata
from app.context.taxonomy import (
    CONTENT_TYPE_TO_CATEGORY,
    EMBEDDING_CONTENT_TYPES,
    feld_schema,
)
from app.db.models import ContextEdge, ContextNode, Group, Subject, ohne_aenderungsstempel

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
#: Die **stabile Kennung** eines Knotens im Fach (AP2, Entscheidung D3). Sie steht im
#: Frontmatter als `id:` und übersteht das Umbenennen der Datei — `seed_quelle` tut das
#: nicht: Eine umbenannte Datei ergäbe einen zweiten Knoten. Der Name führt „seed" fort,
#: weil die drei Schlüssel zusammengehören und dasselbe aussagen — geschrieben vom
#: Import, nicht in der Oberfläche.
SEED_ID = "seed_id"
#: Alles, was der Import an Verwaltungsangaben an den Knoten schreibt.
SEED_SCHLUESSEL = (SEED_QUELLE, SEED_HASH, SEED_ID)



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

#: Eine `id` ist kleingeschrieben, trägt Ziffern und Bindestriche — und sonst nichts.
#: Sie steht in Dateien, in Exportnamen und später in URLs; Großschreibung, Umlaute oder
#: Leerzeichen wären an jeder dieser Stellen eine eigene Fehlerquelle.
_ID_MUSTER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def ist_gueltige_id(wert: str) -> bool:
    return bool(_ID_MUSTER.match(wert or ""))


def _slug(text: str) -> str:
    klein = (text or "").strip().lower().translate(_UMLAUTE)
    return re.sub(r"[^a-z0-9]+", "-", klein).strip("-")


def leite_id_ab(fach_praefix: str, dateiname: str) -> str:
    """Kennung aus Fachkürzel und Dateiname: `CH` + `Oxidation (Sauerstoffaufnahme)`
    → `ch-oxidation-sauerstoffaufnahme`.

    Leer, wenn der Dateiname nichts hergibt (`Δ.md`). Dann hat die Datei keine
    ableitbare Identität, und der Bericht verlangt ein `id:` im Frontmatter — eine
    erfundene Kennung (etwa aus einer Prüfsumme) wäre schlimmer als eine verlangte:
    Sie stünde später im Export, ohne dass jemand sie wiedererkennt.

    ⚠️ Dieselbe Regel steht ein zweites Mal als SQL in Alembic `0079` (Migration der
    Bestandsknoten). `tests/integration/test_seed_id_sql.py` hält beide zusammen.
    """
    rest = _slug(dateiname)
    if not rest:
        return ""
    praefix = _slug(fach_praefix)
    return f"{praefix}-{rest}" if praefix else rest


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
    #: `id:` aus dem Frontmatter, bereits geprüft. Leer heißt „nicht angegeben" — dann
    #: leitet der Schreibteil sie ab; nur er kennt das Fachkürzel.
    id_angabe: str = ""


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


def lies_datei(dateiname: str, roh: str) -> Quelldatei | None:
    """Eine Quelldatei einlesen. ``None``, wenn sie nicht hierher gehört.

    ``dateiname`` ist der Name **ohne** Endung — er ist der Schlüssel, über den
    Wikilinks auflösen (siehe Modulkopf: zwei Durchläufe).

    ⚠️ **Nicht `name` nennen.** Weiter unten läuft ``for name, text in _abschnitte(…)``;
    ein gleichnamiger Parameter wäre nach der Schleife überschrieben, und der Titel
    einer Datei ohne `titel:` würde zum letzten Abschnittsnamen („Offene Fragen").
    Beim Herauslösen aus dem Skript genau so passiert — ein Test hat es gefangen.

    Wirft ``ValueError`` bei kaputtem Frontmatter — das ist ein Fehler in der Datei und
    kein Grund, sie zu überspringen.
    """
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
    id_angabe = str(kopf_daten.get("id") or "").strip()
    if id_angabe and not ist_gueltige_id(id_angabe):
        # ⚠️ **Die Datei wird trotzdem gelesen.** Eine ungültige Kennung hat noch nie
        # einen Knoten benannt — geschrieben wird nur Geprüftes. Sie wie „nicht
        # angegeben" zu behandeln kann deshalb keinen zweiten Knoten erzeugen: Der
        # Import findet den bestehenden weiter über `seed_quelle`. Die Datei
        # abzuweisen verlöre dagegen sechsunddreißig Kanten wegen eines Großbuchstabens.
        warnungen.append(
            f"id „{id_angabe}“ verworfen — erlaubt sind Kleinbuchstaben, Ziffern und "
            "Bindestriche"
        )
        id_angabe = ""
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
        datei=dateiname,
        knotentyp=knotentyp,
        titel=(kopf_daten.get("titel") or dateiname).strip(),
        fach=(kopf_daten.get("fach") or "").strip(),
        content="\n\n".join(a for a in absaetze if a).strip(),
        aliase=alias_dienst.bereinige(_als_liste(kopf_daten.get("aliase"))),
        metadata=metadata,
        fundstellen=[f for f in _als_liste(kopf_daten.get("bildungsplan"))],
        kanten=vereinige(kanten),
        warnungen=warnungen,
        id_angabe=id_angabe,
    )


def lade_svg(metadata: dict[str, Any], dateien: Mapping[str, bytes]) -> list[str]:
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
        roh = dateien.get(str(abb["datei"]))
        if roh is None:
            fehlend.append(str(abb["datei"]))
            continue
        try:
            abb["svg"] = roh.decode("utf-8")
        except UnicodeDecodeError:
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

    ⚠️ **Auch `seed_id`**, und zwar nicht aus Bequemlichkeit: Die Kennung ist Identität,
    nicht Inhalt. Stünde sie im Hash, hielte der Lauf nach der Migration (Alembic 0079)
    sechsunddreißig unveränderte Knoten für handverändert und rührte keinen davon mehr
    an — die Idempotenz wäre genau dort gebrochen, wo sie gebraucht wird.
    """
    ohne_seed = {k: v for k, v in (metadata or {}).items() if k not in SEED_SCHLUESSEL}
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
    #: Dateien ohne `id:` im Frontmatter → die Kennung, die der Lauf vergeben hat.
    #: Solange die Fachschaft in Dateien ohne `id:` pflegt, meldet das jeder Lauf; der
    #: Export (AP5) schreibt sie zurück, und dann verstummt die Meldung von selbst.
    vergebene_ids: dict[str, str] = field(default_factory=dict)
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


@dataclass
class Bestand:
    """Was im Fach schon liegt — für Wikilinks, deren Ziel **nicht** im Bündel steckt.

    Beim Ordnerimport aus dem Vault ist das die Ausnahme (dort liegen alle Dateien
    beieinander); beim Hochladen einer einzelnen Datei ist es der Normalfall, und ohne
    diesen Rückgriff verlöre so eine Datei jede Kante.

    Gesucht wird in drei Anläufen: erst die abgeleitete Kennung, dann die Herkunftsdatei,
    zuletzt der Titel. Der Titel steht am Ende, weil er als Einziger mehrdeutig sein
    kann — „Oxidation" tragen im Pilot zwei Fassungen.
    """

    nach_id: dict[str, Any]
    nach_quelle: dict[str, Any]
    #: Titel (casefold) → Knoten-ID, oder ``None``, wenn ihn mehrere Knoten tragen.
    nach_titel: dict[str, Any]
    praefix: str

    def finde(self, ziel_datei: str) -> Any:
        treffer = self.nach_id.get(leite_id_ab(self.praefix, ziel_datei))
        if treffer is None:
            treffer = self.nach_quelle.get(ziel_datei)
        if treffer is None:
            treffer = self.nach_titel.get(ziel_datei.strip().casefold())
        return treffer

    def mehrdeutig(self, ziel_datei: str) -> bool:
        schluessel = ziel_datei.strip().casefold()
        return schluessel in self.nach_titel and self.nach_titel[schluessel] is None


async def _bestand(db: AsyncSession, fach: Subject) -> Bestand:
    """Kennung, Herkunftsdatei und Titel aller Fachbegriffe **eines Fachs**.

    Auf `TYPEN` beschränkt: Ein Wikilink `[[Säuren und Basen]]` darf nicht auf ein
    gleichnamiges Curriculum-Kapitel zeigen. Was der Import schreibt, darf er auch
    als Ziel annehmen — mehr nicht.
    """
    zeilen = (await db.execute(
        sa.select(
            ContextNode.id,
            ContextNode.title,
            ContextNode.metadata_[SEED_ID].astext,
            ContextNode.metadata_[SEED_QUELLE].astext,
        ).where(
            ContextNode.subject_id == fach.id,
            ContextNode.content_type.in_(TYPEN),
        )
    )).all()
    nach_id: dict[str, Any] = {}
    nach_quelle: dict[str, Any] = {}
    nach_titel: dict[str, Any] = {}
    for knoten_id, titel, kennung, quelle in zeilen:
        if kennung:
            nach_id[kennung] = knoten_id
        if quelle:
            nach_quelle[quelle] = knoten_id
        schluessel = (titel or "").strip().casefold()
        if schluessel:
            nach_titel[schluessel] = None if schluessel in nach_titel else knoten_id
    return Bestand(nach_id, nach_quelle, nach_titel, fach.fach_code or fach.slug)


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


async def _finde_knoten(
    db: AsyncSession, subject_id: int, stabile_id: str, dateiname: str
) -> ContextNode | None:
    """Den Knoten zu einer Quelldatei suchen — **erst** über die Kennung.

    Der zweite Griff über `seed_quelle` ist der Übergang aus Paket 9: Knoten von damals
    tragen nur die Herkunftsdatei. Alembic `0079` rüstet die Kennung nach, aber ein
    Bestand, der vor der Migration importiert und seither nie wieder angefasst wurde,
    liefe sonst in einen zweiten Knoten. Der Lauf schreibt dabei die Kennung mit —
    danach greift der erste Weg.

    ⚠️ Die Reihenfolge zählt, wo **beides** zutrifft — und das ist genau beim Aufräumen
    nach altem Recht: Wer vor AP2 umbenannt hat, hat zwei Knoten, einen mit der Kennung
    und einen mit dem alten Dateinamen. Die Kennung ist die ausdrückliche Angabe der
    Fachschaft, der Dateiname nur eine Vermutung des Imports; also gewinnt sie.
    """
    treffer = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.subject_id == subject_id,
            ContextNode.metadata_[SEED_ID].astext == stabile_id,
        )
    )).scalars().first()
    if treffer is not None:
        return treffer
    return (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.subject_id == subject_id,
            ContextNode.metadata_[SEED_QUELLE].astext == dateiname,
        )
    )).scalars().first()


async def _schreibe_knoten(
    db: AsyncSession,
    quelle: Quelldatei,
    fach: Subject,
    gruppe_id: int,
    bilanz: Bilanz,
    *,
    stabile_id: str,
    vorhanden: ContextNode | None,
    ueberschreiben: bool,
) -> Any:
    """Einen Knoten anlegen oder nachziehen. Gibt die Knoten-ID zurück (oder ``None``)."""
    metadata = dict(quelle.metadata)
    metadata[SEED_QUELLE] = quelle.datei
    metadata[SEED_ID] = stabile_id
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
    await _trage_kennung_nach(db, vorhanden, stabile_id)
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


async def _trage_kennung_nach(
    db: AsyncSession, knoten: ContextNode, stabile_id: str
) -> None:
    """Die Kennung an einem bestehenden Knoten nachziehen — **vor** jedem Rückweg.

    ⚠️ Sonst bliebe die Übergangsschicht liegen, wo sie am meisten gebraucht wird: Ein
    Knoten, dessen Datei sich nicht geändert hat, verließe jeden Lauf über den Zweig
    „unverändert", bekäme nie eine Kennung — und ein Umbenennen der Datei ergäbe doch
    wieder einen zweiten Knoten. Dasselbe gilt für handveränderte Knoten: Ihren Inhalt
    lässt der Lauf in Ruhe, ihre Identität ist davon unberührt.

    Ohne Änderungsstempel: Eine Kennung nachzutragen ist keine Bearbeitung, und
    `updated_at` ist seit Paket 9 die Antwort auf „wie aktuell ist dieser Knoten?".
    Deshalb als Core-`update()` — bei einer ORM-Zuweisung feuerte `onupdate`.
    """
    if (knoten.metadata_ or {}).get(SEED_ID) == stabile_id:
        return
    neu = {**(knoten.metadata_ or {}), SEED_ID: stabile_id}
    await db.execute(
        sa.update(ContextNode)
        .where(ContextNode.id == knoten.id)
        .values(metadata_=neu, **ohne_aenderungsstempel())
        .execution_options(synchronize_session=False)
    )
    # Den Stand im Speicher nachziehen, **ohne** das Objekt schmutzig zu machen: Eine
    # gewöhnliche Zuweisung löste beim Flush ein zweites UPDATE samt `onupdate` aus,
    # `expire()` einen Nachladeversuch — und der bricht in asyncio ab.
    attributes.set_committed_value(knoten, "metadata_", neu)


async def _schreibe_kanten(
    db: AsyncSession,
    quelle: Quelldatei,
    von_id: Any,
    nach_datei: dict[str, Any],
    bestand: Bestand,
    bp: dict[tuple[str, str, str], Any],
    editionen: dict[str, str],
    bilanz: Bilanz,
) -> None:
    """Die Kanten eines Knotens neu setzen — nur die des Seeds.

    Von Hand angelegte Kanten bleiben stehen: Wer im Verknüpfen-Dialog etwas ergänzt,
    soll es beim nächsten Import nicht verlieren. Erkennbar sind die eigenen an
    `metadata.seed`.

    Ein Wikilink zeigt zuerst ins **Bündel** (dort steht die Zuordnung Datei → Knoten
    fest) und erst danach in den vorhandenen Bestand des Fachs — sonst hätte eine
    einzeln hochgeladene Datei keine einzige Kante.
    """
    geplant: list[tuple[str, Any, dict]] = []
    for kante in quelle.kanten:
        ziel_id = nach_datei.get(kante.ziel_datei) or bestand.finde(kante.ziel_datei)
        if ziel_id is None:
            if bestand.mehrdeutig(kante.ziel_datei):
                # Zwei Fassungen tragen denselben Titel („Oxidation"). Eine davon zu
                # greifen wäre geraten; im Bündel unterscheidet der Dateiname sie.
                bilanz.warnungen.append(
                    f"{quelle.datei}: Ziel „{kante.ziel_datei}“ ist im Bestand "
                    "mehrdeutig — keine Kante"
                )
            else:
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
    #: (Fach, Kennung) → Datei. Zwei Dateien mit derselben `id` sind ein Fehler im
    #: Bündel; ohne diese Prüfung überschriebe die zweite die erste, und der Bericht
    #: meldete „2 aktualisiert" für einen Knoten.
    belegt: dict[tuple[int, str], str] = {}
    #: Knoten-ID → Datei. Dieselbe Falle über Bande: Datei A trifft den Knoten über die
    #: Kennung, Datei B über die Herkunftsdatei.
    beansprucht: dict[Any, str] = {}

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

        stabile_id = quelle.id_angabe or leite_id_ab(
            fach.fach_code or fach.slug, quelle.datei
        )
        if not stabile_id:
            bilanz.warnungen.append(
                f"{quelle.datei}: keine `id` ableitbar — bitte `id:` im Frontmatter "
                "setzen"
            )
            continue
        schon = belegt.get((fach.id, stabile_id))
        if schon:
            bilanz.warnungen.append(
                f"{quelle.datei}: Kennung „{stabile_id}“ gehört in diesem Bündel schon "
                f"zu {schon} — übersprungen"
            )
            continue
        belegt[(fach.id, stabile_id)] = quelle.datei
        if not quelle.id_angabe:
            bilanz.vergebene_ids[quelle.datei] = stabile_id

        vorhanden = await _finde_knoten(db, fach.id, stabile_id, quelle.datei)
        if vorhanden is not None and vorhanden.id in beansprucht:
            bilanz.warnungen.append(
                f"{quelle.datei}: trifft denselben Knoten wie "
                f"{beansprucht[vorhanden.id]} — übersprungen"
            )
            continue

        knoten_id = await _schreibe_knoten(
            db, quelle, fach, gruppe_id, bilanz,
            stabile_id=stabile_id, vorhanden=vorhanden, ueberschreiben=ueberschreiben,
        )
        if knoten_id is not None:
            beansprucht[knoten_id] = quelle.datei
            nach_datei[quelle.datei] = knoten_id
            zu_verkanten.append((quelle, knoten_id, fach))

    bp_je_fach: dict[int, dict] = {}
    editionen_je_fach: dict[int, dict] = {}
    bestand_je_fach: dict[int, Bestand] = {}
    for quelle, knoten_id, fach in zu_verkanten:
        if fach.id not in bp_je_fach:
            bp_je_fach[fach.id] = await _bp_knoten(db, fach.id)
            editionen_je_fach[fach.id] = await _editionen(db, fach.id)
            # Nach dem Knotendurchlauf gelesen, also einschließlich der eben
            # geschriebenen — was in `nach_datei` steht, findet sich hier wieder.
            bestand_je_fach[fach.id] = await _bestand(db, fach)
        await _schreibe_kanten(
            db, quelle, knoten_id, nach_datei, bestand_je_fach[fach.id],
            bp_je_fach[fach.id], editionen_je_fach[fach.id], bilanz,
        )




# ── Teil 3: Der gemeinsame Einstieg ──────────────────────────────────────────

def lies_buendel(
    dateien: Mapping[str, bytes], bilanz: "Bilanz", fach_vorgabe: str | None = None
) -> list[Quelldatei]:
    """Alle Knotendateien eines Bündels lesen; Fehler landen im Bericht, nicht im Abbruch.

    Eine unlesbare Datei stoppt den Lauf nicht: Von sechsunddreißig Dateien soll eine
    kaputte nicht die anderen fünfunddreißig verhindern. Sie steht im Bericht, und der
    ist die Arbeitsliste.

    **Welche Dateien gelesen werden:** `*.md` auf oberster Ebene, ohne führenden
    Unterstrich. Das hält `_Format.md` draußen und alles unter `_Abb/` — Letzteres wird
    nicht übersprungen, sondern über :func:`lade_svg` an seinem Pfad gesucht.
    """
    gelesen: list[Quelldatei] = []
    for pfad in sorted(dateien):
        name = pfad.rsplit("/", 1)[-1]
        if "/" in pfad or not name.endswith(".md") or name.startswith("_"):
            continue
        try:
            quelle = lies_datei(name[:-3], dateien[pfad].decode("utf-8"))
        except UnicodeDecodeError:
            bilanz.warnungen.append(f"{name}: nicht lesbar — keine UTF-8-Kodierung")
            continue
        except (ValueError, yaml.YAMLError) as fehler:
            bilanz.warnungen.append(f"{name}: nicht lesbar — {fehler}")
            continue
        if quelle is None:
            continue
        if not quelle.fach and fach_vorgabe:
            quelle.fach = fach_vorgabe
        bilanz.warnungen += [
            f"{quelle.datei}: SVG nicht gefunden — {n}"
            for n in lade_svg(quelle.metadata, dateien)
        ]
        bilanz.warnungen += [
            f"{quelle.datei}: Abbildung im Text ohne Eintrag unter illustrationen — {n}"
            for n in pruefe_abbildungen(quelle)
        ]
        bilanz.warnungen += [f"{quelle.datei}: {w}" for w in quelle.warnungen]
        gelesen.append(quelle)
    return gelesen


async def importiere(
    db: AsyncSession,
    dateien: Mapping[str, bytes],
    *,
    fach_vorgabe: str | None = None,
    ueberschreiben: bool = False,
) -> Bilanz:
    """Ein Bündel einlesen und schreiben — der eine Weg, den Skript und Endpunkt gehen.

    Gibt den Bericht zurück und **committet nicht**: Wer aufruft, entscheidet, ob der
    Lauf zählt. Genau daran hängt der Probelauf des Dialogs (AP3) — er verwirft die
    Transaktion und legt dieselbe Bilanz vor.
    """
    bilanz = Bilanz()
    gelesen = lies_buendel(dateien, bilanz, fach_vorgabe)
    await seed_in_session(db, gelesen, bilanz, ueberschreiben=ueberschreiben)
    return bilanz
