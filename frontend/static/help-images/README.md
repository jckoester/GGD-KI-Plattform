# Screenshots der Hilfe

Bilder hier unter `help-images/<bereich>/<datei>.png` werden an der Wurzel
ausgeliefert (`/help-images/…`) und von den Hilfe-Markdown-Dateien in
`docs/user/` referenziert. Hilfe (`/help/*`) und Anwender-Doku nutzen **dieselbe**
Quelle — ein Screenshot erscheint also an beiden Stellen.

## So ergänzen Sie einen Screenshot

1. PNG mit dem genannten Pfad/Dateinamen ablegen (Ordner ggf. anlegen).
2. In der zugehörigen `docs/user/*.md` die Platzhalter-Zeile ersetzen — aus

   ```
   > 📷 *Screenshot folgt: …*
   <!-- Ersetzen durch: ![Alt-Text](/help-images/…/datei.png) -->
   ```

   wird

   ```
   ![Alt-Text](/help-images/…/datei.png)
   ```

Empfehlung: Breite ca. 1200–1600 px, heller Modus, keine echten Schüler:innennamen.

## Checkliste

| Datei | Hilfe-Seite | Motiv |
|---|---|---|
| `erste-schritte/oberflaeche.png` | Erste Schritte | Hauptansicht: Seitenleiste, Chat-Bereich, User-Menü |
| `chat/eingabefeld.png` | Chat nutzen | Eingabefeld mit Büroklammer, Suche-Button, Modell-Auswahl |
| `chat/modell-auswahl.png` | Chat nutzen | Geöffnete Modell-Auswahl |
| `assistenten/assistenten-liste.png` | Assistenten | Assistenten-Liste mit Namen + Kurzbeschreibung |
| `kontext/kontext-chips.png` | Kontextspeicher | Angeheftete Kontextbausteine als Chips über dem Eingabefeld |
| `profil/budget.png` | Profil & Budget | Budget-Anzeige mit Fortschrittsbalken |
| `unterrichtsplanung/jahresuebersicht.png` | Unterrichtsplanung | Jahresübersicht mit Wochenzeilen, UE-Farbbalken, Bilanz |
| `unterrichtsplanung/stundenentwurf.png` | Unterrichtsplanung | Stundenentwurf: Phasentabelle, Zeitbudget, Kompetenz-Leiste |
| `unterrichtsplanung/methode-sozialform.png` | Unterrichtsplanung | Methodenspalte: gestapelte Sozialform/Methode + Vorschläge |
| `unterrichtsplanung/hinweisleiste.png` | Unterrichtsplanung | Überhang-Hinweisleiste am unteren Rand |
