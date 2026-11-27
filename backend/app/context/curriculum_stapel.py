"""Curriculum-Vorlagen gesammelt einspielen (0.62, Päckchen BH).

Ein Admin gibt viele Curriculum-YAMLs auf einmal; aus jeder wird **ein Entwurf** — nie ein
veröffentlichtes Curriculum, nie eine Änderung an einem vorhandenen (Jan, 27.11.2026, F3). Was
entsteht, folgt aus dem, was es zu Fach, Jahrgang und Edition schon gibt:

- nichts → ein neuer Entwurf (`neu`);
- genau ein veröffentlichtes Curriculum ohne offenen Entwurf → ein Entwurf, der es beim
  Veröffentlichen ersetzt (`ersetzt`), wie die Vorauswahl im Einzelimport;
- schon ein Entwurf (auch aus einer früheren Datei desselben Stapels) oder mehrere
  veröffentlichte → ein zusätzlicher Entwurf, der nichts ersetzt, mit dem Importdatum im
  Titel (`zusaetzlich`).

Jeder Entwurf trägt `metadata.vorlage = {datei, importiert_am}` (F4); die Oberfläche zeigt
daran den Hinweis, dass die Fachschaft ihn prüft. `quelle` kommt aus der Datei (F7).

Jede Datei läuft für sich durch `curriculum_yaml.durchlauf`, in einem eigenen Savepoint: Eine
fehlerhafte Datei hält die übrigen nicht auf. Beim Anlegen wird nach jeder Datei committet.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import sqlalchemy as sa

logger = logging.getLogger(__name__)

MAX_DATEIEN = 60
#: Summe der Dateien je Lauf — 60 × 200 KB; bleibt unter `NGINX_MAX_BODY_SIZE` (24m).
MAX_BYTES_GESAMT = 12_000_000

NEU, ERSETZT, ZUSAETZLICH = "neu", "ersetzt", "zusaetzlich"


def titel_zusatz(tag: date) -> str:
    return f"Import {tag:%d.%m.%Y}"


def art_bestimmen(vorhanden: list[dict], entwuerfe: int, schon_im_stapel: bool) -> tuple[str, str | None]:
    """Was aus einer Datei wird: (`art`, id des Curriculums, das sie ersetzt). Rein, ohne DB.

    `vorhanden` wie in `durchlauf` (veröffentlichte gleichen Fachs, Jahrgangs und Edition),
    `entwuerfe` = Zahl der offenen Entwürfe dazu, `schon_im_stapel` = eine frühere Datei
    dieses Laufs trifft dieselbe Stufe.
    """
    if entwuerfe or schon_im_stapel or len(vorhanden) > 1:
        return ZUSAETZLICH, None
    if len(vorhanden) == 1:
        return ERSETZT, vorhanden[0]["id"]
    return NEU, None


@dataclass
class _Lage:
    schluessel: tuple
    vorhanden: list[dict]
    entwuerfe: int


async def _lage(db, roh: str) -> _Lage | None:
    """Was es zur Stufe der Datei schon gibt — `None`, wenn die Datei sich nicht einlesen lässt
    oder ihr Fach fehlt (die Fehler meldet dann `durchlauf`)."""
    from app.context.curriculum_entwurf import ENTWURF, offener_entwurf
    from app.context.curriculum_yaml import einlesen
    from app.context.service import get_subject_id_by_code
    from app.db.models import ContextNode

    p = einlesen(roh)
    if not p.ok:
        return None
    e = p.entwurf
    subject_id = await get_subject_id_by_code(db, e.fach_code)
    if subject_id is None:
        return None

    def gleiche_stufe(status):
        return sa.select(ContextNode).where(
            ContextNode.content_type == "curriculum", ContextNode.status == status,
            ContextNode.subject_id == subject_id,
            ContextNode.metadata_["jahrgangsstufe"].astext == e.jahrgangsstufe,
            ContextNode.metadata_["bp_version"].astext == e.bp_version)

    veroeffentlicht = (await db.execute(gleiche_stufe("active").order_by(ContextNode.title))).scalars().all()
    entwuerfe = {c.id for c in (await db.execute(gleiche_stufe(ENTWURF))).scalars().all()}
    vorhanden = []
    for c in veroeffentlicht:
        offen = await offener_entwurf(db, c.id)
        if offen is not None:
            entwuerfe.add(offen.id)
        vorhanden.append({"id": str(c.id), "titel": c.title})
    return _Lage((subject_id, e.jahrgangsstufe, e.bp_version), vorhanden, len(entwuerfe))


def _gescheitert(fehler: str) -> dict:
    return {"ok": False, "fehler": [fehler], "warnungen": [], "curriculum": None, "kapitel": [],
            "summen": None, "vorhanden": [], "ersetzen": None}


async def stapel(db, dateien: list[tuple[str, str]], user, *, tag: date, speichern: bool = False) -> dict:
    """Prüft (`speichern=False`) oder legt an. `dateien` = [(Dateiname, YAML-Text)].

    Antwort: `dateien` — je Datei die Antwort von `durchlauf` plus `datei`, `art` und
    `ersetzt_titel` (nach dem Anlegen mit `id`) —, und `zahlen` (`ok`, `fehler`).
    Rechte prüft der Aufrufer (nur Admins); `durchlauf` prüft sie je Fach noch einmal.
    """
    from app.context.curriculum_yaml import KeinRecht, durchlauf

    ergebnisse, gesehen = [], set()
    for name, text in dateien:
        lage = await _lage(db, text)
        art, ersetzen = (art_bestimmen(lage.vorhanden, lage.entwuerfe, lage.schluessel in gesehen)
                         if lage else (None, None))
        sicherung = await db.begin_nested()
        try:
            r = await durchlauf(db, text, user, ersetzen=ersetzen, speichern=speichern,
                                vorlage={"datei": name, "importiert_am": tag.isoformat()},
                                titel_zusatz=titel_zusatz(tag) if art == ZUSAETZLICH else None)
        except KeinRecht as fehler:
            await sicherung.rollback()
            r = _gescheitert(str(fehler))
        except Exception:
            logger.exception("Sammelimport: Datei %s ließ sich nicht verarbeiten", name)
            await sicherung.rollback()
            r = _gescheitert("Die Datei ließ sich nicht verarbeiten (Fehler auf dem Server).")
        else:
            await sicherung.commit()
        if r["ok"]:
            gesehen.add(lage.schluessel)
            if speichern:
                await db.commit()
        ziel = next((v for v in (lage.vorhanden if lage else []) if v["id"] == ersetzen), None)
        ergebnisse.append({**r, "datei": name, "art": art if r["ok"] else None,
                           "ersetzt_titel": ziel["titel"] if ziel and r["ok"] else None})
    ok = sum(1 for r in ergebnisse if r["ok"])
    return {"dateien": ergebnisse, "zahlen": {"ok": ok, "fehler": len(ergebnisse) - ok}}
