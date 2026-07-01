"""Unit-Tests fuer scripts/scraper/parsers.py — gegen statische HTML-Fixtures."""

import re

import pytest
from scripts.scraper.parsers import (
    ScraperParseError,
    extract_grades_from_bp_id,
    extract_niveau_from_bp_id,
    extract_bp_version,
    parse_fachplan,
    parse_leitidee,
    parse_ik_kompetenz_list,
    parse_pk_gruppe,
    parse_pk_kompetenz_list,
    parse_leitperspektive,
    parse_leitperspektive_aspekt_list,
    parse_operator_list,
    expand_operator_title,
)

from scripts.tests.conftest import load_fixture


CHEMIE_IK_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_8-9-10_01"
OPERATOREN_CH_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH.V2_OP"
CHEMIE_IK_STANDARD_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_8-9-10_01_01"
CHEMIE_IK_HINWEIS_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_5-6_01"
CHEMIE_PK_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_PK_01"
LP_BNE_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_LP_BNE"
LP_PG_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_LP_PG"
LP_LFDB_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_LP_LFDB"


class TestParseLeitidee:
    def test_returns_leitidee_node(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert node['content_type'] == 'leitidee'
        assert node['type'] == 'knowledge'
        assert node['bp_id'].startswith('BP2016BW_ALLG_GYM_CH_IK')
        assert node['title']
        assert isinstance(node['content'], str)  # leer ist ok bei reiner Navigationsseite

    def test_no_soft_hyphens_in_title(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert '\u00ad' not in node['title']
        assert '\u00ad' not in node['content']

    def test_breadcrumb_is_list(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert isinstance(node['metadata']['breadcrumb'], list)
        assert len(node['metadata']['breadcrumb']) >= 1

    def test_content_hash_present(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert node['content_hash'].startswith('sha256:')

    def test_visibility_global(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert node['visibility'] == 'global'


class TestParseIkKompetenzList:
    # Standard-Seite mit tktable (IK_8-9-10_01_01), nicht die Leitidee-Navigationsseite
    PARENT = "BP2016BW_ALLG_GYM_CH_IK_8-9-10_01_01"

    def test_returns_multiple_nodes(self):
        soup = load_fixture('chemie_ik_standard.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_STANDARD_URL, self.PARENT)
        assert len(nodes) >= 1

    def test_nodes_have_ik_kompetenz_type(self):
        soup = load_fixture('chemie_ik_standard.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_STANDARD_URL, self.PARENT)
        for node in nodes:
            assert node['content_type'] == 'ik_kompetenz'
            assert node['parent_bp_id'] == self.PARENT

    def test_no_soft_hyphens(self):
        soup = load_fixture('chemie_ik_standard.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_STANDARD_URL, self.PARENT)
        for node in nodes:
            assert '\u00ad' not in node['content']
            assert '\u00ad' not in node['title']

    def test_relations_have_valid_types(self):
        soup = load_fixture('chemie_ik_standard.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_STANDARD_URL, self.PARENT)
        valid_types = {'develops', 'related_to', 'references'}
        for node in nodes:
            for rel in node['relations']:
                assert rel['type'] in valid_types
                assert rel['target_bp_id']

    def test_bp_ids_are_unique(self):
        soup = load_fixture('chemie_ik_standard.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_STANDARD_URL, self.PARENT)
        bp_ids = [n['bp_id'] for n in nodes]
        assert len(bp_ids) == len(set(bp_ids))

    def test_leitidee_nav_page_returns_empty_list(self):
        # Leitidee-Navigationsseite hat kein tktable -> leere Liste, kein Fehler
        soup = load_fixture('chemie_leitidee.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_URL, "BP2016BW_ALLG_GYM_CH_IK_8-9-10_01")
        assert nodes == []


class TestParsePkGruppe:
    def test_returns_pk_gruppe_node(self):
        soup = load_fixture('chemie_pk_gruppe.html')
        node = parse_pk_gruppe(soup, CHEMIE_PK_URL)
        assert node['content_type'] == 'pk_gruppe'
        assert node['bp_id'].startswith('BP2016BW_ALLG_GYM_CH_PK')
        assert node['title']


class TestParsePkKompetenzList:
    def test_returns_pk_kompetenzen(self):
        soup = load_fixture('chemie_pk_gruppe.html')
        parent = "BP2016BW_ALLG_GYM_CH_PK_01"
        nodes = parse_pk_kompetenz_list(soup, CHEMIE_PK_URL, parent)
        assert len(nodes) >= 1

    def test_nodes_have_pk_kompetenz_type(self):
        soup = load_fixture('chemie_pk_gruppe.html')
        nodes = parse_pk_kompetenz_list(soup, CHEMIE_PK_URL, "BP2016BW_ALLG_GYM_CH_PK_01")
        for node in nodes:
            assert node['content_type'] == 'pk_kompetenz'


class TestParseLeitperspektive:
    def test_returns_lp_node(self):
        soup = load_fixture('leitperspektive_bne.html')
        node = parse_leitperspektive(soup, LP_BNE_URL, 'BNE')
        assert node['content_type'] == 'leitperspektive'
        assert node['bp_id'] == 'BP2016BW_ALLG_LP_BNE'
        assert node['metadata']['kuerzel'] == 'BNE'

    def test_aspekt_list_not_empty(self):
        soup = load_fixture('leitperspektive_bne.html')
        nodes = parse_leitperspektive_aspekt_list(soup, LP_BNE_URL, 'BNE')
        assert len(nodes) >= 1

    def test_aspekt_bp_ids_match_pattern(self):
        soup = load_fixture('leitperspektive_bne.html')
        nodes = parse_leitperspektive_aspekt_list(soup, LP_BNE_URL, 'BNE')
        for node in nodes:
            assert re.match(r'^BNE_\d{2}$', node['bp_id']), f"Ungueltige bp_id: {node['bp_id']}"
            assert node['parent_bp_id'] == 'BP2016BW_ALLG_LP_BNE'

    def test_pg_uses_konkretisierung_list_not_first_list(self):
        # PG hat vor der Konkretisierungsliste eine andere Liste
        # („Zentrale Lern- und Handlungsfelder", 5 Items). Der Parser muss
        # die Liste nach dem Anker-Satz „… durch folgende Begriffe
        # konkretisiert:" wählen (8 Aspekte), nicht die erste Liste.
        soup = load_fixture('leitperspektive_pg.html')
        nodes = parse_leitperspektive_aspekt_list(soup, LP_PG_URL, 'PG')
        assert len(nodes) == 8, f"PG sollte 8 Aspekte haben, hat {len(nodes)}"
        titles = [n['title'] for n in nodes]
        assert titles[0] == 'Wahrnehmung und Empfindung'
        assert 'Sucht und Abhängigkeit' in titles
        assert 'Sicherheit und Unfallschutz' in titles

    def test_lfdb_has_import_hinweis_and_no_aspekte(self):
        # LFDB hat auf der BP-Seite keine Aspekt-Liste; die Inhalte stecken in
        # einer PDF. Der Knoten muss einen Import-Hinweis tragen.
        soup = load_fixture('leitperspektive_lfdb.html')
        node = parse_leitperspektive(soup, LP_LFDB_URL, 'LFDB')
        assert node['metadata']['kuerzel'] == 'LFDB'
        assert 'import_hinweis' in node['metadata']
        assert 'PDF' in node['metadata']['import_hinweis']
        assert 'Hinweis' in node['content']
        # Keine Aspekte (kein Anker-Satz, keine passende Liste)
        aspekte = parse_leitperspektive_aspekt_list(soup, LP_LFDB_URL, 'LFDB')
        assert aspekte == []

    def test_non_lfdb_has_no_import_hinweis(self):
        soup = load_fixture('leitperspektive_bne.html')
        node = parse_leitperspektive(soup, LP_BNE_URL, 'BNE')
        assert 'import_hinweis' not in node['metadata']


class TestExtractNiveauFromBpId:
    def test_bf_marker_returns_basis(self):
        assert extract_niveau_from_bp_id("BP2016BW_ALLG_GYM_CH_IK_11-12-BF_01") == "basis"

    def test_lf_marker_returns_leistung(self):
        assert extract_niveau_from_bp_id("BP2016BW_ALLG_GYM_CH_IK_11-12-LF_03") == "leistung"

    def test_no_marker_returns_regulaer(self):
        assert extract_niveau_from_bp_id("BP2016BW_ALLG_GYM_M_IK_5-6_01") == "regulär"

    def test_three_part_grade_returns_regulaer(self):
        assert extract_niveau_from_bp_id("BP2016BW_ALLG_GYM_CH_IK_8-9-10_01") == "regulär"

    def test_leitperspektive_returns_regulaer(self):
        assert extract_niveau_from_bp_id("BP2016BW_ALLG_LP_BNE") == "regulär"

    def test_bf_in_sub_node(self):
        assert extract_niveau_from_bp_id("BP2016BW_ALLG_GYM_CH_IK_11-12-BF_01_01") == "basis"


class TestExtractBpVersion:
    def test_regular_m_returns_2016(self):
        assert extract_bp_version("BP2016BW_ALLG_GYM_M_IK_5-6_01") == "2016"

    def test_v2_m_returns_2016_v2(self):
        assert extract_bp_version("BP2016BW_ALLG_GYM_M.V2_IK_5-6_01") == "2016.V2"

    def test_ch_returns_2016(self):
        assert extract_bp_version("BP2016BW_ALLG_GYM_CH_IK_8-9-10_01") == "2016"

    def test_fachplan_m_returns_2016(self):
        assert extract_bp_version("BP2016BW_ALLG_GYM_M") == "2016"

    def test_fachplan_m_v2_returns_2016_v2(self):
        assert extract_bp_version("BP2016BW_ALLG_GYM_M.V2") == "2016.V2"

    def test_hypothetical_v3_returns_correct(self):
        assert extract_bp_version("BP2030BW_ALLG_GYM_M.V3_IK_5-6_01") == "2030.V3"

    def test_no_year_returns_empty(self):
        assert extract_bp_version("BNE_01") == ""


class TestParseNodeFields:
    """Prüft dass parse_* alle neuen Felder setzen."""

    def test_leitidee_has_niveau_and_bp_version(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert 'niveau' in node
        assert node['niveau'] in ('regulär', 'basis', 'leistung')
        assert 'bp_version' in node
        assert node['bp_version'] == "2016"

    def test_ik_kompetenz_has_niveau_and_bp_version(self):
        soup = load_fixture('chemie_ik_standards.html')
        nodes = parse_ik_kompetenz_list(soup, CHEMIE_IK_STANDARD_URL,
                                        "BP2016BW_ALLG_GYM_CH_IK_8-9-10_01")
        assert len(nodes) > 0
        for node in nodes:
            assert node['niveau'] == "regulär"
            assert node['bp_version'] == "2016"

    def test_pk_gruppe_has_niveau_and_bp_version(self):
        soup = load_fixture('chemie_pk_gruppe.html')
        node = parse_pk_gruppe(soup, CHEMIE_PK_URL)
        assert 'niveau' in node
        assert node['niveau'] == "regulär"
        assert node['bp_version'] == "2016"

    def test_pk_kompetenz_has_niveau_and_bp_version(self):
        soup = load_fixture('chemie_pk_gruppe.html')
        nodes = parse_pk_kompetenz_list(soup, CHEMIE_PK_URL, "BP2016BW_ALLG_GYM_CH_PK_01")
        for node in nodes:
            assert node['niveau'] == "regulär"
            assert node['bp_version'] == "2016"


class TestParseLeitideeHinweis:
    """Tests für die bereinigte parse_leitidee auf einer Hinweis-Seite (kein tktable)."""

    def test_content_contains_description_text(self):
        soup = load_fixture('chemie_leitidee_hinweis.html')
        node = parse_leitidee(soup, CHEMIE_IK_HINWEIS_URL)
        assert 'BNT' in node['content'] or 'Naturphänomene' in node['content']

    def test_content_excludes_col2_boilerplate(self):
        soup = load_fixture('chemie_leitidee_hinweis.html')
        node = parse_leitidee(soup, CHEMIE_IK_HINWEIS_URL)
        assert 'Umsetzungshilfen' not in node['content']
        assert 'Beispielcurricula' not in node['content']
        assert 'verlinkten Unterstützungsmaterialien' not in node['content']

    def test_content_excludes_download_header(self):
        soup = load_fixture('chemie_leitidee_hinweis.html')
        node = parse_leitidee(soup, CHEMIE_IK_HINWEIS_URL)
        assert 'Download als PDF' not in node['content']

    def test_title_not_duplicated_in_content(self):
        soup = load_fixture('chemie_leitidee_hinweis.html')
        node = parse_leitidee(soup, CHEMIE_IK_HINWEIS_URL)
        assert node['title'] not in node['content']

    def test_content_is_string(self):
        soup = load_fixture('chemie_leitidee_hinweis.html')
        node = parse_leitidee(soup, CHEMIE_IK_HINWEIS_URL)
        assert isinstance(node['content'], str)

    def test_nav_leitidee_has_empty_content(self):
        """Navigations-Leitidee (keine Beschreibungsabsätze) → leerer content-String."""
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert node['content'] == ''

    def test_standalone_hinweis_label_excluded(self):
        """Alleinstehender 'Hinweis'-Text in col2 wird nicht in content aufgenommen."""
        soup = load_fixture('chemie_leitidee_hinweis.html')
        node = parse_leitidee(soup, CHEMIE_IK_HINWEIS_URL)
        # "Hinweis" als reiner Blocklist-String darf nicht im Content stehen
        lines = node['content'].split('\n')
        assert 'Hinweis' not in lines


class TestFindTitleTemplateLiteral:
    """_find_title gibt None zurück wenn nur JS-Template-Bindings gefunden werden."""

    def test_dollar_headline_text_returns_none(self):
        from bs4 import BeautifulSoup
        from scripts.scraper.parsers import _find_title
        html = '<html><body><main><h2>$headline.text</h2></main></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert _find_title(soup) is None

    def test_template_literal_returns_none(self):
        from bs4 import BeautifulSoup
        from scripts.scraper.parsers import _find_title
        html = '<html><body><main><h1 class="headline--2">${title}</h1></main></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert _find_title(soup) is None

    def test_real_title_still_returned(self):
        from bs4 import BeautifulSoup
        from scripts.scraper.parsers import _find_title
        html = '<html><body><main><h1 class="headline--2">2.2 Probleme lösen</h1></main></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert _find_title(soup) == '2.2 Probleme lösen'

    def test_parse_pk_gruppe_uses_breadcrumb_fallback(self):
        """parse_pk_gruppe fällt auf Breadcrumb zurück wenn Titel ein Template-Literal ist."""
        from bs4 import BeautifulSoup
        html = '''<html><body><main>
          <div class="breadcrumb">
            <nav class="breadcrumb__nav">
              <ol><li><a>Gymnasium</a></li><li>2.2 Probleme lösen</li></ol>
            </nav>
          </div>
          <h1 class="headline--2">$headline.text</h1>
          <table class="tktable"><tr><td>1. Text einer PK</td><td></td></tr></table>
        </main></body></html>'''
        soup = BeautifulSoup(html, 'html.parser')
        node = parse_pk_gruppe(soup, 'https://example.com/,Lde/BP2016BW_ALLG_GYM_M.V2_PK_02')
        assert node['title'] == '2.2 Probleme lösen'
        assert '$headline' not in node['title']


class TestScraperStructuralRobustness:
    """Regressionen für strukturelle Varianten der Live-Seiten, die die Fixtures
    nicht abdecken (Platzhalter-Titel, Inhalt außerhalb der Grid-Spalte)."""

    LEITIDEE_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_5-6_01"

    def test_find_title_skips_early_placeholder_uses_later_headline(self):
        """Steht das erste headline--2 auf '$headline.text', wird die spätere
        echte headline--2 genommen (nicht nur das erste Element geprüft)."""
        from bs4 import BeautifulSoup
        from scripts.scraper.parsers import _find_title
        html = '''<html><body><main>
          <h1 class="headline--2">$headline.text</h1>
          <h2 class="headline headline--2">2.2 Probleme mathematisch lösen</h2>
        </main></body></html>'''
        soup = BeautifulSoup(html, 'lxml')
        assert _find_title(soup) == '2.2 Probleme mathematisch lösen'

    def test_find_title_falls_back_to_og_title(self):
        """Nur Platzhalter-Überschriften → og:title als verlässlicher Fallback."""
        from bs4 import BeautifulSoup
        from scripts.scraper.parsers import _find_title
        html = '''<html><head>
          <meta property="og:title" content="2.2 Probleme mathematisch lösen">
        </head><body><main>
          <h1 class="headline--2">$headline.text</h1>
          <h2 class="headline headline--2">${headline.text}</h2>
        </main></body></html>'''
        soup = BeautifulSoup(html, 'lxml')
        assert _find_title(soup) == '2.2 Probleme mathematisch lösen'

    def test_leitidee_content_captured_outside_grid_col1(self):
        """Beschreibungstext wird erfasst, auch wenn er NICHT in .grid__col--1 liegt
        und unter einem Container mit 'header' im Klassennamen steht (Substring-Falle).
        Vorgelagerte Navigationstabelle und nachgelagerter Service-Block bleiben außen vor.
        """
        from bs4 import BeautifulSoup
        html = '''<html><head>
          <meta property="og:title" content="3.1.1 Hinweis zu den Klassen 5/6">
        </head><body><main>
          <nav class="breadcrumb__nav"><ol><li>3.1.1 Hinweis zu den Klassen 5/6</li></ol></nav>
          <table class="bplink"><tr><td>Chemie</td><td>Leitgedanken</td></tr></table>
          <h2 class="headline headline--2">3.1.1 Hinweis zu den Klassen 5/6</h2>
          <div class="page__section--header">
            <p>Der Erwerb chemiespezifischer Kompetenzen beginnt in Klasse 5 mit BNT.</p>
          </div>
          <p>Download als PDF</p>
          <div class="grid__col grid__col--2">
            <p>Umsetzungshilfen</p>
            <p>Die Beispielcurricula, Synopsen und Kompetenzraster sind beim Fach zu finden.</p>
          </div>
        </main></body></html>'''
        soup = BeautifulSoup(html, 'lxml')
        node = parse_leitidee(soup, self.LEITIDEE_URL)
        assert node['title'] == '3.1.1 Hinweis zu den Klassen 5/6'
        assert 'Der Erwerb chemiespezifischer Kompetenzen' in node['content']
        assert 'Umsetzungshilfen' not in node['content']
        assert 'Beispielcurricula' not in node['content']
        assert 'Download als PDF' not in node['content']
        assert 'Chemie' not in node['content']  # Navigationstabelle vor dem Titel

    def test_leitidee_content_breaks_at_service_block_without_col2(self):
        """Auch ohne .grid__col--2-Wrapper endet der Inhalt am Service-Block-Marker."""
        from bs4 import BeautifulSoup
        html = '''<html><body><main>
          <h2 class="headline headline--2">3.1.1 Hinweis zu den Klassen 5/6</h2>
          <p>Beschreibender Leitidee-Text.</p>
          <p>Die verlinkten Unterstützungsmaterialien sind nicht Bestandteil des Bildungsplans.</p>
          <p>Die Beispielcurricula, Synopsen und Kompetenzraster sind beim Fach zu finden.</p>
        </main></body></html>'''
        soup = BeautifulSoup(html, 'lxml')
        node = parse_leitidee(soup, self.LEITIDEE_URL)
        assert node['content'] == 'Beschreibender Leitidee-Text.'


class TestLiveFixtureRegressions:
    """Gegen die echten, per httpx gespeicherten Live-Seiten (rohes HTTP-HTML).

    Diese Fixtures bilden die tatsächliche Seitenstruktur ab — anders als die
    idealisierten Fixtures, gegen die beide Fehler grün liefen.
    """

    PK_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_M.V2_PK_02"
    LEITIDEE_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_5-6_01"
    FACHPLAN_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH"

    def test_pk_gruppe_live_title_is_page_title_not_subheading(self):
        """M.V2_PK_02: einziges headline--2 ist '$headline.text'. Titel muss aus
        og:title kommen ('2.2 Probleme mathematisch lösen'), nicht aus einer
        headline--4-Zwischenüberschrift ('Fragen stellen …')."""
        soup = load_fixture('mathematik_v2_pk_02.html')
        node = parse_pk_gruppe(soup, self.PK_URL)
        assert node['title'] == '2.2 Probleme mathematisch lösen'
        assert '$headline' not in node['title']
        assert 'Fragen stellen' not in node['title']

    def test_pk_gruppe_live_content_is_clean(self):
        """content darf weder den JS-Platzhalter noch ein Titel-Duplikat enthalten,
        aber den Einleitungstext."""
        soup = load_fixture('mathematik_v2_pk_02.html')
        node = parse_pk_gruppe(soup, self.PK_URL)
        assert '$headline' not in node['content']
        assert not node['content'].startswith('2.2 Probleme mathematisch lösen')
        assert 'analysieren Probleme' in node['content']

    def test_fachplan_live_no_crash_and_clean_title(self):
        """Fachplan-Übersicht hat keinen Fließtext → content == Titel; Titel sauber,
        kein Platzhalter/Boilerplate."""
        soup = load_fixture('chemie_fachplan_live.html')
        node = parse_fachplan(soup, self.FACHPLAN_URL)
        assert node['content_type'] == 'fachplan'
        assert node['title']
        assert '$headline' not in node['title']
        assert '$headline' not in node['content']
        assert 'Umsetzungshilfen' not in node['content']
        assert 'Download als PDF' not in node['content']

    def test_leitidee_live_hinweis_content_captured(self):
        """CH_IK_5-6_01: Inhalt liegt im 3-Spalten-Layout (grid--25-50-25) in
        .grid__col--2 unter einem .itk_header-Container. Der Beschreibungstext muss
        erfasst werden, Service-/Boilerplate-Text nicht."""
        soup = load_fixture('chemie_leitidee_hinweis_live.html')
        node = parse_leitidee(soup, self.LEITIDEE_URL)
        assert node['title'] == '3.1.1 Hinweis zu den Klassen 5/6'
        assert 'Der Erwerb chemiespezifischer Kompetenzen' in node['content']
        assert 'Umsetzungshilfen' not in node['content']
        assert 'Beispielcurricula' not in node['content']
        assert 'Download als PDF' not in node['content']


class TestExpandOperatorTitle:
    """Zerlegung der Operator-Titelzelle in (Titel, Aliase) — reale BW-Schreibweisen."""

    @pytest.mark.parametrize("raw, expected_title, expected_aliase", [
        # Ergänzungsstrich (Komma/Slash) — Stamm-Extraktion
        ("ein-, zuordnen", "einordnen", ["zuordnen"]),
        ("ein-/zuordnen, erfassen", "einordnen", ["zuordnen", "erfassen"]),
        ("an-/verwenden, nutzen, einsetzen; beachten",
         "anwenden", ["verwenden", "nutzen", "einsetzen", "beachten"]),
        # Klammer-Präfix
        ("(be-)nennen", "nennen", ["benennen"]),
        ("(nach-)erzählen", "erzählen", ["nacherzählen"]),
        # einfache Synonyme (Komma / einwortiger Slash)
        ("beurteilen, bewerten", "beurteilen", ["bewerten"]),
        ("analysieren/untersuchen", "analysieren", ["untersuchen"]),
        # Einzelverb — keine Aliase
        ("nennen", "nennen", []),
        # beschreibende Phrasen (' und ') → verbatim, keine Aliase
        ("wahrnehmen und darüber sprechen/sich äußern",
         "wahrnehmen und darüber sprechen/sich äußern", []),
        # Komma innerhalb Klammern → nicht zerlegen
        ("(global, detailliert, selektiv) verstehen",
         "(global, detailliert, selektiv) verstehen", []),
    ])
    def test_expand(self, raw, expected_title, expected_aliase):
        title, aliase = expand_operator_title(raw)
        assert title == expected_title
        assert aliase == expected_aliase

    def test_soft_hyphens_and_asterisks_stripped(self):
        title, aliase = expand_operator_title("ab­lei­ten")
        assert title == "ableiten"
        assert aliase == []
        title2, _ = expand_operator_title("(*zeigen*)/aufzeigen")
        assert "*" not in title2

    def test_empty(self):
        assert expand_operator_title("   ") == ("", [])


class TestParseOperatorList:
    """parse_operator_list gegen die echte Chemie-Operatoren-Anhangseite (V2)."""

    PARENT = "BP2016BW_ALLG_GYM_CH.V2"

    def _nodes(self):
        soup = load_fixture('operatoren_chemie_live.html')
        return parse_operator_list(soup, OPERATOREN_CH_URL, self.PARENT)

    def test_returns_operator_nodes(self):
        nodes = self._nodes()
        assert len(nodes) == 20
        assert all(n['content_type'] == 'operator' for n in nodes)
        assert all(n['type'] == 'knowledge' for n in nodes)
        assert all(n['visibility'] == 'global' for n in nodes)

    def test_edition_and_parent(self):
        nodes = self._nodes()
        assert all(n['bp_version'] == '2016.V2' for n in nodes)
        assert all(n['parent_bp_id'] == self.PARENT for n in nodes)
        assert all(n['min_grade'] is None and n['max_grade'] is None for n in nodes)

    def test_afb_is_list_of_roman(self):
        nodes = self._nodes()
        allowed = {'I', 'II', 'III'}
        for n in nodes:
            afb = n['metadata']['afb']
            assert isinstance(afb, list) and afb
            assert set(afb) <= allowed

    def test_bp_id_and_metadata(self):
        nodes = self._nodes()
        first = nodes[0]
        assert first['bp_id'] == 'BP2016BW_ALLG_GYM_CH.V2_OP_01'
        assert first['metadata']['operator_nr'] == 1
        assert 'aliase' in first['metadata']

    def test_soft_hyphens_stripped_in_titles_and_content(self):
        nodes = self._nodes()
        assert all('­' not in n['title'] for n in nodes)
        assert all('­' not in n['content'] for n in nodes)

    def test_known_operator_present(self):
        nodes = self._nodes()
        by_title = {n['title']: n for n in nodes}
        assert 'ableiten' in by_title
        assert by_title['ableiten']['metadata']['afb'] == ['II']
        assert by_title['ableiten']['content']

    def test_no_table_returns_empty(self):
        from bs4 import BeautifulSoup
        empty = BeautifulSoup("<html><body><p>kein Anhang</p></body></html>", 'lxml')
        assert parse_operator_list(empty, OPERATOREN_CH_URL, self.PARENT) == []
