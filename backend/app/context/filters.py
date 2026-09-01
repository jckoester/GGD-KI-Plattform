"""Die Feldfilter über ``context_nodes`` — **eine** Übersetzung von Bedingung zu SQL.

Bis 09/2026 standen sie ausschließlich im Endpunkt ``GET /context/nodes``, der die
Bibliothek speist. Die Aufzählung („alle Bausteine, die …", ADR-017) braucht dieselben
Filter, und eine zweite Übersetzung derselben Bedingungen wäre die Sorte Kopie, die man
erst bemerkt, wenn beide Seiten verschiedene Antworten geben.

Die Filter sind **rein fachlich** — wer etwas sehen darf, entscheidet
:mod:`app.context.visibility`, und der Status (``active``) kommt vom Aufrufer. Beides
bleibt draußen, damit ein vergessener Filter hier nie zu einem Rechteproblem wird.
"""

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import and_, or_

from app.context.lookup import titel_normalisiert_sql
from app.db.models import ContextNode, Group, Subject

# Der normalisierte Titel als SQL-Ausdruck — dieselbe Quelle wie der Ausdrucksindex aus
# Migration 0053.
#
# ⚠️ `literal_column`, nicht `text`: Ein `TextClause` ist kein Spaltenausdruck. `==`
# darauf ergibt keine SQL-Bedingung, sondern einen Python-Vergleich mit dem Ergebnis
# `False` — die Abfrage läuft dann fehlerfrei und liefert **nichts**.
TITEL_NORMALISIERT = sa.literal_column(titel_normalisiert_sql("context_nodes.title"))


@dataclass(frozen=True)
class Knotenfilter:
    """Wonach eingeschränkt wird. Alle Felder sind unabhängig und werden UND-verknüpft.

    ``titel`` ist der **exakte** Name über dieselbe Normalisierung wie das Nachschlagen
    (ohne Gliederungsnummer, klein, einfache Leerzeichen); ``q`` ist die unscharfe Suche
    der Bibliothek über Titel und Aliase.
    """

    q: str | None = None
    titel: str | None = None
    category: str | None = None
    content_type: tuple[str, ...] = ()
    exclude_content_type: tuple[str, ...] = ()
    subject_id: int | None = None
    subject_id_or_global: int | None = None
    subject_slug: str | None = None
    group_id: int | None = None
    grade: int | None = None
    bp_version: str | None = None
    owner_pseudonym: str | None = None


def wende_an(stmt, f: Knotenfilter):
    """Die gesetzten Bedingungen an eine Abfrage über ``context_nodes`` hängen."""
    if f.subject_id is not None:
        stmt = stmt.where(ContextNode.subject_id == f.subject_id)

    # Dieses Fach **plus** die fachunabhängigen Knoten (z. B. Vokabular).
    if f.subject_id_or_global is not None:
        stmt = stmt.where(
            or_(
                ContextNode.subject_id == f.subject_id_or_global,
                ContextNode.subject_id.is_(None),
            )
        )

    # Knoten, deren Scope-Gruppe zu diesem Fach gehört, plus schulweite/globale
    # knowledge-Knoten mit passendem oder ohne Fach.
    if f.subject_slug:
        gruppen_des_fachs = (
            sa.select(Group.id)
            .join(Subject, Subject.id == Group.subject_id)
            .where(Subject.slug == f.subject_slug)
            .scalar_subquery()
        )
        fach_id = (
            sa.select(Subject.id).where(Subject.slug == f.subject_slug).scalar_subquery()
        )
        stmt = stmt.where(
            or_(
                ContextNode.read_scope_group_id.in_(gruppen_des_fachs),
                and_(
                    ContextNode.read_scope.in_(["global", "school"]),
                    ContextNode.category == "knowledge",
                    or_(
                        ContextNode.subject_id == fach_id,
                        ContextNode.subject_id.is_(None),
                    ),
                ),
            )
        )

    if f.group_id is not None:
        stmt = stmt.where(ContextNode.read_scope_group_id == f.group_id)

    if f.grade is not None:
        stmt = stmt.where(
            or_(
                ContextNode.min_grade.is_(None),  # keine Stufenangabe = für alle
                and_(
                    ContextNode.min_grade <= f.grade,
                    ContextNode.max_grade >= f.grade,
                ),
            )
        )

    if f.bp_version is not None:
        stmt = stmt.where(ContextNode.metadata_["bp_version"].astext == f.bp_version)

    if f.owner_pseudonym is not None:
        stmt = stmt.where(ContextNode.owner_pseudonym == f.owner_pseudonym)

    if f.q:
        # Titel ODER ein Synonym aus metadata_.aliase (JSONB-Textmatch). So sind
        # Aliase systemweit suchbar (Krücke bis zum echten Alias-Feld am Knoten).
        wie = f"%{f.q}%"
        stmt = stmt.where(
            or_(
                ContextNode.title.ilike(wie),
                ContextNode.metadata_["aliase"].astext.ilike(wie),
            )
        )

    if f.titel:
        stmt = stmt.where(TITEL_NORMALISIERT == f.titel)

    if f.category:
        stmt = stmt.where(ContextNode.category == f.category)

    if f.content_type:
        stmt = stmt.where(ContextNode.content_type.in_(f.content_type))

    if f.exclude_content_type:
        # Knoten ohne content_type (NULL) bleiben erhalten — `NOT IN` verwürfe sie sonst.
        stmt = stmt.where(
            or_(
                ContextNode.content_type.is_(None),
                ContextNode.content_type.notin_(f.exclude_content_type),
            )
        )

    return stmt
