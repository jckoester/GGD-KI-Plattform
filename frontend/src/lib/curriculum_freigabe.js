/**
 * Veröffentlichen eines Curriculum-Entwurfs (0.45, Päckchen AP Teil A) — die Zeilen der
 * Übersicht. Die Zahlen kommen vom Backend (`GET /context/curricula/{id}/publish`); die
 * Übersicht warnt, sie sperrt nicht.
 */

/** @returns {{text: string, warnung: boolean}[]} */
export function uebersichtZeilen(u) {
  if (!u) return []
  const zeilen = []
  const std = Number.isInteger(u.stunden) ? u.stunden : Math.round(u.stunden * 10) / 10
  zeilen.push({ text: `${std} Stunden in den Lernsequenzen`, warnung: !u.stunden })
  if (u.ik.gesamt) {
    const fehlt = u.ik.fehlt
      ? `, ${u.ik.fehlt} nicht verknüpft${u.ik.fehlt_anderswo ? ` (${u.ik.fehlt_anderswo} davon in anderen Curricula des Bands)` : ''}`
      : ''
    zeilen.push({
      text: `${u.ik.verknuepft} von ${u.ik.gesamt} inhaltsbezogenen Kompetenzen verknüpft${u.ik.partiell ? `, ${u.ik.partiell} partiell` : ''}${fehlt}`,
      warnung: u.ik.fehlt - u.ik.fehlt_anderswo > 0,
    })
  }
  if (u.fremdes_fach) zeilen.push({ text: `${u.fremdes_fach} Kompetenzen aus einem anderen Fach`, warnung: true })
  if (u.veraltet) zeilen.push({ text: `${u.veraltet} als veraltet markierte Kompetenzen`, warnung: true })
  if (u.begriffe_fehlend) zeilen.push({ text: `${u.begriffe_fehlend} Begriffe fehlen in der Bibliothek`, warnung: true })
  if (u.begriffe_mehrdeutig) zeilen.push({ text: `${u.begriffe_mehrdeutig} Begriffe ohne gewählte Fassung`, warnung: true })
  if (u.vorgaenger) {
    zeilen.push({
      text: `Ersetzt „${u.vorgaenger.title}“ — es wird archiviert. ${u.einheiten_umgehaengt} Einheiten dieses Schuljahrs wandern auf die neuen Kapitel.`,
      warnung: false,
    })
    for (const e of u.einheiten_ohne_kapitel) {
      zeilen.push({
        text: `Eine Einheit von ${e.gruppe || 'einer Gruppe'} hängt an „${e.kapitel}“, das es im Entwurf nicht mehr gibt — sie behält das alte Kapitel.`,
        warnung: true,
      })
    }
  }
  return zeilen
}
