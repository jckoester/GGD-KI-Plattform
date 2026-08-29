"""Erkennung eines erschöpften Budgets in LiteLLM-Fehlerantworten.

Der Anlass ist eine Messung vom 29.08.2026: LiteLLM 1.83.7 meldet das aufgebrauchte Budget
mit **HTTP 400**, nicht mit 429. Der Code prüfte an mehreren Stellen auf 429 — die
freundliche Meldung erschien deshalb nie, und umgekehrt bekam jede Drosselung
fälschlich „Dein Budget ist erschöpft" zu sehen.

Diese Tests halten fest, dass die Erkennung am **Fehlertyp** hängt und nicht am Status.
"""
import pytest

from app.litellm.errors import BUDGET_TYP, ist_budget_erschoepft

# Wortgleich die Antwort aus der Messung vom 29.08.2026 (LiteLLM 1.83.7).
GEMESSEN = (
    '{"error":{"message":"Budget has been exceeded! Current cost: '
    '2.6269999999999998e-05, Max budget: 2e-05","type":"budget_exceeded",'
    '"param":null,"code":"400"}}'
)


def test_erkennt_die_gemessene_antwort():
    assert ist_budget_erschoepft(GEMESSEN)


def test_erkennt_sie_auch_als_bytes():
    """Der Chat-Pfad liest den Körper als Bytes (`response.aread()`)."""
    assert ist_budget_erschoepft(GEMESSEN.encode())


def test_status_spielt_keine_rolle():
    """Derselbe Körper, egal ob er mit 400 oder 429 kam — die Funktion sieht ihn nur.

    Genau das ist der Punkt: Der Status ist versionsabhängig, der Typ nicht.
    """
    assert ist_budget_erschoepft(GEMESSEN)
    assert ist_budget_erschoepft(GEMESSEN.replace('"code":"400"', '"code":"429"'))


def test_erkennt_flache_form():
    assert ist_budget_erschoepft(f'{{"type":"{BUDGET_TYP}"}}')


def test_erkennt_umgebaute_huelle_ueber_die_textsuche():
    """Rückfall für den Fall, dass LiteLLM die Verschachtelung ändert."""
    assert ist_budget_erschoepft('{"detail":{"reason":{"kind":"budget_exceeded"}}}')


def test_drosselung_ist_kein_budgetfehler():
    """Der wichtigste Negativfall — er war die Ursache der falschen Meldung."""
    ratelimit = (
        '{"error":{"message":"Rate limit reached","type":"rate_limit_error",'
        '"code":"429"}}'
    )
    assert not ist_budget_erschoepft(ratelimit)


@pytest.mark.parametrize("body", [None, "", b"", "kein json", "{}", '{"error":"kaputt"}'])
def test_haelt_unbrauchbare_koerper_aus(body):
    assert not ist_budget_erschoepft(body)


def test_meldet_nicht_bei_blossem_wort_budget():
    """„budget" allein genügt nicht — sonst träfe es jede Meldung, die das Wort enthält."""
    assert not ist_budget_erschoepft(
        '{"error":{"message":"No budget configured for this key",'
        '"type":"invalid_request_error"}}'
    )
