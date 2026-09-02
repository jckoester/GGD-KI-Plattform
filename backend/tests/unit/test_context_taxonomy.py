"""Unit-Tests für app.context.taxonomy."""

import pytest

from app.context.taxonomy import (
    VALID_CONTENT_TYPES,
    validate_content_type,
    get_valid_until_offset,
    get_scope_defaults,
)


# ── validate_content_type ─────────────────────────────────────────────────────

class TestValidateContentType:

    def test_valid_document_types(self):
        for ct in VALID_CONTENT_TYPES["document"]:
            validate_content_type("document", ct)  # kein Fehler

    def test_valid_knowledge_types(self):
        for ct in VALID_CONTENT_TYPES["knowledge"]:
            validate_content_type("knowledge", ct)

    def test_valid_artifact_types(self):
        for ct in VALID_CONTENT_TYPES["artifact"]:
            validate_content_type("artifact", ct)

    def test_valid_concept_types(self):
        for ct in VALID_CONTENT_TYPES["concept"]:
            validate_content_type("concept", ct)

    def test_none_content_type_always_valid(self):
        for cat in ("document", "knowledge", "artifact", "concept"):
            validate_content_type(cat, None)  # kein Fehler

    def test_cross_category_raises(self):
        # knowledge-Type in document-category
        with pytest.raises(ValueError, match="fachplan"):
            validate_content_type("document", "fachplan")

    def test_cross_category_raises_artifact_in_knowledge(self):
        with pytest.raises(ValueError, match="unterrichtsentwurf"):
            validate_content_type("knowledge", "unterrichtsentwurf")

    def test_cross_category_raises_concept_in_artifact(self):
        with pytest.raises(ValueError, match="funktion"):
            validate_content_type("artifact", "funktion")

    def test_unknown_category_raises(self):
        with pytest.raises(ValueError, match="Unbekannte category"):
            validate_content_type("invalid_cat", "something")

    def test_unknown_content_type_raises(self):
        with pytest.raises(ValueError):
            validate_content_type("document", "nonexistent_type")

    def test_error_message_contains_allowed_types(self):
        with pytest.raises(ValueError) as exc_info:
            validate_content_type("concept", "funktion_x")
        assert "Erlaubt:" in str(exc_info.value)


# ── get_valid_until_offset ────────────────────────────────────────────────────

class TestGetValidUntilOffset:

    def test_permanent_types_return_none(self):
        permanent = ["fachplan", "ik_kompetenz", "aufgabe", "arbeitsblatt", "funktion"]
        for ct in permanent:
            assert get_valid_until_offset(ct) is None

    def test_schueler_artefakte_laufen_zum_schuljahresende_ab(self):
        """Seit 02.09.2026 kein Tages-Offset mehr, sondern Schuljahresende.

        Die fünf Typen trugen vorher 42 Tage — ein aus **einem** ADR-013-Beispiel
        (`artifact.lernplan` → ~6 Wochen) verallgemeinerter Wert. Der Offset ist damit
        `None`; die Frist steht als `valid_until_default: schuljahresende` in der
        Taxonomie.
        """
        from app.context.taxonomy import get_valid_until_schuljahresende

        for ct in ["lernplan", "gliederung", "mindmap", "schuelertext", "feedback_text"]:
            assert get_valid_until_offset(ct) is None, ct
            assert get_valid_until_schuljahresende(ct), ct

    def test_none_content_type_returns_none(self):
        assert get_valid_until_offset(None) is None

    def test_unknown_content_type_returns_none(self):
        assert get_valid_until_offset("unbekannt") is None


# ── get_scope_defaults ────────────────────────────────────────────────────────

class TestGetScopeDefaults:

    def test_global_types(self):
        for ct in ("fachplan", "ik_kompetenz", "pk_kompetenz", "leitidee", "leitperspektive_aspekt", "operator"):
            read, write = get_scope_defaults(ct)
            assert read == "global" and write == "global"

    def test_leitperspektive_aspekt_valid(self):
        validate_content_type("knowledge", "leitperspektive_aspekt")

    def test_leitperspektive_aspekt_scope_defaults(self):
        read_scope, write_scope = get_scope_defaults("leitperspektive_aspekt")
        assert read_scope == "global"
        assert write_scope == "global"

    def test_school_subject_curriculum(self):
        read, write = get_scope_defaults("curriculum")
        assert read == "school" and write == "subject"

    def test_private_artifacts(self):
        for ct in ("klausur", "unterrichtsstunde", "lernplan"):
            read, write = get_scope_defaults(ct)
            assert read == "private" and write == "private"

    def test_none_returns_fallback(self):
        read, write = get_scope_defaults(None)
        assert read == "school" and write == "private"

    def test_unknown_returns_fallback(self):
        read, write = get_scope_defaults("completely_unknown")
        assert read == "school" and write == "private"

    def test_scope_restrictivity_invariant(self):
        """write_scope darf nie permissiver sein als read_scope."""
        scope_order = {"private": 0, "group": 1, "subject": 2, "school": 3, "global": 4}
        for ct in list(VALID_CONTENT_TYPES["document"]) + \
                  list(VALID_CONTENT_TYPES["knowledge"]) + \
                  list(VALID_CONTENT_TYPES["artifact"]) + \
                  list(VALID_CONTENT_TYPES["concept"]):
            read, write = get_scope_defaults(ct)
            assert scope_order[write] <= scope_order[read], (
                f"{ct}: write_scope={write!r} ist permissiver als read_scope={read!r}"
            )


class TestLifecycleVollstaendigkeit:
    """Jeder content_type braucht einen **ausdrücklichen** Lifecycle-Eintrag.

    ⚠️ Der Grund, warum das ein Test sein muss: `get_valid_until_offset` liest die
    Handliste mit `.get()`, und ein fehlender Eintrag liefert `None` — was hier „läuft
    nie ab" bedeutet. Ein Typ, der eigentlich verfallen sollte, bliebe damit
    stillschweigend für immer stehen. Am 01.09.2026 fehlten vier Typen unbemerkt
    (`begriff`, die drei LFDB-Typen); bei ihnen war „permanent" zufällig richtig.
    """

    def test_jeder_typ_hat_einen_eintrag(self):
        from app.context.taxonomy import SCOPE_DEFAULTS, VALID_UNTIL_DEFAULTS_DAYS

        fehlend = sorted(set(SCOPE_DEFAULTS) - set(VALID_UNTIL_DEFAULTS_DAYS))
        assert not fehlend, (
            f"Ohne Lifecycle-Eintrag: {fehlend}. Bitte in "
            "VALID_UNTIL_DEFAULTS_DAYS ergänzen — auch wenn der Wert None lautet."
        )

    def test_keine_karteileichen(self):
        """Umgekehrt: kein Eintrag für einen Typ, den es nicht mehr gibt."""
        from app.context.taxonomy import SCOPE_DEFAULTS, VALID_UNTIL_DEFAULTS_DAYS

        verwaist = sorted(set(VALID_UNTIL_DEFAULTS_DAYS) - set(SCOPE_DEFAULTS))
        assert not verwaist, f"Lifecycle-Eintrag ohne content_type: {verwaist}"

    def test_schuljahresende_statt_tages_offset(self):
        """Zwei Mechanismen, die sich ausschließen — nie beide an einem Typ.

        Bis 02.09.2026 trugen fünf Schüler-Artefakte 42 Tage; die Zahl war ein auf
        mehrere Typen verallgemeinertes Beispiel aus ADR-013 und nie begründet. Jetzt
        gilt für sie das Schuljahresende, wie bei Stunde und Einheit.
        """
        from app.context.taxonomy import (
            SCHULJAHRESENDE_CONTENT_TYPES,
            VALID_UNTIL_DEFAULTS_DAYS,
        )

        doppelt = sorted(
            ct for ct in SCHULJAHRESENDE_CONTENT_TYPES
            if VALID_UNTIL_DEFAULTS_DAYS.get(ct) is not None
        )
        assert not doppelt, (
            f"Diese Typen tragen Tages-Offset UND Schuljahresende: {doppelt}"
        )

    def test_kein_tages_offset_mehr_im_bestand(self):
        """Solange keiner existiert, ist die Reihenfolge-Frage aus dem Test darüber
        rein hypothetisch — das soll auffallen, wenn wieder einer dazukommt."""
        from app.context.taxonomy import VALID_UNTIL_DEFAULTS_DAYS

        mit_offset = {k: v for k, v in VALID_UNTIL_DEFAULTS_DAYS.items() if v is not None}
        assert mit_offset == {}, (
            f"Neuer Tages-Offset: {mit_offset}. Zulässig, aber begründungspflichtig — "
            "siehe Todo „valid_until-Defaults prüfen\"."
        )


class TestUiStatus:
    """`ui_status` steuert ausschließlich Auswahlflächen (ADR-019 F6)."""

    def test_nur_gueltige_werte(self):
        from app.context.taxonomy import GUELTIGE_UI_STATUS, UI_STATUS

        ungueltig = {k: v for k, v in UI_STATUS.items() if v not in GUELTIGE_UI_STATUS}
        assert ungueltig == {}, f"Unbekannter ui_status: {ungueltig}"

    def test_jeder_typ_hat_einen_status(self):
        from app.context.taxonomy import SCOPE_DEFAULTS, UI_STATUS

        assert set(UI_STATUS) == set(SCOPE_DEFAULTS)

    def test_typen_ohne_erzeugungsweg_ruhen(self):
        from app.context.taxonomy import ist_ruhend

        for ct in (
            "pruefungsanforderung",
            "lernplan",
            "schuelertext",
            "schuelerpraesentation",
            "strukturierung",
            "feedback_text",
        ):
            assert ist_ruhend(ct), f"{ct} sollte ruhen"

    def test_tragende_typen_ruhen_nicht(self):
        from app.context.taxonomy import ist_ruhend

        for ct in ("arbeitsblatt", "ik_kompetenz", "methode", "begriff", "operator"):
            assert not ist_ruhend(ct), f"{ct} darf nicht ruhen"

    def test_unbekannter_typ_ruht_nicht(self):
        from app.context.taxonomy import ist_ruhend

        assert not ist_ruhend(None)
        assert not ist_ruhend("gibt_es_nicht")


class TestScopeKorrekturen:
    """Die Korrekturen aus ADR-019 K3 — je eine bewusste Zuständigkeits-Entscheidung."""

    def test_fachschaftsgut_statt_verwaltung(self):
        """Was fachlich ist, pflegt die Fachschaft, nicht der Schul-Admin."""
        from app.context.taxonomy import get_scope_defaults

        for ct in ("pruefungsanforderung", "konvention", "themengebiet", "funktion", "bauteil"):
            assert get_scope_defaults(ct) == ("school", "subject"), ct

    def test_sozialform_ist_schulweit(self):
        """Geschlossene, fachneutrale Kleinstmenge — keine Fachschafts-Varianten."""
        from app.context.taxonomy import get_scope_defaults

        assert get_scope_defaults("sozialform") == ("school", "school")

    def test_praesentation_ist_lerngruppen_material(self):
        from app.context.taxonomy import get_scope_defaults

        assert get_scope_defaults("praesentation") == ("group", "private")

    def test_neue_schueler_typen_sind_privat(self):
        from app.context.taxonomy import get_scope_defaults

        for ct in ("schuelerpraesentation", "strukturierung"):
            assert get_scope_defaults(ct) == ("private", "private"), ct

    def test_neue_typen_ohne_embedding(self):
        """Ausschlussgrund 3: fremdes Eigentum ohne Suchnutzen."""
        from app.context.taxonomy import EMBEDDING_CONTENT_TYPES

        assert "schuelerpraesentation" not in EMBEDDING_CONTENT_TYPES
        assert "strukturierung" not in EMBEDDING_CONTENT_TYPES
