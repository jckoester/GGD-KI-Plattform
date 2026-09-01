/**
 * Der Ergebnisumschlag der Kontextsuche, aufbereitet für die Anzeige (ADR-017).
 *
 * **Warum ein eigenes Modul.** Zwei Oberflächen zeigen denselben Umschlag: die Suchseite
 * und das Vorschlagsfenster im Chat. Beide müssen dieselben Abschnitte gleich benennen —
 * sonst hieße dasselbe Ergebnis an zwei Stellen Verschiedenes, und der Unterschied
 * zwischen „trägt diesen Namen" und „ähnelt ihm" verwischt genau dort, wo er zählt.
 * Die Regeln sind zudem das Einzige am Fenster, was sich ohne Browser prüfen lässt.
 *
 * **Was hier bewusst nicht steht:** die `hinweise` des Umschlags. Im Fenster über dem
 * Eingabefeld tragen Abschnittstitel und Fußnote dieselbe Auskunft in einer Zeile, und
 * die Langfassung wäre dort entweder doppelt oder verwirrend — beides am 01.09.2026
 * gemessen: bei „nennen" lautet der Hinweis „24 Bausteine tragen diesen Namen, 5 davon
 * stehen hier" (die Fußnote sagt „5 von 24 angezeigt"), bei einer ganzen Frage
 * „Kein Baustein heißt genau ‚ich schülern bindungsenergie atomkern'" — der von
 * Füllwörtern befreite Suchbegriff, der als Satz gelesen unsinnig wirkt. Auf der
 * Suchseite steht beides unter einer Überschrift und mit Platz; hier nicht.
 */

export const ABSCHNITT_TITEL = {
  exakt: "Bausteine mit diesem Namen",
  aehnlich: "Ähnlich benannte Bausteine",
  aufzaehlung: "Alle passenden Bausteine",
  thematisch: "Nächstliegende Bausteine",
}

/**
 * Wie viele Treffer je Abschnitt vorausgewählt sind (offene Entscheidung 4 des
 * Umsetzungsplans). **Eine Zahl zu ändern genügt, um die Regel zu ändern.**
 *
 * Vorher war **alles** vorausgewählt. Gemessen am 01.09.2026 mit der Anfrage „nennen"
 * und Anzeigelimit 30: 59 Treffer, alle vorausgewählt — jeder davon Text im Prompt, den
 * niemand bewusst gewählt hat.
 *
 * Die Regel jetzt: **höchstens fünf je Abschnitt**, ähnlich benannte gar keine.
 *
 * - **Namensträger**: Der Planvorschlag war „alle" — danach wurde ja gesucht. Dieselbe
 *   Messung zeigt aber, warum das nicht reicht: „nennen" tragen 24 Bausteine, weil der
 *   Operator in jedem Fach und jeder Bildungsplan-Edition steht. Viele Gleichnamige
 *   heißen nicht „alle gemeint", sie heißen „der Name war mehrdeutig". Die fünf sind
 *   nicht beliebig: Sortiert wird mit Fach- und Rollenbonus, vorne steht also, was zum
 *   Fach der Konversation gehört.
 * - **Ähnlich benannte**: keine. Sie können der gesuchte Baustein sein oder ein ganz
 *   anderer mit ähnlichem Titel — das muss man ansehen.
 * - **Nächstliegende**: die ersten fünf; die Liste ist nach Ähnlichkeit sortiert und
 *   wird nach hinten beliebig.
 *
 * Wer doch alles will, hat den „Alle"-Knopf in der Kopfzeile.
 */
export const PRO_ABSCHNITT_VORAUSGEWAEHLT = 5

/**
 * Den Umschlag in die Abschnitte des Vorschlagsfensters zerlegen.
 *
 * Leere Abschnitte fallen weg — eine Überschrift ohne Treffer ist im knappen Fenster
 * verschenkte Höhe. Jeder Treffer erscheint nur einmal: Der gesuchte Baustein kann
 * Namensträger **und** thematisch nah sein, doppelt angezeigt wäre er zweimal
 * anzuhaken.
 *
 * @returns {Array<{schluessel: string, titel: string, treffer: object[],
 *                  fussnote: string, gekuerzt: boolean}>}
 */
export function vorschlagsAbschnitte(umschlag) {
  const ident = umschlag?.identifikation ?? {}
  const identTreffer = ident.treffer ?? []

  const gesehen = new Set()
  const neu = (liste) =>
    liste.filter((t) => {
      if (!t?.node_id || gesehen.has(t.node_id)) return false
      gesehen.add(t.node_id)
      return true
    })

  // ⚠️ Auf `=== 'exakt'` prüfen, nicht auf `!== 'teilweise'`. Die Identifikation kennt
  // seit AP9 eine dritte Stufe (`praefix`, nur für den `@`-Shortcode); eine
  // Ausschlussprüfung ließe sie als Namensträger durchgehen und damit die
  // Existenzaussage falsch werden. So landet alles Unbekannte bei den ähnlich benannten
  // — die schwächere Aussage ist der sichere Rückfall.
  //
  // Reihenfolge zwingend: Die exakten zuerst, damit ein Treffer, den beide Stufen
  // liefern, als Namensträger stehenbleibt und nicht als bloße Ähnlichkeit.
  const exakt = neu(identTreffer.filter((t) => t.treffer_art === 'exakt'))
  const aehnlich = neu(identTreffer.filter((t) => t.treffer_art !== 'exakt'))
  const thematisch = neu(umschlag?.thematisch?.treffer ?? [])

  const abschnitte = []

  if (exakt.length) {
    // `gesamt` zählt die exakten Namensträger — die Zahl trägt die Existenzaussage.
    const gesamt = ident.gesamt ?? exakt.length
    const gekuerzt = !ident.vollstaendig && gesamt > exakt.length
    abschnitte.push({
      schluessel: 'exakt',
      titel: ABSCHNITT_TITEL.exakt,
      treffer: exakt,
      fussnote: gekuerzt
        ? `${exakt.length} von ${gesamt} angezeigt`
        : `${gesamt} gefunden`,
      gekuerzt,
    })
  }

  if (aehnlich.length) {
    abschnitte.push({
      schluessel: 'aehnlich',
      titel: ABSCHNITT_TITEL.aehnlich,
      treffer: aehnlich,
      // Für die Teiltreffer gibt es keine Gesamtzahl: Sie hängen an einer Schwelle, und
      // eine Zahl daraus zu machen hieße, die Schwelle als Wahrheit auszugeben.
      fussnote: 'Ähnlicher Titel — nicht zwingend der gesuchte Baustein.',
      gekuerzt: false,
    })
  }

  if (thematisch.length) {
    abschnitte.push({
      schluessel: 'thematisch',
      titel: ABSCHNITT_TITEL.thematisch,
      treffer: thematisch,
      fussnote: 'Nach Ähnlichkeit sortiert, nie vollständig.',
      gekuerzt: false,
    })
  }

  return abschnitte
}

/**
 * Welche Auswahl gilt — die von Hand geänderte oder wieder die Vorauswahl.
 *
 * ⚠️ **Der Grund, warum das eine Funktion ist und kein `$state`-Initialisierer.** Das
 * Vorschlagsfenster wird per `{#if}` ohne `{#key}` gerendert: Eine zweite Suche bei
 * offenem Fenster baut die Komponente nicht neu auf, sie tauscht nur die Prop. Eine
 * einmal beim Erzeugen gesetzte Auswahl behielte dann die IDs der **ersten** Suche —
 * der Knopf zeigte eine Zahl, bestätigt würde nichts, weil die alten IDs in der neuen
 * Trefferliste nicht vorkommen. Die Handauswahl trägt deshalb ihren Umschlag bei sich;
 * kommt ein anderer, verfällt sie.
 *
 * @param {{umschlag: object, ids: Set<string>}|null} handauswahl
 */
export function gueltigeAuswahl(handauswahl, umschlag, abschnitte) {
  if (handauswahl && handauswahl.umschlag === umschlag) return handauswahl.ids
  return vorauswahl(abschnitte)
}

/** Alle Treffer der Abschnitte in Anzeigereihenfolge — um aus IDs wieder Knoten zu machen. */
export function alleTreffer(abschnitte) {
  return abschnitte.flatMap((a) => a.treffer)
}

/**
 * Die Vorauswahl: je Abschnitt die ersten `PRO_ABSCHNITT_VORAUSGEWAEHLT`, ähnlich
 * benannte keine.
 *
 * @returns {Set<string>} node_ids
 */
export function vorauswahl(abschnitte) {
  const ids = new Set()
  for (const abschnitt of abschnitte) {
    if (abschnitt.schluessel === 'aehnlich') continue
    for (const t of abschnitt.treffer.slice(0, PRO_ABSCHNITT_VORAUSGEWAEHLT)) {
      ids.add(t.node_id)
    }
  }
  return ids
}
