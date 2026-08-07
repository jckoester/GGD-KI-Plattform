"""UP-8 Schritt 7 — Unterrichtsgruppen aus dem Stundenplan vorschlagen.

Kernstück ist `test_unbekanntes_fach_wird_gemeldet`: Ein Fach, das die Plattform nicht
kennt, ist der häufigste Grund für eine fehlende Gruppe. Es still auszulassen ließe den
Anwender mit einer unerklärlichen Lücke zurück.
"""
import pytest

from app.calendar.groups import code_varianten, match_groups, resolve_subject
from app.calendar.patterns import GroupKey


# ── Schreibweisen der Fachkürzel ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "code,erwartet",
    [
        ("M", ["M"]),
        ("m", ["M"]),                 # Groß-/Kleinschreibung schwankt: nwt neben NWT
        ("M1", ["M1", "M"]),          # Parallelkurs
        ("bio2", ["BIO2", "BIO"]),
        ("g3", ["G3", "G"]),
        ("PRÄS", ["PRÄS"]),           # Umlaut bleibt — es ist ein Kürzel, kein Slug
        ("  e1 ", ["E1", "E"]),
    ],
)
def test_code_varianten(code, erwartet):
    assert code_varianten(code) == erwartet


def test_exakte_variante_kommt_vor_der_gekuerzten():
    """`L2` ist ein eigenes Fach (zweite Fremdsprache), nicht der Kurs 2 von `L`.

    Stünde die gekürzte Form vorn, träfe jedes zifferngeschriebene Fach das falsche.
    """
    assert code_varianten("L2")[0] == "L2"


# ── Fake-Datenbank ───────────────────────────────────────────────────────────


class FakeDB:
    """Nur so viel Datenbank, wie `resolve_subject` und `match_groups` brauchen."""

    def __init__(self, subjects, groups=()):
        # subjects: [(id, slug, fach_code, untis_codes)]
        self.subjects = subjects
        self.groups = list(groups)   # [(id, name, subject_id)]

    async def scalar(self, stmt):
        beschreibung = str(stmt)
        werte = _werte(stmt)
        if "untis_codes" in beschreibung:
            gesucht = werte[0]
            for sid, _slug, _fc, codes in self.subjects:
                if gesucht in codes:
                    return sid
            return None
        if "fach_code" in beschreibung:
            gesucht = werte[0]
            for sid, _slug, fc, _codes in self.subjects:
                if (fc or "").upper() == gesucht:
                    return sid
            return None
        # `SELECT subjects.slug ... WHERE subjects.id = :x` — Slug zu einer ID.
        if beschreibung.strip().startswith("SELECT subjects.slug") and "subjects.id" in beschreibung:
            gesucht = werte[0]
            for sid, slug, _fc, _codes in self.subjects:
                if sid == gesucht:
                    return slug
            return None
        # `SELECT subjects.id ... WHERE lower(subjects.slug) = :x` — ID zu einem Slug.
        if "subjects.slug" in beschreibung and "WHERE" in beschreibung:
            gesucht = werte[0]
            for sid, slug, _fc, _codes in self.subjects:
                if slug.lower() == str(gesucht).lower():
                    return sid
            return None
        return None

    async def execute(self, stmt):
        werte = _werte(stmt)
        subject_id = werte[-1] if werte else None

        class Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return Result(
            [(gid, name) for gid, name, sid in self.groups if sid == subject_id]
        )


def _werte(stmt):
    """Die gebundenen Parameter eines Statements — Reihenfolge wie im SQL."""
    return [
        p.value
        for p in stmt.compile().binds.values()
        if p.value is not None
    ]


SUBJECTS = [
    # `MD` (Differenzierungsstunde) gehört zu Mathematik — so ist es auch in
    # config/subjects.yaml eingetragen.
    (1, "mathematik", "M", ["M", "MD"]),
    (2, "ethik", "ETH", ["ET"]),
    (3, "informatik", "INFWFO", ["INF"]),
    (4, "ium", None, ["IUM"]),
]


# ── Fachauflösung ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("code,subject_id", [("M", 1), ("ET", 2), ("INF", 3), ("IUM", 4)])
async def test_untis_codes_loesen_auf(code, subject_id):
    assert await resolve_subject(FakeDB(SUBJECTS), code) == subject_id


@pytest.mark.asyncio
async def test_parallelkurs_loest_auf_dasselbe_fach_auf():
    assert await resolve_subject(FakeDB(SUBJECTS), "M2") == 1


@pytest.mark.asyncio
async def test_bildungsplan_kuerzel_ist_kein_stundenplan_kuerzel():
    """Der Befund, der das eigene Feld nötig machte: ETH ≠ ET, INFWFO ≠ INF.

    Ohne `untis_codes` löste sich von elf beobachteten Kürzeln genau eines auf.
    """
    ohne_untis = [(sid, slug, fc, []) for sid, slug, fc, _ in SUBJECTS]
    assert await resolve_subject(FakeDB(ohne_untis), "ET") is None
    assert await resolve_subject(FakeDB(ohne_untis), "INF") is None
    # `ETH` träfe — aber so heißt das Fach im Stundenplan eben nicht.
    assert await resolve_subject(FakeDB(ohne_untis), "ETH") == 2


@pytest.mark.asyncio
async def test_unbekanntes_kuerzel_bleibt_offen():
    assert await resolve_subject(FakeDB(SUBJECTS), "PRÄS") is None


# ── Abgleich ─────────────────────────────────────────────────────────────────


def key(fach, klassen, gruppe=None):
    return GroupKey(student_group=gruppe, subject=fach, class_names=klassen)


@pytest.mark.asyncio
async def test_fehlende_gruppe_wird_vorgeschlagen():
    ergebnis = await match_groups(FakeDB(SUBJECTS), [key("M", ("5C",))])
    assert len(ergebnis.fehlend) == 1
    vorschlag = ergebnis.fehlend[0]
    assert vorschlag.subject_id == 1
    assert vorschlag.class_names == ("5C",)


@pytest.mark.asyncio
async def test_vorhandene_gruppe_wird_nicht_vorgeschlagen():
    """Vorgeschlagen wird nur, was fehlt — sonst entstünden Dubletten."""
    db = FakeDB(SUBJECTS, groups=[(10, "Mathematik 5c", 1)])
    ergebnis = await match_groups(db, [key("M", ("5C",))])
    assert ergebnis.fehlend == []
    assert len(ergebnis.vorhanden) == 1


@pytest.mark.asyncio
async def test_gruppe_eines_anderen_fachs_zaehlt_nicht_als_treffer():
    db = FakeDB(SUBJECTS, groups=[(10, "Ethik 5c", 2)])
    ergebnis = await match_groups(db, [key("M", ("5C",))])
    assert len(ergebnis.fehlend) == 1


@pytest.mark.asyncio
async def test_unbekanntes_fach_wird_gemeldet():
    """Die Abnahme aus dem Plan.

    An echten Daten trifft das `MD` und `PRÄS` — Kürzel, hinter denen kein Fach der
    Plattform steht. Sie stumm zu überspringen hieße, eine Lücke ohne Erklärung zu
    hinterlassen.
    """
    ergebnis = await match_groups(
        FakeDB(SUBJECTS), [key("PRÄS", ("PRÄ",)), key("PRÄS", ("PRÄ",)), key("M", ("5C",))]
    )
    assert [u.code for u in ergebnis.unbekannte_faecher] == ["PRÄS"]
    assert ergebnis.unbekannte_faecher[0].klassen == ("PRÄ",)
    # Das auflösbare Fach kommt trotzdem durch — ein unbekanntes bremst nicht alles aus.
    assert len(ergebnis.fehlend) == 1


@pytest.mark.asyncio
async def test_haeufigkeit_wird_mitgezaehlt():
    """Damit sich beurteilen lässt, ob ein unbekanntes Kürzel Pflege lohnt."""
    schluessel = key("PRÄS", ("PRÄ",))
    ergebnis = await match_groups(FakeDB(SUBJECTS), [schluessel, schluessel, schluessel])
    assert ergebnis.unbekannte_faecher[0].stunden == 3


@pytest.mark.asyncio
async def test_ohne_klasse_getrennt_gemeldet():
    """Kein Fachproblem, sondern ein Datenproblem — deshalb ein eigener Topf."""
    ergebnis = await match_groups(FakeDB(SUBJECTS), [key("M", ())])
    assert ergebnis.ohne_klasse and not ergebnis.fehlend
    assert not ergebnis.unbekannte_faecher


@pytest.mark.asyncio
async def test_ohne_fach_getrennt_gemeldet():
    ergebnis = await match_groups(FakeDB(SUBJECTS), [key(None, ("5C",))])
    assert ergebnis.ohne_klasse and not ergebnis.unbekannte_faecher


@pytest.mark.asyncio
async def test_gruppe_ueber_mehrere_klassen():
    """Ethik wird klassenübergreifend unterrichtet — der Vorschlag nennt alle."""
    ergebnis = await match_groups(
        FakeDB(SUBJECTS), [key("ET", ("5A", "5B", "5C"), gruppe="ET_5_BU")]
    )
    assert ergebnis.fehlend[0].class_names == ("5A", "5B", "5C")


# ── Kursart aus der Groß-/Kleinschreibung ────────────────────────────────────

from app.calendar.groups import (  # noqa: E402
    BASISKURS,
    LEISTUNGSKURS,
    REGULAER,
    ist_kursstufe,
    kursart,
)


@pytest.mark.parametrize(
    "klassen,erwartet",
    [
        (("11",), True),
        (("12",), True),
        (("11", "12"), True),
        (("J1",), True),
        (("5A",), False),
        (("10D",), False),
        (("PRÄ",), False),
        ((), False),
    ],
)
def test_ist_kursstufe(klassen, erwartet):
    """Sek-I-Klassen tragen immer einen Buchstaben (5A…10D), die Kursstufe nicht."""
    assert ist_kursstufe(klassen) is erwartet


@pytest.mark.parametrize(
    "code,klassen,erwartet",
    [
        # Kursstufe: die Schreibweise entscheidet
        ("bio", ("11",), BASISKURS),
        ("m1", ("11",), BASISKURS),
        ("g3", ("11", "12"), BASISKURS),
        ("BIO", ("11",), LEISTUNGSKURS),
        ("GEO", ("11",), LEISTUNGSKURS),
        ("D2", ("12",), LEISTUNGSKURS),
        # Sek I: immer regulärer Unterricht
        ("BIO", ("5C",), REGULAER),
        ("M", ("9C",), REGULAER),
    ],
)
def test_kursart(code, klassen, erwartet):
    """Kleingeschrieben = Basiskurs, großgeschrieben = Leistungskurs bzw. Sek-I-Unterricht.

    An den echten Daten belegt: Kleingeschriebene Kürzel kamen **ausschließlich** mit den
    Klassen 11 und 12 vor.
    """
    assert kursart(code, klassen) == erwartet


@pytest.mark.asyncio
async def test_basis_und_leistungskurs_sind_zwei_gruppen():
    """Der Kern der Korrektur.

    Würde die Schreibweise normalisiert, ergäbe Biologie 11 **eine** Gruppe statt zweier —
    und die Lehrkraft fände einen ihrer Kurse nicht wieder.
    """
    ergebnis = await match_groups(
        FakeDB(SUBJECTS + [(5, "biologie", "BIO", ["BIO"])]),
        [key("bio", ("11",)), key("BIO", ("11",))],
    )
    assert len(ergebnis.fehlend) == 2
    arten = {v.kursart for v in ergebnis.fehlend}
    assert arten == {BASISKURS, LEISTUNGSKURS}
    # Die Namen müssen unterscheidbar sein — sonst nützt die Trennung nichts.
    namen = {v.vorschlag_name for v in ergebnis.fehlend}
    assert len(namen) == 2
    assert all("kurs" in n.lower() for n in namen)


@pytest.mark.asyncio
async def test_gruppe_mit_kursart_im_namen_trifft_genau():
    db = FakeDB(
        SUBJECTS + [(5, "biologie", "BIO", ["BIO"])],
        groups=[(10, "Biologie 11 Basiskurs", 5)],
    )
    ergebnis = await match_groups(db, [key("bio", ("11",)), key("BIO", ("11",))])
    assert len(ergebnis.vorhanden) == 1
    assert len(ergebnis.fehlend) == 1
    assert ergebnis.fehlend[0].kursart == LEISTUNGSKURS


@pytest.mark.asyncio
async def test_gruppe_ohne_kursart_wird_als_mehrdeutig_gemeldet():
    """Statt zu raten, welcher der beiden Kurse gemeint ist.

    Ein Namenstreffer auf „Biologie 11" unterdrückte sonst systematisch einen der beiden
    Vorschläge — und zwar immer denselben.
    """
    db = FakeDB(
        SUBJECTS + [(5, "biologie", "BIO", ["BIO"])],
        groups=[(10, "Biologie 11", 5)],
    )
    ergebnis = await match_groups(db, [key("bio", ("11",))])
    assert ergebnis.fehlend           # Vorschlag bleibt stehen
    assert ergebnis.mehrdeutig
    assert "Kursart" in ergebnis.mehrdeutig[0]


@pytest.mark.asyncio
async def test_sek_eins_braucht_keine_kursart():
    """Dort gibt es die Unterscheidung nicht — der Name bleibt schlicht."""
    db = FakeDB(SUBJECTS, groups=[(10, "Mathematik 5c", 1)])
    ergebnis = await match_groups(db, [key("M", ("5C",))])
    assert ergebnis.vorhanden and not ergebnis.mehrdeutig


# ── Kürzel, hinter denen kein Unterricht steht ───────────────────────────────


def test_kein_unterricht_liste_kommt_aus_der_config():
    """Schulspezifisch, deshalb Konfiguration: Präsenzstunde, Personalrat, Schulleitung."""
    from app.calendar.groups import kein_unterricht_codes

    codes = kein_unterricht_codes()
    assert {"PRÄS", "ÖPR", "SL"} <= codes


def test_dienstliche_termine_erzeugen_kein_muster():
    """Der Unterschied zu einem unbekannten Fach ist der Handlungsbedarf.

    Ein unbekanntes Kürzel heißt: Hier fehlt ein Eintrag. Ein Diensttermin heißt: Hier
    fehlt nichts. Beides gleich zu melden ließe die echten Lücken darin untergehen.
    """
    from datetime import date, timedelta

    from app.calendar.base import Lesson, LessonState
    from app.calendar.patterns import derive_patterns

    montag = date(2026, 6, 8)
    wochen = [montag + timedelta(weeks=n) for n in range(4)]
    lessons = [
        Lesson(date=w, start_period=6, periods=1, state=LessonState.REGULAR,
               subject="PRÄS", class_names=("PRÄ",))
        for w in wochen
    ]
    ergebnis = derive_patterns(
        lessons, wochen=wochen, kein_unterricht=frozenset({"PRÄS"})
    )
    assert ergebnis.proposals == []
    assert any("Nicht als Unterricht" in h for h in ergebnis.hinweise)


# ── Gleichnamige Gruppen ─────────────────────────────────────────────────────


SPORT = (6, "sport", "SPO", ["SP", "SPM", "SPW"])


@pytest.mark.asyncio
async def test_studentgroup_trennt_gleiches_fach_in_gleicher_klasse():
    """`SPM_7_RO` und `SPW_7_GÜN` — Sport männlich und weiblich, dieselben Klassen.

    In den echten Daten trägt **jede** solche Stunde ein `studentGroup`; ohne es wäre die
    Unterscheidung unmöglich. Die Namen kollidieren trotzdem (beide „sport 7A/7D"),
    deshalb der Kürzel-Zusatz — kollisionsgetrieben, nicht als Sonderfall für Sport.
    """
    db = FakeDB(SUBJECTS + [SPORT])
    ergebnis = await match_groups(
        db,
        [
            key("SPM", ("7A", "7D"), gruppe="SPM_7_RO"),
            key("SPW", ("7A", "7D"), gruppe="SPW_7_GÜN"),
        ],
    )
    namen = sorted(v.vorschlag_name for v in ergebnis.fehlend)
    assert namen == ["sport 7A/7D [SPM]", "sport 7A/7D [SPW]"]


@pytest.mark.asyncio
async def test_differenzierungsstunde_ist_dieselbe_gruppe():
    """`M` und `MD` in 5C — Differenzierungsstunde Mathematik.

    Gleiche Klasse, gleiche Lehrkraft, gleiches Curriculum, **kein** `studentGroup`. Das
    ist eine weitere Stunde derselben Gruppe, keine zweite Gruppe. Getrennt vorgeschlagen
    entstünde eine Dublette, die die Lehrkraft von Hand wieder zusammenführen müsste.

    Belegt: In den echten Daten hat **keine** Stunde ohne `studentGroup` einen
    Kursstufen-Bezug — ohne `studentGroup` ist es immer regulärer Klassenunterricht.
    """
    db = FakeDB(SUBJECTS)
    ergebnis = await match_groups(db, [key("M", ("5C",)), key("MD", ("5C",))])
    assert len(ergebnis.fehlend) == 1
    vorschlag = ergebnis.fehlend[0]
    assert vorschlag.vorschlag_name == "mathematik 5C"
    assert vorschlag.codes == ("M", "MD")
    # Beide Muster gehören zu dieser einen Gruppe.
    assert len(vorschlag.keys) == 2


@pytest.mark.asyncio
async def test_parallelkurse_der_kursstufe_bleiben_getrennt():
    """`M1` und `M2` in 11 — zwei Kurse, je eigenes `studentGroup`."""
    db = FakeDB(SUBJECTS)
    ergebnis = await match_groups(
        db, [key("M1", ("11",), gruppe="M1_11"), key("M2", ("11",), gruppe="M2_11")]
    )
    assert len(ergebnis.fehlend) == 2


@pytest.mark.asyncio
async def test_eindeutige_namen_bleiben_schlicht():
    """Der Zusatz erscheint nur, wo er gebraucht wird."""
    db = FakeDB(SUBJECTS + [SPORT])
    ergebnis = await match_groups(
        db, [key("SPW", ("7A",), gruppe="SPW_7_KA"), key("M", ("5C",))]
    )
    assert all("[" not in v.vorschlag_name for v in ergebnis.fehlend)
