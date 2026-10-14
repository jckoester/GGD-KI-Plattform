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

import json
import re

from app.context.taxonomy import modell_metadata_felder
from app.pedagogy.config import load_pedagogy


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
    ergebnis: dict = {}
    for feld in modell_metadata_felder(content_type):
        # Ein Punktpfad (`schaltzeichen.kennung`) holt ein **einzelnes** Unterfeld und
        # legt es unter demselben Pfad ab — so kommt nicht das ganze Objekt mit, nur
        # weil ein Teil davon gebraucht wird (F6: die Norm eines Schaltzeichens nicht).
        *eltern, blatt = feld.split(".")
        quelle, ziel = metadata, ergebnis
        for teil in eltern:
            quelle = quelle.get(teil) if isinstance(quelle, dict) else None
            ziel = ziel.setdefault(teil, {})
        wert = quelle.get(blatt) if isinstance(quelle, dict) else None
        # Leere Werte weglassen: `"fassung": ""` an jedem Treffer ist Rauschen, und ein
        # leeres Feld sagt dem Modell nichts, was das Fehlen nicht auch sagte.
        if not _leer(wert):
            ziel[blatt] = ohne_svg(wert)
    # Ein Elternobjekt ohne gesetztes Unterfeld bleibt hier als `{}` stehen; weg nimmt
    # es der Leerfilter in `fuer_modell` — die eine Stelle für diese Regel.
    return ergebnis


def _leer(wert) -> bool:
    """Leer heißt: ``None``, ``""``, ``[]`` oder ``{}`` — **nicht** ``0`` oder ``False``."""
    return wert is None or (isinstance(wert, (str, list, dict)) and len(wert) == 0)


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


#: Knotenarten, deren Text **abschnittsweise** gekürzt wird (Paket 9, N14).
#: Sie sind nach `_Format.md` gegliedert: Definition (ohne Überschrift), „### Erklärung",
#: „### Beispiele" — und nur bei ihnen lohnt die Unterscheidung.
ABSCHNITTS_TYPEN: tuple[str, ...] = ("begriff", "stoffsteckbrief")

#: Wie viel Text ein solcher Baustein im Prompt bekommen darf.
#:
#: ⚠️ **Warum die harte Grenze von 800 Zeichen hier schadete** (nachgezählt 26.09.2026):
#: 26 der 36 Pilotknoten wurden gekürzt, und der Schnitt lag fast immer mitten in der
#: Erklärung — die Beispiele erreichten das Modell praktisch **nie**. Bei drei von fünf
#: Knoten mit Abbildung fiel auch der Platzhalter `[Abbildung: …]` weg, also gerade der
#: Hinweis, dass es dazu ein Bild gibt.
INHALT_MAX_ZEICHEN_ABSCHNITTE = 1500

#: Wie lang der **Kern** (Definition und Erklärung) eines solchen Bausteins höchstens
#: werden darf (0.14, F4). Bis zum Gesamtbudget füllen Beispiele den Rest auf; ist der
#: Kern länger als das Gesamtbudget, kommt er **ohne** Beispiele, aber bis zu dieser
#: Grenze ganz.
#:
#: ⚠️ **Gemessen, nicht gesetzt** (07.10.2026): Bei 1500 verloren 15 von 112 Begriffen
#: und Stoffsteckbriefen Teile ihres Kerns — darunter Antwortrelevantes: „Ein
#: Magnesiumbrand wird mit trockenem Sand abgedeckt" (der Prompt endete bei „Ein
#: Magnesiumbra …"), die Benennungsregel der Anionen bei „Ion", der letzte Schritt der
#: elektrophilen Substitution. Alle 15 passen unter 2500; die Kontextblöcke der
#: AP7-Fragen wuchsen dabei um 0,5 %.
INHALT_MAX_ZEICHEN_KERN = 2500

#: Weniger Platz als das lohnt sich für ein Beispiel nicht — ein angefangener Satz
#: kostet Tokens und sagt nichts.
_BEISPIEL_MINDESTPLATZ = 120

_BEISPIEL_UEBERSCHRIFT = re.compile(r"^#{1,6}\s*Beispiel", re.MULTILINE | re.IGNORECASE)


def _hart(inhalt: str, grenze: int) -> str:
    return inhalt[:grenze] + " …" if len(inhalt) > grenze else inhalt


def kuerze(inhalt: str, content_type: str | None) -> str:
    """Den Knotentext auf Prompt-Maß bringen — je nach Knotenart anders.

    Für :data:`ABSCHNITTS_TYPEN`: **Definition und Erklärung vollständig**, Beispiele nur,
    soweit das Budget reicht, abgeschnitten an einer Zeilengrenze und mit sichtbarem „…".
    Für alle anderen Arten bleibt es beim harten Schnitt bei
    :data:`INHALT_MAX_ZEICHEN` — eine Bildungsplan-Kompetenz hat keine Beispiele, die
    man schonen könnte, und liegt im Median ohnehin bei 137 Zeichen.

    ⚠️ **Auch der Kern ist nicht unbegrenzt.** Ist er länger als das Gesamtbudget, kommt
    er ohne Beispiele, aber ganz — bis :data:`INHALT_MAX_ZEICHEN_KERN`. Darüber greift
    derselbe harte Schnitt, sonst füllte ein einzelner Baustein den halben Prompt. Die
    Zusage lautet „Beispiele werden zuerst geopfert", nicht „der Kern ist heilig".

    Bildbeschreibungen zählen mit: :func:`abbildungen_aufgeloest` läuft **vor** dieser
    Funktion, ihr Ergebnis ist Teil des Textes.
    """
    if content_type not in ABSCHNITTS_TYPEN:
        return _hart(inhalt, INHALT_MAX_ZEICHEN)

    treffer = _BEISPIEL_UEBERSCHRIFT.search(inhalt)
    kern = inhalt[: treffer.start()].rstrip() if treffer else inhalt.rstrip()
    beispiele = inhalt[treffer.start():].rstrip() if treffer else ""

    if len(kern) >= INHALT_MAX_ZEICHEN_KERN:
        return _hart(kern, INHALT_MAX_ZEICHEN_KERN)
    if len(kern) >= INHALT_MAX_ZEICHEN_ABSCHNITTE:
        # Länger als das Gesamtbudget, kürzer als der Kerndeckel: Der Kern kommt ganz,
        # für Beispiele bleibt kein Platz — sichtbar, damit das Modell es weiß.
        return kern + ("\n\n…" if beispiele else "")
    if not beispiele:
        return kern

    rest = INHALT_MAX_ZEICHEN_ABSCHNITTE - len(kern) - 2   # die beiden Zeilenumbrüche
    if rest < _BEISPIEL_MINDESTPLATZ:
        return kern + "\n\n…"

    # An einer Zeilengrenze schneiden: Die Beispiele sind eine Aufzählung, ein halber
    # Spiegelstrich ist schlechter als einer weniger.
    passend: list[str] = []
    verbraucht = 0
    for zeile in beispiele.splitlines():
        if verbraucht + len(zeile) + 1 > rest:
            break
        passend.append(zeile)
        verbraucht += len(zeile) + 1
    gekuerzt = len(passend) < len(beispiele.splitlines())
    if len(passend) <= 1:          # nur die Überschrift passt — dann lieber gar nicht
        return kern + "\n\n…"
    return kern + "\n\n" + "\n".join(passend).rstrip() + ("\n…" if gekuerzt else "")


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
        # `distanz` trägt die Vorab-Suche für die Zeile „Kontext" unter der Antwort
        # (0.14) — dem Modell sagt sie nichts, und ein Prompt-Feld mehr wäre eine
        # Prompt-Änderung ohne Messung.
        eintrag = {
            k: v for k, v in t.items()
            if k not in ("node_id", "content", "subject_id", "fach", "metadata",
                         "aliase", "distanz")
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
        # ⚠️ **Leere Felder weglassen** (0.14, F3) — an einer Stelle, für beide Wege.
        # `nr` und `bp_version` kamen an jedem Fachbegriff als `null` mit: Rauschen, das
        # dem Modell nichts sagt, was das Fehlen nicht auch sagte.
        eintrag = {k: v for k, v in eintrag.items() if not _leer(v)}
        inhalt = (t.get("content") or "").strip()
        if inhalt:
            # ⚠️ **Auflösen vor dem Kürzen.** Andersherum bliebe ein halber Platzhalter
            # stehen (`{{abbildung:EN_H`). Der Preis: Eine Bildbeschreibung ist rund
            # 200 Zeichen lang und zählt zum Budget. Für Begriffe und Stoffsteckbriefe
            # gilt seit N14 ein eigenes, abschnittsweises Budget (`kuerze`), seit 0.14
            # dazu ein Deckel für den Kern (`INHALT_MAX_ZEICHEN_KERN`).
            inhalt = abbildungen_aufgeloest(inhalt, t.get("metadata"))
            eintrag["content"] = kuerze(inhalt, t.get("content_type"))
        aufbereitet.append(eintrag)
    return aufbereitet


def mit_lesehinweis(rumpf: str) -> str:
    """Den Lesehinweis vor einen Kontextblock setzen (Paket 9, N13).

    ⚠️ **Es gibt zwei Wege, auf denen Bausteine zum Modell kommen** — die Vorab-Suche
    und das Suchwerkzeug —, und beide brauchen denselben Hinweis. Stünde er nur am
    einen, hinge das Verhalten davon ab, welchen Weg das Modell zufällig genommen hat;
    genau diese Abhängigkeit hat die Vorab-Suche gerade beseitigt.

    Der Text selbst steht in ``pedagogy.yaml`` (Schlüssel ``kontext_hinweis``): Er ist
    Prompt-Text, wird wie die Präambeln gegengelesen und gehört nicht in den Code.
    """
    hinweis = load_pedagogy().kontext_hinweis.strip()
    return f"{hinweis}\n\n{rumpf}" if hinweis else rumpf


def werkzeug_nutzlast(ergebnis) -> str:
    """Ein Ergebnis der Werkzeuggruppe ``context_search``, wie das Modell es liest.

    Die **einzige** Stelle, die daraus Text macht — samt Lesehinweis. Vorher stand die
    Serialisierung an zwei Zweigen im Streaming-Pfad des Routers, und damit hätte ein
    dritter Zweig den Hinweis leicht vergessen.

    Zwei Formen, weil die Werkzeuge zwei liefern: Die Suche und die Aufzählung geben
    einen fertigen Umschlag (Dict), ``get_operatoren`` noch eine flache Liste, die hier
    durch :func:`fuer_modell` geht.
    """
    if isinstance(ergebnis, list):
        ergebnis = {"nodes": fuer_modell(ergebnis)}
    return mit_lesehinweis(json.dumps(ergebnis, ensure_ascii=False))
