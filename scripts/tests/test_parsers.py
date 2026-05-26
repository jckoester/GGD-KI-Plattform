"""Unit-Tests fuer scripts/scraper/parsers.py — gegen statische HTML-Fixtures."""

import re

import pytest
from scripts.scraper.parsers import (
    ScraperParseError,
    parse_leitidee,
    parse_ik_kompetenz_list,
    parse_pk_gruppe,
    parse_pk_kompetenz_list,
    parse_leitperspektive,
    parse_leitperspektive_aspekt_list,
)

from scripts.tests.conftest import load_fixture


CHEMIE_IK_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_8-9-10_01"
CHEMIE_IK_STANDARD_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_IK_8-9-10_01_01"
CHEMIE_PK_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_GYM_CH_PK_01"
LP_BNE_URL = "https://www.bildungsplaene-bw.de/,Lde/BP2016BW_ALLG_LP_BNE"


class TestParseLeitidee:
    def test_returns_leitidee_node(self):
        soup = load_fixture('chemie_leitidee.html')
        node = parse_leitidee(soup, CHEMIE_IK_URL)
        assert node['content_type'] == 'leitidee'
        assert node['type'] == 'knowledge'
        assert node['bp_id'].startswith('BP2016BW_ALLG_GYM_CH_IK')
        assert node['title']
        assert node['content']

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
