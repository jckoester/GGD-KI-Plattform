/**
 * Wann das `@`-Dropdown offen ist und wonach es sucht (ADR-017, AP9).
 *
 * **Warum Leerzeichen erlaubt sein müssen.** Mit `@` schlägt man einen Titel nach, den
 * man kennt — und Titel sind mehrwortig („Anleitung für den Operator nennen"). Die
 * bisherige Regel `/@(\S*)$/` schloss das Dropdown am ersten Leerzeichen: Schon
 * `"@Satz "` traf nicht mehr, ein solcher Titel war nur über ein einzelnes enthaltenes
 * Wort erreichbar.
 *
 * **Warum es dafür eine Abbruchregel braucht.** Ohne sie verschluckt ein `@` im
 * Fließtext den Rest des Satzes als Suchanfrage. Drei Dinge schließen das Dropdown:
 * `esc`, die Auswahl eines Treffers — und ein Ergebnis ohne Treffer (das entscheidet der
 * Aufrufer, hier steht nur die Textregel). Der dritte Fall ist nicht Kosmetik: Solange
 * `mentionOpen` gilt, fängt der Chat die Eingabetaste ab. Bliebe das Dropdown bei
 * sinnloser Anfrage offen, ließe sich die Nachricht nicht mehr abschicken.
 */

/**
 * Länge, ab der keine Anfrage mehr daraus wird.
 *
 * Kein Titel ist so lang; was darüber hinausgeht, ist Fließtext hinter einem `@`. Der
 * Deckel greift, bevor die Abbruchregel „keine Treffer" greifen kann, und spart die
 * Anfragen dorthin.
 */
export const ANFRAGE_MAX = 80

// Das `@` muss am Zeilenanfang oder hinter einem Leerzeichen stehen — sonst löste jede
// E-Mail-Adresse im Text das Dropdown aus. Bis 09/2026 tat sie das („jan@example.de"),
// blieb aber folgenlos, weil die Anfrage am nächsten Leerzeichen endete. Mit erlaubten
// Leerzeichen wäre daraus eine Anfrage über den halben Satz geworden.
const AUSLOESER = /(?:^|\s)@([^@\n]*)$/

/**
 * Die Anfrage hinter dem `@` links vom Cursor — oder `null`, wenn keine gilt.
 *
 * @param {string} textVorCursor Der Text von Feldanfang bis Cursor.
 * @returns {string|null}
 */
export function mentionAnfrage(textVorCursor) {
  const treffer = (textVorCursor ?? '').match(AUSLOESER)
  if (!treffer) return null
  const anfrage = treffer[1]
  if (anfrage.length > ANFRAGE_MAX) return null
  return anfrage
}

/**
 * Das `@`-Fragment aus dem Text entfernen — beim Übernehmen eines Treffers.
 *
 * Muss dieselbe Stelle treffen wie {@link mentionAnfrage}: Nähme das Entfernen eine
 * andere Regel, bliebe bei mehrwortigen Anfragen ein Rest im Eingabefeld stehen.
 */
export function ohneMentionFragment(textVorCursor) {
  return (textVorCursor ?? '').replace(/(^|\s)@[^@\n]*$/, '$1')
}
