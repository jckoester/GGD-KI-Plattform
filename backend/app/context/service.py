"""Context-Service – öffentliche Schnittstelle des Kontextspeichers.

get_context_for_query() ist die einzige Funktion, die vom Chat-Router aufgerufen wird.
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embedding import enqueue_embedding_job
from app.context.grades import parse_grade_band
from app.context.retrieval import EngagementEntry, get_engagement_context
from app.context.search import Suchprofil, thematisch, vektor_oder_none
from app.context.schemas import CurriculumDraftConfirmed
from app.db.models import (
    AssistantContextAnchor,
    ChatContextNode,
    ContextEdge,
    ContextNode,
    Conversation,
    Group,
    GroupMembership,
    Subject,
)

logger = logging.getLogger(__name__)


# Wie viele Bausteine ein Anker-Assistent aus seinem Teilgraphen in den Prompt bekommt.
# Der Wert stammt aus dem früheren `get_semantic_context(top_k=10)` und ist mit der
# Vereinheitlichung unverändert übernommen worden — er begrenzt die Prompt-Länge, nicht
# die Suchgüte.
_ANKER_TOP_K = 10

_RELATION_LABELS: dict[str, str] = {
    "introduced": "eingeführt",
    "knows": "bekannt",
    "mastered": "beherrscht",
    "struggles_with": "Schwierigkeiten",
}


def _assemble_context(
    semantic_treffer: list[dict],
    engagement_entries: list[EngagementEntry],
    pinned_nodes: list[ContextNode],
) -> str:
    """Den Kontext-Block für den Prompt bauen.

    ``semantic_treffer`` sind Treffer der Suchschicht (Dicts), keine ORM-Knoten: Seit
    ADR-017/AP5 liefert der Anker-Weg dasselbe wie jede andere Suche. Gepinnte Knoten
    kommen weiterhin als ORM-Objekte — sie werden direkt geladen, nicht gesucht.
    """
    sections: list[str] = []

    if semantic_treffer:
        lines = ["## Relevante Lerninhalte\n"]
        for treffer in semantic_treffer:
            meta = treffer.get("metadata") or {}
            breadcrumb = ""
            if "breadcrumb" in meta:
                breadcrumb = " | ".join(meta["breadcrumb"]) + "\n"
            content = treffer.get("content") or ""
            lines.append(f"### {treffer['title']}\n{breadcrumb}{content}\n")
        sections.append("\n".join(lines))

    if engagement_entries:
        lines = ["## Vorwissen dieses Lernenden\n"]
        for entry in engagement_entries:
            label = " / ".join(
                _RELATION_LABELS.get(r, r) for r in entry.relations
            )
            lines.append(f"- **{entry.node.title}** ({label})")
        sections.append("\n".join(lines))

    if pinned_nodes:
        lines = ["## Explizit hinzugefügter Kontext\n"]
        for node in pinned_nodes:
            content = node.content or ""
            lines.append(f"### {node.title}\n{content}\n")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "\n\n---\n\n".join(sections)


async def get_context_for_query(
    assistant_id: int | None,
    pseudonym: str,
    query_text: str,
    chat_id: UUID | None,
    db: AsyncSession,
    rollen: Sequence[str] = (),
) -> str:
    """Assembliert den Kontext-String für einen Chat-Prompt.

    Kombiniert semantische Suche, Engagement-Retrieval und explizit gepinnte Knoten.
    Pinned nodes werden unabhängig von einem Assistenten oder retrieval_scope geladen.

    ``rollen`` geht in die Sichtbarkeitsprüfung der Suchschicht ein. Ohne Angabe gilt die
    strengere Nicht-Admin-Regel — im Zweifel weniger zu zeigen ist die richtige Richtung.
    """
    # Retrieval-Scope-Anker nur laden wenn ein Assistent aktiv ist
    anchor_ids: list[UUID] = []
    if assistant_id is not None:
        result = await db.execute(
            sa.select(AssistantContextAnchor.node_id)
            .where(
                AssistantContextAnchor.assistant_id == assistant_id,
                AssistantContextAnchor.role == "retrieval_scope",
            )
        )
        anchor_ids = [row[0] for row in result.all()]

    # Gepinnte Knoten immer laden (unabhängig von retrieval_scope)
    pinned_nodes: list[ContextNode] = []
    if chat_id is not None:
        pinned_result = await db.execute(
            sa.select(ContextNode)
            .join(ChatContextNode, ChatContextNode.node_id == ContextNode.id)
            .where(
                ChatContextNode.chat_id == chat_id,
                ContextNode.status == "active",
            )
        )
        pinned_nodes = list(pinned_result.scalars().all())

    # Semantische Suche nur wenn retrieval_scope-Anker vorhanden
    semantic_treffer: list[dict] = []
    engagement_entries: list[EngagementEntry] = []
    if anchor_ids:
        # Der Jahrgang entscheidet, welche BP-Fassung gilt, solange eine neue
        # Edition nach oben wächst. Ohne Gruppenbezug bleibt er None — die Suche
        # fasst Fassungs-Dubletten dann nur zusammen, statt zu filtern.
        grade = await _conversation_grade(db, chat_id)
        # Profil „Anker-Assistent": dieselbe Schicht wie überall, nur mit Teilgraph.
        #
        # Aufgerufen wird `thematisch()` direkt, nicht `suche()`: Dieser Kontext wandert
        # **ungefragt** in den Prompt, nicht in eine Antwort an das Modell. Ein
        # Ergebnisumschlag mit beschrifteten Abschnitten hätte hier niemanden, der ihn
        # liest — und die Identifikation trüge im Teilgraphen wenig bei, wo ohnehin
        # jeder Knoten zum Gegenstand des Assistenten gehört.
        #
        # `mit_metadaten`, weil der Breadcrumb in den Prompt gehört: Er ordnet eine
        # Kompetenz in ihren Bildungsplan ein.
        profil = Suchprofil(
            pseudonym=pseudonym,
            rollen=rollen,
            anchor_ids=tuple(anchor_ids),
            grade=grade,
            thematisch=_ANKER_TOP_K,
            mit_metadaten=True,
        )
        # ⚠️ **Kein `gather` über zwei Datenbankaufrufe.** Bis 09/2026 liefen thematische
        # Suche und Lernstand hier nebenläufig auf **derselben** `AsyncSession` — das
        # ging nur gut, weil die Suche zuerst auf das Embedding wartete und dem
        # Lernstand damit die Datenbank überließ. Ein schnelleres Embedding (Cache,
        # anderer Anbieter) hätte beide gleichzeitig auf die Session gelassen, und die
        # Anfrage wäre mit `IllegalStateChangeError` gescheitert.
        #
        # Überlappt wird stattdessen ausdrücklich das, was überlappt werden darf: der
        # Netzaufruf. Er startet zuerst und läuft, während der Lernstand abgefragt wird.
        vektor_task = asyncio.create_task(vektor_oder_none(query_text))
        try:
            engagement_entries = await get_engagement_context(anchor_ids, pseudonym, db)
        except BaseException:
            vektor_task.cancel()
            raise
        thematisch_abschnitt = await thematisch(
            query_text, profil, db, vektor=await vektor_task
        )
        semantic_treffer = thematisch_abschnitt.treffer

    base = _assemble_context(semantic_treffer, engagement_entries, pinned_nodes)

    # UP-7: Planungs-Block „Aktueller Unterricht" für Conversations mit Gruppenbezug.
    planning_block = await _planning_block(db, chat_id)
    if planning_block:
        return f"{planning_block}\n\n{base}" if base else planning_block
    return base


async def _conversation_grade(db: AsyncSession, chat_id: UUID | None) -> int | None:
    """Jahrgang der Konversation über ihre Unterrichtsgruppe — sonst ``None``."""
    if chat_id is None:
        return None
    conv = await db.get(Conversation, chat_id)
    if conv is None or not isinstance(conv.group_id, int):
        return None

    # Lokaler Import vermeidet eine Modul-Zyklus-Abhängigkeit context ↔ planning.
    from app.planning.curriculum_resolver import group_grade

    return await group_grade(db, conv.group_id)


async def _group_label(db: AsyncSession, group_id: int) -> str:
    group = await db.get(Group, group_id)
    if group is None:
        return "Unterricht"
    subj = await db.get(Subject, group.subject_id) if group.subject_id else None
    if subj and subj.name.lower() not in (group.name or "").lower():
        return f"{subj.name}, {group.name}"
    return group.name


async def _planning_block(db: AsyncSession, chat_id: UUID | None) -> str | None:
    """Markdown-Block aus den Planungsdaten der Conversation-Gruppe (UP-7)."""
    if chat_id is None:
        return None
    conv = await db.get(Conversation, chat_id)
    if conv is None or not isinstance(conv.group_id, int):
        return None

    # Lokaler Import vermeidet eine Modul-Zyklus-Abhängigkeit context ↔ planning.
    from datetime import date as _date

    from app.planning.student_context import (
        get_current_topic,
        get_exam_scope,
        render_topic_block,
    )

    today = _date.today()
    topic = await get_current_topic(db, conv.group_id, today)
    exam = await get_exam_scope(db, conv.group_id, today=today)
    if topic is None and exam is None:
        return None
    return render_topic_block(topic, await _group_label(db, conv.group_id), exam)


# -- KS-Phase-6 Curriculum Import Logic -----------------------------------------


@dataclass
class ImportStats:
    """Statistiken für den Curriculum-Import."""
    curriculum_count: int = 0
    kapitel_count: int = 0
    lernsequenz_count: int = 0
    edge_count: int = 0
    archived_count: int = 0
    warnings: list[str] = field(default_factory=list)


async def get_subject_id_by_code(db: AsyncSession, fach_code: str) -> int | None:
    """Lädt subject_id aus DB für den gegebenen fach_code.

    Match über die Spalte subjects.fach_code (Bildungsplan-Kürzel, z. B. 'M', 'CH'),
    normalisiert auf Großschreibung — nicht über den Slug.
    """
    from app.db.models import Subject
    if not fach_code:
        return None
    result = await db.execute(
        sa.select(Subject.id).where(
            Subject.fach_code == fach_code.strip().upper(),
        )
    )
    row = result.fetchone()
    return row[0] if row else None


async def get_fachplan_node(db: AsyncSession, fachplan_id: str) -> ContextNode | None:
    """Lädt den fachplan-Knoten für die gegebene fachplan_id."""
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "fachplan",
            ContextNode.metadata_["fachplan_id"].astext == fachplan_id,
            ContextNode.status == "active",
        )
    )
    return result.scalars().first()


async def resolve_fachplan(
    db: AsyncSession,
    *,
    fachplan_id: str | None = None,
    bp_id: str | None = None,
    subject_id: int | None = None,
    bp_version: str | None = None,
) -> ContextNode | None:
    """Den Fachplan-Knoten über die belastbarste verfügbare Angabe finden.

    Nötig, weil `fachplan_id` **in der Praxis leer ist**: Vom Scraper importierte
    Fachplan-Knoten tragen `bp_id` (`BP2016BW_ALLG_GYM_CH.V2`) und `bp_version`, aber kein
    `fachplan_id` — geprüft an allen 28 Knoten der Dev-Instanz. Ein Curriculum-Export
    schrieb deshalb `fachplan_id: null`, und der Wiederimport scheiterte mit der
    irreführenden Meldung „Bildungsplan-Import fehlt?", obwohl der Plan vorhanden war.

    Reihenfolge — von der eindeutigsten zur schwächsten Angabe:

    1. `fachplan_id` (Alt-/Testdaten, dort eindeutig),
    2. `bp_id` (der Bezeichner echter Knoten, über Instanzen hinweg stabil),
    3. Fach + Edition — die Rückfallebene für Exporte, die vor `bp_id` entstanden sind.

    Stufe 3 ist bewusst die letzte: Sie ist nur eindeutig, solange ein Fach je Edition
    genau einen Fachplan hat. Trifft sie mehrere, wird **keiner** gewählt (siehe unten) —
    lieber ein klarer Fehler als das falsche Curriculum am falschen Plan.
    """
    if fachplan_id:
        node = await get_fachplan_node(db, fachplan_id)
        if node:
            return node

    if bp_id:
        result = await db.execute(
            sa.select(ContextNode).where(
                ContextNode.content_type == "fachplan",
                ContextNode.metadata_["bp_id"].astext == bp_id,
                ContextNode.status == "active",
            )
        )
        node = result.scalars().first()
        if node:
            return node

    if subject_id is not None and bp_version:
        result = await db.execute(
            sa.select(ContextNode).where(
                ContextNode.content_type == "fachplan",
                ContextNode.subject_id == subject_id,
                ContextNode.metadata_["bp_version"].astext == bp_version,
                ContextNode.status == "active",
            )
        )
        treffer = result.scalars().all()
        if len(treffer) == 1:
            return treffer[0]
        if len(treffer) > 1:
            logger.warning(
                "Fach %s / Edition %s hat %d Fachpläne — nicht eindeutig auflösbar.",
                subject_id, bp_version, len(treffer),
            )

    return None


async def fachplan_diagnose(
    db: AsyncSession, subject_id: int | None, bp_version: str | None
) -> str:
    """Beschreibt, **warum** kein Fachplan gefunden wurde — für die Fehlermeldung.

    Die frühere Meldung fragte pauschal „Ist der Bildungsplan dieses Fachs importiert?"
    und schickte damit in die falsche Richtung: Der häufigste Fall ist, dass der Plan sehr
    wohl da ist, aber in einer **anderen Edition** aktiv — oder dass genau die gesuchte
    Edition **archiviert** wurde, weil später eine andere importiert wurde. Beides sieht
    man der Datenbank sofort an; man muss es nur sagen.
    """
    if subject_id is None:
        return "Das Fach ist in dieser Instanz nicht angelegt."

    rows = (
        await db.execute(
            sa.select(
                ContextNode.metadata_["bp_version"].astext, ContextNode.status
            ).where(
                ContextNode.content_type == "fachplan",
                ContextNode.subject_id == subject_id,
            )
        )
    ).all()

    if not rows:
        return (
            "Für dieses Fach ist überhaupt kein Bildungsplan importiert "
            "(siehe docs/runbooks/bildungsplan-import.md)."
        )

    aktiv = sorted({v for v, s in rows if s == "active" and v})
    archiviert = sorted({v for v, s in rows if s != "active" and v})

    if bp_version and bp_version in archiviert:
        return (
            f"Die Edition '{bp_version}' ist in dieser Instanz vorhanden, aber "
            f"**archiviert** — vermutlich, weil danach eine andere Edition importiert "
            f"wurde. Aktiv ist derzeit: {', '.join(aktiv) or '(keine)'}. Entweder die "
            f"passende Edition importieren (`bildungsplan_suffix` in subjects.yaml prüfen) "
            f"oder den Import mit der aktiven Edition erzwingen."
        )

    return (
        f"Für dieses Fach ist die Edition '{bp_version}' nicht aktiv. "
        f"Aktiv ist: {', '.join(aktiv) or '(keine)'}"
        + (f"; archiviert: {', '.join(archiviert)}" if archiviert else "")
        + "."
    )


async def get_subject_department_group_id(db: AsyncSession, subject_id: int) -> int | None:
    """Lädt eine Fachschafts-Gruppen-ID für ein Fach (deterministisch: kleinste id).

    Wird für `write_scope_group_id` neuer Curriculum-Knoten genutzt. `ORDER BY id`
    sorgt für eine stabile Auswahl, falls für ein Fach mehrere subject_department-
    Gruppen existieren (z. B. Alt-/Doppelgruppen mit abweichender sso_group_id aus
    früheren Sync-Ständen). Für die **Berechtigungsprüfung** nicht diese eine Gruppe
    verwenden, sondern `is_subject_department_member` (prüft Mitgliedschaft über
    *alle* Fachschaftsgruppen des Fachs).
    """
    result = await db.execute(
        sa.select(Group.id).where(
            Group.subject_id == subject_id,
            Group.type == "subject_department",
        ).order_by(Group.id).limit(1)
    )
    row = result.fetchone()
    return row[0] if row else None


async def subject_has_department_group(db: AsyncSession, subject_id: int) -> bool:
    """True, wenn für das Fach überhaupt eine Fachschaftsgruppe existiert."""
    return await get_subject_department_group_id(db, subject_id) is not None


async def is_subject_department_member(
    db: AsyncSession, subject_id: int, pseudonym: str
) -> bool:
    """Ist der/die Nutzer:in Mitglied **irgendeiner** Fachschaftsgruppe des Fachs?

    Robust gegen mehrere subject_department-Gruppen pro Fach: Es zählt allein, ob
    eine Mitgliedschaft in *einer* von ihnen besteht — nicht, welche Gruppe zuerst
    gefunden wird. Das war die Schwäche der früheren „eine Gruppe per LIMIT 1, dann
    Mitgliedschaft prüfen"-Logik (sie konnte die *falsche* Doppelgruppe treffen).
    """
    result = await db.execute(
        sa.select(GroupMembership.group_id)
        .join(Group, Group.id == GroupMembership.group_id)
        .where(
            Group.subject_id == subject_id,
            Group.type == "subject_department",
            GroupMembership.pseudonym == pseudonym,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


_LP_PRAEFIX = re.compile(r"^\(?L\)?\s+", re.IGNORECASE)


def normalize_lp_code(value: str | None) -> str:
    """Leitperspektiven-Kürzel vereinheitlichen: ``"(L) BO"``/``"L BO"`` → ``"BO"``.

    Die Bildungsplan-Texte markieren Leitperspektiven als „(L) BO"; in Entwurfsdaten
    taucht die Form mit vorangestelltem „L " auf. Das Leerzeichen im Muster ist wichtig:
    Ohne es würde ``LFDB`` (Leitfaden Demokratiebildung) zu ``FDB`` verstümmelt.
    """
    if not value:
        return ""
    return _LP_PRAEFIX.sub("", str(value).strip()).strip().upper()


def leitperspektive_code(metadata: dict | None) -> str:
    """Kürzel einer Leitperspektive — aus ``code``, sonst aus der ``bp_id`` abgeleitet.

    ⚠️ **`code` ist in echten Daten immer leer.** Der Scraper schreibt das Feld nicht;
    geprüft an allen 7 Leitperspektiven und 48 Aspekten der Dev-Instanz: null Treffer.
    Ein Export übersetzte LP-Verweise deshalb nie in portable Kürzel, und der Import löste
    Kürzel nie zu Knoten auf — beides scheiterte an demselben nie gefüllten Feld.

    Statt das Feld nachzupflegen (Re-Scrape, Re-Import, ein zweiter Ort für dieselbe
    Wahrheit) wird es aus der ohnehin vorhandenen `bp_id` gewonnen:
    ``BP2016BW_ALLG_LP_PG`` → ``PG``. Wirkt sofort auf Bestandsdaten.
    """
    meta = metadata or {}
    if meta.get("code"):
        return normalize_lp_code(meta["code"])
    bp_id = meta.get("bp_id") or ""
    if "_LP_" in bp_id:
        return normalize_lp_code(bp_id.rsplit("_LP_", 1)[-1])
    return ""


def _normalize_ref(ref: str) -> str:
    """Normalisiert eine Referenz für toleranten Vergleich.
    
    Entfernt Leerzeichen, vereinheitlicht Klammern und Punkte.
    Wird für resolve_ik_node und resolve_pk_node verwendet.
    """
    if not ref:
        return ""
    # Leerzeichen entfernen
    ref = ref.replace(" ", "")
    # Klammern vereinheitlichen
    ref = ref.replace("[", "(").replace("]", ")")
    # Doppelte Punkte entfernen
    ref = ref.replace(".(", "(").replace(")", ".")
    return ref


def _fach_filter(subject_id: int | None):
    """Zusatzbedingung für das Fach — oder nichts, wenn keines angegeben ist."""
    if subject_id is None:
        return sa.true()
    return ContextNode.subject_id == subject_id


def _editions_filter(bp_version: str | None):
    """Zusatzbedingung für die Fassung — oder nichts, wenn keine gefordert ist.

    Während eines Editionswechsels sind **mehrere Fassungen gleichzeitig aktiv**; das ist
    der Normalfall, nicht die Ausnahme. Bei Mathematik kommen 316 von 319 IK-Nummern in
    V2 *und* V3 vor. Ohne diese Bedingung entscheidet die Reihenfolge in der Datenbank,
    welche Fassung getroffen wird — ein Curriculum für Klasse 9 könnte stillschweigend an
    V3-Kompetenzen hängen.

    Bewusst **ohne Rückfall** auf eine andere Fassung: Findet sich die Nummer in der
    verlangten Fassung nicht, ist das eine Lücke, die der Aufrufer melden soll. Eine
    Auflösung aus der falschen Fassung wäre nicht zu bemerken.
    """
    if not bp_version:
        return sa.true()
    return ContextNode.metadata_["bp_version"].astext == bp_version


async def resolve_ik_node(
    db: AsyncSession, subject_id: int, nr: str, bp_version: str | None = None
) -> UUID | None:
    """Löst eine IK-Nummer zu einer node_id auf (mit toleranter Normalisierung).

    ⚠️ Wie bei :func:`resolve_pk_node` tragen **zwei Felder** dieselbe Nummer: Vom
    Scraper importierte Knoten führen sie als `kompetenz_nr` (Dev-Instanz: 5141 Knoten),
    `nr` benutzen nur Testdaten und Alt-Bestände (0 Knoten). Gesucht wurde bislang nur
    `nr` — der Wiederimport eines exportierten Curriculums verlor dadurch seine
    Kompetenzverweise, obwohl die Knoten vorhanden waren.
    """
    normalized_nr = _normalize_ref(nr)

    # Erst: exakter Vergleich auf beiden Feldern
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "ik_kompetenz",
            ContextNode.subject_id == subject_id,
            sa.or_(
                ContextNode.metadata_["nr"].astext == nr,
                ContextNode.metadata_["kompetenz_nr"].astext == nr,
            ),
            ContextNode.status == "active",
            _editions_filter(bp_version),
        )
    )
    row = result.fetchone()
    if row:
        return row[0]

    # Fallback: normalisierter Vergleich
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "ik_kompetenz",
            ContextNode.subject_id == subject_id,
            ContextNode.status == "active",
            _editions_filter(bp_version),
        )
    )
    for (node,) in result.fetchall():
        meta = node.metadata_ or {}
        for feld in ("nr", "kompetenz_nr"):
            if _normalize_ref(meta.get(feld, "")) == normalized_nr:
                return node.id

    return None


async def resolve_pk_node(
    db: AsyncSession,
    pk_id: str,
    subject_id: int | None = None,
    bp_version: str | None = None,
) -> UUID | None:
    """Löst eine PK-Nummer zu einer node_id auf (mit toleranter Normalisierung).

    ⚠️ **``subject_id`` angeben.** Prozessbezogene Kompetenzen sind je Fach von 2.1.1 an
    durchnummeriert — ``2.1.1`` gibt es in 24 Fächern. Ohne Fachbezug entscheidet die
    Reihenfolge in der Datenbank, welches getroffen wird. Beim Wiederimport eines echten
    Mathematik-Curriculums landeten so **54 von 65 PK-Kanten in fremden Fächern**
    (Gemeinschaftskunde, Musik, Informatik, Sport …), ohne jede Meldung. Der Parameter ist
    aus Rücksicht auf Bestandsaufrufe optional — wer ihn wegläßt, bekommt weiterhin das
    alte, unzuverlässige Verhalten.

    ⚠️ **Zwei Felder tragen dieselbe Nummer.** Vom Scraper importierte PK-Knoten führen
    sie als `kompetenz_nr` (in der Dev-Instanz: 755 Knoten), `pk_id` benutzen nur
    Testdaten und Alt-Bestände (0 Knoten). `load_curriculum_tree` liest bereits
    `kompetenz_nr` — hier wurde bislang nur `pk_id` gesucht.

    Folge dieser Asymmetrie: Der Export schrieb Nummern heraus, die der Wiederimport
    nicht auflösen konnte. Ein echtes Curriculum verlor dabei **69 PK-Verweise** — beim
    Re-Import in dieselbe Instanz, aus der es stammte. Deshalb werden jetzt beide Felder
    berücksichtigt.
    """
    normalized_pk = _normalize_ref(pk_id)

    # Erst: exakter Vergleich auf beiden Feldern
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "pk_kompetenz",
            sa.or_(
                ContextNode.metadata_["pk_id"].astext == pk_id,
                ContextNode.metadata_["kompetenz_nr"].astext == pk_id,
            ),
            ContextNode.status == "active",
            _fach_filter(subject_id),
            _editions_filter(bp_version),
        )
    )
    row = result.fetchone()
    if row:
        return row[0]

    # Fallback: normalisierter Vergleich
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "pk_kompetenz",
            ContextNode.status == "active",
            _fach_filter(subject_id),
            _editions_filter(bp_version),
        )
    )
    for (node,) in result.fetchall():
        meta = node.metadata_ or {}
        for feld in ("pk_id", "kompetenz_nr"):
            if _normalize_ref(meta.get(feld, "")) == normalized_pk:
                return node.id

    return None


async def resolve_leitperspektive_node(db: AsyncSession, lp_code: str) -> UUID | None:
    """Löst ein Leitperspektiven-Kürzel zu einer node_id auf.

    Verglichen wird gegen :func:`leitperspektive_code` — also gegen `code` **oder** das
    aus der `bp_id` abgeleitete Kürzel. Die frühere Fassung fragte ausschließlich
    `metadata->>'code'` ab und traf damit nie (das Feld ist in echten Daten leer).

    In Python statt in SQL, weil die Ableitung sonst als String-Operation in die Abfrage
    müsste — bei sieben Zeilen ist das die falsche Sparsamkeit.
    """
    gesucht = normalize_lp_code(lp_code)
    if not gesucht:
        return None

    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == "leitperspektive",
            ContextNode.status == "active",
        )
    )
    for node in result.scalars().all():
        if leitperspektive_code(node.metadata_) == gesucht:
            return node.id
    return None


async def resolve_leitperspektive_aspekt_node(db: AsyncSession, bp_id: str) -> UUID | None:
    """Löst Leitperspektive-Aspekt-bp_id (z. B. 'BNE_01') zu node_id auf."""
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.content_type == "leitperspektive_aspekt",
            ContextNode.metadata_["bp_id"].astext == bp_id,
            ContextNode.status == "active",
        )
    )
    row = result.fetchone()
    return row[0] if row else None


async def resolve_ik_node_by_fach_code(
    db: AsyncSession, fach_code: str, nr: str, bp_version: str | None = None
) -> UUID | None:
    """Löst Cross-Fach-IK via (fach_code, nr) auf — bei Bedarf fassungsgenau.

    ``bp_version`` ist die Fassung des **verweisenden** Curriculums: Wer aus einem
    V2-Curriculum auf Physik verweist, meint die Physik-Fassung, die derselbe Jahrgang
    liest. Ohne Angabe bleibt es bei der alten, fassungsblinden Suche.
    """
    # subject_id aus fach_code (Spalte heißt fach_code; Konvention: Großschreibung)
    if not fach_code:
        return None
    result = await db.execute(
        sa.text("SELECT id FROM subjects WHERE fach_code = :code LIMIT 1"),
        {"code": fach_code.strip().upper()},
    )
    row = result.fetchone()
    if not row:
        return None
    return await resolve_ik_node(db, row[0], nr, bp_version)


# ── Code-Token → UUID-Token Übersetzer (für Re-Import) ───────────────────────

_LP_CODE_TOKEN  = re.compile(r'@\[([^\]]*)\]\(lp:([^)]+)\)')
_LPA_CODE_TOKEN = re.compile(r'@\[([^\]]*)\]\(lpa:([^)]+)\)')

# Die Kompetenznummer darf selbst Klammern enthalten — in Mathematik und Physik ist
# `3.4.3(2)` die Regel, nicht die Ausnahme. Ein einfaches `[^)]+` endet dann an der
# *inneren* Klammer: Gesucht wurde `3.4.3(2`, gefunden nichts, und im Text blieb eine
# verwaiste `)` zurück. Deshalb erlaubt die Nummer eine Ebene ausgeglichener Klammern.
# Fächer wie Ethik mit `2.1.1` haben den Fehler nie ausgelöst — daher fiel er erst an
# einem echten Mathematik-Curriculum auf.
_IK_CODE_TOKEN  = re.compile(
    r'#\[([^\]]*)\]\(ik:([^/:()]+):((?:[^()]|\([^()]*\))*)\)'
)
_NODE_UUID_TOKEN = re.compile(r'@\[([^\]]*)\]\(node:[0-9a-f-]{36}\)')


async def hinweise_code_to_uuid(
    text: str,
    db: AsyncSession,
    warnings: list[str],
    context_label: str = "",
    bp_version: str | None = None,
) -> str:
    """Übersetzt Code-Token im Hinweise-Feld zurück in UUID-Token.

    Verarbeitet: lp:<code>, lpa:<bp_id>, ik:<fach>:<nr>.
    node:<uuid> (Material) bleibt unverändert.
    Unbekannte Tokens werden als Freitext belassen + Warnung.
    """
    if not text:
        return text

    all_matches: list[tuple[re.Match, str]] = []
    for pattern, kind in [
        (_LP_CODE_TOKEN, "lp"),
        (_LPA_CODE_TOKEN, "lpa"),
        (_IK_CODE_TOKEN, "ik"),
    ]:
        for m in pattern.finditer(text):
            all_matches.append((m, kind))
    if not all_matches:
        return text
    all_matches.sort(key=lambda x: x[0].start())

    parts = []
    last = 0
    for m, kind in all_matches:
        parts.append(text[last:m.start()])
        label = m.group(1)
        if kind == "lp":
            code = m.group(2)
            uid = await resolve_leitperspektive_node(db, code)
            if uid:
                parts.append(f"@[{label}](lp:{uid})")
            else:
                warnings.append(f"LP '{code}' nicht gefunden{' in ' + context_label if context_label else ''}")
                parts.append(m.group(0))
        elif kind == "lpa":
            bp_id = m.group(2)
            uid = await resolve_leitperspektive_aspekt_node(db, bp_id)
            if uid:
                parts.append(f"@[{label}](lpa:{uid})")
            else:
                warnings.append(f"LP-Aspekt '{bp_id}' nicht gefunden{' in ' + context_label if context_label else ''}")
                parts.append(m.group(0))
        elif kind == "ik":
            fach_code = m.group(2)
            nr = m.group(3)
            uid = await resolve_ik_node_by_fach_code(db, fach_code, nr, bp_version)
            if uid:
                parts.append(f"#[{label}](ik:{uid})")
            else:
                fassung = f" in Fassung {bp_version}" if bp_version else ""
                warnings.append(
                    f"Cross-IK '{fach_code}:{nr}'{fassung} nicht gefunden"
                    f"{' in ' + context_label if context_label else ''}"
                )
                parts.append(m.group(0))
        last = m.end()
    parts.append(text[last:])
    return "".join(parts)


async def material_resolve_nodes(
    text: str,
    db: AsyncSession,
    warnings: list[str],
    context_label: str = "",
) -> list[UUID]:
    """Extrahiert UUIDs aus Material-node-Token und prüft Existenz.

    Gibt Liste gültiger node_ids zurück; fehlende → Warnung.
    """
    node_token = re.compile(r'@\[[^\]]*\]\(node:([0-9a-f-]{36})\)')
    valid_ids = []
    for m in node_token.finditer(text or ""):
        uid_str = m.group(1)
        try:
            uid = UUID(uid_str)
        except ValueError:
            continue
        result = await db.execute(
            sa.select(ContextNode.id).where(
                ContextNode.id == uid, ContextNode.status == "active"
            )
        )
        if result.fetchone():
            valid_ids.append(uid)
        else:
            warnings.append(
                f"Material-Knoten '{uid_str}' nicht gefunden"
                f"{' in ' + context_label if context_label else ''} – Token bleibt erhalten"
            )
    return valid_ids


async def get_or_create_node(
    db: AsyncSession,
    category: str,
    content_type: str,
    import_key: str,
    data: dict[str, Any],
) -> tuple[UUID, bool]:
    """Holt existierenden Knoten via import_key oder erstellt neuen.
    
    Rückgabe: (node_id, was_created)
    """
    # Existing node via import_key suchen
    result = await db.execute(
        sa.select(ContextNode.id).where(
            ContextNode.metadata_["import_key"].astext == import_key
        )
    )
    row = result.fetchone()
    
    if row:
        node_id = row[0]
        # Update existing node
        update_data = {}
        if "category" in data:
            update_data["category"] = data["category"]
        if "content_type" in data:
            update_data["content_type"] = data["content_type"]
        if "title" in data:
            update_data["title"] = data["title"]
        if "content" in data:
            update_data["content"] = data["content"]
            update_data["embedding"] = None  # Reset embedding wenn content sich ändert
        if "read_scope" in data:
            update_data["read_scope"] = data["read_scope"]
        if "write_scope" in data:
            update_data["write_scope"] = data["write_scope"]
        if "write_scope_group_id" in data:
            update_data["write_scope_group_id"] = data["write_scope_group_id"]
        if "subject_id" in data:
            update_data["subject_id"] = data["subject_id"]
        if "min_grade" in data:
            update_data["min_grade"] = data["min_grade"]
        if "max_grade" in data:
            update_data["max_grade"] = data["max_grade"]
        if "metadata_" in data:
            update_data["metadata_"] = data["metadata_"]
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        await db.execute(
            sa.update(ContextNode).where(ContextNode.id == node_id).values(**update_data)
        )
        return node_id, False
    
    # Create new node
    node_id = UUID(str(uuid.uuid4()))
    node_data = {
        "id": node_id,
        "category": data.get("category", category),
        "content_type": data.get("content_type", content_type),
        "title": data.get("title", ""),
        "content": data.get("content"),
        "read_scope": data.get("read_scope", "school"),
        "write_scope": data.get("write_scope", "private"),
        "write_scope_group_id": data.get("write_scope_group_id"),
        "subject_id": data.get("subject_id"),
        "min_grade": data.get("min_grade"),
        "max_grade": data.get("max_grade"),
        "metadata_": data.get("metadata_", {}),
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    # Setze import_key in metadata
    if "metadata_" not in node_data or not node_data["metadata_"]:
        node_data["metadata_"] = {}
    node_data["metadata_"]["import_key"] = import_key
    
    db.add(ContextNode(**node_data))
    await db.flush()  # FK-Constraint bei nachfolgenden Edge-Inserts sichern
    return node_id, True


async def create_edge(
    db: AsyncSession,
    from_node_id: UUID,
    to_node_id: UUID,
    relation: str,
    metadata: dict | None = None,
) -> None:
    """Erstellt eine Kante zwischen zwei Knoten (idempotent)."""
    existing = await db.execute(
        sa.select(ContextEdge.id).where(
            ContextEdge.from_node_id == from_node_id,
            ContextEdge.to_node_id == to_node_id,
            ContextEdge.relation == relation,
        )
    )
    if existing.fetchone():
        return
    edge = ContextEdge(
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        relation=relation,
        metadata_=metadata or {},
    )
    db.add(edge)
    await db.flush()


async def archive_orphaned_curriculum_nodes(
    db: AsyncSession,
    import_key_base: str,
    import_keys: set[str],
) -> int:
    """Kapitel/Lernsequenzen archivieren, die dieser Import nicht mehr erzeugt.

    Ohne das überlebt ein aus dem YAML **gelöschtes** Kapitel jeden Re-Import: Der Import
    legt an und aktualisiert, aber räumt nicht ab — das entfernte Kapitel hängt weiter am
    Curriculum und erscheint im Baum.

    ⚠️ **Zweifach eingegrenzt**, und beides ist wesentlich:

    1. Auf den **Schlüsselpräfix dieses Curriculums** (`import_key_base`). Die frühere
       Fassung durchsuchte die **ganze Tabelle**: Jeder aktive Curriculum-, Kapitel- und
       Lernsequenz-Knoten, dessen `import_key` nicht in der übergebenen Menge stand, wurde
       archiviert — also **sämtliche anderen Curricula der Instanz**. Aufgerufen wurde sie
       nie; als benannte, plausibel aussehende Funktion war sie eine Einladung. Genau
       dieselbe Bauart hat beim Bildungsplan-Import zwei Fächer stillgelegt.
    2. Auf Knoten, die **dieser Importpfad selbst angelegt hat**. Im Editor entstandene
       Kapitel tragen `temp_<uuid>` als Schlüssel und passen nicht auf den Präfix — sie
       bleiben unberührt. Ein YAML-Import darf die Handarbeit einer Lehrkraft nicht
       stillschweigend abräumen, auch wenn das YAML sie nicht kennt.

    Der Curriculum-Knoten selbst wird nie archiviert; er ist das Ziel des Imports.
    """
    if not import_key_base:
        return 0

    result = await db.execute(
        sa.select(ContextNode.id, ContextNode.metadata_["import_key"].astext).where(
            ContextNode.content_type.in_(["kapitel", "lernsequenz"]),
            ContextNode.status == "active",
            ContextNode.metadata_["import_key"].isnot(None),
        )
    )

    archived = 0
    for node_id, schluessel in result.all():
        if not schluessel or not schluessel.startswith(f"{import_key_base}_"):
            continue                       # fremdes Curriculum oder Editor-Knoten
        if schluessel in import_keys:
            continue                       # kommt im Import weiterhin vor
        logger.info("Archiviere verwaisten Curriculum-Knoten: %s", schluessel)
        await db.execute(
            sa.update(ContextNode)
            .where(ContextNode.id == node_id)
            .values(status="archived", archived_at=datetime.now(timezone.utc))
        )
        archived += 1

    return archived


async def load_curriculum_tree(db: AsyncSession, curriculum_id: UUID) -> dict | None:
    """Lädt das vollständige Curriculum als verschachtelten Dict (ohne Berechtigungsprüfung).

    Gibt None zurück wenn das Curriculum nicht existiert oder inaktiv ist.
    Der zurückgegebene Dict enthält `read_scope` und `owner_pseudonym` für die
    Berechtigungsprüfung im Router.
    """
    result = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.id == curriculum_id,
            ContextNode.status == "active",
            ContextNode.content_type == "curriculum",
        )
    )
    curriculum = result.scalar_one_or_none()
    if not curriculum:
        return None

    # Kapitel laden
    result = await db.execute(
        sa.select(ContextNode)
        .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
        .where(
            ContextEdge.to_node_id == curriculum_id,
            ContextEdge.relation == "part_of",
            ContextNode.content_type == "kapitel",
            ContextNode.status == "active",
        )
        .order_by(ContextNode.metadata_["reihenfolge"].as_integer())
    )
    kapitel_nodes = result.scalars().all()

    kapitel_list = []
    for kap_node in kapitel_nodes:
        result = await db.execute(
            sa.select(ContextNode)
            .join(ContextEdge, ContextEdge.from_node_id == ContextNode.id)
            .where(
                ContextEdge.to_node_id == kap_node.id,
                ContextEdge.relation == "part_of",
                ContextNode.content_type == "lernsequenz",
                ContextNode.status == "active",
            )
            .order_by(ContextNode.metadata_["reihenfolge"].as_integer())
        )
        lernsequenz_nodes = result.scalars().all()

        lernsequenzen_list = []
        for ls_node in lernsequenz_nodes:
            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title,
                           n.metadata->>'kompetenz_nr' AS nr,
                           e.metadata->>'partiell' AS partiell
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'references'
                      AND n.content_type = 'ik_kompetenz'
                    -- Status bewusst NICHT gefiltert: Curricula referenzieren teils
                    -- durch BP-Re-Import archivierte IK-Knoten; deren Volltext soll für
                    -- Tooltip/Export erhalten bleiben (Kante von genau dieser Lernsequenz).
                """),
                {"ls_id": str(ls_node.id)},
            )
            ik_refs = [
                {
                    "node_id": str(row.id),
                    "title": row.title,
                    "nr": row.nr,
                    "partiell": row.partiell == "true",
                }
                for row in result.mappings().all()
            ]

            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title, n.metadata->>'kompetenz_nr' AS pk_id
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'develops'
                      AND n.content_type = 'pk_kompetenz'
                    -- Status bewusst NICHT gefiltert (siehe IK-Query oben).
                """),
                {"ls_id": str(ls_node.id)},
            )
            pk_refs = [
                {"node_id": str(row.id), "title": row.title, "pk_id": row.pk_id}
                for row in result.mappings().all()
            ]

            result = await db.execute(
                sa.text("""
                    SELECT n.id, n.title, n.metadata->>'code' AS lp_code
                    FROM context_nodes n
                    JOIN context_edges e ON e.to_node_id = n.id
                    WHERE e.from_node_id = :ls_id
                      AND e.relation = 'references'
                      AND n.content_type = 'leitperspektive'
                    -- Status bewusst NICHT gefiltert (siehe IK-Query oben).
                """),
                {"ls_id": str(ls_node.id)},
            )
            leitperspektive_refs = [
                {"node_id": str(row.id), "title": row.title, "lp_code": row.lp_code}
                for row in result.mappings().all()
            ]

            lernsequenzen_list.append({
                "id": ls_node.id,
                "title": ls_node.title,
                "metadata": ls_node.metadata_ or {},
                "ik_refs": ik_refs,
                "pk_refs": pk_refs,
                "leitperspektive_refs": leitperspektive_refs,
            })

        kapitel_list.append({
            "id": kap_node.id,
            "title": kap_node.title,
            "metadata": kap_node.metadata_ or {},
            "content": kap_node.content,
            "lernsequenzen": lernsequenzen_list,
        })

    return {
        "id": curriculum.id,
        "title": curriculum.title,
        "metadata": curriculum.metadata_ or {},
        "content": curriculum.content,
        "subject_id": curriculum.subject_id,
        "write_scope_group_id": curriculum.write_scope_group_id,
        "read_scope": curriculum.read_scope,
        "owner_pseudonym": curriculum.owner_pseudonym,
        "kapitel": kapitel_list,
    }


async def import_curriculum_from_draft(
    db: AsyncSession,
    payload: CurriculumDraftConfirmed,
    user_pseudonym: str,
) -> tuple[UUID, ImportStats]:
    """Importiert ein Curriculum aus dem bestätigten Zwischenformat.
    
    Dies ist die Kernlogik für Stufe 2 (Persistenz).
    Wird sowohl vom API-Endpunkt als auch vom CLI-Skript aufgerufen.
    
    Rückgabe: (curriculum_id, stats)
    """
    stats = ImportStats()
    
    # Validieren
    if not payload.kapitel:
        raise ValueError("Keine Kapitel in den Import-Daten gefunden")
    
    # Subject laden
    subject_id = await get_subject_id_by_code(db, payload.fach_code)
    if subject_id is None:
        raise ValueError(f"Fach mit fach_code '{payload.fach_code}' nicht gefunden")
    
    # Fachplan laden — über die belastbarste verfügbare Angabe, nicht nur fachplan_id
    fachplan = await resolve_fachplan(
        db,
        fachplan_id=payload.fachplan_id,
        bp_id=payload.bp_id,
        subject_id=subject_id,
        bp_version=payload.bp_version,
    )
    if not fachplan:
        diagnose = await fachplan_diagnose(db, subject_id, payload.bp_version)
        raise ValueError(
            f"Kein Fachplan für Fach '{payload.fach_code}' und Edition "
            f"'{payload.bp_version}' gefunden"
            + (f" (bp_id '{payload.bp_id}')" if payload.bp_id else "")
            + (f" (fachplan_id '{payload.fachplan_id}')" if payload.fachplan_id else "")
            + f". {diagnose}"
        )
    fachplan_id = fachplan.id

    # Fachschafts-Gruppen-ID
    department_group_id = await get_subject_department_group_id(db, subject_id)

    # Import-Key Basis. `fachplan_id` bleibt führend, damit vorhandene Curricula ihren
    # Schlüssel behalten und weiterhin idempotent aktualisiert werden. Fehlt sie — der
    # Normalfall bei echten Daten —, tritt der `bp_id` des aufgelösten Fachplans an ihre
    # Stelle. Ein leerer Präfix („_8") wäre für alle Fächer derselbe und würde beim
    # zweiten Import ein fremdes Curriculum überschreiben.
    schluessel_praefix = (
        payload.fachplan_id
        or (fachplan.metadata_ or {}).get("bp_id")
        or f"fachplan-{fachplan.id}"
    )
    import_key_base = f"{schluessel_praefix}_{payload.jahrgangsstufe}"
    curriculum_import_key = import_key_base
    
    # Alle import_keys sammeln für späteres Archivieren
    all_import_keys: set[str] = set()
    
    # 1. Curriculum-Knoten
    min_grade, max_grade = parse_grade_band(payload.jahrgangsstufe)
    curriculum_data = {
        "category": "knowledge",
        "content_type": "curriculum",
        "title": f"{payload.fach or payload.fach_code} Kl. {payload.jahrgangsstufe}",
        "content": payload.vorwort or "",
        "read_scope": "school",
        "write_scope": "subject" if department_group_id else "school",
        "write_scope_group_id": department_group_id,
        "subject_id": subject_id,
        "min_grade": min_grade,
        "max_grade": max_grade,
        "owner_pseudonym": user_pseudonym,
        "metadata_": {
            "fachplan_id": payload.fachplan_id,
            "bp_version": payload.bp_version,
            "schule": payload.schule,
            "fach_code": payload.fach_code,
            "fach": payload.fach or payload.fach_code,
            "schulart": payload.schulart,
            "jahrgangsstufe": payload.jahrgangsstufe,
            "import_key": curriculum_import_key,
        }
    }
    curriculum_id, created = await get_or_create_node(
        db, "knowledge", "curriculum", curriculum_import_key, curriculum_data
    )
    all_import_keys.add(curriculum_import_key)
    if created:
        stats.curriculum_count += 1
    
    # Kante: curriculum -> fachplan
    await create_edge(db, curriculum_id, UUID(str(fachplan_id)), "part_of")
    stats.edge_count += 1
    
    # Fach-Name für Breadcrumb
    fach_name = payload.fach or payload.fach_code
    schulart = payload.schulart
    jahrgangsstufe = payload.jahrgangsstufe
    
    # 2. Kapitel und Lernsequenzen
    for kap in payload.kapitel:
        kapitel_import_key = f"{import_key_base}_kapitel_{kap.reihenfolge}"
        
        # Kapitel-Knoten
        konkretisierung_text = " ".join(kap.konkretisierung) if kap.konkretisierung else None
        kapitel_data = {
            "category": "knowledge",
            "content_type": "kapitel",
            "title": kap.titel,
            "content": konkretisierung_text,
            "read_scope": "school",
            "write_scope": "subject" if department_group_id else "school",
            "write_scope_group_id": department_group_id,
            "subject_id": subject_id,
            "owner_pseudonym": user_pseudonym,
            "metadata_": {
                "std": kap.std,
                "reihenfolge": kap.reihenfolge,
                "einleitung": kap.hinweis or "",
                "breadcrumb": f"{schulart} | {fach_name} | Kl. {jahrgangsstufe}: {kap.titel}",
                "import_key": kapitel_import_key,
            }
        }
        kapitel_id, created = await get_or_create_node(
            db, "knowledge", "kapitel", kapitel_import_key, kapitel_data
        )
        all_import_keys.add(kapitel_import_key)
        if created:
            stats.kapitel_count += 1
        
        # Kante: kapitel -> curriculum
        await create_edge(db, kapitel_id, curriculum_id, "part_of")
        stats.edge_count += 1
        
        # Embedding-Job für Kapitel
        if created:
            await enqueue_embedding_job(kapitel_id, db)
        
        # 3. Lernsequenzen
        for ls in kap.lernsequenzen:
            ls_reihenfolge = ls.reihenfolge if ls.reihenfolge is not None else 0
            ls_import_key = f"{kapitel_import_key}_ls_{ls_reihenfolge}"
            ls_label = ls.bp_titel or "?"

            # Einträge vorverarbeiten: IK/PK auflösen, Hinweise rewriten, Material prüfen
            eintraege_for_meta = []
            resolved_edges: list[tuple[UUID, UUID, str, dict]] = []  # (from, to, relation, meta)

            for entry in ls.eintraege:
                # ── IK normalisieren ────────────────────────────────────────
                ik_pairs = _normalize_ik_input(entry.ik, entry.ik_partiell)
                editor_ik = []
                for ik_nr, partiell in ik_pairs:
                    ik_node_id = await resolve_ik_node(
                        db, subject_id, ik_nr, payload.bp_version
                    )
                    if ik_node_id:
                        editor_ik.append({"node_id": str(ik_node_id), "nr": ik_nr, "partiell": partiell})
                        resolved_edges.append((None, ik_node_id, "references", {"partiell": str(partiell).lower()}))
                    else:
                        w = f"IK {ik_nr} nicht gefunden für LS {ls_label} (Fassung {payload.bp_version})"
                        if w not in stats.warnings:
                            stats.warnings.append(w)
                        logger.warning(w)

                # ── PK normalisieren ─────────────────────────────────────────
                pk_raw = entry.pk if isinstance(entry.pk, list) else ([entry.pk] if entry.pk else [])
                editor_pk = []
                for pk_ref in pk_raw:
                    pk_id_str = pk_ref.get("id") if isinstance(pk_ref, dict) else str(pk_ref)
                    if pk_id_str:
                        pk_node_id = await resolve_pk_node(
                            db, pk_id_str, subject_id, payload.bp_version
                        )
                        if pk_node_id:
                            editor_pk.append({"node_id": str(pk_node_id), "pk_id": pk_id_str})
                            resolved_edges.append((None, pk_node_id, "develops", {}))
                        else:
                            w = f"PK {pk_id_str} nicht gefunden für LS {ls_label} (Fassung {payload.bp_version})"
                            if w not in stats.warnings:
                                stats.warnings.append(w)
                            logger.warning(w)

                # ── Hinweise: Code-Token → UUID-Token rewrite + Kanten ───────
                hinweise_raw = entry.hinweise or ""
                hinweise_uuid = await hinweise_code_to_uuid(
                    hinweise_raw, db, stats.warnings, ls_label, payload.bp_version
                )

                # Kanten aus UUID-Token (LP, LP-Aspekt, Cross-Fach-IK).
                #
                # ⚠️ Die UUIDs stammen aus dem Text und können auf Knoten einer **anderen
                # Instanz** zeigen: Beim Export bleibt ein Token als rohe UUID stehen,
                # wenn der Zielknoten keinen Code trägt. Ungeprüft eingefügt, brach der
                # Fremdschlüssel und riss den **gesamten** Import mit — ein einzelner
                # Verweis machte das ganze Curriculum unimportierbar. Deshalb wird die
                # Existenz vorher geprüft und der Fall wie eine unauflösbare Nummer
                # behandelt: melden, überspringen, weitermachen.
                for muster, art in (
                    (r'@\[[^\]]*\]\(lp:([0-9a-f-]{36})\)', "LP"),
                    (r'@\[[^\]]*\]\(lpa:([0-9a-f-]{36})\)', "LP-Aspekt"),
                    (r'#\[[^\]]*\]\(ik:([0-9a-f-]{36})\)', "Cross-Fach-IK"),
                ):
                    for uid_str in re.findall(muster, hinweise_uuid):
                        ziel = UUID(uid_str)
                        if await db.get(ContextNode, ziel) is None:
                            w = (
                                f"{art}-Verweis {uid_str} zeigt auf einen Knoten, den es "
                                f"in dieser Instanz nicht gibt (LS {ls_label}) — "
                                f"übersprungen."
                            )
                            if w not in stats.warnings:
                                stats.warnings.append(w)
                            continue
                        resolved_edges.append((None, ziel, "references", {}))

                # Legacy lp-Liste (dedupliziert mit Token-Kanten)
                for lp_code in (entry.lp or []):
                    lp_node_id = await resolve_leitperspektive_node(db, str(lp_code))
                    if lp_node_id:
                        resolved_edges.append((None, lp_node_id, "references", {}))
                    else:
                        w = f"LP {lp_code} nicht gefunden für LS {ls_label}"
                        if w not in stats.warnings:
                            stats.warnings.append(w)
                        logger.warning(w)

                # ── Material: node-Token → used_with Kanten ──────────────────
                material_text = entry.material or ""
                material_uuids = await material_resolve_nodes(
                    material_text, db, stats.warnings, ls_label
                )
                for mat_uid in material_uuids:
                    resolved_edges.append((None, mat_uid, "used_with", {"via": "material"}))

                eintraege_for_meta.append({
                    "ik": editor_ik,
                    "pk": editor_pk,
                    "konkretisierung": entry.konkretisierung or "",
                    "hinweise": hinweise_uuid,
                    "material": material_text,
                })

            # Lernsequenz-Knoten (metadata mit editor-kompatiblen eintraege)
            ls_data = {
                "category": "knowledge",
                "content_type": "lernsequenz",
                "title": ls.bp_titel or "",
                "content": None,
                "read_scope": "school",
                "write_scope": "subject" if department_group_id else "school",
                "write_scope_group_id": department_group_id,
                "subject_id": subject_id,
                "owner_pseudonym": user_pseudonym,
                "metadata_": {
                    "bp_leitidee": ls.bp_leitidee,
                    "reihenfolge": ls_reihenfolge,
                    "std": getattr(ls, "std", None),
                    "eintraege": eintraege_for_meta,
                    "import_key": ls_import_key,
                }
            }
            lernsequenz_id, created = await get_or_create_node(
                db, "knowledge", "lernsequenz", ls_import_key, ls_data
            )
            all_import_keys.add(ls_import_key)
            if created:
                stats.lernsequenz_count += 1

            # Kante: lernsequenz -> kapitel
            await create_edge(db, lernsequenz_id, kapitel_id, "part_of")
            stats.edge_count += 1

            # 4. Vorberechnete Kanten anlegen (dedupliziert nach to_node_id + relation)
            seen_edges: set[tuple[str, str]] = set()
            for (_from, to_id, relation, meta) in resolved_edges:
                edge_key = (str(to_id), relation)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                await create_edge(db, lernsequenz_id, to_id, relation, meta or None)
                stats.edge_count += 1

    # Was dieser Import früher angelegt hat und jetzt nicht mehr erzeugt, wird abgeräumt —
    # sonst überlebt ein aus dem YAML gelöschtes Kapitel jeden Re-Import.
    stats.archived_count = await archive_orphaned_curriculum_nodes(
        db, import_key_base, all_import_keys
    )
    if stats.archived_count:
        logger.info(
            "%d verwaiste Kapitel/Lernsequenzen archiviert (nicht mehr im Import)",
            stats.archived_count,
        )

    return curriculum_id, stats


def _normalize_ik_input(ik_raw: str | list | None, ik_partiell_default: bool) -> list[tuple[str, bool]]:
    """Normalisiert den ik-Eingabewert auf eine Liste von (nr, partiell)-Paaren."""
    if not ik_raw:
        return []
    if isinstance(ik_raw, str):
        return [(nr.strip(), ik_partiell_default) for nr in ik_raw.split(",") if nr.strip()]
    if isinstance(ik_raw, list):
        result = []
        for item in ik_raw:
            if isinstance(item, dict):
                nr = item.get("nr")
                partiell = bool(item.get("partiell", False))
                if nr:
                    result.append((str(nr), partiell))
            elif isinstance(item, str) and item.strip():
                result.append((item.strip(), ik_partiell_default))
        return result
    return []
