"""Verstümmelte Herkunftsdateien von Fachbegriffen reparieren (0.14, einmalig).

Bis 0.14 las der Zip-Import Dateinamen ohne UTF-8-Kennzeichen als CP437 (siehe
`fachbegriffe_upload.eintragsname`). Aus `Hückel-Regel.md` — von macOS zerlegt
geschrieben, `u` + U+0308 — wurde die Herkunftsdatei `Hu╠êckel-Regel` und die Kennung
`ch-hu-ckel-regel`. Inhalt, Titel, Aliasse und Vektoren sind davon unberührt; falsch sind
nur diese beiden Verwaltungsangaben. Gefunden 06.10.2026: 15 Knoten auf Dev, 17 auf Prod.

⚠️ **Vor dem nächsten Import laufen lassen.** Der richtig gelesene Name ergibt die
richtige Kennung; findet der Import sie am Knoten nicht, legt er einen zweiten an.
Umgekehrt nützt die Reparatur ohne den behobenen Import nichts — die nächste Zip
verstümmelte wieder.

Aufruf über `scripts/fachbegriffe_namen_reparieren.py`. Ein zweiter Lauf findet nichts
mehr (außer gemeldeten Kollisionen, die er weiter meldet).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.fachbegriffe_import import SEED_ID, SEED_QUELLE, TYPEN, leite_id_ab
from app.db.models import ContextNode, Subject, ohne_aenderungsstempel


def zurueckgelesen(name: str) -> str | None:
    """Der gemeinte Name zu einem als CP437 gelesenen UTF-8-Namen — sonst ``None``.

    Umkehrbar, weil CP437 jedem der 256 Bytewerte genau ein Zeichen zuordnet: Zurück in
    CP437 kodiert ergibt der verstümmelte Name genau die Bytes aus dem Archiv. Ein richtig
    geschriebener Name übersteht das nicht — „ü" ist in CP437 das Byte 0x81, und das ist
    kein gültiges UTF-8 —, reines ASCII bleibt gleich. Beides heißt: nichts zu tun.
    """
    try:
        gemeint = name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if gemeint == name:
        return None
    return unicodedata.normalize("NFC", gemeint)


@dataclass
class Reparatur:
    titel: str
    fach: str
    alt_quelle: str
    neu_quelle: str
    alt_id: str | None
    #: Gleich `alt_id`, wenn die Kennung aus dem Frontmatter stammt (`id:`) — die hat die
    #: Fachschaft gesetzt, nicht der Dateiname.
    neu_id: str | None
    #: Titel des Knotens, dem die neue Kennung im Fach schon gehört. Dann wird **nichts**
    #: geschrieben: Zwei Knoten mit einer Kennung wären schlimmer als eine falsche.
    kollision: str | None = None


async def namen_reparieren(db: AsyncSession) -> list[Reparatur]:
    """Herkunftsdatei und — wo sie daraus abgeleitet war — Kennung zurücklesen.

    Schreibt, **committet aber nicht**: Der Aufrufer entscheidet (Probelauf).

    ⚠️ **Ohne Änderungsstempel und ohne die Vektoren anzufassen.** Inhaltlich ändert sich
    nichts; `updated_at` stünde sonst als „geändert am heute" unter jeder Antwort, die
    den Begriff im Kontext hatte. Und weil die Seed-Angaben nicht in den Prüfwert des
    Imports eingehen (`stand_hash`), hält der nächste Import die Knoten auch nicht für
    in der Oberfläche bearbeitet.
    """
    zeilen = (await db.execute(
        sa.select(ContextNode.id, ContextNode.subject_id, ContextNode.title,
                  ContextNode.metadata_, Subject.name, Subject.fach_code, Subject.slug)
        .join(Subject, Subject.id == ContextNode.subject_id)
        .where(ContextNode.content_type.in_(TYPEN),
               ContextNode.metadata_.has_key(SEED_QUELLE))
        .order_by(Subject.name, ContextNode.title)
    )).all()
    belegt = {
        (z.subject_id, z.metadata_.get(SEED_ID)): z for z in zeilen if z.metadata_.get(SEED_ID)
    }

    ergebnis: list[Reparatur] = []
    for z in zeilen:
        alt_quelle = str(z.metadata_[SEED_QUELLE])
        neu_quelle = zurueckgelesen(alt_quelle)
        if neu_quelle is None:
            continue
        praefix = z.fach_code or z.slug
        alt_id = z.metadata_.get(SEED_ID)
        # Nur eine **abgeleitete** Kennung folgt dem Namen.
        abgeleitet = bool(alt_id) and alt_id == leite_id_ab(praefix, alt_quelle)
        neu_id = leite_id_ab(praefix, neu_quelle) if abgeleitet else alt_id
        reparatur = Reparatur(z.title, z.name, alt_quelle, neu_quelle, alt_id, neu_id)

        inhaber = belegt.get((z.subject_id, neu_id))
        if abgeleitet and inhaber is not None and inhaber.id != z.id:
            reparatur.kollision = inhaber.title
            ergebnis.append(reparatur)
            continue

        metadata = {**z.metadata_, SEED_QUELLE: neu_quelle}
        if neu_id:
            metadata[SEED_ID] = neu_id
        await db.execute(
            sa.update(ContextNode)
            .where(ContextNode.id == z.id)
            .values(metadata_=metadata, **ohne_aenderungsstempel())
        )
        belegt.pop((z.subject_id, alt_id), None)
        belegt[(z.subject_id, neu_id)] = z
        ergebnis.append(reparatur)
    return ergebnis
