"""Was der Chat aus einem Werkzeug-Ergebnis macht (app/chat/router.py).

Übrig ist ein Weg: der **Text ans Modell**. Er trug bis 08/2026 ausschließlich Titel,
womit jede Frage nach dem *Inhalt* des Wissensgraphen unbeantwortbar war.

Der zweite Weg — die Vorschlagsliste im Chat (SSE `context_suggestions`) — ist mit
ADR-017/AP1 entfallen. Die Form**prüfung**, die er brauchte, ist damit ebenfalls weg;
`_fuer_modell` prüft ohnehin je Eintrag und reicht fremde Formen durch (siehe
``TestFuerModell``). Genau daran war der Stream einmal abgerissen: Die Gruppe
`context_search` enthält auch `get_operatoren`, dessen Einträge `operator`/`afb`/
`bedeutung` tragen und keinen `title`.
"""

from app.chat.router import _INHALT_MAX_ZEICHEN, _fuer_modell


def _knoten(**felder):
    return {"node_id": "abc", "title": "Titel", "category": "knowledge",
            "content_type": "ik_kompetenz", "subject_id": 13, "fach": "Mathematik",
            **felder}


class TestFuerModell:
    def test_inhalt_geht_mit(self):
        """Der Kern der Sache: ohne Inhalt kann das Modell die Knoten nicht lesen."""
        [e] = _fuer_modell([_knoten(content="Fläche und Umfang eines Kreises")])
        assert e["content"] == "Fläche und Umfang eines Kreises"

    def test_node_id_bleibt_draussen(self):
        """Sie nützt dem Modell nichts und landet sonst in der Antwort."""
        [e] = _fuer_modell([_knoten(content="x")])
        assert "node_id" not in e and e["title"] == "Titel"

    def test_langer_inhalt_wird_gekuerzt(self):
        [e] = _fuer_modell([_knoten(content="A" * (_INHALT_MAX_ZEICHEN + 500))])
        assert len(e["content"]) == _INHALT_MAX_ZEICHEN + 2
        assert e["content"].endswith(" …")

    def test_leerer_inhalt_erzeugt_kein_feld(self):
        [e] = _fuer_modell([_knoten(content=None)])
        assert "content" not in e

    def test_fach_statt_interner_id(self):
        """Das Modell braucht den Fachnamen, nicht `subject_id`.

        Mit `subject_id: 13` konnte ein Modell die Frage „… in den verschiedenen Fächern"
        nicht beantworten und meldete, es gebe keine Einträge je Fach — obwohl die
        Treffer stimmten.
        """
        [e] = _fuer_modell([_knoten()])
        assert e["fach"] == "Mathematik"
        assert "subject_id" not in e

    def test_knoten_ohne_fach_bekommt_kein_feld(self):
        """Leitperspektiven tragen kein Fach — dann steht dort auch nichts."""
        [e] = _fuer_modell([_knoten(fach=None, subject_id=None)])
        assert "fach" not in e and "subject_id" not in e

    def test_fremde_form_wird_durchgereicht(self):
        """Operatoren behalten ihre Felder — sonst verlöre das Modell die Definition.

        Zugleich der Beleg, dass es keine vorgeschaltete Formprüfung braucht: Die
        Unterscheidung fällt je Eintrag, nicht für die Liste als Ganzes.
        """
        eintrag = {"operator": "nennen", "afb": "I", "bedeutung": "knapp anführen"}
        assert _fuer_modell([eintrag]) == [eintrag]

    def test_gemischte_liste(self):
        """Knoten und fremde Form nebeneinander — beide überstehen die Aufbereitung."""
        fremd = {"operator": "nennen", "afb": "I"}
        knoten, durchgereicht = _fuer_modell([_knoten(content="x"), fremd])
        assert durchgereicht == fremd
        assert knoten["title"] == "Titel" and "node_id" not in knoten

    def test_hinweis_dict_wird_nicht_angefasst(self):
        """`get_operatoren` ohne Fachbezug liefert einen Hinweis statt einer Liste."""
        assert _fuer_modell([{"hinweis": "kein Fachbezug"}]) == [{"hinweis": "kein Fachbezug"}]


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
