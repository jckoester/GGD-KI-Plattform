/**
 * Die Regeln der Unterrichtsgruppen-Seite — ohne Markup.
 *
 * Dieselbe Seite bedient beide Rollen: Was eine Schüler:in „mein Fach Mathematik"
 * nennt, ist im Datenmodell die Unterrichtsgruppe — genau das, was die Lehrkraft
 * „Klasse 8c" nennt. Was sich zwischen den Rollen unterscheidet, ist keine andere
 * Seite, sondern ein Sichtbarkeitsschalter.
 *
 * Hier steht nur, was sich ohne Browser prüfen lässt; das Projekt hat keine
 * Komponententests.
 */

/**
 * Die Reiter der Lehrkraft-Ansicht, in Anzeigereihenfolge.
 *
 * Schüler:innen sehen **keine** Reiter — für sie gibt es nur die Übersicht.
 * `klasse` ist im September 2026 entfallen: Was der Reiter versprach (Freigabe und
 * Sichtbarkeitsfenster je Gruppe), liegt längst am Assistenten selbst
 * (`scope_group_id`, `available_from`, `available_until`). Ein Reiter, der
 * Vorhandenes ankündigt, ist schlimmer als keiner.
 */
export const REITER = [
  { id: 'uebersicht', label: 'Übersicht' },
  { id: 'curriculum', label: 'Curriculum' },
  { id: 'bildungsplan', label: 'Bildungsplan' },
  { id: 'archiv', label: 'Archiv' },
  { id: 'kontext', label: 'weiterer Kontext' },
]

/**
 * Kennungen, die es einmal gab und die in Lesezeichen stehen.
 *
 * Bis 09/2026 hieß die Übersicht `vorbereitung`. Die Kennung steht in gespeicherten
 * Links; sie fallen zu lassen hieße, dass ein Lesezeichen wortlos auf einer leeren
 * Seite landet — der Reiter-Zustand kommt aus der URL, ein unbekannter Wert trifft
 * dann keinen Zweig.
 */
const ALTE_KENNUNGEN = {
  vorbereitung: 'uebersicht',
}

const GUELTIG = new Set(REITER.map((r) => r.id))

/**
 * Welcher Reiter zu einem `?tab=`-Wert gehört.
 *
 * Unbekannte und fehlende Werte fallen auf die Übersicht zurück — sie ist die
 * Antwort auf „wo war ich stehengeblieben?", also der richtige Ort für jemanden,
 * der aus Versehen hier gelandet ist.
 *
 * @param {string|null|undefined} roh  der Wert aus der Adresszeile
 * @returns {string} eine Kennung aus {@link REITER}
 */
export function aktiverReiter(roh) {
  if (!roh) return 'uebersicht'
  const uebersetzt = ALTE_KENNUNGEN[roh] ?? roh
  return GUELTIG.has(uebersetzt) ? uebersetzt : 'uebersicht'
}

// ── Die Schüler-Weiche ──────────────────────────────────────────────────────

/**
 * Die eigenen Unterrichtsgruppen eines Fachs.
 *
 * @param {Array<{id:number, subject_id:number|null}>} gruppen  aus `myTeachingGroups`
 * @param {number|null|undefined} subjectId
 */
export function gruppenImFach(gruppen, subjectId) {
  if (subjectId == null) return []
  return (gruppen ?? []).filter((g) => g.subject_id === subjectId)
}

/**
 * Was `/subjects/<slug>` für eine Schüler:in tun soll.
 *
 * Für Schüler:innen gibt es **keine** Fach-Ebene: Jeder ihrer Chats, jeder ihrer
 * Bausteine hängt an einer Unterrichtsgruppe. Die Fachseite hat für sie deshalb
 * keinen eigenen Inhalt — sie ist eine Weiche.
 *
 * Zwei Gruppen im selben Fach *sollten* bei Schüler:innen nicht vorkommen. Der Fall
 * wird trotzdem behandelt: Stillschweigend die erste zu nehmen hieße, die andere
 * unerreichbar zu machen, ohne dass jemand es merkt.
 *
 * @returns {{art:'keine'}|{art:'weiterleiten', gruppe:object}|{art:'auswahl', gruppen:Array}}
 */
export function schuelerWeiche(gruppen, subjectId) {
  const eigene = gruppenImFach(gruppen, subjectId)
  if (eigene.length === 0) return { art: 'keine' }
  if (eigene.length === 1) return { art: 'weiterleiten', gruppe: eigene[0] }
  return { art: 'auswahl', gruppen: eigene }
}

/**
 * Wohin ein Fach-Eintrag der Übersicht `/subjects` für Schüler:innen führt.
 *
 * Bei genau einer Gruppe direkt dorthin — der Zwischenschritt über die Weiche wäre
 * eine Seite, die nur weiterleitet. Bei mehreren auf die Weiche, die dann fragt.
 *
 * @param {string|null} slug
 * @param {Array} gruppen  die eigenen Gruppen **dieses** Fachs
 */
export function fachZielSchueler(slug, gruppen) {
  if (!slug) return '/history'
  const eigene = gruppen ?? []
  return eigene.length === 1
    ? `/subjects/${slug}/groups/${eigene[0].id}`
    : `/subjects/${slug}`
}
