"""Was ein Suchtreffer dem **Modell** über sich sagt (Paket 9, AP3 und N11).

Hier — und nur hier — fällt die Entscheidung, welche Felder eines Knotens in einen
Prompt wandern. Die Suchschicht liefert die rohe Metadatenspalte mit
(``Suchprofil.mit_metadaten``); diese Auswahl macht daraus das, was das Modell zu sehen
bekommt. Wer eine Trefferliste daran vorbei serialisiert, umgeht sie — dann steht das
47-kB-SVG einer Strukturformel im Prompt.

⚠️ **Warum ein eigenes Modul und nicht `app/chat/router.py`** (Stand 26.09.2026): Bis
zur Vorab-Suche (N11) gab es genau einen Weg, auf dem Treffer zum Modell kamen — das
Werkzeug. Seither gibt es zwei: das Werkzeug **und** die Grundschicht, die zu jeder
Nachricht ungefragt sucht. Beide müssen dieselbe Auswahl treffen, sonst sähe das Modell
je nach Weg etwas anderes. Der Kontextdienst kann `app.chat.router` nicht importieren
(die Abhängigkeit läuft andersherum), also liegt die gemeinsame Entscheidung hier.

Die Tabelle, **welches** Feld je Knotenart erlaubt ist, steht in
:data:`app.context.taxonomy.MODELL_METADATA` — samt Begründung je Feld.
"""

import re

from app.context.taxonomy import modell_metadata_felder


# Wie viel eines Knoteninhalts das Modell im Suchergebnis sieht. Bemessen am Bestand:
# Kompetenzen liegen im Median bei 137 Zeichen, Leitideen bei 307, das 90. Perzentil
# reicht bis 775. 800 deckt also fast alles vollständig ab, und selbst bei der größten
# erlaubten Trefferzahl bleibt das Ergebnis im vierstelligen Tokenbereich.
INHALT_MAX_ZEICHEN = 800


# Eine Abbildung im Knotentext: `{{abbildung:EN_H2O.svg}}`.
#
# ⚠️ **Der Platzhalter ist die Absprache zwischen drei Stellen** (Paket 9): Das
# Seed-Skript setzt ihn anstelle der Obsidian-Einbettung `![[…]]` (AP5), die Oberfläche
# zeigt dort das SVG (AP6), und hier wird er zur Bildbeschreibung fürs Modell. Eine
# eigene Form statt der Vault-Syntax, weil der Text im Web-Editor bearbeitbar ist: Ein
# `![[…]]` dort sähe aus wie ein durchgerutschtes Artefakt, dies sieht aus wie das, was
# es ist. Und es bleibt sichtbar, wenn eine Seite ihn nicht auflöst, statt still zu
# verschwinden.
_ABBILDUNG = re.compile(r"\{\{abbildung:([^{}]+)\}\}")


def ohne_svg(wert):
    """Alle ``svg``-Schlüssel in jeder Tiefe entfernen, der Rest bleibt.

    ⚠️ **Ein SVG ist für das Modell nur Ballast** — im Pilot bis 47 kB je Bild, also
    mehr als der gesamte übrige Kontext einer Anfrage. Was es zeigt, steht daneben in
    ``beschreibung``; genau die soll das Modell lesen. Betroffen sind
    ``illustrationen[].svg`` (Fachbegriffe, Stoffsteckbriefe) und ``schaltzeichen.svg``
    (Bauteile).

    Offen für AP5: Führt das Seed-Skript unter ``tex`` künftig den **Quelltext** statt
    des Vault-Pfads, gehört der Schlüssel hier dazu — derselbe Ballast, andere Endung.
    """
    if isinstance(wert, dict):
        return {k: ohne_svg(v) for k, v in wert.items() if k != "svg"}
    if isinstance(wert, list):
        return [ohne_svg(v) for v in wert]
    return wert


def metadata_fuers_modell(content_type, metadata) -> dict:
    """Die Metadatenfelder dieses Knotentyps, die das Modell sehen darf.

    Die Auswahl steht als Whitelist je Typ in :data:`app.context.taxonomy.MODELL_METADATA`
    — dort auch die Begründung je Feld. Hier bleibt nur das Anwenden, samt SVG-Filter für
    den Fall, dass ein erlaubtes Feld selbst eine Grafik trägt (``schaltzeichen``).
    """
    if not isinstance(metadata, dict):
        return {}
    erlaubt = modell_metadata_felder(content_type)
    # Leere Werte weglassen: `"fassung": ""` an jedem Treffer ist Rauschen, und ein
    # leeres Feld sagt dem Modell nichts, was das Fehlen nicht auch sagte.
    return {
        feld: ohne_svg(metadata[feld])
        for feld in erlaubt
        if metadata.get(feld) not in (None, "", [], {})
    }


def abbildungen_aufgeloest(inhalt: str, metadata) -> str:
    """Bild-Einbettungen im Knotentext durch ihre Beschreibung ersetzen.

    Aus ``{{abbildung:EN_H2O.svg}}`` wird ``[Abbildung: Wassermolekül mit
    Partialladungen …]``. So weiß der Assistent **an der Stelle, an der das Bild
    steht**, was dort zu sehen ist — ohne dass ihm jemand das SVG vorlegt.

    Gefunden wird die Beschreibung über den **Dateinamen**, nicht über den ganzen Pfad:
    Im Vault steht im Text die bare Form (`EN_H2O.svg`), im Frontmatter eine
    Pfadangabe (`_Abb/EN_H2O.svg`). Welche von beiden das Seed-Skript in den Platzhalter
    schreibt, darf hier keine Rolle spielen — an genau dieser Stelle fänden die zwei
    Schreibweisen sonst nicht zusammen.

    Ohne passenden Eintrag bleibt ``[Abbildung]`` stehen: Dass dort ein Bild ist, gehört
    zur Aussage des Textes. Der Dateiname wandert bewusst **nicht** mit — er lädt dazu
    ein, ihn Lernenden gegenüber zu zitieren, und eine fehlende Beschreibung ist ein
    Importmangel, den der Bericht des Seed-Skripts meldet (AP5).
    """
    if "{{abbildung:" not in inhalt:
        return inhalt
    beschreibungen = {}
    if isinstance(metadata, dict):
        for abb in metadata.get("illustrationen") or []:
            if isinstance(abb, dict) and abb.get("datei"):
                name = str(abb["datei"]).rsplit("/", 1)[-1]
                beschreibungen[name] = (abb.get("beschreibung") or "").strip()

    def ersetze(treffer):
        name = treffer.group(1).strip().rsplit("/", 1)[-1]
        text = beschreibungen.get(name)
        return f"[Abbildung: {text}]" if text else "[Abbildung]"

    return _ABBILDUNG.sub(ersetze, inhalt)


def fuer_modell(
    treffer: list,
    abgrenzungen: dict | None = None,
    stufenvermerke: dict | None = None,
) -> list:
    """Suchergebnis für den LLM-Kontext aufbereiten.

    Bis 08/2026 bekam das Modell **nur die Titel**. Damit war jede Frage nach dem
    *Inhalt* des Wissensgraphen unbeantwortbar: Die Suche fand die richtigen Knoten, das
    Modell sah aber nur deren Überschriften und meldete, es gebe nichts. Deshalb geht der
    Inhalt jetzt mit — gekürzt, nicht weggelassen.

    Die interne ``node_id`` bleibt draußen: Sie nützt dem Modell nichts (kein Werkzeug
    nimmt sie entgegen) und taucht sonst in Antworten auf. Ergebnisse anderer Werkzeuge
    der Gruppe werden unverändert durchgereicht.

    ⚠️ **Hier fällt die Entscheidung, was das Modell sieht** (Paket 9, AP3). Die
    Suchschicht liefert seither die rohe Metadatenspalte mit (`mit_metadaten`); diese
    Funktion ist die einzige Stelle, die daraus auswählt. Wer eine Trefferliste am
    Werkzeugweg vorbei serialisiert, umgeht die Auswahl — dann steht das 47-kB-SVG einer
    Strukturformel im Prompt.

    ``abgrenzungen`` kommt aus :func:`app.context.search.abgrenzungen_zu` — je Knoten
    die Sätze, die ihn von ähnlichen unterscheiden. ``stufenvermerke`` aus
    :mod:`app.context.stufen`. Beide brauchen eine Datenbank und können hier deshalb
    nicht selbst geholt werden.
    """
    aufbereitet = []
    for t in treffer:
        if not isinstance(t, dict) or "node_id" not in t:
            aufbereitet.append(t)          # fremde Form (z. B. get_operatoren)
            continue
        # `subject_id` ist eine interne Zahl — für das Modell wertlos und irreführend.
        # Sie wird durch den Fachnamen ersetzt, den `fach` trägt.
        eintrag = {
            k: v for k, v in t.items()
            if k not in ("node_id", "content", "subject_id", "fach", "metadata",
                         "aliase")
        }
        if t.get("fach"):
            eintrag["fach"] = t["fach"]
        # ⚠️ **Aliase beschriftet, nicht nackt** (Paket 9, N1). Unter `aliase` standen
        # sie gleichberechtigt neben `bevorzugter_begriff` — und das Modell verwendete
        # sie: In Szenario (f) antwortete es mit „Wasserstoffbrückenbindung", obwohl
        # der Knoten „Wasserstoffbrücken" heißt und den anderen Ausdruck nur als
        # Suchbegriff führt. `_Format.md` sagt es deutlich: Aliase sind das, **wonach
        # gefragt wird**, auch in schiefer Form („Mol" für die Stoffmenge).
        #
        # Im **Embedding** und im **Namensabgleich** bleiben sie unverändert — dort
        # sind sie richtig, und drei Prüfsatzfälle halten das fest.
        if t.get("aliase"):
            eintrag["suchbegriffe"] = list(t["aliase"])
        hinweise = (abgrenzungen or {}).get(str(t["node_id"]))
        if hinweise:
            eintrag["abgrenzungen"] = hinweise
        # ⚠️ **Nur wo etwas nicht passt** (Paket 9, N6). Ein Vermerk an jedem Treffer
        # wäre Rauschen; er soll auffallen.
        vermerk = (stufenvermerke or {}).get(str(t["node_id"]))
        if vermerk:
            eintrag["stufe"] = vermerk
        eintrag |= metadata_fuers_modell(t.get("content_type"), t.get("metadata"))
        inhalt = (t.get("content") or "").strip()
        if inhalt:
            # ⚠️ **Auflösen vor dem Kürzen.** Andersherum bliebe ein halber Platzhalter
            # stehen (`{{abbildung:EN_H`). Der Preis: Eine Bildbeschreibung ist rund
            # 200 Zeichen lang und verdrängt damit ein Viertel des Kürzungsbudgets —
            # AP7 misst, ob 800 Zeichen für Begriffe noch reichen.
            inhalt = abbildungen_aufgeloest(inhalt, t.get("metadata"))
            eintrag["content"] = (
                inhalt[:INHALT_MAX_ZEICHEN] + " …"
                if len(inhalt) > INHALT_MAX_ZEICHEN
                else inhalt
            )
        aufbereitet.append(eintrag)
    return aufbereitet
