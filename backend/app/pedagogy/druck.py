"""Zug-Anweisungen bei Nachsetzen und Lehrkraft-Behauptung (0.26, Rückfall Schritt 9 B, Schritt 10).

**Warum es diese Schicht gibt.** Der Baustein „Begleiten statt lösen“ hält die *erste* Bitte um
die Lösung, der Grundton die erste Behauptung, Lehrkraft zu sein. Beim *zweiten* Beharren gaben
die Assistenten in den Messungen vom 29.–31.10.2026 nach, und stehende Regeln bewegten das nicht.
Wie bei den Hausversuchen (:mod:`app.pedagogy.hausversuche`) wird aus der allgemeinen Regel eine
konkrete Anweisung für genau diese Antwort, an der letzten Stelle des Systemtexts. Wo sie gesetzt
war, hielt die Zusage (Schritt 9: 6 von 6); der Engpass war die **Erkennung**.

**Zwei Auslöser, zwei Wege der Erkennung, ODER-verknüpft:**

- *Muster* (`config/druck_triggers.yaml`) für die eindeutigen Fälle;
- *Korpus* (`config/druck_korpus.yaml`): Beispielsätze je Art, beim ersten Gebrauch eingebettet.
  Treffer, wenn der nächste Satz der Art näher liegt als die Schwelle **und** näher als der nächste
  Gegensatz (`kein_druck`, `kein_lehrkraft`) — die Gegenbeispiel-Regel des Vorschlags. Den Vektor
  der aktuellen Nachricht hat die Vorab-Suche schon berechnet.

**Nachsetzen** (`nachsetzen`): nur in Assistenten mit `begleiten_statt_loesen`. Den ersten Druck
hält der Baustein; die Anweisung gilt für die **beiden Antworten danach** (Jan, 31.10.2026, F36 a):
War eine der beiden vorherigen Schülernachrichten Druck, bekommt die Antwort die Anweisung — auch
wenn die aktuelle Bitte nur einen Teil der Lösung verlangt und weder Muster noch Korpus sie
erkennen. Ob die vorherigen Druck waren, steht in `zug_ausloeser` (Migration 0094), sonst prüfen
es die Muster am Text; neu eingebettet wird nichts.

**Lehrkraft-Behauptung** (`lehrkraft`): in **allen** Schüler-Chats, schon beim ersten Treffer —
auch im freien Chat bekäme die Behauptung sonst, was der Assistent verweigert. Erkannt **satzweise**
(F35): In einer langen Nachricht mit Aufgabe überdeckt die Aufgabe den Satz, auf den es ankommt.
Die Sätze werden nur eingebettet, wenn die Nachricht ein Wort aus :data:`ROLLE` enthält.

⚠️ **Keine Sperre**, und eine Prompt-Anweisung wird ihrerseits nur wahrscheinlich befolgt. Beide
Auslöser sollen verbessern, nicht garantieren (Jan, 31.10.2026).

⚠️ **Fehlt eine Datei, greift nur, was da ist** (Warnung im Log): ohne Muster-Datei nichts, ohne
Korpus nur die Muster. Anders als bei den Hausversuchen hängt keine Sicherheitszusage daran.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, PrivateAttr, model_validator

from app.config import settings
from app.core.paths import aufloesen
from app.crisis.config import normalize

logger = logging.getLogger(__name__)

#: Wie viele Schülernachrichten vor der aktuellen nach einem früheren Treffer abgesucht werden.
FENSTER = 2
#: Nur Assistenten mit diesem Baustein — die Nachsetz-Anweisung setzt sein Antwortschema voraus.
BAUSTEIN = "begleiten_statt_loesen"
#: Arten im Korpus: je Auslöser die Art und ihr Gegensatz.
ARTEN = {"druck": "kein_druck", "lehrkraft": "kein_lehrkraft"}
#: Vorfilter der satzweisen Lehrkraft-Erkennung: Ohne eines dieser Wörter behauptet niemand,
#: Lehrkraft zu sein — dann kein zusätzlicher Embedding-Aufruf.
ROLLE = re.compile(r"lehr|unterricht|referendar|schuldienst|kollegium|klasse|kurs|schüler", re.I)
#: Satzgrenzen für die satzweise Erkennung.
_SATZ = re.compile(r"(?<=[.!?;:])\s+|\n+")


class Ausloeser(BaseModel):
    patterns: list[str] = Field(min_length=1)
    anweisung: str = Field(min_length=1)

    _compiled: list[re.Pattern] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _kompiliere(self) -> "Ausloeser":
        self._compiled = [re.compile(normalize(p)) for p in self.patterns]
        return self

    def trifft(self, text: str) -> bool:
        n = normalize(text or "")
        return bool(n.strip()) and any(p.search(n) for p in self._compiled)


class Druckausloeser(BaseModel):
    nachsetzen: Ausloeser
    lehrkraft: Ausloeser


class Satz(BaseModel):
    text: str = Field(min_length=1)
    art: str


class Korpus(BaseModel):
    #: Kosinus-Distanz, unter der ein Satz der Art als Treffer gilt — je Art.
    schwellen: dict[str, float]
    saetze: list[Satz] = Field(min_length=1)

    @model_validator(mode="after")
    def _arten(self) -> "Korpus":
        erlaubt = set(ARTEN) | set(ARTEN.values())
        fremd = {s.art for s in self.saetze} - erlaubt
        if fremd:
            raise ValueError(f"Unbekannte Art im Korpus: {sorted(fremd)}")
        return self


@dataclass(frozen=True)
class Erkennung:
    treffer: bool
    quelle: str | None = None                # regex | korpus
    abstand: float | None = None             # nächster Satz der Art
    gegen: float | None = None               # nächster Satz des Gegensatzes


@dataclass(frozen=True)
class Befund:
    """Für den Messkanal: Erkennung der aktuellen Nachricht, Treffer in den letzten drei, ob die
    Anweisung gesetzt wurde."""

    erkennung: Erkennung
    zaehler: int
    anweisung: bool

    def debug(self) -> dict:
        e = self.erkennung
        return {"treffer": e.treffer, "quelle": e.quelle, "zaehler": self.zaehler,
                "anweisung": self.anweisung,
                "abstand": None if e.abstand is None else round(e.abstand, 3),
                "gegen": None if e.gegen is None else round(e.gegen, 3)}


# ── Reine Funktionen ─────────────────────────────────────────────────────────


def abstand(v: Sequence[float], w: Sequence[float]) -> float:
    """Kosinus-Distanz (1 − Kosinus), wie `cosine_distance` in pgvector."""
    dot = sum(a * b for a, b in zip(v, w))
    nv = math.sqrt(sum(a * a for a in v))
    nw = math.sqrt(sum(b * b for b in w))
    return 1.0 if nv == 0 or nw == 0 else 1.0 - dot / (nv * nw)


def naechster(vektor: Sequence[float], vektoren: Sequence[Sequence[float]]) -> float:
    return min((abstand(vektor, w) for w in vektoren), default=math.inf)


def saetze(text: str) -> list[str]:
    """Die Sätze einer Nachricht (mindestens vier Zeichen), ohne die ganze Nachricht."""
    return [t for t in (x.strip() for x in _SATZ.split(text or "")) if len(t) > 3]


def urteil(art: str, text: str, vektor: Sequence[float] | None, ausloeser: Ausloeser,
           vektoren: dict[str, list[list[float]]] | None, schwelle: float | None) -> Erkennung:
    """Muster zuerst; sonst Korpus mit Schwelle und Gegenbeispiel-Regel."""
    d_pos = d_neg = None
    if vektor is not None and vektoren:
        d_pos = naechster(vektor, vektoren.get(art, []))
        d_neg = naechster(vektor, vektoren.get(ARTEN[art], []))
    if ausloeser.trifft(text):
        return Erkennung(True, "regex", d_pos, d_neg)
    if d_pos is not None and schwelle is not None and d_pos < schwelle and d_pos < d_neg:
        return Erkennung(True, "korpus", d_pos, d_neg)
    return Erkennung(False, None, d_pos, d_neg)


# ── Laden ────────────────────────────────────────────────────────────────────

_konfig: Druckausloeser | None = None
_korpus: Korpus | None = None
_vektoren: dict[str, list[list[float]]] | None = None
_vektoren_modell: str | None = None
_gemeldet: set[str] = set()


def _melde_einmal(schluessel: str, text: str, *args) -> None:
    if schluessel not in _gemeldet:
        logger.warning(text, *args)
        _gemeldet.add(schluessel)


def load_druck() -> Druckausloeser | None:
    """Die Muster (einmalig); ``None``, wenn die Datei fehlt."""
    global _konfig
    if _konfig is not None:
        return _konfig
    pfad: Path = aufloesen(settings.druck_triggers_path)
    if not pfad.exists():
        _melde_einmal("muster", "Nachsetz-/Lehrkraft-Auslöser nicht gefunden unter %s — sie greifen nicht.", pfad)
        return None
    with open(pfad, "r", encoding="utf-8") as f:
        _konfig = Druckausloeser.model_validate(yaml.safe_load(f) or {})
    logger.info("Nachsetz-/Lehrkraft-Auslöser geladen von %s", pfad)
    return _konfig


def load_korpus() -> Korpus | None:
    """Der Korpus (einmalig); ``None``, wenn die Datei fehlt — dann gelten nur die Muster."""
    global _korpus
    if _korpus is not None:
        return _korpus
    pfad: Path = aufloesen(settings.druck_korpus_path)
    if not pfad.exists():
        _melde_einmal("korpus", "Korpus der Auslöser nicht gefunden unter %s — nur die Muster greifen.", pfad)
        return None
    with open(pfad, "r", encoding="utf-8") as f:
        _korpus = Korpus.model_validate(yaml.safe_load(f) or {})
    logger.info("Korpus der Auslöser geladen von %s (%d Sätze)", pfad, len(_korpus.saetze))
    return _korpus


async def korpus_vektoren() -> dict[str, list[list[float]]] | None:
    """Die Korpus-Sätze eingebettet, je Art — einmal je Embedding-Modell. Bei einem Fehler
    ``None`` (dann nur die Muster) und beim nächsten Zug ein neuer Versuch."""
    global _vektoren, _vektoren_modell
    korpus = load_korpus()
    if korpus is None:
        return None
    if _vektoren is not None and _vektoren_modell == settings.embedding_model:
        return _vektoren
    from app.context.embedding import generate_embeddings
    try:
        stapel = await generate_embeddings([s.text for s in korpus.saetze])
    except Exception:
        logger.exception("Korpus der Auslöser nicht eingebettet — nur die Muster greifen.")
        return None
    je_art: dict[str, list[list[float]]] = {}
    for s, v in zip(korpus.saetze, stapel.vektoren):
        je_art.setdefault(s.art, []).append(v)
    _vektoren, _vektoren_modell = je_art, settings.embedding_model
    return _vektoren


def invalidate_druck_cache() -> None:
    global _konfig, _korpus, _vektoren, _vektoren_modell
    _konfig = _korpus = _vektoren = _vektoren_modell = None
    _gemeldet.clear()


# ── Entscheidung ─────────────────────────────────────────────────────────────


async def nachsetzen_fuer(aktuell: str, vektor, vorher: Sequence[str], frueher_druck: Sequence[bool] = (),
                          *, student_treatment: bool, bausteine: Sequence[str] | None) -> Befund | None:
    """Gilt die Nachsetz-Anweisung für diese Antwort? ``None``, wenn der Auslöser hier nicht gilt.

    ``vorher``: die Schülernachrichten vor der aktuellen, älteste zuerst. ``frueher_druck``: für
    dieselben Nachrichten, ob `zug_ausloeser` dort Druck erkannt hat (gleich lang oder leer)."""
    if not student_treatment or BAUSTEIN not in (bausteine or ()):
        return None
    konfig = load_druck()
    if konfig is None:
        return None
    korpus = load_korpus()
    schwelle = korpus.schwellen.get("druck") if korpus else None
    vektoren = await korpus_vektoren() if korpus else None
    jetzt = urteil("druck", aktuell, vektor, konfig.nachsetzen, vektoren, schwelle)
    texte = list(vorher)[-FENSTER:]
    flags = list(frueher_druck)[-FENSTER:] if len(frueher_druck) == len(vorher) else [False] * len(texte)
    frueher = sum(1 for t, f in zip(texte, flags) if f or konfig.nachsetzen.trifft(t))
    return Befund(jetzt, int(jetzt.treffer) + frueher, frueher > 0)


async def lehrkraft_fuer(aktuell: str, vektor, vorher: Sequence[str], *,
                         student_treatment: bool) -> Befund | None:
    """Behauptet die Schüler:in, Lehrkraft zu sein? Anweisung schon beim ersten Treffer und bei
    jedem weiteren („doch, ich bin wirklich Lehrerin“). Der Zähler ist nur Auskunft (Muster)."""
    if not student_treatment:
        return None
    konfig = load_druck()
    if konfig is None:
        return None
    korpus = load_korpus()
    schwelle = korpus.schwellen.get("lehrkraft") if korpus else None
    vektoren = await korpus_vektoren() if korpus else None
    jetzt = urteil("lehrkraft", aktuell, vektor, konfig.lehrkraft, vektoren, schwelle)
    teile = saetze(aktuell)
    if not jetzt.treffer and vektoren and schwelle is not None and len(teile) > 1 and ROLLE.search(aktuell):
        from app.context.embedding import generate_embeddings
        try:
            stapel = await generate_embeddings(teile)
        except Exception:
            logger.exception("Sätze nicht eingebettet — Lehrkraft nur über die ganze Nachricht.")
        else:
            for t, v in zip(teile, stapel.vektoren):
                e = urteil("lehrkraft", t, v, konfig.lehrkraft, vektoren, schwelle)
                if e.treffer:
                    jetzt = Erkennung(True, "korpus-satz", e.abstand, e.gegen)
                    break
    frueher = sum(konfig.lehrkraft.trifft(t) for t in list(vorher)[-FENSTER:])
    return Befund(jetzt, int(jetzt.treffer) + frueher, jetzt.treffer)


# ── Ablage (Migration 0094) ──────────────────────────────────────────────────


async def fruehere_druck_treffer(db, conversation_id, anzahl_vorher: int) -> list[bool]:
    """Für die Schülernachrichten 1 … ``anzahl_vorher``: ob dort Druck erkannt wurde."""
    import sqlalchemy as sa

    from app.db.models import ZugAusloeser
    if conversation_id is None or anzahl_vorher <= 0:
        return [False] * max(anzahl_vorher, 0)
    nummern = set((await db.execute(
        sa.select(ZugAusloeser.nutzer_nachricht).where(
            ZugAusloeser.conversation_id == conversation_id, ZugAusloeser.art == "druck",
            ZugAusloeser.treffer.is_(True))
    )).scalars().all())
    return [i in nummern for i in range(1, anzahl_vorher + 1)]


async def speichere(conversation_id, nutzer_nachricht: int, befunde: dict[str, Befund | None],
                    sitzungen=None) -> None:
    """Treffer und gesetzte Anweisungen ablegen — eigene Transaktion, wirft nie. Nur Zeilen mit
    Treffer oder Anweisung; kein Text."""
    zeilen = [(art, b) for art, b in befunde.items() if b is not None and (b.erkennung.treffer or b.anweisung)]
    if conversation_id is None or not zeilen:
        return
    from app.db.models import ZugAusloeser
    if sitzungen is None:
        from app.db.session import AsyncSessionLocal as sitzungen
    try:
        async with sitzungen() as db:
            for art, b in zeilen:
                db.add(ZugAusloeser(conversation_id=conversation_id, nutzer_nachricht=nutzer_nachricht,
                                    art=art, quelle=b.erkennung.quelle, treffer=b.erkennung.treffer,
                                    anweisung=b.anweisung))
            await db.commit()
    except Exception:
        logger.exception("Zug-Auslöser nicht abgelegt (Konversation %s)", conversation_id)


def anweisung(art: str) -> str:
    konfig = load_druck()
    if konfig is None:
        return ""
    return (konfig.nachsetzen if art in ("nachsetzen", "druck") else konfig.lehrkraft).anweisung.strip()
