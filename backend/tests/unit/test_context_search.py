"""Die Suchschicht (app/context/search.py) — Umschlag, Budgets, Abfrageform.

Geprüft wird hier, was ohne Datenbank prüfbar ist: die Zusagen des Ergebnisumschlags
und die Form der erzeugten Abfragen. Ob die Treffer stimmen, misst der Prüfsatz
(`scripts/search_eval.py`), ob die Rechte greifen, die Integrationstests.
"""

import sqlalchemy as sa
import pytest

from app.context.search import (
    Abschnitt,
    Suchergebnis,
    Suchprofil,
    _aus_dem_fach,
    identifikations_abfrage,
    praefix_abfrage,
)
from app.context.visibility import read_scope_clause


def _sql(ausdruck) -> str:
    return str(ausdruck.compile(compile_kwargs={"literal_binds": True}))


class TestUmschlag:
    """Vollständigkeit ist eine Angabe, keine Vermutung."""

    def test_leerer_umschlag_behauptet_nichts(self):
        """Der Vorgabewert darf nicht versehentlich „alles gefunden" bedeuten."""
        leer = Suchergebnis()
        assert leer.identifikation.treffer == []
        assert leer.identifikation.gesamt is None
        assert leer.identifikation.vollstaendig is False
        assert leer.aufzaehlung is None

    def test_geliefert_zaehlt_die_treffer(self):
        assert Abschnitt(treffer=[{"node_id": "a"}, {"node_id": "b"}]).geliefert == 2

    def test_thematisch_traegt_keine_gesamtzahl(self):
        """Zu „ähnlich genug" gibt es keine verteidigbare Grenze — also auch keine
        Gesamtmenge, die man zählen könnte (Bestandsaufnahme, widerlegte Schwellen)."""
        assert Abschnitt(treffer=[{"node_id": "a"}], gesamt=None).vollstaendig is False


class TestFachvorzug:
    """Der Bonus gilt dem Fach der Konversation — nicht dem Fehlen eines Fachs."""

    def test_ohne_fachbezug_kein_vergleich(self):
        """⚠️ Der Fehler, den dieser Test verhindert: ``subject_id == None`` wird in
        SQLAlchemy zu ``IS NULL``. Dann bekämen ausgerechnet die fachlosen Knoten
        (Leitperspektiven, prozessbezogene Gruppen) den Fachbonus. Im Prüfsatz kostete
        das zwei Fälle, in denen ein fachloser Knoten den richtigen Fachtreffer von
        Platz 1 verdrängte."""
        assert _aus_dem_fach(Suchprofil(pseudonym="p")) is None

    def test_mit_fachbezug_wird_verglichen(self):
        ausdruck = _aus_dem_fach(Suchprofil(pseudonym="p", subject_id=7))
        assert ausdruck is not None
        assert "IS NULL" not in _sql(ausdruck)
        assert "= 7" in _sql(ausdruck)

    def test_identifikation_ohne_fach_sortiert_nicht_nach_fachvorzug(self):
        sql = _sql(identifikations_abfrage("nennen", Suchprofil(pseudonym="p")))
        assert "subject_id IS NULL" not in sql


class TestIdentifikationsAbfrage:
    def test_ohne_embedding_filter(self):
        """Ein Titel wird verglichen, nicht eingebettet.

        30 der 45 Knotentypen tragen laut `app/context/taxonomy.yaml` bewusst kein Embedding.
        Bliebe der Filter hier stehen, wären Fachpläne, Curricula und Methoden unter
        ihrem **eigenen Namen** unauffindbar, während die Aufzählung sie zählt — und die
        Existenzaussage des Umschlags wäre gebrochen.
        """
        sql = _sql(identifikations_abfrage("nennen", Suchprofil(pseudonym="p")))
        assert "embedding IS NOT NULL" not in sql

    def test_zaehlt_vor_dem_limit(self):
        """Ohne `COUNT(*) OVER ()` wüsste niemand, ob die gelieferten Namensträger alle
        sind — und genau diese Auskunft trägt die Existenzaussage."""
        sql = _sql(identifikations_abfrage("nennen", Suchprofil(pseudonym="p")))
        assert "count(*) OVER" in sql
        assert "LIMIT" in sql

    def test_nutzt_den_normalisierten_titel(self):
        """Derselbe Ausdruck wie der Index aus Migration 0053 — sonst greift er nicht."""
        from app.context.lookup import titel_normalisiert_sql

        sql = _sql(identifikations_abfrage("nennen", Suchprofil(pseudonym="p")))
        assert titel_normalisiert_sql("context_nodes.title") in sql

    def test_budget_begrenzt_die_namenstraeger(self):
        sql = _sql(identifikations_abfrage("x", Suchprofil(pseudonym="p", identifikation=3)))
        assert "LIMIT 3" in sql


class TestAnkerProfil:
    """Der Anker-Weg ist seit AP5 eine Profilvariante, kein zweiter Suchweg."""

    def test_ohne_anker_kein_teilgraph_filter(self):
        """Der freie Chat sucht im ganzen Graphen — ein leerer Anker darf nicht
        versehentlich zu „nirgends" werden."""
        from app.context.search import Suchprofil, identifikations_abfrage

        sql = _sql(identifikations_abfrage(["x"], Suchprofil(pseudonym="p")))
        assert "abstammung" not in sql.lower()

    def test_mit_anker_wird_eingeschraenkt(self):
        from uuid import uuid4

        from app.context.search import Suchprofil, identifikations_abfrage

        anker = uuid4()
        sql = _sql(identifikations_abfrage(
            ["x"], Suchprofil(pseudonym="p", anchor_ids=(anker,))
        ))
        assert "RECURSIVE" in sql.upper()
        assert "context_edges" in sql
        # PostgreSQL erhält die UUID ohne Bindestriche — deshalb hier so verglichen.
        assert anker.hex in sql

    def test_teilgraph_folgt_beiden_wegen(self):
        """Abstammung über `part_of` **und** Verweise über `references`/`develops` —
        beide aus ADR-013. Fiele einer weg, verlöre ein Anker die Hälfte seines
        Gegenstands."""
        from uuid import uuid4

        from app.context.search import teilgraph

        sql = _sql(teilgraph([uuid4()]))
        assert "'part_of'" in sql
        assert "'references'" in sql and "'develops'" in sql

    def test_anker_erben_die_gemeinsame_sichtbarkeitsregel(self):
        """⚠️ **Bewusste Verhaltensänderung.** Der Ankerweg las bis 09/2026 nur
        `global`/`school` plus eigene private Knoten. Jetzt gilt dieselbe Regel wie
        überall — Anker-Assistenten sehen damit auch `subject`-Knoten und
        mitgliedschaftsgeprüfte `group`-Knoten in ihrem Teilgraphen."""
        from uuid import uuid4

        from app.context.search import Suchprofil, identifikations_abfrage

        sql = _sql(identifikations_abfrage(
            ["x"], Suchprofil(pseudonym="p", anchor_ids=(uuid4(),))
        ))
        assert "group_memberships" in sql
        assert "'subject'" in sql


class TestEditionen:
    """Fassungs-Bereinigung — seit AP5 für alle Profile, nicht nur für Anker."""

    def test_frontier_behaelt_unversionierte(self):
        """Ein Knoten ohne BP-Fassung ist keine Fassung von irgendetwas und bleibt."""
        from app.context.search import _filtere_auf_frontier

        treffer = [{"bp_version": None, "subject_id": 1, "title": "Notiz"}]
        assert _filtere_auf_frontier(treffer, {1: "2016.V3"}) == treffer

    def test_frontier_filtert_die_alte_fassung(self):
        from app.context.search import _filtere_auf_frontier

        alt = {"bp_version": "2016", "subject_id": 1}
        neu = {"bp_version": "2016.V3", "subject_id": 1}
        assert _filtere_auf_frontier([alt, neu], {1: "2016.V3"}) == [neu]

    def test_fach_ohne_bestimmbare_fassung_bleibt_ungefiltert(self):
        """Sonst bliebe von einem Fach, dessen Fassung sich nicht bestimmen lässt,
        gar nichts übrig."""
        from app.context.search import _filtere_auf_frontier

        treffer = [{"bp_version": "2016", "subject_id": 9}]
        assert _filtere_auf_frontier(treffer, {1: "2016.V3"}) == treffer

    def test_ueberhang_deckt_die_bereinigung(self):
        """Filter und Zusammenfassung entfernen Treffer **nach** der Abfrage. Ohne
        Überhang lieferte eine Suche mit Budget 10 am Ende womöglich vier."""
        from app.context.search import _KANDIDATEN_FAKTOR

        assert _KANDIDATEN_FAKTOR >= 2


class TestKandidaten:
    """Wonach die Identifikation sucht — und warum es zwei Formen braucht."""

    def test_reduzierter_begriff_und_rohanfrage(self):
        from app.context.search import _kandidaten

        assert _kandidaten("Was bedeutet der Operator nennen?") == [
            "nennen", "was bedeutet der operator nennen?",
        ]

    def test_kein_tor_mehr(self):
        """⚠️ Bis 09/2026 entschied die Wortliste, **ob** identifiziert wird. Sprach sie
        nicht an, fand gar keine Identifikation statt — eine verpasste Erkennung kostete
        Treffer. Jetzt bleibt die Rohanfrage als Kandidat, und sie kostet nur
        Reihenfolge (ADR-017, Befund 9)."""
        from app.context.lookup import nachschlage_begriff
        from app.context.search import _kandidaten

        frage = "Gedichte interpretieren und sprachliche Bilder deuten"
        assert _kandidaten(frage), "ohne Kandidaten liefe die Identifikation nie"
        assert nachschlage_begriff(frage) in _kandidaten(frage)

    def test_gleiche_formen_werden_nicht_doppelt_gesucht(self):
        from app.context.search import _kandidaten

        assert _kandidaten("Elektrochemie") == ["elektrochemie"]

    def test_leere_anfrage_ergibt_keine_kandidaten(self):
        from app.context.search import _kandidaten

        assert _kandidaten("   ") == []


class TestTeilsuche:
    """Die zweite Identifikationsstufe (Trigramm, Migration 0054)."""

    def test_schwelle_ist_gemessen_und_dokumentiert(self):
        """0,50 ist der Kipppunkt: alle vier S2-Fälle gefunden, kein thematischer Fall
        gestört. Ab 0,55 fällt der Leitfall durch (Messung 01.09.2026)."""
        from app.context.search import _TEILTREFFER_SCHWELLE

        assert _TEILTREFFER_SCHWELLE == 0.50

    def test_nutzt_den_trigramm_operator(self):
        from app.context.search import Suchprofil, teiltreffer_abfrage

        sql = _sql(teiltreffer_abfrage("anleitung nennen", Suchprofil(pseudonym="p"),
                                       ausschluss=set()))
        assert " %% " in sql or " % " in sql, sql
        assert "similarity(" in sql

    def test_eigenes_zuerst(self):
        """Der Eigentümer-Vorrang ist eine Sortierstufe, kein Filter: Fremde
        gleichnamige Bausteine verschwinden nicht, sie rücken nach."""
        from app.context.search import Suchprofil, teiltreffer_abfrage

        sql = _sql(teiltreffer_abfrage("x", Suchprofil(pseudonym="lehrer-7"),
                                       ausschluss=set()))
        ordnung = sql.split("ORDER BY", 1)[1]
        assert ordnung.index("owner_pseudonym = 'lehrer-7'") < ordnung.index("similarity")

    def test_exakte_stufe_sortiert_ebenso(self):
        from app.context.search import Suchprofil, identifikations_abfrage

        sql = _sql(identifikations_abfrage(["x"], Suchprofil(pseudonym="lehrer-7")))
        assert "owner_pseudonym = 'lehrer-7'" in sql.split("ORDER BY", 1)[1]

    def test_beide_kandidaten_im_exakten_abgleich(self):
        from app.context.search import Suchprofil, identifikations_abfrage

        sql = _sql(identifikations_abfrage(["nennen", "operator nennen"],
                                           Suchprofil(pseudonym="p")))
        assert "'nennen'" in sql and "'operator nennen'" in sql


class TestEigentuemerBonus:
    def test_bonus_ist_fliesskomma(self):
        """⚠️ Wird der Bonus als ganze Zahl typisiert, rundet PostgreSQL ihn auf 0 —
        die Abfrage läuft, sie tut nur nichts."""
        import sqlalchemy as sa

        from app.context.search import _EIGENTUEMER_BONUS, _bonus
        from app.db.models import ContextNode

        sql = _sql(_bonus(ContextNode.owner_pseudonym == "p", _EIGENTUEMER_BONUS))
        assert "AS FLOAT" in sql.upper() or "DOUBLE PRECISION" in sql.upper()
        assert str(_EIGENTUEMER_BONUS) in sql

    def test_groessenordnung_wie_der_fachbonus(self):
        from app.context.search import _EIGENTUEMER_BONUS, _FACHBONUS

        assert 0 < _EIGENTUEMER_BONUS <= _FACHBONUS


class TestAufzaehlung:
    """„Alle, die …" — Vollständigkeit ist der Anspruch, nicht Ähnlichkeit."""

    def _abschnitt(self, treffer, gesamt=None, budget=50):
        from app.context.search import Abschnitt, _gruppiere

        return Abschnitt(
            treffer=treffer[:budget],
            gesamt=gesamt if gesamt is not None else len(treffer),
            vollstaendig=len(treffer) <= budget,
            gruppen=_gruppiere(treffer, "fach"),
        )

    def test_gruppierung_zaehlt_alle_treffer(self):
        """Nicht nur die mitgelieferten: „In welchen Fächern gibt es das?" ist eine Frage
        nach dem Bestand, nicht nach dem Ausschnitt, der ins Budget passte."""
        from app.context.search import _gruppiere

        treffer = [{"fach": "Mathematik"}] * 3 + [{"fach": "Physik"}]
        gruppen = _gruppiere(treffer, "fach")
        assert [(g.name, g.anzahl) for g in gruppen] == [("Mathematik", 3), ("Physik", 1)]

    def test_gruppierung_nach_typ(self):
        from app.context.search import _gruppiere

        treffer = [{"content_type": "operator"}, {"content_type": "leitidee"}]
        assert {g.name for g in _gruppiere(treffer, "typ")} == {"operator", "leitidee"}

    def test_knoten_ohne_fach_verschwinden_nicht(self):
        """Leitperspektiven und schulweite Dokumente tragen kein Fach — sie dürfen aus
        der Zählung nicht herausfallen, sonst stimmt die Gesamtzahl nicht mehr."""
        from app.context.search import _gruppiere

        gruppen = _gruppiere([{"fach": None}, {"fach": "Mathematik"}], "fach")
        assert sum(g.anzahl for g in gruppen) == 2
        assert any(g.name == "ohne Angabe" for g in gruppen)

    def test_unbekannte_gruppierung_ist_kein_absturz(self):
        from app.context.search import _gruppiere

        assert _gruppiere([{"fach": "Mathematik"}], "sternzeichen") == []

    def test_gekuerzte_liste_ist_nicht_vollstaendig(self):
        a = self._abschnitt([{"fach": "M"} for _ in range(24)], budget=8)
        assert a.gesamt == 24 and a.geliefert == 8 and a.vollstaendig is False


class TestFassungen:
    """Dieselbe Kompetenz in zwei BP-Editionen ist **ein** Treffer, nicht zwei."""

    def test_gleiche_nummer_wird_zusammengefasst(self):
        from app.context.search import _treffer_schluessel, fasse_fassungen_zusammen

        alt = {"subject_id": 1, "content_type": "ik_kompetenz", "nr": "3.1.2(4)",
               "bp_version": "2016", "title": "alt"}
        neu = {**alt, "bp_version": "2016.V2", "title": "neu"}
        behalten = fasse_fassungen_zusammen([alt, neu], _treffer_schluessel)
        assert [t["title"] for t in behalten] == ["alt"]

    def test_ohne_nummer_wird_nie_zusammengefasst(self):
        """Operatoren tragen keine Kompetenznummer — „nennen" in Mathematik und „nennen"
        in Physik sind zwei Bausteine und müssen zwei bleiben."""
        from app.context.search import _treffer_schluessel, fasse_fassungen_zusammen

        a = {"subject_id": 1, "content_type": "operator", "nr": None,
             "bp_version": "2016", "title": "nennen"}
        b = {**a, "subject_id": 2}
        assert len(fasse_fassungen_zusammen([a, b], _treffer_schluessel)) == 2

    def test_unversionierte_knoten_bleiben_getrennt(self):
        """Zwei Nutzerknoten mit zufällig gleicher Nummer sind keine Fassungen
        voneinander."""
        from app.context.search import _treffer_schluessel, fasse_fassungen_zusammen

        a = {"subject_id": 1, "content_type": "aufgabe", "nr": "1", "bp_version": None}
        assert len(fasse_fassungen_zusammen([a, dict(a)], _treffer_schluessel)) == 2

    def test_gilt_fuer_alle_profile(self):
        """Seit AP5 gibt es nur noch **einen** Weg, auf dem Fassungen zusammenfallen.

        Bis dahin lag die Regel im Anker-Weg (`retrieval.py`); der freie Chat bekam
        Fassungs-Dubletten ungefiltert. `retrieval.py` hat davon nichts mehr — es trägt
        nur noch den Lernstand, und der ist Traversierung, keine Suche.
        """
        import app.context.retrieval as retrieval

        for name in ("get_semantic_context", "_fasse_fassungen_zusammen",
                     "_frontier_je_fach", "_fassungs_schluessel"):
            assert not hasattr(retrieval, name), (
                f"`{name}` lebt wieder in retrieval.py — damit gibt es zwei Wege."
            )


class TestAufzaehlungsWerkzeug:
    """`list_context_nodes` — die Aufzählung für das Modell."""

    async def _antwort(self, args, abschnitt, subject_id=None):
        from unittest.mock import AsyncMock, patch

        from app.chat import router

        with patch.object(router, "aufzaehlung", new=AsyncMock(return_value=abschnitt)) as gez, \
             patch.object(router, "_subject_id_aus_name",
                          new=AsyncMock(return_value=subject_id)):
            ctx = router.ToolContext(
                db=object(), user=type("U", (), {"sub": "p", "roles": []})(),
                group_id=None, conversation_id=None,
            )
            return await router._list_context_nodes_handler(args, ctx), gez

    async def test_ohne_fachangabe_ueber_alle_faecher(self):
        """⚠️ Der Musterfall lautet „in welchen Fächern gibt es ‚nennen'?". Ein stiller
        Fachfilter machte daraus die falsche Antwort — und zwar eine, die vollständig
        aussieht."""
        from app.context.search import Abschnitt

        _, gezaehlt = await self._antwort({"titel": "nennen"}, Abschnitt(gesamt=0))
        assert gezaehlt.await_args.args[0].subject_id is None

    async def test_titel_wird_normalisiert(self):
        """Gliederungsnummern und Großschreibung dürfen kein Hindernis sein."""
        from app.context.search import Abschnitt

        _, gezaehlt = await self._antwort(
            {"titel": "3.3.2 Leitidee Messen"}, Abschnitt(gesamt=0)
        )
        assert gezaehlt.await_args.args[0].titel == "leitidee messen"

    async def test_unbekanntes_fach_wird_benannt(self):
        antwort, _ = await self._antwort(
            {"titel": "nennen", "subject": "Klingonisch"}, None, subject_id=None
        )
        assert "Klingonisch" in antwort["hinweis"]

    async def test_zaehlung_und_gruppen_gehen_mit(self):
        from app.context.search import Abschnitt, Gruppe

        antwort, _ = await self._antwort(
            {"titel": "nennen", "gruppierung": "fach"},
            Abschnitt(
                treffer=[{"node_id": "a", "title": "nennen"}],
                gesamt=24, vollstaendig=False,
                gruppen=[Gruppe("Mathematik", 1), Gruppe("Physik", 1)],
            ),
        )
        assert antwort["gesamt"] == 24 and antwort["geliefert"] == 1
        assert antwort["gruppen"] == [
            {"name": "Mathematik", "anzahl": 1}, {"name": "Physik", "anzahl": 1}
        ]
        assert any("24" in h for h in antwort["hinweise"])

    async def test_vollstaendige_liste_ohne_hinweis(self):
        from app.context.search import Abschnitt

        antwort, _ = await self._antwort(
            {"titel": "nennen"},
            Abschnitt(treffer=[{"node_id": "a"}], gesamt=1, vollstaendig=True),
        )
        assert "hinweise" not in antwort

    def test_werkzeug_grenzt_sich_von_der_thematischen_suche_ab(self):
        """Die fragile Werkzeugwahl (Befund 8) wird über die Beschreibung gesteuert —
        das Modell muss lesen können, wann es welches nimmt."""
        from app.chat.router import _LIST_CONTEXT_NODES_TOOL

        text = _LIST_CONTEXT_NODES_TOOL["function"]["description"]
        assert "search_context_nodes" in text
        assert "gesamt" in text

    def test_registriert_in_der_gruppe_context_search(self):
        from app.chat import router  # noqa: F401 — registriert das Werkzeug
        from app.chat.tools import TOOL_REGISTRY

        werkzeug = TOOL_REGISTRY["list_context_nodes"]
        assert werkzeug.group == "context_search" and werkzeug.writes is False


class TestEineSichtbarkeitsregel:
    """Die Suche prüft Gruppenmitgliedschaft — bis 09/2026 tat sie das nicht.

    Eine gruppenweit freigegebene Aufgabe einer fremden Lerngruppe erschien in den
    Suchtreffern und ging über das Chat-Werkzeug mitsamt Inhalt ans Modell (Audit #1 war
    nur im Kontext-Router behoben worden).
    """

    def test_suche_nutzt_die_gemeinsame_regel(self):
        sql = _sql(identifikations_abfrage("x", Suchprofil(pseudonym="p")))
        assert "group_memberships" in sql, (
            "Die Suche prüft die Gruppenmitgliedschaft nicht — fremde group-Knoten "
            "wären wieder sichtbar."
        )

    def test_ohne_admin_nur_eigene_gruppen(self):
        sql = _sql(read_scope_clause("p", ["student"]))
        assert "group_memberships" in sql
        assert "'private'" not in sql

    def test_admin_sieht_alle_gruppen_aber_keine_fremden_privaten(self):
        sql = _sql(read_scope_clause("p", ["admin"]))
        assert "group_memberships" not in sql
        assert "'private'" not in sql
        assert "owner_pseudonym = 'p'" in sql

    @pytest.mark.parametrize("rollen", [(), ("student",), ("teacher",), ("admin",)])
    def test_private_nie_ueber_den_scope(self, rollen):
        """`private` ist ausschließlich über die Eigentümerschaft erreichbar — auch für
        Admins. Stünde es in der Scope-Liste, läse jede Rolle fremde private Knoten."""
        assert "'private'" not in _sql(read_scope_clause("p", rollen))


class TestZusammensetzung:
    """Was `suche()` aus den beiden Verfahren macht."""

    async def _suche(self, frage, ident, thema):
        from unittest.mock import AsyncMock, patch

        from app.context import search

        with patch.object(search, "identifikation", new=AsyncMock(return_value=ident)), \
             patch.object(search, "thematisch", new=AsyncMock(return_value=thema)) as t:
            ergebnis = await search.suche(frage, Suchprofil(pseudonym="p"), object())
        return ergebnis, t

    async def test_kein_knoten_zweimal_im_umschlag(self):
        """Namensträger werden aus der thematischen Auswahl ausgeschlossen."""
        ident = Abschnitt(treffer=[{"node_id": "a"}], gesamt=1, vollstaendig=True)
        _, thematisch = await self._suche("nennen", ident, Abschnitt())
        assert thematisch.await_args.kwargs["ausschluss"] == {"a"}

    async def test_ohne_erkannten_namen_ist_der_leere_abschnitt_bedeutungslos(self):
        """Nennt die Anfrage gar keinen Namen, sagt der leere Abschnitt nichts aus."""
        ergebnis, _ = await self._suche(
            "die",  # bleibt nach der Wortlisten-Reduktion nichts übrig
            Abschnitt(gesamt=0, vollstaendig=True),
            Abschnitt(treffer=[{"node_id": "x"}]),
        )
        assert any("keine Aussage" in h for h in ergebnis.hinweise)

    async def test_erkannter_name_ohne_treffer_ist_eine_auskunft(self):
        """Der andere Fall: Ein Name wurde erkannt, aber es gibt ihn nicht.

        Das ist eine belastbare Auskunft — über den **Namen**, nicht über das Thema.
        Der Hinweis muss beides sagen, sonst wird aus „heißt so nicht" ein „gibt es
        nicht" (Leitplanke 4)."""
        ergebnis, _ = await self._suche(
            "Zwirbeln",
            Abschnitt(gesamt=0, vollstaendig=True),
            Abschnitt(treffer=[{"node_id": "x"}]),
        )
        [hinweis] = ergebnis.hinweise
        assert "Zwirbeln" in hinweis.lower() or "zwirbeln" in hinweis
        assert "sagt das" in hinweis

    async def test_gekuerzte_identifikation_nennt_die_gesamtzahl(self):
        """Nie stumm kürzen: Wenn nicht alle Namensträger passen, steht die Zahl dabei —
        der Musterfall aus Befund 1 („nennen" gibt es in 18 Fächern)."""
        ident = Abschnitt(
            treffer=[{"node_id": str(i), "treffer_art": "exakt"} for i in range(8)],
            gesamt=24, vollstaendig=False,
        )
        ergebnis, _ = await self._suche("nennen", ident, Abschnitt())
        assert any("24" in h and "8" in h for h in ergebnis.hinweise)

    async def test_teiltreffer_zaehlen_nicht_als_namenstraeger(self):
        """⚠️ Die Zahl im Hinweis meint die **exakten** Namensträger.

        Zählte sie die ähnlich benannten mit, stünde dort eine Zahl, die keine Frage
        beantwortet — und die Existenzaussage hinge wieder an einer Ähnlichkeit.
        """
        ident = Abschnitt(
            treffer=[
                {"node_id": "a", "treffer_art": "exakt"},
                {"node_id": "b", "treffer_art": "teilweise"},
                {"node_id": "c", "treffer_art": "teilweise"},
            ],
            gesamt=24, vollstaendig=False,
        )
        ergebnis, _ = await self._suche("nennen", ident, Abschnitt())
        [hinweis] = ergebnis.hinweise
        assert "24 Bausteine tragen diesen Namen, 1 davon" in hinweis

    async def test_aehnlich_benannte_belegen_keinen_namen(self):
        """Ohne exakten Treffer bleibt es dabei: Der Name existiert nicht — die
        ähnlich benannten sind ein Angebot zum Nachsehen, kein Beleg."""
        ident = Abschnitt(
            treffer=[{"node_id": "a", "treffer_art": "teilweise"}],
            gesamt=0, vollstaendig=True,
        )
        ergebnis, _ = await self._suche("Zwirbeln", ident, Abschnitt())
        [hinweis] = ergebnis.hinweise
        assert "Kein Baustein heißt genau" in hinweis
        assert "1 ähnlich benannte" in hinweis

    async def test_vollstaendige_identifikation_ohne_hinweis(self):
        ident = Abschnitt(treffer=[{"node_id": "a"}], gesamt=1, vollstaendig=True)
        ergebnis, _ = await self._suche("nennen", ident, Abschnitt())
        assert ergebnis.hinweise == []


class TestWerkzeugantwort:
    """Was das Modell sieht — beschriftete Abschnitte statt einer flachen Liste.

    Ohne die Beschriftung konnte ein Modell nicht unterscheiden, ob ein Treffer der
    gesuchte Baustein **ist** oder ihm nur ähnelt; entsprechend gab es Antworten wie
    „dazu gibt es nichts" auf eine Liste thematischer Nachbarn hin.
    """

    async def _antwort(self, ergebnis):
        from unittest.mock import AsyncMock, patch

        from app.chat import router

        with patch.object(router, "suche", new=AsyncMock(return_value=ergebnis)), \
             patch.object(router, "_resolve_conversation_subject_id",
                          new=AsyncMock(return_value=None)):
            ctx = router.ToolContext(
                db=object(), user=type("U", (), {"sub": "p", "roles": []})(),
                group_id=None, conversation_id=None,
            )
            return await router._search_context_nodes_handler({"query": "nennen"}, ctx)

    async def test_abschnitte_sind_benannt_und_getrennt(self):
        antwort = await self._antwort(Suchergebnis(
            identifikation=Abschnitt(
                treffer=[{"node_id": "a", "title": "nennen", "content": "…"}],
                gesamt=24, vollstaendig=False,
            ),
            thematisch=Abschnitt(treffer=[{"node_id": "b", "title": "beschreiben"}]),
        ))
        assert [t["title"] for t in antwort["exakte_namenstraeger"]] == ["nennen"]
        assert [t["title"] for t in antwort["naechstliegende_bausteine"]] == ["beschreiben"]

    async def test_vollstaendigkeit_geht_mit(self):
        """Das Modell soll die Gesamtzahl nennen können, statt acht Treffer als
        vollständige Liste auszugeben."""
        antwort = await self._antwort(Suchergebnis(
            identifikation=Abschnitt(treffer=[], gesamt=24, vollstaendig=False),
        ))
        assert antwort["gesamt"] == 24 and antwort["vollstaendig"] is False

    async def test_node_id_bleibt_draussen(self):
        """Sie nützt dem Modell nichts (kein Werkzeug nimmt sie entgegen) und taucht
        sonst in Antworten auf."""
        antwort = await self._antwort(Suchergebnis(
            identifikation=Abschnitt(treffer=[{"node_id": "a", "title": "nennen"}]),
        ))
        assert "node_id" not in antwort["exakte_namenstraeger"][0]

    async def test_werkzeugbeschreibung_verbietet_die_existenzaussage(self):
        """Leitplanke 4: Aus thematischer Nähe folgt keine Aussage über Vorhandensein."""
        from app.chat.router import _SEARCH_CONTEXT_NODES_TOOL

        text = _SEARCH_CONTEXT_NODES_TOOL["function"]["description"]
        assert "exakte_namenstraeger" in text and "naechstliegende_bausteine" in text
        assert "NIE vollständig" in text


class TestKontextRouterTeiltDieRegel:
    def test_router_delegiert(self):
        """Zwei Kopien einer Rechteprüfung driften auseinander; die eine wird gepflegt,
        die andere vergessen. Deshalb muss der Router dieselbe Funktion benutzen."""
        from app.context.router import _read_scope_clause

        nutzer = type("U", (), {"sub": "p", "roles": ["student"]})()
        assert _sql(_read_scope_clause(nutzer)) == _sql(read_scope_clause("p", ["student"]))


class TestRollenGewichtung:
    """AP6: Dieselbe Anfrage, je nach Rolle andere Reihenfolge — nie andere Rechte."""

    def _sortierung_sql(self, rollen):
        """Der Sortierausdruck der thematischen Suche, ohne Datenbank."""
        from app.context.search import Suchprofil, _typ_bonus

        ausdruck = _typ_bonus(Suchprofil(pseudonym="p", rollen=rollen))
        return _sql(ausdruck) if ausdruck is not None else ""

    def test_bildungsplan_typen_bleiben_neutral(self):
        """Das Abnahmekriterium der Tabelle: Auf reinem BP-Bestand ändert sie nichts,
        und deshalb bewegt sich der Prüfsatz nicht."""
        from app.context.taxonomy import ROLLEN_TYP_BONUS

        bp_typen = {
            "ik_kompetenz", "pk_kompetenz", "pk_gruppe", "leitidee",
            "leitperspektive_aspekt", "kapitel", "operator", "themengebiet",
            "lfdb_themenblock", "lfdb_kompetenz",
        }
        for rolle, tabelle in ROLLEN_TYP_BONUS.items():
            assert not (set(tabelle) & bp_typen), f"{rolle} gewichtet BP-Typen"

    def test_nur_eingebettete_typen_werden_gewichtet(self):
        """Ein Bonus auf einen Typ ohne Embedding tut nichts — er könnte in der
        thematischen Auswahl gar nicht auftauchen. Genau daran wäre AP6 vor der
        Embedding-Entscheidung gescheitert."""
        from app.context.taxonomy import EMBEDDING_CONTENT_TYPES, ROLLEN_TYP_BONUS

        gewichtet = set().union(*(set(t) for t in ROLLEN_TYP_BONUS.values()))
        assert gewichtet <= set(EMBEDDING_CONTENT_TYPES)

    def test_werte_bleiben_klein(self):
        """Sie sollen innerhalb dessen sortieren, was ohnehin zur Auswahl stand —
        nicht Fernes heranholen. Obergrenze ist der gemessene Fachbonus."""
        from app.context.search import _FACHBONUS
        from app.context.taxonomy import ROLLEN_TYP_BONUS

        for tabelle in ROLLEN_TYP_BONUS.values():
            for typ, wert in tabelle.items():
                assert 0 < wert <= _FACHBONUS, f"{typ}: {wert}"

    def test_admin_zaehlt_als_lehrkraft(self):
        """`admin` ist eine Erweiterung der Lehrkraft-Rolle, kein eigener Nutzertyp
        (CLAUDE.md)."""
        from app.context.taxonomy import ROLLEN_TYP_BONUS, rollen_typ_bonus

        assert rollen_typ_bonus(["admin"]) is ROLLEN_TYP_BONUS["teacher"]
        assert rollen_typ_bonus(["teacher", "admin"]) is ROLLEN_TYP_BONUS["teacher"]

    def test_lehrkraft_schlaegt_schueler_bei_doppelrolle(self):
        from app.context.taxonomy import ROLLEN_TYP_BONUS, rollen_typ_bonus

        assert rollen_typ_bonus(["student", "teacher"]) is ROLLEN_TYP_BONUS["teacher"]

    def test_ohne_rolle_keine_gewichtung(self):
        """Cron-Jobs und der Prüfsatz suchen ohne Rolle — dann gilt allein die
        Ähnlichkeit."""
        assert self._sortierung_sql([]) == ""

    def test_rollen_unterscheiden_sich(self):
        schueler, lehrkraft = self._sortierung_sql(["student"]), self._sortierung_sql(["teacher"])
        assert schueler and lehrkraft and schueler != lehrkraft
        assert "klausur" in lehrkraft and "klausur" not in schueler
        assert "methodenblatt" in schueler and "methodenblatt" not in lehrkraft

    def test_bonus_ist_fliesskomma(self):
        """⚠️ Als ganze Zahl typisiert rundet PostgreSQL den Bonus auf 0 — die Abfrage
        läuft, sie tut nur nichts."""
        sql = self._sortierung_sql(["teacher"]).upper()
        assert "AS FLOAT" in sql or "DOUBLE PRECISION" in sql

    def test_gewichtung_ist_kein_filter(self):
        """Eine Klausur verschwindet für Schüler:innen nicht durch diese Tabelle —
        dafür sorgt der Sichtbarkeits-Scope. Wer beides verwechselt, baut den
        Rechteschutz an die falsche Stelle."""
        sql = self._sortierung_sql(["student"])
        assert "WHERE" not in sql.upper()


class TestZeitraumAufzaehlung:
    """„Was haben wir letzte Woche gemacht?" — eine Aufzählungs-, keine Ähnlichkeitsfrage."""

    def test_grenzen_letzte_woche(self):
        from datetime import date

        from app.chat.router import _zeitraum_grenzen

        # Mittwoch, 02.09.2026
        assert _zeitraum_grenzen("letzte_woche", date(2026, 9, 2)) == (
            date(2026, 8, 24), date(2026, 8, 30)
        )

    def test_grenzen_diese_woche_am_montag(self):
        from datetime import date

        from app.chat.router import _zeitraum_grenzen

        assert _zeitraum_grenzen("diese_woche", date(2026, 8, 31)) == (
            date(2026, 8, 31), date(2026, 9, 6)
        )

    def test_monatsgrenzen_ueber_den_jahreswechsel(self):
        from datetime import date

        from app.chat.router import _zeitraum_grenzen

        assert _zeitraum_grenzen("letzter_monat", date(2027, 1, 15)) == (
            date(2026, 12, 1), date(2026, 12, 31)
        )

    def test_unbekannter_zeitraum(self):
        from datetime import date

        from app.chat.router import _zeitraum_grenzen

        assert _zeitraum_grenzen("neulich", date(2026, 9, 2)) is None

    def test_filter_geht_ueber_den_stundenplan(self):
        """Der Termin eines Bausteins steht in `lesson_slots`, nirgends sonst — und dort
        an **beiden** Spalten: Einheit und Stundenentwurf."""
        from datetime import date

        import sqlalchemy as sa

        from app.context.filters import Knotenfilter, wende_an
        from app.db.models import ContextNode

        sql = _sql(wende_an(sa.select(ContextNode.id), Knotenfilter(
            unterrichtet_ab=date(2026, 8, 24), unterrichtet_bis=date(2026, 8, 30),
            unterrichtet_in_gruppe=7,
        )))
        assert "lesson_slots" in sql
        assert "ue_node_id" in sql and "stunde_node_id" in sql
        assert "group_id = 7" in sql

    def test_ohne_zeitangaben_kein_stundenplan_join(self):
        """Der Normalfall darf nicht teurer werden, nur weil es den Filter gibt."""
        import sqlalchemy as sa

        from app.context.filters import Knotenfilter, wende_an
        from app.db.models import ContextNode

        sql = _sql(wende_an(sa.select(ContextNode.id), Knotenfilter(titel="nennen")))
        assert "lesson_slots" not in sql

    async def test_zeitraum_ohne_gruppe_wird_abgelehnt(self):
        """Ohne Unterrichtsgruppe gibt es keinen Stundenplan, auf den sich ein Zeitraum
        beziehen könnte. Ein stillschweigend ignorierter Filter lieferte eine Antwort
        über **fremden** Unterricht, die vollständig aussieht."""
        from unittest.mock import AsyncMock, patch

        from app.chat import router

        with patch.object(router, "aufzaehlung", new=AsyncMock()) as gezaehlt:
            ctx = router.ToolContext(
                db=object(), user=type("U", (), {"sub": "p", "roles": []})(),
                group_id=None, conversation_id=None,
            )
            antwort = await router._list_context_nodes_handler(
                {"zeitraum": "letzte_woche"}, ctx
            )
        assert "Unterrichtsgruppe" in antwort["hinweis"]
        gezaehlt.assert_not_awaited()


class TestUeberlappterNetzaufruf:
    """Das Embedding läuft, während die Identifikation die Datenbank befragt."""

    async def test_embedding_startet_vor_der_identifikation(self):
        """Gemessen: Embedding ~370 ms, Identifikation ~50 ms. Nacheinander sind das
        420 ms, überlappt 370. Die Reihenfolge ist deshalb kein Zufall."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from app.context import search

        reihenfolge = []

        async def embedding(text):
            reihenfolge.append("embedding-start")
            return [0.1]

        async def ident(frage, profil, db):
            # Eine echte Identifikation fragt die Datenbank und gibt dabei die
            # Kontrolle ab — erst dann kommt der angestoßene Netzaufruf zum Zug.
            # `create_task` startet nicht sofort, sondern am nächsten Await-Punkt.
            await asyncio.sleep(0)
            reihenfolge.append("identifikation")
            return search.Abschnitt()

        with patch.object(search, "generate_embedding", new=embedding), \
             patch.object(search, "identifikation", new=ident), \
             patch.object(search, "thematisch",
                          new=AsyncMock(return_value=search.Abschnitt())):
            await search.suche("x", search.Suchprofil(pseudonym="p"), object())

        assert reihenfolge[0] == "embedding-start"

    async def test_vektor_wird_durchgereicht_statt_zweimal_geholt(self):
        """Sonst liefe der teure Netzaufruf zweimal — und die Ersparnis wäre dahin."""
        from unittest.mock import AsyncMock, patch

        from app.context import search

        embedding = AsyncMock(return_value=[0.1])
        with patch.object(search, "generate_embedding", new=embedding), \
             patch.object(search, "identifikation",
                          new=AsyncMock(return_value=search.Abschnitt())), \
             patch.object(search, "thematisch",
                          new=AsyncMock(return_value=search.Abschnitt())) as thema:
            await search.suche("x", search.Suchprofil(pseudonym="p"), object())

        assert embedding.await_count == 1
        assert thema.await_args.kwargs["vektor"] == [0.1]

    async def test_gescheitertes_embedding_wird_zu_none(self):
        """Der ILIKE-Rückfall hängt daran: `None` heißt „es gibt keinen Vektor“ —
        eine durchgereichte Ausnahme würde die ganze Suche abbrechen."""
        from unittest.mock import AsyncMock, patch

        from app.context import search

        with patch.object(search, "generate_embedding",
                          new=AsyncMock(side_effect=RuntimeError("Dienst weg"))):
            assert await search.vektor_oder_none("x") is None

    async def test_datenbankabfragen_bleiben_nacheinander(self):
        """⚠️ Eine `AsyncSession` verträgt keine nebenläufigen Abfragen
        (`IllegalStateChangeError`). Überlappt wird der Netzaufruf, nie die Datenbank —
        deshalb darf hier kein `gather` über zwei DB-Aufrufe stehen.
        """
        from pathlib import Path

        from app.context import search, service

        for modul in (search, service):
            quelle = Path(modul.__file__).read_text(encoding="utf-8")
            assert "asyncio.gather(" not in quelle, (
                f"{modul.__name__} lässt Aufrufe nebenläufig laufen — auf einer "
                f"gemeinsamen Session endet das in IllegalStateChangeError."
            )


class TestNurIdentifikation:
    """Der Namensnachschlag des `@`-Dropdowns läuft ohne thematische Auswahl.

    Nicht als Sparmaßnahme am Rand: Die thematische Auswahl kostet einen Netzaufruf zum
    Embedding-Modell (rund 370 ms, gemessen 01.09.2026, über den Master-Key also aufs
    Systembudget). Das Dropdown fragt bei **jedem Tastendruck** neu und zeigt von den
    thematischen Treffern keinen einzigen — sie wären weder gewollt noch sichtbar, nur
    bezahlt.
    """

    async def _suche(self, **kwargs):
        from unittest.mock import AsyncMock, patch

        from app.context import search as modul

        with patch.object(modul, "identifikation",
                          new=AsyncMock(return_value=Abschnitt(gesamt=0, vollstaendig=True))), \
             patch.object(modul, "thematisch",
                          new=AsyncMock(return_value=Abschnitt())) as thema, \
             patch.object(modul, "vektor_oder_none", new=AsyncMock()) as vektor:
            ergebnis = await modul.suche(
                "nennen", Suchprofil(pseudonym="p"), object(), **kwargs
            )
        return ergebnis, thema, vektor

    async def test_kein_embedding_aufruf(self):
        _, _, vektor = await self._suche(nur_identifikation=True)
        vektor.assert_not_awaited()

    async def test_keine_thematische_auswahl(self):
        ergebnis, thema, _ = await self._suche(nur_identifikation=True)
        thema.assert_not_awaited()
        assert ergebnis.thematisch.treffer == []
        # Und der leere Abschnitt behauptet nichts (vgl. TestUmschlag).
        assert ergebnis.thematisch.vollstaendig is False

    async def test_der_normalfall_bleibt_beides(self):
        """Der Schalter ist eine Ausnahme für einen Aufrufer, keine neue Vorgabe."""
        _, thema, vektor = await self._suche()
        thema.assert_awaited()
        vektor.assert_awaited()


class TestPraefixStufe:
    """Die Namensvervollständigung des `@`-Shortcodes (AP9).

    ⚠️ **Warum es sie überhaupt gibt.** Die Trigramm-Ähnlichkeit ist längennormiert:
    „Satz" gegen „Satz des Pythagoras" liegt bei rund 0,25 und damit unter der Schwelle
    von 0,50. Ohne diese Stufe sähe man beim Tippen eines bekannten Titels bis zum
    letzten Wort nichts — gemessen am 01.09.2026, und genau das ist der Fall, für den
    der `@`-Shortcode da ist.
    """

    def test_sucht_den_titelanfang(self):
        sql = _sql(praefix_abfrage("satz", Suchprofil(pseudonym="p"), ausschluss=set()))
        assert "LIKE 'satz%'" in sql

    def test_kuerzeste_titel_zuerst(self):
        """Bei „Satz" steht „Satz des Pythagoras" vor einem Kompetenztext, der genauso
        anfängt und drei Zeilen weitergeht — für eine Vervollständigung ist der kürzeste
        passende Titel der wahrscheinlich gemeinte."""
        sql = _sql(praefix_abfrage("satz", Suchprofil(pseudonym="p"), ausschluss=set()))
        assert "length" in sql.lower()

    def test_bereits_gefundene_bleiben_draussen(self):
        """Sonst stünde ein exakter Namensträger gleich noch einmal als Präfixtreffer da.

        Verglichen wird die **bindestrichlose** Form: SQLAlchemy rendert UUIDs als
        Hex-Kette (`dabf4812353e…`), nicht in der Schreibweise mit Bindestrichen.
        """
        from uuid import uuid4

        schon = uuid4()
        sql = _sql(praefix_abfrage(
            "satz", Suchprofil(pseudonym="p"), ausschluss={str(schon)}
        ))
        assert "NOT IN" in sql.upper()
        assert schon.hex in sql

    async def test_nur_der_shortcode_bekommt_die_stufe(self):
        """Alle anderen Aufrufer bleiben ohne — sonst wäre der Prüfsatz nicht mehr
        vergleichbar."""
        from unittest.mock import AsyncMock, patch

        from app.context import search as modul

        async def ruf(**kwargs):
            with patch.object(modul, "identifikation",
                              new=AsyncMock(return_value=Abschnitt(gesamt=0, vollstaendig=True))) as ident, \
                 patch.object(modul, "thematisch",
                              new=AsyncMock(return_value=Abschnitt())), \
                 patch.object(modul, "vektor_oder_none", new=AsyncMock()):
                await modul.suche("satz", Suchprofil(pseudonym="p"), object(), **kwargs)
            return ident.await_args.kwargs.get("praefix", False)

        assert await ruf(nur_identifikation=True) is True
        assert await ruf() is False
