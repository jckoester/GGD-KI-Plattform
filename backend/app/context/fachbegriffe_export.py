"""Fachbegriffe zurück in Markdown-Dateien — der Rückweg (Paket 10, AP5, D1).

**Warum es den Export geben muss.** Eine Fachschaft darf in Dateien pflegen *oder* in
der Oberfläche (Entscheidung D1). Ohne Rückweg wäre die zweite von jeder späteren
Massenänderung abgeschnitten: Wer einmal importiert und danach im Editor gearbeitet hat,
bekäme seinen Bestand nie wieder als Dateien heraus.

**Die Umkehrung von `lies_datei`, nicht die Originaldatei.** Exportiert wird der Stand
des Speichers. Was der Import unterwegs auflöst, kommt nicht zurück: Ein `[[Verweis]]`
im Fließtext wurde beim Lesen zu Klartext, ein `pruefstatus` wurde nie gespeichert.
Beides ist gewollt — der Speicher ist die Wahrheit, nicht die Datei von vorgestern.

⚠️ **Jede Datei prüft sich selbst.** Nach dem Schreiben liest
:func:`app.context.fachbegriffe_import.lies_datei` sie wieder ein und vergleicht den
Stand-Hash mit dem des Knotens. Stimmt er nicht, stünde beim nächsten Import
„aktualisiert", obwohl sich nichts geändert hat — und niemand wüsste, warum. Der
Prüfsatz in `tests/` deckt die Fixtures ab; diese Prüfung deckt **den echten Bestand**
ab, in dem Knoten stehen, die nie durch eine Datei gegangen sind.

**Was der Export nicht kann,** steht als Hinweis in `_Export-Hinweise.txt` im Bündel:
Metadaten außerhalb des Formats, Kanten auf Knoten, die das Format nicht benennen kann,
und jede Datei, die die Selbstprüfung nicht besteht. Die Datei beginnt mit einem
Unterstrich und wird beim Wiedereinlesen übergangen — sie ist Beipackzettel, kein Inhalt.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.context import aliase as alias_dienst
from app.context.fachbegriffe_import import (
    ABSCHNITT_KANTEN,
    ABSCHNITT_METADATA,
    DEFINITION,
    FREIE_METADATEN,
    SEED_ID,
    SEED_QUELLE,
    SEED_SCHLUESSEL,
    TYPEN,
    lies_datei,
    stand_hash,
)
from app.context.metadata import STUB_MARKIERUNG
from app.context.taxonomy import feld_schema
from app.db.models import ContextEdge, ContextNode, Subject

logger = logging.getLogger(__name__)

#: Die Hinweisdatei im Bündel. Unterstrich, damit `lies_buendel` sie übergeht.
HINWEISE = "_Export-Hinweise.txt"

#: Metadatenschlüssel, die nicht ins Frontmatter gehören, ohne dass etwas fehlte:
#: Verwaltungsangaben des Imports und die Stub-Markierung, die der Schreibteil aus dem
#: leeren `content` ohnehin neu setzt.
OHNE_ENTSPRECHUNG = frozenset({*SEED_SCHLUESSEL, STUB_MARKIERUNG})


@dataclass
class Ausgabedatei:
    pfad: str
    inhalt: bytes


@dataclass
class Exportbilanz:
    knoten: int = 0
    abbildungen: int = 0
    warnungen: list[str] = field(default_factory=list)


# ── Teil 1: Eine Datei schreiben ─────────────────────────────────────────────

def _abschnitte_aus_content(content: str) -> list[tuple[str, str]]:
    """`content` zurück in `(Überschrift, Text)`.

    Der Leser macht aus `## Erklärung` in der Datei ein `### Erklärung` in `content`;
    hier geht es die Stufe wieder hinauf. Der Text **vor** der ersten Überschrift ist
    die Definition — sie steht in der Datei unter ihrem Namen, in `content` ohne, weil
    die Taxonomie das Feld selbst so nennt.
    """
    name, zeilen = DEFINITION, []
    teile: list[tuple[str, str]] = []
    for zeile in (content or "").splitlines():
        if zeile.startswith("### "):
            teile.append((name, "\n".join(zeilen).strip()))
            name, zeilen = zeile[4:].strip(), []
        else:
            zeilen.append(zeile)
    teile.append((name, "\n".join(zeilen).strip()))
    return [(n, t) for n, t in teile if t]


def _mit_einbettungen(text: str) -> str:
    """`{{abbildung:x.svg}}` → `![[x.svg]]` — der Platzhalter zurück in Obsidian-Form."""
    import re

    return re.sub(r"\{\{abbildung:([^}]+)\}\}", lambda m: f"![[{m.group(1)}]]", text)


def _wikilink(name: str) -> str:
    return f"[[{name}]]"


def _arten(metadata: dict) -> list[str]:
    """Alle Lesarten einer Kante.

    ⚠️ **`arten` vor `art`.** Eine Kante kann aus zwei Nennungen entstanden sein —
    „Redoxreaktion (Sauerstoffübertragung)" nennt die Elektronenfassung als Abgrenzung
    *und* als Vertiefung, und `vereinige()` hält beides in `arten` fest. Nur die
    Gewinner-Art zurückzuschreiben verlöre die andere bei jedem Rundgang.
    """
    mehrere = metadata.get("arten")
    if isinstance(mehrere, list) and mehrere:
        return [str(a) for a in mehrere]
    art = metadata.get("art")
    return [str(art)] if art else [""]


def _kantenfelder(
    knotentyp: str, kanten: list[tuple[str, str, dict]], warnungen: list[str]
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Kanten → (Frontmatter-Felder, Abgrenzungszeilen, Fundstellen).

    ``kanten`` ist `(relation, Zielname, metadata)`; der Zielname ist der Dateiname im
    Bündel, denn darüber lösen Wikilinks auf.
    """
    # `is_a` heißt im Frontmatter je nach Typ anders — die Relation ist dieselbe, das
    # Wort der Fachschaft nicht. `_Format.md` kennt `stoffklasse` nur beim Steckbrief.
    oberbegriff_feld = "stoffklasse" if knotentyp == "stoffsteckbrief" else "oberbegriff"
    felder: dict[str, list[str]] = {}
    abgrenzungen: list[str] = []
    fundstellen: list[str] = []

    def dazu(feld: str, ziel: str) -> None:
        felder.setdefault(feld, [])
        if ziel not in felder[feld]:
            felder[feld].append(ziel)

    for relation, ziel, metadata in kanten:
        if relation == "references":
            fundstelle = metadata.get("fundstelle")
            if fundstelle:
                fundstellen.append(str(fundstelle))
            continue
        if not ziel:
            warnungen.append(
                f"Kante `{relation}` zeigt auf einen Knoten außerhalb dieses Fachs — "
                "das Format kann sie nicht benennen"
            )
            continue
        if relation == "is_a":
            dazu(oberbegriff_feld, _wikilink(ziel))
            continue
        if relation == "requires":
            dazu("voraussetzung", _wikilink(ziel))
            continue
        if relation != "related_to":
            warnungen.append(f"Kante `{relation}` → {ziel}: im Format nicht vorgesehen")
            continue
        for art in _arten(metadata):
            if art == "vertiefung":
                dazu("vertieft_in", _wikilink(ziel))
            elif art == "teilchen":
                dazu("teilchen", _wikilink(ziel))
            elif art == "ghs":
                # Steht wörtlich in `metadata.ghs` und wird von dort geschrieben —
                # samt `gilt_fuer`, das an der Kante hängt. Zweimal wäre doppelt.
                continue
            elif art == "abgrenzung":
                hinweis = str(metadata.get("hinweis") or "").strip()
                abgrenzungen.append(
                    f"{_wikilink(ziel)} – {hinweis}" if hinweis else _wikilink(ziel)
                )
            else:
                dazu("verwandt", _wikilink(ziel))
    return felder, abgrenzungen, fundstellen


def schreibe_datei(
    node: ContextNode,
    aliase: list[str],
    kanten: list[tuple[str, str, dict]],
    fach_name: str,
    warnungen: list[str],
) -> str:
    """Einen Knoten als Markdown-Datei im Vault-Format."""
    metadata = dict(node.metadata_ or {})
    knotentyp = node.content_type
    felder, abgrenzungen, fundstellen = _kantenfelder(knotentyp, kanten, warnungen)

    kopf: dict[str, Any] = {
        "id": metadata.get(SEED_ID) or "",
        "knotentyp": knotentyp,
        "titel": node.title,
        "fach": fach_name,
    }
    schema = feld_schema(knotentyp)
    for name in schema:
        # Die Fehlvorstellungen stehen im Textteil — von dort liest der Import sie.
        if name == "fehlvorstellungen":
            continue
        wert = metadata.get(name)
        if wert not in (None, "", [], {}):
            kopf[name] = wert
    if aliase:
        kopf["aliase"] = list(aliase)
    if fundstellen:
        kopf["bildungsplan"] = fundstellen
    for feld in ("oberbegriff", "stoffklasse", "verwandt", "voraussetzung",
                 "vertieft_in", "teilchen"):
        if felder.get(feld):
            kopf[feld] = felder[feld]
    for name in FREIE_METADATEN:
        wert = metadata.get(name)
        if wert in (None, "", [], {}):
            continue
        if name == "illustrationen":
            # ⚠️ **Ohne `svg`.** Der Inhalt liegt als Datei unter `_Abb/` — beides zu
            # schreiben blähte das Frontmatter um Kilobyte auf, die der Import beim
            # Lesen ohnehin verwirft und aus der Datei neu holt.
            kopf[name] = [
                {k: v for k, v in abb.items() if k != "svg"} if isinstance(abb, dict)
                else abb
                for abb in wert
            ]
        else:
            kopf[name] = wert

    verbleibend = set(metadata) - set(kopf) - OHNE_ENTSPRECHUNG - set(schema)
    for name in sorted(verbleibend):
        warnungen.append(
            f"Feld `{name}` steht nicht im Format und fehlt in der Datei — ein erneuter "
            "Import legt es nicht wieder an"
        )

    teile = [
        yaml.safe_dump(
            kopf,
            allow_unicode=True,
            sort_keys=False,
            width=10_000,
            # ⚠️ `None`, nicht `False`: Einfache Listen bleiben in einer Zeile
            # (`aliase: [Oxidierung, Sauerstoffaufnahme]`), verschachtelte brechen um
            # (`illustrationen`). So sieht die Datei aus wie die, die jemand von Hand
            # geschrieben hat — und ein Diff gegen den Vault zeigt Inhalt statt Form.
            default_flow_style=None,
        ).strip()
    ]
    rumpf: list[str] = []
    for name, text in _abschnitte_aus_content(node.content or ""):
        rumpf.append(f"## {name}\n\n{_mit_einbettungen(text)}")
    if abgrenzungen:
        rumpf.append(
            f"## {ABSCHNITT_KANTEN}\n\n"
            + "\n".join(f"- {zeile}" for zeile in abgrenzungen)
        )
    fehlvorstellungen = metadata.get("fehlvorstellungen") or []
    if fehlvorstellungen:
        rumpf.append(
            f"## {ABSCHNITT_METADATA}\n\n"
            + "\n".join(f"- {eintrag}" for eintrag in fehlvorstellungen)
        )
    return "---\n" + teile[0] + "\n---\n\n" + "\n\n".join(rumpf) + "\n"


def pruefe_rundreise(
    dateiname: str, text: str, node: ContextNode, aliase: list[str]
) -> str | None:
    """Liest die geschriebene Datei zurück und vergleicht den Stand. Grund oder ``None``.

    ⚠️ **Das ist der Wächter, der im Betrieb greift.** Der Prüfsatz in `tests/` deckt
    die Fixtures ab; hier stehen Knoten, die nie durch eine Datei gegangen sind — im
    Editor angelegt, mit einer Überschrift im Text oder einer mehrzeiligen
    Fehlvorstellung. Ohne die Prüfung meldete der nächste Import sie als „aktualisiert",
    und niemand wüsste, warum.

    Die Abbildungen bleiben außen vor: Ihr `svg` holt der Import aus `_Abb/`, hier liegt
    nur der Verweis. Verglichen wird deshalb ohne sie.
    """
    try:
        zurueck = lies_datei(dateiname, text)
    except Exception as fehler:            # noqa: BLE001 — jeder Fehler ist derselbe Befund
        return f"nicht wieder lesbar ({fehler})"
    if zurueck is None:
        return "wird beim Wiedereinlesen übergangen"

    def ohne_bilder(daten: dict) -> dict:
        return {k: v for k, v in daten.items() if k != "illustrationen"}

    ist = stand_hash(
        node.title, node.content or "", ohne_bilder(dict(node.metadata_ or {})), aliase
    )
    neu = stand_hash(
        zurueck.titel, zurueck.content, ohne_bilder(dict(zurueck.metadata)),
        zurueck.aliase,
    )
    return None if ist == neu else "ein erneuter Import meldete sie als geändert"


# ── Teil 2: Den Bestand eines Fachs einsammeln ───────────────────────────────

def _dateiname(node: ContextNode, vergeben: set[str]) -> str:
    """Wie die Datei im Bündel heißt — möglichst so wie die, aus der sie kam.

    ⚠️ **`seed_quelle` hat Vorrang vor dem Titel.** Nur so entsteht beim Export der
    Ordner, aus dem importiert wurde; ein aus dem Titel erfundener Name machte aus
    „Oxidation (Sauerstoffaufnahme).md" plötzlich „Oxidation.md" — und damit beim
    nächsten Lauf einen zweiten Knoten, solange keine `id` in der Datei steht.

    Bei Namensgleichheit gewinnt die Kennung als Name: Sie ist je Fach eindeutig und
    **stabil**, während ein angehängtes „(2)" davon abhinge, welcher Knoten zuerst
    drankommt.
    """
    metadata = node.metadata_ or {}
    roh = str(metadata.get(SEED_QUELLE) or node.title or "").strip()
    # `/` zerlegte den Pfad im Bündel, ein führender Unterstrich ließe den Import die
    # Datei übergehen (dort hält er `_Format.md` draußen).
    name = roh.replace("/", "-").lstrip("_").strip()
    if not name or name in vergeben:
        name = str(metadata.get(SEED_ID) or "") or name
    return name


async def _kanten_je_knoten(
    db: AsyncSession, ids: list[Any], namen: dict[Any, str]
) -> dict[Any, list[tuple[str, str, dict]]]:
    """Alle ausgehenden Kanten, das Ziel schon als Dateiname.

    ⚠️ **Auch Kanten, die nicht vom Import stammen.** Wer in der Oberfläche verknüpft
    hat, soll das im Export wiederfinden — sonst wäre der Rückweg löchrig, und genau
    dagegen gibt es ihn (D1). Die Folge steht in der Doku: Nach einem Rundgang gehört
    auch diese Verbindung der Datei.
    """
    if not ids:
        return {}
    zeilen = (await db.execute(
        sa.select(
            ContextEdge.from_node_id, ContextEdge.relation,
            ContextEdge.to_node_id, ContextEdge.metadata_,
        ).where(ContextEdge.from_node_id.in_(ids))
        .order_by(ContextEdge.relation, ContextEdge.id)
    )).all()
    je_knoten: dict[Any, list[tuple[str, str, dict]]] = {}
    for von, relation, nach, metadata in zeilen:
        je_knoten.setdefault(von, []).append(
            (relation, namen.get(nach, ""), dict(metadata or {}))
        )
    return je_knoten


async def exportiere(
    db: AsyncSession, fach: Subject, *, nur: Any = None
) -> tuple[list[Ausgabedatei], Exportbilanz]:
    """Den Fachbegriffsbestand eines Fachs als Bündel — dasselbe Format wie beim Import.

    ``nur`` beschränkt auf **einen** Knoten (Detailansicht „als Markdown"). Die
    Dateinamen der Kantenziele kommen trotzdem aus dem ganzen Fach: Ein Wikilink zeigt
    auf eine Datei, und deren Name hängt nicht davon ab, wie viel gerade exportiert wird.
    """
    bilanz = Exportbilanz()
    knoten = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.subject_id == fach.id,
            ContextNode.content_type.in_(TYPEN),
            ContextNode.status == "active",
        ).order_by(ContextNode.title, ContextNode.id)
    )).scalars().all()

    namen: dict[Any, str] = {}
    vergeben: set[str] = set()
    for node in knoten:
        name = _dateiname(node, vergeben)
        namen[node.id] = name
        vergeben.add(name)

    gewaehlt = [n for n in knoten if nur is None or n.id == nur]
    aliase = await alias_dienst.lade_viele(db, [n.id for n in gewaehlt])
    kanten = await _kanten_je_knoten(db, [n.id for n in gewaehlt], namen)

    dateien: list[Ausgabedatei] = []
    for node in gewaehlt:
        eigene: list[str] = []
        name = namen[node.id]
        text = schreibe_datei(
            node, aliase.get(node.id, []), kanten.get(node.id, []), fach.name, eigene
        )
        grund = pruefe_rundreise(name, text, node, aliase.get(node.id, []))
        if grund:
            eigene.append(grund)
        bilanz.warnungen += [f"{name}: {w}" for w in eigene]
        dateien.append(Ausgabedatei(f"{name}.md", text.encode("utf-8")))
        bilanz.knoten += 1

        for abb in (node.metadata_ or {}).get("illustrationen") or []:
            if not isinstance(abb, dict) or not abb.get("datei") or not abb.get("svg"):
                continue
            pfad = str(abb["datei"]).replace("\\", "/").lstrip("/")
            dateien.append(Ausgabedatei(pfad, str(abb["svg"]).encode("utf-8")))
            bilanz.abbildungen += 1

    return dateien, bilanz


#: Steht in **jedem** Export, auch wenn nichts schiefging.
#:
#: ⚠️ **Der zweite Absatz ist der wichtige.** Gemessen am Chemie-Pilot: 251 Wikilinks
#: zeigen auf Begriffe, die es noch nicht gibt. Die erzeugen bewusst keine Knoten
#: (Entscheidung E3) — also kennt der Speicher sie nicht, und der Export kann sie nicht
#: schreiben. Wer seinen Vault mit einem Export überbügelt, verliert genau die
#: Arbeitsliste, an der die Fachschaft als Nächstes arbeiten wollte.
STANDHINWEIS = """Hinweise zum Export
===================

Diese Datei gehört nicht zum Format; ein erneuter Import übergeht sie.

Der Export ist der Stand des Wissensspeichers, nicht die Datei von vorgestern.
Nicht mitkommen können:

- Verweise auf Begriffe, die es im Speicher noch nicht gibt. Sie sind beim Import
  bewusst zu keinem Knoten geworden und deshalb hier nicht abgebildet.
  ** Wer damit einen gepflegten Vault überschreibt, verliert diese Arbeitsliste. **
- `pruefstatus`: ein Arbeitsstand der Fachschaft, den die Plattform nicht speichert.
- Verweise im Fließtext: Sie wurden beim Lesen zu Klartext.
- Abschnitte unter „Offene Fragen".
"""


def hinweisdatei(bilanz: Exportbilanz) -> Ausgabedatei:
    """Der Beipackzettel im Bündel — **immer**, nicht nur im Fehlerfall.

    Der Unterstrich im Namen ist kein Schmuck: `lies_buendel` übergeht solche Dateien,
    die Hinweise fahren also mit, ohne beim nächsten Import als Knoten aufzuschlagen.

    ⚠️ **Auch ohne Befund.** Was der Export nicht mitbringen *kann*, hängt nicht davon
    ab, ob diesmal etwas aufgefallen ist — und es ist die eine Sache, die jemand wissen
    muss, bevor er damit seinen Vault überschreibt.
    """
    text = STANDHINWEIS
    if bilanz.warnungen:
        text += "\nZu einzelnen Einträgen:\n\n" + "\n".join(
            f"- {zeile}" for zeile in bilanz.warnungen
        ) + "\n"
    return Ausgabedatei(HINWEISE, text.encode("utf-8"))


def als_zip(dateien: list[Ausgabedatei]) -> bytes:
    """Das Bündel als Zip — flach, mit `_Abb/` darin, wie der Import es erwartet."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        for datei in dateien:
            archiv.writestr(datei.pfad, datei.inhalt)
    return puffer.getvalue()
