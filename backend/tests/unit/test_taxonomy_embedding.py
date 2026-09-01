"""Unit-Tests fuer EMBEDDING_ENRICHMENT und Anreicherungslogik."""
import pytest
from datetime import date, datetime
from uuid import UUID, uuid4

from app.context.embedding import (
    EMBEDDING_CONTENT_TYPES,
    _build_embedding_input,
    _build_signature_line,
    _extract_metadata_field,
    traegt_substanz,
)
from app.context.taxonomy import EMBEDDING_ENRICHMENT, EMBEDDING_CONTENT_TYPES as TAXONOMY_EMBEDDING_CONTENT_TYPES, get_scope_defaults, validate_content_type


# ── Fixture: Mock ContextNode ────────────────────────────────────────────────

class MockContextNode:
    """Minimaler Mock fuer ContextNode mit den benoetigten Attributen."""
    def __init__(self, category=None, content_type=None, content=None, metadata_=None, title=None):
        self.category = category
        self.content_type = content_type
        self.content = content
        self.metadata_ = metadata_ or {}
        self.title = title


@pytest.fixture
def make_node():
    """Fixture zum Erstellen von Mock-Knoten."""
    def _make(category, content_type=None, content="", metadata=None, title="Test"):
        return MockContextNode(
            category=category,
            content_type=content_type,
            content=content,
            metadata_=metadata or {},
            title=title,
        )
    return _make


# ── Embedding-Ableitung aus taxonomy.yaml ───────────────────────────────────

# Die Liste ist eine **Entscheidung**, keine Ableitung — deshalb steht sie hier ausgeschrieben
# und nicht aus `taxonomy.yaml` gelesen. Kriterium und Begründung je Typ: ADR-017, Nachtrag
# 31.08./01.09.2026. Wer einen Typ hinzunimmt, ändert beides.
EXPECTED_EMBEDDING_TYPES = frozenset({
    # Bildungsplan und Struktur (Bestand bis 09/2026)
    'ik_kompetenz', 'pk_kompetenz', 'pk_gruppe', 'leitidee', 'leitperspektive_aspekt',
    'kapitel', 'themengebiet', 'funktion', 'bauteil', 'abstrakt', 'konvention',
    'operator',
    # LFDB (aus PDF): Themenblock + Kompetenz sind inhaltstragend; Baustein ist Container.
    'lfdb_themenblock', 'lfdb_kompetenz',
    # Nutzererzeugte Inhalte. Ohne sie konnte thematisch nur der Bildungsplan gefunden
    # werden — und jede Gewichtung nach Rolle lief ins Leere, weil die gewichteten Typen
    # in der Ähnlichkeitssuche gar nicht vorkamen.
    'aufgabenblatt', 'quelltext', 'methodenblatt', 'operatorenblatt', 'praesentation',
    'methode', 'pruefungsanforderung', 'unterrichtsstunde', 'unterrichtseinheit',
    'reflexion', 'arbeitsblatt', 'aufgabe', 'klausur', 'code_beispiel', 'lerntext',
    # Fachbegriffe mit Definition (neuer Typ, ADR-017-Nachtrag).
    'begriff',
})

# Typen, deren Embedding-Input ausdrücklich festgelegt ist, statt sich aus `content` plus
# Anreicherung zu ergeben. Nur hier lässt sich etwas gezielt **weglassen**.
EXPECTED_INPUT_KEYS = {
    ('knowledge', 'methode'),
    ('artifact', 'unterrichtsstunde'),
    ('artifact', 'unterrichtseinheit'),
}

EXPECTED_ENRICHMENT_KEYS = {
    ('concept', 'funktion'),
    ('concept', 'bauteil'),
    ('knowledge', 'ik_kompetenz'),
    ('knowledge', 'pk_kompetenz'),
    ('knowledge', 'kapitel'),
}


class TestEmbeddingDerivation:
    def test_embedding_content_types_exact(self):
        assert TAXONOMY_EMBEDDING_CONTENT_TYPES == EXPECTED_EMBEDDING_TYPES

    def test_embedding_input_nur_wo_beabsichtigt(self):
        """`embedding_input` ersetzt den Standardaufbau und ist damit die einzige Stelle,
        an der etwas aus dem Vektor **herausgehalten** wird. Ein versehentlicher Eintrag
        würde `content` stillschweigend ausschließen."""
        from app.context.taxonomy import EMBEDDING_INPUT

        assert set(EMBEDDING_INPUT) == EXPECTED_INPUT_KEYS

    def test_verlaufsplan_bleibt_draussen(self):
        """⚠️ Das Thema, nicht der Ablauf (ADR-017, Nachtrag 01.09.2026).

        „Einstieg, Erarbeitung, Sicherung" steht in jedem Stundenentwurf und machte alle
        einander ähnlich statt ihrem Gegenstand — dieselbe Falle wie das dominierende
        Wort „Operator" bei den Operator-Knoten.
        """
        from app.context.taxonomy import EMBEDDING_INPUT

        for schluessel in (("artifact", "unterrichtsstunde"), ("artifact", "unterrichtseinheit")):
            quellen = EMBEDDING_INPUT[schluessel]
            assert not any("phasen" in q for q in quellen), quellen
            assert "title" in quellen

    def test_embedding_re_export_matches_taxonomy(self):
        assert EMBEDDING_CONTENT_TYPES == TAXONOMY_EMBEDDING_CONTENT_TYPES

    def test_embedding_enrichment_keys_exact(self):
        assert set(EMBEDDING_ENRICHMENT.keys()) == EXPECTED_ENRICHMENT_KEYS

    def test_consistency_guard_enrichment_implies_embedding(self):
        """Jeder Typ mit embedding_enrichment muss auch embedding: true tragen."""
        for cat, ct_key in EMBEDDING_ENRICHMENT:
            assert ct_key in TAXONOMY_EMBEDDING_CONTENT_TYPES, (
                f"({cat}, {ct_key}) hat embedding_enrichment aber kein embedding: true"
            )

    def test_enrichment_count(self):
        assert len(EMBEDDING_ENRICHMENT) == 5


# ── Taxonomie-Tests ─────────────────────────────────────────────────────────

class TestTaxonomyThemengebiet:
    def test_themengebiet_valid(self):
        validate_content_type("knowledge", "themengebiet")  # darf nicht werfen

    def test_themengebiet_scope_default(self):
        read, write = get_scope_defaults("themengebiet")
        assert read == "school"
        assert write == "school"


# ── Embedding Enrichment Config ──────────────────────────────────────────────

class TestEmbeddingEnrichmentConfig:
    def test_contains_expected_entries(self):
        assert ("concept", "bauteil") in EMBEDDING_ENRICHMENT
        assert ("concept", "funktion") in EMBEDDING_ENRICHMENT
        assert ("knowledge", "ik_kompetenz") in EMBEDDING_ENRICHMENT
        assert ("knowledge", "pk_kompetenz") in EMBEDDING_ENRICHMENT

    def test_bauteil_enrichment_field(self):
        fields = EMBEDDING_ENRICHMENT[("concept", "bauteil")]
        assert "metadata.schaltzeichen.beschreibung" in fields

    def test_funktion_enrichment_field(self):
        fields = EMBEDDING_ENRICHMENT[("concept", "funktion")]
        assert "metadata.signatur" in fields

    def test_ik_kompetenz_enrichment_field(self):
        fields = EMBEDDING_ENRICHMENT[("knowledge", "ik_kompetenz")]
        assert "metadata.breadcrumb" in fields


# ── Signature Line ───────────────────────────────────────────────────────────

class TestBuildSignatureLine:
    def test_signature_line_full(self):
        sig = {
            "name": "digitalWrite",
            "sprache": "arduino_cpp",
            "parameter": [
                {"name": "pin", "typ": "int", "beschreibung": "Pin-Nummer"},
                {"name": "value", "typ": "int", "beschreibung": "HIGH oder LOW"},
            ],
            "rueckgabe": {"typ": "void", "beschreibung": ""},
        }
        assert _build_signature_line(sig) == "digitalWrite(pin: int, value: int) -> void"

    def test_signature_line_no_params(self):
        sig = {"name": "millis", "parameter": [], "rueckgabe": {"typ": "unsigned long"}}
        assert _build_signature_line(sig) == "millis() -> unsigned long"

    def test_signature_line_no_return(self):
        sig = {"name": "setup", "parameter": [], "rueckgabe": {}}
        assert _build_signature_line(sig) == "setup()"

    def test_signature_line_empty(self):
        assert _build_signature_line({}) == ""

    def test_signature_line_missing_name(self):
        sig = {"parameter": [{"name": "x", "typ": "int"}]}
        assert _build_signature_line(sig) == ""


# ── Extract Metadata Field ───────────────────────────────────────────────────

class TestExtractMetadataField:
    def test_extract_nested_field(self):
        meta = {"schaltzeichen": {"beschreibung": "Rechteck mit Anschluessen"}}
        result = _extract_metadata_field(meta, "metadata.schaltzeichen.beschreibung")
        assert result == "Rechteck mit Anschluessen"

    def test_extract_top_level_field(self):
        meta = {"beschreibung": "Test"}
        result = _extract_metadata_field(meta, "metadata.beschreibung")
        assert result == "Test"

    def test_extract_missing_field(self):
        assert _extract_metadata_field({}, "metadata.schaltzeichen.beschreibung") == ""

    def test_extract_nested_missing_intermediate(self):
        meta = {"schaltzeichen": {}}
        assert _extract_metadata_field(meta, "metadata.schaltzeichen.beschreibung") == ""

    def test_extract_signatur_field(self):
        meta = {
            "signatur": {
                "name": "func",
                "parameter": [{"name": "a", "typ": "int"}],
                "rueckgabe": {"typ": "bool"},
            }
        }
        result = _extract_metadata_field(meta, "metadata.signatur")
        assert result == "func(a: int) -> bool"


# ── Build Embedding Input ───────────────────────────────────────────────────

class TestBuildEmbeddingInput:
    def test_build_embedding_input_bauteil(self, make_node):
        """Bauteil-Node: schaltzeichen.beschreibung wird vorangestellt."""
        node = make_node(
            category="concept",
            content_type="bauteil",
            content="LED - Leuchtdiode.",
            metadata={"schaltzeichen": {"beschreibung": "Diodensymbol mit Pfeilen"}},
        )
        result = _build_embedding_input(node)
        # Der Titel steht vorn, weil er weder im Inhalt noch in der Anreicherung vorkommt;
        # die Anreicherung folgt direkt danach.
        assert result == "Test\nDiodensymbol mit Pfeilen\nLED - Leuchtdiode."

    def test_build_embedding_input_funktion(self, make_node):
        """Funktion-Node: Signaturzeile wird vorangestellt."""
        node = make_node(
            category="concept",
            content_type="funktion",
            content="Setzt einen digitalen Pin auf HIGH oder LOW.",
            metadata={
                "signatur": {
                    "name": "digitalWrite",
                    "parameter": [{"name": "pin", "typ": "int"}, {"name": "value", "typ": "int"}],
                    "rueckgabe": {"typ": "void"},
                }
            },
        )
        result = _build_embedding_input(node)
        assert "digitalWrite(pin: int, value: int) -> void" in result
        assert result.startswith("Test\n")  # Titel trägt eigene Information

    def test_build_embedding_input_fallback(self, make_node):
        """Knoten ohne EMBEDDING_ENRICHMENT-Eintrag: Titel + content."""
        node = make_node(category="concept", content_type="abstrakt",
                         content="PWM simuliert analoge Spannung.", metadata={})
        assert _build_embedding_input(node) == "Test\nPWM simuliert analoge Spannung."

    def test_build_embedding_input_titel_im_content_nicht_doppelt(self, make_node):
        """Steht der Titel schon im Inhalt, bleibt der Input unveraendert.

        Das ist der Regelfall bei Bildungsplan-Kompetenzen (Titel = Inhalt + Nummer) und
        der Grund, warum die Titel-Aufnahme kein Re-Embedding des Bestands erzwingt.
        """
        node = make_node(category="concept", content_type="abstrakt",
                         content="Ein Test der Signalform.", metadata={})
        assert _build_embedding_input(node) == "Ein Test der Signalform."

    def test_build_embedding_input_no_content(self, make_node):
        """Knoten ohne content: der Titel allein — frueher wurde er uebersprungen."""
        node = make_node(category="concept", content_type="abstrakt", content="")
        assert _build_embedding_input(node) == "Test"

    def test_build_embedding_input_bp_ik_kompetenz(self, make_node):
        """Bildungsplan IK-Kompetenz: breadcrumb wird vorangestellt."""
        node = make_node(
            category="knowledge",
            content_type="ik_kompetenz",
            content="Die Schuelerinnen und Schueler koennen...",
            metadata={"breadcrumb": ["Gymnasium", "Mathematik", "Klasse 7/8", "Algebra"]},
        )
        result = _build_embedding_input(node)
        assert "Gymnasium | Mathematik | Klasse 7/8 | Algebra" in result
        assert "Die Schuelerinnen und Schueler koennen..." in result

    def test_build_embedding_input_operator(self, make_node):
        """Operator: Titel (Verb) + Synonyme werden dem content (Definition) vorangestellt."""
        node = make_node(
            category="knowledge",
            content_type="operator",
            content="Sachverhalte auf Regeln zurueckfuehren",
            metadata={"afb": ["III"], "aliase": ["begruenden"]},
            title="begründen",
        )
        result = _build_embedding_input(node)
        assert result.startswith("begründen, begruenden")
        assert "Sachverhalte auf Regeln zurueckfuehren" in result

    def test_build_embedding_input_operator_no_aliase(self, make_node):
        """Operator ohne Synonyme: nur der Titel wird vorangestellt."""
        node = make_node(
            category="knowledge",
            content_type="operator",
            content="Elemente ohne Erlaeuterung wiedergeben",
            metadata={"afb": ["I"], "aliase": []},
            title="nennen",
        )
        result = _build_embedding_input(node)
        assert result == "nennen\nElemente ohne Erlaeuterung wiedergeben"


class TestEmbeddingInputJeTyp:
    """`embedding_input` aus `taxonomy.yaml` — der Weg, etwas gezielt wegzulassen."""

    def test_methode_traegt_titel_aliase_und_content(self, make_node):
        """Beschluss vom 01.09.2026: Methoden sollen über Titel, Aliase **und** Inhalt
        gefunden werden. Der Inhalt fehlt im Dev-Bestand noch — die Reihenfolge steht."""
        node = make_node(
            "knowledge", "methode", content="Zuerst allein, dann zu zweit, dann im Plenum.",
            metadata={"aliase": ["Ich-Du-Wir"]}, title="Think-Pair-Share",
        )
        assert _build_embedding_input(node) == (
            "Think-Pair-Share\nIch-Du-Wir\nZuerst allein, dann zu zweit, dann im Plenum."
        )

    def test_stunde_traegt_kompetenztitel_statt_verlaufsplan(self, make_node):
        node = make_node(
            "artifact", "unterrichtsstunde", content="",
            metadata={
                "refs": [
                    {"node_id": "x", "titel": "Bruchteile von Größen bestimmen", "code": "3.1"},
                    {"node_id": "y", "titel": "Anteile vergleichen", "code": "3.2"},
                ],
                "phasen": [{"name": "Einstieg"}, {"name": "Erarbeitung"}, {"name": "Sicherung"}],
            },
            title="Brüche einführen",
        )
        eingabe = _build_embedding_input(node)
        assert eingabe == (
            "Brüche einführen\nBruchteile von Größen bestimmen, Anteile vergleichen"
        )
        for wort in ("Einstieg", "Erarbeitung", "Sicherung"):
            assert wort not in eingabe

    def test_leere_refs_lassen_nur_den_titel(self, make_node):
        node = make_node("artifact", "unterrichtsstunde", metadata={"refs": []},
                         title="Projektauftrag")
        assert _build_embedding_input(node) == "Projektauftrag"


class TestBackfillRegel:
    """Kein Vektor, der nur aus dem Titel besteht — aber nur, wo das gemeint ist."""

    def test_stunde_ohne_kompetenzen_wird_vertagt(self, make_node):
        node = make_node("artifact", "unterrichtsstunde", metadata={"refs": []},
                         title="Projektauftrag")
        assert traegt_substanz(node) is False

    def test_stunde_mit_kompetenzen_wird_eingebettet(self, make_node):
        node = make_node(
            "artifact", "unterrichtsstunde",
            metadata={"refs": [{"titel": "Anteile vergleichen"}]}, title="Brüche",
        )
        assert traegt_substanz(node) is True

    def test_bildungsplan_knoten_bleiben_unberuehrt(self, make_node):
        """⚠️ Der Fall, der die Regel begrenzt: Bei `leitidee`, `pk_gruppe` und `kapitel`
        ist der Titel als alleiniger Input **Absicht** — er benennt das Thema, das im
        Inhalt oft gar nicht vorkommt. Griffe die Regel dort, verlören Tausende
        Bildungsplan-Knoten ihr Embedding."""
        node = make_node("knowledge", "leitidee", content="", title="3.1.2 Malerei")
        assert traegt_substanz(node) is True
        assert _build_embedding_input(node) == "3.1.2 Malerei"

    def test_methode_ohne_alles_wird_vertagt(self, make_node):
        node = make_node("knowledge", "methode", content="", metadata={"aliase": []},
                         title="Placemat")
        assert traegt_substanz(node) is False

    def test_methode_mit_aliasen_genuegt(self, make_node):
        node = make_node("knowledge", "methode", content="",
                         metadata={"aliase": ["Ich-Du-Wir"]}, title="Think-Pair-Share")
        assert traegt_substanz(node) is True
