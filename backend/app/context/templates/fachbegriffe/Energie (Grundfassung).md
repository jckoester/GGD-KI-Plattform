---
# ── MUSTERDATEI ───────────────────────────────────────────────────────────────
# Ändern Sie Titel und Inhalt, bevor Sie sie einspielen — sonst legen Sie einen
# Eintrag „Energie" an, den Sie so nicht gemeint haben. Die Vorschau im Dialog zeigt
# vorher, was geschähe. Alles, was mit # beginnt, ist eine Anmerkung und wird nicht
# eingespielt.
#
# `id`: die Kennung, an der die Plattform den Eintrag wiedererkennt. Sie brauchen sie
# nicht zu setzen — beim ersten Einspielen wird eine vergeben, und der Export trägt
# sie hier ein. Von Hand nur dann, wenn Sie die Datei umbenennen wollen, bevor sie
# einmal eingespielt war.
# id: energie-grundfassung

knotentyp: begriff
titel: Energie

# `fassung` unterscheidet gleichnamige Einträge. Zwei Fassungen sind der vorgesehene
# Weg, wenn derselbe Begriff in zwei Jahrgängen etwas anderes bedeutet — nicht ein
# Eintrag, der beides zugleich zu sagen versucht.
fassung: Grundfassung
ab_klasse: 6

# `fach` können Sie weglassen: Eingespielt wird in das Fach, dessen Seite Sie offen
# haben. Steht hier ein anderes Fach, wird die Datei gemeldet und übergangen.
# fach: Physik

# Die Bezeichnung, mit der der Assistent antwortet.
bevorzugter_begriff: Energie

# `aliase` sind Suchbegriffe, keine Antwortbegriffe: alles, womit jemand nach dem
# Begriff fragt — auch schiefe Wörter, die Schüler:innen benutzen. Sie machen den
# Eintrag auffindbar; geantwortet wird immer mit `bevorzugter_begriff`.
aliase: [Energieform, Power]

genus: die
plural: Energieformen

# Fundstellen im Bildungsplan, Schema `<Fachkürzel> <Abschnitt> (<Nummer>)`. Eine
# Angabe, die keine Kompetenz trifft, steht im Bericht — eingespielt wird trotzdem.
# bildungsplan: ["PH 3.2.1.1 (2)"]

# Beziehungen. Ziel ist der **Dateiname** im Bündel, in doppelten eckigen Klammern.
# Zeigt ein Verweis auf etwas, das es noch nicht gibt, entsteht keine Verbindung — der
# Bericht listet ihn als Arbeitsliste auf, und sobald das Ziel da ist, schließt der
# nächste Lauf die Lücke.
vertieft_in: ["[[Energie (Erhaltung)]]"]

# Abbildungen: Datei unter `_Abb/`, Beschreibung für Assistenten und Screenreader.
# Im Text steht sie als `![[dateiname.svg]]` an der Stelle, an der sie erklärt wird.
illustrationen:
  - datei: _Abb/energiefluss.svg
    # ⚠️ Einfache Anführungszeichen, wenn im Text welche vorkommen — in doppelten
    # beendete das erste innere Zeichen die Angabe, und die Datei wäre unlesbar.
    beschreibung: 'Pfeil von einem Kasten „chemisch" zu einem Kasten „Bewegung".'

# Woher der Entwurf stammt — hilfreich, wenn später jemand fragt.
quelle: Muster aus der Vorlage
---

## Definition

Energie ist die Fähigkeit eines Körpers oder Systems, Arbeit zu verrichten. Sie kommt in verschiedenen Formen vor und lässt sich von einer Form in eine andere umwandeln.

## Erklärung

Ein gespannter Flitzebogen, ein heißer Ofen und eine geladene Batterie haben etwas gemeinsam: In allen dreien steckt Energie, und in allen dreien lässt sie sich nutzen. Der Unterschied liegt in der Form — Spannenergie, thermische Energie, chemische Energie.

Beim Umwandeln geht keine Energie verloren. Was umgangssprachlich „Energieverbrauch" heißt, ist eine Umwandlung in eine Form, die sich schlechter weiternutzen lässt.

![[energiefluss.svg]]

## Beispiele

- Eine Lampe wandelt elektrische Energie in Licht und Wärme um.
- Beim Fahrradfahren wird chemische Energie aus der Nahrung zu Bewegungsenergie.

## Abgrenzung

- [[Energie (Erhaltung)]] – dieselbe Größe, ab Klasse 10 quantitativ und mit dem Erhaltungssatz.

## Fehlvorstellungen

- „Energie wird verbraucht." – Sie wird umgewandelt; die Gesamtmenge bleibt gleich.
- „Energie ist dasselbe wie Kraft." – Eine Kraft wirkt, Energie wird übertragen oder umgewandelt.

## Offene Fragen

- Dieser Abschnitt wird nicht eingespielt. Er ist Platz für Notizen an die Fachschaft.
