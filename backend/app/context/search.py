"""Die Suchschicht des Kontextspeichers (ADR-017).

Eine Stelle für alle Aufrufer: Chat-Werkzeug, Suchknopf, ``@``-Shortcode, später
Suchseite und Anker-Assistenten. Bis 08/2026 lag die Suche in ``app/chat/router.py``
und ein zweiter, ungeprüfter Weg in ``app/context/retrieval.py``; jede Verbesserung war
damit doppelt anzubringen, und einer der beiden blieb regelmäßig zurück.

**Zwei Verfahren, zwei Abschnitte.** Eine Anfrage kann einen Baustein *benennen*
(„Operator nennen") oder ein *Thema* umreißen („Wie berechnet man den Flächeninhalt
eines Kreises?"). Beide Fragen brauchen verschiedene Verfahren, und bis 09/2026 mussten
sie sich eine einzige Trefferliste mit einem einzigen Limit teilen: Wer nach einem Namen
suchte, dessen Nachschlage-Treffer verdrängten die thematischen. Jetzt laufen beide
Verfahren immer, und jeder Abschnitt des Umschlags hat sein eigenes Budget. Die
Aufzählung („alle, die …") kommt als dritter Abschnitt hinzu (AP3).

**Vollständigkeit ist eine Angabe, keine Vermutung.** Die Identifikation weiß, wie viele
Namensträger es gibt, und sagt es auch, wenn sie nur einen Teil liefert. Die thematische
Auswahl weiß es prinzipiell nicht — sie ist deshalb **nie** vollständig und trägt keine
Gesamtzahl. Aussagen darüber, ob es etwas gibt, stützen sich nur auf die Identifikation
und die Aufzählung, nie auf thematische Nähe.

📖 **Feintuning:** Welche Zahlen sich verstellen lassen, was sie bewirken und wie man
misst, ob eine Änderung etwas verbessert hat, steht in ``docs/dev/kontextsuche.md``.
Jede Konstante hier ist gemessen; wer eine ändert, misst neu
(``python scripts/search_eval.py``).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.editions import aktive_bp_version
from app.context.embedding import generate_embedding
from app.context.filters import TITEL_NORMALISIERT as _TITEL_NORMALISIERT
from app.context.filters import Knotenfilter, wende_an
from app.context.lookup import nachschlage_begriff, normalisiere_titel
from app.context.schemas import anzeige_felder
from app.context.taxonomy import rollen_typ_bonus
from app.context.visibility import read_scope_clause
from app.db.models import ContextEdge, ContextNode, Subject

logger = logging.getLogger(__name__)


# ── Profil: wer sucht, mit welchem Budget ────────────────────────────────────


@dataclass(frozen=True)
class Suchprofil:
    """Was eine Oberfläche von der Suche braucht — statt eines eigenen Suchwegs.

    Die Budgets gelten **je Abschnitt**. Absichtlich getrennt: Ein gemeinsames Limit
    hieße, dass der eine Abschnitt den anderen verdrängt, und genau das war das Problem.
    Im ungünstigsten Fall liefert eine Anfrage also die Summe beider Budgets — bei einer
    Nachschlage-Anfrage mit vielen Gleichnamigen. Der Regelfall bleibt unverändert: Bei
    einer thematischen Anfrage ist die Identifikation leer.
    """

    pseudonym: str
    rollen: Sequence[str] = ()
    # Fach der Konversation, falls bekannt. Treffer daraus werden vorgezogen, nicht
    # gefiltert (siehe `_FACHBONUS`).
    subject_id: int | None = None
    identifikation: int = 8
    thematisch: int = 8
    # Die Aufzählung darf großzügiger sein: Sie beantwortet „alle, die …", und eine
    # Antwort mit acht von vierundzwanzig hilft dort niemandem. Die Zählung selbst ist
    # ohnehin vollständig, unabhängig davon, wie viele Treffer mitgeliefert werden.
    aufzaehlung: int = 50
    # Anker eines Assistenten (`retrieval_scope`). Sind sie gesetzt, sucht die
    # thematische Auswahl **nur** im Teilgraphen darunter — der frühere zweite Suchweg
    # ist damit eine Profilvariante und kein eigener Code mehr.
    anchor_ids: tuple[UUID, ...] = ()
    # Jahrgangsstufe der/des Fragenden, falls ableitbar. Entscheidet, welche
    # Bildungsplan-Fassung gilt, solange eine neue Edition nach oben wächst.
    grade: int | None = None
    # Rohe Metadaten an den Treffern (Breadcrumb, `afb`, `aliase`). Standardmäßig aus:
    # Sie kosten im Modellkontext Platz, den Import-Interna nicht wert sind.
    mit_metadaten: bool = False


# ── Ergebnisumschlag ─────────────────────────────────────────────────────────


@dataclass
class Gruppe:
    """„Mathematik: 3" — eine Zeile der Gruppierung einer Aufzählung.

    Gezählt wird über **alle** Treffer, nicht nur die mitgelieferten: Die Frage „in
    welchen Fächern gibt es das?" ist eine Frage nach dem Bestand, nicht nach dem
    Ausschnitt, der gerade ins Budget passte.
    """

    name: str
    anzahl: int


@dataclass
class Abschnitt:
    """Ein beschrifteter Teil des Ergebnisses samt Auskunft über seine Vollständigkeit.

    ``gesamt`` ist die Anzahl **aller** passenden Knoten, soweit bestimmbar — bei
    Identifikation und Aufzählung eine echte Zahl, bei der thematischen Auswahl
    ``None``: Dort gibt es keine Gesamtmenge, nur eine Rangfolge nach Ähnlichkeit.
    """

    treffer: list[dict] = field(default_factory=list)
    gesamt: int | None = None
    vollstaendig: bool = False
    gruppen: list[Gruppe] | None = None
    # Was dieser Abschnitt über sich selbst sagen muss — etwa dass die Zählung an eine
    # Obergrenze gestoßen ist. Nie stumm kürzen.
    hinweis: str | None = None

    @property
    def geliefert(self) -> int:
        return len(self.treffer)


@dataclass
class Suchergebnis:
    """Der Ergebnisumschlag: getrennte Abschnitte statt einer vermischten Liste."""

    identifikation: Abschnitt = field(default_factory=Abschnitt)
    thematisch: Abschnitt = field(default_factory=Abschnitt)
    # Erst mit AP3 belegt; ``None`` heißt „nicht als Filterabfrage aufgerufen".
    aufzaehlung: Abschnitt | None = None
    hinweise: list[str] = field(default_factory=list)


# ── Fachbonus ────────────────────────────────────────────────────────────────

# Wie viel Vorsprung ein Treffer aus dem Fach der Konversation bekommt — gerechnet in
# Kosinus-Distanz, also derselben Einheit wie die Ähnlichkeit selbst.
#
# **0,05 ist gemessen, nicht geschätzt** (Prüfsatz, 30.08.2026). Zur Einordnung: Innerhalb
# einer Zehnertrefferliste liegen zwischen Platz 1 und Platz 10 im Median 0,063. Der Bonus
# sortiert also innerhalb dessen, was ohnehin zur Auswahl stand — er holt nichts Fernes
# heran.
#
#   Bonus   richtiges Fach oben        fachfremder Treffer bleibt
#           (15 Fälle im Fach-Chat)    (3 Gegenfälle)
#   0,00              11/15                     3/3
#   0,03              13/15                     3/3
#   0,05              15/15                     3/3     ← gewählt
#   0,08              15/15                     2/3
#   0,15              15/15                     0/3
#
# Nach oben begrenzt ihn der Gegenfall: Wer im Physik-Chat nach dem Satz des Pythagoras
# fragt, soll die Mathematik-Kompetenz bekommen. Ab 0,08 verdrängt das Fach der
# Konversation genau solche Treffer — deshalb der Abstand zur Kippgrenze.
_FACHBONUS = 0.05


# ── Trefferform ──────────────────────────────────────────────────────────────


def _treffer(row, *, mit_metadaten: bool = False) -> dict:
    """Eine Trefferzeile in die Form bringen, die Aufrufer und Modell erwarten.

    Gemeinsam für alle Verfahren — liefen sie auseinander, trüge dieselbe Trefferliste
    je nach Abschnitt unterschiedliche Felder.

    ``mit_metadaten`` hängt die rohe JSON-Spalte an. Standardmäßig bleibt sie **draußen**:
    Sie enthält Import-Interna, die im Modellkontext nur Platz kosten. Wer sie braucht
    (die Operatorenliste braucht ``afb`` und ``aliase``), fordert sie ausdrücklich an.
    """
    treffer = {
        "node_id": str(row["id"]),
        "title": row["title"],
        "category": row["category"],
        "content_type": row["content_type"],
        # Der Inhalt geht mit, damit das Modell die Knoten auch **lesen** kann.
        # `/context/search` streift ihn über sein response_model wieder ab — die
        # Vorschlagsliste im Chat zeigt nur Titel.
        "content": row["content"],
        # Der Fachname, nicht nur die interne `subject_id`: Auf die Frage „… in den
        # verschiedenen Fächern" konnte ein Modell mit `subject_id: 13` nichts anfangen
        # und meldete, es gebe keine Einträge je Fach.
        "fach": row["fach"],
        **anzeige_felder(row),
    }
    if mit_metadaten:
        treffer["metadata"] = row["metadata"] or {}
    return treffer


_SPALTEN = (
    ContextNode.id,
    ContextNode.category,
    ContextNode.content_type,
    ContextNode.title,
    ContextNode.content,
    ContextNode.subject_id,
    ContextNode.bp_version,
    ContextNode.metadata_.label("metadata"),
    Subject.name.label("fach"),
)


def _grundabfrage(profil: Suchprofil):
    """Sichtbare, aktive Knoten mit Fachnamen — die gemeinsame Basis aller Verfahren.

    Sind Anker gesetzt, wird zusätzlich auf deren Teilgraphen eingeschränkt: Ein
    Assistent mit ``retrieval_scope`` soll nur finden, was zu seinem Gegenstand gehört.
    """
    stmt = (
        select(*_SPALTEN)
        .outerjoin(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.status == "active")
        .where(read_scope_clause(profil.pseudonym, profil.rollen))
    )
    if profil.anchor_ids:
        stmt = stmt.where(ContextNode.id.in_(teilgraph(profil.anchor_ids)))
    return stmt


def _bonus(bedingung, wert: float):
    """Additiver Vorsprung in der Sortierung — ``CASE WHEN … THEN wert ELSE 0``."""
    return sa.case(
        (bedingung, sa.cast(sa.literal(wert), sa.Float)),
        else_=sa.cast(sa.literal(0.0), sa.Float),
    )


def _typ_bonus(profil: Suchprofil):
    """Rollenabhängiger Vorsprung je Knotenart — oder ``None``, wenn keiner gilt.

    Dieselbe Anfrage meint je nach Rolle etwas anderes: Wer als Schüler:in nach
    „Bruchrechnung" sucht, will lernen; wer als Lehrkraft danach sucht, will
    unterrichten oder prüfen. Beide finden dasselbe, nur in anderer Reihenfolge.

    Die Tabelle steht in :data:`app.context.taxonomy.ROLLEN_TYP_BONUS` — dort auch die
    Begründung je Typ und die Zusage, dass Bildungsplan-Typen bei 0 bleiben.
    """
    tabelle = rollen_typ_bonus(profil.rollen)
    if not tabelle:
        return None
    return sa.case(
        *[
            (ContextNode.content_type == typ, sa.cast(sa.literal(wert), sa.Float))
            for typ, wert in tabelle.items()
        ],
        else_=sa.cast(sa.literal(0.0), sa.Float),
    )


def _aus_dem_fach(profil: Suchprofil):
    """„Stammt dieser Knoten aus dem Fach der Konversation?" — oder ``None``.

    ⚠️ **Nicht durch ``ContextNode.subject_id == profil.subject_id`` ersetzen.** Ist kein
    Fach im Spiel, macht SQLAlchemy daraus ``subject_id IS NULL`` — und damit bekämen
    ausgerechnet die fachlosen Knoten (Leitperspektiven, prozessbezogene Gruppen,
    schulweite Dokumente) den Fachbonus. Im rohen SQL war das kein Thema:
    ``c.subject_id = NULL`` ist nie wahr, der Bonus fiel von selbst weg. Gemessen am
    Prüfsatz kostete der Fehler zwei Fälle, in denen ein fachloser Knoten den richtigen
    Fachtreffer von Platz 1 verdrängte.
    """
    if profil.subject_id is None:
        return None
    return ContextNode.subject_id == profil.subject_id


# ── Teilgraph unter Ankern (Profil `anchor_ids`) ─────────────────────────────


def teilgraph(anchor_ids: Sequence[UUID]):
    """Die Knoten unter den Ankern eines Assistenten — als Unterabfrage.

    Zwei Wege führen hinein, beide aus ADR-013:

    * **Abstammung** — alles, was über ``part_of`` unter einem Anker hängt, rekursiv.
      Ein Curriculum-Anker erfasst so seine Kapitel und deren Lernsequenzen.
    * **Verweise** — was der Anker selbst über ``references`` oder ``develops``
      benennt. Eine Lernsequenz zieht damit die Kompetenzen herein, die sie entwickelt,
      ohne dass sie unter ihr hängen.

    Bis 09/2026 stand diese Abfrage als roher SQL-Text in ``retrieval.py`` und war der
    einzige Ort mit einer zweiten Vektorsuche. Jetzt ist sie ein Vorfilter der Schicht:
    Anker-Assistenten erben damit Nachschlagen, Boni und Prüfsatz.
    """
    kanten = ContextEdge.__table__
    knoten = ContextNode.__table__
    ids = list(anchor_ids)

    abstammung = (
        sa.select(knoten.c.id)
        .where(knoten.c.id.in_(ids), knoten.c.status == "active")
        .cte("abstammung", recursive=True)
    )
    abstammung = abstammung.union_all(
        sa.select(kanten.c.from_node_id)
        .select_from(kanten.join(abstammung, kanten.c.to_node_id == abstammung.c.id))
        .where(kanten.c.relation == "part_of")
    )
    verwiesen = sa.select(kanten.c.to_node_id).where(
        kanten.c.from_node_id.in_(ids),
        kanten.c.relation.in_(["references", "develops"]),
    )
    return sa.union(sa.select(abstammung.c.id), verwiesen)


# ── Editionen: zwei gültige BP-Fassungen gleichzeitig ────────────────────────
#
# Solange eine neue Bildungsplan-Edition jahrgangsweise nach oben wächst, liegen dieselben
# Kompetenzen doppelt im Speicher — in der alten und der neuen Fassung, textlich oft nur
# in Nuancen verschieden. Ohne Gegenmaßnahme belegen beide je einen der Plätze und
# verdrängen anderes.
#
# Zwei Stufen, absichtlich in dieser Reihenfolge:
#   1. Filtern, wo ein Jahrgang bekannt ist — dann entscheidet der Fahrplan, welche
#      Fassung gilt (fachweise, inkl. Inhalts-Fallback).
#   2. Zusammenfassen, was danach noch doppelt ist — greift auch im freien Chat ohne
#      Gruppenbezug, wählt aber nur nach Ähnlichkeit.
#
# Seit 09/2026 gilt beides für **alle** Profile. Bis dahin lag es allein im Anker-Weg;
# der freie Chat bekam Fassungs-Dubletten ungefiltert.

# Überhang beim Holen: Filter und Zusammenfassung entfernen Treffer, deshalb wird ein
# Vielfaches des Budgets geladen und erst danach gekürzt.
_KANDIDATEN_FAKTOR = 3


async def _frontier_je_fach(
    db: AsyncSession, subject_ids: set[int], grade: int
) -> dict[int, str]:
    """{subject_id: geltende bp_version} für diese Stufe im laufenden Schuljahr.

    Fächer ohne bestimmbare Fassung fehlen im Ergebnis — für sie wird nicht gefiltert.
    Der Editionsbestand kommt je Fach aus der DB, damit der Inhalts-Fallback greift (neue
    Edition laut Fahrplan in Kraft, aber für dieses Fach noch nicht importiert → vorige
    Edition gilt weiter).
    """
    if not subject_ids:
        return {}

    zeilen = await db.execute(
        sa.select(ContextNode.subject_id, ContextNode.bp_version)
        .where(
            ContextNode.subject_id.in_(subject_ids),
            ContextNode.status == "active",
            ContextNode.bp_version != "",
        )
        .distinct()
    )
    bestand: dict[int, set[str]] = {}
    for subject_id, bp_version in zeilen.all():
        bestand.setdefault(subject_id, set()).add(bp_version)

    frontier: dict[int, str] = {}
    for subject_id, verfuegbar in bestand.items():
        gilt = aktive_bp_version(grade, verfuegbar)
        if gilt:
            frontier[subject_id] = gilt
    return frontier


def _filtere_auf_frontier(treffer: list[dict], frontier: dict[int, str]) -> list[dict]:
    """Nur die geltende Fassung behalten — unversionierte Knoten bleiben immer.

    Fächer ohne Eintrag in ``frontier`` werden nicht gefiltert; sonst bliebe von einem
    Fach, dessen Fassung sich nicht bestimmen lässt, gar nichts übrig.
    """
    return [
        t
        for t in treffer
        if not t.get("bp_version")
        or frontier.get(t.get("subject_id")) in (None, t.get("bp_version"))
    ]


async def _auf_geltende_fassung(
    treffer: list[dict], profil: Suchprofil, db: AsyncSession
) -> list[dict]:
    """Beide Editionsstufen anwenden: erst filtern (wenn ein Jahrgang bekannt ist),
    dann zusammenfassen, was noch doppelt ist."""
    if profil.grade is not None:
        faecher = {
            t["subject_id"]
            for t in treffer
            if t.get("bp_version") and t.get("subject_id")
        }
        treffer = _filtere_auf_frontier(
            treffer, await _frontier_je_fach(db, faecher, profil.grade)
        )
    return fasse_fassungen_zusammen(treffer, _treffer_schluessel)


# ── Fassungen derselben Kompetenz ────────────────────────────────────────────
#
# Solange eine neue Bildungsplan-Edition jahrgangsweise nach oben wächst, liegen dieselben
# Kompetenzen doppelt im Speicher — in der alten und der neuen Fassung, textlich oft nur
# in Nuancen verschieden. Ohne Gegenmaßnahme belegen beide je einen Platz und verdrängen
# anderes; in einer Aufzählung verfälschen sie zusätzlich die Zählung.


def fassungs_schluessel(subject_id, content_type, nr) -> tuple | None:
    """Identität einer BP-Kompetenz **über Fassungen hinweg**: Fach, Typ, Nummer.

    ``None`` für alles ohne Nummer (Operatoren, Fachpläne, Nutzerknoten) — das wird nie
    zusammengefasst. Die Nummer genügt als Schlüssel: Sie ist je Fach und Knotentyp
    innerhalb einer Fassung eindeutig, das Stufenband steckt bereits in ihr.

    Eine Regel, zwei Aufrufer: die Aufzählung hier (auf Schicht-Treffern) und der
    Anker-Weg in :mod:`app.context.retrieval` (auf ORM-Objekten). AP5 führt beide
    zusammen; bis dahin teilen sie wenigstens die Entscheidung.
    """
    if subject_id is None or not nr:
        return None
    return (subject_id, content_type, nr)


def fasse_fassungen_zusammen(eintraege: list, schluessel) -> list:
    """Je Kompetenz nur den erstbesten Eintrag behalten (Reihenfolge bleibt).

    ``schluessel`` liefert je Eintrag den Fassungsschlüssel oder ``None``; Einträge ohne
    Schlüssel bleiben immer erhalten.
    """
    gesehen: set[tuple] = set()
    behalten: list = []
    for eintrag in eintraege:
        s = schluessel(eintrag)
        if s is None:
            behalten.append(eintrag)
            continue
        if s in gesehen:
            continue
        gesehen.add(s)
        behalten.append(eintrag)
    return behalten


def _treffer_schluessel(t: dict) -> tuple | None:
    """Der Fassungsschlüssel eines Schicht-Treffers.

    ``bp_version`` muss gesetzt sein: Unversionierte Knoten sind keine Fassungen
    voneinander, auch wenn sie zufällig dieselbe Nummer tragen.
    """
    if not t.get("bp_version"):
        return None
    return fassungs_schluessel(t.get("subject_id"), t.get("content_type"), t.get("nr"))


# ── Verfahren 3: Aufzählung ──────────────────────────────────────────────────

# Wie viele Zeilen die Aufzählung höchstens holt, um zu zählen und zu gruppieren. Die
# Zählung selbst ist unabhängig davon exakt (`COUNT(*) OVER ()`); die Obergrenze schützt
# nur davor, für eine allzu weite Bedingung den halben Wissensgraphen in den Speicher zu
# ziehen. Wird sie erreicht, sagt der Umschlag es.
_AUFZAEHLUNG_MAX = 500


async def aufzaehlung(
    filter_: Knotenfilter,
    profil: Suchprofil,
    db: AsyncSession,
    *,
    gruppierung: str | None = None,
    mit_metadaten: bool = False,
) -> Abschnitt:
    """„Alle Bausteine, die …" — deterministisch, gezählt, ohne Ähnlichkeitsmaß.

    Der Unterschied zur Identifikation ist der **Vollständigkeitsanspruch**, nicht das
    Matching: Beide können denselben Namen suchen (über dieselbe Normalisierung), aber
    die Identifikation liefert Anheft-Kandidaten im Budget der Oberfläche, die Aufzählung
    die gezählte Gesamtliste. Deshalb steht hier ``gesamt`` immer, auch wenn nur ein Teil
    mitgeliefert wird — „14 von 24" ist eine Antwort, 14 kommentarlos gelieferte Treffer
    sind eine Falle.

    ``gruppierung``: ``"fach"`` oder ``"typ"``; ohne Angabe wird nicht gruppiert.
    """
    stmt = (
        wende_an(_grundabfrage(profil), filter_)
        # ⚠️ Die Zählung **vor** dem Limit. Sie ist der Grund für dieses Verfahren.
        .add_columns(sa.func.count().over().label("gesamt"))
        .order_by(Subject.name.nulls_last(), ContextNode.title, ContextNode.id)
        .limit(_AUFZAEHLUNG_MAX)
    )
    zeilen = (await db.execute(stmt)).mappings().all()
    roh_gesamt = zeilen[0]["gesamt"] if zeilen else 0

    treffer = fasse_fassungen_zusammen(
        [_treffer(z, mit_metadaten=mit_metadaten) for z in zeilen], _treffer_schluessel
    )
    gruppen = _gruppiere(treffer, gruppierung) if gruppierung else None

    # ⚠️ Beim Deckel ist die Zählung **nicht** `len(treffer)`. Sonst meldete eine Suche
    # über alle Operatoren „500 von 500" — der Deckel als Gesamtzahl ausgegeben, was
    # vollständig aussieht und um mehr als das Doppelte danebenliegt (1 278 sind es).
    # Über dem Deckel gilt die rohe Zählung aus der Datenbank; sie ist exakt, nur eben
    # vor der Fassungs-Zusammenfassung, die auf den geholten Zeilen arbeitet.
    gedeckelt = roh_gesamt > _AUFZAEHLUNG_MAX
    return Abschnitt(
        treffer=treffer[: profil.aufzaehlung],
        gesamt=roh_gesamt if gedeckelt else len(treffer),
        vollstaendig=not gedeckelt and len(treffer) <= profil.aufzaehlung,
        gruppen=gruppen,
        hinweis=(
            f"Mehr als {_AUFZAEHLUNG_MAX} Treffer: Gezählt ist der Bestand, gruppiert "
            f"und um Fassungs-Dubletten bereinigt sind nur die ersten "
            f"{_AUFZAEHLUNG_MAX}. Grenze die Suche ein."
            if gedeckelt
            else None
        ),
    )


_GRUPPIERUNG_FELD = {"fach": "fach", "typ": "content_type"}


def _gruppiere(treffer: list[dict], nach: str) -> list[Gruppe]:
    """Nach Fach oder Typ zählen, absteigend nach Anzahl, dann alphabetisch."""
    feld = _GRUPPIERUNG_FELD.get(nach)
    if feld is None:
        return []
    zaehler: dict[str, int] = {}
    for t in treffer:
        name = t.get(feld) or "ohne Angabe"
        zaehler[name] = zaehler.get(name, 0) + 1
    return [
        Gruppe(name=name, anzahl=anzahl)
        for name, anzahl in sorted(zaehler.items(), key=lambda p: (-p[1], p[0]))
    ]


# ── Verfahren 1: Identifikation ──────────────────────────────────────────────

# Ab welcher Trigramm-Ähnlichkeit ein Titel als teilweise getroffen gilt.
#
# **0,50 ist gemessen** (01.09.2026, an den Testknoten aus
# `scripts/seed_search_eval_nodes.py` und den 21 thematischen Prüfsatzfällen):
#
#   Schwelle   S2-Fälle gefunden   thematische Fälle mit Namensträger-Block
#     0,30           4/4                        13 von 21
#     0,40           4/4                         6
#     0,45           4/4                         3
#     0,50           4/4                         0        ← gewählt
#     0,55           2/4                         0
#     0,60           2/4                         0
#
# Der Kipppunkt liegt genau dort: volle Trefferquote bei null Störung. Ab 0,55 fällt der
# Leitfall „Anleitung Operator nennen" durch — die Anfrage, um die es geht.
#
# Das ist **kein Gütesignal** im Sinne der verworfenen Ähnlichkeitsschwellen
# (Bestandsaufnahme): Es entscheidet nicht, ob ein Treffer gut ist, sondern ob zwei
# Zeichenketten einander ähnlich genug sind, um denselben Namen zu meinen.
_TEILTREFFER_SCHWELLE = 0.50

# Wie viel Vorsprung eigenes Material in der thematischen Auswahl bekommt — dieselbe
# Einheit und Größenordnung wie `_FACHBONUS`.
#
# ⚠️ **Heute nicht am Prüfsatz messbar, und das hat einen Grund.** Von 26 Knoten mit
# Eigentümer tragen 6 ein Embedding; keiner davon gehört dem Prüfsatz-Pseudonym. Wirksam
# wird der Bonus erst, wenn nutzererzeugte Typen eingebettet werden — dieselbe
# Vorbedingung, an der auch die rollenbasierte Typ-Gewichtung hängt (ADR-017-Nachtrag,
# AP6 Schritt 0). Bis dahin ist er nachweislich wirkungslos, nicht ungeprüft: Der
# Prüfsatz bleibt mit und ohne ihn unverändert.
_EIGENTUEMER_BONUS = 0.05


def _kandidaten(frage: str) -> list[str]:
    """Wonach die Identifikation sucht: reduzierter Begriff **und** Rohanfrage.

    Bis 09/2026 war die Wortlisten-Reduktion ein **Tor**: Sprach sie nicht an, fand die
    Identifikation gar nicht erst statt. Jetzt ist sie nur noch eine Kandidatenquelle,
    und eine verpasste Erkennung kostet Reihenfolge statt Treffer (ADR-017).

    Beide Formen sind nötig, und zwar für verschiedene Stufen: Der reduzierte Begriff
    isoliert den Namen aus der Frageform („Was bedeutet der Operator nennen?" →
    ``nennen``) und trägt damit den **exakten** Abgleich. Für die **Teilsuche** wäre er
    schädlich — sie vergleicht ganze Titel, und `reduziere()` wirft mit „Operator" genau
    das Wort weg, das „Anleitung zur Verwendung des Operators nennen" ausmacht. Gemessen:
    Mit dem reduzierten Begriff wird der Leitfall bei **keiner** Schwelle gefunden, mit
    der Rohanfrage bei jeder bis 0,50.
    """
    roh = normalisiere_titel(frage)
    begriff = nachschlage_begriff(frage)
    return [k for k in dict.fromkeys([begriff, roh]) if k]


def _vorrang(profil: Suchprofil) -> list:
    """Eigenes zuerst, dann das Fach der Konversation.

    Der Eigentümer-Vorrang ist eine **Sortierstufe, kein Filter**: Fremde gleichnamige
    Bausteine verschwinden nicht, sie rücken nach. Wer nach „seinem" Merkblatt sucht,
    soll es oben finden, ohne dass die Handreichung der Fachschaft unauffindbar wird.
    """
    stufen = [sa.case((ContextNode.owner_pseudonym == profil.pseudonym, 0), else_=1)]
    aus_dem_fach = _aus_dem_fach(profil)
    if aus_dem_fach is not None:
        stufen.append(sa.case((aus_dem_fach, 0), else_=1))
    return stufen


def _sortierung(profil: Suchprofil) -> list:
    """Vorrangstufen, dann stabil nach Fach und ID — damit dieselbe Frage nicht bei
    jedem Aufruf anders sortiert erscheint."""
    return [*_vorrang(profil), Subject.name.nulls_last(), ContextNode.id]


def identifikations_abfrage(begriffe: list[str] | str, profil: Suchprofil):
    """Die Abfrage hinter dem **exakten** Namensabgleich — eigenständig, damit prüfbar.

    Der Integrationstest lässt sie von PostgreSQL erklären (``EXPLAIN``) und stellt so
    sicher, dass der Ausdrucksindex aus Migration 0053 tatsächlich greift. Sein Ausfall
    ist still: dasselbe Ergebnis, nur rund 70 statt 0,3 ms — bei **jeder** Suche.
    """
    if isinstance(begriffe, str):
        begriffe = [begriffe]
    return (
        _grundabfrage(profil)
        # Die Gesamtzahl **vor** dem Limit: Sonst wäre nicht zu sagen, ob die gelieferten
        # Namensträger alle sind. Genau diese Auskunft trägt die Existenzaussage.
        .add_columns(sa.func.count().over().label("gesamt"))
        .where(_TITEL_NORMALISIERT.in_(begriffe))
        .order_by(*_sortierung(profil))
        .limit(profil.identifikation)
    )


def teiltreffer_abfrage(roh: str, profil: Suchprofil, *, ausschluss: set[str]):
    """Die zweite Stufe: Titel, die dem Gesuchten **ähneln**.

    Nutzt den GIN-Trigramm-Index aus Migration 0054 über den ``%``-Operator. Die Schwelle
    ist eine Sitzungseinstellung (siehe :func:`_setze_schwelle`) — deshalb steht sie hier
    nicht im SQL.
    """
    stmt = (
        _grundabfrage(profil)
        .where(sa.literal(roh).op("%")(_TITEL_NORMALISIERT))
        .order_by(
            *_vorrang(profil),
            sa.func.similarity(sa.literal(roh), _TITEL_NORMALISIERT).desc(),
            ContextNode.id,
        )
        .limit(profil.identifikation + len(ausschluss))
    )
    if ausschluss:
        stmt = stmt.where(ContextNode.id.notin_([UUID(i) for i in ausschluss]))
    return stmt


def praefix_abfrage(roh: str, profil: Suchprofil, *, ausschluss: set[str]):
    """Titel, die mit dem Getippten **anfangen** — für die Namensvervollständigung.

    ⚠️ **Warum die Trigramm-Stufe das nicht abdeckt.** Ihre Ähnlichkeit ist
    längennormiert: Ein kurzer Anfang gegen einen langen Titel fällt unter die Schwelle.
    Gemessen am 01.09.2026 liefert „Satz" gegen „Satz des Pythagoras" **keinen** Treffer
    (rund 0,25 gegen eine Schwelle von 0,50) — wer einen bekannten Titel von vorne
    tippt, sähe also bis zum letzten Wort nichts. Genau dieser Fall ist der Anlass des
    `@`-Shortcodes.

    Der GIN-Trigramm-Index aus Migration 0054 trägt auch das ``LIKE 'x%'``; eine eigene
    Migration braucht es nicht.

    Sortiert wird nach **Titellänge**: Bei „Satz" steht „Satz des Pythagoras" vor einem
    Kompetenztext, der genauso anfängt und drei Zeilen weitergeht. Für eine
    Vervollständigung ist der kürzeste passende Titel der wahrscheinlich gemeinte.
    """
    stmt = (
        _grundabfrage(profil)
        .where(_TITEL_NORMALISIERT.like(sa.literal(roh + "%")))
        .order_by(
            *_vorrang(profil),
            sa.func.length(_TITEL_NORMALISIERT),
            ContextNode.id,
        )
        .limit(profil.identifikation + len(ausschluss))
    )
    if ausschluss:
        stmt = stmt.where(ContextNode.id.notin_([UUID(i) for i in ausschluss]))
    return stmt


async def _setze_schwelle(db: AsyncSession) -> None:
    """Die Trigramm-Schwelle für **diese Transaktion** setzen.

    ⚠️ **Transaktionslokal**, nicht sitzungsweit. Die pg_trgm-Schwellen sind
    Sitzungseinstellungen; im gepoolten Async-Betrieb wanderte ein einfaches ``SET`` mit
    der Verbindung zum nächsten Request und veränderte dort eine Suche, die nie darum
    gebeten hat.

    ``set_config(…, true)`` statt ``SET LOCAL``, weil ``SET`` keine Parameter annimmt
    („syntax error at or near $1"). Die Alternative wäre, den Wert in die Anweisung zu
    schreiben — das geht hier nur um eine Modulkonstante, aber eine Abfrage ohne
    Parameterbindung ist eine Gewohnheit, die man sich nicht angewöhnt.
    """
    await db.execute(
        sa.select(
            sa.func.set_config(
                "pg_trgm.similarity_threshold", str(_TEILTREFFER_SCHWELLE), True
            )
        )
    )


async def identifikation(
    frage: str, profil: Suchprofil, db: AsyncSession, *, praefix: bool = False
) -> Abschnitt:
    """Knoten, deren Titel der gesuchte Name **ist** — oder ihm nahekommt.

    Zwei Stufen, und die Reihenfolge ist die Aussage: erst die exakten Namensträger,
    dahinter die ähnlich benannten. Nur die erste Stufe trägt die Zählung und damit die
    Existenzaussage; welcher Stufe ein Treffer entstammt, steht an ihm (``treffer_art``).

    ``praefix`` schiebt eine dritte Stufe dazwischen: Titel, die mit dem Getippten
    **anfangen**. Sie gilt nur für die Namensvervollständigung des `@`-Shortcodes —
    dort tippt man einen bekannten Titel von vorne, und ohne sie sähe man bis zum
    letzten Wort nichts (Begründung und Messung: :func:`praefix_abfrage`). Für alle
    anderen Aufrufer bleibt sie aus, damit der Prüfsatz vergleichbar bleibt.

    ⚠️ **Ohne Embedding-Filter, anders als die thematische Auswahl.** Ein Titel wird
    verglichen, nicht eingebettet — und 30 der 44 Knotentypen tragen laut
    ``taxonomy.yaml`` bewusst kein Embedding (Fachpläne, Curricula, Methoden,
    Leitperspektiven …). Bliebe der Filter hier stehen, wären diese Knoten unter ihrem
    eigenen Namen unauffindbar, während die Aufzählung sie zählt: zwei Grundmengen in
    einem Umschlag, und die Existenzaussage wäre gebrochen.
    """
    kandidaten = _kandidaten(frage)
    if not kandidaten:
        return Abschnitt(gesamt=0, vollstaendig=True)

    zeilen = (
        await db.execute(identifikations_abfrage(kandidaten, profil))
    ).mappings().all()
    gesamt = zeilen[0]["gesamt"] if zeilen else 0
    exakt = [_treffer(z) | {"treffer_art": "exakt"} for z in zeilen]

    # Die weiteren Stufen füllen nur auf, was die erste offen gelassen hat.
    rest = profil.identifikation - len(exakt)
    roh = normalisiere_titel(frage)
    gesehen = {t["node_id"] for t in exakt}
    weitere: list[dict] = []

    if praefix and rest > 0:
        zeilen_p = (await db.execute(
            praefix_abfrage(roh, profil, ausschluss=gesehen)
        )).mappings().all()
        neu = [_treffer(z) | {"treffer_art": "praefix"} for z in zeilen_p[:rest]]
        weitere += neu
        gesehen |= {t["node_id"] for t in neu}
        rest -= len(neu)

    if rest > 0:
        await _setze_schwelle(db)
        zeilen_t = (await db.execute(
            teiltreffer_abfrage(roh, profil, ausschluss=gesehen)
        )).mappings().all()
        weitere += [
            _treffer(z) | {"treffer_art": "teilweise"} for z in zeilen_t[:rest]
        ]

    return Abschnitt(
        treffer=exakt + weitere,
        # `gesamt` zählt die **exakten** Namensträger. Für die Teiltreffer gibt es keine
        # verteidigbare Gesamtmenge — sie hängt an einer Schwelle, und eine Zahl daraus
        # zu machen hieße, die Schwelle als Wahrheit auszugeben.
        gesamt=gesamt,
        vollstaendig=len(exakt) >= gesamt,
    )


# ── Verfahren 2: Thematische Auswahl ─────────────────────────────────────────


# Sentinel: „hol den Vektor selbst" — zu unterscheiden von `None` (= es gibt keinen,
# also ILIKE-Rückfall). Ein blosses `None` als Vorgabe könnte beides bedeuten.
_SELBST_HOLEN = object()


async def vektor_oder_none(frage: str) -> list[float] | None:
    """Das Anfrage-Embedding — oder ``None``, wenn es nicht zu haben ist.

    Ausgelagert, damit Aufrufer den Netzaufruf **vorziehen** können: Er dauert rund
    370 ms und ist damit der weitaus teuerste Teil einer Suche (die Datenbank braucht
    zusammen rund 70 ms, gemessen 01.09.2026). Wer ihn als Task startet, kann in der
    Zwischenzeit die Identifikation über die Datenbank laufen lassen.

    ⚠️ Nebenläufig laufen darf nur der **Netzaufruf**, nie zwei Datenbankabfragen: Eine
    ``AsyncSession`` verträgt das nicht und wirft ``IllegalStateChangeError``.
    """
    try:
        return await generate_embedding(frage)
    except Exception:
        logger.warning("Embedding-Suche fehlgeschlagen, Fallback auf ILIKE")
        return None


async def thematisch(
    frage: str,
    profil: Suchprofil,
    db: AsyncSession,
    *,
    ausschluss: set[str] | None = None,
    vektor=_SELBST_HOLEN,
) -> Abschnitt:
    """Semantische Suche über alle sichtbaren Knoten mit Embedding.

    ``profil.subject_id`` = Fach der Konversation, falls bekannt. Treffer aus diesem Fach
    werden **vorgezogen, nicht gefiltert**: Fachfremdes bleibt in der Liste, denn eine
    Mathematik-Kompetenz kann im Physik-Chat genau das Gesuchte sein. Ein harter Filter
    schiede zusätzlich alle Knoten **ohne** Fach aus (Leitperspektiven, schulweite
    Dokumente); auch deshalb nur ein Bonus.

    ``ausschluss`` sind bereits in der Identifikation gelieferte Knoten — sie sollen
    nicht zweimal im selben Umschlag stehen.

    Sind ``profil.anchor_ids`` gesetzt, läuft dieselbe Suche im Teilgraphen unter den
    Ankern — das ist der frühere ``get_semantic_context``.

    Fällt auf ILIKE zurück, wenn kein Embedding erzeugt werden kann oder kein Knoten ein
    Embedding hat.
    """
    ausschluss = ausschluss or set()
    # Überhang holen: Der Ausschluss der Identifikations-Treffer und die
    # Editionsbereinigung entfernen Zeilen, und beides erst nach der Abfrage.
    hole = (profil.thematisch + len(ausschluss)) * _KANDIDATEN_FAKTOR

    async def fertig(zeilen) -> Abschnitt:
        treffer = [
            t
            for t in (_treffer(z, mit_metadaten=profil.mit_metadaten) for z in zeilen)
            if t["node_id"] not in ausschluss
        ]
        treffer = await _auf_geltende_fassung(treffer, profil, db)
        # Die thematische Auswahl ist **nie** vollständig: Zu „ähnlich genug" gibt es
        # keine Grenze, die sich verteidigen ließe (in der Bestandsaufnahme widerlegt).
        return Abschnitt(treffer=treffer[: profil.thematisch], gesamt=None, vollstaendig=False)

    aus_dem_fach = _aus_dem_fach(profil)
    if vektor is _SELBST_HOLEN:
        vektor = await vektor_oder_none(frage)

    if vektor is not None:
        naehe = ContextNode.embedding.cosine_distance(vektor)
        # ⚠️ Die Boni müssen als **Fließkommazahl** in die Abfrage. Werden sie als ganze
        # Zahl typisiert — was PostgreSQL aus dem anderen CASE-Zweig ableiten kann —,
        # runden sie auf 0 und die Sortierung bleibt unverändert. Ohne Fehlermeldung:
        # Die Abfrage läuft, sie tut nur nichts.
        if aus_dem_fach is not None:
            naehe = naehe - _bonus(aus_dem_fach, _FACHBONUS)
        naehe = naehe - _bonus(
            ContextNode.owner_pseudonym == profil.pseudonym, _EIGENTUEMER_BONUS
        )
        typ_bonus = _typ_bonus(profil)
        if typ_bonus is not None:
            naehe = naehe - typ_bonus
        stmt = (
            _grundabfrage(profil)
            .where(ContextNode.embedding.is_not(None))
            .order_by(naehe)
            .limit(hole)
        )
        zeilen = (await db.execute(stmt)).mappings().all()
        if zeilen:
            return await fertig(zeilen)
        # Kein Knoten hat ein Embedding → Fallback

    # Fallback: ILIKE auf Titel und Inhalt — mit demselben Fachvorzug. Ohne ihn verhielte
    # sich die Rückfallebene anders als der Normalfall, und das fiele erst auf, wenn
    # ohnehin schon etwas klemmt.
    stmt = (
        _grundabfrage(profil)
        .where(
            or_(
                ContextNode.title.ilike(f"%{frage}%"),
                ContextNode.content.ilike(f"%{frage}%"),
            )
        )
        .limit(hole)
    )
    if aus_dem_fach is not None:
        stmt = stmt.order_by(sa.case((aus_dem_fach, 0), else_=1))
    return await fertig((await db.execute(stmt)).mappings().all())


# ── Einstiegspunkt ───────────────────────────────────────────────────────────

_HINWEIS_KEIN_NAME = (
    "Die Anfrage benennt keinen Baustein; der Abschnitt der exakten Namensträger bleibt "
    "deshalb leer. Das ist keine Aussage darüber, ob es solche Bausteine gibt."
)


def _hinweise(frage: str, ident: Abschnitt) -> list[str]:
    """Was der Umschlag über sich selbst sagen muss.

    Ein leerer Identifikationsabschnitt hat zwei sehr verschiedene Bedeutungen, und wer
    sie verwechselt, antwortet falsch: Entweder hat die Anfrage gar keinen Namen genannt
    (dann ist der leere Abschnitt bedeutungslos), oder sie hat einen genannt, den es
    nicht gibt (dann ist er eine belastbare Auskunft — aber nur über den **Namen**,
    nicht über das Thema).
    """
    if ident.gesamt:
        if ident.vollstaendig:
            return []
        exakt = sum(1 for t in ident.treffer if t.get("treffer_art") == "exakt")
        return [
            f"{ident.gesamt} Bausteine tragen diesen Namen, {exakt} davon stehen hier."
        ]

    # Keine exakten Namensträger. Ähnlich benannte gelten ausdrücklich **nicht** als
    # Beleg dafür, dass es den gesuchten Namen gibt — sonst führte die Teilsuche genau
    # die Verwechslung wieder ein, die der Umschlag auflösen soll.
    teilweise = sum(1 for t in ident.treffer if t.get("treffer_art") == "teilweise")
    begriff = nachschlage_begriff(frage)
    if not begriff:
        return [_HINWEIS_KEIN_NAME]
    kern = f"Kein Baustein heißt genau „{begriff}“."
    if teilweise:
        return [
            f"{kern} {teilweise} ähnlich benannte stehen hier — prüfe am Titel, ob "
            f"einer davon gemeint ist."
        ]
    return [
        f"{kern} Über Bausteine zu diesem Thema sagt das nichts — dafür stehen die "
        f"nächstliegenden Bausteine da."
    ]


async def suche(
    frage: str,
    profil: Suchprofil,
    db: AsyncSession,
    *,
    nur_identifikation: bool = False,
) -> Suchergebnis:
    """Beide Verfahren, ein Umschlag.

    Die Identifikation läuft zuerst: Ihre Treffer werden aus der thematischen Auswahl
    ausgeschlossen, damit kein Knoten zweimal im selben Umschlag steht.

    ``nur_identifikation`` lässt die thematische Auswahl aus. Das ist keine
    Sparmaßnahme am Rand: Sie kostet einen **Netzaufruf zum Embedding-Modell** (rund
    370 ms, gemessen 01.09.2026), und das `@`-Dropdown fragt bei jedem Tastendruck neu.
    Wer dort einen Titel nachschlägt, will Namensträger — thematische Nachbarn wären
    weder gezeigt noch gewollt, nur bezahlt (der Aufruf läuft über den Master-Key, also
    aufs Systembudget).
    """
    if nur_identifikation:
        # Mit Präfix-Stufe: Der einzige Aufrufer ist die Namensvervollständigung des
        # `@`-Shortcodes, und dort wird ein bekannter Titel von vorne getippt.
        ident = await identifikation(frage, profil, db, praefix=True)
        return Suchergebnis(identifikation=ident, hinweise=_hinweise(frage, ident))

    # Das Embedding zuerst **anstoßen**, aber noch nicht abwarten: Es dauert rund 370 ms
    # (Netzaufruf zum Modell), die Identifikation rund 70 ms (Datenbank). Nacheinander
    # sind das 440 ms, überlappt 370 — die Titelabfragen laufen, während der Vektor
    # unterwegs ist.
    #
    # ⚠️ Überlappt wird der **Netzaufruf**, nicht die Datenbankarbeit. Zwei Abfragen
    # gleichzeitig auf derselben `AsyncSession` enden in `IllegalStateChangeError`; die
    # Identifikation ist deshalb `await`, nicht Teil eines `gather`.
    vektor_task = asyncio.create_task(vektor_oder_none(frage))
    try:
        ident = await identifikation(frage, profil, db)
    except BaseException:
        vektor_task.cancel()
        raise

    thema = await thematisch(
        frage,
        profil,
        db,
        ausschluss={t["node_id"] for t in ident.treffer},
        vektor=await vektor_task,
    )
    return Suchergebnis(
        identifikation=ident, thematisch=thema, hinweise=_hinweise(frage, ident)
    )
