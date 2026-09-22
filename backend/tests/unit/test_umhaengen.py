"""Wie die Jahresplanung auf ein neues Stundenraster wandert (AP3, 22.09.2026).

`plane_umhaengen` rechnet ohne Datenbank — die Regeln sind hier vollständig prüfbar.
Geschrieben wird in `wende_umhaengen_an`; das prüft
`tests/integration/test_umhaengen_anwenden.py` gegen die Datenbank, weil dort die
Reihenfolge von Schreiben und Löschen zählt.
"""
from datetime import date

from app.planning.umhaengen import AlterSlot, NeuerTermin, plane_umhaengen

MO, DI, MI = date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)
MO2, DI2 = date(2026, 3, 9), date(2026, 3, 10)


def slot(id_, datum, *, periods=1, thema=None, kategorie="unterricht", pinned=False,
         start_period=1):
    return AlterSlot(
        id=id_, datum=datum, start_period=start_period, periods=periods,
        kategorie=kategorie, pinned=pinned, thema=thema,
    )


def termin(datum, *, periods=1, start_period=1):
    return NeuerTermin(datum=datum, start_period=start_period, periods=periods)


class TestGleicheAnzahl:
    def test_alles_zugeordnet_kein_befund(self):
        alt = [slot(1, MO, thema="A"), slot(2, MO2, thema="B")]
        plan = plane_umhaengen(alt, [termin(DI), termin(DI2)])

        assert [z.quelle.thema for z in plan.zuordnungen] == ["A", "B"]
        assert [z.termin.datum for z in plan.zuordnungen] == [DI, DI2]
        assert plan.ueberhang == []
        assert plan.nicht_zuordenbar == []
        assert plan.abweichende_periods == 0

    def test_reihenfolge_bleibt_reihenfolge(self):
        """Der Kern von E3: Der i-te Inhalt landet auf dem i-ten Termin."""
        alt = [slot(1, MI, thema="spät"), slot(2, MO, thema="früh")]
        plan = plane_umhaengen(alt, [termin(DI), termin(DI2)])
        # Nach Datum sortiert, nicht in Eingabereihenfolge.
        assert [z.quelle.thema for z in plan.zuordnungen] == ["früh", "spät"]


class TestUmfang:
    def test_doppelstunde_auf_einzelstunden_wird_markiert(self):
        """E4: Was für eine Doppelstunde geplant war, passt nicht ungeprüft in eine
        Einzelstunde — das ist der Grund, warum die Planung an Terminen hängt."""
        alt = [slot(1, MO, periods=2, thema="Versuchsreihe")]
        plan = plane_umhaengen(alt, [termin(DI, periods=1)])

        assert len(plan.zuordnungen) == 1
        assert plan.zuordnungen[0].anpassung_noetig is True
        assert plan.abweichende_periods == 1
        assert any("Umfang" in m for m in plan.meldungen)

    def test_gleicher_umfang_ohne_marke(self):
        alt = [slot(1, MO, periods=2, thema="A")]
        plan = plane_umhaengen(alt, [termin(DI, periods=2)])
        assert plan.zuordnungen[0].anpassung_noetig is False


class TestUeberhang:
    def test_ein_termin_weniger_gibt_genau_einen_ueberhang(self):
        alt = [slot(1, MO, thema="A"), slot(2, MO2, thema="B")]
        plan = plane_umhaengen(alt, [termin(DI)])

        assert len(plan.zuordnungen) == 1
        assert [s.thema for s in plan.ueberhang] == ["B"]
        assert any("Parkplatz" in m for m in plan.meldungen)

    def test_der_spaetere_inhalt_bleibt_uebrig(self):
        """Nicht der frühere: Was zuerst geplant war, wird zuerst unterrichtet."""
        alt = [slot(1, MO, thema="A"), slot(2, MO2, thema="B"), slot(3, DI2, thema="C")]
        plan = plane_umhaengen(alt, [termin(DI)])
        assert [s.thema for s in plan.ueberhang] == ["B", "C"]

    def test_inhaltsleere_slots_erzeugen_keinen_ueberhang(self):
        alt = [slot(1, MO), slot(2, MO2, thema="A")]
        plan = plane_umhaengen(alt, [termin(DI)])
        assert plan.ueberhang == []
        assert len(plan.zuordnungen) == 1


class TestFixpunkte:
    def test_klassenarbeit_behaelt_ihr_datum(self):
        """E5: nicht ihren Platz in der Reihenfolge, sondern ihr Datum."""
        alt = [
            slot(1, MO, thema="Vorbereitung"),
            slot(2, DI, kategorie="pruefung", thema="Klassenarbeit"),
        ]
        plan = plane_umhaengen(alt, [termin(MO2), termin(DI)])

        nach_thema = {z.quelle.thema: z.termin.datum for z in plan.zuordnungen}
        assert nach_thema["Klassenarbeit"] == DI, "Die Arbeit ist verschoben worden"
        assert nach_thema["Vorbereitung"] == MO2

    def test_gepinnter_slot_ist_auch_fixpunkt(self):
        alt = [slot(1, DI, pinned=True, thema="Exkursion")]
        plan = plane_umhaengen(alt, [termin(MO2), termin(DI)])
        assert plan.zuordnungen[0].termin.datum == DI

    def test_fixpunkt_ohne_termin_ist_nicht_zuordenbar(self):
        alt = [slot(1, DI, kategorie="pruefung", thema="Klassenarbeit")]
        plan = plane_umhaengen(alt, [termin(MO2)])

        assert plan.zuordnungen == []
        assert [s.thema for s in plan.nicht_zuordenbar] == ["Klassenarbeit"]
        # Der Termin darf nicht als Überhang durchgehen — er soll stehen bleiben.
        assert plan.ueberhang == []
        assert any("nicht vorgesehen" in m for m in plan.meldungen)

    def test_fixpunkt_bevorzugt_die_gleiche_stunde_am_tag(self):
        alt = [slot(1, DI, start_period=5, kategorie="pruefung", thema="KA")]
        plan = plane_umhaengen(
            alt, [termin(DI, start_period=1), termin(DI, start_period=5)]
        )
        assert plan.zuordnungen[0].termin.start_period == 5

    def test_fixpunkt_nimmt_seinen_termin_vor_der_reihenfolge(self):
        """Ohne diesen Vorrang schöbe die Reihenfolge die Klassenarbeit weg."""
        alt = [
            slot(1, MO, thema="A"),
            slot(2, DI, kategorie="pruefung", thema="KA"),
            slot(3, MI, thema="B"),
        ]
        plan = plane_umhaengen(alt, [termin(MO), termin(DI), termin(MI)])
        nach_thema = {z.quelle.thema: z.termin.datum for z in plan.zuordnungen}
        assert nach_thema["KA"] == DI
        assert nach_thema["A"] == MO
        assert nach_thema["B"] == MI


class TestRandfaelle:
    def test_leere_planung_gibt_keine_operation(self):
        plan = plane_umhaengen([slot(1, MO), slot(2, MO2)], [termin(DI)])
        assert plan.zuordnungen == []
        assert plan.ueberhang == []
        assert len(plan.freie_termine) == 1

    def test_mehr_termine_als_inhalt_ist_kein_befund(self):
        plan = plane_umhaengen([slot(1, MO, thema="A")], [termin(DI), termin(DI2)])
        assert len(plan.zuordnungen) == 1
        assert len(plan.freie_termine) == 1
        assert plan.ueberhang == []

    def test_alte_ids_sind_vollstaendig(self):
        """Das Anwenden löscht darüber — auch die inhaltsleeren Slots müssen drin sein."""
        alt = [slot(1, MO), slot(2, MO2, thema="A"), slot(3, DI2, thema="B")]
        plan = plane_umhaengen(alt, [termin(DI)])
        assert set(plan.alte_ids) == {1, 2, 3}

    def test_ohne_raster_wandert_alles_auf_den_parkplatz(self):
        alt = [slot(1, MO, thema="A"), slot(2, MO2, thema="B")]
        plan = plane_umhaengen(alt, [])
        assert len(plan.ueberhang) == 2
        assert plan.zuordnungen == []
