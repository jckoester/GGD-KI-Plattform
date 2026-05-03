# GGD-KI-Plattform

Eine selbst gehostete KI-Zugangsplattform für Schulen. Sie bietet eine Web-Oberfläche für den Zugang zu großen Sprachmodellen (LLMs) und setzt dabei DSGVO-konforme Pseudonymisierung durch: Schüleridentitäten verlassen den Schulserver nie — externe KI-Anbieter erhalten ausschließlich den Gesprächsinhalt.

---

## Funktionsumfang

### Implementiert

- **Chat** mit Streaming-Antworten, Markdown-Rendering, Code-Highlighting
- **Dateianhänge** im Chat (PDF, Bilder, Textdateien bis 10 MB)
- **Assistenten** — vorkonfigurierte Chat-Umgebungen mit System-Prompt und optionalem Modell; Test-Chat direkt im Editor
- **Modellauswahl** — freigeschaltete Modelle pro Nutzergruppe wählbar
- **Budget-System** — monatliche EUR-Limits pro Jahrgang und Rolle, automatische EUR→USD-Umrechnung via EZB-Kurs, Anzeige des Restbudgets
- **Konversationsverlauf** mit automatischer Titelgenerierung
- **Admin-Bereich** — Modell-Freischaltungsmatrix, Budget-Übersicht, Nutzungsstatistiken, Assistentenverwaltung, Site-Texte
- **Automatische Datenlöschung** — Konten nach 90 Tagen ohne Login, Konversationen nach 93 Tagen ohne neue Nachricht
- **Authentifizierung** via OAuth2/OIDC (Produktivbetrieb) oder YAML-Testadapter (Entwicklung)
- **Anpassbares Branding** — Schulname, Logo (getrennte Varianten für Light/Dark-Theme)

### Geplant

- Fachspezifische Assistenten mit Fachfarben und gefilterter Auswahl
- Statische Kontext-Dokumente für Assistenten (automatischer Hintergrundtext)
- Krisenintervention — Schlüsselwort-Erkennung mit Weiterleitung zu Hilfsangeboten
- Lehrkräfte-eigene Assistenten und Klassenverwaltung

---

## Datenschutzprinzip

Pseudonymisierung findet im Backend statt, bevor Daten das Schulnetz verlassen. Aus der schulinternen Nutzer-ID wird per HMAC-SHA256 ein anonymes Pseudonym berechnet — dieser Schritt ist ohne den schulgeheimen `SCHOOL_SECRET`-Schlüssel nicht umkehrbar. LiteLLM ist der einzige Dienst, der mit externen KI-Anbietern kommuniziert; er übermittelt ausschließlich den Gesprächsinhalt, nie Namen oder andere Personendaten.

→ Details: [docs/dev/architektur.md](docs/dev/architektur.md)

---

## Dokumentation

| Zielgruppe | Dokument |
|-----------|---------|
| Schüler:innen & Lehrkräfte | [docs/user/](docs/user/README.md) |
| IT-Administration & Betrieb | [docs/admin/](docs/admin/README.md) |
| Entwickler:innen | [docs/dev/](docs/dev/README.md) |

---

## Lizenz

EUPL-1.2 — siehe [LICENSE](LICENSE)
