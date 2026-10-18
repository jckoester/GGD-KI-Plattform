"""Die Beispiel-Assistenten (`config/assistants.example.yaml`) und ihre Prompts.

Der Seed (`scripts/seed_assistants.py`) legt sie auf einer neuen Instanz an. Was hier
schiefgeht, fällt sonst erst im Chat auf: eine Fähigkeit, die der Import verwirft, eine
Prompt-Datei, die fehlt, oder ein Prompt, der ein Werkzeug beim alten Namen ruft.
"""
import re
from pathlib import Path

import pytest
import yaml

import app.chat.router  # noqa: F401 — füllt TOOL_REGISTRY
from app.chat.tools import FAEHIGKEITEN, TOOL_REGISTRY

WURZEL = Path(__file__).resolve().parents[3]
EINTRAEGE = yaml.safe_load((WURZEL / "config" / "assistants.example.yaml").read_text(encoding="utf-8"))["assistants"]


def _eintrag(name):
    return next(e for e in EINTRAEGE if e["name"] == name)


def _prompt(eintrag) -> str:
    return (WURZEL / eintrag["system_prompt_file"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("eintrag", EINTRAEGE, ids=lambda e: e["name"])
def test_faehigkeiten_und_prompt_datei(eintrag):
    assert set(eintrag.get("tool_groups", [])) <= set(FAEHIGKEITEN)
    if "system_prompt_file" in eintrag:
        assert (WURZEL / eintrag["system_prompt_file"]).is_file()


@pytest.mark.parametrize("eintrag", [e for e in EINTRAEGE if "system_prompt_file" in e],
                         ids=lambda e: e["name"])
def test_prompt_nennt_nur_werkzeuge_seiner_faehigkeiten(eintrag):
    """`snake_case` in Backticks, der wie ein Werkzeugname aussieht, muss eines sein — und
    eines, das die Fähigkeiten dieses Assistenten freischalten (oder die Suche, die immer
    greift)."""
    erreichbar = {
        name for name, werkzeug in TOOL_REGISTRY.items()
        if werkzeug.groups & (set(eintrag.get("tool_groups", [])) | {"context_search"})
    }
    genannt = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", _prompt(eintrag)))
    werkzeugnamen = {n for n in genannt if n in TOOL_REGISTRY or n.split("_")[0] in
                     {"get", "update", "create", "set", "assign", "apply", "undo", "finde",
                      "waehle", "search", "list"}}
    assert werkzeugnamen <= erreichbar, sorted(werkzeugnamen - erreichbar)


@pytest.mark.parametrize("datei", sorted((WURZEL / "config" / "prompts").glob("*.md")),
                         ids=lambda p: p.name)
def test_kein_bilanzbeispiel_mit_zahlen(datei):
    """Ein Beispiel mit Zahlen schreibt das Modell als Bilanz ab: „34 Slots bis Februar, 36 Std.
    geplant — 2 Std. Überhang" stand im Jahresplanungs-Prompt und kam in den Entfall-Messungen
    zu 0.15 einmal je Messung als Bilanz einer Gruppe mit 12 Terminen heraus — trotz „Niemals
    selbst rechnen". Platzhalter (X, Y) sind unverdächtig; Ziffern vor „Slots"/„Std." nicht.
    Alle Prompt-Dateien, nicht nur die mit Seed-Eintrag: Den Verschiebe-Assistenten legen
    Admins von Hand aus `verschiebe_assistent.md` an — dort stand „2 von 18 Std."."""
    beispiele = re.findall(r"\d+\s*(?:Slots|Std\.|Stunden)", datei.read_text(encoding="utf-8"))
    assert beispiele == [], beispiele


class TestStundenentwurf:
    """Der schulweite Stundenassistent (0.15, Päckchen A Schritt 6)."""

    def test_eintrag(self):
        e = _eintrag("Stundenentwurf")
        assert e["tool_groups"] == ["lesson_planning"]
        assert e["audience"] == "teacher" and e["status"] == "active"

    def test_prompt_nennt_die_stundenwerkzeuge(self):
        text = _prompt(_eintrag("Stundenentwurf"))
        for werkzeug in ("finde_stunde", "waehle_stunde", "get_lesson_detail",
                         "update_lesson_phases"):
            assert f"`{werkzeug}`" in text, werkzeug
        # Das Vokabular kommt mit dem Entwurf; einzeln nachschlagen kostete die Runden,
        # die zum Schreiben fehlten (Messung 1, 10.10.2026).
        assert "`vokabular`" in text

    def test_vorlage_fuer_eigene_assistenten(self):
        """Der Abschnitt mit den Lücken ist die Vorlage (Plan F6) — und der Prompt sagt, dass
        eine leere Lücke nicht gilt."""
        text = _prompt(_eintrag("Stundenentwurf"))
        abschnitt = text.split("## Meine Planungsgewohnheiten", 1)[1]
        assert abschnitt.count("[…]") >= 4
        assert "gilt nicht" in abschnitt

    def test_genannte_bausteinarten_gibt_es(self):
        """In der Untersuchung „Kompetenz vorschlagen" (10.10.2026) suchte das Modell mit
        einem Typ „kompetenz", den es nicht gibt. Nennt der Prompt eine Bausteinart, muss sie
        existieren — sonst leitet er genau dazu an."""
        from app.context.taxonomy import CONTENT_TYPE_TO_CATEGORY

        text = _prompt(_eintrag("Stundenentwurf"))
        genannt = re.findall(r'`content_type` „([a-z_]+)[“"]', text)
        assert genannt, "der Prompt nennt keine Bausteinart mehr — Test anpassen"
        assert set(genannt) <= set(CONTENT_TYPE_TO_CATEGORY), genannt

    def test_zusammenhang_und_phasenbedeutung(self):
        """Der Entwurf bringt seinen Zusammenhang mit (A1); die Phasen haben eine Aufgabe —
        ohne sie machte das Modell aus „Sicherung" neue Übungsaufgaben (Messung 3)."""
        text = _prompt(_eintrag("Stundenentwurf"))
        assert "`zusammenhang`" in text
        abschnitt = text.split("## Was die Phasen bedeuten", 1)[1].split("\n## ", 1)[0]
        assert "**Sicherung:**" in abschnitt

    def test_fachbegriffe_der_stunde(self):
        """0.17 (A1): `begriffe` kommt mit dem Entwurf, Begriffe stehen als `typ` „concept“ in
        `refs`, ein fehlender wird nicht eingetragen (F6). Seit 0.18 schlägt die Leiste die
        Begriffe vor (eigener Aufruf aus den Phasentexten); der Assistent nennt sie nur noch, wenn
        die Lehrkraft fragt oder sie selbst nennt — der Pflichtabsatz „Begriffe dieser Stunde“
        ist weg (Plan „Begriffe aus den Phasentexten", Schritt 7)."""
        text = _prompt(_eintrag("Stundenentwurf"))
        assert "`begriffe`" in text
        abschnitt = text.split("## Fachbegriffe der Stunde", 1)[1].split("\n## ", 1)[0]
        assert "nicht von dir aus" in abschnitt and "Leiste" in abschnitt
        assert "Begriffe dieser Stunde" not in text
        # F1 (Jan, 18.10.2026): frühere Begriffe sind eine Planungshilfe, kein Lernstand.
        assert "`begriffe_frueherer_stunden`" in text and "kein Lernstand" in text
        # Fragt die Lehrkraft: Phase für Phase, auch unveränderte Phasen (0.17, Fables Fassung).
        assert "Phase für Phase" in abschnitt
        assert "auch für die Phasen, die du nicht änderst" in abschnitt
        # Messung 5 (0.17): Nachschlagen kostete die Runden — die Suche nur noch als Verbot.
        assert abschnitt.count("`search_context_nodes`") == abschnitt.count("kein `search_context_nodes`")
        assert "`update_lesson_phases` prüft" in abschnitt
        assert "Fachschaft" in abschnitt and "fehlen" in abschnitt
        assert "`nicht_eingetragen`" in abschnitt
        assert "unter `aliase`" in abschnitt
        refs_regel = next(z for z in text.splitlines() if z.startswith("- `refs` schreibst du"))
        assert "concept" in refs_regel and "`titel`" in refs_regel
        schritt3 = text.split("**Schritt 3", 1)[1].split("**Schritt 4", 1)[0]
        assert "nicht von dir aus" in schritt3
        # Messung 2 (0.17): Die Zustimmung galt dem Modell nur für die Phasen.
        schritt5 = text.split("**Schritt 5", 1)[1].split("\n## ", 1)[0]
        assert "gilt die Zustimmung auch für sie" in schritt5
        # Messung 9 und 11 (0.17): gegen `eingetragen` prüfen, jeden Namen einzeln schicken.
        assert "unter `eingetragen` bestätigt" in schritt5
        assert "jeden genannten Namen als eigenen Eintrag" in schritt5
