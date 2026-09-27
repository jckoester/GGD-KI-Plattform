"""Was ein Treffer dem Modell über sich sagt (app/context/modellsicht.py).

Übrig ist ein Weg: der **Text ans Modell**. Er trug bis 08/2026 ausschließlich Titel,
womit jede Frage nach dem *Inhalt* des Wissensgraphen unbeantwortbar war.

Der zweite Weg — die Vorschlagsliste im Chat (SSE `context_suggestions`) — ist mit
ADR-017/AP1 entfallen. Die Form**prüfung**, die er brauchte, ist damit ebenfalls weg;
`fuer_modell` prüft ohnehin je Eintrag und reicht fremde Formen durch (siehe
``TestFuerModell``). Genau daran war der Stream einmal abgerissen: Die Gruppe
`context_search` enthält auch `get_operatoren`, dessen Einträge `operator`/`afb`/
`bedeutung` tragen und keinen `title`.
"""

# ⚠️ **Seit 26.09.2026 nicht mehr aus `app.chat.router`.** Die Auswahl gilt für zwei
# Wege — das Werkzeug und die Vorab-Suche (N11) — und liegt deshalb im Kontextpaket.
from app.context.modellsicht import (
    INHALT_MAX_ZEICHEN,
    INHALT_MAX_ZEICHEN_ABSCHNITTE,
    abbildungen_aufgeloest,
    fuer_modell,
    ohne_svg,
)


def _knoten(**felder):
    return {"node_id": "abc", "title": "Titel", "category": "knowledge",
            "content_type": "ik_kompetenz", "subject_id": 13, "fach": "Mathematik",
            **felder}


class TestFuerModell:
    def test_inhalt_geht_mit(self):
        """Der Kern der Sache: ohne Inhalt kann das Modell die Knoten nicht lesen."""
        [e] = fuer_modell([_knoten(content="Fläche und Umfang eines Kreises")])
        assert e["content"] == "Fläche und Umfang eines Kreises"

    def test_node_id_bleibt_draussen(self):
        """Sie nützt dem Modell nichts und landet sonst in der Antwort."""
        [e] = fuer_modell([_knoten(content="x")])
        assert "node_id" not in e and e["title"] == "Titel"

    def test_langer_inhalt_wird_gekuerzt(self):
        [e] = fuer_modell([_knoten(content="A" * (INHALT_MAX_ZEICHEN + 500))])
        assert len(e["content"]) == INHALT_MAX_ZEICHEN + 2
        assert e["content"].endswith(" …")

    def test_leerer_inhalt_erzeugt_kein_feld(self):
        [e] = fuer_modell([_knoten(content=None)])
        assert "content" not in e

    def test_fach_statt_interner_id(self):
        """Das Modell braucht den Fachnamen, nicht `subject_id`.

        Mit `subject_id: 13` konnte ein Modell die Frage „… in den verschiedenen Fächern"
        nicht beantworten und meldete, es gebe keine Einträge je Fach — obwohl die
        Treffer stimmten.
        """
        [e] = fuer_modell([_knoten()])
        assert e["fach"] == "Mathematik"
        assert "subject_id" not in e

    def test_knoten_ohne_fach_bekommt_kein_feld(self):
        """Leitperspektiven tragen kein Fach — dann steht dort auch nichts."""
        [e] = fuer_modell([_knoten(fach=None, subject_id=None)])
        assert "fach" not in e and "subject_id" not in e

    def test_fremde_form_wird_durchgereicht(self):
        """Operatoren behalten ihre Felder — sonst verlöre das Modell die Definition.

        Zugleich der Beleg, dass es keine vorgeschaltete Formprüfung braucht: Die
        Unterscheidung fällt je Eintrag, nicht für die Liste als Ganzes.
        """
        eintrag = {"operator": "nennen", "afb": "I", "bedeutung": "knapp anführen"}
        assert fuer_modell([eintrag]) == [eintrag]

    def test_gemischte_liste(self):
        """Knoten und fremde Form nebeneinander — beide überstehen die Aufbereitung."""
        fremd = {"operator": "nennen", "afb": "I"}
        knoten, durchgereicht = fuer_modell([_knoten(content="x"), fremd])
        assert durchgereicht == fremd
        assert knoten["title"] == "Titel" and "node_id" not in knoten

    def test_hinweis_dict_wird_nicht_angefasst(self):
        """`get_operatoren` ohne Fachbezug liefert einen Hinweis statt einer Liste."""
        assert fuer_modell([{"hinweis": "kein Fachbezug"}]) == [{"hinweis": "kein Fachbezug"}]


class TestErgebnisUmfangFuersLog:
    """Die Logzeile sagt, **welches** Werkzeug lief und wie viel es lieferte — nie *was*.

    Ein Werkzeug-Ergebnis kann Knoteninhalte tragen, und die Argumente enthalten den
    Suchtext der Nutzer:in. Beides gehört nicht ins Log: Logs unterliegen anderen
    Aufbewahrungsregeln als die Konversation, und der Suchtext ist genau die Eingabe, vor
    deren unbedachter Weitergabe die PII-Warnung schützt.
    """

    def test_liste_nennt_nur_die_anzahl(self):
        from app.chat.router import _ergebnis_umfang

        assert _ergebnis_umfang([_knoten(content="geheim"), _knoten()]) == "2 Einträge"

    def test_dict_nennt_nur_die_feldnamen(self):
        from app.chat.router import _ergebnis_umfang

        assert _ergebnis_umfang({"hinweis": "kein Fachbezug"}) == "Felder ['hinweis']"

    def test_kein_inhalt_im_logtext(self):
        """Gegenprobe: Nichts vom Ergebnis darf durchsickern."""
        from app.chat.router import _ergebnis_umfang

        text = _ergebnis_umfang([_knoten(title="Streng geheim", content="auch geheim")])
        assert "geheim" not in text.lower()

    def test_unerwartete_form_stuerzt_nicht_ab(self):
        from app.chat.router import _ergebnis_umfang

        assert _ergebnis_umfang(None) == "NoneType"


class TestOhneSvg:
    """Der SVG-Filter (Paket 9, AP3).

    ⚠️ **Warum überhaupt.** Eine Strukturformel liegt als SVG **inline** im Metadata
    (Muster `schaltzeichen`, Entscheidung E5) — im Pilot bis 47 kB je Bild. Ginge sie
    mit, stünde in einem Suchergebnis mehr Grafikmarkup als Unterrichtsinhalt, und das
    Modell könnte damit nichts anfangen: Was das Bild zeigt, steht daneben in
    `beschreibung`.
    """

    def test_svg_faellt_weg_beschreibung_bleibt(self):
        roh = {"schaltzeichen": {"svg": "<svg/>", "beschreibung": "Dreieck", "norm": "IEC"}}
        assert ohne_svg(roh) == {
            "schaltzeichen": {"beschreibung": "Dreieck", "norm": "IEC"}
        }

    def test_in_einer_liste_von_objekten(self):
        """Der eigentliche Fall: `illustrationen` ist eine Liste, nicht ein Objekt."""
        roh = {"illustrationen": [
            {"datei": "a.svg", "svg": "<svg/>", "beschreibung": "eins"},
            {"datei": "b.svg", "svg": "<svg/>", "beschreibung": "zwei"},
        ]}
        assert ohne_svg(roh) == {"illustrationen": [
            {"datei": "a.svg", "beschreibung": "eins"},
            {"datei": "b.svg", "beschreibung": "zwei"},
        ]}

    def test_beliebige_tiefe(self):
        """„In jeder Tiefe" heißt: auch dort, wo heute niemand ein SVG erwartet."""
        roh = {"a": {"b": [{"c": {"svg": "<svg/>", "d": 1}}]}}
        assert ohne_svg(roh) == {"a": {"b": [{"c": {"d": 1}}]}}

    def test_ohne_svg_bleibt_alles_stehen(self):
        roh = {"fassung": "Klasse 8", "fehlvorstellungen": ["a", "b"], "ab_klasse": 8}
        assert ohne_svg(roh) == roh

    def test_skalare_und_leeres_ueberstehen_es(self):
        assert ohne_svg({}) == {} and ohne_svg([]) == []
        assert ohne_svg("svg") == "svg" and ohne_svg(None) is None

    def test_nur_der_schluessel_zaehlt_nicht_der_wert(self):
        """Gegenprobe: Ein Feld, das zufällig „svg" **enthält**, bleibt."""
        roh = {"svg_beschreibung": "x", "quelle": "svg-Datei aus dem Vault"}
        assert ohne_svg(roh) == roh


class TestAbbildungenFuersModell:
    """Bild-Einbettungen werden zur Beschreibung (Paket 9, AP3/E5).

    Die Oberfläche setzt an derselben Stelle das SVG ein (AP6). Beide Seiten finden
    dieselbe Stelle über den **Dateinamen**: im Text die bare Obsidian-Form, im
    Frontmatter ein Pfad.
    """

    ILL = {"illustrationen": [
        {"datei": "_Abb/EN_H2O.svg", "beschreibung": "Wassermolekül mit Partialladungen"}
    ]}

    def test_platzhalter_wird_zur_beschreibung(self):
        text = abbildungen_aufgeloest("Davor\n\n{{abbildung:EN_H2O.svg}}\n\nDanach", self.ILL)
        assert text == (
            "Davor\n\n[Abbildung: Wassermolekül mit Partialladungen]\n\nDanach"
        )

    def test_pfad_und_bare_form_treffen_denselben_eintrag(self):
        """⚠️ Verglichen wird der **Dateiname**, nicht der Pfad.

        Im Vault steht im Text die bare Form, im Frontmatter eine Pfadangabe. Welche
        von beiden das Seed-Skript in den Platzhalter schreibt, darf hier nicht
        entscheiden — sonst hinge die Auflösung an einer Festlegung in AP5.
        """
        for platzhalter in ("{{abbildung:EN_H2O.svg}}", "{{abbildung:_Abb/EN_H2O.svg}}"):
            assert "Partialladungen" in abbildungen_aufgeloest(platzhalter, self.ILL)

    def test_ohne_eintrag_bleibt_die_stelle_sichtbar(self):
        """Dass dort ein Bild steht, gehört zur Aussage — der Dateiname nicht.

        Er lädt dazu ein, ihn Lernenden gegenüber zu zitieren; eine fehlende
        Beschreibung ist ein Importmangel und gehört in den Bericht, nicht in den
        Prompt.
        """
        text = abbildungen_aufgeloest("{{abbildung:Unbekannt.svg}}", self.ILL)
        assert text == "[Abbildung]" and "Unbekannt" not in text

    def test_leere_beschreibung_zaehlt_als_fehlend(self):
        ill = {"illustrationen": [{"datei": "a.svg", "beschreibung": "   "}]}
        assert abbildungen_aufgeloest("{{abbildung:a.svg}}", ill) == "[Abbildung]"

    def test_mehrere_bilder_je_an_ihrer_stelle(self):
        ill = {"illustrationen": [
            {"datei": "_Abb/a.svg", "beschreibung": "eins"},
            {"datei": "_Abb/b.svg", "beschreibung": "zwei"},
        ]}
        assert abbildungen_aufgeloest("{{abbildung:b.svg}} x {{abbildung:a.svg}}", ill) == (
            "[Abbildung: zwei] x [Abbildung: eins]"
        )

    def test_text_ohne_einbettung_bleibt_unberuehrt(self):
        assert abbildungen_aufgeloest("Nur Text", self.ILL) == "Nur Text"

    def test_kein_metadata_stuerzt_nicht_ab(self):
        assert abbildungen_aufgeloest("{{abbildung:a.svg}}", None) == "[Abbildung]"


class TestMetadataFuersModell:
    """Welche Metadaten ein Treffer mitbringt — Whitelist je Typ (Paket 9, AP3).

    Die Suchschicht liefert seither die **rohe** Spalte mit; `fuer_modell` wählt aus.
    Die Tabelle steht in `app.context.taxonomy.MODELL_METADATA`, geprüft gegen
    `taxonomy.yaml` in `test_context_taxonomy.py`.
    """

    def _begriff(self, metadata, **felder):
        return _knoten(content_type="begriff", metadata=metadata, **felder)

    def test_fachliche_felder_gehen_mit(self):
        """Der Zweck der Sache: Ohne sie ist ein Fachbegriff im Dialog nur ein Text."""
        [e] = fuer_modell([self._begriff({
            "bevorzugter_begriff": "Elektronenpaarbindung",
            "fassung": "Elektronenabgabe",
            "ab_klasse": 10,
            "genus": "die",
            "plural": "Oxidationen",
            "fehlvorstellungen": ["Oxidation braucht immer Sauerstoff."],
        })])
        assert e["bevorzugter_begriff"] == "Elektronenpaarbindung"
        assert e["fassung"] == "Elektronenabgabe" and e["ab_klasse"] == 10
        assert e["genus"] == "die" and e["plural"] == "Oxidationen"
        assert e["fehlvorstellungen"] == ["Oxidation braucht immer Sauerstoff."]

    def test_rohe_spalte_bleibt_draussen(self):
        """⚠️ Der eigentliche Wächter: Nichts geht mit, was nicht benannt ist.

        `metadata` als Ganzes durchzureichen wäre die bequeme Lösung gewesen — und
        hätte Import-Interna, Breadcrumbs und ganze SVG-Dokumente in den Prompt
        gestellt.
        """
        [e] = fuer_modell([self._begriff({
            "fassung": "Elektronenabgabe",
            "bp_id": "CH.V2 3.2.1.1",
            "breadcrumb": ["Chemie", "Leitidee"],
            "illustrationen": [{"datei": "a.svg", "svg": "<svg>" + "x" * 5000}],
        })])
        assert "metadata" not in e and "bp_id" not in e
        assert "breadcrumb" not in e and "illustrationen" not in e
        assert "svg" not in repr(e)

    def test_typ_ohne_eintrag_bekommt_nichts(self):
        """Der Normalfall und der Stand vor AP3."""
        [e] = fuer_modell([_knoten(metadata={"kompetenz_nr": "3.2.1.1", "std": 4})])
        assert "kompetenz_nr" not in e and "std" not in e

    def test_leere_werte_erzeugen_kein_feld(self):
        """`"fassung": ""` an jedem Treffer wäre Rauschen ohne Aussage."""
        [e] = fuer_modell([self._begriff(
            {"fassung": "", "fehlvorstellungen": [], "ab_klasse": None, "genus": "der"}
        )])
        assert "fassung" not in e and "fehlvorstellungen" not in e
        assert "ab_klasse" not in e and e["genus"] == "der"

    def test_stoffsteckbrief_bringt_seine_tabelle_mit(self):
        """`eigenschaften` steht bewusst **nicht** im Embedding, aber im Gespräch.

        „Bei welcher Temperatur schmilzt Magnesiumoxid?" ist die Frage, für die der
        Steckbrief da ist.
        """
        [e] = fuer_modell([_knoten(content_type="stoffsteckbrief", metadata={
            "formel": r"\ce{MgO}",
            "eigenschaften": {"schmelztemperatur": "2852 °C"},
            "trivialnamen": ["gebrannte Magnesia"],
            "smiles": "[Mg]=O",
        })])
        assert e["eigenschaften"] == {"schmelztemperatur": "2852 °C"}
        assert e["formel"] == r"\ce{MgO}" and e["trivialnamen"] == ["gebrannte Magnesia"]
        # `smiles` ist ein Maschinenformat fürs Zeichnen, kein Gesprächsinhalt.
        assert "smiles" not in e

    def test_abbildung_wird_vor_dem_kuerzen_aufgeloest(self):
        """⚠️ Der Platzhalter liegt **auf** der Schnittkante — der einzige Fall, in dem
        sich die Reihenfolge überhaupt zeigt.

        Erst kürzen hieße: `{{abbildun` bleibt als Bruchstück stehen, die Beschreibung
        geht verloren, und das Modell liest geschweifte Klammern. Geprüft wird deshalb
        auf **jede** Klammer, nicht auf das ganze Wort — ein abgeschnittenes
        `{{abbildun` enthält `{{abbildung` gerade nicht mehr und käme sonst durch.
        """
        # ⚠️ Die Schnittkante hängt an der **Knotenart**: `begriff` wird seit N14
        # abschnittsweise gekürzt und hat ein größeres Budget. Der Test rechnete bis zum
        # 27.09.2026 mit 800 und prüfte danach an einem Text, der gar nicht mehr
        # geschnitten wurde — die Zusage wäre still ungeprüft geblieben.
        vorlauf = "A" * (INHALT_MAX_ZEICHEN_ABSCHNITTE - 10)
        [e] = fuer_modell([self._begriff(
            {"illustrationen": [{"datei": "_Abb/x.svg", "beschreibung": "Ein Bild"}]},
            content=vorlauf + "{{abbildung:x.svg}}",
        )])
        assert "{" not in e["content"] and "}" not in e["content"]
        assert e["content"].startswith(vorlauf + "[Abbildung")
        assert len(e["content"]) == INHALT_MAX_ZEICHEN_ABSCHNITTE + 2

    def test_metadata_ohne_dict_stuerzt_nicht_ab(self):
        [e] = fuer_modell([self._begriff(None)])
        assert "fassung" not in e


class TestSuchbegriffeUndAbgrenzungen:
    """Was ein Treffer dem Modell über sich sagt (Paket 9, Nachgang N1 + N4)."""

    def _knoten_mit(self, **felder):
        return _knoten(content_type="begriff", **felder)

    def test_aliase_heissen_suchbegriffe(self):
        """⚠️ Der Name ist die Maßnahme.

        Unter `aliase` standen sie gleichberechtigt neben `bevorzugter_begriff`, und
        das Modell verwendete sie: In Szenario (f) antwortete es mit
        „Wasserstoffbrückenbindung", obwohl der Knoten „Wasserstoffbrücken" heißt und
        den anderen Ausdruck nur als Suchbegriff führt.
        """
        [e] = fuer_modell([self._knoten_mit(aliase=["Wasserstoffbrückenbindung"])])
        assert e["suchbegriffe"] == ["Wasserstoffbrückenbindung"]
        assert "aliase" not in e, "Der alte, unbeschriftete Schlüssel ist weg"

    def test_ohne_aliase_kein_feld(self):
        """`"suchbegriffe": []` an jedem Treffer wäre Rauschen ohne Aussage."""
        [e] = fuer_modell([self._knoten_mit()])
        assert "suchbegriffe" not in e

    def test_abgrenzungen_gehen_mit(self):
        """Sie stehen weder im Knotentext noch im Embedding — bis N4 sah das Modell
        sie gar nicht, dabei verhindern genau sie die Verwechslung."""
        grenzen = {"abc": [{"zu": "Elektronenpaarbindung",
                            "hinweis": "wirkt innerhalb eines Moleküls"}]}
        [e] = fuer_modell([self._knoten_mit()], grenzen)
        assert e["abgrenzungen"] == grenzen["abc"]

    def test_abgrenzungen_werden_dem_richtigen_knoten_zugeordnet(self):
        """Die Zuordnung läuft über die `node_id` — wäre sie positionsabhängig, stünde
        der Hinweis am falschen Treffer und niemandem fiele es auf."""
        grenzen = {"zwei": [{"zu": "Y"}]}
        eins, zwei = fuer_modell(
            [_knoten(node_id="eins", title="Eins"), _knoten(node_id="zwei", title="Zwei")],
            grenzen,
        )
        assert "abgrenzungen" not in eins
        assert zwei["abgrenzungen"] == [{"zu": "Y"}]

    def test_ohne_abgrenzungen_kein_feld(self):
        [e] = fuer_modell([self._knoten_mit()], {})
        assert "abgrenzungen" not in e
        [e2] = fuer_modell([self._knoten_mit()])
        assert "abgrenzungen" not in e2


class TestLesehinweis:
    """Der Lesehinweis vor jedem Kontextblock (Paket 9, N13).

    ⚠️ **Zwei Wege, ein Hinweis.** Bausteine erreichen das Modell über die Vorab-Suche
    **und** über das Suchwerkzeug. Stünde der Hinweis nur an einem, hinge das Verhalten
    davon ab, welchen Weg das Modell zufällig genommen hat — genau die Abhängigkeit, die
    die Vorab-Suche gerade beseitigt hat.
    """

    def test_hinweis_steht_vorn(self):
        from app.context.modellsicht import mit_lesehinweis
        from app.pedagogy.config import load_pedagogy
        aus = mit_lesehinweis('{"nodes": []}')
        assert aus.startswith(load_pedagogy().kontext_hinweis.strip())
        assert aus.endswith('{"nodes": []}')

    def test_ohne_hinweis_bleibt_der_rumpf_unberuehrt(self, monkeypatch):
        """Leerer Schlüssel = kein Hinweis. Eine Schule, die ihn streicht, bekommt den
        Block ohne Vorwort — nicht einen Block mit zwei Leerzeilen davor."""
        from app.context import modellsicht
        from app.pedagogy.config import load_pedagogy

        konfig = load_pedagogy().model_copy(update={"kontext_hinweis": "  "})
        monkeypatch.setattr(modellsicht, "load_pedagogy", lambda: konfig)
        assert modellsicht.mit_lesehinweis("RUMPF") == "RUMPF"

    def test_werkzeugergebnis_traegt_den_hinweis(self):
        """Beide Ergebnisformen der Gruppe `context_search` — Umschlag und flache Liste."""
        from app.context.modellsicht import werkzeug_nutzlast
        from app.pedagogy.config import load_pedagogy
        kopf = load_pedagogy().kontext_hinweis.strip()

        umschlag = werkzeug_nutzlast({"exakte_namenstraeger": [], "gesamt": 0})
        assert umschlag.startswith(kopf)
        assert '"gesamt": 0' in umschlag

        liste = werkzeug_nutzlast([_knoten(content="x")])
        assert liste.startswith(kopf)
        assert '"nodes"' in liste
        # Durch `fuer_modell` gelaufen: die interne ID bleibt draußen.
        assert "node_id" not in liste

    def test_regeln_stehen_nicht_mehr_in_der_werkzeugbeschreibung(self):
        """⚠️ **Sonst stünden sie an zwei Orten.** Der Grund für N13 war, dass die
        Leseregeln nur dort standen, wo das Modell sie oft nicht sieht. Sie zusätzlich
        stehen zu lassen, hieße dieselbe Regel doppelt zu pflegen — und die eine würde
        eines Tages geändert und die andere nicht.
        """
        from app.chat.router import _SEARCH_CONTEXT_NODES_TOOL
        beschreibung = _SEARCH_CONTEXT_NODES_TOOL["function"]["description"]
        assert "suchbegriffe" not in beschreibung
        assert "abgrenzungen" not in beschreibung
        assert "Hinweis" in beschreibung


class TestAbschnittsweiseKuerzung:
    """Definition und Erklärung vollständig, Beispiele nach Budget (Paket 9, N14).

    ⚠️ **Der Anlass war eine Zählung, kein Gefühl:** Bei 800 Zeichen wurden 26 der 36
    Pilotknoten gekürzt, der Schnitt lag fast immer mitten in der Erklärung, und der
    Beispiel-Abschnitt erreichte das Modell in 11 von 36 Fällen. Bei drei von fünf Knoten
    mit Abbildung fiel auch der Platzhalter weg — gerade der Hinweis, dass es ein Bild gibt.
    """

    def _knoten_text(self, erklaerung_laenge=300, beispiele=6):
        return (
            "Die Definition in einem Satz.\n\n### Erklärung\n\n"
            + "E" * erklaerung_laenge
            + "\n\n### Beispiele\n\n"
            + "\n".join(f"- Beispiel {i} " + "b" * 90 for i in range(beispiele))
        )

    def test_definition_und_erklaerung_bleiben_ganz(self):
        from app.context.modellsicht import kuerze
        text = self._knoten_text()
        aus = kuerze(text, "begriff")
        assert "Die Definition in einem Satz." in aus
        assert "E" * 300 in aus

    def test_beispiele_werden_zuerst_geopfert(self):
        from app.context.modellsicht import kuerze, INHALT_MAX_ZEICHEN_ABSCHNITTE
        aus = kuerze(self._knoten_text(beispiele=30), "begriff")
        assert len(aus) <= INHALT_MAX_ZEICHEN_ABSCHNITTE
        assert aus.rstrip().endswith("…"), "gekürzt, aber ohne sichtbares Zeichen"
        assert "Beispiel 0" in aus and "Beispiel 29" not in aus

    def test_schnitt_liegt_auf_einer_zeilengrenze(self):
        """Ein halber Spiegelstrich ist schlechter als einer weniger."""
        from app.context.modellsicht import kuerze
        aus = kuerze(self._knoten_text(beispiele=30), "begriff")
        for zeile in aus.splitlines():
            if zeile.startswith("- Beispiel"):
                assert zeile.endswith("b" * 90), f"angeschnitten: {zeile[-30:]!r}"

    def test_kurzer_knoten_bleibt_unangetastet(self):
        from app.context.modellsicht import kuerze
        text = self._knoten_text(erklaerung_laenge=50, beispiele=2)
        assert kuerze(text, "begriff") == text

    def test_ueberlanger_kern_wird_trotzdem_geschnitten(self):
        """⚠️ Die Zusage lautet „Beispiele zuerst", nicht „der Kern ist heilig" — sonst
        füllte ein einzelner Baustein den halben Prompt."""
        from app.context.modellsicht import kuerze, INHALT_MAX_ZEICHEN_ABSCHNITTE
        aus = kuerze(self._knoten_text(erklaerung_laenge=4000, beispiele=3), "begriff")
        assert len(aus) <= INHALT_MAX_ZEICHEN_ABSCHNITTE + 2
        assert aus.endswith("…")

    def test_andere_knotenarten_behalten_den_harten_schnitt(self):
        """Eine Bildungsplan-Kompetenz hat keine Beispiele, die man schonen könnte —
        und liegt im Median bei 137 Zeichen."""
        from app.context.modellsicht import kuerze, INHALT_MAX_ZEICHEN
        lang = "K" * (INHALT_MAX_ZEICHEN + 500)
        assert len(kuerze(lang, "ik_kompetenz")) == INHALT_MAX_ZEICHEN + 2

    def test_bildbeschreibung_zaehlt_mit(self):
        """`abbildungen_aufgeloest` läuft vorher; ihr Ergebnis ist Teil des Budgets.

        Ohne diese Reihenfolge stünde am Ende ein halber Platzhalter im Prompt — der
        Fehler, den schon AP3 vermieden hat.
        """
        from app.context.modellsicht import fuer_modell, INHALT_MAX_ZEICHEN_ABSCHNITTE
        beschreibung = "Wassermolekül mit Partialladungen, " * 20
        [e] = fuer_modell([_knoten(
            content_type="begriff",
            content="Definition.\n\n{{abbildung:x.svg}}\n\n### Beispiele\n\n"
                    + "\n".join(f"- B{i} " + "y" * 90 for i in range(30)),
            metadata={"illustrationen": [{"datei": "x.svg", "beschreibung": beschreibung}]},
        )])
        assert "[Abbildung: " in e["content"]
        assert "{" not in e["content"] and "}" not in e["content"]
        assert len(e["content"]) <= INHALT_MAX_ZEICHEN_ABSCHNITTE + 2
