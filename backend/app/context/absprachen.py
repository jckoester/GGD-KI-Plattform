"""Absprachen zwischen Fächern am Kapitel eines Curriculums (0.63, Päckchen AY Teil 2).

Eine Fachschaft hält am **eigenen** Kapitel fest, was sie mit einer anderen Fachschaft vereinbart
hat (F1). Gespeichert als `metadata.absprachen` am Kapitel-Knoten:

    [{"id": "…", "fach_code": "PH", "kapitel_id": "…" | None, "kapitel_titel": "Dichte" | None,
      "art": "vorher", "text": "…"}]

- `fach_code` ist Pflicht, das Kapitel des anderen Fachs freiwillig (F2). `kapitel_titel` ist der
  Stand beim Speichern — er bleibt lesbar, wenn das Ziel verschwindet, und trägt Absprachen aus
  einer YAML, deren Kapitel sich nicht auflösen ließ.
- `art` (F3): `vorher` (das andere Kapitel liegt vor diesem), `gleichzeitig`, `nachher`,
  `abgestimmt` (inhaltlich, ohne Zeit). Eine zeitliche Art braucht ein Kapitel.
- Keine Zustimmung der anderen Seite (F4); sie sieht die Absprache über die Rückwärtssuche und
  kann eine Gegenabsprache anlegen (`GEGENART`).

Hier: Prüfen und Bereinigen (rein) und die Prüfung der Ziele gegen die Datenbank.
"""
from __future__ import annotations

import uuid
from typing import Any

ARTEN: tuple[str, ...] = ("vorher", "gleichzeitig", "nachher", "abgestimmt")
ZEITLICH = frozenset({"vorher", "gleichzeitig", "nachher"})
#: Die Art aus Sicht der anderen Fachschaft („Mathematik vorher“ ↔ „Physik nachher“).
GEGENART = {"vorher": "nachher", "nachher": "vorher", "gleichzeitig": "gleichzeitig", "abgestimmt": "abgestimmt"}

MAX_JE_KAPITEL = 20
MAX_TEXT = 1_000
MAX_TITEL = 200


def _uuid_text(wert: Any, wo: str) -> str:
    try:
        return str(uuid.UUID(str(wert)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{wo}: keine gültige Kennung.") from None


def normalisieren(liste: Any, eigenes_fach: str | None = None) -> list[dict]:
    """Prüft und bereinigt die Absprachen eines Kapitels (Kopie). `ValueError` mit der Stelle
    („Absprache 2: …“) bei unbrauchbaren Werten. Fehlt eine `id`, bekommt die Absprache eine."""
    if liste is None:
        return []
    if not isinstance(liste, list):
        raise ValueError("Die Absprachen müssen eine Liste sein.")
    if len(liste) > MAX_JE_KAPITEL:
        raise ValueError(f"Höchstens {MAX_JE_KAPITEL} Absprachen je Kapitel.")
    eigen = (eigenes_fach or "").strip().upper()
    aus, ids, gesehen = [], set(), set()
    for i, roh in enumerate(liste, 1):
        wo = f"Absprache {i}"
        if not isinstance(roh, dict):
            raise ValueError(f"{wo}: muss ein Objekt sein.")
        fach = roh.get("fach_code")
        if not isinstance(fach, str) or not fach.strip():
            raise ValueError(f"{wo}: Das andere Fach fehlt.")
        fach = fach.strip().upper()
        if eigen and fach == eigen:
            raise ValueError(f"{wo}: Eine Absprache gilt einem anderen Fach, nicht dem eigenen.")
        art = roh.get("art")
        if art not in ARTEN:
            raise ValueError(f"{wo}: Art „{art}“ gibt es nicht ({', '.join(ARTEN)}).")
        text = roh.get("text")
        if text is not None and not isinstance(text, str):
            raise ValueError(f"{wo}: Der Text muss Text sein.")
        text = (text or "").strip()
        if len(text) > MAX_TEXT:
            raise ValueError(f"{wo}: Der Text ist zu lang ({len(text)} Zeichen, höchstens {MAX_TEXT}).")
        kid = roh.get("kapitel_id")
        kid = _uuid_text(kid, wo) if kid not in (None, "") else None
        titel = roh.get("kapitel_titel")
        if titel is not None and not isinstance(titel, str):
            raise ValueError(f"{wo}: Der Kapiteltitel muss Text sein.")
        titel = (titel or "").strip()[:MAX_TITEL] or None
        if art in ZEITLICH and not (kid or titel):
            raise ValueError(f"{wo}: „{art}“ braucht ein Kapitel des anderen Fachs.")
        if art == "abgestimmt" and not text:
            raise ValueError(f"{wo}: Was abgestimmt ist, steht im Text — er fehlt.")
        schluessel = (fach, kid or titel, art)
        if schluessel in gesehen:
            raise ValueError(f"{wo}: Dieselbe Absprache steht schon da.")
        gesehen.add(schluessel)
        aid = roh.get("id")
        aid = _uuid_text(aid, wo) if aid not in (None, "") else str(uuid.uuid4())
        if aid in ids:
            aid = str(uuid.uuid4())
        ids.add(aid)
        aus.append({"id": aid, "fach_code": fach, "kapitel_id": kid, "kapitel_titel": titel,
                    "art": art, "text": text})
    return aus


async def ziele_pruefen(db, absprachen: list[dict]) -> list[dict]:
    """Prüft die Ziele bereinigter Absprachen gegen die Datenbank und setzt `kapitel_titel` auf
    den aktuellen Titel (Kopie). `ValueError`, wenn das Fach unbekannt ist oder das Kapitel kein
    veröffentlichtes oder Entwurfs-Kapitel dieses Fachs ist."""
    import sqlalchemy as sa

    from app.context.curriculum_entwurf import LESBARE_STATUS
    from app.db.models import ContextNode, Subject

    if not absprachen:
        return []
    faecher = {a["fach_code"] for a in absprachen}
    fach_ids = dict((await db.execute(
        sa.select(Subject.fach_code, Subject.id).where(Subject.fach_code.in_(faecher)))).all())
    kids = [uuid.UUID(a["kapitel_id"]) for a in absprachen if a.get("kapitel_id")]
    kapitel = {str(n.id): n for n in (await db.execute(
        sa.select(ContextNode).where(ContextNode.id.in_(kids)))).scalars()} if kids else {}
    aus = []
    for i, a in enumerate(absprachen, 1):
        wo = f"Absprache {i}"
        if a["fach_code"] not in fach_ids:
            raise ValueError(f"{wo}: Ein Fach „{a['fach_code']}“ gibt es hier nicht.")
        a = dict(a)
        if a.get("kapitel_id"):
            k = kapitel.get(a["kapitel_id"])
            if (k is None or k.content_type != "kapitel" or k.status not in LESBARE_STATUS
                    or k.subject_id != fach_ids[a["fach_code"]]):
                raise ValueError(f"{wo}: Das Kapitel gehört nicht zu einem Curriculum von „{a['fach_code']}“.")
            a["kapitel_titel"] = (k.title or "")[:MAX_TITEL] or a.get("kapitel_titel")
        aus.append(a)
    return aus
