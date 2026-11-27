/**
 * Absprachen zwischen Fächern am Kapitel (0.63, Päckchen AY Teil 2) — Regeln für Editor und Anzeige.
 *
 * Gespeichert am eigenen Kapitel (`metadata.absprachen`), geprüft im Backend
 * (`app/context/absprachen.py`). Hier: Beschriftungen, das Formular und was daraus wird.
 */

/** Arten in der Reihenfolge der Auswahl; `vorher` = das andere Kapitel liegt vor diesem. */
export const ARTEN = ['vorher', 'gleichzeitig', 'nachher', 'abgestimmt']
export const ZEITLICH = new Set(['vorher', 'gleichzeitig', 'nachher'])
export const GEGENART = { vorher: 'nachher', nachher: 'vorher', gleichzeitig: 'gleichzeitig', abgestimmt: 'abgestimmt' }

/** Beschriftung der Auswahl — aus Sicht dieses Kapitels. */
export const ART_AUSWAHL = {
  vorher: 'vorher — das andere Kapitel kommt zuerst',
  gleichzeitig: 'gleichzeitig — etwa in denselben Wochen',
  nachher: 'danach — das andere Kapitel kommt später',
  abgestimmt: 'abgestimmt — inhaltlich, ohne Zeitpunkt',
}

/** Kurzform in der Liste. */
export const ART_KURZ = { vorher: 'vorher', gleichzeitig: 'gleichzeitig', nachher: 'danach', abgestimmt: 'abgestimmt' }

export const MAX_TEXT = 1000
export const MAX_JE_KAPITEL = 20

/** Leeres Formular, wahlweise vorbelegt (etwa aus einer Fundstelle der Querverweise). */
export function formular(vorbelegung = {}) {
  return {
    id: vorbelegung.id ?? null,
    fach_code: vorbelegung.fach_code ?? '',
    curriculum_id: vorbelegung.curriculum_id ?? '',
    kapitel_id: vorbelegung.kapitel_id ?? '',
    kapitel_titel: vorbelegung.kapitel_titel ?? '',
    art: vorbelegung.art ?? (vorbelegung.kapitel_id ? 'vorher' : 'abgestimmt'),
    text: vorbelegung.text ?? '',
  }
}

/** Was im Formular noch fehlt — leer, wenn es sich übernehmen lässt. Wie im Backend. */
export function formularFehler(f, { vorhandene = [], eigenesFach = null } = {}) {
  if (!f.fach_code) return 'Wähle das andere Fach.'
  if (eigenesFach && f.fach_code === eigenesFach) return 'Eine Absprache gilt einem anderen Fach.'
  if (ZEITLICH.has(f.art) && !f.kapitel_id && !f.kapitel_titel) return 'Für „vorher“, „gleichzeitig“ und „danach“ wähle ein Kapitel des anderen Fachs.'
  if (f.art === 'abgestimmt' && !f.text.trim()) return 'Schreib, was abgestimmt ist.'
  if (f.text.length > MAX_TEXT) return `Der Text ist zu lang (höchstens ${MAX_TEXT} Zeichen).`
  const doppelt = vorhandene.some((a) => a.id !== f.id && a.fach_code === f.fach_code && a.art === f.art
    && (a.kapitel_id || a.kapitel_titel || null) === (f.kapitel_id || f.kapitel_titel || null))
  if (doppelt) return 'Dieselbe Absprache steht schon da.'
  if (!f.id && vorhandene.length >= MAX_JE_KAPITEL) return `Höchstens ${MAX_JE_KAPITEL} Absprachen je Kapitel.`
  return ''
}

/** Aus dem Formular der Eintrag fürs Kapitel. Ohne Kapitel fällt auch der Titel weg. */
export function ausFormular(f) {
  const mitKapitel = !!f.kapitel_id
  return {
    ...(f.id ? { id: f.id } : {}),
    fach_code: f.fach_code,
    kapitel_id: mitKapitel ? f.kapitel_id : null,
    kapitel_titel: mitKapitel ? f.kapitel_titel || null : (f.kapitel_titel || null),
    art: f.art,
    text: f.text.trim(),
  }
}

/** Liste nach dem Übernehmen: ersetzt die Absprache mit derselben `id` oder hängt an. */
export function uebernehmen(liste, eintrag) {
  const alt = liste ?? []
  if (eintrag.id && alt.some((a) => a.id === eintrag.id)) return alt.map((a) => (a.id === eintrag.id ? eintrag : a))
  return [...alt, eintrag]
}

/** Gegenabsprache zu einer Absprache von außen (Schritt 4): Fach und Kapitel der Quelle, Gegenart. */
export function gegenabsprache(vonAussen) {
  return formular({
    fach_code: vonAussen.fach_code,
    curriculum_id: vonAussen.quelle?.curriculum_id,
    kapitel_id: vonAussen.quelle?.kapitel_id,
    kapitel_titel: vonAussen.quelle?.kapitel,
    art: vonAussen.art_hier ?? GEGENART[vonAussen.art] ?? 'abgestimmt',
    text: vonAussen.text ?? '',
  })
}

/** Fächer zur Auswahl: alle mit Kürzel außer dem eigenen, nach Name. */
export function faecherZurAuswahl(faecher, eigenesFachId) {
  return (faecher ?? []).filter((s) => s.fach_code && s.id !== eigenesFachId)
    .sort((a, b) => a.name.localeCompare(b.name, 'de'))
}

/**
 * Fachfarbe als Rahmen und leichte Tönung (wie die Marken der Querverweise) — die Schrift bleibt
 * in den Text-Tokens, damit sie auf jeder Fachfarbe und in beiden Modi lesbar ist.
 */
export function fachToenung(farbe) {
  if (!farbe) return ''
  const hex = /^#[0-9a-f]{6}$/i.test(farbe) ? ` background-color: ${farbe}1f;` : ''
  return `border-color: ${farbe};${hex}`
}

/** Curricula eines Fachs zur Auswahl: gleiche Stufen zuerst; Fassung und Entwurf in Klammern. */
export function curriculaZurAuswahl(curricula, stufe = null) {
  const passt = (c) => stufe != null && c.min_grade != null && c.min_grade <= stufe && stufe <= (c.max_grade ?? c.min_grade)
  return [...(curricula ?? [])]
    .sort((a, b) => (passt(b) - passt(a)) || (a.min_grade ?? 0) - (b.min_grade ?? 0) || a.title.localeCompare(b.title, 'de'))
    .map((c) => {
      const zusatz = [c.metadata?.bp_version ?? c.bp_version, c.status === 'draft' ? 'Entwurf' : null].filter(Boolean)
      return { id: c.id, text: zusatz.length ? `${c.title} (${zusatz.join(', ')})` : c.title }
    })
}

/** „Physik · Dichte“ oder „Physik · ganzes Fach“ — für die Zeile in der Liste. */
export function zielText(a, faecherJeCode = {}) {
  const fach = faecherJeCode[a.fach_code]?.name ?? a.fach ?? a.fach_code
  return `${fach} · ${a.ziel?.kapitel ?? a.kapitel_titel ?? 'ganzes Fach'}`
}

/** Die Art als Satzteil hinter dem anderen Kapitel: „Physik · Dichte — kommt vorher“. */
export const ART_SATZ = {
  vorher: 'kommt vorher',
  gleichzeitig: 'läuft gleichzeitig',
  nachher: 'kommt danach',
  abgestimmt: 'abgestimmt',
}

/** Sprungziel auf ein Kapitel eines Curriculums. */
export function kapitelPfad(ort) {
  return ort?.curriculum_id && ort?.kapitel_id ? `/knowledge/curriculum/${ort.curriculum_id}#kapitel-${ort.kapitel_id}` : null
}

/** „Dichte · Physik Kl. 8 (Entwurf)“ — das Kapitel eines Ziels oder einer Quelle. */
export function ortText(ort, kapitelTitel = null) {
  if (!ort) return kapitelTitel ?? 'ganzes Fach'
  return `${ort.kapitel} · ${ort.curriculum}${ort.status === 'draft' ? ' (Entwurf)' : ''}`
}

/** Ob es an einem Kapitel etwas zu zeigen gibt. */
export function hatAbsprachen(eigene, vonAussen) {
  return !!(eigene?.length || vonAussen?.length)
}

/** Link in den Editor, der dort die Gegenabsprache vorbelegt (Lesesicht, Schritt 4). */
export function gegenabspracheHref(curriculumId, absprache) {
  return `/knowledge/curriculum/${curriculumId}/edit?gegen=${encodeURIComponent(absprache.id)}`
}

/** Die Absprache von außen mit dieser Kennung samt eigenem Kapitel — für `?gegen=` im Editor. */
export function findeVonAussen(daten, id) {
  for (const [kapId, k] of Object.entries(daten?.kapitel ?? {})) {
    const a = (k.von_aussen ?? []).find((x) => x.id === id)
    if (a) return { kapId, absprache: a }
  }
  return null
}
