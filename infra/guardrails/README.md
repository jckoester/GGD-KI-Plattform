# Jugendschutz-Guardrail-Pattern-Dateien (LiteLLM-Proxy)

Diese Dateien sind **Starter-Vorlagen** für die Regex-Guardrails am LiteLLM-Proxy
(ADR-008 Teil 1A). Sie prüfen die **Ausgabe** des Modells (`post_call`) und blockieren
bei einem Treffer die Antwort.

> ⚠️ **Vor der Aktivierung kuratieren.** Die mitgelieferten Muster sind bewusst
> minimal und illustrativ. Sie müssen mit Schulleitung, Schulsozialarbeit und den
> betroffenen Fachschaften abgestimmt und getestet werden, bevor sie produktiv
> greifen. Falsch gesetzte Muster blockieren entweder zu viel (legitime Bildungs-
> inhalte, z. B. Sexualkunde, historische Gewalt) oder zu wenig.

## Format

- Eine Regex pro Zeile.
- Zeilen, die mit `#` beginnen, sind Kommentare.
- Die exakte Regex-Auswertung (Groß/Kleinschreibung, Flags) hängt von der
  LiteLLM-Version ab — gegen die LiteLLM-Doku abgleichen.

## Dateien & Status

| Datei | Im Beispiel aktiv? | Empfehlung |
|---|---|---|
| `drugs_how_to.txt` | ✅ aktiv | Regex eignet sich für konkrete Herstellungs-/Beschaffungsanleitungen |
| `explicit_sexual.txt` | ➖ optional (auskommentiert) | Primär `openai_moderation` (kontextsensitiv); Regex nur als Zusatzschicht |
| `self_harm_instructions.txt` | ➖ optional (auskommentiert) | **Primär `openai_moderation`.** Regex hier riskant — s. u. |

## ⚠️ Besondere Vorsicht: Selbstverletzung

Eine Regex auf Selbstverletzungs-Begriffe blockiert leicht **auch die fürsorgliche
Krisen-Antwort** des Modells (die Selbstverletzung benennt, aber auf Hilfe verweist).
Das wäre das Gegenteil des Gewollten — Hilfe würde weggefiltert. Deshalb läuft
`self_harm_instructions` im Beispiel über `openai_moderation` (Kategorie
`self-harm/instructions`), **nicht** über diese Datei. Die Regex-Datei nur aktivieren,
wenn sie gründlich gegen echte Krisen-Hilfe-Antworten getestet wurde.

Die universelle Basis-Präambel (`pedagogy.yaml`, ADR-008 Teil 2) weist das Modell
ohnehin an, keine Selbstverletzungs-Anleitung zu geben — der Proxy-Guard ist nur der
Backstop.
