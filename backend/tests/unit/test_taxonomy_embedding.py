"""Unit-Tests fuer EMBEDDING_ENRICHMENT und Anreicherungslogik."""
import pytest
from datetime import date, datetime
from uuid import UUID, uuid4

from app.context.embedding import _build_signature_line, _extract_metadata_field, _build_embedding_input, EMBEDDING_CONTENT_TYPES
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

EXPECTED_EMBEDDING_TYPES = frozenset({
    'ik_kompetenz', 'pk_kompetenz', 'pk_gruppe', 'leitidee', 'leitperspektive_aspekt',
    'kapitel', 'themengebiet', 'funktion', 'bauteil', 'abstrakt', 'konvention',
    'operator',
})

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
        assert result.startswith("Diodensymbol mit Pfeilen")
        assert "LED - Leuchtdiode." in result

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
        assert result.startswith("digitalWrite(pin: int, value: int) -> void")

    def test_build_embedding_input_fallback(self, make_node):
        """Knoten ohne EMBEDDING_ENRICHMENT-Eintrag: nur content."""
        node = make_node(category="concept", content_type="abstrakt",
                         content="PWM simuliert analoge Spannung.", metadata={})
        assert _build_embedding_input(node) == "PWM simuliert analoge Spannung."

    def test_build_embedding_input_no_content(self, make_node):
        """Knoten ohne content: leerer String."""
        node = make_node(category="concept", content_type="abstrakt", content="")
        assert _build_embedding_input(node) == ""

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
