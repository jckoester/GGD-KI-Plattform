"""Arduino-Wissensgraph: Testdaten und Seed-Funktion für KS-Phase-3-E2E-Tests."""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_SLUG = "arduino-wissensgraph"

NODES: list[dict] = [
    # ── Wurzel ───────────────────────────────────────────────────────────────
    {
        "slug": ROOT_SLUG,
        "category": "knowledge", "content_type": "themengebiet",
        "title": "Arduino-Wissensgraph",
        "content": "Überblick über Funktionen, Bauteile und Konzepte für Arduino-Projekte.",
        "parent_slug": None,
    },

    # ── Funktionen ────────────────────────────────────────────────────────────
    {
        "slug": "arduino-fn-digitalwrite",
        "category": "concept", "content_type": "funktion",
        "title": "digitalWrite",
        "content": "Setzt einen digitalen Pin auf HIGH oder LOW.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"signatur": {
            "name": "digitalWrite", "sprache": "arduino_cpp",
            "parameter": [
                {"name": "pin",   "typ": "int", "beschreibung": "Pin-Nummer (0-13)"},
                {"name": "value", "typ": "int", "beschreibung": "HIGH oder LOW"},
            ],
            "rueckgabe": {"typ": "void", "beschreibung": ""},
        }},
    },
    {
        "slug": "arduino-fn-analogread",
        "category": "concept", "content_type": "funktion",
        "title": "analogRead",
        "content": "Liest den analogen Wert eines Pins (0-1023).",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"signatur": {
            "name": "analogRead", "sprache": "arduino_cpp",
            "parameter": [
                {"name": "pin", "typ": "int", "beschreibung": "Analoger Pin (A0-A5)"},
            ],
            "rueckgabe": {"typ": "int", "beschreibung": "Analogwert 0-1023"},
        }},
    },
    {
        "slug": "arduino-fn-analogwrite",
        "category": "concept", "content_type": "funktion",
        "title": "analogWrite",
        "content": "Gibt ein PWM-Signal auf einem PWM-fähigen Pin aus (Wert 0-255).",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"signatur": {
            "name": "analogWrite", "sprache": "arduino_cpp",
            "parameter": [
                {"name": "pin",   "typ": "int", "beschreibung": "PWM-fähiger Pin"},
                {"name": "value", "typ": "int", "beschreibung": "PWM-Wert 0-255"},
            ],
            "rueckgabe": {"typ": "void", "beschreibung": ""},
        }},
    },
    {
        "slug": "arduino-fn-delay",
        "category": "concept", "content_type": "funktion",
        "title": "delay",
        "content": "Hält das Programm für eine Anzahl Millisekunden an.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"signatur": {
            "name": "delay", "sprache": "arduino_cpp",
            "parameter": [
                {"name": "ms", "typ": "unsigned long", "beschreibung": "Wartezeit in Millisekunden"},
            ],
            "rueckgabe": {"typ": "void", "beschreibung": ""},
        }},
    },
    {
        "slug": "arduino-fn-pinmode",
        "category": "concept", "content_type": "funktion",
        "title": "pinMode",
        "content": "Setzt die Betriebsart eines Pins (INPUT, OUTPUT, INPUT_PULLUP).",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"signatur": {
            "name": "pinMode", "sprache": "arduino_cpp",
            "parameter": [
                {"name": "pin",  "typ": "int", "beschreibung": "Pin-Nummer"},
                {"name": "mode", "typ": "int", "beschreibung": "INPUT, OUTPUT oder INPUT_PULLUP"},
            ],
            "rueckgabe": {"typ": "void", "beschreibung": ""},
        }},
    },
    {
        "slug": "arduino-fn-millis",
        "category": "concept", "content_type": "funktion",
        "title": "millis",
        "content": "Gibt die Laufzeit des Programms seit dem letzten Reset in Millisekunden zurück.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"signatur": {
            "name": "millis", "sprache": "arduino_cpp",
            "parameter": [],
            "rueckgabe": {"typ": "unsigned long", "beschreibung": "Laufzeit in ms"},
        }},
    },

    # ── Bauteile ─────────────────────────────────────────────────────────────
    {
        "slug": "arduino-bauteil-led",
        "category": "concept", "content_type": "bauteil",
        "title": "LED",
        "content": "Leuchtendes Halbleiterbauteil. Braucht einen Vorwiderstand (~220 Ohm). Langer Pin (Anode, +) an Signal, kurzer Pin (Kathode) an GND.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"schaltzeichen": {
            "svg": "",
            "beschreibung": "Diodensymbol: Dreieck mit senkrechter Linie, zwei schräge Pfeile zeigen Lichtaussendung an",
            "norm": "DIN EN IEC 60617",
            "kennung": "LED",
        }},
    },
    {
        "slug": "arduino-bauteil-widerstand",
        "category": "concept", "content_type": "bauteil",
        "title": "Widerstand",
        "content": "Begrenzt den Stromfluss. Wert in Ohm. Farbring-Code oder Aufdruck gibt den Widerstandswert an.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"schaltzeichen": {
            "svg": "",
            "beschreibung": "Rechteck mit zwei Anschlusslinien links und rechts; europäisches Symbol nach IEC 60617",
            "norm": "DIN EN IEC 60617",
            "kennung": "R",
        }},
    },
    {
        "slug": "arduino-bauteil-servo",
        "category": "concept", "content_type": "bauteil",
        "title": "Servo",
        "content": "Dreht sich auf einen vorgegebenen Winkel (0-180 Grad). Ansteuerung über die Arduino-Servo-Bibliothek mit analogWrite-ähnlichem Interface.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"schaltzeichen": {
            "svg": "",
            "beschreibung": "Rechteck mit M-Beschriftung und Positionspfeil; vereinfachtes Motorsymbol",
            "norm": "DIN EN IEC 60617",
            "kennung": "M",
        }},
    },
    {
        "slug": "arduino-bauteil-taster",
        "category": "concept", "content_type": "bauteil",
        "title": "Taster",
        "content": "Schalter mit zwei Zuständen: gedrückt (geschlossen) und nicht gedrückt (offen). Mit INPUT_PULLUP verwenden, um floatende Pins zu vermeiden.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"schaltzeichen": {
            "svg": "",
            "beschreibung": "Zwei parallele Anschlusslinien mit schwebender Kontaktbrücke; Schließer-Symbol nach IEC 60617",
            "norm": "DIN EN IEC 60617",
            "kennung": "S",
        }},
    },
    {
        "slug": "arduino-bauteil-poti",
        "category": "concept", "content_type": "bauteil",
        "title": "Potentiometer",
        "content": "Variabler Widerstand. Mittlerer Pin -> analogRead, Außenpins an 5V und GND.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"schaltzeichen": {
            "svg": "",
            "beschreibung": "Rechteck (wie Widerstand) mit diagonalem Pfeil als Abgriff; Potentiometer-Symbol nach IEC 60617",
            "norm": "DIN EN IEC 60617",
            "kennung": "RV",
        }},
    },
    {
        "slug": "arduino-bauteil-ultrasonic",
        "category": "concept", "content_type": "bauteil",
        "title": "Ultraschallsensor HC-SR04",
        "content": "Misst Entfernungen per Schallecho. Pins: VCC (5V), Trig (Auslöser), Echo (Messung), GND.",
        "parent_slug": ROOT_SLUG,
        "extra_metadata": {"schaltzeichen": {
            "svg": "",
            "beschreibung": "Rechteck mit Sende- und Empfangswandler-Symbolen; kein normiertes IEC-Symbol, schulübliche Darstellung",
            "norm": None,
            "kennung": "US",
        }},
    },

    # ── Abstrakte Konzepte ───────────────────────────────────────────────────
    {
        "slug": "arduino-abstrakt-pwm",
        "category": "concept", "content_type": "abstrakt",
        "title": "PWM",
        "content": "Pulsweitenmodulation simuliert analoge Spannung durch schnelles Ein-/Ausschalten. Duty Cycle bestimmt das Verhältnis.",
        "parent_slug": ROOT_SLUG,
    },
    {
        "slug": "arduino-abstrakt-i2c",
        "category": "concept", "content_type": "abstrakt",
        "title": "I2C",
        "content": "Serielles Zwei-Draht-Protokoll (SDA + SCL). Adressiert mehrere Geräte am selben Bus.",
        "parent_slug": ROOT_SLUG,
    },
    {
        "slug": "arduino-abstrakt-pullup",
        "category": "concept", "content_type": "abstrakt",
        "title": "Pull-up-Widerstand",
        "content": "Hält einen unverbundenen Pin auf HIGH. Wird mit INPUT_PULLUP aktiviert oder extern mit ~10 kOhm gegen 5V beschaltet.",
        "parent_slug": ROOT_SLUG,
    },
    {
        "slug": "arduino-abstrakt-dutycycle",
        "category": "concept", "content_type": "abstrakt",
        "title": "Duty Cycle",
        "content": "Verhältnis von HIGH-Zeit zur Gesamtperiode beim PWM-Signal, angegeben in Prozent (0-100 %) oder als Wert 0-255.",
        "parent_slug": ROOT_SLUG,
    },

    # ── Konventionen ─────────────────────────────────────────────────────────
    {
        "slug": "arduino-konv-stil",
        "category": "document", "content_type": "konvention",
        "title": "Arduino-Codierkonventionen",
        "content": """# Codierkonventionen für Arduino-Projekte

## Kommentare
- Jede Funktion mit einem Kommentar erklären: was macht sie, welche Parameter
- Komplexe Logik mit Inline-Kommentaren versehen

## Variablennamen
- Sprechende Namen: `sensorWert` statt `x`
- Konstanten in GROSSBUCHSTABEN: `const int LED_PIN = 13;`
- Camel Case für Variablen und Funktionen

## Einrückung
- 2 Leerzeichen oder 1 Tab — einheitlich im Projekt
""",
        "parent_slug": ROOT_SLUG,
    },
    {
        "slug": "arduino-konv-schaltplan",
        "category": "document", "content_type": "konvention",
        "title": "Schaltplan-Zeichenkonventionen",
        "content": """# Schaltplan-Zeichenkonventionen (Arduino-Projekte)

## Symbole
- Europäische Schaltsymbole nach DIN EN IEC 60617 (Widerstand = Rechteck, nicht Zickzack)
- Jedes Bauteil trägt Kennung und Wert: R1 = 220 Ohm, LED1, S1

## Leitungsführung
- Leitungen immer rechtwinklig (keine Diagonalen)
- Kreuzung ohne Verbindung: Brücke (kein Punkt)
- Kreuzung mit Verbindung: Lötpunkt (gefüllter Kreis)

## Layout
- Spannungsquelle (5V/VCC) oben oder links
- GND unten oder rechts
- Signalfluss von links nach rechts

## Beschriftung
- Bauteilkennungen über dem Symbol, Werte darunter
- Spannungspegel an Knoten nur bei Unklarheit angeben
""",
        "parent_slug": ROOT_SLUG,
    },
]


async def seed(db: AsyncSession) -> None:
    """Idempotentes Seeden der Arduino-Wissensgraph-Knoten.

    Prüft per metadata->>'slug' ob jeder Knoten bereits existiert.
    Legt alle Knoten mit read_scope=write_scope='school' an.
    """
    slug_to_id: dict[str, str] = {}

    for node in NODES:
        slug = node["slug"]
        metadata = {"slug": slug, **node.get("extra_metadata", {})}

        result = await db.execute(
            text("SELECT id FROM context_nodes WHERE metadata->>'slug' = :slug"),
            {"slug": slug},
        )
        row = result.fetchone()
        if row:
            slug_to_id[slug] = str(row[0])
            continue

        result = await db.execute(
            text("""
                INSERT INTO context_nodes
                  (category, content_type, title, content, metadata,
                   read_scope, write_scope, status)
                VALUES (:category, :content_type, :title, :content,
                        CAST(:metadata AS jsonb), 'school', 'school', 'active')
                RETURNING id
            """),
            {
                "category": node["category"],
                "content_type": node["content_type"],
                "title": node["title"],
                "content": node["content"],
                "metadata": json.dumps(metadata, ensure_ascii=False),
            },
        )
        slug_to_id[slug] = str(result.fetchone()[0])

    await db.flush()

    for node in NODES:
        parent_slug = node.get("parent_slug")
        if parent_slug is None:
            continue
        from_id = slug_to_id.get(node["slug"])
        to_id = slug_to_id.get(parent_slug)
        if not from_id or not to_id:
            continue
        await db.execute(
            text("""
                INSERT INTO context_edges (from_node_id, to_node_id, relation, metadata)
                VALUES (:from_id, :to_id, 'part_of', '{}')
                ON CONFLICT DO NOTHING
            """),
            {"from_id": from_id, "to_id": to_id},
        )

    await db.commit()
