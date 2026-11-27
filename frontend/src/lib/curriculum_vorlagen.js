/**
 * Curriculum-Vorlagen gesammelt einspielen (0.62, Päckchen BH) — die Regeln des Dialogs.
 *
 * Nur Admins. Viele YAML-Dateien auf einmal; das Backend prüft sie einzeln
 * (`POST /context/curricula/import/stapel/pruefen`) und legt aus jeder fehlerfreien einen
 * **Entwurf** an (`…/stapel`). Was entsteht, sagt es je Datei in `art`.
 */
import { dateiLesen } from './curriculum_yaml_import.js'

/** Dateien je Durchgang und ihre Summe — wie im Backend (`curriculum_stapel.py`). */
export const MAX_DATEIEN = 60
export const MAX_BYTES_GESAMT = 12_000_000

/**
 * Gewählte Dateien lesen. Zu große oder zu viele melden sich hier, bevor etwas hochgeht.
 * Rückgabe: `dateien` ([{name, yaml}], nach Namen sortiert) und `fehler` ([{name, fehler}]).
 */
export async function dateienLesen(liste) {
  const alle = [...(liste ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'de', { numeric: true }))
  const dateien = []
  const fehler = []
  let summe = 0
  for (const datei of alle) {
    if (dateien.length >= MAX_DATEIEN) {
      fehler.push({ name: datei.name, fehler: `Höchstens ${MAX_DATEIEN} Dateien je Durchgang.` })
      continue
    }
    const gelesen = await dateiLesen(datei)
    if (gelesen.fehler) {
      fehler.push({ name: datei.name, fehler: gelesen.fehler })
      continue
    }
    const bytes = new TextEncoder().encode(gelesen.text).length
    if (summe + bytes > MAX_BYTES_GESAMT) {
      fehler.push({ name: datei.name, fehler: 'Zusammen zu groß (höchstens 12 MB) — bitte in einem zweiten Durchgang.' })
      continue
    }
    summe += bytes
    dateien.push({ name: datei.name, yaml: gelesen.text })
  }
  return { dateien, fehler }
}

/** Was aus einer geprüften Datei entsteht, in einem Satz. */
export function artText(d) {
  if (!d?.ok) return 'wird nicht angelegt'
  if (d.art === 'ersetzt') return `Entwurf, der „${d.ersetzt_titel ?? 'das veröffentlichte Curriculum'}“ beim Veröffentlichen ersetzt`
  if (d.art === 'zusaetzlich') return 'zusätzlicher Entwurf — es gibt schon einen, das Datum steht im Titel'
  return 'neuer Entwurf'
}

/** Beschriftung des Knopfs: „3 Entwürfe anlegen“; leer, wenn keine Datei fehlerfrei ist. */
export function anlegenText(zahlen) {
  const n = zahlen?.ok ?? 0
  if (!n) return ''
  return n === 1 ? '1 Entwurf anlegen' : `${n} Entwürfe anlegen`
}

/** Nur die fehlerfreien Dateien gehen ans Anlegen — in der Reihenfolge der Prüfung. */
export function anzulegen(dateien, vorschau) {
  const ok = new Set((vorschau?.dateien ?? []).filter((d) => d.ok).map((d) => d.datei))
  return dateien.filter((d) => ok.has(d.name))
}

/** Satz nach dem Anlegen. */
export function ergebnisText(zahlen) {
  const ok = zahlen?.ok ?? 0
  const f = zahlen?.fehler ?? 0
  const teil = ok === 1 ? '1 Entwurf angelegt' : `${ok} Entwürfe angelegt`
  return f ? `${teil}, ${f} ${f === 1 ? 'Datei' : 'Dateien'} mit Fehlern.` : `${teil}.`
}
