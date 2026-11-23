/**
 * Curriculum aus YAML importieren (0.56, Päckchen BA Schritt 4) — die Regeln des Dialogs.
 *
 * Die Vorschau kommt vom Backend (`POST /context/curricula/import/pruefen`, der echte Import,
 * danach verworfen). Hier steht nur, was der Dialog daraus macht: welches Curriculum als Ersatz
 * vorausgewählt ist (F2), ob „Anlegen“ geht und wie die Summen gelesen werden.
 */

/** Größte Datei, die das Backend annimmt (Zeichen; die genaue Grenze in Bytes prüft es selbst). */
export const MAX_ZEICHEN = 200_000

/**
 * Veröffentlichte Curricula gleichen Fachs, Jahrgangs und Edition, die der Entwurf ersetzen
 * kann — ohne die, zu denen es schon einen offenen Entwurf gibt.
 */
export function ersetzbar(vorschau) {
  return (vorschau?.vorhanden ?? []).filter((v) => !v.offener_entwurf)
}

/**
 * Vorauswahl (F2): Gibt es genau ein ersetzbares Curriculum, ersetzt der Entwurf es beim
 * Veröffentlichen. Bei mehreren (etwa parallele Bänder) wählt die Lehrkraft selbst; ohne eins
 * entsteht ein neuer Entwurf (`null`).
 */
export function vorauswahl(vorschau) {
  const kandidaten = ersetzbar(vorschau)
  return kandidaten.length === 1 ? kandidaten[0].id : null
}

/** Ob „Als Entwurf anlegen“ geht: eine Vorschau ohne Fehler zu genau diesem Text und dieser Wahl. */
export function kannAnlegen(vorschau, { geaendert = false } = {}) {
  return !!vorschau?.ok && !(vorschau.fehler?.length) && !geaendert
}

/** „3 Kapitel · 12 Lernsequenzen · 40 Einträge · 56 Stunden“ — Stunden nur, wenn angegeben. */
export function summenText(summen) {
  if (!summen) return ''
  const teile = [
    `${summen.kapitel} Kapitel`,
    `${summen.lernsequenzen} ${summen.lernsequenzen === 1 ? 'Lernsequenz' : 'Lernsequenzen'}`,
    `${summen.eintraege} ${summen.eintraege === 1 ? 'Eintrag' : 'Einträge'}`,
  ]
  if (summen.stunden) teile.push(`${summen.stunden.toLocaleString('de-DE')} Stunden`)
  return teile.join(' · ')
}

/** Text einer gewählten Datei, mit Grenze — eine zu große meldet sich, bevor sie hochgeht. */
export async function dateiLesen(datei) {
  if (!datei) return { text: '', fehler: null }
  if (datei.size > MAX_ZEICHEN * 4) return { text: '', fehler: 'Die Datei ist zu groß.' }
  const text = await datei.text()
  if (text.length > MAX_ZEICHEN) return { text: '', fehler: 'Die Datei ist zu groß (höchstens 200 000 Zeichen).' }
  return { text, fehler: null }
}
