"""Gehört eine Gruppe zum laufenden Schuljahr?

**Warum das hier liegt und nicht im Router.** Die Frage stellt sich an zwei Stellen: in
der Gruppenliste (was zeigen wir als aktuell?) und beim Stundenplan-Abgleich (für welche
Gruppen lohnt der Hinweis „nicht mehr im Stundenplan"?). Zwei Fassungen derselben Regel
liefen auseinander — und die Abweichung fiele als widersprüchliche Auskunft auf, nicht
als Fehler.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode, LessonSlot
from app.planning.calendar import SchoolYearConfig


def ist_aktuell(gruppe, mit_beleg: set[int], cfg: SchoolYearConfig) -> bool:
    """Ob eine Gruppe zum laufenden Schuljahr gehört.

    Drei Fälle brauchen keine Ableitung:

    * **Kein Unterricht.** Klassen, Fachschaften und Arbeitsgruppen kennen kein
      Schuljahresende in diesem Sinne.
    * **Aus dem Schulkonto.** Für eine Gruppe mit `sso_group_id` ist die Mitgliedschaft
      bereits die Antwort: Der Immediate Mirror entfernt bei jeder Anmeldung, was das Token
      nicht mehr deckt. Steht der Kurs noch im Schulkonto, gibt es ihn. Das trägt zugleich
      den **Kursstufenkurs über zwei Schuljahre** — er hat am ersten Schultag weder Stunden
      noch Jahresplan im neuen Jahr und wäre sonst wochenlang „früher", ohne dass die
      Lehrkraft etwas dagegen tun könnte (der Stundenplan ist noch nicht veröffentlicht).
    * **Gerade erst angelegt.** Sie hat noch nichts, woran man sie erkennen könnte.

    Bleibt die Ableitung für von Hand angelegte und adoptierte Gruppen.

    ⚠️ **Korrektur 23.09.2026:** Hier stand, solche Gruppen seien „immer an eine Klasse
    gebunden (`POST /groups/teaching` verlangt eine `school_class`) und laufen deshalb
    nie über den Schuljahreswechsel". Seit AP3 stimmt das nicht mehr: Eine aus dem
    Stundenplan angelegte **Kursstufengruppe** hat gar keine Quellklasse und läuft sehr
    wohl über zwei Schuljahre. Sie hat am ersten Schultag weder Stunden noch Jahresplan
    und trägt kein `sso_group_id` — sie fällt hier also auf das Anlagedatum zurück und
    gilt wochenlang als „früher", bis der neue Stundenplan da ist. Genau der Fall, für
    den die SSO-Ausnahme oben gebaut wurde; die Kursstufengruppe aus dem Stundenplan
    erreicht sie nicht. Vermerkt in `Todo.md`.

    `mit_beleg` sind die Gruppen mit Stunden oder Planung im laufenden Schuljahr —
    ermittelt von `gruppen_mit_beleg`, in **einer** Abfrage für alle.
    """
    if gruppe.type != "teaching_group":
        return True
    if gruppe.sso_group_id:
        return True
    if gruppe.id in mit_beleg:
        return True
    # `astimezone()` vor `date()`: Der Zeitstempel kommt in der Zeitzone der
    # Datenbanksitzung zurück, der Schuljahresbeginn ist ein Kalendertag der Schule. Ohne
    # die Umrechnung entschied die Zeitzone über die Jahresgrenze — eine am ersten
    # Schultag um 00:30 angelegte Gruppe galt als im Vorjahr angelegt. Aufgefallen am
    # 15.09.2026, als der Integrationstest die Grenze mit einem reinen Datum traf.
    return gruppe.created_at.astimezone().date() >= cfg.beginn


async def gruppen_mit_beleg(
    db: AsyncSession, gruppen_ids: list[int], cfg: SchoolYearConfig
) -> set[int]:
    """Welche dieser Gruppen im laufenden Schuljahr Stunden oder Planung haben.

    Zwei Belege, weil sie zu verschiedenen Zeitpunkten entstehen: Der Jahresplan entsteht
    beim ersten Öffnen der Planung, die Stunden erst mit dem Stundenraster. Wer nur auf
    einen schaute, übersähe die halbe Wirklichkeit.
    """
    if not gruppen_ids:
        return set()
    stunden = select(LessonSlot.group_id).where(
        LessonSlot.group_id.in_(gruppen_ids),
        LessonSlot.date.between(cfg.beginn, cfg.ende),
    )
    planung = select(ContextNode.write_scope_group_id).where(
        ContextNode.write_scope_group_id.in_(gruppen_ids),
        ContextNode.schuljahr == cfg.schuljahr,
        ContextNode.status == "active",
    )
    zeilen = await db.execute(stunden.union(planung))
    return {zeile[0] for zeile in zeilen.all()}
