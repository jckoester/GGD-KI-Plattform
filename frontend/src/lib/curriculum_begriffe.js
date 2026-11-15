/**
 * Begriffe und Fachmethoden am Eintrag eines Curriculums (0.44, Päckchen AQ).
 *
 * Gespeichert sind **Namen** (`[{name, fassung?}]`), keine Verweise. Ob es einen Namen als
 * Begriff gibt, sagt die Auflösung des Servers (`curriculum.begriffe`, nachgereicht über
 * `aufloesenCurriculumBegriffe`) — sie steht neben dem Baum, nicht in den Einträgen, weil der
 * Editor die Einträge als Ganzes zurückschreibt. Backend: `app/context/curriculum_begriffe.py`.
 */

/** Gleiche Schreibweise wie der Server: klein, ein Leerraum, Bindestrich-Varianten gleich. */
export function nameSchluessel(name) {
  return String(name ?? '')
    .replace(/[‐‑]/g, '-')
    .replace(/­/g, '')
    .toLocaleLowerCase('de')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ')
}

/** Wie der Server: höchstens so viele Zeichen je Name (`NAME_LAENGE`). */
export const NAME_LAENGE = 200

function leerraum(s) {
  return String(s ?? '').split(/\s+/).filter(Boolean).join(' ').slice(0, NAME_LAENGE)
}

/** Ein Eintrag der Liste: `{name}` oder `{name, fassung}`; `null`, wenn der Name leer ist. */
export function namensEintrag(name, fassung = null) {
  const n = leerraum(name)
  if (!n) return null
  const f = leerraum(fassung)
  return f ? { name: n, fassung: f } : { name: n }
}

function gleich(a, b) {
  return nameSchluessel(a.name) === nameSchluessel(b.name) &&
    (a.fassung ?? '').toLocaleLowerCase('de') === (b.fassung ?? '').toLocaleLowerCase('de')
}

/** Liste plus Eintrag — ohne Dublette (Name und Fassung). */
export function mitName(liste, eintrag) {
  if (!eintrag) return liste ?? []
  return (liste ?? []).some((e) => gleich(e, eintrag)) ? liste : [...(liste ?? []), eintrag]
}

/** Liste ohne den Eintrag an Stelle `i`. */
export function ohneName(liste, i) {
  return (liste ?? []).filter((_, j) => j !== i)
}

/** Fassung eines Eintrags setzen (Auswahl bei *mehrdeutig*, E4). */
export function mitFassung(liste, i, fassung) {
  return (liste ?? []).map((e, j) => (j === i ? namensEintrag(e.name, fassung) : e))
}

// ── Auflösung ────────────────────────────────────────────────────────────────

function aufloesungsSchluessel(name, fassung) {
  return `${name}\u0000${fassung ?? ''}`
}

/** Auflösung des Servers als Map, damit ein Chip seinen Zustand findet. */
export function aufloesungsMap(liste, bisher = null) {
  const map = new Map(bisher ?? [])
  for (const a of liste ?? []) map.set(aufloesungsSchluessel(a.name, a.fassung), a)
  return map
}

/** Zustand eines Chips: Auflösung oder `null` (noch nicht geprüft). */
export function aufloesungVon(map, eintrag) {
  return map?.get(aufloesungsSchluessel(eintrag.name, eintrag.fassung ?? null)) ?? null
}

/** Welche Einträge der Server noch nicht geprüft hat. */
export function ungeprueft(eintraege, map) {
  return (eintraege ?? []).filter((e) => !aufloesungVon(map, e))
}

/** Alle Begriffe der Einträge eines Curriculums (für erneutes Prüfen nach dem Anlegen). */
export function begriffeImCurriculum(curriculum) {
  const aus = []
  for (const kap of curriculum?.kapitel ?? []) {
    for (const ls of kap.lernsequenzen ?? []) {
      for (const e of ls.metadata?.eintraege ?? []) {
        for (const b of e.begriffe ?? []) aus.push(b)
      }
    }
  }
  return aus
}

// ── Darstellung ──────────────────────────────────────────────────────────────

/**
 * Farbe je Zustand (E5): verknüpft violett wie die Begriffe der Stunde, Platzhalter
 * gestrichelt, mehrdeutig gelb, ungeprüft schlicht. Nur semantische Tokens.
 */
export const CHIP_KLASSEN = {
  gefunden: 'bg-light-pu/20 text-light-pu dark:bg-dark-pu/20 dark:text-dark-pu border border-transparent',
  fehlt: 'border border-dashed border-light-tx-2 dark:border-dark-tx-2 text-light-tx-2 dark:text-dark-tx-2',
  mehrdeutig: 'bg-light-ye-bg dark:bg-dark-ye-bg text-light-tx dark:text-dark-tx border border-light-ye dark:border-dark-ye',
  ungeprueft: 'border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2',
  fachmethode: 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx border border-transparent',
}

export function chipZustand(aufloesung) {
  return aufloesung?.zustand ?? 'ungeprueft'
}

/** Beschriftung am Chip: der Name, bei gewählter Fassung mit ihr, bei Bezugsfach mit dem Fach. */
export function chipText(eintrag, aufloesung) {
  let text = eintrag.name
  if (eintrag.fassung) text += ` (${eintrag.fassung})`
  if (aufloesung?.zustand === 'gefunden' && aufloesung.bezugsfach && aufloesung.fach) text += ` · ${aufloesung.fach}`
  return text
}

/** Tooltip je Zustand. */
export function chipHinweis(aufloesung, { kannAnlegen = false } = {}) {
  switch (aufloesung?.zustand) {
    case 'gefunden':
      return aufloesung.titel ? `Begriff „${aufloesung.titel}“ in der Bibliothek` : 'Begriff in der Bibliothek'
    case 'fehlt':
      return kannAnlegen
        ? 'Diesen Begriff gibt es in der Bibliothek noch nicht — du kannst ihn anlegen.'
        : 'Diesen Begriff gibt es in der Bibliothek noch nicht. Anlegen kann die Fachschaft.'
    case 'mehrdeutig': {
      const fassungen = (aufloesung.kandidaten ?? []).map((k) => k.fassung || 'ohne Fassung')
      return `Mehrere Begriffe dieses Namens (${fassungen.join(', ')}) — wähle die Fassung.`
    }
    default:
      return 'Wird geprüft …'
  }
}

/** Darf die Person im Fach Begriffe anlegen? Mitglied der Fachschaft des Fachs (E6). */
export function kannAnlegen(fachschaften, subjectId) {
  return subjectId != null && (fachschaften ?? []).some((g) => g.subject_id === subjectId)
}

/** Link zum Anlegen eines fehlenden Begriffs (Weg 1). */
export function anlegenPfad(subjectId, name, back) {
  const p = new URLSearchParams()
  if (subjectId != null) p.set('subject_id', String(subjectId))
  p.set('titel', name)
  if (back) p.set('back', back)
  return `/knowledge/collections/begriff/new?${p}`
}

/** Aus einem Suchtreffer: der Titel und, falls der Baustein eine trägt, seine Fassung (E4). */
export function ausTreffer(node) {
  return namensEintrag(node?.title, node?.metadata?.fassung ?? null)
}

/**
 * Was Enter übernimmt: einen Treffer mit genau dem getippten Namen, sonst den mit Pfeiltasten
 * angesteuerten, sonst den Text, wie er dasteht — den es vielleicht noch nicht gibt.
 */
export function enterWahl(text, treffer, aktiv, navigiert, titelVon = (t) => t.title) {
  const k = nameSchluessel(text)
  const genau = (treffer ?? []).find((t) => nameSchluessel(titelVon(t)) === k)
  if (genau) return { treffer: genau }
  if (navigiert && treffer?.[aktiv]) return { treffer: treffer[aktiv] }
  return k ? { text } : null
}

/** Alle Fachmethoden der Einträge eines Curriculums — auch die noch nicht gespeicherten. */
export function fachmethodenImCurriculum(curriculum) {
  const aus = []
  for (const kap of curriculum?.kapitel ?? []) {
    for (const ls of kap.lernsequenzen ?? []) {
      for (const e of ls.metadata?.eintraege ?? []) {
        for (const f of e.fachmethoden ?? []) aus.push(f.name)
      }
    }
  }
  return aus
}

/**
 * Vorschläge für Fachmethoden: die des Servers (gespeicherte Curricula des Fachs) und die aus
 * dem offenen Editor, die dort noch fehlen — sonst kämen Namen erst nach dem Speichern.
 */
export function fachmethodenVorschlaege(server, lokal, q) {
  const gesucht = nameSchluessel(q)
  const aus = [...(server ?? [])]
  const bekannt = new Set(aus.map((m) => nameSchluessel(m.name)))
  const neu = new Map()
  for (const name of lokal ?? []) {
    const k = nameSchluessel(name)
    if (!k || bekannt.has(k) || (gesucht && !k.includes(gesucht))) continue
    const m = neu.get(k) ?? { name, anzahl: 0 }
    m.anzahl += 1
    neu.set(k, m)
  }
  return [...aus, ...neu.values()].sort((a, b) => {
    const vorn = (m) => (gesucht && nameSchluessel(m.name).startsWith(gesucht) ? 0 : 1)
    return vorn(a) - vorn(b) || b.anzahl - a.anzahl || a.name.localeCompare(b.name, 'de')
  })
}
