#!/usr/bin/env python3
"""
Misst, **wie** LiteLLM ein Bildmodell abrechnet — Vorarbeit zum Mehrmodell-Plan.

**Diagnosewerkzeug, kein Produktcode.** Es erzeugt echte Bilder (kostet Geld) und liest
Kosten; an der Konfiguration ändert es nichts.

## Die Frage

`IMAGE_PRICES` + der Callback `guardrails.bildpreise` registrieren einen **festen Preis je
Bild** (`input_cost_per_image`). Für FLUX.1-schnell stimmt das — ein Bild, ein Preis.
FLUX.2-klein rechnet dagegen **nach Megapixeln** ab (Preisliste 27./28.08.2026: 0,014 $ für
das erste MP, 0,001 $ für jedes weitere). Ein fester Preis je Bild bildet das nur dann
richtig ab, wenn alle Formate ähnlich groß sind.

Offen und **nicht** aus der Doku zu beantworten ist deshalb:

  A  Wird überhaupt etwas gebucht? (`x-litellm-response-cost` ≠ 0 **und** Spend am Key)
  B  Nach welcher Regel? Fester Preis je Bild, linear nach Pixeln, oder gar nichts?
  C  Wie weit liegt das vom echten IONOS-Tarif entfernt — je Format und in Summe?
  D  Stimmen Header und SpendLog überein? Der Header speist die Anzeige
     (`LiteLLMClient.generate_image`), der SpendLog das Budget. Gehen sie auseinander,
     lügt die Kostenanzeige, ohne dass etwas fehlschlägt.

Gemessen wird über einen **eigens angelegten Virtual Key** — also auf demselben Weg, den
auch der Chat nimmt. Nur so ist sichtbar, ob das Budget tatsächlich belastet wird; der
Master-Key würde am Nutzerbudget vorbeilaufen. Der Key wird am Ende gelöscht; der dabei
angelegte LiteLLM-Nutzer `bildpreis-probe` bleibt bestehen (harmlos, sammelt die Läufe).

## Größen wählen

Die Regel (B) lässt sich nur unterscheiden, wenn die Testgrößen **deutlich verschiedene
Pixelzahlen** haben. 1024×1024 (1,05 MP) und 1344×768 (1,03 MP) sind praktisch gleich groß
— daran sieht man nichts. Die Vorgabe nimmt deshalb 512², 1024² und 1536² (0,26 / 1,05 /
2,36 MP). Lehnt das Modell eine Größe ab, wird sie übersprungen; für eine Aussage braucht
es mindestens zwei erfolgreiche Messungen.

Das Skript liest zusätzlich **Breite und Höhe aus den Bildbytes**. Liefert der Anbieter
stillschweigend eine andere Größe als bestellt, ist jede Preisrechnung hinfällig — und
genau das sieht man sonst nirgends.

## Zugang

Aus der Umgebung oder der `.env` im Repo-Wurzelverzeichnis. Nichts davon wird ausgegeben:

    LITELLM_PROXY_URL=http://localhost:4000
    LITELLM_MASTER_KEY=<Master-Key des Proxys>

## Verwendung

    python scripts/bildpreis_probe.py bild-standard
    python scripts/bildpreis_probe.py bild-flux2 --groessen 512x512,1024x1024,1536x1536
    python scripts/bildpreis_probe.py bild-flux2 --tarif-erstes-mp 0.014 --tarif-weitere-mp 0.001
    python scripts/bildpreis_probe.py bild-flux2 --ja        # ohne Rückfrage

`modell` ist der **`model_name` aus der LiteLLM-Config** (der Aliasname, z. B.
`bild-standard`), nicht die Anbieter-ID.
"""

from __future__ import annotations

import argparse
import base64
import math
import os
import struct
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

WURZEL = Path(__file__).resolve().parent.parent
STANDARD_PROXY = "http://localhost:4000"
TIMEOUT = httpx.Timeout(180.0, connect=15.0)
STANDARD_GROESSEN = "512x512,1024x1024,1536x1536"

# IONOS-Preisliste FLUX.2-klein-4B, gelesen am 27./28.08.2026. Vor dem Lauf gegenprüfen —
# Anbieter ändern Preise, und ein falscher Sollwert macht den ganzen Vergleich wertlos.
#
# ⚠️ Diese Staffel ist fast flach: 0,26 MP kosten 0,0140 $, 2,36 MP kosten 0,0154 $ — über
# den ganzen Bereich rund 10 % Unterschied. Trifft der Sollwert zu, ist ein **fester Preis
# je Bild** für dieses Modell eine gute Näherung, und die Frage nach `input_cost_per_pixel`
# erledigt sich. Der Lauf lohnt trotzdem: Ob überhaupt gebucht wird (A) und ob Header und
# SpendLog übereinstimmen (D), hängt nicht am Tarif.
TARIF_ERSTES_MP = 0.013
TARIF_WEITERE_MP = 0.001
# Die IONOS-Preisliste steht in **EUR**, LiteLLM bucht in **USD**. Ohne Umrechnung
# erschiene der Wechselkurs als Abrechnungsfehler. Der Wert ist der Faktor, mit dem die
# vorhandenen IMAGE_PRICES gebildet wurden (0,0288 € → 0,032 $); bei Bedarf nachführen.
TARIF_KURS = 1.1111

# Der Prompt ist bewusst banal und für alle Größen gleich: gemessen wird der Preis, nicht
# die Bildqualität. Kurz, damit kein Modell ihn als Anlass für lange Denkspuren nimmt.
PROMPT = "Ein einfacher roter Würfel auf weißem Grund"


# ── Zugang ──────────────────────────────────────────────────────────────────────────


def _aus_env_datei(name: str) -> str | None:
    """Liest einen Wert aus der `.env` im Repo-Wurzelverzeichnis (nur wenn nötig)."""
    pfad = WURZEL / ".env"
    if not pfad.is_file():
        return None
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, _, wert = zeile.partition("=")
        if schluessel.strip() == name:
            return wert.strip().strip("'\"") or None
    return None


def _zugang() -> tuple[str, str]:
    key = os.environ.get("LITELLM_MASTER_KEY") or _aus_env_datei("LITELLM_MASTER_KEY")
    if not key:
        sys.exit(
            "FEHLER: LITELLM_MASTER_KEY fehlt — weder in der Umgebung noch in der .env.\n"
            "Ohne Master-Key lässt sich kein Virtual Key anlegen und kein SpendLog lesen."
        )
    base = (
        os.environ.get("LITELLM_PROXY_URL")
        or _aus_env_datei("LITELLM_PROXY_URL")
        or STANDARD_PROXY
    )
    return key, base.rstrip("/")


def _fehler(antwort: httpx.Response) -> str:
    """Fehlertext ohne Schlüssel — der Body kann alles enthalten, deshalb gekürzt."""
    text = antwort.text.strip()
    return f"HTTP {antwort.status_code}: {text[:400] or '(leerer Body)'}"


# ── Bildmaße aus den Bytes ──────────────────────────────────────────────────────────


def _bildmasse(daten: bytes) -> tuple[int, int] | None:
    """Breite/Höhe aus PNG- oder JPEG-Bytes. None, wenn das Format unbekannt ist.

    Zweck ist nicht Vollständigkeit, sondern die Gegenprobe: Wurde wirklich die bestellte
    Größe geliefert? Ein Modell, das jede Anfrage auf 1024² zurechtstutzt, ließe eine
    Pixelpreis-Messung sonst wie eine Bildpreis-Messung aussehen.
    """
    if daten[:8] == b"\x89PNG\r\n\x1a\n" and len(daten) >= 24:
        breite, hoehe = struct.unpack(">II", daten[16:24])
        return int(breite), int(hoehe)

    if daten[:2] == b"\xff\xd8":  # JPEG: SOF-Marker suchen
        i = 2
        while i + 9 < len(daten):
            if daten[i] != 0xFF:
                i += 1
                continue
            marker = daten[i + 1]
            # SOF0–SOF15 tragen die Maße; DHT/DAC/RST/SOS nicht.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                hoehe, breite = struct.unpack(">HH", daten[i + 5 : i + 9])
                return int(breite), int(hoehe)
            if i + 4 > len(daten):
                break
            laenge = struct.unpack(">H", daten[i + 2 : i + 4])[0]
            if laenge < 2:
                break
            i += 2 + laenge
    return None


def _megapixel(breite: int, hoehe: int) -> float:
    return breite * hoehe / 1_000_000


# ── Messung ─────────────────────────────────────────────────────────────────────────


@dataclass
class Messung:
    groesse: str            # bestellt, z. B. "1024x1024"
    ok: bool
    fehler: str | None = None
    header_kosten: float | None = None   # x-litellm-response-cost
    request_id: str | None = None
    log_kosten: float | None = None      # aus /spend/logs/v2
    bytes_gross: int | None = None
    ist_breite: int | None = None        # tatsächlich geliefert
    ist_hoehe: int | None = None
    sekunden: float | None = None

    @property
    def mp(self) -> float | None:
        if self.ist_breite and self.ist_hoehe:
            return _megapixel(self.ist_breite, self.ist_hoehe)
        return None


def schluessel_anlegen(client: httpx.Client, master: str, modell: str) -> str:
    """Wegwerf-Key mit `user_id`, damit der Spend zuordenbar ist (wie im Chat-Pfad)."""
    antwort = client.post(
        "/key/generate",
        headers={"Authorization": f"Bearer {master}", "Content-Type": "application/json"},
        json={
            "user_id": "bildpreis-probe",
            "key_alias": f"bildpreis-probe-{int(time.time())}",
            "models": [modell],
        },
    )
    if antwort.status_code not in (200, 201):
        sys.exit(f"FEHLER: Virtual Key konnte nicht angelegt werden — {_fehler(antwort)}")
    return antwort.json()["key"]


def schluessel_loeschen(client: httpx.Client, master: str, key: str) -> bool:
    antwort = client.post(
        "/key/delete",
        headers={"Authorization": f"Bearer {master}", "Content-Type": "application/json"},
        json={"keys": [key]},
    )
    return antwort.status_code in (200, 204, 404)


def schluessel_spend(client: httpx.Client, master: str, key: str) -> float | None:
    """Gebuchter Spend des Keys. **Das ist die budgetrelevante Zahl** — nicht der Header."""
    antwort = client.get(
        "/key/info", headers={"Authorization": f"Bearer {master}"}, params={"key": key}
    )
    if antwort.status_code != 200:
        return None
    info = antwort.json().get("info") or {}
    spend = info.get("spend")
    try:
        return float(spend) if spend is not None else None
    except (TypeError, ValueError):
        return None


def warte_auf_spend(
    client: httpx.Client, master: str, key: str, vorher: float | None, geduld: float = 45.0
) -> float | None:
    """Wartet, bis der Spend sich bewegt — LiteLLM schreibt SpendLogs **verzögert**.

    Gemessen am 28.08.2026: rund 10 Sekunden zwischen Antwort und sichtbarem Spend. Ohne
    diese Warteschleife meldete die Probe „Das Budget wurde NICHT belastet" — der
    alarmierendste Satz des ganzen Berichts, und schlicht falsch. Nach Ablauf der Geduld
    wird der letzte gelesene Wert zurückgegeben; dann ist die Aussage wieder ehrlich.
    """
    ende = time.monotonic() + geduld
    letzter = schluessel_spend(client, master, key)
    while time.monotonic() < ende:
        if letzter is not None and (vorher is None or letzter > vorher):
            return letzter
        time.sleep(2.0)
        letzter = schluessel_spend(client, master, key)
    return letzter


def bild_erzeugen(client: httpx.Client, key: str, modell: str, groesse: str) -> Messung:
    """Ein Bild über den Proxy — derselbe Weg wie `LiteLLMClient.generate_image`."""
    beginn = time.monotonic()
    try:
        antwort = client.post(
            "/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": modell, "prompt": PROMPT, "n": 1, "size": groesse},
        )
    except httpx.HTTPError as e:
        return Messung(groesse=groesse, ok=False, fehler=f"Verbindungsfehler: {e}")
    dauer = time.monotonic() - beginn

    if antwort.status_code != 200:
        return Messung(groesse=groesse, ok=False, fehler=_fehler(antwort), sekunden=dauer)

    roh = antwort.headers.get("x-litellm-response-cost")
    try:
        header_kosten = float(roh) if roh else None
    except (TypeError, ValueError):
        header_kosten = None

    request_id = (
        antwort.headers.get("x-litellm-call-id")
        or antwort.headers.get("x-litellm-response-id")
    )

    daten = (antwort.json().get("data") or [{}])[0]
    b64 = daten.get("b64_json")
    if not b64:
        hinweis = "URL statt Base64" if daten.get("url") else "weder b64_json noch url"
        return Messung(
            groesse=groesse, ok=False, fehler=f"Keine Bildbytes ({hinweis})",
            header_kosten=header_kosten, request_id=request_id, sekunden=dauer,
        )

    bild = base64.b64decode(b64)
    masse = _bildmasse(bild)
    return Messung(
        groesse=groesse,
        ok=True,
        header_kosten=header_kosten,
        request_id=request_id,
        bytes_gross=len(bild),
        ist_breite=masse[0] if masse else None,
        ist_hoehe=masse[1] if masse else None,
        sekunden=dauer,
    )


def spendlog_abfragen(
    client: httpx.Client, master: str, request_id: str, geduld: float = 20.0
) -> float | None:
    """SpendLog je Request — LiteLLM schreibt ihn asynchron, deshalb mit Warteschleife."""
    heute = date.today()
    params = {
        "request_id": request_id,
        "start_date": (heute - timedelta(days=1)).isoformat(),
        "end_date": (heute + timedelta(days=1)).isoformat(),
    }
    ende = time.monotonic() + geduld
    while True:
        antwort = client.get(
            "/spend/logs/v2",
            headers={"Authorization": f"Bearer {master}"},
            params=params,
        )
        if antwort.status_code == 200:
            eintraege = antwort.json().get("data") or []
            if eintraege:
                spend = eintraege[0].get("spend")
                try:
                    return float(spend) if spend is not None else None
                except (TypeError, ValueError):
                    return None
        if time.monotonic() >= ende:
            return None
        time.sleep(2.0)


# ── Auswertung ──────────────────────────────────────────────────────────────────────


def regel_ableiten(messungen: list[Messung]) -> tuple[str, str]:
    """Leitet aus ≥2 Messungen die angewandte Preisregel ab → (Kennung, Klartext)."""
    brauchbar = [
        m for m in messungen
        if m.ok and m.header_kosten is not None and m.mp is not None and m.mp > 0
    ]
    if len(brauchbar) < 2:
        return "unklar", "Zu wenige erfolgreiche Messungen (mindestens zwei nötig)."

    kosten = [m.header_kosten for m in brauchbar]
    if all(k == 0 for k in kosten):
        return "keine", "Es wird nichts gebucht — jedes Bild kostet 0,00 $."

    # Streuung ohne statistics-Import: relative Spannweite um den Mittelwert.
    def _konstant(werte: list[float], toleranz: float = 0.02) -> bool:
        mittel = sum(werte) / len(werte)
        if mittel == 0:
            return False
        return (max(werte) - min(werte)) / mittel <= toleranz

    if _konstant(kosten):
        return (
            "pro_bild",
            "Fester Preis je Bild — die Größe spielt keine Rolle "
            "(`input_cost_per_image` greift).",
        )

    je_pixel = [m.header_kosten / m.mp for m in brauchbar]
    if _konstant(je_pixel, toleranz=0.05):
        mittel = sum(je_pixel) / len(je_pixel)
        return (
            "pro_pixel",
            f"Linear nach Fläche — rund {mittel:.5f} $ je Megapixel "
            "(`input_cost_per_pixel` greift).",
        )

    return (
        "unklar",
        "Die Kosten ändern sich mit der Größe, aber weder konstant noch linear. "
        "Womöglich eine gestaffelte Tabelle — die Einzelwerte oben zeigen es.",
    )


def tarif_soll(
    mp: float, erstes: float, weitere: float, aufgerundet: bool, kurs: float = 1.0
) -> float:
    """Sollpreis nach dem Staffeltarif „erstes MP … , jedes weitere …".

    Die Preisliste sagt nicht, ob angefangene Megapixel voll zählen. Deshalb rechnet das
    Skript beide Lesarten und zeigt sie nebeneinander.

    `kurs` rechnet die Preisliste in die Buchungswährung um. **Das ist keine Feinheit:**
    LiteLLM bucht in USD, die IONOS-Preisliste steht in EUR — ohne Umrechnung schlägt der
    Wechselkurs (~11 %) als vermeintliche Abrechnungsabweichung durch und verdeckt den
    tatsächlichen Fehler von wenigen Prozent.
    """
    rest = max(0.0, mp - 1.0)
    if aufgerundet:
        rest = float(math.ceil(rest))
    return (erstes + weitere * rest) * kurs


def _eur(betrag: float | None) -> str:
    return "—" if betrag is None else f"{betrag:.6f}"


def bericht(
    messungen: list[Messung], erstes: float, weitere: float, kurs: float = 1.0
) -> str:
    print()
    print("── Messwerte ───────────────────────────────────────────────────────────────")
    kopf = (
        f"{'bestellt':>11}  {'geliefert':>11}  {'MP':>5}  {'Header $':>10}  "
        f"{'SpendLog $':>10}  {'KB':>6}  {'s':>5}"
    )
    print(kopf)
    for m in messungen:
        if not m.ok:
            print(f"{m.groesse:>11}  FEHLER: {m.fehler}")
            continue
        geliefert = (
            f"{m.ist_breite}x{m.ist_hoehe}" if m.ist_breite else "unbekannt"
        )
        warnung = ""
        if m.ist_breite and geliefert != m.groesse:
            warnung = "  ⚠️ abweichend"
        print(
            f"{m.groesse:>11}  {geliefert:>11}  "
            f"{(f'{m.mp:.2f}' if m.mp else '—'):>5}  "
            f"{_eur(m.header_kosten):>10}  {_eur(m.log_kosten):>10}  "
            f"{(m.bytes_gross // 1024 if m.bytes_gross else 0):>6}  "
            f"{(f'{m.sekunden:.1f}' if m.sekunden else '—'):>5}{warnung}"
        )

    kennung, klartext = regel_ableiten(messungen)

    print()
    print("── B  Angewandte Preisregel ────────────────────────────────────────────────")
    print(f"   {klartext}")

    # ── D  Header gegen SpendLog
    abweichungen = [
        m for m in messungen
        if m.ok and m.header_kosten is not None and m.log_kosten is not None
        and abs(m.header_kosten - m.log_kosten) > 1e-9
    ]
    print()
    print("── D  Header gegen SpendLog ────────────────────────────────────────────────")
    mit_header = [m for m in messungen if m.ok and m.header_kosten is not None]
    mit_log = [m for m in messungen if m.log_kosten is not None]
    if not mit_header and any(m.ok for m in messungen):
        # Kein Vergleich, sondern ein Befund: Ohne `x-litellm-response-cost` bucht auch
        # `LiteLLMClient.generate_image` nichts — die Kostenanzeige bliebe leer.
        print("   ⚠️ Der Header `x-litellm-response-cost` fehlt bei ALLEN Antworten —")
        print("      LiteLLM hat für dieses Modell gar keine Kosten berechnet. Vergleich")
        print("      gegenstandslos; siehe Abschnitt A.")
    elif not mit_log:
        print("   Kein SpendLog-Eintrag gefunden — Vergleich nicht möglich.")
        print("   (Ohne Request-ID im Header oder bei abgeschalteter Protokollierung normal.)")
    elif abweichungen:
        print("   ⚠️ Header und SpendLog weichen ab — die Kostenanzeige im Chat stimmt dann")
        print("      nicht mit dem überein, was das Budget belastet:")
        for m in abweichungen:
            print(
                f"      {m.groesse}: Header {_eur(m.header_kosten)} ≠ "
                f"SpendLog {_eur(m.log_kosten)}"
            )
    else:
        print("   ✅ Identisch — Anzeige und Budget rechnen mit derselben Zahl.")

    # ── C  Vergleich mit dem Staffeltarif
    print()
    print("── C  Vergleich mit dem Staffeltarif ───────────────────────────────────────")
    print(f"   Preisliste: {erstes:.4f} erstes MP, {weitere:.4f} je weiteres MP"
          + (f"  ×{kurs} → USD" if kurs != 1.0 else "  (bereits USD)"))
    if kurs == 1.0:
        print("   ⚠️ Ohne --tarif-kurs wird die Preisliste als USD gelesen. Steht sie in")
        print("      EUR, erscheint der Wechselkurs (~11 %) als Abrechnungsfehler.")
    if kennung == "keine":
        print("   Entfällt — es wird nichts gebucht.")
    else:
        print(
            f"   {'Größe':>11}  {'gebucht $':>10}  {'soll linear':>12}  "
            f"{'soll aufger.':>12}  {'Abw. linear':>12}"
        )
        summe_ist = summe_soll = 0.0
        for m in messungen:
            if not (m.ok and m.header_kosten is not None and m.mp):
                continue
            soll_lin = tarif_soll(m.mp, erstes, weitere, aufgerundet=False, kurs=kurs)
            soll_auf = tarif_soll(m.mp, erstes, weitere, aufgerundet=True, kurs=kurs)
            abw = (m.header_kosten - soll_lin) / soll_lin * 100 if soll_lin else 0.0
            summe_ist += m.header_kosten
            summe_soll += soll_lin
            print(
                f"   {m.groesse:>11}  {m.header_kosten:>10.6f}  {soll_lin:>12.6f}  "
                f"{soll_auf:>12.6f}  {abw:>11.1f}%"
            )
        if summe_soll:
            gesamt = (summe_ist - summe_soll) / summe_soll * 100
            print(f"   {'Summe':>11}  {summe_ist:>10.6f}  {summe_soll:>12.6f}"
                  f"  {'':>12}  {gesamt:>11.1f}%")
    return kennung


def empfehlung(kennung: str, messungen: list[Messung]) -> None:
    print()
    print("── Was daraus folgt ────────────────────────────────────────────────────────")
    if kennung == "keine":
        print("   ❌ Das Modell ist so NICHT freizugeben. Jedes Bild kostet 0,00 $, damit")
        print("      laufen EUR-Budget, 429-Sperre und Kostenstatistik ins Leere — ohne dass")
        print("      irgendetwas fehlschlägt.")
        print("      Prüfen: Steht das Modell in IMAGE_PRICES? Ist der Callback")
        print("      `guardrails.bildpreise.registrierung` in litellm_settings.callbacks")
        print("      eingetragen? Wurde der Proxy danach neu gestartet?")
    elif kennung == "pro_bild":
        werte = [m.mp for m in messungen if m.ok and m.mp]
        spanne = f"{min(werte):.2f}–{max(werte):.2f} MP" if werte else "?"
        print("   Fester Preis je Bild. Für ein megapixelbasiertes Modell heißt das: Der")
        print(f"   Preis stimmt nur bei einer Größe. Über die getestete Spanne ({spanne})")
        print("   liegt die Abrechnung entsprechend daneben (Tabelle C).")
        print()
        print("   Zwei Wege:")
        print("   a) Eine Bildart je Größenklasse anlegen und jeweils passend bepreisen —")
        print("      geht ohne Codeänderung, weil `IMAGE_PRICES` je Modell greift, kostet")
        print("      aber je Größe einen eigenen LiteLLM-Eintrag.")
        print("   b) `bildpreise.py` um `input_cost_per_pixel` erweitern — nur sinnvoll,")
        print("      wenn der nächste Punkt zutrifft.")
    elif kennung == "pro_pixel":
        print("   ✅ Der Bild-Kostenrechner wertet die Fläche aus. Damit lässt sich ein")
        print("      megapixelbasierter Tarif sauber abbilden: `bildpreise.py` registriert")
        print("      dann `input_cost_per_pixel` statt `input_cost_per_image`.")
        print("      Rest-Ungenauigkeit bleibt die Staffel (erstes MP teurer als die")
        print("      weiteren) — ein linearer Preis über- oder unterzeichnet die Ränder.")
    else:
        print("   Unklar. Die Einzelwerte oben zeigen, wie sich die Kosten mit der Größe")
        print("   verhalten; erst danach über die Bepreisung entscheiden.")

    abweichende = [
        m for m in messungen
        if m.ok and m.ist_breite and f"{m.ist_breite}x{m.ist_hoehe}" != m.groesse
    ]
    if abweichende:
        print()
        print("   ⚠️ Das Modell hat nicht in der bestellten Größe geliefert:")
        for m in abweichende:
            print(f"      bestellt {m.groesse} → geliefert {m.ist_breite}x{m.ist_hoehe}")
        print("      Solange das so ist, sind alle Formatangaben in `image_models.yaml`")
        print("      für dieses Modell Fiktion — und eine Flächenrechnung ohnehin.")


# ── Ablauf ──────────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Misst, wie LiteLLM ein Bildmodell abrechnet (erzeugt echte Bilder).",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("modell", help="model_name aus der LiteLLM-Config, z. B. bild-standard")
    p.add_argument(
        "--groessen", default=STANDARD_GROESSEN,
        help=f"Kommaliste, Vorgabe: {STANDARD_GROESSEN} (deutlich verschiedene Flächen wählen)",
    )
    p.add_argument("--tarif-erstes-mp", type=float, default=TARIF_ERSTES_MP,
                   help=f"Sollpreis erstes Megapixel laut Preisliste (Vorgabe {TARIF_ERSTES_MP})")
    p.add_argument("--tarif-weitere-mp", type=float, default=TARIF_WEITERE_MP,
                   help=f"Sollpreis je weiteres Megapixel (Vorgabe {TARIF_WEITERE_MP})")
    p.add_argument("--tarif-kurs", type=float, default=TARIF_KURS,
                   help=f"Umrechnung Preisliste → USD (Vorgabe {TARIF_KURS}; "
                        "IONOS listet in EUR, LiteLLM bucht in USD)")
    p.add_argument("--ja", action="store_true", help="Ohne Rückfrage starten")
    args = p.parse_args()

    groessen = [g.strip() for g in args.groessen.split(",") if g.strip()]
    if not groessen:
        sys.exit("FEHLER: --groessen ist leer.")

    master, base = _zugang()

    print("Bildpreis-Probe")
    print(f"  Proxy   : {base}")
    print(f"  Modell  : {args.modell}")
    print(f"  Größen  : {', '.join(groessen)}")
    print()
    print(f"  ⚠️ Es werden {len(groessen)} echte Bilder erzeugt. Das kostet Geld —")
    print("     bei FLUX-Modellen grob 0,01–0,03 $ je Bild.")
    if not args.ja:
        try:
            if input("     Fortfahren? [j/N] ").strip().lower() not in ("j", "ja"):
                sys.exit("Abgebrochen.")
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nAbgebrochen.")

    with httpx.Client(base_url=base, timeout=TIMEOUT) as client:
        key = schluessel_anlegen(client, master, args.modell)
        print("\n   Virtual Key angelegt (wird am Ende gelöscht).")
        spend_vorher = schluessel_spend(client, master, key)

        messungen: list[Messung] = []
        try:
            for groesse in groessen:
                print(f"   … {groesse}", flush=True)
                messungen.append(bild_erzeugen(client, key, args.modell, groesse))

            for m in messungen:
                if m.ok and m.request_id:
                    m.log_kosten = spendlog_abfragen(client, master, m.request_id)

            # Nicht sofort lesen — der SpendLog erscheint mit Verzögerung.
            spend_nachher = warte_auf_spend(client, master, key, spend_vorher)

            kennung = bericht(
                messungen, args.tarif_erstes_mp, args.tarif_weitere_mp, args.tarif_kurs
            )

            print()
            print("── A  Belastung des Budgets ────────────────────────────────────────────────")
            if spend_vorher is None or spend_nachher is None:
                print("   Spend am Key nicht lesbar (/key/info) — Budgetpfad ungeprüft.")
            else:
                delta = spend_nachher - spend_vorher
                summe_header = sum(
                    m.header_kosten for m in messungen
                    if m.ok and m.header_kosten is not None
                )
                print(f"   Spend am Key: {spend_vorher:.6f} → {spend_nachher:.6f} $"
                      f"  (Δ {delta:.6f})")
                print(f"   Summe der Header-Kosten:              {summe_header:.6f} $")
                if delta <= 0:
                    print("   ❌ Das Budget wurde NICHT belastet. Genau der Fall, in dem")
                    print("      Schüler:innen unbegrenzt Bilder erzeugen könnten.")
                elif abs(delta - summe_header) > max(1e-6, 0.02 * summe_header):
                    print("   ⚠️ Budget und Anzeige gehen auseinander (>2 %). Maßgeblich fürs")
                    print("      Budget ist der Spend, angezeigt wird der Header.")
                else:
                    print("   ✅ Budget wurde belastet, passend zur angezeigten Summe.")

            empfehlung(kennung, messungen)
        finally:
            if schluessel_loeschen(client, master, key):
                print("\n   Virtual Key gelöscht.")
            else:
                print("\n   ⚠️ Virtual Key konnte nicht gelöscht werden — bitte in der")
                print("      LiteLLM-UI entfernen (user_id 'bildpreis-probe').")


if __name__ == "__main__":
    main()
