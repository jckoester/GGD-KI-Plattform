"""Ein Bibliotheks-Artefakt als Baustein in den Wissensgraphen übernehmen (AP8).

**Was hier passiert und was nicht.** „In Bibliothek speichern" hebt einen flüchtigen
Chat-Inhalt in die persönliche Bibliothek (Phase 18) — dort liegt er als Datei, mit
Ablauffrist, und niemand sonst sieht ihn. Die Übernahme ist der Schritt danach: aus dem
Artefakt wird ein **Baustein**, also etwas mit Bausteinart, Sichtbarkeit, Ablaufdatum und
Verknüpfungen. Das Artefakt bleibt daneben bestehen; der Baustein trägt in
`metadata.source_artifact_id` seine Herkunft.

**Nur textliche Artefakte.** Übernehmbar sind `document` (Markdown) und `mermaid`
(Diagrammquelltext) — bei beiden hat der Baustein einen Inhalt, den man lesen, suchen und
im Editor weiterschreiben kann. Ein Bild ergäbe einen Knoten, der außer dem Titel nichts
trägt; Schaltplan, Funktionsgraph und GeoGebra-Datei bleiben vorerst in der Bibliothek,
wo sie hingehören (Entscheidung 7 zum Umsetzungsplan, 07.09.2026).

**Erneute Übernahme erzeugt eine Fassung, keinen Zweitknoten.** Wer ein überarbeitetes
Dokument nochmals übernimmt, bekommt einen neuen Baustein; der alte wandert ins Archiv und
wird per `supersedes`-Kante mit dem neuen verbunden. Das ist nicht Zierrat: Verweist eine
Unterrichtsstunde auf die alte Fassung, schlägt `GET /nodes/{id}/archived-references`
genau über diese Kante den Nachfolger vor. In-place zu überschreiben nähme dieser
Mechanik ihre Grundlage — und der Stunde ihren stabilen Bezug.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import JwtPayload
from app.context.scope_gruppen import pruefe_scopes
from app.context.taxonomy import (
    CONTENT_TYPE_TO_CATEGORY,
    RUHENDE_CONTENT_TYPES,
    SCOPE_DEFAULTS,
)
from app.db.models import Artifact, ContextEdge, ContextNode

# Artefaktarten mit lesbarem Quelltext. `image`, `circuit`, `plot` und `ggb` fehlen
# absichtlich — siehe Modul-Kopf.
UEBERNEHMBARE_KINDS: frozenset[str] = frozenset({"document", "mermaid"})

# ── Wer welche Bausteinart aus einem Artefakt machen darf ────────────────────
#
# Drei Listen statt einer Ableitung, weil die Frage „taugt diese Bausteinart als
# Ergebnis eines Chats?" sich aus keinem Attribut der Taxonomie ergibt. Damit die
# Listen nicht auseinanderlaufen, prüft `test_uebernahme_typen_vollstaendig`, dass
# jede aktive Art aus `document`/`artifact` in genau einer davon steht — ein neuer
# Typ zwingt so zur Entscheidung, statt still herauszufallen.

LEHRKRAFT_TYPEN: tuple[str, ...] = (
    "arbeitsblatt",
    "aufgabe",
    "klausur",
    "lerntext",
    "code_beispiel",
    "praesentation",
    "vokabelliste",
    "quelltext",
    "methodenblatt",
    "operatorenblatt",
    "konvention",
    "strukturierung",
)

# Schüler:innen legen nur Eigenes ab. `strukturierung` steht in beiden Listen: Der Typ
# ist rollenoffen — die Mindmap einer Schüler:in und die einer Lehrkraft für ihre Klasse
# sind dasselbe Ding mit anderer Sichtbarkeit.
SCHUELER_TYPEN: tuple[str, ...] = (
    "schuelertext",
    "lernplan",
    "schuelerpraesentation",
    "strukturierung",
)

# Nicht übernehmbar — mit dem Grund, damit die Entscheidung nachlesbar bleibt.
NICHT_UEBERNEHMBAR: dict[str, str] = {
    "unterrichtsstunde": "Planungsobjekt — entsteht im Unterrichtsplaner, nicht im Chat",
    "unterrichtseinheit": "Planungsobjekt — entsteht im Unterrichtsplaner, nicht im Chat",
    "formatierungsvorlage": "schulweite Vorlage — wird in den Einstellungen gepflegt",
    "feedback_text": "entsteht im Feedback-Flow, den es noch nicht gibt",
}


def ist_lehrkraft(roles: list[str]) -> bool:
    """Admin ist eine Erweiterung der Lehrkraft, kein eigener Nutzertyp (CLAUDE.md)."""
    return "teacher" in roles or "admin" in roles


def angebotene_typen(roles: list[str]) -> tuple[str, ...]:
    """Bausteinarten, die diese Rolle aus einem Artefakt machen darf.

    ⚠️ **Ruhende Arten fallen heraus.** „Ruhend" heißt: Es gibt keinen Weg, so einen
    Knoten anzulegen (ADR-019 F6). Die Übernahme wäre so ein Weg — sie hier anzubieten
    machte den `ui_status` zur Lüge und umginge die eine Stelle, an der über die
    Sichtbarkeit einer Bausteinart entschieden wird. Solange die vier Schülerarten
    ruhen, bekommt eine Schüler:in also eine leere Liste; das ist die richtige Antwort,
    bis AP8 Schritt 2 sie weckt.
    """
    basis = LEHRKRAFT_TYPEN if ist_lehrkraft(roles) else SCHUELER_TYPEN
    return tuple(t for t in basis if t not in RUHENDE_CONTENT_TYPES)


def erzwungene_scopes(roles: list[str]) -> tuple[str, str] | None:
    """Sichtbarkeit, die die Rolle nicht wählen darf — `None` heißt „freie Wahl".

    Ein Schüler-Baustein ist `private`/`private`, ohne Ausnahme und ohne Formularfeld.
    Die Alternative wäre ein Auswahlfeld, das eine Sichtbarkeit anbietet, die es nicht
    geben soll — und das ein Fehlgriff dann veröffentlicht, statt ihn abzuweisen.
    """
    return None if ist_lehrkraft(roles) else ("private", "private")


def vorgabe_scopes(content_type: str) -> tuple[str, str]:
    """Vorbelegung des Formulars: was die Taxonomie für diese Art vorsieht."""
    return SCOPE_DEFAULTS.get(content_type, ("private", "private"))


class UebernahmeFehler(Exception):
    """Übernahme nicht möglich (Artefaktart, Bausteinart, leerer Inhalt)."""


def inhalt_aus_artefakt(artifact: Artifact) -> str:
    """Der Knotentext zum Artefakt.

    Ein Dokument ist bereits Markdown und wandert unverändert. Ein Mermaid-Diagramm
    bekommt seinen Zaun zurück: Erst als ```mermaid-Block rendert die Knotenansicht es
    als Diagramm statt als Codewüste — dort läuft dieselbe `renderDiagrams`-Aktion wie
    im Chat.
    """
    quelle = (artifact.source or "").strip()
    if not quelle:
        raise UebernahmeFehler("Das Artefakt hat keinen Inhalt zum Übernehmen.")
    if artifact.kind == "mermaid":
        return f"```mermaid\n{quelle}\n```"
    return quelle


def ist_uebernehmbar(artifact: Artifact) -> bool:
    """Taugt dieses Artefakt überhaupt als Baustein?

    Die Bibliothek fragt das je Eintrag, um den Knopf nur dort zu zeigen, wo er etwas
    tut. Damit steht die Antwort an **einer** Stelle: Ein Knopf, dessen Bedingung der
    Browser für sich nachbaut, zeigt irgendwann etwas anderes an als der Server erlaubt.
    """
    return artifact.kind in UEBERNEHMBARE_KINDS and bool((artifact.source or "").strip())


def ablehnungsgrund(artifact: Artifact) -> str | None:
    """Warum nicht — in einem Satz für die Oberfläche. ``None``, wenn es geht."""
    if artifact.kind not in UEBERNEHMBARE_KINDS:
        return (
            "Aus dieser Artefaktart lässt sich kein Baustein machen — übernehmbar sind "
            "Dokumente und Mermaid-Diagramme."
        )
    if not (artifact.source or "").strip():
        return "Das Artefakt hat keinen Inhalt zum Übernehmen."
    return None


def pruefe(artifact: Artifact, content_type: str, roles: list[str]) -> None:
    """Artefaktart und Bausteinart gegen die Rolle. Wirft ``UebernahmeFehler``."""
    if artifact.kind not in UEBERNEHMBARE_KINDS:
        raise UebernahmeFehler(
            f"Aus einem Artefakt der Art „{artifact.kind}“ lässt sich kein Baustein "
            "machen — übernehmbar sind Dokumente und Mermaid-Diagramme."
        )
    erlaubt = angebotene_typen(roles)
    if not erlaubt:
        raise UebernahmeFehler(
            "Für diese Rolle ist zurzeit keine Bausteinart zur Übernahme freigegeben."
        )
    if content_type not in erlaubt:
        raise UebernahmeFehler(
            f"„{content_type}“ steht für die Übernahme nicht zur Wahl. "
            f"Möglich sind: {', '.join(sorted(erlaubt))}."
        )


_HERKUNFT = ContextNode.metadata_["source_artifact_id"].astext


def _eigene_uebernahmen(pseudonym: str):
    """Die aktiven Bausteine dieser Person, die aus einem Artefakt stammen.

    Über `metadata.source_artifact_id` statt über eine eigene Spalte: Die Herkunft ist
    eine Notiz am Knoten, kein Fremdschlüssel. Ein gelöschtes Artefakt soll den Baustein
    nicht mitreißen — er hat dann eine Herkunft, die es nicht mehr gibt, und das ist der
    richtige Zustand.

    **Nur `active`.** Abgelöste Fassungen tragen dieselbe Herkunft; sie mitzuzählen hieße,
    für ein Artefakt mehrere „aktuelle" Bausteine zu behaupten.
    """
    return sa.select(ContextNode).where(
        ContextNode.owner_pseudonym == pseudonym,
        ContextNode.status == "active",
        _HERKUNFT.isnot(None),
    )


async def vorhandener_baustein(
    db: AsyncSession, *, artifact_id: UUID, pseudonym: str
) -> ContextNode | None:
    """Der aktive Baustein dieser Person zu diesem Artefakt — oder ``None``."""
    treffer = await db.execute(
        _eigene_uebernahmen(pseudonym)
        .where(_HERKUNFT == str(artifact_id))
        .order_by(ContextNode.created_at.desc())
        .limit(1)
    )
    return treffer.scalars().first()


async def bausteine_zu_artefakten(
    db: AsyncSession, *, artifact_ids: list[UUID], pseudonym: str
) -> dict[str, ContextNode]:
    """Dasselbe für eine ganze Bibliothek — Artefakt-ID (als Text) → Baustein.

    Eine Abfrage statt einer je Karte: Die Bibliothek zeigt alle Einträge auf einmal,
    und eine Schleife über Einzelabfragen wäre genau das N+1, das man später nicht mehr
    findet, weil es nur bei vollen Bibliotheken weh tut.
    """
    if not artifact_ids:
        return {}
    treffer = await db.execute(
        _eigene_uebernahmen(pseudonym)
        .where(_HERKUNFT.in_([str(a) for a in artifact_ids]))
        .order_by(ContextNode.created_at.asc())
    )
    # Aufsteigend sortiert, damit bei einem (nicht vorgesehenen) Doppel der jüngste
    # gewinnt — dieselbe Wahl wie in `vorhandener_baustein`.
    return {n.metadata_["source_artifact_id"]: n for n in treffer.scalars()}


def _unveraendert(node: ContextNode, *, titel: str, content_type: str, inhalt: str) -> bool:
    """Zweimal dasselbe übernehmen soll keine zweite Fassung erzeugen."""
    return (
        node.title == titel
        and node.content_type == content_type
        and (node.content or "") == inhalt
    )


async def uebernimm(
    db: AsyncSession,
    *,
    user: JwtPayload,
    artifact: Artifact,
    content_type: str,
    title: str | None = None,
    read_scope: str | None = None,
    write_scope: str | None = None,
    read_scope_group_id: int | None = None,
    write_scope_group_id: int | None = None,
    subject_id: int | None = None,
    valid_until=None,
    schuljahr: str | None = None,
) -> tuple[ContextNode, ContextNode | None, bool]:
    """Legt den Baustein an. Gibt ``(baustein, ersetzter_baustein, angelegt)`` zurück.

    ``angelegt=False`` heißt: Es gab den Baustein schon und nichts hat sich geändert —
    dann kommt er unverändert zurück, ohne zweite Fassung. ``ersetzter_baustein`` ist
    nur bei einer echten Aktualisierung gesetzt.

    Committet nicht — das tut der Endpunkt, nachdem er die Scopes geprüft hat.
    """
    pruefe(artifact, content_type, user.roles)
    inhalt = inhalt_aus_artefakt(artifact)
    titel = (title or artifact.title or "").strip()[:200]
    if not titel:
        raise UebernahmeFehler("Der Baustein braucht einen Titel.")

    erzwungen = erzwungene_scopes(user.roles)
    if erzwungen is not None:
        read_scope, write_scope = erzwungen
        read_scope_group_id = write_scope_group_id = None
    else:
        vorgabe = vorgabe_scopes(content_type)
        read_scope = read_scope or vorgabe[0]
        write_scope = write_scope or vorgabe[1]

    # ⚠️ **Vor** dem ersten Schreibzugriff. `read_scope: group` ohne Trägergruppe kann
    # die Datenbank nicht speichern; stünde die Prüfung erst hinter dem `flush()`,
    # käme statt einer lesbaren Meldung ein CheckViolationError als 500 zurück — beim
    # ersten Testlauf genau so passiert. Dieselbe Prüfung wie beim Anlegen und Ändern
    # eines Knotens, nicht eine zweite Meinung daneben.
    try:
        await pruefe_scopes(
            db,
            read_scope=read_scope,
            read_gruppen_id=read_scope_group_id,
            write_scope=write_scope,
            write_gruppen_id=write_scope_group_id,
        )
    except ValueError as exc:
        raise UebernahmeFehler(str(exc)) from exc

    vorhanden = await vorhandener_baustein(
        db, artifact_id=artifact.id, pseudonym=user.sub
    )
    if vorhanden is not None and _unveraendert(
        vorhanden, titel=titel, content_type=content_type, inhalt=inhalt
    ):
        return vorhanden, None, False

    neu = ContextNode(
        category=CONTENT_TYPE_TO_CATEGORY[content_type],
        content_type=content_type,
        title=titel,
        content=inhalt,
        # Der Titel kommt von Hand — er soll einen Re-Import überleben (C1), wie im
        # Editor und in „Meine Bausteine".
        title_locked=True,
        metadata_={"source_artifact_id": str(artifact.id)},
        owner_pseudonym=user.sub,
        read_scope=read_scope,
        write_scope=write_scope,
        read_scope_group_id=read_scope_group_id,
        write_scope_group_id=write_scope_group_id,
        subject_id=subject_id,
        valid_until=valid_until,
        schuljahr=schuljahr,
    )
    db.add(neu)
    await db.flush()

    if vorhanden is not None:
        vorhanden.status = "archived"
        # `archived_at` trägt die Aufbewahrungsfrist (ADR-013) — ohne sie fasste der
        # nächtliche Löschlauf die alte Fassung nie an.
        vorhanden.archived_at = datetime.now(timezone.utc)
        db.add(
            ContextEdge(
                from_node_id=neu.id,
                to_node_id=vorhanden.id,
                relation="supersedes",
                metadata_={"via": "uebernahme"},
            )
        )

    return neu, vorhanden, True
