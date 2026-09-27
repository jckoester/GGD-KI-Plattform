"""Unit-Tests für app.pedagogy.compose (Phase 13, Schritt 3)."""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.pedagogy.compose import compose_system_content, is_student_treatment
from app.pedagogy.config import invalidate_pedagogy_cache, load_pedagogy


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_pedagogy_cache()
    yield
    invalidate_pedagogy_cache()


# ---------- is_student_treatment (D1-Matrix) ----------

@pytest.mark.parametrize(
    "audience,user_is_student,expected",
    [
        ("student", False, True),   # Test-Chat Lehrkraft an Schüler-Assistent → Schüler
        ("student", True, True),
        ("teacher", True, False),
        ("teacher", False, False),
        ("all", True, True),        # Schüler:in an all-Assistent → Schüler
        ("all", False, False),      # Lehrkraft an all-Assistent → Lehrkraft
        (None, True, True),         # kein Assistent → nach Rolle
        (None, False, False),
    ],
)
def test_is_student_treatment(audience, user_is_student, expected):
    assert is_student_treatment(audience, user_is_student) is expected


# ---------- compose_system_content ----------

def _ped():
    return load_pedagogy()


def _aug(key: str) -> str:
    """Text einer Lernverhalten-Augmentierung über ihren **Schlüssel**.

    ⚠️ **Die Formulierung nicht festnageln.** Bis zum 26.09.2026 prüften zwei Tests
    hier auf die Wendung „zum Ergebnis kommt". Sie fielen um, als N8 die Texte neu
    fasste — obwohl am geprüften Verhalten nichts falsch war. Zugesagt ist der
    Schlüssel (`disabled_augmentations` in der Datenbank nennt genau ihn), nicht der
    Wortlaut; den ändert die Redaktion.
    """
    return next(a.text for a in load_pedagogy().student_augmentations if a.key == key)


def test_student_treatment_includes_extension_and_augmentations():
    out = compose_system_content(
        _ped(), student_treatment=True, context_str=None, assistant_system_prompt="SP"
    )
    assert "Lernassistent" in out          # student_extension
    assert "Lehrkräfte" not in out         # KEINE teacher_extension
    assert _aug("no_complete_homework_solutions") in out
    assert "SP" in out


def test_teacher_treatment_has_no_augmentations():
    out = compose_system_content(
        _ped(), student_treatment=False, context_str=None, assistant_system_prompt="SP"
    )
    assert "Lehrkräfte" in out             # teacher_extension
    assert "Lernassistent" not in out
    assert _aug("no_complete_homework_solutions") not in out


def test_universal_base_always_present():
    for treat in (True, False):
        out = compose_system_content(
            _ped(), student_treatment=treat, context_str=None, assistant_system_prompt=None
        )
        assert "schulischen Umfeld" in out  # aus universal_base


def test_context_and_prompt_joined_with_separator():
    out = compose_system_content(
        _ped(), student_treatment=False, context_str="KTX", assistant_system_prompt="SP"
    )
    assert "KTX\n\n---\n\nSP" in out


def test_context_only():
    out = compose_system_content(
        _ped(), student_treatment=False, context_str="KTX", assistant_system_prompt=None
    )
    assert "KTX" in out
    assert "---" not in out


def test_neither_context_nor_prompt_is_just_preamble():
    out = compose_system_content(
        _ped(), student_treatment=True, context_str=None, assistant_system_prompt=None
    )
    assert "schulischen Umfeld" in out
    assert "---" not in out


def test_disabled_augmentation_excluded():
    out = compose_system_content(
        _ped(),
        student_treatment=True,
        context_str=None,
        assistant_system_prompt="SP",
        disabled_augmentations=["no_complete_homework_solutions"],
    )
    assert _aug("no_complete_homework_solutions") not in out   # deaktiviert
    assert _aug("socratic_preference") in out                  # bleibt aktiv


def test_output_format_not_in_compose():
    # output_format hängt der Aufrufer separat an, nicht compose_system_content
    out = compose_system_content(
        _ped(), student_treatment=True, context_str=None, assistant_system_prompt="SP"
    )
    assert "Markdown gerendert" not in out


class TestKlassenstufeImSystemkontext:
    """Die eine Zeile zur Klassenstufe (Paket 9, N5).

    ⚠️ **Sie steht vor dem Kontext, nicht darin.** Die Stufe gilt für die ganze
    Antwort, auch wenn die Suche nichts gefunden hat — läge sie im Kontextblock,
    verschwände sie genau dann, wenn das Modell ohnehin aus eigenem Wissen antwortet.
    """

    def _inhalt(self, **kwargs):
        from app.pedagogy.compose import compose_system_content
        from app.pedagogy.config import load_pedagogy

        vorgaben = dict(
            student_treatment=True, context_str=None, assistant_system_prompt=None
        )
        return compose_system_content(load_pedagogy(), **{**vorgaben, **kwargs})

    def test_stufe_steht_drin(self):
        assert "Klasse 9" in self._inhalt(stufe=9)

    def test_regel_steht_daneben(self):
        """Ohne sie ist die Stufe eine Angabe ohne Auftrag: Das Modell weiß, in welcher
        Klasse jemand ist, und antwortet trotzdem auf Kursstufenniveau."""
        from app.pedagogy.compose import STUFEN_REGEL

        assert STUFEN_REGEL in self._inhalt(stufe=9)

    def test_ohne_stufe_keine_zeile(self):
        assert "Klasse" not in self._inhalt(stufe=None).split("Wissens")[0][-400:]

    def test_lehrkraefte_bekommen_keine_stufe(self):
        """Eine Lehrkraft, die den Unterricht einer neunten Klasse vorbereitet, braucht
        alle Fassungen ohne Zurückhaltung — sie entscheidet, was in die Stunde gehört."""
        inhalt = self._inhalt(student_treatment=False, stufe=9)
        assert "Die fragende Person ist in Klasse" not in inhalt

    def test_stufe_vor_dem_kontext(self):
        inhalt = self._inhalt(stufe=9, context_str="## Relevante Lerninhalte\n\nX")
        assert inhalt.index("Klasse 9") < inhalt.index("Relevante Lerninhalte")
