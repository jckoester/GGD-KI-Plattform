"""Assistenten-Vorschlag im Chat (Päckchen C2, Schritt 2) — reine Funktionen des Dienstes."""
from app.assistants.vorschlag import (
    BEENDEN_KENNUNG,
    Kandidat,
    im_assistenten,
    lies_antwort,
    prompt_kandidaten,
    zusammenstellen,
)


def _k(i, art="specific", abstand=0.4, gegen=float("inf"), fach=None, fallbacks=()):
    return Kandidat(id=i, name=f"A{i}", art=art, text=f"Text {i}", subject_id=fach,
                    fallbacks=tuple(fallbacks), abstand=abstand, gegen=gegen)


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
    assert [o.assistant_id for o in zusammenstellen([3, 1, 2, 42], [9, 8, 7], k)] == [1, 2, 9, 8]


def test_im_assistenten_wechsel_beenden_bleiben():
    k = {2: _k(2, abstand=0.30)}
    assert [o.assistant_id for o in im_assistenten(0.40, k, True)] == [2]           # 0,30 + 0,05 < 0,40
    assert im_assistenten(0.33, k, True) == []                                      # Marge nicht erreicht
    assert [o.art for o in im_assistenten(0.60, {}, True)] == ["beenden"]
    assert im_assistenten(0.60, {}, False) == []                                    # Ruheregel
    assert im_assistenten(0.45, {}, True) == []                                     # bleiben
    gegen = {2: _k(2, abstand=0.30, gegen=0.25)}
    assert [o.assistant_id for o in im_assistenten(0.60, gegen, True)] == [BEENDEN_KENNUNG]


def test_prompt_nennt_art_und_beispiele():
    k = Kandidat(id=4, name="Reaktionsgleichungen", art="fallback", text="T", subject_id=None, fallbacks=(),
                 abstand=0.4, gegen=1.0, beispiele=("b1", "b2"))
    assert prompt_kandidaten([k]).splitlines() == [
        "- Kennung 4 · Rückfall · „Assistent für Reaktionsgleichungen“: T", "    Beispiel: b1", "    Beispiel: b2"]
