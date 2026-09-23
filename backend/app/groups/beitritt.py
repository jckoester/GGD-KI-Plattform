"""Beitrittscodes für Unterrichtsgruppen (AP4).

**Warum es diesen Weg gibt.** Wo die Vererbung aus der Klasse nicht trägt — Kursstufe
ohne Klassenanker, Teilgruppen aus mehreren Klassen, Nachzügler —, kommt sonst niemand in
die Gruppe. Manuelle Mitgliederpflege scheidet aus, weil die Plattform keine Klarnamen
zeigt (ADR-003 Teil 3): Eine Liste aus Pseudonymen wäre nicht bedienbar.

**Zweistufig wie im Haus üblich:** Die reinen Regeln (`pruefe_code`, `code_erzeugen`,
`normalisiere`) rechnen ohne Datenbank und sind ohne sie prüfbar; die schreibenden
Funktionen setzen darauf auf.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupJoinCode, GroupMembership

# ⚠️ **Ohne `O`, `0`, `I`, `1` und `L`.** Ein Code wird an die Tafel geschrieben oder
# diktiert; `I` gegen `1` zu verwechseln ist kein Randfall, sondern der Normalfall. Was
# hier fehlt, spart eine Rückfrage in jeder zweiten Klasse.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Zwei Blöcke à vier Zeichen: kurz genug zum Abtippen, lang genug, dass Raten sich nicht
# lohnt (31^8 ≈ 8·10^11). Gegen systematisches Probieren schützt ohnehin die Drossel auf
# dem Einlöse-Pfad, nicht die Länge allein.
BLOCKLAENGE = 4
BLOECKE = 2

# Drei Tage (Entscheidung Jan, 23.09.2026). Der Code wird im Unterricht ausgegeben, der
# Beitritt geschieht sofort oder am selben Abend; drei Tage decken „ich mach das zu
# Hause" ab. Länger wäre praktisch dauerhaft — und machte die Rücknahme unbrauchbar,
# weil eine Code-Runde dann mehrere Anlässe umfasste.
GUELTIGKEIT_TAGE = 3


def code_erzeugen() -> str:
    """Ein neuer Code — `secrets`, nicht `random`: Er ist eine Berechtigung."""
    bloecke = [
        "".join(secrets.choice(ALPHABET) for _ in range(BLOCKLAENGE))
        for _ in range(BLOECKE)
    ]
    return "-".join(bloecke)


def normalisiere(eingabe: str) -> str:
    """Tippfehler-Toleranz beim Einlösen — Groß/klein, Leerzeichen, fehlender Strich.

    Bewusst **keine** Ersetzung ähnlicher Zeichen (`0`→`O`): Die kommen im Alphabet gar
    nicht vor, und eine Ersetzungstabelle würde stillschweigend Codes gültig machen, die
    nie ausgegeben wurden.
    """
    roh = "".join(c for c in eingabe.upper() if c.isalnum())
    if len(roh) == BLOCKLAENGE * BLOECKE:
        return "-".join(
            roh[i : i + BLOCKLAENGE] for i in range(0, len(roh), BLOCKLAENGE)
        )
    return roh


@dataclass(frozen=True)
class Codelage:
    """Warum ein Code (nicht) gilt — eine Auskunft, kein Wahr/Falsch."""

    gueltig: bool
    grund: str | None = None


def pruefe_code(code: GroupJoinCode | None, jetzt: datetime) -> Codelage:
    """Rein: Gilt dieser Code gerade?

    ⚠️ **Unbekannt und widerrufen werden gleich beantwortet.** Wer einen fremden Code
    probiert, soll nicht erfahren, ob es ihn gibt — sonst ließe sich der Bestand
    abklopfen. Abgelaufen darf dagegen klar benannt werden: Diesen Code hatte die Person
    in der Hand, die Auskunft verrät nichts Neues und erspart ratloses Wiederholen.
    """
    if code is None or code.widerrufen_am is not None:
        return Codelage(False, "unbekannt")
    if code.gueltig_bis <= jetzt:
        return Codelage(False, "abgelaufen")
    return Codelage(True)


async def erzeuge_code(
    db: AsyncSession, group_id: int, pseudonym: str, jetzt: datetime | None = None
) -> GroupJoinCode:
    """Einen neuen Code ausgeben und den bisherigen der Gruppe widerrufen.

    **Immer nur einer je Gruppe gilt.** „Erneuern" heißt: Der alte verfällt sofort.
    Zwei gleichzeitig gültige Codes wären nicht erklärbar — und die Rücknahme einer
    Runde verlöre ihren Bezug.
    """
    jetzt = jetzt or datetime.now(UTC)
    await widerrufe_codes(db, group_id, jetzt)
    code = GroupJoinCode(
        group_id=group_id,
        code=code_erzeugen(),
        erstellt_von_pseudonym=pseudonym,
        gueltig_bis=jetzt + timedelta(days=GUELTIGKEIT_TAGE),
    )
    db.add(code)
    await db.flush()
    return code


async def widerrufe_codes(
    db: AsyncSession, group_id: int, jetzt: datetime | None = None
) -> int:
    """Alle noch gültigen Codes einer Gruppe ungültig machen."""
    jetzt = jetzt or datetime.now(UTC)
    ergebnis = await db.execute(
        update(GroupJoinCode)
        .where(
            GroupJoinCode.group_id == group_id,
            GroupJoinCode.widerrufen_am.is_(None),
        )
        .values(widerrufen_am=jetzt)
    )
    return ergebnis.rowcount or 0


async def aktueller_code(db: AsyncSession, group_id: int) -> GroupJoinCode | None:
    """Der jüngste nicht widerrufene Code der Gruppe — auch ein abgelaufener.

    Abgelaufene werden **mitgeliefert**, damit die Oberfläche „abgelaufen, erneuern?"
    sagen kann statt „kein Code" — das sind zwei verschiedene Lagen.
    """
    return (
        await db.execute(
            select(GroupJoinCode)
            .where(
                GroupJoinCode.group_id == group_id,
                GroupJoinCode.widerrufen_am.is_(None),
            )
            .order_by(GroupJoinCode.erstellt_am.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def loese_ein(
    db: AsyncSession, eingabe: str, pseudonym: str, jetzt: datetime | None = None
) -> tuple[GroupJoinCode | None, Codelage]:
    """Einen Code einlösen. Gibt den Code und die Lage zurück.

    Idempotent: Wer schon Mitglied ist, bleibt es — mit seiner **bisherigen** Herkunft.
    Ein geerbtes Mitglied, das zusätzlich den Code eintippt, wird nicht zum
    Code-Mitglied; sonst fiele es beim Klassenwechsel nicht mehr heraus.
    """
    jetzt = jetzt or datetime.now(UTC)
    code = (
        await db.execute(
            select(GroupJoinCode).where(GroupJoinCode.code == normalisiere(eingabe))
        )
    ).scalar_one_or_none()

    lage = pruefe_code(code, jetzt)
    if not lage.gueltig:
        return None, lage

    await db.execute(
        pg_insert(GroupMembership)
        .values(
            group_id=code.group_id,
            pseudonym=pseudonym,
            role_in_group="student",
            herkunft="code",
            beigetreten_am=jetzt,
            join_code_id=code.id,
        )
        .on_conflict_do_nothing(index_elements=["group_id", "pseudonym"])
    )
    return code, lage


@dataclass(frozen=True)
class Beitrittstag:
    """Wie viele an einem Tag beigetreten sind — ohne zu sagen, wer."""

    tag: date
    anzahl: int


async def beitritte_je_tag(db: AsyncSession, code_id: UUID) -> list[Beitrittstag]:
    """Die Beitritte einer Code-Runde, nach Tag gezählt.

    **Nur Zahlen, keine Pseudonyme.** Die Lehrkraft soll erkennen, *wann* zu viele
    dazukamen — nicht *wer*. Mehr gäbe die Oberfläche ohnehin nicht her, und weniger
    machte die Rücknahme zum Blindflug.
    """
    zeilen = await db.execute(
        select(
            func.date(GroupMembership.beigetreten_am).label("tag"),
            func.count().label("anzahl"),
        )
        .where(
            GroupMembership.join_code_id == code_id,
            GroupMembership.herkunft == "code",
        )
        .group_by(func.date(GroupMembership.beigetreten_am))
        .order_by(func.date(GroupMembership.beigetreten_am))
    )
    return [Beitrittstag(tag=t, anzahl=n) for t, n in zeilen.all()]


async def nimm_beitritte_zurueck(
    db: AsyncSession,
    code_id: UUID,
    tag: date | None = None,
    jetzt: datetime | None = None,
) -> int:
    """Beitritte einer Code-Runde zurücknehmen — ganz oder einen Tag daraus.

    **Drei Regeln, und jede hat einen Grund:**

    1. Entfernt werden **ausschließlich** Mitgliedschaften mit `herkunft='code'` und
       passender `join_code_id`. Geerbte, SSO- und `eigen`-Mitgliedschaften bleiben
       unberührt — auch dann, wenn dieselbe Person auf zwei Wegen drin wäre.
    2. Der Code wird **im selben Vorgang widerrufen**. Sonst treten dieselben Falschen
       unmittelbar wieder bei, und die Rücknahme wäre folgenlos.
    3. Zurückgenommen wird eine **Menge**, nie eine einzelne Person: Ohne Namen ist eine
       Einzelauswahl nicht sicher bedienbar (Entscheidung Jan, F1).
    """
    jetzt = jetzt or datetime.now(UTC)
    bedingungen = [
        GroupMembership.join_code_id == code_id,
        GroupMembership.herkunft == "code",
    ]
    if tag is not None:
        bedingungen.append(func.date(GroupMembership.beigetreten_am) == tag)

    ergebnis = await db.execute(delete(GroupMembership).where(*bedingungen))
    await db.execute(
        update(GroupJoinCode)
        .where(GroupJoinCode.id == code_id, GroupJoinCode.widerrufen_am.is_(None))
        .values(widerrufen_am=jetzt)
    )
    return ergebnis.rowcount or 0
