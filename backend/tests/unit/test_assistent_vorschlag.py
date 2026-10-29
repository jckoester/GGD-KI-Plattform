import pytest
"""Assistenten-Vorschlag im Chat (Päckchen C2, Schritt 2) — reine Funktionen des Dienstes."""
from app.assistants.vorschlag import (
    Kandidat,
    im_assistenten_band,
    lies_antwort,
    lies_wechsel,
    prompt_im_assistenten,
    prompt_kandidaten,
    zusammenstellen,
)


def _k(i, art="specific", abstand=0.4, gegen=float("inf"), fach=None, fallbacks=(), mittel=None):
    return Kandidat(id=i, name=f"A{i}", art=art, text=f"Text {i}", subject_id=fach,
                    fallbacks=tuple(fallbacks), abstand=abstand, gegen=gegen,
                    mittel=abstand if mittel is None else mittel)


def test_lies_antwort_codeblock_und_fremde_kennungen():
    erlaubt = {1: "specific", 3: "fallback"}
    assert lies_antwort('```json\n{"spezifisch": [1, "1", 7], "rueckfall": ["3"]}\n```', erlaubt) == ([1], [3])
    assert lies_antwort("[1, 2]", erlaubt) == ([], [])
    assert lies_antwort("", erlaubt) == ([], [])


def test_zusammenstellen_rueckfall_aus_fallbacks_des_treffers():
    k = {1: _k(1, fallbacks=[5]), 2: _k(2, abstand=0.3), 5: _k(5, "fallback"), 6: _k(6, "fallback")}
    optionen = zusammenstellen([1, 2], [6], k)
    assert [o.assistant_id for o in optionen] == [2, 1, 5]     # näherer zuerst, dann fallbacks von 1


def test_zusammenstellen_konversationsfach_sortiert_schliesst_nicht_aus():
    k = {1: _k(1, abstand=0.30), 2: _k(2, abstand=0.40, fach=9)}
    assert [o.assistant_id for o in zusammenstellen([1, 2], [], k, konversationsfach=9)] == [2, 1]


def test_zusammenstellen_hoechstens_zwei_und_nur_kandidaten():
    k = {i: _k(i, abstand=0.3 + i / 100) for i in (1, 2, 3)} | {8: _k(8, "fallback"), 9: _k(9, "fallback")}
    assert [o.assistant_id for o in zusammenstellen([3, 1, 2, 42], [9, 8, 7], k)] == [1, 2, 9]
    # Ohne spezifischen Treffer: nur der erste Rückfall des Klassifikators (0.26, V1).
    assert [o.assistant_id for o in zusammenstellen([], [9, 8, 7], k)] == [9]


def test_zusammenstellen_fallbacks_des_treffers_bis_zwei():
    k = {1: _k(1, fallbacks=[8, 9]), 8: _k(8, "fallback"), 9: _k(9, "fallback")}
    assert [o.assistant_id for o in zusammenstellen([1], [], k)] == [1, 8, 9]




def test_prompt_nennt_art_und_beispiele():
    k = Kandidat(id=4, name="Reaktionsgleichungen", art="fallback", text="T", subject_id=None, fallbacks=(),
                 abstand=0.4, gegen=1.0, beispiele=("b1", "b2"))
    assert prompt_kandidaten([k]).splitlines() == [
        "- Kennung 4 · Rückfall · „Assistent für Reaktionsgleichungen“: T", "    Beispiel: b1", "    Beispiel: b2"]


def test_vorschlag_nur_fuer_schuelerinnen_ohne_vorschau_und_stundenbezug():
    from types import SimpleNamespace

    from app.chat.router import _vorschlag_moeglich

    schueler = SimpleNamespace(roles=["student"])
    assert _vorschlag_moeglich(schueler, False, None)
    assert not _vorschlag_moeglich(schueler, True, None)                     # Vorschau (Editor)
    assert not _vorschlag_moeglich(schueler, False, "stunde")                # Stundenbezug
    assert not _vorschlag_moeglich(SimpleNamespace(roles=["teacher"]), False, None)
    assert not _vorschlag_moeglich(SimpleNamespace(roles=["student", "teacher"]), False, None)


def test_beenden_und_assistent_schliessen_sich_aus():
    import pytest
    from pydantic import ValidationError

    from app.chat.schemas import ChatRequest

    nachricht = [{"role": "user", "content": "x"}]
    assert ChatRequest(messages=nachricht, assistent_beenden=True).assistent_beenden
    with pytest.raises(ValidationError):
        ChatRequest(messages=nachricht, assistent_beenden=True, assistant_id=3)


async def test_klassifikator_zweiter_versuch_bei_5xx():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.assistants import vorschlag as dienst

    def antwort(code):
        a = MagicMock(status_code=code)
        a.json.return_value = {"choices": [{"message": {"content": '{"spezifisch": []}'}}]}
        a.raise_for_status = MagicMock()
        return a
    client = MagicMock(post=AsyncMock(side_effect=[antwort(500), antwort(200)]))
    with patch("app.litellm.systemkonto.verbuche", new=AsyncMock()):
        r = await dienst.klassifiziere("x", [], modell="m", client=client)
    assert client.post.await_count == 2 and r["roh"] == '{"spezifisch": []}'


def test_im_assistenten_band():
    """Vorfilter für den Klassifikator in der Assistenten-Konversation (Jan, 29.10.2026): jeder
    andere Assistent mit seinem besten Beispiel unter 0,45, spezifisch wie Rückfall — ohne Marge
    und Gegenbeispiel-Regel."""
    k = {1: _k(1, abstand=0.40), 2: _k(2, "fallback", abstand=0.35), 3: _k(3, "fallback", abstand=0.45),
         4: _k(4, abstand=0.30, gegen=0.20, mittel=0.60)}
    assert [c.id for c in im_assistenten_band(k)] == [4, 2, 1]        # das beste Beispiel, nicht das Mittel
    assert im_assistenten_band({}) == []


def test_lies_wechsel():
    assert lies_wechsel('```json\n{"neue_aufgabe": "7"}\n```', {7}) == 7
    assert lies_wechsel('{"neue_aufgabe": null}', {7}) is None
    assert lies_wechsel('{"neue_aufgabe": 8}', {7}) is None          # nicht im Band
    assert lies_wechsel("laufendes Gespräch", {7}) is None
    assert lies_wechsel('{"neue_aufgabe": [7]}', {7}) is None


def test_prompt_im_assistenten_kuerzt_von_vorn():
    lang = "x" * 1000 + " Welche Größe fehlt?"
    text = prompt_im_assistenten("hä?", ("Mathe-Aufgaben", "Hilft bei Mathe"), lang, [_k(3)])
    assert "Welche Größe fehlt?“" in text and "x" * 700 not in text
    assert "„Assistent für Mathe-Aufgaben“: Hilft bei Mathe" in text and "Kennung 3" in text
    assert "(keine)" in prompt_im_assistenten("hä?", ("M", ""), None, [])
