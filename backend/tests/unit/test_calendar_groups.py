"""UP-8 Schritt 7 — Unterrichtsgruppen aus dem Stundenplan vorschlagen.

Kernstück ist `test_unbekanntes_fach_wird_gemeldet`: Ein Fach, das die Plattform nicht
kennt, ist der häufigste Grund für eine fehlende Gruppe. Es still auszulassen ließe den
Anwender mit einer unerklärlichen Lücke zurück.
"""
import pytest

from app.calendar.groups import (
    Kandidat,
    code_varianten,
    match_groups,
    resolve_subject,
    zuordnen,
)
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


# Wer abruft. Die Gruppen der FakeDB tragen ihre Lehrkraft, weil `match_groups` seit dem
# 15.09.2026 nur noch unter den **eigenen** Gruppen sucht.
LEHRKRAFT = "pseudo-ich"
KOLLEGIN = "pseudo-andere"


class FakeDB:
    """Nur so viel Datenbank, wie `resolve_subject` und `match_groups` brauchen."""

    def __init__(self, subjects, groups=()):
        # subjects: [(id, slug, fach_code, untis_codes)]
        self.subjects = subjects
        self.groups = list(groups)   # siehe `gruppe()`

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
        # Über die **Namen** der gebundenen Parameter, nicht über ihre Position: Der
        # Mitgliedschafts-Join hat die Reihenfolge verschoben, und `werte[-1]` traf danach
        # die Rolle statt der Fach-ID.
        gebunden = _gebunden(stmt)
        pseudonym = gebunden.get("pseudonym_1")
        rolle = gebunden.get("role_in_group_1")

        class Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        # Fehlt eine Bedingung im Statement, filtert die Attrappe auch nicht danach —
        # sonst verhielte sich eine **entfernte** Einschränkung wie eine vorhandene, und
        # der Wächter darüber liefe ins Leere. (Genau das war am 15.09.2026 der Fall.)
        return Result(
            [
                (gid, name, sid, quellklasse, fach_code)
                for gid, name, sid, lehrkraft, mitgliedsrolle, quellklasse, fach_code in self.groups
                if (pseudonym is None or lehrkraft == pseudonym)
                and (rolle is None or mitgliedsrolle == rolle)
            ]
        )


def gruppe(
    gid,
    name,
    subject_id,
    *,
    lehrkraft=None,
    rolle="teacher",
    quellklasse=None,
    fach_code=None,
):
    """Eine Unterrichtsgruppe für die Attrappe — so, wie `_eigene_gruppen` sie liest.

    **Einzahl mit Absicht:** Die Abfrage joint auf `group_source_classes` und liefert je
    Quellklasse **eine Zeile**. Eine Gruppe aus 10a/10b/10c entsteht hier also durch drei
    `gruppe(...)`-Einträge mit derselben `gid` — genauso, wie die Datenbank sie liefert.
    """
    return (gid, name, subject_id, lehrkraft or LEHRKRAFT, rolle, quellklasse, fach_code)


def _werte(stmt):
    """Die gebundenen Parameter eines Statements — Reihenfolge wie im SQL."""
    return [
        p.value
        for p in stmt.compile().binds.values()
        if p.value is not None
    ]


def _gebunden(stmt) -> dict:
    """Die gebundenen Parameter nach ihrem Namen (`subject_id_1`, `pseudonym_1`, …)."""
    return {name: p.value for name, p in stmt.compile().binds.items()}


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
    ergebnis = await match_groups(FakeDB(SUBJECTS), [key("M", ("5C",))], pseudonym=LEHRKRAFT)
    assert len(ergebnis.fehlend) == 1
    vorschlag = ergebnis.fehlend[0]
    assert vorschlag.subject_id == 1
    assert vorschlag.class_names == ("5C",)


@pytest.mark.asyncio
async def test_vorhandene_gruppe_wird_nicht_vorgeschlagen():
    """Vorgeschlagen wird nur, was fehlt — sonst entstünden Dubletten."""
    db = FakeDB(SUBJECTS, groups=[gruppe(10, "Mathematik 5c", 1)])
    ergebnis = await match_groups(db, [key("M", ("5C",))], pseudonym=LEHRKRAFT)
    assert ergebnis.fehlend == []
    assert len(ergebnis.vorhanden) == 1


@pytest.mark.asyncio
async def test_gruppe_einer_kollegin_zaehlt_nicht_als_treffer():
    """Gesucht wird nur unter den eigenen Gruppen.

    Bis zum 15.09.2026 lief die Suche schulweit. Ein passender Name genügte, und der
    Vorschlag zeigte auf eine fremde Gruppe — wohin die Lehrkraft dann ihr Wochenmuster
    geschrieben hätte und wohin der tägliche Abgleich Entfall und Vertretung getragen
    hätte. Aufgefallen wäre es zuerst der Kollegin, in deren Jahresplanung fremde
    Änderungen auftauchen.
    """
    db = FakeDB(SUBJECTS, groups=[gruppe(10, "Mathematik 5c", 1, lehrkraft=KOLLEGIN)])
    ergebnis = await match_groups(db, [key("M", ("5C",))], pseudonym=LEHRKRAFT)
    assert ergebnis.vorhanden == []
    assert ergebnis.zuordnung == {}
    assert len(ergebnis.fehlend) == 1, "die eigene Gruppe fehlt tatsächlich"


@pytest.mark.asyncio
async def test_gleichnamige_gruppen_zweier_lehrkraefte_treffen_die_eigene():
    """Derselbe Name, zwei Lehrkräfte — der Namensabgleich allein entschiede falsch."""
    db = FakeDB(
        SUBJECTS,
        groups=[gruppe(10, "Mathematik 5c", 1, lehrkraft=KOLLEGIN), gruppe(11, "Mathematik 5c", 1)],
    )
    ergebnis = await match_groups(db, [key("M", ("5C",))], pseudonym=LEHRKRAFT)
    assert list(ergebnis.zuordnung.values()) == [11]


@pytest.mark.asyncio
async def test_mitgliedschaft_ohne_lehrkraft_rolle_zaehlt_nicht():
    """Dieselbe Bedingung wie in `require_group_teacher`: Mitglied **als Lehrkraft**.

    Eine Unterrichtsgruppe enthält auch ihre Schüler:innen. Ohne die Rollenbedingung
    entschiede eine beliebige Mitgliedschaft über den Treffer.
    """
    db = FakeDB(SUBJECTS, groups=[gruppe(10, "Mathematik 5c", 1, rolle="student")])
    ergebnis = await match_groups(db, [key("M", ("5C",))], pseudonym=LEHRKRAFT)
    assert ergebnis.vorhanden == []
    assert len(ergebnis.fehlend) == 1


@pytest.mark.asyncio
async def test_gruppe_eines_anderen_fachs_zaehlt_nicht_als_treffer():
    db = FakeDB(SUBJECTS, groups=[gruppe(10, "Ethik 5c", 2)])
    ergebnis = await match_groups(db, [key("M", ("5C",))], pseudonym=LEHRKRAFT)
    assert len(ergebnis.fehlend) == 1


@pytest.mark.asyncio
async def test_unbekanntes_fach_wird_gemeldet():
    """Die Abnahme aus dem Plan.

    An echten Daten trifft das `MD` und `PRÄS` — Kürzel, hinter denen kein Fach der
    Plattform steht. Sie stumm zu überspringen hieße, eine Lücke ohne Erklärung zu
    hinterlassen.
    """
    ergebnis = await match_groups(
        FakeDB(SUBJECTS),
        [key("PRÄS", ("PRÄ",)), key("PRÄS", ("PRÄ",)), key("M", ("5C",))],
        pseudonym=LEHRKRAFT,
    )
    assert [u.code for u in ergebnis.unbekannte_faecher] == ["PRÄS"]
    assert ergebnis.unbekannte_faecher[0].klassen == ("PRÄ",)
    # Das auflösbare Fach kommt trotzdem durch — ein unbekanntes bremst nicht alles aus.
    assert len(ergebnis.fehlend) == 1


@pytest.mark.asyncio
async def test_haeufigkeit_wird_mitgezaehlt():
    """Damit sich beurteilen lässt, ob ein unbekanntes Kürzel Pflege lohnt."""
    schluessel = key("PRÄS", ("PRÄ",))
    ergebnis = await match_groups(FakeDB(SUBJECTS), [schluessel, schluessel, schluessel], pseudonym=LEHRKRAFT)
    assert ergebnis.unbekannte_faecher[0].stunden == 3


@pytest.mark.asyncio
async def test_ohne_klasse_getrennt_gemeldet():
    """Kein Fachproblem, sondern ein Datenproblem — deshalb ein eigener Topf."""
    ergebnis = await match_groups(FakeDB(SUBJECTS), [key("M", ())], pseudonym=LEHRKRAFT)
    assert ergebnis.ohne_klasse and not ergebnis.fehlend
    assert not ergebnis.unbekannte_faecher


@pytest.mark.asyncio
async def test_ohne_fach_getrennt_gemeldet():
    ergebnis = await match_groups(FakeDB(SUBJECTS), [key(None, ("5C",))], pseudonym=LEHRKRAFT)
    assert ergebnis.ohne_klasse and not ergebnis.unbekannte_faecher


@pytest.mark.asyncio
async def test_gruppe_ueber_mehrere_klassen():
    """Ethik wird klassenübergreifend unterrichtet — der Vorschlag nennt alle."""
    ergebnis = await match_groups(
        FakeDB(SUBJECTS),
        [key("ET", ("5A", "5B", "5C"), gruppe="ET_5_BU")],
        pseudonym=LEHRKRAFT,
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
        pseudonym=LEHRKRAFT,
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
        groups=[gruppe(10, "Biologie 11 Basiskurs", 5)],
    )
    ergebnis = await match_groups(db, [key("bio", ("11",)), key("BIO", ("11",))], pseudonym=LEHRKRAFT)
    assert len(ergebnis.vorhanden) == 1
    assert len(ergebnis.fehlend) == 1
    assert ergebnis.fehlend[0].kursart == LEISTUNGSKURS


@pytest.mark.asyncio
async def test_zwei_kurse_auf_eine_gruppe_bleiben_unzugeordnet():
    """Statt zu raten, welcher der beiden Kurse gemeint ist.

    Eine Gruppe „Biologie 11" ohne Angabe der Kursart, dazu Basis- **und** Leistungskurs
    im Stundenplan. Wer hier „genau ein Kandidat" rechnet, legt beide auf dieselbe Gruppe.
    Deshalb muss die Zuordnung von beiden Seiten eindeutig sein.
    """
    db = FakeDB(
        SUBJECTS + [(5, "biologie", "BIO", ["BIO"])],
        groups=[gruppe(10, "Biologie 11", 5)],
    )
    ergebnis = await match_groups(
        db, [key("bio", ("11",)), key("BIO", ("11",))], pseudonym=LEHRKRAFT
    )
    assert ergebnis.vorhanden == []
    assert len(ergebnis.fehlend) == 2      # Vorschläge bleiben stehen
    assert len(ergebnis.mehrdeutig) == 2
    assert all("Biologie 11" in m for m in ergebnis.mehrdeutig)


@pytest.mark.asyncio
async def test_einzelner_kursstufenkurs_trifft_die_einzige_gruppe():
    """Der gemessene Fehlschlag vom 14.09.2026, andersherum.

    Der Stundenplan nennt die „Klasse" `11`, die Gruppe heißt `ch2-ks-abi28` — über den
    Namen findet sich nichts. Unter den **eigenen** Gruppen gibt es aber nur eine in
    diesem Fach, und im Stundenplan nur einen Kurs. Das ist eindeutig, ohne zu raten.
    """
    db = FakeDB(
        SUBJECTS + [(5, "chemie", "CH", ["CH"])],
        groups=[gruppe(58, "ch2-ks-abi28", 5)],
    )
    ergebnis = await match_groups(db, [key("CH2", ("11",))], pseudonym=LEHRKRAFT)
    assert list(ergebnis.zuordnung.values()) == [58]
    assert ergebnis.fehlend == []
    assert ergebnis.mehrdeutig == []


@pytest.mark.asyncio
async def test_sek_eins_braucht_keine_kursart():
    """Dort gibt es die Unterscheidung nicht — der Name bleibt schlicht."""
    db = FakeDB(SUBJECTS, groups=[gruppe(10, "Mathematik 5c", 1)])
    ergebnis = await match_groups(db, [key("M", ("5C",))], pseudonym=LEHRKRAFT)
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
        pseudonym=LEHRKRAFT,
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
    ergebnis = await match_groups(db, [key("M", ("5C",)), key("MD", ("5C",))], pseudonym=LEHRKRAFT)
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
        db,
        [key("M1", ("11",), gruppe="M1_11"), key("M2", ("11",), gruppe="M2_11")],
        pseudonym=LEHRKRAFT,
    )
    assert len(ergebnis.fehlend) == 2


@pytest.mark.asyncio
async def test_eindeutige_namen_bleiben_schlicht():
    """Der Zusatz erscheint nur, wo er gebraucht wird."""
    db = FakeDB(SUBJECTS + [SPORT])
    ergebnis = await match_groups(
        db,
        [key("SPW", ("7A",), gruppe="SPW_7_KA"), key("M", ("5C",))],
        pseudonym=LEHRKRAFT,
    )
    assert all("[" not in v.vorschlag_name for v in ergebnis.fehlend)


# ── Das Zuordnungsverfahren ──────────────────────────────────────────────────
#
# Direkt auf `zuordnen` statt über `match_groups`: Das Verfahren ist der heikle Teil, und
# ohne Fachauflösung und Bündelung davor liest sich nur, worum es geht.

CHEMIE = 5


def lerngruppe(klassen, art=REGULAER, fach=CHEMIE):
    return (fach, klassen, art)


def test_starke_kante_zuerst_dann_der_rest():
    """Der Produktionsfall: Ein Namenstreffer räumt den Weg für die Zuordnung ohne Namen.

    `CH 9D` findet Gruppe 49 über den Klassennamen. Damit sind beide Enden vergeben, und
    für `CH2_11` bleibt nur noch Gruppe 58 übrig — eindeutig von beiden Seiten.
    """
    kandidaten = [
        Kandidat(id=49, name="Chemie 9D", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=58, name="ch2-ks-abi28", subject_id=CHEMIE, quellklassen=()),
    ]
    treffer, rest = zuordnen(
        [lerngruppe(("9D",)), lerngruppe(("11",), LEISTUNGSKURS)], kandidaten
    )
    assert treffer == {0: 49, 1: 58}
    assert rest == {}


def test_alle_eindeutigen_paare_werden_zugeordnet():
    """Der Alltagsfall: drei Gruppen, drei Lerngruppen, jede über den Namen erkennbar.

    Der Wächter darüber, dass **alle** gleichzeitig eindeutigen Paare zugeordnet werden.
    Die innere Schleife bricht nach jedem Treffer ab — ohne die Wiederholung bliebe es bei
    einem Paar je Durchgang, und die dritte Gruppe fiele lautlos heraus.
    """
    kandidaten = [
        Kandidat(id=1, name="Chemie 9D", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=2, name="Chemie 9C", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=3, name="Chemie 8A", subject_id=CHEMIE, quellklassen=()),
    ]
    treffer, rest = zuordnen(
        [lerngruppe(("9D",)), lerngruppe(("9C",)), lerngruppe(("8A",))], kandidaten
    )
    assert treffer == {0: 1, 1: 2, 2: 3}
    assert rest == {}


def test_ohne_die_starke_kante_bliebe_alles_mehrdeutig():
    """Die Gegenprobe zur Reihenfolge: Erst der Namenstreffer macht den Rest eindeutig."""
    kandidaten = [
        Kandidat(id=49, name="Chemie A", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=58, name="Chemie B", subject_id=CHEMIE, quellklassen=()),
    ]
    treffer, rest = zuordnen(
        [lerngruppe(("9D",)), lerngruppe(("11",), LEISTUNGSKURS)], kandidaten
    )
    assert treffer == {}
    assert len(rest[0]) == 2 and len(rest[1]) == 2


def test_quellklasse_traegt_die_starke_kante():
    """Der Gruppenname muss die Klasse nicht nennen — die Quellklasse ist belastbarer.

    Sie ist ein Fremdschlüssel auf die Klassengruppe, kein Text, und entsteht bei der
    Adoption einer Klasse.
    """
    kandidaten = [
        Kandidat(id=7, name="Mein Chemiekurs", subject_id=CHEMIE, quellklassen=("9D",)),
        Kandidat(id=8, name="Chemie irgendwas", subject_id=CHEMIE, quellklassen=("8A",)),
    ]
    treffer, _ = zuordnen([lerngruppe(("9D",))], kandidaten)
    assert treffer == {0: 7}


def test_eine_gruppe_zwei_lerngruppen_bleibt_offen():
    """Der Fall, an dem „genau ein Kandidat" scheitern würde."""
    kandidaten = [Kandidat(id=7, name="Chemie", subject_id=CHEMIE, quellklassen=())]
    treffer, rest = zuordnen(
        [lerngruppe(("11",), BASISKURS), lerngruppe(("11",), LEISTUNGSKURS)], kandidaten
    )
    assert treffer == {}
    assert rest == {0: kandidaten, 1: kandidaten}


def test_eine_lerngruppe_zwei_gruppen_bleibt_offen():
    """Auch andersherum wird nicht geraten."""
    kandidaten = [
        Kandidat(id=7, name="Chemie eins", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=8, name="Chemie zwei", subject_id=CHEMIE, quellklassen=()),
    ]
    treffer, rest = zuordnen([lerngruppe(("11",), BASISKURS)], kandidaten)
    assert treffer == {}
    assert len(rest[0]) == 2


def test_kursart_im_namen_streicht_die_kante():
    """Ein Leistungskurs passt nicht auf eine Gruppe, die sich Basiskurs nennt."""
    kandidaten = [
        Kandidat(id=7, name="Chemie 11 Basiskurs", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=8, name="Chemie 11 Leistungskurs", subject_id=CHEMIE, quellklassen=()),
    ]
    treffer, _ = zuordnen(
        [lerngruppe(("11",), LEISTUNGSKURS), lerngruppe(("11",), BASISKURS)], kandidaten
    )
    assert treffer == {0: 8, 1: 7}


def test_fachkuerzel_bk_wird_nicht_als_basiskurs_gelesen():
    """`BK` heißt Bildende Kunst **und** Basiskurs.

    Eine BK-Gruppe namens „BK 11" las sich als Basiskurs. War sie in Wahrheit der
    Leistungskurs, strich `_widerspricht_kursart` ihre Kante — und der Kurs erschien als
    „Gruppe fehlt", obwohl sie danebenstand. Das Fachkürzel der Gruppe steht fest, also
    lässt sich die Doppeldeutigkeit auflösen statt erraten.
    """
    kandidaten = [
        Kandidat(id=7, name="BK 11", subject_id=CHEMIE, quellklassen=(), fach_code="BK")
    ]
    treffer, _ = zuordnen([lerngruppe(("11",), LEISTUNGSKURS)], kandidaten)
    assert treffer == {0: 7}


def test_kurzform_neben_einem_anderen_fach_zaehlt_weiter():
    """Die Gegenprobe: Bei „Bio BK 11" ist `bk` nicht das Fach, sondern der Basiskurs."""
    kandidaten = [
        Kandidat(id=7, name="Bio BK 11", subject_id=CHEMIE, quellklassen=(), fach_code="BIO")
    ]
    treffer, rest = zuordnen([lerngruppe(("11",), LEISTUNGSKURS)], kandidaten)
    assert treffer == {}
    assert rest == {0: []}


def test_marker_werden_an_wortgrenzen_gesucht():
    """Als Teilzeichenkette fand sich `lk` in „Volkskunde" und `bk` in „Werkbank"."""
    kandidaten = [
        Kandidat(id=7, name="Volkskunde 11", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=8, name="Werkbank 11", subject_id=CHEMIE, quellklassen=()),
    ]
    for art in (BASISKURS, LEISTUNGSKURS):
        _, rest = zuordnen([lerngruppe(("11",), art)], kandidaten)
        assert len(rest[0]) == 2, f"{art}: eine Kante wurde zu Unrecht gestrichen"


def test_anderes_fach_bildet_keine_kante():
    kandidaten = [Kandidat(id=7, name="Mathematik 9D", subject_id=99, quellklassen=("9D",))]
    treffer, rest = zuordnen([lerngruppe(("9D",))], kandidaten)
    assert treffer == {}
    assert rest == {0: []}


def test_kettenaufloesung_ueber_mehrere_runden():
    """Jede Zuordnung nimmt beide Enden heraus und kann die nächste erst eindeutig machen.

    A trifft über den Namen. Danach bleibt für B nur noch die mittlere Gruppe, und erst
    danach ist C eindeutig. Ohne Wiederholung bliebe nach der ersten Runde alles offen.
    """
    kandidaten = [
        Kandidat(id=1, name="Chemie 9D", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=2, name="Kurs mitte", subject_id=CHEMIE, quellklassen=()),
        Kandidat(id=3, name="Kurs rechts", subject_id=CHEMIE, quellklassen=()),
    ]
    # Zwei namenlose Lerngruppen — erst nachdem 9D vergeben ist, wird der Rest eng.
    treffer, rest = zuordnen(
        [lerngruppe(("9D",)), lerngruppe(("11",), BASISKURS), lerngruppe(("12",), BASISKURS)],
        kandidaten,
    )
    assert treffer[0] == 1
    # Die beiden übrigen bleiben untereinander mehrdeutig — das ist richtig so.
    assert sorted(rest) == [1, 2]
    assert all(len(r) == 2 for r in rest.values())
