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

        30 der 44 Knotentypen tragen laut `config/taxonomy.yaml` bewusst kein Embedding.
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
