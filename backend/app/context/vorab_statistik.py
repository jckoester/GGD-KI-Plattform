"""Zähler der Vorab-Suche — ohne Personenbezug (0.16, Plan „Vorab-Suche-Begriffe" § 7.3).

Drei Fragen soll die Statistik im Betrieb beantworten: Hält die Quote, mit der Angebote
nachgeschlagen werden? Welche Titel werden oft angeboten und nie nachgeschlagen (Alltagswörter →
Alias-Pflege)? Sucht das Modell Begriffe knapp über dem Band per Werkzeug nach?

Gezählt wird je Antwort, **nach** dem Speichern und in einer eigenen Transaktion: Ein Fehler
beim Zählen darf die Antwort nie kosten — er wird geloggt, die Zähler fehlen dann für diese
Nachricht. Vorschau-Chats (``is_test``, ADR-016) zählt der Aufrufer nicht.

⚠️ **„Nachgeschlagen" heißt: im Werkzeugergebnis derselben Antwort.** Ob das Modell den
angebotenen Titel gezielt gesucht hat oder er bei einer anderen Suche mitkam, sieht die
Tabelle nicht.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.bausteine import VORAB, Baustein, Kontext
from app.db.models import ContextNode, VorabStatistik

logger = logging.getLogger(__name__)

SICHER = "sicher"
ANGEBOT = "angebot"
#: ``grund`` einer sicheren Knotenzeile: sicher, weil die Unterrichtsgruppe ihn hatte (0.20).
GRUPPE = "gruppe"
ZAEHLER = (
    "vorgelegt", "im_werkzeugergebnis", "nachrichten", "mit_sicher", "mit_angebot",
    "angebot_nachgeschlagen", "suchen_ohne_angebot", "angebot_ohne_sicher",
    "angebot_ohne_sicher_nachgeschlagen",
)
_ORT = ZoneInfo("Europe/Berlin")


def woche_von(zeitpunkt: datetime) -> date:
    """Montag der ISO-Kalenderwoche, in Ortszeit — Sonntag 23:30 gehört zur alten Woche."""
    tag = zeitpunkt.astimezone(_ORT).date()
    return tag - timedelta(days=tag.weekday())


def zeilen(
    sicher: Iterable[str], angebot: Iterable[str], im_werkzeugergebnis: set[str], gesucht: bool,
    *, aus_gruppe: Iterable[str] = (),
) -> list[dict]:
    """Die Zeilen **einer** Antwort, ohne Woche, Fach und Modell: zuerst die Wochenzeile, dann
    die Knotenzeilen. Nicht genannte Zähler sind 0.

    ``aus_gruppe``: sichere Knoten, die es nur wurden, weil die Gruppe sie hatte (0.20) — ihre
    Zeile trägt ``grund = 'gruppe'``, alle anderen keinen."""
    aus_gruppe = set(aus_gruppe)
    sicher, angebot = list(dict.fromkeys(sicher)), list(dict.fromkeys(angebot))
    nachgeschlagen = any(k in im_werkzeugergebnis for k in angebot)
    ohne_sicher = bool(angebot) and not sicher
    woche = {
        "node_id": None, "stufe": None, "grund": None, "nachrichten": 1,
        "mit_sicher": int(bool(sicher)),
        "mit_angebot": int(bool(angebot)),
        "angebot_nachgeschlagen": int(nachgeschlagen),
        "suchen_ohne_angebot": int(gesucht and not angebot),
        "angebot_ohne_sicher": int(ohne_sicher),
        "angebot_ohne_sicher_nachgeschlagen": int(ohne_sicher and nachgeschlagen),
    }
    knoten = [{"node_id": k, "stufe": SICHER, "grund": GRUPPE if k in aus_gruppe else None,
               "vorgelegt": 1} for k in sicher]
    knoten += [{"node_id": k, "stufe": ANGEBOT, "grund": None, "vorgelegt": 1,
                "im_werkzeugergebnis": int(k in im_werkzeugergebnis)} for k in angebot]
    return [{z: 0 for z in ZAEHLER} | zeile for zeile in (woche, *knoten)]


async def zaehlen(
    db: AsyncSession,
    *,
    kontext: Kontext,
    werkzeug_bausteine: Iterable[Baustein],
    gesucht: bool,
    modell: str,
    zeitpunkt: datetime | None = None,
) -> None:
    """Die Zähler einer Antwort hochsetzen und committen. Wirft nie — siehe Modulkopf."""
    try:
        roh = zeilen(
            sicher=[b.node_id for b in kontext.bausteine if b.herkunft == VORAB],
            angebot=[a.node_id for a in kontext.angebot],
            im_werkzeugergebnis={b.node_id for b in werkzeug_bausteine},
            gesucht=gesucht,
            aus_gruppe=[b.node_id for b in kontext.bausteine if b.herkunft == VORAB and b.grund == GRUPPE],
        )
        # Nur Knoten, die es noch gibt — wie beim Speichern der Bausteine: Zwischen Suche und
        # Zählen vergehen Sekunden, und ein gelöschter Knoten ließe den Fremdschlüssel anschlagen.
        ids = {UUID(z["node_id"]) for z in roh if z["node_id"]}
        vorhanden = {str(i) for i in (await db.execute(
            sa.select(ContextNode.id).where(ContextNode.id.in_(ids))
        )).scalars()} if ids else set()
        woche = woche_von(zeitpunkt or datetime.now(_ORT))
        werte = [
            z | {"woche": woche, "subject_id": kontext.subject_id, "modell": modell,
                 "node_id": UUID(z["node_id"]) if z["node_id"] else None}
            for z in roh if z["node_id"] is None or z["node_id"] in vorhanden
        ]
        # Feste Reihenfolge (Wochenzeile zuerst, dann nach Kennung): Zwei gleichzeitige Antworten
        # sperren dieselben Zeilen in derselben Folge und können sich nicht verklemmen.
        werte.sort(key=lambda w: (w["node_id"] is not None, str(w["node_id"] or ""), w["stufe"] or "",
                                  w["grund"] or ""))
        stmt = insert(VorabStatistik).values(werte)
        await db.execute(stmt.on_conflict_do_update(
            constraint="uq_vorab_statistik_schluessel",
            set_={z: getattr(VorabStatistik, z) + getattr(stmt.excluded, z) for z in ZAEHLER},
        ))
        await db.commit()
    except Exception:
        logger.exception("Vorab-Statistik nicht gezählt (Modell %s)", modell)
        try:
            await db.rollback()
        except Exception:
            logger.exception("Rücksetzen nach der Vorab-Statistik gescheitert")
