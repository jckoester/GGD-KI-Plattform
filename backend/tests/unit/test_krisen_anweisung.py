"""Die Anweisung bei einem Krisentreffer (Paket 1 von 0.12, AP3).

Bis 0.12 erzeugte ein Treffer Banner, Flag und Benachrichtigung — die **Antwort** blieb
unberührt. Was das Modell sagt, hing allein an Punkt 3 der Präambel; dieselbe
Konstruktion wurde bei den Hausversuchen (Punkt 8) gemessen in 18 von 20 Läufen
überlesen.
"""

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")

from app.crisis.anweisung import STANDARD, anweisung_fuer
from app.crisis.detector import CrisisHit


def _treffer(anweisung=None) -> CrisisHit:
    return CrisisHit(
        category="letalitaet",
        severity="alert",
        help_topic="crisis",
        trigger_rule="crisis_triggers:letalitaet",
        coreviewer_role="review",
        anweisung=anweisung,
    )


class TestWelcherText:
    def test_ohne_eigenen_text_gilt_der_standard(self):
        assert anweisung_fuer(_treffer()) == STANDARD

    def test_eigener_text_der_kategorie_gewinnt(self):
        assert anweisung_fuer(_treffer("Sag bitte nichts dazu.")) == "Sag bitte nichts dazu."

    @pytest.mark.parametrize("leer", ["", "   ", "\n\t "])
    def test_leerer_eigener_text_faellt_auf_den_standard_zurueck(self, leer):
        """Ein versehentlich leeres `anweisung:` darf die Anweisung nicht abschalten."""
        assert anweisung_fuer(_treffer(leer)) == STANDARD


class TestStandardtext:
    """Er wird mit dem Update **ohne Zutun der Schule** aktiv (E4) und muss deshalb
    ohne schulspezifische Abstimmung vertretbar sein."""

    @pytest.mark.parametrize("zusage", [
        "Mengen",       # keine Mengen, Mittel, Methoden
        "Methoden",
        "Diagnose",     # keine Ferndiagnose
        "frage, wie es ihr geht",
    ])
    def test_nennt_seine_grenzen(self, zusage):
        assert zusage in STANDARD

    def test_verbietet_erfundene_kontaktdaten(self):
        """Eine halluzinierte Hotline ist in dieser Lage der schlechteste Fehler."""
        assert "erfinde" in STANDARD.lower()
        assert "Telefonnummern" in STANDARD

    @pytest.mark.parametrize("verweis", ["unter dieser Nachricht", "eingeblendet", "unten"])
    def test_verweist_nicht_auf_das_banner(self, verweis):
        """Das Hilfe-Banner erscheint nur beim **ersten** Treffer einer Kategorie je
        Konversation (`show_banner`). Ein Verweis darauf wäre ab dem zweiten Treffer
        falsch — und das Modell soll nicht behaupten, was nicht da ist."""
        assert verweis not in STANDARD


class TestStellungImSystemtext:
    """Wächter auf der Quelle: Die Reihenfolge der Systemnachrichten ist die halbe
    Zusage von AP3, und es gibt (noch) keinen Prüfstand für den Chat-Endpunkt.

    ⚠️ Das prüft die **Stellung im Quelltext**, nicht die ausgehende Nutzlast. Ein
    echter Test bräuchte einen Prüfstand für `chat()` mit Datenbank, Auth und
    LiteLLM-Attrappe — den gibt es im Projekt nirgends, und für dieses Paket wäre er
    unverhältnismäßig. Als Todo notiert.
    """

    @pytest.fixture(scope="class")
    def quelle(self) -> str:
        pfad = Path(__file__).resolve().parents[2] / "app" / "chat" / "router.py"
        return pfad.read_text(encoding="utf-8")

    def _pos(self, quelle: str, muster: str) -> int:
        treffer = re.search(muster, quelle)
        assert treffer, f"Ankerpunkt nicht gefunden: {muster}"
        return treffer.start()

    def test_krisen_anweisung_steht_nach_der_hausversuchs_anweisung(self, quelle):
        n12 = self._pos(quelle, r"hausversuch_anweisung\(gefahr\)")
        krise = self._pos(quelle, r"krisen_anweisung\(crisis_hit\)")
        assert krise > n12, (
            "Greifen beide (Dosisfrage mit Personenbezug), soll die Krisen-Anweisung "
            "die äußere sein."
        )

    def test_beide_stehen_vor_den_nachrichten_der_konversation(self, quelle):
        krise = self._pos(quelle, r"krisen_anweisung\(crisis_hit\)")
        gespraech = self._pos(quelle, r"llm_messages\.extend\(")
        assert krise < gespraech, "Systemnachrichten gehören vor den Gesprächsverlauf."

    def test_testchats_bekommen_die_anweisung_trotzdem(self, quelle):
        """Sie werden nicht geflaggt — sonst wäre das Verhalten nur prüfbar, indem man
        einen echten Fall in der Einsicht zu zweit erzeugt (AP4)."""
        block = re.search(
            r"if not conversation_is_test:(?:.|\n)*?else:(?:.|\n)*?crisis_hit = scan\(",
            quelle,
        )
        assert block, "Im Test-Chat-Zweig wird nicht gescannt"

    def test_die_anweisung_haengt_nicht_an_der_schuelerbehandlung(self, quelle):
        """E2: Eine Notlage kennt keine Rolle — anders als N12."""
        ausschnitt = quelle[self._pos(quelle, r"if crisis_hit is not None:"):][:400]
        assert "student_treatment" not in ausschnitt


class TestWegVonDerKonfigurationZumTreffer:
    """Die Lücke zwischen `anweisung:` in der YAML und dem Text an der Antwort.

    Ohne diesen Test prüfte alles oben nur `CrisisHit`-Objekte, die der Test selbst
    gebaut hat — ob `scan()` das Feld überhaupt weiterreicht, stünde nirgends.
    """

    def test_scan_reicht_den_eigenen_text_durch(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.crisis.config import invalidate_crisis_cache
        from app.crisis.detector import scan

        datei = tmp_path / "crisis_triggers.yaml"
        datei.write_text(
            "triggers:\n"
            "  - category: testfall\n"
            "    severity: alert\n"
            "    help_topic: crisis\n"
            "    anweisung: Antworte besonders behutsam.\n"
            "    patterns:\n"
            '      - "zauberwort"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(settings, "crisis_triggers_path", str(datei))
        invalidate_crisis_cache()
        try:
            hit = scan("hier steht das zauberwort")
            assert hit is not None
            assert anweisung_fuer(hit) == "Antworte besonders behutsam."
        finally:
            invalidate_crisis_cache()

    def test_ohne_feld_kommt_der_standard_an(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.crisis.config import invalidate_crisis_cache
        from app.crisis.detector import scan

        datei = tmp_path / "crisis_triggers.yaml"
        datei.write_text(
            "triggers:\n"
            "  - category: testfall\n"
            "    severity: alert\n"
            "    help_topic: crisis\n"
            "    patterns:\n"
            '      - "zauberwort"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(settings, "crisis_triggers_path", str(datei))
        invalidate_crisis_cache()
        try:
            assert anweisung_fuer(scan("zauberwort")) == STANDARD
        finally:
            invalidate_crisis_cache()
