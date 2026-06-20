# Screenshots: Unterrichtsplanung-Hilfe

Dateien aus diesem Ordner werden unter `/help-images/unterrichtsplanung/<datei>`
ausgeliefert und von `docs/user/unterrichtsplanung.md` referenziert.

## So ergänzen Sie einen Screenshot

1. PNG mit dem unten genannten Dateinamen hier ablegen.
2. In `docs/user/unterrichtsplanung.md` die zugehörige Platzhalter-Zeile
   ersetzen — aus

   ```
   > 📷 *Screenshot folgt: …*
   <!-- Ersetzen durch: ![Alt-Text](/help-images/unterrichtsplanung/datei.png) -->
   ```

   wird

   ```
   ![Alt-Text](/help-images/unterrichtsplanung/datei.png)
   ```

Die Hilfe-Seite (`/help/unterrichtsplanung`) und die Anwender-Doku nutzen dieselbe
Markdown-Datei — ein Screenshot erscheint also an beiden Stellen.

## Erwartete Dateien

| Datei | Motiv |
|---|---|
| `jahresuebersicht.png` | Jahresübersicht mit Wochenzeilen, UE-Farbbalken und Stundenbilanz |
| `stundenentwurf.png` | Stundenentwurf mit Phasentabelle, Zeitbudget-Balken, Kompetenz-Leiste |
| `methode-sozialform.png` | Methodenspalte: gestapelte Sozialform/Methode + Vorschlagsliste |
| `hinweisleiste.png` | Überhang-Hinweisleiste am unteren Rand der Jahresübersicht |

Empfehlung: Breite ca. 1200–1600 px, heller Modus, ohne echte Schüler:innennamen.
