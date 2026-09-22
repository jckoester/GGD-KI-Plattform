"""Die Jahresplanung auf ein neues Stundenraster umhängen (AP3, 22.09.2026).

**Der Befund.** Ändert sich das Wochenmuster, baute `generate_slots(regenerate=True)` das
Halbjahr neu auf: Snapshot, alles löschen, neu erzeugen. Die Planung an den Slots — Einheit,
Stundenentwurf, Thema — war danach weg. `restore_snapshot` half nicht: Das ist ein
Rückgängig, kein Zusammenführen. Man bekam den alten Stand **oder** den neuen, nicht die
Planung auf den neuen Terminen. Zu Schuljahresbeginn ein vorläufiges 2. Halbjahr zu
erzeugen hätte damit im Februar ein halbes Jahr Arbeit gekostet.

**Die Richtung** (Entscheidung Jan, 22.09.2026): Die Planung **hängt an Terminen**. Ein
Wechsel zwischen Einzel- und Doppelstunde beeinflusst massiv, was für eine Stunde planbar
ist, und der Rhythmus dieses Wechsels hängt an Terminen. Ein terminloses Folgenmodell ist
deshalb verworfen. Umgehängt wird nach **Reihenfolge** — die Voraussetzung dafür ist die
Beobachtung aus der Praxis, dass die Gesamtzahl der Stunden über den Halbjahreswechsel
etwa gleich bleibt.

**Zweistufig** wie `plan_sync`/`apply_sync`: `plane_umhaengen` rechnet ohne Datenbank und
ohne Seiteneffekt, `wende_umhaengen_an` schreibt. Das erlaubt eine Vorschau und macht die
Regeln ohne Datenbank prüfbar.

**Vier Regeln:**

1. **Fixpunkte behalten ihr Datum**, nicht ihren Platz in der Reihenfolge. Eine
   Klassenarbeit am 12.03. bleibt am 12.03.
2. **Der Rest wandert nach Reihenfolge** auf die freien neuen Termine.
3. **Ändert sich der Umfang** (Einzel- ↔ Doppelstunde), wird der Termin mit
   `anpassung_noetig` markiert — nicht stillschweigend übernommen.
4. **Nichts wird verworfen.** Was keinen Termin findet, landet auf dem Parkplatz
   (`ParkedLessonContent`).

⚠️ **Wer hier hineingegeben wird, entscheidet der Aufrufer.** `plane_umhaengen` bekommt nur
die Slots, die tatsächlich verschwinden — also `source='pattern'`. Slots aus dem
Stundenplan oder von Hand überleben den Neuaufbau (AP1) und behalten ihren Inhalt dort, wo
er liegt. Gäbe man sie mit, würde ihr Inhalt kopiert und der Originalslot bliebe stehen:
eine Dublette.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonSlot, ParkedLessonContent
from app.planning.snapshots import create_snapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlterSlot:
    """Ein Slot, wie das Umhängen ihn braucht — ohne SQLAlchemy-Bindung."""

    id: object
    datum: date
    start_period: int | None
    periods: int
    kategorie: str
    pinned: bool
    ue_node_id: object | None = None
    stunde_node_id: object | None = None
    thema: str | None = None

    @property
    def hat_inhalt(self) -> bool:
        return bool(self.ue_node_id or self.stunde_node_id or (self.thema or "").strip())

    @property
    def ist_fixpunkt(self) -> bool:
        # Dieselbe Definition wie `reflow_service._is_fixpunkt` — es gibt nur eine.
        return self.pinned or self.kategorie == "pruefung"


@dataclass(frozen=True)
class NeuerTermin:
    datum: date
    start_period: int
    periods: int = 1


@dataclass(frozen=True)
class Zuordnung:
    termin: NeuerTermin
    quelle: AlterSlot
    anpassung_noetig: bool


@dataclass
class UmhaengePlan:
    zuordnungen: list[Zuordnung] = field(default_factory=list)
    # Die IDs **aller** übergebenen alten Slots — auch der inhaltsleeren, die in keiner
    # der Listen unten auftauchen. Ohne sie wüsste das Anwenden nicht, was zu löschen ist:
    # Eine Abfrage „alles mit `source='pattern'`" träfe auch die gerade angelegten Slots,
    # weil erst geschrieben und dann gelöscht wird.
    alte_ids: list = field(default_factory=list)
    # Fixpunkte, für die das neue Raster ihren Tag nicht kennt.
    nicht_zuordenbar: list[AlterSlot] = field(default_factory=list)
    # Inhalt ohne Termin — wird geparkt.
    ueberhang: list[AlterSlot] = field(default_factory=list)
    # Neue Termine ohne Inhalt. Kein Befund, nur Vorrat.
    freie_termine: list[NeuerTermin] = field(default_factory=list)
    meldungen: list[str] = field(default_factory=list)

    @property
    def abweichende_periods(self) -> int:
        return sum(1 for z in self.zuordnungen if z.anpassung_noetig)


def _sortiert(slots):
    # `start_period` kann NULL sein — dann zuerst, damit die Ordnung total bleibt.
    return sorted(slots, key=lambda s: (s.datum, s.start_period if s.start_period else 0))


def plane_umhaengen(
    alte_slots: list[AlterSlot], neues_raster: list[NeuerTermin]
) -> UmhaengePlan:
    """Rechnet, was wohin wandert. Ohne Datenbank, ohne Seiteneffekt."""
    plan = UmhaengePlan(alte_ids=[s.id for s in alte_slots])
    frei = sorted(neues_raster, key=lambda t: (t.datum, t.start_period))

    inhaltlich = _sortiert([s for s in alte_slots if s.hat_inhalt])
    fixpunkte = [s for s in inhaltlich if s.ist_fixpunkt]
    laufend = [s for s in inhaltlich if not s.ist_fixpunkt]

    def zuordnen(termin: NeuerTermin, quelle: AlterSlot) -> None:
        plan.zuordnungen.append(
            Zuordnung(
                termin=termin,
                quelle=quelle,
                anpassung_noetig=termin.periods != quelle.periods,
            )
        )

    # 1. Fixpunkte zuerst, datumsgleich — sie nehmen ihren Termin aus dem Vorrat, bevor
    #    die Reihenfolge verteilt wird. Andernfalls verschöbe eine Klassenarbeit sich mit.
    for f in fixpunkte:
        am_tag = [t for t in frei if t.datum == f.datum]
        if not am_tag:
            plan.nicht_zuordenbar.append(f)
            continue
        # Gleiche Stunde bevorzugt, sonst die erste des Tages.
        termin = next((t for t in am_tag if t.start_period == f.start_period), am_tag[0])
        frei.remove(termin)
        zuordnen(termin, f)

    # 2. Der Rest nach Reihenfolge auf die verbliebenen Termine.
    for s in laufend:
        if not frei:
            plan.ueberhang.append(s)
            continue
        zuordnen(frei.pop(0), s)

    plan.freie_termine = frei
    plan.meldungen = _meldungen(plan)
    return plan


def _meldungen(plan: UmhaengePlan) -> list[str]:
    """Lesbare Sätze — dasselbe Muster wie beim Stundenplan-Abgleich."""
    zeilen: list[str] = []
    anzahl = len(plan.zuordnungen)
    if anzahl:
        zeilen.append(
            f"{anzahl} {'Stunde' if anzahl == 1 else 'Stunden'} auf die neuen Termine "
            "umgehängt."
        )
    if plan.abweichende_periods:
        n = plan.abweichende_periods
        zeilen.append(
            f"{n} davon {'liegt' if n == 1 else 'liegen'} jetzt auf einem anderen Umfang "
            "(Einzel- statt Doppelstunde oder umgekehrt) und "
            f"{'ist' if n == 1 else 'sind'} als anzupassen markiert."
        )
    for f in plan.nicht_zuordenbar:
        zeilen.append(
            f"{f.datum}: Dieser Termin ist im neuen Raster nicht vorgesehen. Die Stunde "
            "bleibt stehen und ist als anzupassen markiert."
        )
    if plan.ueberhang:
        n = len(plan.ueberhang)
        zeilen.append(
            f"{n} {'Stunde' if n == 1 else 'Stunden'} ohne Termin — auf dem Parkplatz. "
            "Von dort umplanen oder durch Kürzen eingliedern."
        )
    if plan.freie_termine:
        n = len(plan.freie_termine)
        zeilen.append(f"{n} neue {'Stunde' if n == 1 else 'Stunden'} ohne Inhalt.")
    return zeilen


async def wende_umhaengen_an(
    db: AsyncSession,
    group_id: int,
    halbjahr: int,
    plan: UmhaengePlan,
    *,
    vorlaeufig: bool = False,
    created_by: str | None = None,
) -> int:
    """Schreibt den Plan. Gibt die Zahl der neu angelegten Slots zurück.

    **Reihenfolge:** Snapshot, dann die neuen Termine samt Inhalt anlegen, dann die alten
    löschen — und erst am Ende ein Commit. Bricht etwas dazwischen ab, ist nichts
    geschrieben; umgekehrt (erst löschen) stünde die Planung bei einem Abbruch nirgends
    mehr. Es gibt keinen Unique-Index auf `(group_id, date, start_period)` — alt und neu
    dürfen sich also kurz überlappen (nachgemessen 22.09.2026).

    ⚠️ **Fixpunkte ohne Termin im neuen Raster bleiben stehen** und wechseln auf
    `source='manual'`. Die Entscheidung löst einen Widerspruch der Regeln auf: E5 sagt
    „Fixpunkt behält sein Datum", E6 „nichts wird verworfen" — sie bloß zu *melden* und
    ihren Slot zu löschen hätte beides gebrochen. `manual` beschreibt danach den
    tatsächlichen Zustand: Dieser Termin wird von Hand gepflegt, nicht vom Muster, und der
    nächste Neuaufbau lässt ihn stehen (AP1).
    """
    await create_snapshot(db, group_id, reason="regeneration", created_by=created_by)

    # 1. Neue Termine mit Inhalt.
    for z in plan.zuordnungen:
        # ⚠️ **Kategorie und `pinned` wandern nicht mit — außer bei Fixpunkten.** Sie
        # beschreiben den **Termin**, nicht den Inhalt: `ausfall` heißt „hier findet
        # nichts statt", `vertretung` „hier unterrichtet jemand anders", `pinned` „diesen
        # Termin nicht anfassen". Auf einen frischen Termin aus dem neuen Muster
        # übertragen, markierte `ausfall` eine Stunde als abgesagt, die niemand abgesagt
        # hat. Ein Fixpunkt **bewegt sich nicht** (er behält sein Datum), deshalb behält
        # er beides — sonst würde aus einer Klassenarbeit eine gewöhnliche Stunde.
        fix = z.quelle.ist_fixpunkt
        db.add(
            LessonSlot(
                group_id=group_id,
                date=z.termin.datum,
                start_period=z.termin.start_period,
                periods=z.termin.periods,
                halbjahr=halbjahr,
                kategorie=z.quelle.kategorie if fix else "unterricht",
                pinned=z.quelle.pinned if fix else False,
                ue_node_id=z.quelle.ue_node_id,
                stunde_node_id=z.quelle.stunde_node_id,
                thema=z.quelle.thema,
                anpassung_noetig=z.anpassung_noetig,
                vorlaeufig=vorlaeufig,
            )
        )

    # 2. Neue Termine ohne Inhalt — der Vorrat des Halbjahres.
    for t in plan.freie_termine:
        db.add(
            LessonSlot(
                group_id=group_id,
                date=t.datum,
                start_period=t.start_period,
                periods=t.periods,
                halbjahr=halbjahr,
                kategorie="unterricht",
                vorlaeufig=vorlaeufig,
            )
        )

    # 3. Was keinen Termin bekam, auf den Parkplatz — nicht in den Papierkorb.
    for s in plan.ueberhang:
        db.add(
            ParkedLessonContent(
                group_id=group_id,
                halbjahr=halbjahr,
                herkunft_datum=s.datum,
                ue_node_id=s.ue_node_id,
                stunde_node_id=s.stunde_node_id,
                thema=s.thema,
            )
        )
    await db.flush()

    # 4. Die alten Slots löschen — außer den Fixpunkten, die stehen bleiben.
    bleiben = {s.id for s in plan.nicht_zuordenbar}
    zu_loeschen = [i for i in plan.alte_ids if i not in bleiben]
    if zu_loeschen:
        await db.execute(sa.delete(LessonSlot).where(LessonSlot.id.in_(zu_loeschen)))
    if bleiben:
        await db.execute(
            sa.update(LessonSlot)
            .where(LessonSlot.id.in_(bleiben))
            .values(source="manual", anpassung_noetig=True)
        )

    await db.commit()
    logger.info(
        "slots_umgehaengt gruppe=%s halbjahr=%s zuordnungen=%d abweichend=%d "
        "geparkt=%d fixpunkte_ohne_termin=%d",
        group_id, halbjahr, len(plan.zuordnungen), plan.abweichende_periods,
        len(plan.ueberhang), len(plan.nicht_zuordenbar),
    )
    return len(plan.zuordnungen) + len(plan.freie_termine)
