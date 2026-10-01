"""Was das Modell bei einem Krisentreffer zu tun hat (Paket 1 von 0.12, AP3).

**Warum es diese Schicht gibt.** Ein Krisentreffer erzeugte bis 0.12 ein Banner, ein
pseudonymes Flag und eine Benachrichtigung — **die Antwort selbst blieb unberührt**. Wie
das Modell mit der Nachricht umgeht, hing allein an Punkt 3 der Präambel. Dieselbe
Konstruktion hat bei den Hausversuchen nicht getragen: Punkt 8 verbietet gefährliche
Versuchsvorschläge und wurde am 26.09.2026 gemessen in 18 von 20 Läufen überlesen. Für
Punkt 3 gibt es keinen Grund, auf mehr zu hoffen.

Wie bei N12 wird daraus deshalb eine **konkrete Anweisung für genau diese Antwort**, und
sie steht als **allerletzte** Systemnachricht — nach der Hausversuchs-Anweisung, falls
beide greifen.

⚠️ **Dieser Text wird mit dem Update aktiv, ohne dass eine Schule etwas tut.** Anders als
die Muster in ``crisis_triggers.example.yaml``, die man übernehmen muss, ist er Vorgabe im
Code: kein Vorschlag, den man annimmt, sondern Verhalten, das man abbestellt. Er muss
deshalb ohne jede schulspezifische Abstimmung vertretbar sein — zurückhaltend, ohne
Mengen, ohne Diagnose, ohne Versprechen. Wer ihn anders will, setzt ``anweisung:`` an der
Kategorie in ``crisis_triggers.yaml``.

⚠️ **Kein Verweis auf das eingeblendete Hilfe-Banner.** Es erscheint nur beim **ersten**
Treffer einer Kategorie je Konversation (``show_banner`` in ``app/chat/router.py``); ein
Satz wie „die Angebote unter dieser Nachricht" wäre ab dem zweiten Treffer schlicht
falsch. Stattdessen das Verbot, Nummern zu erfinden: Eine halluzinierte Hotline ist in
genau dieser Lage der denkbar schlechteste Fehler.

⚠️ **Es ist keine Sperre.** Der Chat läuft weiter; die Anweisung ändert den Ton und die
Grenzen der Antwort, nicht den Zugang.
"""

from __future__ import annotations

from app.crisis.detector import CrisisHit

#: Gilt für **alle** Kategorien, nicht nur für neue — die fehlende Anweisung betraf
#: Suizidalität und Selbstverletzung genauso.
STANDARD = (
    "Diese Nachricht kann auf eine persönliche Notlage hindeuten. Nenne keine Mengen, "
    "Mittel oder Methoden, auch nicht zur Information oder auf Nachfrage. Sprich die "
    "Person direkt, ruhig und ohne Vorwurf an und frage, wie es ihr geht. Stelle keine "
    "Diagnose. Weise darauf hin, dass sie sich Hilfe holen kann — bei einer "
    "Vertrauensperson, in der Schule oder bei einer Beratungsstelle; erfinde dabei keine "
    "Telefonnummern, Adressen oder Öffnungszeiten."
)


def anweisung_fuer(hit: CrisisHit) -> str:
    """Der Text für diesen Treffer — eigener aus der Konfiguration, sonst der Standard."""
    eigener = (hit.anweisung or "").strip()
    return eigener or STANDARD
