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
(und später die Aufzählung), nie auf thematische Nähe.
"""

import logging
from dataclasses import dataclass, field
from typing import Sequence

import sqlalchemy as sa
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embedding import generate_embedding
from app.context.lookup import nachschlage_begriff, titel_normalisiert_sql
from app.context.schemas import anzeige_felder
from app.context.visibility import read_scope_clause
from app.db.models import ContextNode, Subject

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


# ── Ergebnisumschlag ─────────────────────────────────────────────────────────


@dataclass
class Abschnitt:
    """Ein beschrifteter Teil des Ergebnisses samt Auskunft über seine Vollständigkeit.

    ``gesamt`` ist die Anzahl **aller** passenden Knoten, soweit bestimmbar — bei der
    Identifikation die Zahl der Namensträger, bei der thematischen Auswahl ``None``:
    Dort gibt es keine Gesamtmenge, nur eine Rangfolge nach Ähnlichkeit.
    """

    treffer: list[dict] = field(default_factory=list)
    gesamt: int | None = None
    vollstaendig: bool = False

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


def _treffer(row) -> dict:
    """Eine Trefferzeile in die Form bringen, die Aufrufer und Modell erwarten.

    Gemeinsam für alle Verfahren — liefen sie auseinander, trüge dieselbe Trefferliste
    je nach Abschnitt unterschiedliche Felder.
    """
    return {
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
    """Sichtbare, aktive Knoten mit Fachnamen — die gemeinsame Basis aller Verfahren."""
    return (
        select(*_SPALTEN)
        .outerjoin(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.status == "active")
        .where(read_scope_clause(profil.pseudonym, profil.rollen))
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


# ── Verfahren 1: Identifikation ──────────────────────────────────────────────

# Der normalisierte Titel als SQL-Ausdruck — dieselbe Quelle wie der Ausdrucksindex aus
# Migration 0053. Weichen beide voneinander ab, benutzt PostgreSQL den Index
# stillschweigend nicht (siehe Docstring in `lookup.py`).
#
# ⚠️ `literal_column`, nicht `text`: Ein `TextClause` ist kein Spaltenausdruck. `==`
# darauf ergibt keine SQL-Bedingung, sondern einen Python-Vergleich mit dem Ergebnis
# `False` — die Abfrage läuft dann fehlerfrei und liefert **nichts**.
_TITEL_NORMALISIERT = sa.literal_column(titel_normalisiert_sql("context_nodes.title"))


def identifikations_abfrage(begriff: str, profil: Suchprofil):
    """Die Abfrage hinter der Identifikation — eigenständig, damit sie prüfbar ist.

    Der Integrationstest lässt sie von PostgreSQL erklären (``EXPLAIN``) und stellt so
    sicher, dass der Ausdrucksindex aus Migration 0053 tatsächlich greift. Sein Ausfall
    ist still: dasselbe Ergebnis, nur rund 70 statt 0,3 ms — bei **jeder** Suche.
    """
    aus_dem_fach = _aus_dem_fach(profil)
    sortierung = [Subject.name.nulls_last(), ContextNode.id]
    if aus_dem_fach is not None:
        sortierung.insert(0, sa.case((aus_dem_fach, 0), else_=1))

    return (
        _grundabfrage(profil)
        # Die Gesamtzahl **vor** dem Limit: Sonst wäre nicht zu sagen, ob die gelieferten
        # Namensträger alle sind. Genau diese Auskunft trägt die Existenzaussage.
        .add_columns(sa.func.count().over().label("gesamt"))
        .where(_TITEL_NORMALISIERT == begriff)
        .order_by(*sortierung)
        .limit(profil.identifikation)
    )


async def identifikation(
    frage: str, profil: Suchprofil, db: AsyncSession
) -> Abschnitt:
    """Knoten, deren Titel der gesuchte Name **ist**.

    ⚠️ **Ohne Embedding-Filter, anders als die thematische Auswahl.** Ein Titel wird
    verglichen, nicht eingebettet — und 30 der 44 Knotentypen tragen laut
    ``config/taxonomy.yaml`` bewusst kein Embedding (Fachpläne, Curricula, Methoden,
    Leitperspektiven …). Bliebe der Filter hier stehen, wären diese Knoten unter ihrem
    eigenen Namen unauffindbar, während die Aufzählung sie zählt: zwei Grundmengen in
    einem Umschlag, und die Existenzaussage wäre gebrochen.

    Innerhalb der Treffer steht das Fach der Konversation vorn, danach alphabetisch nach
    Fach — eine stabile Reihenfolge, damit dieselbe Frage nicht bei jedem Aufruf anders
    sortiert erscheint.
    """
    begriff = nachschlage_begriff(frage)
    if not begriff:
        # Kein Name gemeint. Der Abschnitt bleibt leer, ist damit aber **nicht**
        # „nichts vorhanden" — der Hinweis in `suche()` sagt das ausdrücklich.
        return Abschnitt(gesamt=0, vollstaendig=True)

    zeilen = (
        await db.execute(identifikations_abfrage(begriff, profil))
    ).mappings().all()
    gesamt = zeilen[0]["gesamt"] if zeilen else 0
    return Abschnitt(
        treffer=[_treffer(z) for z in zeilen],
        gesamt=gesamt,
        vollstaendig=len(zeilen) >= gesamt,
    )


# ── Verfahren 2: Thematische Auswahl ─────────────────────────────────────────


async def thematisch(
    frage: str,
    profil: Suchprofil,
    db: AsyncSession,
    *,
    ausschluss: set[str] | None = None,
) -> Abschnitt:
    """Semantische Suche über alle sichtbaren Knoten mit Embedding.

    ``profil.subject_id`` = Fach der Konversation, falls bekannt. Treffer aus diesem Fach
    werden **vorgezogen, nicht gefiltert**: Fachfremdes bleibt in der Liste, denn eine
    Mathematik-Kompetenz kann im Physik-Chat genau das Gesuchte sein. Ein harter Filter
    schiede zusätzlich alle Knoten **ohne** Fach aus (Leitperspektiven, schulweite
    Dokumente); auch deshalb nur ein Bonus.

    ``ausschluss`` sind bereits in der Identifikation gelieferte Knoten — sie sollen
    nicht zweimal im selben Umschlag stehen.

    Fällt auf ILIKE zurück, wenn kein Embedding erzeugt werden kann oder kein Knoten ein
    Embedding hat.
    """
    ausschluss = ausschluss or set()
    # Überhang holen, damit der Ausschluss der Identifikations-Treffer das Budget nicht
    # von unten aufzehrt.
    hole = profil.thematisch + len(ausschluss)

    def fertig(zeilen) -> Abschnitt:
        treffer = [t for t in (_treffer(z) for z in zeilen) if t["node_id"] not in ausschluss]
        # Die thematische Auswahl ist **nie** vollständig: Zu „ähnlich genug" gibt es
        # keine Grenze, die sich verteidigen ließe (in der Bestandsaufnahme widerlegt).
        return Abschnitt(treffer=treffer[: profil.thematisch], gesamt=None, vollstaendig=False)

    aus_dem_fach = _aus_dem_fach(profil)

    try:
        vektor = await generate_embedding(frage)

        naehe = ContextNode.embedding.cosine_distance(vektor)
        if aus_dem_fach is not None:
            # ⚠️ Der Bonus muss als **Fließkommazahl** in die Abfrage. Wird er als ganze
            # Zahl typisiert — was PostgreSQL aus dem anderen CASE-Zweig ableiten kann —,
            # rundet er auf 0 und die Sortierung bleibt unverändert. Ohne Fehlermeldung:
            # Die Abfrage läuft, sie tut nur nichts.
            naehe = naehe - sa.case(
                (aus_dem_fach, sa.cast(sa.literal(_FACHBONUS), sa.Float)),
                else_=sa.cast(sa.literal(0.0), sa.Float),
            )
        stmt = (
            _grundabfrage(profil)
            .where(ContextNode.embedding.is_not(None))
            .order_by(naehe)
            .limit(hole)
        )
        zeilen = (await db.execute(stmt)).mappings().all()
        if zeilen:
            return fertig(zeilen)
        # Kein Knoten hat ein Embedding → Fallback
    except Exception:
        logger.warning("Embedding-Suche fehlgeschlagen, Fallback auf ILIKE")

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
    return fertig((await db.execute(stmt)).mappings().all())


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
    if ident.treffer:
        if ident.vollstaendig:
            return []
        return [
            f"{ident.gesamt} Bausteine tragen diesen Namen, {ident.geliefert} davon "
            f"stehen hier."
        ]

    begriff = nachschlage_begriff(frage)
    if not begriff:
        return [_HINWEIS_KEIN_NAME]
    return [
        f"Kein Baustein heißt „{begriff}“. Über Bausteine zu diesem Thema sagt das "
        f"nichts — dafür stehen die nächstliegenden Bausteine da."
    ]


async def suche(frage: str, profil: Suchprofil, db: AsyncSession) -> Suchergebnis:
    """Beide Verfahren, ein Umschlag.

    Die Identifikation läuft zuerst: Ihre Treffer werden aus der thematischen Auswahl
    ausgeschlossen, damit kein Knoten zweimal im selben Umschlag steht.
    """
    ident = await identifikation(frage, profil, db)
    thema = await thematisch(
        frage, profil, db, ausschluss={t["node_id"] for t in ident.treffer}
    )
    return Suchergebnis(
        identifikation=ident, thematisch=thema, hinweise=_hinweise(frage, ident)
    )
