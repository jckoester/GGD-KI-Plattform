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

from app.db.models import ContextNode, GroupSourceClass, LessonSlot
from app.planning.calendar import SchoolYearConfig


def ist_aktuell(
    gruppe, mit_beleg: set[int], cfg: SchoolYearConfig, mit_quellklasse: set[int]
) -> bool:
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
    * **Ohne Quellklasse.** Eine Gruppe, die an keinen Klassenverband gebunden ist,
      ist auch an kein Schuljahr gebunden — Kursstufenkurse laufen über zwei. Das ist
      seit dem 25.09.2026 der eigentliche Grund; die SSO-Ausnahme darüber ist der
      Sonderfall davon, den es zuerst gab.
    * **Gerade erst angelegt.** Sie hat noch nichts, woran man sie erkennen könnte.

    Bleibt die Ableitung für von Hand angelegte und adoptierte Gruppen **mit** Klasse.

    ⚠️ **Behoben am 25.09.2026 (Paket 7, AP3).** Hier stand, die Ableitung gelte für
    Gruppen, die „immer an eine Klasse gebunden" seien — das stimmte seit dem
    Stundenplan-Anlegeweg nicht mehr: Eine **Kursstufengruppe** aus dem Stundenplan hat
    keine Quellklasse, trägt kein `sso_group_id` und fiel deshalb auf das Anlagedatum
    zurück. Im zweiten Schuljahr galt sie als ausgelaufen, bis der neue Stundenplan
    Stunden lieferte — die Lehrkraft fand ihren laufenden Kurs im Archiv. Jetzt
    entscheidet die **Quellklasse**, nicht die Herkunft.

    ⚠️ **Die SSO-Ausnahme bleibt trotzdem stehen**, obwohl der Todo sie ersetzen wollte.
    Sie deckt einen Fall ab, den die Quellklasse nicht abdeckt: Eine von Hand angelegte
    Gruppe *mit* Klasse, die später einem Schulkonto-Angebot zugeordnet wurde
    (`angebote.ordne_zu`), hat beides. Ohne die Zeile fiele sie in die Ableitung zurück
    und wäre am Schuljahresanfang „früher", bevor die erste Stunde steht.

    `mit_quellklasse` sind die Gruppen mit einem Eintrag in `group_source_classes` —
    ermittelt von `gruppen_mit_quellklasse`, in **einer** Abfrage für alle. Der Parameter
    hat bewusst **keinen Vorgabewert**: „leer" hieße „keine Gruppe hat eine Klasse" und
    damit „alles ist aktuell" — ein vergessenes Argument bliebe still folgenlos richtig
    aussehend.

    `mit_beleg` sind die Gruppen mit Stunden oder Planung im laufenden Schuljahr —
    ermittelt von `gruppen_mit_beleg`, in **einer** Abfrage für alle.
    """
    if gruppe.type != "teaching_group":
        return True
    if gruppe.sso_group_id:
        return True
    if gruppe.id not in mit_quellklasse:
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


async def gruppen_mit_quellklasse(db: AsyncSession, gruppen_ids: list[int]) -> set[int]:
    """Welche dieser Gruppen an einen Klassenverband gebunden sind.

    Die Gegenprobe zu `ist_aktuell`: Wer keine Quellklasse hat, hat auch kein
    Schuljahresende — Kursstufenkurse und Gruppen aus dem Stundenplan ohne Klasse.
    """
    if not gruppen_ids:
        return set()
    zeilen = await db.execute(
        select(GroupSourceClass.group_id).where(
            GroupSourceClass.group_id.in_(gruppen_ids)
        )
    )
    return {zeile[0] for zeile in zeilen.all()}
