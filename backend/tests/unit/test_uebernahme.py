"""Die Regeln der Artefakt-Übernahme (AP8, Schritt 1) — ohne Datenbank.

Geprüft wird, was sich ohne Bestand entscheiden lässt: welche Artefaktart taugt, welche
Bausteinart welche Rolle wählen darf, was aus dem Quelltext wird, und dass die
Typen-Listen die Taxonomie vollständig abdecken. Die Fassungskette (`supersedes`) braucht
echte Zeilen und steht in `tests/integration/test_uebernahme.py`.
"""
from types import SimpleNamespace

import pytest

from app.artifacts import uebernahme
from app.context.taxonomy import CONTENT_TYPE_TO_CATEGORY, RUHENDE_CONTENT_TYPES


def _artefakt(kind="document", source="# Titel\n\nText."):
    return SimpleNamespace(kind=kind, source=source, title="Artefakt", id="a-1")


LEHRKRAFT = ["teacher"]
ADMIN = ["admin"]
SCHUELER = ["student"]


class TestRollen:
    def test_admin_zaehlt_als_lehrkraft(self):
        """CLAUDE.md: Admin ist eine Erweiterung der Lehrkraft, kein eigener Nutzertyp."""
        assert uebernahme.ist_lehrkraft(ADMIN)
        assert uebernahme.angebotene_typen(ADMIN) == uebernahme.angebotene_typen(LEHRKRAFT)

    def test_schueler_bekommt_erzwungene_scopes(self):
        assert uebernahme.erzwungene_scopes(SCHUELER) == ("private", "private")

    def test_lehrkraft_waehlt_die_sichtbarkeit_selbst(self):
        assert uebernahme.erzwungene_scopes(LEHRKRAFT) is None


class TestAngeboteneTypen:
    def test_ruhende_arten_werden_nicht_angeboten(self):
        """Sonst wäre `ui_status: ruhend` eine Behauptung, die die Übernahme unterläuft."""
        for rolle in (LEHRKRAFT, SCHUELER):
            angeboten = set(uebernahme.angebotene_typen(rolle))
            assert not (angeboten & RUHENDE_CONTENT_TYPES)

    def test_schueler_bekommen_keine_lehrkraft_arten(self):
        angeboten = set(uebernahme.angebotene_typen(SCHUELER))
        assert "arbeitsblatt" not in angeboten
        assert "klausur" not in angeboten

    def test_listen_decken_die_taxonomie_ab(self):
        """Wächter: Ein neuer Dokument-/Artefakt-Typ zwingt zur Entscheidung.

        Ohne diese Prüfung fiele er stillschweigend aus der Übernahme heraus — nicht als
        Ablehnung, sondern als Lücke, die niemandem auffiele.
        """
        alle = {
            key for key, cat in CONTENT_TYPE_TO_CATEGORY.items()
            if cat in ("document", "artifact")
        }
        eingeordnet = (
            set(uebernahme.LEHRKRAFT_TYPEN)
            | set(uebernahme.SCHUELER_TYPEN)
            | set(uebernahme.NICHT_UEBERNEHMBAR)
        )
        assert alle - eingeordnet == set(), (
            "Bausteinart weder in LEHRKRAFT_TYPEN/SCHUELER_TYPEN noch in "
            "NICHT_UEBERNEHMBAR — Entscheidung fehlt (app/artifacts/uebernahme.py)"
        )
        assert eingeordnet - alle == set(), "Unbekannte Bausteinart in den Listen"

    def test_uebernehmbar_und_abgelehnt_schliessen_sich_aus(self):
        anbietbar = set(uebernahme.LEHRKRAFT_TYPEN) | set(uebernahme.SCHUELER_TYPEN)
        assert not (anbietbar & set(uebernahme.NICHT_UEBERNEHMBAR))

    def test_jede_ablehnung_nennt_einen_grund(self):
        for typ, grund in uebernahme.NICHT_UEBERNEHMBAR.items():
            assert grund.strip(), f"{typ} ohne Begründung"


class TestInhalt:
    def test_dokument_wandert_unveraendert(self):
        assert uebernahme.inhalt_aus_artefakt(_artefakt()) == "# Titel\n\nText."

    def test_mermaid_bekommt_seinen_zaun(self):
        """Ohne den Zaun stünde in der Knotenansicht Code statt eines Diagramms."""
        inhalt = uebernahme.inhalt_aus_artefakt(
            _artefakt(kind="mermaid", source="graph TD; A-->B;")
        )
        assert inhalt == "```mermaid\ngraph TD; A-->B;\n```"

    def test_leeres_artefakt_wird_abgewiesen(self):
        with pytest.raises(uebernahme.UebernahmeFehler):
            uebernahme.inhalt_aus_artefakt(_artefakt(source="   \n "))


class TestPruefung:
    @pytest.mark.parametrize("kind", ["image", "circuit", "plot", "ggb"])
    def test_nicht_textliche_artefakte_werden_abgewiesen(self, kind):
        with pytest.raises(uebernahme.UebernahmeFehler, match="Dokumente und Mermaid"):
            uebernahme.pruefe(_artefakt(kind=kind), "arbeitsblatt", LEHRKRAFT)

    def test_dokument_und_mermaid_gehen_durch(self):
        for kind in ("document", "mermaid"):
            uebernahme.pruefe(_artefakt(kind=kind), "arbeitsblatt", LEHRKRAFT)

    def test_fremde_bausteinart_wird_abgewiesen(self):
        """Eine Unterrichtsstunde entsteht im Planer, nicht aus einem Chat-Dokument."""
        with pytest.raises(uebernahme.UebernahmeFehler):
            uebernahme.pruefe(_artefakt(), "unterrichtsstunde", LEHRKRAFT)

    def test_schueler_kommt_nicht_an_lehrkraft_arten(self):
        with pytest.raises(uebernahme.UebernahmeFehler):
            uebernahme.pruefe(_artefakt(), "arbeitsblatt", SCHUELER)


class TestVorgabeScopes:
    def test_vorgabe_kommt_aus_der_taxonomie(self):
        assert uebernahme.vorgabe_scopes("arbeitsblatt") == ("group", "private")
        assert uebernahme.vorgabe_scopes("klausur") == ("private", "private")

    def test_jede_angebotene_art_hat_eine_kategorie(self):
        """`uebernimm` schlägt die Kategorie über CONTENT_TYPE_TO_CATEGORY nach —
        ein fehlender Eintrag wäre dort ein KeyError mitten im Anlegen."""
        for typ in uebernahme.LEHRKRAFT_TYPEN + uebernahme.SCHUELER_TYPEN:
            assert typ in CONTENT_TYPE_TO_CATEGORY
