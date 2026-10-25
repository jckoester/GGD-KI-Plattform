"""Auslöser-Beispiele eines Assistenten pflegen und einbetten (Päckchen C1, Schritt 3).

Ein Assistent trägt zwei Listen kurzer Texte — typische erste Schülernachrichten:

* **Beispiele** (`art = 'beispiel'`): Dafür ist er da.
* **Gegenbeispiele** (`art = 'gegenbeispiel'`, F4 b, Jan 25.10.2026): Das gehört nicht zu ihm,
  etwa Aufgaben des Nachbarassistenten oder Verständnisfragen, die im Chat bleiben sollen.

Beide werden eingebettet. Verglichen wird damit erst in C2; hier geht es nur um Speichern und
Vektoren.

**Setzen ist ein Abgleich, kein Neuschreiben.** Ein Text, der bleibt, behält Zeile und Vektor;
nur neue Texte brauchen ein Embedding. Sonst kostete jedes Speichern im Editor einen Aufruf je
Beispiel.

**Einbetten** geschieht nach dem Speichern als Hintergrundaufgabe (wie beim Fachbegriff-Import,
0.14) und nachts in `scripts/embedding_backfill.py`. Offen ist eine Zeile ohne Vektor **oder**
mit einem Vektor eines anderen Modells (`embedding_model`) — so erledigt der nächtliche Lauf
auch einen Modellwechsel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.context.embedding import generate_embeddings
from app.db.models import AssistantTriggerExample

logger = logging.getLogger(__name__)

BEISPIEL = "beispiel"
GEGENBEISPIEL = "gegenbeispiel"
ARTEN = (BEISPIEL, GEGENBEISPIEL)

# Der Editor empfiehlt 5–15; die Grenze hier fängt nur Versehen ab (eingefügte Textwand).
MAX_EINTRAEGE = 30
MAX_ZEICHEN = 500

_BEZEICHNUNG = {BEISPIEL: "Auslöser-Beispiele", GEGENBEISPIEL: "Gegenbeispiele"}


class AusloeserFehler(ValueError):
    """Eine Liste verletzt eine Grenze; der Text ist für Menschen."""


def bereinige(texte: Iterable[str] | None, art: str) -> list[str]:
    """Leerzeichen am Rand weg, leere Einträge weg, Dubletten weg — Reihenfolge bleibt.

    Wirft :class:`AusloeserFehler` bei zu vielen oder zu langen Einträgen.
    """
    ergebnis: list[str] = []
    for roh in texte or []:
        t = str(roh).strip()
        if t and t not in ergebnis:
            ergebnis.append(t)
    bezeichnung = _BEZEICHNUNG[art]
    if len(ergebnis) > MAX_EINTRAEGE:
        raise AusloeserFehler(
            f"{bezeichnung}: höchstens {MAX_EINTRAEGE} Einträge, es sind {len(ergebnis)}."
        )
    zu_lang = [t for t in ergebnis if len(t) > MAX_ZEICHEN]
    if zu_lang:
        raise AusloeserFehler(
            f"{bezeichnung}: höchstens {MAX_ZEICHEN} Zeichen je Eintrag "
            f"(„{zu_lang[0][:40]}…“ hat {len(zu_lang[0])})."
        )
    return ergebnis


async def lade(db: AsyncSession, assistant_id: int) -> dict[str, list[str]]:
    """Beide Listen in der gespeicherten Reihenfolge."""
    zeilen = (
        await db.execute(
            select(AssistantTriggerExample.art, AssistantTriggerExample.text_)
            .where(AssistantTriggerExample.assistant_id == assistant_id)
            .order_by(AssistantTriggerExample.position, AssistantTriggerExample.id)
        )
    ).all()
    listen: dict[str, list[str]] = {art: [] for art in ARTEN}
    for art, text in zeilen:
        listen[art].append(text)
    return listen


async def setze(db: AsyncSession, assistant_id: int, art: str, texte: list[str]) -> int:
    """Gleicht die Liste ``art`` an ``texte`` an (bereits bereinigt). Gibt die Zahl neuer
    Einträge zurück — nur die brauchen ein Embedding. Kein Commit."""
    bestehend = {
        z.text_: z
        for z in (
            await db.execute(
                select(AssistantTriggerExample).where(
                    AssistantTriggerExample.assistant_id == assistant_id,
                    AssistantTriggerExample.art == art,
                )
            )
        ).scalars()
    }
    for text, zeile in bestehend.items():
        if text not in texte:
            await db.delete(zeile)
    neu = 0
    for position, text in enumerate(texte):
        zeile = bestehend.get(text)
        if zeile is not None:
            zeile.position = position
        else:
            db.add(AssistantTriggerExample(
                assistant_id=assistant_id, art=art, text_=text, position=position,
            ))
            neu += 1
    await db.flush()
    return neu


def _offen():
    """Ohne Vektor, oder mit dem Vektor eines anderen Modells."""
    return or_(
        AssistantTriggerExample.embedding.is_(None),
        AssistantTriggerExample.embedding_model.is_distinct_from(settings.embedding_model),
    )


@dataclass
class EinbettStand:
    gefunden: int = 0
    ok: int = 0
    fehler: int = 0


async def einbetten(
    db: AsyncSession, assistant_ids: Iterable[int] | None = None, *, stapel: int = 100
) -> EinbettStand:
    """Bettet alle offenen Beispiele ein — die der genannten Assistenten oder alle.

    Ein gescheiterter Stapel bleibt offen und wird beim nächsten Lauf erneut versucht; die
    übrigen Stapel laufen weiter.
    """
    stand = EinbettStand()
    if not settings.embeddings_enabled:
        return stand
    abfrage = select(AssistantTriggerExample).where(_offen()).order_by(AssistantTriggerExample.id)
    if assistant_ids is not None:
        ids = list(assistant_ids)
        if not ids:
            return stand
        abfrage = abfrage.where(AssistantTriggerExample.assistant_id.in_(ids))
    zeilen = list((await db.execute(abfrage)).scalars())
    stand.gefunden = len(zeilen)
    for anfang in range(0, len(zeilen), stapel):
        teil = zeilen[anfang:anfang + stapel]
        try:
            ergebnis = await generate_embeddings([z.text_ for z in teil])
        except Exception as exc:
            logger.warning("Auslöser-Beispiele: %d nicht eingebettet (%s)", len(teil), exc)
            stand.fehler += len(teil)
            continue
        for zeile, vektor in zip(teil, ergebnis.vektoren):
            zeile.embedding = vektor
            zeile.embedding_model = settings.embedding_model
        await db.commit()
        stand.ok += len(teil)
    return stand


async def einbetten_im_hintergrund(assistant_id: int, sitzungen) -> None:
    """Nach dem Speichern, in eigener Sitzung — die der Anfrage ist dann zu.

    Scheitern ist kein Fehler des Speicherns: Die Texte stehen, der nächtliche Lauf holt
    den Vektor nach.
    """
    try:
        async with sitzungen() as db:
            stand = await einbetten(db, [assistant_id])
    except Exception:
        logger.exception(
            "Auslöser-Beispiele von Assistent %d nicht eingebettet — der nächtliche Lauf "
            "holt es nach", assistant_id,
        )
        return
    if stand.fehler:
        logger.warning(
            "Auslöser-Beispiele von Assistent %d: %d ok, %d offen für den nächtlichen Lauf",
            assistant_id, stand.ok, stand.fehler,
        )
