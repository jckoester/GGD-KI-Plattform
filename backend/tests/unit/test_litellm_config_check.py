"""Unit-Tests für die Vollständigkeitsprüfung der LiteLLM-Konfiguration.

Jeder dieser Funde entspricht einem Fehler, der sonst **still** bleibt und erst Wochen später
auffällt — an einer Kostenstatistik, die auf 0 steht, oder an Werkzeugen, die nicht mehr
erscheinen. Der Zweck der Prüfung ist, sie vor der Inbetriebnahme sichtbar zu machen.
"""
from types import SimpleNamespace

import pytest

from app.litellm.config_check import ERROR, INFO, WARNING, check_config


def _settings(**over):
    base = dict(
        chat_default_model="chat-standard",
        title_model="system-titel",
        embedding_model="embedding-standard",
        image_default_model="bild-standard",
        model_picker_hidden_prefixes=["system-", "embedding-", "bild-"],
    )
    base.update(over)
    return SimpleNamespace(**base)


def _entry(name, *, target="openai/x", **info):
    return {
        "model_name": name,
        "litellm_params": {"model": target},
        "model_info": info,
    }


def _healthy():
    """Eine Konfiguration, die alle Anforderungen erfüllt."""
    return [
        _entry("chat-standard", supports_function_calling=True,
               input_cost_per_token=1.5e-7, output_cost_per_token=6e-7),
        _entry("system-titel", supports_function_calling=False,
               input_cost_per_token=1e-8, output_cost_per_token=2e-8),
        _entry("embedding-standard", mode="embedding", input_cost_per_token=1e-9),
        _entry("bild-standard", mode="image_generation", input_cost_per_image=0.032),
        _entry("lokal", target="ollama/llama3", litellm_provider="ollama",
               supports_function_calling=False),
    ]


def _bildart(id="standard", modell="bild-standard"):
    from app.chat.image_models import Bildart

    return Bildart(
        id=id, label=id, modell=modell,
        formate={"quadratisch": "1024x1024"}, standardformat="quadratisch",
    )


# Explizit übergeben statt geladen: Sonst läse check_config die echte
# config/image_models.yaml bzw. die echte .env — die Tests hingen dann an der Umgebung.
_BILDARTEN = [_bildart()]


def _levels(findings, level):
    return [f.message for f in findings if f.level == level]


def test_healthy_config_has_no_errors_or_warnings():
    findings = check_config(_healthy(), _settings(), bildarten=_BILDARTEN)

    assert _levels(findings, ERROR) == []
    assert _levels(findings, WARNING) == []


def test_empty_proxy_is_an_error():
    findings = check_config([], _settings(), bildarten=_BILDARTEN)

    assert len(_levels(findings, ERROR)) == 1


# ── Preise: der teuerste stille Fehler ───────────────────────────────────────

def test_missing_token_prices_are_errors():
    """Ohne Preise meldet der SpendLog 0 — Budgets und 429-Enforcement greifen nicht."""
    entries = _healthy()
    entries[0] = _entry("chat-standard", supports_function_calling=True)

    errors = _levels(check_config(entries, _settings(), bildarten=_BILDARTEN), ERROR)

    assert any("input_cost_per_token" in m for m in errors)
    assert any("output_cost_per_token" in m for m in errors)
    assert any("Umrechnung" in m for m in errors), "Meldung soll die Umrechnung nennen"


def test_lokales_modell_braucht_keine_preise():
    """Ein lokal betriebenes Modell kostet nichts — es zu bemängeln wäre Rauschen.

    Erkannt wird es am Anbieter, nicht am Namen: Die Plattform liefert keinen lokalen
    Eintrag mehr mit, wer einen betreibt, benennt ihn wie er mag.
    """
    findings = check_config(_healthy(), _settings(), bildarten=_BILDARTEN)

    assert not [m for m in _levels(findings, ERROR) if "lokal" in m]


def test_openai_kompatibler_anbieter_bleibt_preispflichtig():
    """Gegenprobe: Ein Anbieter mit eigener api_base ist nicht automatisch kostenlos.

    IONOS und Mistral laufen als OpenAI-kompatible Endpunkte. Würde die Ausnahme für
    lokale Modelle auch sie erfassen, bliebe ihr fehlender Preis unbemerkt — und genau
    daran hängen Budgets, Sperre und Kostenstatistik.
    """
    eintraege = _healthy() + [
        _entry("chat-eu", target="openai/irgendwas", litellm_provider="openai",
               supports_function_calling=True)
    ]
    findings = check_config(eintraege, _settings(), bildarten=_BILDARTEN)

    assert [m for m in _levels(findings, ERROR) if "chat-eu" in m], (
        "Fehlende Preise eines bezahlten Anbieters müssen gemeldet werden"
    )


def test_per_image_token_pricing_counts_as_priced():
    """Regression: gpt-image-1 rechnet pro **Bild-Token** ab, nicht pro Bild.

    Eine feste Schlüsselliste (`output_cost_per_image`) hat das als „kein Preis" gemeldet —
    ein Fehlalarm, aufgefallen erst beim Lauf gegen den echten Dev-Proxy. Ein Prüfer, der
    grundlos warnt, wird ignoriert.
    """
    entries = _healthy()
    entries[3] = _entry(
        "bild-standard", mode="image_generation",
        input_cost_per_image_token=1e-5, output_cost_per_image_token=4e-5,
    )

    findings = check_config(entries, _settings(), bildarten=_BILDARTEN)

    assert not [m for m in _levels(findings, WARNING) if "bild-standard" in m]


def test_fehlender_preis_in_model_info_ist_kein_fund():
    """Für **Bilder** ist ein Preis unter `model_info` bedeutungslos.

    LiteLLM löst Bildpreise über seine eingebaute Tabelle auf und liest das `model_info`
    des Deployments dabei nicht (gemessen 28.08.2026). Ihn hier anzumahnen, hätte in die
    falsche Richtung gewiesen: Wer ihn daraufhin einträgt, hält das Problem für gelöst und
    bucht weiter 0,00 $. Gerügt wird deshalb nur ein fehlender Eintrag in IMAGE_PRICES.
    """
    entries = _healthy()
    entries[3] = _entry("bild-standard", mode="image_generation")  # kein Preis

    findings = check_config(entries, _settings(), bildarten=_BILDARTEN)

    assert not [m for m in _levels(findings, WARNING) if "bild-standard" in m]
    assert not [m for m in _levels(findings, ERROR) if "bild-standard" in m]


def test_output_cost_per_image_ist_der_falsche_schluessel():
    entries = _healthy()
    entries[3] = _entry("bild-standard", mode="image_generation", output_cost_per_image=0.01)

    warnings = _levels(check_config(entries, _settings(), bildarten=_BILDARTEN), WARNING)

    assert any("output_cost_per_image" in m and "input_cost_per_image" in m for m in warnings)


def test_abweichung_zwischen_model_info_und_image_prices():
    """Die Config-Vorlagen verlangen, beide Stellen gleich zu halten."""
    entries = _healthy()  # model_info: 0.032
    warnings = _levels(
        check_config(
            entries, _settings(), bildarten=_BILDARTEN,
            image_prices={"x": 0.05},  # _entry-Standardziel ist "openai/x"
        ),
        WARNING,
    )

    assert any("0.032" in m and "0.05" in m for m in warnings)


# ── Werkzeug-Fähigkeit ───────────────────────────────────────────────────────

def test_unset_function_calling_is_an_error():
    """Unbestimmt ist schlimmer als False: Das Backend kann sich dann nicht entscheiden."""
    entries = _healthy()
    entries[0] = _entry("chat-standard", input_cost_per_token=1e-7, output_cost_per_token=1e-7)

    errors = _levels(check_config(entries, _settings(), bildarten=_BILDARTEN), ERROR)

    assert any("supports_function_calling" in m for m in errors)


def test_explicit_false_is_only_a_warning():
    """Ein bewusst tool-loses Standardmodell ist eine Entscheidung, kein Konfigurationsfehler."""
    entries = _healthy()
    entries[0] = _entry("chat-standard", supports_function_calling=False,
                        input_cost_per_token=1e-7, output_cost_per_token=1e-7)

    findings = check_config(entries, _settings(), bildarten=_BILDARTEN)

    assert any("Function-Calling" in m for m in _levels(findings, WARNING))
    assert not [m for m in _levels(findings, ERROR) if "chat-standard" in m]


# ── .env ↔ Proxy ─────────────────────────────────────────────────────────────

def test_unknown_model_name_in_env_is_an_error():
    findings = check_config(_healthy(), _settings(chat_default_model="gibt-es-nicht"), bildarten=_BILDARTEN)

    errors = _levels(findings, ERROR)
    assert any("CHAT_DEFAULT_MODEL" in m and "gibt-es-nicht" in m for m in errors)
    assert any("chat-standard" in m for m in errors), "verfügbare Namen sollen genannt werden"


def test_missing_required_env_var_is_an_error():
    findings = check_config(_healthy(), _settings(chat_default_model=""), bildarten=_BILDARTEN)

    assert any("CHAT_DEFAULT_MODEL ist nicht gesetzt" in m for m in _levels(findings, ERROR))


def test_optional_title_model_may_be_empty():
    """Leeres TITLE_MODEL heißt schlicht „keine Titelgenerierung"."""
    findings = check_config(_healthy(), _settings(title_model=""), bildarten=_BILDARTEN)

    assert not [m for m in _levels(findings, ERROR) if "TITLE_MODEL" in m]


# ── Modalitäten ──────────────────────────────────────────────────────────────

def test_image_model_without_mode_is_an_error():
    """Ohne mode taucht es in der Bild-Freigabe-Matrix nicht auf."""
    entries = _healthy()
    entries[3] = _entry("bild-standard", output_cost_per_image=0.01)

    errors = _levels(check_config(entries, _settings(), bildarten=_BILDARTEN), ERROR)

    assert any("image_generation" in m for m in errors)


def test_embedding_model_without_mode_is_only_a_warning():
    entries = _healthy()
    entries[2] = _entry("embedding-standard", input_cost_per_token=1e-9)

    findings = check_config(entries, _settings(), bildarten=_BILDARTEN)

    assert any("embedding" in m for m in _levels(findings, WARNING))
    assert not [m for m in _levels(findings, ERROR) if "embedding-standard" in m]


# ── Sichtbarkeit ─────────────────────────────────────────────────────────────

def test_reports_which_models_are_pickable():
    findings = check_config(_healthy(), _settings(), bildarten=_BILDARTEN)
    info = " ".join(_levels(findings, INFO))

    assert "chat-standard" in info
    assert "system-titel" in info  # als ausgeblendet gemeldet


def test_title_model_visible_in_picker_is_a_warning():
    """Ein Titelmodell ohne system--Präfix landet im Dropdown der Schüler:innen."""
    entries = _healthy()
    entries[1] = _entry("gpt-4o-mini", supports_function_calling=False,
                        input_cost_per_token=1e-8, output_cost_per_token=2e-8)

    findings = check_config(entries, _settings(title_model="gpt-4o-mini"), bildarten=_BILDARTEN)

    warnings = _levels(findings, WARNING)
    assert any("TITLE_MODEL" in m and "Modellwähler" in m for m in warnings)
    assert any("freigeschaltet bleiben muss" in m for m in warnings), (
        "Die Warnung darf nicht dazu verleiten, das Modell aus der Allowlist zu nehmen"
    )


# ── Vorlagen-Platzhalter ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name,target", [
    ("ionos-<GROSS>", "openai/x"),
    ("chat-standard", "openai/<IONOS-CHAT-ID>"),
    ("chat-standard", "openai/TODO"),
])
def test_unreplaced_placeholders_are_errors(name, target):
    """Die Vorlage ist voller `<…>` — wer eines übersieht, soll es hier erfahren."""
    findings = check_config([_entry(name, target=target)], _settings(), bildarten=_BILDARTEN)

    assert any("Platzhalter" in m for m in _levels(findings, ERROR))


# ── Bildarten gegen die Proxy-Config ─────────────────────────────────────────
#
# Die Bildarten stehen in einer eigenen Datei; sie kann von der LiteLLM-Config abdriften,
# ohne dass es jemandem auffällt. Jeder Fund hier ist ein Fall, der sonst erst mitten im
# Gespräch scheitert.

def test_bildart_auf_unbekanntes_modell_ist_ein_fehler():
    errors = _levels(
        check_config(_healthy(), _settings(),
                     bildarten=[_bildart("comic", modell="bild-comic")]),
        ERROR,
    )

    assert any("bild-comic" in m and "comic" in m for m in errors)
    assert any("bild-standard" in m for m in errors), "Meldung soll die vorhandenen nennen"


def test_bildmodell_ohne_mode_ist_ein_fehler():
    """Ohne `mode: image_generation` taucht es in der Freigabe-Matrix nicht auf."""
    entries = _healthy()
    entries[3] = _entry("bild-standard", input_cost_per_image=0.032)  # mode fehlt

    errors = _levels(check_config(entries, _settings(), bildarten=_BILDARTEN), ERROR)

    assert any("image_generation" in m and "Freigabe-Matrix" in m for m in errors)


def test_fehlender_eintrag_in_image_prices_ist_eine_warnung():
    """Für Bilder greift NUR IMAGE_PRICES — ein Preis unter model_info bleibt wirkungslos."""
    entries = _healthy()
    entries[3] = _entry("bild-standard", target="openai/black-forest-labs/FLUX.1-schnell",
                        mode="image_generation")

    warnings = _levels(
        check_config(entries, _settings(), bildarten=_BILDARTEN, image_prices={}), WARNING
    )

    assert any("IMAGE_PRICES" in m and "0,00" in m for m in warnings)


def test_preis_wird_auch_ohne_provider_praefix_gefunden():
    """Config: `openai/<id>`, IMAGE_PRICES: `<id>` — beide Schreibweisen zählen."""
    entries = _healthy()
    entries[3] = _entry("bild-standard", target="openai/black-forest-labs/FLUX.1-schnell",
                        mode="image_generation")

    findings = check_config(
        entries, _settings(), bildarten=_BILDARTEN,
        image_prices={"black-forest-labs/FLUX.1-schnell": 0.032},
    )

    assert _levels(findings, WARNING) == []


def test_unbekannte_image_prices_melden_sich_als_ungeprueft():
    """None heißt „nicht prüfbar" (Proxy auf anderem Host) — kein Fehlalarm."""
    findings = check_config(_healthy(), _settings(), bildarten=_BILDARTEN, image_prices=None)

    assert any("nicht lesbar" in m for m in _levels(findings, INFO))
    assert _levels(findings, WARNING) == []


def test_bildmodell_ohne_bildart_wird_gemeldet():
    """Freischaltbar, aber von keinem Assistenten nutzbar — ein Eintrag fehlt."""
    entries = _healthy()
    entries.append(_entry("bild-flux2", mode="image_generation", input_cost_per_image=0.0152))

    infos = _levels(check_config(entries, _settings(), bildarten=_BILDARTEN), INFO)

    assert any("bild-flux2" in m and "ohne Bildart" in m for m in infos)


def test_zwei_bildarten_auf_einem_modell_melden_es_nicht_als_verwaist():
    entries = _healthy()

    infos = _levels(
        check_config(entries, _settings(),
                     bildarten=[_bildart("a"), _bildart("b")]),
        INFO,
    )

    assert not any("ohne Bildart" in m for m in infos)


# ── Währung in den Bildpreis-Meldungen (30.08.2026) ──────────────────────────

def _bildmodell(preis: float) -> list[dict]:
    return [{
        "model_name": "bild-flux2",
        "litellm_params": {"model": "black-forest-labs/FLUX.2-klein-4B",
                           "api_base": "https://example.invalid/v1"},
        "model_info": {"mode": "image_generation", "input_cost_per_image": preis},
    }]


def _bildpreis_meldung(*, waehrung: str, dokumentiert: float, wirksam: float) -> str:
    findings = check_config(
        _bildmodell(dokumentiert),
        _settings(litellm_price_currency=waehrung, image_default_model="bild-flux2"),
        bildarten=_BILDARTEN,
        image_prices={"black-forest-labs/FLUX.2-klein-4B": wirksam},
    )
    passende = [f.message for f in findings if "IMAGE_PRICES" in f.message and "model_info" in f.message]
    assert len(passende) == 1, findings
    return passende[0]


def test_bildpreis_meldung_nennt_euro_im_euro_betrieb():
    """Ein fest verdrahtetes „$" hat die Fehlersuche am 30.08.2026 in die Irre geführt."""
    meldung = _bildpreis_meldung(waehrung="EUR", dokumentiert=0.0131, wirksam=0.0152)
    assert "€/Bild" in meldung and "$/Bild" not in meldung


def test_bildpreis_meldung_nennt_dollar_im_dollar_betrieb():
    meldung = _bildpreis_meldung(waehrung="USD", dokumentiert=0.0131, wirksam=0.0152)
    assert "$/Bild" in meldung and "€/Bild" not in meldung


def test_kursverdacht_wird_benannt():
    """Der Produktivfall: 0,0131 gegen 0,0152 — Verhältnis 1,16."""
    meldung = _bildpreis_meldung(waehrung="EUR", dokumentiert=0.0131, wirksam=0.0152)
    assert "Wechselkurs" in meldung and "1.16" in meldung


def test_kein_kursverdacht_bei_deutlich_anderen_zahlen():
    """Ein Tippfehler um den Faktor 10 ist kein Währungsproblem — nicht falsch beraten."""
    meldung = _bildpreis_meldung(waehrung="EUR", dokumentiert=0.0131, wirksam=0.131)
    assert "Wechselkurs" not in meldung
