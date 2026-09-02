"""Unit-Tests für die Taxonomie-Startprüfung (ADR-018, AP1).

Der Normalfall — das Repository, so wie es ist — muss **still** sein: Findet die
Prüfung hier etwas, startet das Backend nicht. Alle übrigen Tests führen je eine Drift
künstlich herbei und verlangen, dass sie benannt wird.
"""

import pytest

from app.context import taxonomy
from app.context.taxonomy_check import (
    TaxonomieFehler,
    pruefe_altlast,
    pruefe_bestand,
    pruefe_beim_start,
    pruefe_taxonomie,
)


class _FakeErgebnis:
    def __init__(self, zeilen):
        self._zeilen = zeilen

    def all(self):
        return self._zeilen


class _FakeSession:
    """Minimale Session-Attrappe — die Prüfung braucht nur `execute(...).all()`."""

    def __init__(self, zeilen=(), fehler=None):
        self._zeilen = list(zeilen)
        self._fehler = fehler

    async def __aenter__(self):
        if self._fehler:
            raise self._fehler
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return _FakeErgebnis(self._zeilen)


def _factory(zeilen=(), fehler=None):
    return lambda: _FakeSession(zeilen, fehler)


# ── Normalfall ────────────────────────────────────────────────────────────────

class TestNormalfall:

    def test_repository_ist_konsistent(self):
        """Der ausgelieferte Stand darf keinen Befund erzeugen."""
        assert pruefe_taxonomie() == []

    async def test_start_mit_bekannten_typen_laeuft_durch(self):
        zeilen = [("knowledge", "operator", 1553), ("artifact", "arbeitsblatt", 3)]
        await pruefe_beim_start(_factory(zeilen))  # kein Fehler

    async def test_strukturelle_knoten_ohne_typ_sind_erlaubt(self):
        await pruefe_beim_start(_factory([("knowledge", None, 7)]))


# ── (a) Bestand gegen Taxonomie ───────────────────────────────────────────────

class TestBestand:

    def test_unbekannter_typ_wird_benannt(self):
        befunde = pruefe_bestand([("artifact", "aufgabenblatt_alt", 42)])
        assert len(befunde) == 1
        assert "aufgabenblatt_alt" in befunde[0]
        assert "42" in befunde[0]
        assert "alembic upgrade head" in befunde[0]

    def test_typ_in_falscher_kategorie(self):
        befunde = pruefe_bestand([("document", "operator", 5)])
        assert len(befunde) == 1
        assert "operator" in befunde[0] and "knowledge" in befunde[0]

    def test_bekannte_kombination_ist_still(self):
        assert pruefe_bestand([("knowledge", "operator", 1)]) == []

    async def test_unbekannter_typ_verhindert_den_start(self):
        with pytest.raises(TaxonomieFehler, match="aufgabenblatt_alt"):
            await pruefe_beim_start(_factory([("artifact", "aufgabenblatt_alt", 1)]))

    async def test_unlesbare_datenbank_ist_kein_fehler(self, caplog):
        """Frische Installation vor der ersten Migration — keine Abweichung, nur offen."""
        await pruefe_beim_start(_factory(fehler=RuntimeError("relation does not exist")))
        assert "nicht prüfbar" in caplog.text


# ── (b) Taxonomie gegen die Handtabellen ──────────────────────────────────────

class TestLookupDrift:

    def test_fehlender_lifecycle_eintrag(self, monkeypatch):
        gekuerzt = dict(taxonomy.VALID_UNTIL_DEFAULTS_DAYS)
        gekuerzt.pop("operator")
        monkeypatch.setattr(taxonomy, "VALID_UNTIL_DEFAULTS_DAYS", gekuerzt)

        befunde = pruefe_taxonomie()
        assert any("operator" in b and "läuft nie ab" in b for b in befunde)

    def test_lifecycle_karteileiche(self, monkeypatch):
        erweitert = dict(taxonomy.VALID_UNTIL_DEFAULTS_DAYS, laengst_weg=None)
        monkeypatch.setattr(taxonomy, "VALID_UNTIL_DEFAULTS_DAYS", erweitert)

        assert any("laengst_weg" in b for b in pruefe_taxonomie())

    def test_rollenbonus_auf_unbekanntem_typ(self, monkeypatch):
        monkeypatch.setattr(
            taxonomy, "ROLLEN_TYP_BONUS", {"student": {"gibt_es_nicht": 0.02}}
        )
        befunde = pruefe_taxonomie()
        assert any("gibt_es_nicht" in b and "ins Leere" in b for b in befunde)

    def test_doppelt_vergebener_content_type(self, monkeypatch):
        doppelt = {
            cat: list(keys) for cat, keys in taxonomy.VALID_CONTENT_TYPES.items()
        }
        doppelt["document"] = doppelt["document"] + ["operator"]
        monkeypatch.setattr(taxonomy, "VALID_CONTENT_TYPES", doppelt)

        assert any("doppelt vergeben" in b and "operator" in b for b in pruefe_taxonomie())

    def test_write_scope_weiter_als_read_scope(self, monkeypatch):
        verdreht = dict(taxonomy.SCOPE_DEFAULTS, klausur=("private", "school"))
        monkeypatch.setattr(taxonomy, "SCOPE_DEFAULTS", verdreht)

        assert any("reicht weiter als" in b for b in pruefe_taxonomie())

    def test_unbekannter_scope_wert(self, monkeypatch):
        falsch = dict(taxonomy.SCOPE_DEFAULTS, klausur=("weltweit", "private"))
        monkeypatch.setattr(taxonomy, "SCOPE_DEFAULTS", falsch)

        assert any("unbekannte Scope-Werte" in b for b in pruefe_taxonomie())

    def test_embedding_input_ohne_embedding(self, monkeypatch):
        """Ein Vektor-Input für einen Typ, der nie eingebettet wird, ist tote Konfig."""
        ohne = frozenset(taxonomy.EMBEDDING_CONTENT_TYPES - {"unterrichtsstunde"})
        monkeypatch.setattr(taxonomy, "EMBEDDING_CONTENT_TYPES", ohne)

        befunde = pruefe_taxonomie()
        assert any("embedding_input" in b and "unterrichtsstunde" in b for b in befunde)

    def test_bp_curriculum_liste_mit_unbekanntem_typ(self, monkeypatch):
        monkeypatch.setattr(
            taxonomy, "BP_CURRICULUM_CONTENT_TYPES", ("curriculum", "gibt_es_nicht")
        )
        assert any("gibt_es_nicht" in b for b in pruefe_taxonomie())

    def test_ankerliste_darf_nicht_wieder_auseinanderlaufen(self, monkeypatch):
        """Genau die Drift, die AP1 vorgefunden hat: drei Listen, zwei Meinungen."""
        from app.context import retrieval

        monkeypatch.setattr(
            retrieval,
            "VALID_SCOPE_ANCHOR_TYPES",
            frozenset(taxonomy.VALID_SCOPE_ANCHOR_TYPES - {"kapitel"}),
        )
        befunde = pruefe_taxonomie()
        assert any("retrieval_scope-Anker weichen" in b and "kapitel" in b for b in befunde)

    async def test_drift_verhindert_den_start(self, monkeypatch):
        gekuerzt = dict(taxonomy.VALID_UNTIL_DEFAULTS_DAYS)
        gekuerzt.pop("operator")
        monkeypatch.setattr(taxonomy, "VALID_UNTIL_DEFAULTS_DAYS", gekuerzt)

        with pytest.raises(TaxonomieFehler, match="ADR-018"):
            await pruefe_beim_start(_factory())


class TestAltlast:
    """Die zurückgebliebene `config/taxonomy.yaml` einer Bestandsinstallation.

    Sie ist nach dem Umzug (02.09.2026) wirkungslos, sieht aber gültig aus — und liegt
    genau dort, wo die Admin-Doku zum Bearbeiten einlädt. Ein Hinweis, kein Fehler.
    """

    def test_ohne_altlast_still(self):
        assert pruefe_altlast() is None

    def test_altlast_wird_gemeldet(self, tmp_path, monkeypatch):
        from app.context import taxonomy_check

        alt = tmp_path / "config" / "taxonomy.yaml"
        alt.parent.mkdir()
        alt.write_text("categories: {}\n", encoding="utf-8")
        monkeypatch.setattr(
            "app.core.paths.aufloesen", lambda pfad: tmp_path / pfad, raising=True
        )

        meldung = taxonomy_check.pruefe_altlast()
        assert meldung is not None
        assert "Altlast" in meldung and str(alt) in meldung

    async def test_altlast_verhindert_den_start_nicht(self, tmp_path, monkeypatch, caplog):
        alt = tmp_path / "config" / "taxonomy.yaml"
        alt.parent.mkdir()
        alt.write_text("categories: {}\n", encoding="utf-8")
        monkeypatch.setattr("app.core.paths.aufloesen", lambda pfad: tmp_path / pfad)

        await pruefe_beim_start(_factory())  # kein Fehler
        assert "Altlast" in caplog.text


class TestFrontendAbleitung:
    """`frontend/src/lib/taxonomy.js` ist generiert — und kann veralten.

    Die Startprüfung sieht die Datei nicht: Sie liegt im Frontend und wird beim Build
    erzeugt (`npm run prebuild`). Wer die YAML ändert und den Lauf vergisst, bekommt
    eine Oberfläche mit der alten Typenliste — Labels fehlen, Filter zeigen zu viel
    oder zu wenig, und nichts davon meldet sich. Deshalb hier.
    """

    def _generator(self):
        # Über den Dateipfad laden, nicht `from scripts.… import`: `backend/scripts/`
        # und `scripts/` heißen beide `scripts` (siehe CLAUDE.md).
        import importlib.util
        from pathlib import Path

        wurzel = Path(__file__).resolve().parents[3]
        pfad = wurzel / "scripts" / "generate_taxonomy.py"
        spec = importlib.util.spec_from_file_location("_generate_taxonomy", pfad)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul, wurzel

    def test_taxonomy_js_ist_aktuell(self, tmp_path, monkeypatch):
        modul, wurzel = self._generator()
        erzeugt = tmp_path / "taxonomy.js"
        monkeypatch.setattr(modul, "OUT_PATH", erzeugt)
        modul.main()

        im_repo = (wurzel / "frontend" / "src" / "lib" / "taxonomy.js").read_text(
            encoding="utf-8"
        )
        assert erzeugt.read_text(encoding="utf-8") == im_repo, (
            "frontend/src/lib/taxonomy.js passt nicht zu app/context/taxonomy.yaml. "
            "Neu erzeugen: python scripts/generate_taxonomy.py"
        )
