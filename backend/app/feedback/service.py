"""Die Regeln des Feedback-Kanals (ADR-020).

**Warum der Missbrauchsschutz ohne eigene Tabelle auskommt.** Sperre und Tageslimit
lesen sich aus den Meldungen selbst: dreimal `spam` in 30 Tagen sperrt 14 Tage, zwanzig
Meldungen in 24 Stunden sind genug. Eine Sperrtabelle daneben müsste gepflegt,
aufgeräumt und bei jeder Statuskorrektur nachgezogen werden — und wäre doch nur eine
zweite Meinung über dieselben Daten.

**Reihenfolge der Prüfungen.** Sperre vor Tageslimit vor Snapshot: Wer gesperrt ist,
soll nicht erst erfahren, dass sein Anhang in Ordnung gewesen wäre.

Die Statusmaschine für die Sichtung kommt in AP3 in dieselbe Datei — beide Seiten
sollen dieselbe Auffassung davon haben, was ein Status bedeutet.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.feedback import snapshot
from app.feedback.schemas import BekanntesProblemOut, FeedbackCreate, FeedbackOut
from app.core.audit import audit, audit_getrennt

logger = logging.getLogger(__name__)

# ── Missbrauchsschutz (ADR-010 §1.2/1.3 Nachtrag) ────────────────────────────────
SPAM_SCHWELLE = 3
SPAM_FENSTER = timedelta(days=30)
SPERRE = timedelta(days=14)
TAGESLIMIT = 20
TAGESFENSTER = timedelta(hours=24)

# ── Statusmaschine (ADR-020) ─────────────────────────────────────────────────────
OFFEN = "open"
IN_ARBEIT = "in_progress"
ERLEDIGT = "done"
ABGELEHNT = "declined"
SPAM = "spam"

# Zustände, in denen die Sichtung fertig ist. Beim Eintritt fallen Kontakt und
# (ohne ausdrückliches Behalten) der Chat-Anhang.
ABGESCHLOSSEN = frozenset({ERLEDIGT, ABGELEHNT, SPAM})

# Wohin es von wo aus gehen darf. Was hier fehlt, ist ein 409 — nicht, weil der
# Übergang undenkbar wäre, sondern weil er unter der Hand Daten vernichtete: Ein
# direkter Sprung von `done` nach `declined` etwa liefe am Wiedereröffnen vorbei und
# schriebe `status_changed_at` neu, obwohl der Anhang längst gefallen ist.
UEBERGAENGE: dict[str, frozenset[str]] = {
    OFFEN: frozenset({IN_ARBEIT, ERLEDIGT, ABGELEHNT, SPAM}),
    IN_ARBEIT: frozenset({ERLEDIGT, ABGELEHNT, SPAM, OFFEN}),
    # Aus einem abgeschlossenen Zustand führt nur der Weg zurück an den Anfang.
    ERLEDIGT: frozenset({OFFEN}),
    ABGELEHNT: frozenset({OFFEN}),
    SPAM: frozenset({OFFEN}),
}

# ── Bekannte Probleme (0.31, Päckchen T) ─────────────────────────────────────────
ALLE = "all"
NUR_LEHRKRAEFTE = "teacher"
ZIELGRUPPEN = frozenset({ALLE, NUR_LEHRKRAEFTE})
# Behobene Einträge bleiben so lange stehen (Plan F2): Wer das Problem kannte, sieht, dass
# es weg ist.
BEHOBEN_SICHTBAR = timedelta(days=30)
# Abgelehnt und Spam sind nie ein bekanntes Problem.
NIE_OEFFENTLICH = frozenset({ABGELEHNT, SPAM})


def _jetzt(jetzt: datetime | None) -> datetime:
    return jetzt or datetime.now(timezone.utc)


async def gesperrt_bis(
    db: AsyncSession, pseudonym: str, *, jetzt: datetime | None = None
) -> datetime | None:
    """Bis wann dieses Pseudonym gesperrt ist — `None`, wenn es frei ist.

    Gezählt werden die `spam`-Einträge der letzten 30 Tage. Ab dem dritten läuft die
    Sperre **ab dem jüngsten** von ihnen, also `max(status_changed_at) + 14 Tage`: Die
    Sperre setzt mit dem dritten Eintrag ein, und der ist der zuletzt gesetzte. Der
    älteste (`min`) wäre der erste Verstoß und ließe die Sperre zu früh enden.
    """
    jetzt = _jetzt(jetzt)
    anzahl, juengster = (
        await db.execute(
            select(func.count(), func.max(Feedback.status_changed_at)).where(
                Feedback.pseudonym == pseudonym,
                Feedback.status == "spam",
                Feedback.status_changed_at > jetzt - SPAM_FENSTER,
            )
        )
    ).one()
    if anzahl < SPAM_SCHWELLE or juengster is None:
        return None
    ende = juengster + SPERRE
    return ende if ende > jetzt else None


async def _tageslage(
    db: AsyncSession, pseudonym: str, *, jetzt: datetime
) -> tuple[int, datetime | None]:
    """Wie viele Meldungen in den letzten 24 Stunden — und ab wann wieder Platz ist."""
    anzahl, aeltester = (
        await db.execute(
            select(func.count(), func.min(Feedback.created_at)).where(
                Feedback.pseudonym == pseudonym,
                Feedback.created_at > jetzt - TAGESFENSTER,
            )
        )
    ).one()
    return anzahl, aeltester


async def pruefe_grenzen(
    db: AsyncSession, pseudonym: str, *, jetzt: datetime | None = None
) -> None:
    """Sperre und Tageslimit. Wirft 403 bzw. 429, sonst still."""
    jetzt = _jetzt(jetzt)

    ende = await gesperrt_bis(db, pseudonym, jetzt=jetzt)
    if ende is not None:
        logger.info("feedback_blocked pseudonym=%s bis=%s", pseudonym, ende.isoformat())
        await audit_getrennt("auth", "feedback_blocked", akteur=pseudonym,
                             daten={"gesperrt_bis": ende.isoformat()})
        raise HTTPException(
            status_code=403,
            detail=f"Feedback vorübergehend gesperrt bis {ende.strftime('%d.%m.%Y')}.",
        )

    anzahl, aeltester = await _tageslage(db, pseudonym, jetzt=jetzt)
    if anzahl >= TAGESLIMIT:
        # Frei wird ein Platz, wenn die älteste Meldung aus dem Fenster fällt — kein
        # pauschales „in 24 Stunden", das wäre fast immer zu lang.
        frei_ab = (aeltester or jetzt) + TAGESFENSTER
        wartezeit = max(1, int((frei_ab - jetzt).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail="Heute wurden schon viele Meldungen gesendet. Bitte später erneut.",
            headers={"Retry-After": str(wartezeit)},
        )


async def erstelle(
    db: AsyncSession,
    daten: FeedbackCreate,
    *,
    pseudonym: str,
    rolle: str,
    aus_vorschau: bool = False,
    jetzt: datetime | None = None,
) -> Feedback:
    """Legt eine Meldung an — nach Sperre, Tageslimit und (optional) Snapshot."""
    jetzt = _jetzt(jetzt)
    await pruefe_grenzen(db, pseudonym, jetzt=jetzt)

    anhang = None
    if daten.attach_conversation_id is not None:
        anhang = await snapshot.lade(db, daten.attach_conversation_id, pseudonym)
        if anhang is None:
            raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    modell = anbietermodell = None
    if daten.active_conversation_id is not None:
        modell, anbietermodell = await snapshot.modell(
            db, daten.active_conversation_id, pseudonym
        )

    eintrag = Feedback(
        pseudonym=pseudonym,
        role=rolle,
        category=daten.category,
        content=daten.content,
        contact=daten.contact,
        app_version=daten.app_version,
        route=daten.route,
        assistant_id=daten.assistant_id,
        user_agent=daten.user_agent,
        viewport=daten.viewport,
        model=modell,
        provider_model=anbietermodell,
        preview=aus_vorschau,
        conversation_snapshot=anhang,
    )
    db.add(eintrag)
    await db.commit()
    await db.refresh(eintrag)

    # Ohne Inhalt: Was gemeldet wurde, steht in der Tabelle und geht niemanden an, der
    # ins Log sieht (ADR-010 Nachtrag).
    logger.info(
        "feedback_created pseudonym=%s id=%s kategorie=%s anhang=%s zeichen=%d",
        pseudonym, eintrag.id, eintrag.category, anhang is not None, len(daten.content),
    )
    return eintrag


async def eigene(db: AsyncSession, pseudonym: str) -> list[Feedback]:
    """Die eigenen Meldungen, neueste zuerst."""
    ergebnis = await db.execute(
        select(Feedback)
        .where(Feedback.pseudonym == pseudonym)
        .order_by(Feedback.created_at.desc())
    )
    return list(ergebnis.scalars().all())


async def ziehe_zurueck(db: AsyncSession, pseudonym: str, feedback_id: UUID) -> None:
    """Löscht eine eigene, noch unbearbeitete Meldung.

    404 für fremd und nicht vorhanden (kein Hinweis auf fremde Existenz), 409, sobald
    die Sichtung sie angefasst hat: Was bereits bearbeitet wird, verschwindet nicht
    unter den Händen der sichtenden Person.
    """
    eintrag = await db.scalar(
        select(Feedback).where(
            Feedback.id == feedback_id, Feedback.pseudonym == pseudonym
        )
    )
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Meldung nicht gefunden")
    if eintrag.status != OFFEN:
        raise HTTPException(
            status_code=409,
            detail="Die Meldung wird bereits bearbeitet und kann nicht mehr zurückgezogen werden.",
        )
    await db.delete(eintrag)
    await db.commit()
    logger.info("feedback_withdrawn pseudonym=%s id=%s", pseudonym, feedback_id)


def nach_aussen(eintrag: Feedback) -> FeedbackOut:
    """Die Sicht der meldenden Person auf ihre eigene Meldung.

    `spam` erscheint als `declined` **ohne** Begründung (ADR-020): Der Status ist ein
    Urteil der Sichtung über die Meldung, kein Gesprächsangebot. Wer ihn als solchen
    angezeigt bekäme, widerspräche — und der Kanal ist bewusst eine Einbahnstraße.
    """
    status = eintrag.status
    antwort = eintrag.admin_reply
    if status == "spam":
        status, antwort = "declined", None
    return FeedbackOut(
        id=eintrag.id,
        category=eintrag.category,
        content=eintrag.content,
        contact=eintrag.contact,
        app_version=eintrag.app_version,
        route=eintrag.route,
        assistant_id=eintrag.assistant_id,
        status=status,
        admin_reply=antwort,
        resolved_in_version=eintrag.resolved_in_version,
        has_snapshot=eintrag.conversation_snapshot is not None,
        created_at=eintrag.created_at,
        status_changed_at=eintrag.status_changed_at,
    )


# ── Sichtung (AP3) ──────────────────────────────────────────────────────────────


def pruefe_uebergang(alt: str, neu: str) -> None:
    """Wirft 409, wenn der Wechsel nicht vorgesehen ist. Gleicher Status: erlaubt."""
    if alt == neu:
        return
    if neu not in UEBERGAENGE.get(alt, frozenset()):
        raise HTTPException(
            status_code=409,
            detail=f"Wechsel von „{alt}“ nach „{neu}“ ist nicht vorgesehen.",
        )


async def aendere(
    db: AsyncSession,
    feedback_id: UUID,
    *,
    admin_pseudonym: str,
    status: str | None = None,
    admin_reply: str | None = None,
    resolved_in_version: str | None = None,
    issue_ref: str | None = None,
    keep_snapshot: bool = False,
    public_title: str | None = None,
    public_audience: str | None = None,
    jetzt: datetime | None = None,
) -> Feedback:
    """Der Statuswechsel der Sichtung — mit allem, was daran hängt.

    **Bekanntes Problem** (0.31): `public_audience` ``all``/``teacher`` zeigt die Meldung mit
    `public_title` öffentlich, ``none`` nimmt sie zurück, ``None`` lässt sie, wie sie ist. Wie
    die Begründung wird der Titel gegen den Endzustand geprüft. Wird eine öffentliche Meldung
    abgelehnt oder als Spam markiert, verschwindet sie aus der Liste; der Titel bleibt.

    **Was beim Abschluss fällt.** `contact` immer: Nach dem Abschluss gibt es nichts
    mehr nachzufragen, und es ist die einzige Spalte im System, die einen Klarnamen
    tragen kann. Der Chat-Anhang ebenfalls, außer die sichtende Person wählt
    ausdrücklich „behalten" — er ist eine Kopie fremder Chatinhalte und hat ohne
    laufende Bearbeitung keinen Zweck.

    `keep_snapshot` ohne Abschluss ist wirkungslos und **kein Fehler**: Die Oberfläche
    schickt die Auswahl mit, auch wenn der Status unverändert bleibt.
    """
    jetzt = _jetzt(jetzt)
    eintrag = await db.scalar(select(Feedback).where(Feedback.id == feedback_id))
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Meldung nicht gefunden")

    vorher = eintrag.status
    ziel = status or vorher
    pruefe_uebergang(vorher, ziel)

    # Die Begründung wird gegen den **Endzustand** geprüft, nicht gegen die Eingabe:
    # Auch wer eine bereits abgelehnte Meldung nur nachbearbeitet, soll sie nicht
    # begründungslos zurücklassen können.
    antwort = admin_reply if admin_reply is not None else eintrag.admin_reply
    if ziel == ABGELEHNT and not (antwort or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Für „nicht umgesetzt“ ist eine kurze Begründung erforderlich.",
        )

    titel = public_title.strip() if public_title is not None else eintrag.public_title
    zielgruppe_vorher = eintrag.public_audience
    if public_audience is None:
        zielgruppe = zielgruppe_vorher
    else:
        zielgruppe = None if public_audience == "none" else public_audience
        if zielgruppe is not None and zielgruppe not in ZIELGRUPPEN:
            raise HTTPException(status_code=422, detail=f"Unbekannte Zielgruppe: {public_audience}")
    if ziel in NIE_OEFFENTLICH:
        if public_audience not in (None, "none"):
            raise HTTPException(
                status_code=422,
                detail="Eine abgelehnte Meldung kann kein bekanntes Problem sein.",
            )
        zielgruppe = None
    if zielgruppe is not None and not titel:
        raise HTTPException(
            status_code=422, detail="Ein bekanntes Problem braucht einen Titel.",
        )

    if admin_reply is not None:
        eintrag.admin_reply = admin_reply.strip() or None
    if resolved_in_version is not None:
        eintrag.resolved_in_version = resolved_in_version.strip() or None
    if issue_ref is not None:
        eintrag.issue_ref = issue_ref.strip() or None

    eintrag.public_title = titel or None
    eintrag.public_audience = zielgruppe
    if zielgruppe != zielgruppe_vorher:
        await audit(db, "admin", "feedback_public_changed", akteur=admin_pseudonym, rolle="admin",
                    ziel=("feedback", feedback_id),
                    daten={"von": zielgruppe_vorher, "nach": zielgruppe})

    if ziel != vorher:
        eintrag.status = ziel
        eintrag.status_changed_at = jetzt
        if ziel in ABGESCHLOSSEN:
            eintrag.contact = None
            if not keep_snapshot:
                eintrag.conversation_snapshot = None
        await audit(db, "admin", "feedback_status_changed", akteur=admin_pseudonym, rolle="admin",
                    ziel=("feedback", feedback_id),
                    daten={"von": vorher, "nach": ziel, "anhang_behalten": bool(keep_snapshot)})

    await db.commit()
    await db.refresh(eintrag)

    logger.info(
        "feedback_status_changed admin=%s id=%s status=%s->%s anhang_behalten=%s",
        admin_pseudonym, feedback_id, vorher, ziel, keep_snapshot,
    )
    return eintrag


# ── Bekannte Probleme (0.31) ─────────────────────────────────────────────────────


async def bekannte(
    db: AsyncSession, *, lehrkraft: bool, jetzt: datetime | None = None,
) -> list[Feedback]:
    """Die öffentlichen Meldungen für eine Rolle: Offenes zuerst, dann kürzlich Behobenes.

    Schüler:innen sehen nur Einträge für alle, Lehrkräfte (und Admins) auch die für
    Lehrkräfte. Behobenes bleibt `BEHOBEN_SICHTBAR` nach dem Statuswechsel stehen.
    """
    jetzt = _jetzt(jetzt)
    zielgruppen = [ALLE, NUR_LEHRKRAEFTE] if lehrkraft else [ALLE]
    ergebnis = await db.execute(
        select(Feedback).where(
            Feedback.public_audience.in_(zielgruppen),
            (Feedback.status.in_([OFFEN, IN_ARBEIT]))
            | ((Feedback.status == ERLEDIGT)
               & (Feedback.status_changed_at >= jetzt - BEHOBEN_SICHTBAR)),
        )
    )
    eintraege = list(ergebnis.scalars().all())
    # Offenes nach Eingang, Behobenes nach Behebung — jeweils neueste zuerst.
    offen = sorted((e for e in eintraege if e.status != ERLEDIGT),
                   key=lambda e: e.created_at, reverse=True)
    behoben = sorted((e for e in eintraege if e.status == ERLEDIGT),
                     key=lambda e: e.status_changed_at, reverse=True)
    return offen + behoben


def als_bekanntes_problem(eintrag: Feedback) -> BekanntesProblemOut:
    """Nur, was der Admin für die Öffentlichkeit geschrieben hat — nie der Text der Meldung."""
    return BekanntesProblemOut(
        id=eintrag.id,
        title=eintrag.public_title or "",
        status=eintrag.status,
        resolved_in_version=eintrag.resolved_in_version if eintrag.status == ERLEDIGT else None,
        seit=eintrag.status_changed_at if eintrag.status == ERLEDIGT else eintrag.created_at,
    )
