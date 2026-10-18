/**
 * Begriffe der Stunde in der Kompetenzleiste (0.17, Päckchen A1, Schritt 3).
 *
 * Ein Begriff steht in `refs` neben den Kompetenzen, mit `typ: 'concept'`. Die Leiste zeigt
 * beide getrennt, und jede Gruppe wird für sich bearbeitet: Kompetenzen ändern lässt die
 * Begriffe stehen und umgekehrt.
 */

/**
 * Was als Begriff der Stunde gilt — dieselbe Liste wie `BEGRIFF_TYPEN` in
 * `backend/app/planning/schemas.py` (ein Backend-Test vergleicht beide).
 */
export const BEGRIFF_TYPEN = ['begriff', 'stoffsteckbrief']

/** So viele Treffer zeigt die Suche der Leiste. */
export const SUCHGRENZE = 20

export function istBegriff(ref) {
  return ref?.typ === 'concept'
}

/** `refs` getrennt: Kompetenzen (ik/pk) und Begriffe — je in der gespeicherten Reihenfolge. */
export function aufteilen(refs) {
  const kompetenzen = []
  const begriffe = []
  for (const ref of refs ?? []) (istBegriff(ref) ? begriffe : kompetenzen).push(ref)
  return { kompetenzen, begriffe }
}

/**
 * Die Aliase, unter denen die Stunde einen Begriff nennt („σ-Komplex, Arenium-Ion" bei
 * „elektrophile Substitution") — leer, wenn sie ihn unter seinem Titel nennt.
 */
export function aliaseText(ref) {
  return (ref?.aliase ?? []).filter(Boolean).join(', ')
}

/** Titel und Aliase in einer Zeile, etwa für den Tooltip. */
export function begriffAnzeige(ref) {
  const titel = ref?.titel ?? ref?.node_id ?? ''
  const aliase = aliaseText(ref)
  return aliase ? `${titel} · ${aliase}` : titel
}

/**
 * Das Alias, über das ein Treffer gefunden wurde — `null`, wenn der Titel passt.
 *
 * Dieselbe Regel wie der Server (`filters.py`: Titel oder Alias enthält das Gesuchte,
 * ohne Groß-/Kleinschreibung). Wer „σ-Kom" tippt und „elektrophile Substitution" wählt,
 * meint den σ-Komplex — der Name soll in der Leiste stehen bleiben (0.18).
 */
export function getroffenesAlias(node, q) {
  const gesucht = (q ?? '').trim().toLocaleLowerCase('de')
  if (!gesucht || (node?.title ?? '').toLocaleLowerCase('de').includes(gesucht)) return null
  return (node?.aliase ?? []).find((a) => a.toLocaleLowerCase('de').includes(gesucht)) ?? null
}

/**
 * Der Eintrag in `refs` für einen Treffer aus `GET /context/nodes` — mit dem Alias, über
 * das er gefunden wurde, falls nicht über den Titel.
 */
export function begriffAusTreffer(node, q = '') {
  const eintrag = {
    node_id: node.id,
    typ: 'concept',
    titel: node.title,
    partiell: false,
    content_type: node.content_type,
  }
  const alias = getroffenesAlias(node, q)
  return alias ? { ...eintrag, aliase: [alias] } : eintrag
}

/** Einen Begriff dazu — nur, wenn er noch nicht drinsteht. Kompetenzen bleiben. */
export function mitBegriff(refs, eintrag) {
  if ((refs ?? []).some((r) => r.node_id === eintrag.node_id)) return refs
  return [...(refs ?? []), eintrag]
}

/** Einen Begriff weg. Kompetenzen bleiben, auch eine mit derselben Kennung nicht. */
export function ohneBegriff(refs, nodeId) {
  return (refs ?? []).filter((r) => !(istBegriff(r) && r.node_id === nodeId))
}

/**
 * Ein einzelnes Alias eines Begriffs weg; der Begriff bleibt, auch ohne Aliase (0.18).
 * Viele Aliase im Speicher sind Unterbegriffe — nicht jeder passt zu jeder Stunde.
 */
export function ohneAlias(refs, nodeId, alias) {
  return (refs ?? []).map((r) => {
    if (!istBegriff(r) || r.node_id !== nodeId) return r
    const aliase = (r.aliase ?? []).filter((a) => a !== alias)
    if (aliase.length) return { ...r, aliase }
    const { aliase: _, ...ohne } = r
    return ohne
  })
}

/** Die Parameter der Suche: Begriffe des Fachs und seiner Bezugsfächer, aktive. */
export function suchparameter(q, subjectId) {
  const params = { q, content_type: BEGRIFF_TYPEN, status: 'active', limit: SUCHGRENZE }
  if (subjectId != null) {
    params.subject_id = subjectId
    params.mit_bezugsfaechern = true
  }
  return params
}

/**
 * Treffer ordnen: Wer mit dem Gesuchten beginnt, zuerst, dann alphabetisch.
 *
 * Der Endpunkt sortiert nach Anlagedatum — für eine Liste richtig, für eine Suche nicht:
 * Bei „Sub" stünde der zuletzt importierte Begriff vor „Substitution".
 */
export function ordneTreffer(treffer, q) {
  const gesucht = (q ?? '').trim().toLocaleLowerCase('de')
  const rang = (n) => ((n.title ?? '').toLocaleLowerCase('de').startsWith(gesucht) ? 0 : 1)
  return [...(treffer ?? [])].sort(
    (a, b) => rang(a) - rang(b) || (a.title ?? '').localeCompare(b.title ?? '', 'de'),
  )
}

/** Fachname am Treffer — nur, wenn er aus einem Bezugsfach stammt. */
export function bezugsfach(node, subjectId, faecher) {
  if (node?.subject_id == null || node.subject_id === subjectId) return null
  return faecher?.[node.subject_id]?.name ?? null
}

// ── Vorschläge aus den Phasentexten (0.18, Schritt 6) ────────────────────────

/**
 * Was vom Vorschlag noch offen ist: ohne die Begriffe, die inzwischen eingetragen oder
 * verworfen sind. Der Server filtert beim Laden genauso; hier zählt der Stand der Seite,
 * damit ein ✓ oder ✕ sofort wirkt, ohne neu zu laden.
 */
export function offeneVorschlaege(vorschlag, refs, verworfen) {
  if (!vorschlag) return { eintraege: [], frueher: [], ohne: [] }
  const weg = new Set([...(refs ?? []).map((r) => r.node_id), ...(verworfen ?? [])])
  return {
    eintraege: (vorschlag.eintraege ?? []).filter((e) => !weg.has(e.node_id)),
    frueher: (vorschlag.frueher ?? []).filter((f) => !weg.has(f.node_id)),
    ohne: vorschlag.ohne_knoten ?? [],
  }
}

/** Ein Vorschlag als Eintrag in `refs` — samt den Aliasen, unter denen die Stunde ihn nennt. */
export function refAusVorschlag(eintrag) {
  const ref = {
    node_id: eintrag.node_id,
    typ: 'concept',
    titel: eintrag.titel,
    partiell: false,
    content_type: eintrag.content_type ?? 'begriff',
  }
  return eintrag.aliase?.length ? { ...ref, aliase: [...eintrag.aliase] } : ref
}

/** Einen Begriff verwerfen: in `refs_dismissed`, ohne Doppel. Er kommt nicht wieder. */
export function mitVerworfen(verworfen, nodeId) {
  return (verworfen ?? []).includes(nodeId) ? verworfen : [...(verworfen ?? []), nodeId]
}

/** „12.10." aus „2026-10-12". */
export function kurzdatum(iso) {
  const [, m, t] = (iso ?? '').split('-')
  return t && m ? `${Number(t)}.${Number(m)}.` : ''
}

/** Was die Leiste sagt, wenn kein neuer Vorschlag kam (`fehler` aus dem Endpunkt). */
export function vorschlagFehlerText(fehler) {
  if (!fehler) return null
  return {
    budget: 'Dein Budget ist aufgebraucht — keine neuen Vorschläge.',
    zeit: 'Keine Antwort in der Zeit. Bitte später noch einmal.',
    kein_fach: 'Die Stunde hat kein Fach — Vorschläge gehen nur mit Fach.',
    kein_modell: 'Begriffsvorschläge sind an dieser Schule nicht eingerichtet.',
  }[fehler] ?? 'Ein Vorschlag war gerade nicht möglich.'
}

