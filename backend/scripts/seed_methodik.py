#!/usr/bin/env python3
"""Grundvokabular für Methoden und Sozialformen in den Wissensgraph einspielen (Upsert).

Schulweit (`read_scope`/`write_scope` = `school`), fachübergreifend (`subject_id` bleibt
leer). Fachspezifische Methoden legen Fachschaften selbst an — die Taxonomie führt für
`methode` deshalb `write_scope: subject` als Vorgabewert; die hier geseedeten Einträge
gehören keiner Fachschaft und sind die Ausnahme davon (ADR-019, Zielbild K3).

    python scripts/seed_methodik.py
    python scripts/seed_methodik.py --dry-run
    python scripts/seed_methodik.py --ueberschreiben

**Der Seed füllt Lücken, er überschreibt nichts.** Nach dem ersten Lauf gehören die
Knoten der Schule: `write_scope = school` heißt, jede Lehrkraft darf sie über die
Sammlung bearbeiten. Ein zweiter Lauf, der Text und Aliase zurücksetzt, nähme diese
Arbeit weg — lautlos, denn niemand führt Buch darüber. Wer das ausdrücklich will, nimmt
`--ueberschreiben`.

Anders die **Scopes**: Sie sind kein Redaktionsergebnis, sondern das Zielbild aus
ADR-019, und werden bei jedem Lauf nachgezogen.

⚠️ **Einträge ohne Kurzbeschreibung werden als unvollständig markiert**
(`metadata.unvollstaendig`, dieselbe Markierung wie beim Verknüpfen-Dialog, UI-Notiz A8).
Der Grund ist nicht Ordnungsliebe: Bei `methode` bildet sich der Vektor aus Titel,
Aliasen und dem **Ablaufsatz** (`embedding_input` in `taxonomy.yaml`; ohne ihn aus der
Kurzbeschreibung). Fehlt beides, besteht er aus dem Namen — eine unscharfe Titelsuche im
Vektorraum, die die thematische Suche nur verwässert. `traegt_substanz()` weist genau
solche Knoten ab, und die Markierung sorgt dafür, dass ein bereits gebildeter Vektor auch
wieder verschwindet. Sobald die Beschreibung nachgetragen ist, fällt die Markierung weg.

Geänderte Knoten verlieren ihr Embedding (`embedding = NULL`) und bekommen beim nächsten
Backfill ein neues — der Seed selbst braucht dafür keinen laufenden LiteLLM-Proxy:

    python scripts/embedding_backfill.py --content-type methode
"""
import argparse
import asyncio
import logging
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.context.metadata import STUB_MARKIERUNG
from app.context.taxonomy import (
    CONTENT_TYPE_TO_CATEGORY,
    EMBEDDING_CONTENT_TYPES,
    content_ist_pflicht,
)
from app.db.models import ContextNode

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Das Zielbild aus ADR-019 K3 — kein Redaktionsergebnis, sondern eine Systementscheidung.
ZIEL_SCOPES: dict[str, Any] = {
    "read_scope": "school",
    "write_scope": "school",
    "read_scope_group_id": None,
    "write_scope_group_id": None,
}


@dataclass(frozen=True)
class Baustein:
    """Ein Vokabeleintrag: Titel, andere Bezeichnungen, Kurzbeschreibung, Ablaufsatz.

    Die Aliase tragen den Vektor mit und sind zugleich der lexikalische Weg: Wer
    „Ich-Du-Wir" sucht, soll „Think-Pair-Share" finden. Was `content` von `ablauf`
    unterscheidet, steht am Grundvokabular weiter unten.
    """

    titel: str
    aliase: tuple[str, ...] | str = ()
    content: str = ""
    ablauf: str = ""

    def __post_init__(self) -> None:
        # ⚠️ `("Concept Map")` ist in Python **kein** Tupel, sondern ein String — das
        # Komma fehlt. Ohne diese Zeile wird er Zeichen für Zeichen durchlaufen und
        # landet als `["C", "o", "n", …]` in den Aliasen, in der Datenbank und im
        # Vektor. Nichts daran schlägt fehl; sichtbar wird es erst in der Sammlung.
        # Am 04.09.2026 ist genau das zweimal passiert.
        if isinstance(self.aliase, str):
            object.__setattr__(self, "aliase", (self.aliase,))
        else:
            object.__setattr__(self, "aliase", tuple(self.aliase))

    @property
    def text(self) -> str:
        return textwrap.dedent(self.content).strip()

    @property
    def ablaufsatz(self) -> str:
        return textwrap.dedent(self.ablauf).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Das Grundvokabular. Zwei Textfelder mit verschiedenen Aufgaben:
#
# **`content` — die Kurzbeschreibung.** Was eine Lehrkraft liest: Ablauf *und* Hinweise
# zum Einsatz, Varianten, Fallstricke. Darf wachsen.
#
# **`ablauf` — ein Satz, und nur der Ablauf.** Er allein bildet den Vektor
# (`embedding_input` in `taxonomy.yaml`) und beantwortet die Prüfsatz-Fälle des
# Abschnitts S8 in `config/search_eval.yaml` („Erst allein nachdenken, dann zu zweit
# austauschen …"). Zwei Regeln, beide gemessen:
#
# 1. **Kein Beiwerk.** Am 04.09.2026 lag der Galeriegang auf Rang 1, bis ein
#    Variantensatz dazukam („ein Gruppenmitglied bleibt stehen und erklärt es den
#    Besuchern"). Danach Rang 7, verdrängt von den Operatoren *präsentieren*,
#    *demonstrieren*, *erbringen*. Was den Eintrag für Lesende reicher macht, macht
#    seinen Vektor unschärfer — deshalb die Trennung.
# 2. **Abgrenzen, aber positiv.** „Anders als beim Lernzirkel gibt es keine feste
#    Reihenfolge" trägt den fremden Namen und den verneinten Begriff in die Eingabe und
#    zieht den Knoten an den heran, von dem er sich abgrenzen soll — Verneinungen kennt
#    ein Embedding nicht. Mit diesem Satz stand der **Lernzirkel** vor Stationenlernen
#    (0,733 zu 0,701); positiv formuliert kehrt sich die Reihenfolge um.
#
# Wo zwei Methoden einander ähneln — Stationenlernen, Lernzirkel und Lerntheke;
# Kugellager und Fishbowl; Rollen- und Planspiel —, muss der Ablaufsatz den Unterschied
# tragen. Fehlt er, zählt `content` wie bisher; ein leeres Feld macht nichts kaputt.
#
# `sozialform` hat kein Embedding und deshalb auch kein `ablauf`-Feld.
# ─────────────────────────────────────────────────────────────────────────────

SOZIALFORMEN: list[Baustein] = [
    Baustein(
        "Plenum",
        ("Frontalunterricht", "Unterrichtsgespräch", "Lehrgespräch"),
        content=(
            "Die ganze Klasse arbeitet gemeinsam an einer Sache, geführt von der "
            "Lehrkraft. Alle hören dasselbe und sprechen nacheinander. Typisch für Einstieg, Sicherung und gemeinsame Auswertung: Ergebnisse werden vorgestellt, verglichen, ggf. diskutiert und festgehalten."
        ),
    ),
    Baustein(
        "Einzelarbeit",
        ("Stillarbeit",),
        content=(
            "Jede und jeder arbeitet für sich, still und im eigenen Tempo. Sinnvoll vor allem zur Erarbeitung von Texten, Übungen und anderen Aufgaben, bei denen die eigenständige Denkleistung des Einzelnen im Vordergrund steht."
        ),
    ),
    Baustein(
        "Partnerarbeit",
        (),
        content=(
            "Zwei bearbeiten eine Aufgabe gemeinsam. Weil man dem Gegenüber erklären muss, was man meint, treten Lücken hervor, die in der Einzelarbeit unbemerkt bleiben. Zugleich kommt jede Person oft zu Wort — mehr als in jeder größeren Runde. Gut geeignet für die Erarbeitung von Texten, Übungen und komplexeren Aufgaben, Problemlöseaufgaben und Aufgaben, die kooperatives Vorgehen erfordern."
        ),
    ),
    Baustein(
        "Gruppenarbeit",
        ("Teamarbeit",),
        content=(
            "Drei bis fünf Lernende bearbeiten zusammen eine Aufgabe und stellen ihr Ergebnis anschließend vor. Ideal für Aufgaben, die kooperativ gelöst werden müssen, Projektarbeiten oder Aufgaben, die arbeitsteilig gelöst werden können. Eine klare Absprache über die Rollen und Verantwortlichkeiten sowie die Zusammenführung der Ergebnisse ist wichtig."
        ),
    ),
]

METHODEN: list[Baustein] = [
    Baustein(
        "Think-Pair-Share",
        ("Ich-Du-Wir", "Prinzip der wachsenden Gruppe"),
        content=(
            "Drei Schritte in fester Reihenfolge: Zuerst denkt jede Person allein über die Frage nach und hält etwas fest. Dann tauschen sich zwei darüber aus und einigen sich auf ein gemeinsames Ergebnis. Zuletzt wird es in der ganzen Klasse diskutiert. Der erste Schritt sorgt dafür, dass niemand mit leeren Händen kommt, der zweite dafür, dass jede Person einmal die Frage diskutiert hat."
        ),
        ablauf=(
            "Zuerst denkt jede Person allein über die Frage nach, dann tauschen sich zwei darüber "
            "aus, zuletzt wird das Ergebnis in der ganzen Klasse besprochen."
        ),
    ),
    Baustein(
        "Placemat",
        (),
        content=(
            "Ein großes Blatt liegt in der Mitte der Gruppe, aufgeteilt in ein Randfeld je Person und ein gemeinsames Feld in der Mitte. Zuerst schreibt jede Person still in ihr eigenes Randfeld. Dann werden die Beiträge reihum gelesen, und in die Mitte kommt nur, worauf sich die Gruppe einigt."
        ),
        ablauf=(
            "Ein großes Blatt liegt in der Mitte der Gruppe: Jede Person schreibt still in ihr "
            "eigenes Randfeld, danach kommt in die Mitte, worauf sich die Gruppe einigt."
        ),
    ),
    Baustein(
        "Gruppenpuzzle",
        ("Jigsaw", "Expertenpuzzle"),
        content=(
            "Der Stoff wird in Teilthemen zerlegt. Zuerst arbeitet sich jede „Expertengruppe“ in genau ein Teilthema ein. Dann werden die Gruppen neu gemischt, so dass in jeder neuen Gruppe zu jedem Teilthema eine Person sitzt und es den anderen erklärt. Idealerweise erstellt jede Gruppe eine gemeinsame Sicherung des Gesamtthemas."
        ),
        ablauf=(
            "Jede Gruppe arbeitet sich in ein Teilthema ein; danach werden die Gruppen so neu "
            "gemischt, dass jede Person ihr Teilthema den anderen erklärt."
        ),
    ),
    Baustein(
        "Stationenlernen",
        ("Stationenarbeit",),
        content=(
            "An mehreren Plätzen im Raum liegen Aufgaben zu einem Thema bereit. Die Lernenden wandern zwischen ihnen und suchen sich selbst aus, womit sie anfangen und wie lange sie an einer Station bleiben; ein Laufzettel hält fest, was erledigt ist. Pflicht- und Wahlstationen lassen sich mischen. Eine große Herausforderung ist das Zeitmanagement durch die Lernenden, sodass am Ende der vorgesehenen Zeit alle Pflichtstationen bearbeitet sind."
        ),
        ablauf=(
            "An mehreren Plätzen im Raum liegen Aufgaben, zwischen denen die Lernenden "
            "wandern; Reihenfolge und Verweildauer bestimmen sie selbst."
        ),
    ),
    Baustein(
        "Lernzirkel",
        (),
        content=(
            "Aufgaben liegen an mehreren Plätzen aus, und alle Gruppen sind gleichzeitig unterwegs: Jede beginnt an einer anderen Station und rückt nach einer abgesprochenen Zeit gemeinsam mit den übrigen weiter."
        ),
        ablauf=(
            "Aufgaben liegen an mehreren Plätzen aus; jede Gruppe beginnt an einer anderen "
            "Station und rückt nach einer abgesprochenen Zeit gemeinsam mit den übrigen weiter."
        ),
    ),
    Baustein(
        "Kugellager",
        ("Innen-Außen-Kreis",),
        content=(
            "Die Klasse bildet zwei Kreise, einen inneren und einen äußeren, mit Blick zueinander. Je zwei Gegenüberstehende tauschen sich kurz zu einer Frage aus. Dann rückt ein Kreis um einen Platz weiter, und es geht mit einem neuen Gegenüber weiter. In kurzer Zeit spricht so jede Person mit vielen anderen — alle reden gleichzeitig, niemand schaut nur zu. Ziel ist nie, dass alle mit allen gesprochen haben."
        ),
        ablauf=(
            "Zwei Kreise stehen sich gegenüber; je zwei Gegenüberstehende sprechen kurz "
            "miteinander, dann rückt ein Kreis weiter und alle haben ein neues Gegenüber."
        ),
    ),
    Baustein(
        "Galeriegang",
        ("Gallery Walk", "Museumsrundgang"),
        content=(
            "Die Ergebnisse — Plakate, Skizzen, Texte — hängen im Raum aus. Die Klasse geht herum, sieht sie sich an und gibt Rückmeldung, oft schriftlich auf Klebezetteln. Statt einer Reihe von Vorträgen entsteht ein Rundgang, bei dem alle gleichzeitig in Bewegung sind. Als Variante bleibt ein Gruppenmitglied beim Plakat der Gruppe stehen und erklärt es den „Besuchern“."
        ),
        ablauf=(
            "Die Ergebnisse hängen im Raum aus, und die Klasse geht herum, sieht sie sich an und "
            "gibt Rückmeldung."
        ),
    ),
    Baustein(
        "Brainstorming",
        (),
        content=(
            "In kurzer Zeit werden möglichst viele Einfälle zu einer Frage gesammelt, ohne sie zu bewerten. Kritik und Auswahl kommen erst danach. Geeignet als Einstieg, um Vorwissen und erste Vermutungen sichtbar zu machen. Die Einfälle werden entweder auf Zettel geschrieben und an die Tafel gehängt oder auf eine Tafel direkt geschrieben."
        ),
        ablauf=(
            "In kurzer Zeit werden möglichst viele Einfälle zu einer Frage gesammelt, ohne sie "
            "dabei zu bewerten."
        ),
    ),
    Baustein(
        "Mindmap",
        ("Concept Map"),
        content=(
            "Das Thema steht in der Mitte, von ihm gehen Äste zu Teilaspekten oder verwandten Themen aus, die sich weiter verzweigen. Die Darstellung zeigt Zusammenhänge, die eine Liste verbirgt, und lässt sich jederzeit ergänzen. Nützlich zum Ordnen von Gesammeltem, zum Strukturieren von Gelerntem und zum Wiederholen eines Themas."
        ),
        ablauf=(
            "Das Thema steht in der Mitte, von ihm gehen Äste zu Teilaspekten aus, die sich "
            "weiter verzweigen."
        ),
    ),
    Baustein(
        "Fishbowl",
        ("Innenkreis-Außenkreis-Diskussion",),
        content=(
            "Eine kleine Gruppe diskutiert in der Mitte, die übrigen sitzen außen herum und beobachten, ohne einzugreifen. Ein freier Stuhl im Innenkreis erlaubt es, dazuzukommen und nach dem Beitrag wieder zu gehen. So bleibt die Diskussion überschaubar, und trotzdem kann sich die ganze Klasse beteiligen."
        ),
        ablauf=(
            "Eine kleine Gruppe diskutiert in der Mitte, während die übrigen außen herum sitzen "
            "und beobachten."
        ),
    ),
    Baustein(
        "Fragend-entwickelndes Gespräch",
        (),
        content=(
            "Die Lehrkraft führt mit einer Kette von Fragen auf eine Einsicht hin; die Klasse antwortet Schritt für Schritt. Geeignet, um an Vorwissen anzuknüpfen und einen Gedankengang gemeinsam aufzubauen. Der Verlauf liegt dabei weitgehend bei der Lehrkraft — die Klasse geht einen Weg mit, den sie nicht selbst gewählt hat."
        ),
        ablauf=(
            "Die Lehrkraft führt mit einer Kette von Fragen auf eine Einsicht hin, und die Klasse "
            "antwortet Schritt für Schritt."
        ),
    ),
    Baustein(
        "Lerntempoduett",
        (),
        content=(
            "Alle bearbeiten dieselbe Aufgabe zunächst allein. Wer fertig ist, meldet sich und arbeitet mit der nächsten fertigen Person weiter — es finden sich also Paare mit ähnlichem Arbeitstempo. Wartezeiten entfallen, und niemand wird zum Weitermachen gedrängt."
        ),
        ablauf=(
            "Alle bearbeiten dieselbe Aufgabe zunächst allein; wer fertig ist, arbeitet mit der "
            "nächsten fertigen Person weiter."
        ),
    ),
    Baustein(
        "Lerntheke",
        (),
        content=(
            "An einer Stelle im Raum liegen Aufgaben und Hilfen unterschiedlicher Schwierigkeit aus, meist gestuft. Die Lernenden holen sich von dort, was sie brauchen, arbeiten an ihrem Sitzplatz und legen es zurück. Was zum eigenen Stand passt, entscheidet jede Person selbst. Besonders geeignet für selbstdifferenzierende Übungsphasen am Ende einer Unterrichtseinheit."
        ),
        ablauf=(
            "An einer Stelle im Raum liegen gestufte Aufgaben und Hilfen aus, von denen sich die "
            "Lernenden holen, was sie brauchen, und am Sitzplatz bearbeiten."
        ),
    ),
    Baustein(
        "Debatte",
        ("Pro-Contra-Debatte", "Streitgespräch"),
        content=(
            "Zu einer strittigen Frage vertreten zwei Seiten gegensätzliche Positionen nach festen Regeln: Redezeit, Reihenfolge und Rollen sind vorher vereinbart. Die zugeteilte Seite muss nicht die eigene Meinung sein — gerade das schult das Abwägen von Argumenten. Eine solche Debatte kann sowohl als Partner- oder Gruppenarbeit gestaltet werden, als auch als „Podiumsdiskussion“ mit der ganzen Klasse."
        ),
        ablauf=(
            "Zwei Seiten vertreten zu einer strittigen Frage gegensätzliche Positionen nach "
            "vorher vereinbarten Regeln für Redezeit, Reihenfolge und Rollen."
        ),
    ),
    Baustein(
        "Rollenspiel",
        (),
        content=(
            "Die Lernenden übernehmen Rollen in einer vorgegebenen Situation und handeln sie miteinander aus. Anschließend wird ausgewertet, was im Spiel geschehen ist und woran es lag. Die Auswertung ist oft der eigentliche Lernschritt, nicht die Aufführung."
        ),
        ablauf=(
            "Die Lernenden übernehmen Rollen in einer vorgegebenen Situation, handeln sie "
            "miteinander aus und werten anschließend aus, was geschehen ist."
        ),
    ),
    Baustein(
        "Planspiel",
        ("Simulation"),
        content=(
            "Die Lernenden übernehmen Rollen in einer vorgegebenen Situation und agieren entsprechend. Die Situation ist oft komplex und die Folgen der Handlungen nicht vorhersehbar. Die Rollen und ihre Interessen müssen entsprechend klar definiert sein. Geeignet z. B. zur Simulation von Konflikten, Wirtschaftsprozessen oder politischen Entscheidungen. "
        ),
        ablauf=(
            "Die Lernenden übernehmen klar umrissene Rollen in einer komplexen Situation und "
            "handeln darin, ohne dass die Folgen ihrer Entscheidungen vorhersehbar sind."
        ),
    ),
]

BESTAND: list[tuple[str, list[Baustein]]] = [
    ("sozialform", SOZIALFORMEN),
    ("methode", METHODEN),
]


@dataclass
class Aenderung:
    """Was ein Lauf an einem Knoten täte — ohne Datenbank entschieden und deshalb prüfbar."""

    felder: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    geaendert: list[str] = field(default_factory=list)
    behalten: list[str] = field(default_factory=list)
    embedding_verwerfen: bool = False

    @property
    def wirkt(self) -> bool:
        return bool(self.geaendert) or self.embedding_verwerfen


def plane_aenderung(
    ist: dict[str, Any],
    baustein: Baustein,
    content_type: str,
    *,
    ueberschreiben: bool = False,
) -> Aenderung:
    """Vergleicht Ist und Soll und beschreibt den Unterschied.

    ``ist`` ist der Zustand des vorhandenen Knotens (leer für einen neuen): ``content``,
    ``ablauf``, ``aliase``, die vier Scope-Felder und ``embedding_vorhanden``.

    Eine Regel für Anlegen und Aktualisieren — ein neuer Knoten ist hier nur der Fall,
    in dem alles fehlt. Zwei getrennte Wege wären zwei Gelegenheiten, auseinanderzulaufen.
    """
    aenderung = Aenderung(metadata=dict(ist.get("metadata") or {}))

    # ── Text ──────────────────────────────────────────────────────────────────
    ist_text = (ist.get("content") or "").strip()
    soll_text = baustein.text
    if soll_text and soll_text != ist_text:
        if ist_text and not ueberschreiben:
            aenderung.behalten.append("Text")
        else:
            aenderung.felder["content"] = soll_text
            aenderung.geaendert.append("Text")
            aenderung.embedding_verwerfen = True

    # ── Ablaufsatz ────────────────────────────────────────────────────────────
    # Dieselbe Regel wie beim Text — und aus demselben Grund getrennt von ihm: Der
    # Ablaufsatz ist der Vektor, die Kurzbeschreibung die Handreichung.
    ist_ablauf = (ist.get("ablauf") or "").strip()
    soll_ablauf = baustein.ablaufsatz
    if soll_ablauf and soll_ablauf != ist_ablauf:
        if ist_ablauf and not ueberschreiben:
            aenderung.behalten.append("Ablaufsatz")
        else:
            aenderung.metadata["ablauf"] = soll_ablauf
            aenderung.geaendert.append("Ablaufsatz")
            aenderung.embedding_verwerfen = True

    # ── Aliase ────────────────────────────────────────────────────────────────
    ist_aliase = list(ist.get("aliase") or [])
    soll_aliase = list(baustein.aliase)
    if soll_aliase != ist_aliase:
        if ist_aliase and not ueberschreiben:
            aenderung.behalten.append("Aliase")
        else:
            aenderung.metadata["aliase"] = soll_aliase
            aenderung.geaendert.append("Aliase")
            aenderung.embedding_verwerfen = True

    # ── Unvollständig-Markierung ──────────────────────────────────────────────
    # Maßgeblich ist der Text *nach* dieser Änderung, nicht der gelieferte: Ein Eintrag,
    # dessen Beschreibung die Schule geschrieben hat, ist vollständig, auch wenn der Seed
    # keinen Text mitbringt.
    text_danach = aenderung.felder.get("content", ist_text)
    war_stub = bool(aenderung.metadata.get(STUB_MARKIERUNG))
    ist_stub_jetzt = content_ist_pflicht(content_type) and not text_danach
    if ist_stub_jetzt and not war_stub:
        aenderung.metadata[STUB_MARKIERUNG] = True
        aenderung.geaendert.append("als unvollständig markiert")
        aenderung.embedding_verwerfen = True
    elif war_stub and not ist_stub_jetzt:
        aenderung.metadata.pop(STUB_MARKIERUNG, None)
        aenderung.geaendert.append("Markierung „unvollständig“ entfernt")

    # ── Scopes ────────────────────────────────────────────────────────────────
    for name, soll in ZIEL_SCOPES.items():
        if name in ist and ist[name] == soll:
            continue
        aenderung.felder[name] = soll
        if name in ist:
            aenderung.geaendert.append(name)

    if aenderung.metadata != (ist.get("metadata") or {}):
        aenderung.felder["metadata_"] = aenderung.metadata

    # Ein Vektor, den es gar nicht gibt, ist nichts zu verwerfen — und ein Typ ohne
    # Embedding (`sozialform`) hat nie einen.
    aenderung.embedding_verwerfen = (
        aenderung.embedding_verwerfen
        and content_type in EMBEDDING_CONTENT_TYPES
        and bool(ist.get("embedding_vorhanden"))
    )
    return aenderung


def _ist_zustand(node: ContextNode) -> dict[str, Any]:
    metadata = dict(node.metadata_ or {})
    return {
        "content": node.content,
        "ablauf": metadata.get("ablauf") or "",
        "aliase": list(metadata.get("aliase") or []),
        "metadata": metadata,
        "read_scope": node.read_scope,
        "write_scope": node.write_scope,
        "read_scope_group_id": node.read_scope_group_id,
        "write_scope_group_id": node.write_scope_group_id,
        "embedding_vorhanden": node.embedding is not None,
    }


@dataclass
class Bilanz:
    neu: int = 0
    aktualisiert: int = 0
    unveraendert: int = 0
    neu_einzubetten: int = 0
    behalten: list[str] = field(default_factory=list)
    ohne_text: list[str] = field(default_factory=list)


async def _upsert(
    db: AsyncSession,
    content_type: str,
    baustein: Baustein,
    bilanz: Bilanz,
    *,
    ueberschreiben: bool,
) -> None:
    vorhanden = (
        await db.execute(
            select(ContextNode).where(
                ContextNode.content_type == content_type,
                ContextNode.title == baustein.titel,
            )
        )
    ).scalar_one_or_none()

    ist = _ist_zustand(vorhanden) if vorhanden else {}
    aenderung = plane_aenderung(ist, baustein, content_type, ueberschreiben=ueberschreiben)

    if aenderung.behalten:
        bilanz.behalten.append(
            f"{baustein.titel}: {', '.join(aenderung.behalten)} aus der Schule behalten"
        )
    if content_ist_pflicht(content_type) and not aenderung.felder.get(
        "content", (ist.get("content") or "").strip()
    ):
        bilanz.ohne_text.append(baustein.titel)

    if vorhanden is None:
        felder = {k: v for k, v in aenderung.felder.items() if k != "metadata_"}
        db.add(
            ContextNode(
                category=CONTENT_TYPE_TO_CATEGORY[content_type],
                content_type=content_type,
                title=baustein.titel,
                status="active",
                metadata_=aenderung.metadata,
                **felder,
            )
        )
        bilanz.neu += 1
        return

    if not aenderung.wirkt:
        bilanz.unveraendert += 1
        return

    for name, wert in aenderung.felder.items():
        setattr(vorhanden, name, wert)
    if aenderung.embedding_verwerfen:
        vorhanden.embedding = None
        bilanz.neu_einzubetten += 1
    bilanz.aktualisiert += 1
    logger.info("  %-12s %-35s %s", content_type, baustein.titel, ", ".join(aenderung.geaendert))


async def seed(*, dry_run: bool = False, ueberschreiben: bool = False) -> Bilanz:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    bilanz = Bilanz()
    async with session_factory() as db:
        for content_type, eintraege in BESTAND:
            for baustein in eintraege:
                await _upsert(
                    db, content_type, baustein, bilanz, ueberschreiben=ueberschreiben
                )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    await engine.dispose()
    return bilanz


def _berichte(bilanz: Bilanz, *, dry_run: bool) -> None:
    logger.info(
        "Methodik-Seed%s: %d neu, %d aktualisiert, %d unverändert.",
        " (Probelauf, nichts geschrieben)" if dry_run else "",
        bilanz.neu,
        bilanz.aktualisiert,
        bilanz.unveraendert,
    )
    for zeile in bilanz.behalten:
        logger.info("Nicht überschrieben — %s (mit --ueberschreiben erzwingen).", zeile)
    if bilanz.ohne_text:
        logger.warning(
            "%d Einträge ohne Kurzbeschreibung, als unvollständig markiert und ohne "
            "Vektor: %s",
            len(bilanz.ohne_text),
            ", ".join(bilanz.ohne_text),
        )
    if bilanz.neu_einzubetten:
        logger.info(
            "%d Vektoren verworfen — ihre Eingabe hat sich geändert.",
            bilanz.neu_einzubetten,
        )
    if bilanz.neu_einzubetten or bilanz.neu:
        logger.info(
            "Nächster Schritt: python scripts/embedding_backfill.py --content-type methode"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grundvokabular Methoden/Sozialformen einspielen"
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen, nichts schreiben")
    parser.add_argument(
        "--ueberschreiben",
        action="store_true",
        help="Auch Text und Aliase ersetzen, die in der Schule geändert wurden",
    )
    args = parser.parse_args()

    bilanz = asyncio.run(seed(dry_run=args.dry_run, ueberschreiben=args.ueberschreiben))
    _berichte(bilanz, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
