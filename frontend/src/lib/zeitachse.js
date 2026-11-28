/**
 * Anordnung der Zeitachse „Vernetzung der Fächer“ (Päckchen BE, Teil A, Schritt 4) — rein, ohne DOM.
 * (Nicht zu verwechseln mit `vernetzung.js`: Nachbarschaft eines Bausteins als Liste.)
 *
 * Die Ansicht (Schritt 5) und der PDF-Export (Schritt 7, F14 a: dasselbe SVG für eine feste
 * Seitenbreite) rechnen beide hiermit. Eingabe ist die Antwort von `GET /context/vernetzung`.
 *
 * Entschieden (Plan `Vernetzung-Zeitachse-BE-Plan`, 28.11.2026):
 * - Zeit läuft von oben nach unten, Stufe für Stufe; jede Stufe hat ihre Unterrichtswochen.
 * - Spalten: Leitlinien | linke Spuren | Rinne | Mitte | rechte Spuren | Leitperspektiven.
 *   Die erste Spur steht rechts innen, die zweite links innen, dann abwechselnd nach außen.
 * - F4: Spurbreite aus dem verfügbaren Platz; unter `SCHMAL` ohne Text, unter `MIN_SPUR` passt
 *   die Spur nicht mehr. Unter `MOBIL` nur die Mitte.
 * - F5: Absprachen als breite S-Kurve, Querverweise gestrichelt, Bereiche fein gepunktet; im
 *   eigenen Fach eine Klammer in der Rinne, die waagerecht ins spätere Kapitel einläuft.
 * - Nach Schritt 1: Spuren vorbelegt nur aus Absprachen und Kompetenz-Bezügen; Fächer nur über
 *   Bereiche sind wählbar und schalten die Bereich-Bezüge ein.
 */

import { ART_SATZ, pruefungText } from './absprachen.js'

export const PX_WOCHE = 13
export const STUFENKOPF = 42
export const STUFENABSTAND = 10
export const OBEN = 8
/** Anmerkungen zur Stufe: je eine Zeile als Aufzählung in einem Rahmen unter dem Kopf (Jan 28.11.2026). */
export const HINWEISZEILE = 16
export const HINWEISRAHMEN = 14

/** Zusätzliche Höhe einer Stufe für `n` Anmerkungen (Zeilen, Rahmen, Abstand). */
export function hinweisHoehe(n) {
  return n ? n * HINWEISZEILE + HINWEISRAHMEN : 0
}

export const MITTE = 220
export const RINNE = 64
export const ACHSE = 58
export const RANDSPALTE = 112
export const LUECKE = 18
export const SPUR_STANDARD = 150
/** Breiter wird eine Spur nicht; was dann noch frei ist, bekommt die Mitte (Jan 28.11.2026: Tabelle immer volle Breite). */
export const SPUR_MAX = 260
export const SCHMAL = 110
export const MIN_SPUR = 28
export const MOBIL = 700

/** Linienarten je Bezug (F5, mit breiteren Absprachen, Jan 28.11.2026). */
export const STIL = {
  absprache: { breite: 3, strich: null },
  kompetenz: { breite: 1.5, strich: '5 4' },
  bereich: { breite: 1, strich: '1 3' },
  eigen: { breite: 2, strich: null },
}

// ── Achse ────────────────────────────────────────────────────────────────────

/**
 * Je Stufe ihr Platz: `oben` (Kopf), `start` (erste Woche), `hoehe`, `hinweise` (Anmerkungen in
 * eigener Zeile unter dem Kopf, `stufenHinweise`). Dazu die Gesamthöhe.
 */
export function achse(stufen, { px = PX_WOCHE, fachName = '' } = {}) {
  let y = OBEN
  const je = {}
  const liste = (stufen ?? []).map((s, i) => {
    const hinweise = stufenHinweise(s, stufen[i - 1], fachName)
    const kopf = STUFENKOPF + hinweisHoehe(hinweise.length)
    const eintrag = { stufe: s.stufe, oben: y, start: y + kopf, wochen: s.wochen, hoehe: kopf + s.wochen * px, hinweise }
    je[s.stufe] = eintrag
    y += eintrag.hoehe + STUFENABSTAND
    return eintrag
  })
  return { stufen: liste, je, hoehe: y, px }
}

/**
 * Anmerkungen zu einer Stufe: kein Kalender, kein Curriculum in der geltenden Fassung,
 * Fassungswechsel gegenüber der Stufe davor (dann fehlen Bezüge im eigenen Fach).
 */
export function stufenHinweise(info, vorher = null, fachName = '') {
  const kurz = (f) => (f ? String(f).split('.')[1] ?? String(f) : '')
  return [
    info?.kalender === false && 'ohne Kalender, nur Unterrichtswochen',
    info?.curricula && !info.curricula.length
      && `kein Curriculum ${fachName}${info.fassung ? ` in der Fassung ${kurz(info.fassung)}` : ''}`.replace('  ', ' '),
    vorher?.fassung && info?.fassung && vorher.fassung !== info.fassung
      && `Fassung wechselt: Bezüge zu Kl. ${vorher.stufe} im eigenen Fach fehlen`,
  ].filter(Boolean)
}

/** Oberkante einer Unterrichtswoche (1-basiert) in einer Stufe. */
export function wocheY(a, stufe, woche) {
  const s = a.je[stufe]
  return s ? s.start + (woche - 1) * a.px : null
}

/** Kalenderwoche einer Unterrichtswoche, wenn die Stufe einen Kalender hat. */
export function kalenderwoche(stufeInfo, woche) {
  return stufeInfo?.kalenderwochen?.[woche - 1] ?? null
}

// ── Spuren ───────────────────────────────────────────────────────────────────

/**
 * Welche Fächer als Spur stehen. `faecher` in der Reihenfolge des Backends (Absprachen, dann
 * Kompetenz, dann Bereich). `gewaehlt`: Kennungen, die die Lehrkraft gewählt hat (oder null:
 * Vorgabe). Vorbelegt nur Fächer, die nicht nur über Bereiche verbunden sind.
 * Rückgabe: `spuren`, `weitere`, `bereiche` (ob die Bereich-Bezüge an sein müssen).
 */
export function spurenWaehlen(faecher, { gewaehlt = null, max = Infinity } = {}) {
  const alle = faecher ?? []
  let spuren
  if (gewaehlt) {
    spuren = gewaehlt.map((id) => alle.find((f) => f.id === id)).filter(Boolean)
  } else {
    spuren = alle.filter((f) => !f.nur_bereich)
  }
  spuren = spuren.slice(0, Math.max(0, max))
  const ids = new Set(spuren.map((f) => f.id))
  return {
    spuren,
    weitere: alle.filter((f) => !ids.has(f.id)),
    bereiche: spuren.some((f) => f.nur_bereich),
  }
}

/** Die rechte Spur innen zuerst, dann links innen, dann abwechselnd nach außen. */
export function seiten(spuren) {
  const rechts = []
  const links = []
  spuren.forEach((f, i) => (i % 2 === 0 ? rechts : links).push(f))
  return { rechts, links }
}

/**
 * Spalten für die verfügbare Breite (F4). `anzahl` Spuren werden verteilt; wie viele überhaupt
 * passen, steht in `passen`. Rückgabe: `spalten` (Schlüssel → {x, b}), `spurBreite`,
 * `schmal`, `mobil`, `passen`, `breite` (tatsächlich belegt).
 */
export const BILDSCHIRM = { ACHSE, RANDSPALTE, RINNE, MITTE, LUECKE, SPUR_STANDARD, SCHMAL, MIN_SPUR, MOBIL, SPUR_MAX }

export function spalten(breite, spurFaecher, { leitlinien = true, masse = BILDSCHIRM, fuellen = false } = {}) {
  const m = { ...BILDSCHIRM, ...masse }
  const mobil = breite < m.MOBIL
  const rand = leitlinien && !mobil ? m.RANDSPALTE : 0
  const fest = m.ACHSE + 2 * rand + m.RINNE + m.MITTE + (rand ? 2 * m.LUECKE : 0)
  const frei = Math.max(0, breite - fest)
  const passen = mobil ? 0 : Math.floor(frei / (m.MIN_SPUR + m.LUECKE))
  const n = Math.min(spurFaecher.length, passen)
  const genutzt = spurFaecher.slice(0, n)
  let spurBreite = n ? Math.min(m.SPUR_STANDARD, Math.floor(frei / n) - m.LUECKE) : 0
  let mitte = m.MITTE
  if (fuellen && !mobil) {
    // Volle Breite: Spuren wachsen bis SPUR_MAX, der Rest geht an die Mitte
    spurBreite = n ? Math.min(m.SPUR_MAX, Math.floor(frei / n) - m.LUECKE) : 0
    mitte += Math.max(0, frei - n * (spurBreite + m.LUECKE))
  }
  const { rechts, links } = seiten(genutzt)

  const sp = {}
  let x = m.ACHSE
  if (rand) { sp.leitlinien = { x, b: rand }; x += rand + m.LUECKE }
  for (const f of [...links].reverse()) { sp[f.id] = { x, b: spurBreite, seite: 'links' }; x += spurBreite + m.LUECKE }
  sp.rinne = { x, b: m.RINNE }
  x += m.RINNE
  sp.mitte = { x, b: mitte, seite: 'mitte' }
  x += mitte + m.LUECKE
  for (const f of rechts) { sp[f.id] = { x, b: spurBreite, seite: 'rechts' }; x += spurBreite + m.LUECKE }
  if (rand) { sp.leitperspektiven = { x, b: rand }; x += rand }
  return { spalten: sp, spurBreite, schmal: n > 0 && spurBreite < m.SCHMAL, mobil, passen, genutzt, breite: x }
}

// ── Kapitel ──────────────────────────────────────────────────────────────────

/**
 * Blöcke der Kapitel: je Lage ein Block {id, x, y, b, h, stufe, quelle, seite}. Kapitel ohne
 * Spalte (Fach nicht als Spur) oder ohne Lage fehlen. `anker(id)` liefert den ersten Block —
 * daran hängen die Linien.
 */
export function bloecke(kapitel, a, sp, fachId) {
  const je = new Map()
  for (const k of kapitel ?? []) {
    const spalte = k.fach_id === fachId ? sp.mitte : sp[k.fach_id]
    if (!spalte) continue
    const liste = []
    for (const l of k.lage ?? []) {
      const y = wocheY(a, l.stufe, l.von_woche)
      if (y == null) continue
      liste.push({ id: k.id, x: spalte.x, y, b: spalte.b, h: (l.bis_woche - l.von_woche + 1) * a.px - 3,
        stufe: l.stufe, quelle: l.quelle, seite: spalte.seite })
    }
    if (liste.length) je.set(k.id, liste)
  }
  return je
}

export function anker(je, id) {
  return je.get(id)?.[0] ?? null
}

/** Ob ein Block Text trägt: erst ab zwei Wochen — in einer Woche ist er nicht lesbar (Jan 28.11.2026). */
export function mitText(blk, px = PX_WOCHE) {
  return blk.h >= 2 * px - 3
}

/** Senkrechte Mitte eines Blocks, bei langen Blöcken nahe am Kopf (Titel). */
export function mittelY(b) {
  return b.y + Math.min(b.h / 2, 20)
}

/** Früher oder später: nach Stufe und Woche des ersten Blocks. */
export function frueher(je, a, b) {
  const x = anker(je, a)
  const y = anker(je, b)
  if (!x || !y) return 0
  return x.y - y.y
}

// ── Linien ───────────────────────────────────────────────────────────────────

/** S-Kurve zwischen zwei Punkten, waagerecht an beiden Enden. */
export function kurve(x1, y1, x2, y2) {
  const xm = (x1 + x2) / 2
  return `M${x1},${y1} C${xm},${y1} ${xm},${y2} ${x2},${y2}`
}

/** Endpunkte einer Linie zwischen einem Block der Mitte und einem einer Spur. */
export function kurvenEnden(mitte, spur) {
  const links = spur.seite === 'links'
  return {
    x1: links ? mitte.x : mitte.x + mitte.b, y1: mittelY(mitte),
    x2: links ? spur.x + spur.b : spur.x, y2: mittelY(spur),
  }
}

/**
 * Klammer in der Rinne (F5): vom früheren Block waagerecht nach links bis zur Tiefe, mit
 * gerundeten Ecken senkrecht zum späteren, dort waagerecht hinein. Endet waagerecht — der
 * Pfeil am Ende steht deshalb immer richtig.
 */
export function klammer(x0, y1, y2, tiefe, radius = 6) {
  const xl = x0 - tiefe
  const r = Math.max(0, Math.min(radius, Math.abs(y2 - y1) / 2, tiefe / 2))
  const d = y2 > y1 ? 1 : -1
  return `M${x0},${y1} H${xl + r} Q${xl},${y1} ${xl},${y1 + d * r} V${y2 - d * r} Q${xl},${y2} ${xl + r},${y2} H${x0 - 2}`
}

/**
 * Tiefe je Klammer, damit sich senkrechte Stücke nicht decken: kurze innen, lange außen
 * (Intervallzuteilung). `klammern`: [{schluessel, y1, y2}]. Rückgabe: Map schluessel → tiefe.
 */
export function rinnenTiefen(klammern, { min = 10, schritt = 7, max = RINNE - 6 } = {}) {
  const sortiert = [...klammern].sort((a, b) => Math.abs(a.y2 - a.y1) - Math.abs(b.y2 - b.y1))
  const ebenen = []   // je Ebene belegte Intervalle
  const aus = new Map()
  for (const k of sortiert) {
    const lo = Math.min(k.y1, k.y2) - 2
    const hi = Math.max(k.y1, k.y2) + 2
    let e = ebenen.findIndex((iv) => iv.every(([a, b]) => hi < a || lo > b))
    if (e < 0) { ebenen.push([]); e = ebenen.length - 1 }
    ebenen[e].push([lo, hi])
    aus.set(k.schluessel, Math.min(max, min + e * schritt))
  }
  return aus
}

/** Linienart eines Bezugs: Breite, Strich, ob rot (verletzte Absprache). */
export function stil(bezug) {
  if (bezug.typ === 'absprache') {
    return { ...STIL.absprache, verletzt: bezug.pruefung?.ergebnis === 'verletzt' }
  }
  if (bezug.eigenes_fach) return { ...STIL.eigen, verletzt: false }
  return { ...(STIL[bezug.typ] ?? STIL.kompetenz), verletzt: false }
}

/**
 * Welche Bezüge zu zeichnen sind. Ohne Auswahl keine Klammern und keine Kurven, außer mit
 * `alle` (nach Schritt 1). Bereich-Bezüge nur mit `bereiche`. Kurven nur zu Fächern mit Spur.
 */
export function sichtbar(bezuege, { gewaehlt = null, alle = false, bereiche = false, kapitelFach, fachId, spurIds }) {
  return (bezuege ?? []).filter((b) => {
    if (b.typ === 'bereich' && !bereiche) return false
    if (gewaehlt ? b.a !== gewaehlt && b.b !== gewaehlt : !alle) return false
    const fa = kapitelFach.get(b.a)
    const fb = kapitelFach.get(b.b)
    if (fa === fb) return fa === fachId
    const ander = fa === fachId ? fb : fa
    return spurIds.has(ander)
  })
}

/** Alle Kapitel, die mit `id` verbunden sind (für das Abblenden), samt `id` selbst. */
export function verbunden(bezuege, id, { bereiche = false } = {}) {
  const aus = new Set([id])
  for (const b of bezuege ?? []) {
    if (b.typ === 'bereich' && !bereiche) continue
    if (b.a === id) aus.add(b.b)
    else if (b.b === id) aus.add(b.a)
  }
  return aus
}

/** Zahlen für die Marken eines Kapitels: ⇄ andere Fächer, ↕ eigenes Fach, ! verletzt. */
export function marken(bezuege, id, kapitelFach, { bereiche = false } = {}) {
  let fremd = 0
  let eigen = 0
  let verletzt = false
  for (const b of bezuege ?? []) {
    if (b.a !== id && b.b !== id) continue
    if (b.typ === 'bereich' && !bereiche) continue
    if (kapitelFach.get(b.a) === kapitelFach.get(b.b)) eigen += 1
    else fremd += 1
    if (b.typ === 'absprache' && b.pruefung?.ergebnis === 'verletzt') verletzt = true
  }
  return { fremd, eigen, verletzt }
}

// ── Leitperspektiven und Leitlinien ──────────────────────────────────────────

/**
 * Marken in den Randspalten (F6: nur Kapitel der Mitte), auf Höhe ihres Kapitels, sich
 * überdeckende nach unten versetzt. Rückgabe: [{kapitel, art, kuerzel, titel, aspekte, x, y}].
 */
export function randmarken(leitlinien, je, sp, { abstand = 15 } = {}) {
  const aus = []
  for (const [art, spalte] of [['ll', sp.leitlinien], ['lp', sp.leitperspektiven]]) {
    if (!spalte) continue
    const eintraege = []
    for (const [kid, liste] of Object.entries(leitlinien ?? {})) {
      const b = anker(je, kid)
      if (!b || b.seite !== 'mitte') continue
      for (const e of liste) if (e.art === art) eintraege.push({ kapitel: kid, ...e, x: spalte.x + 4, y: mittelY(b) })
    }
    eintraege.sort((a, b) => a.y - b.y || a.kuerzel.localeCompare(b.kuerzel))
    let letzt = -Infinity
    for (const e of eintraege) {
      e.y = Math.max(e.y, letzt + abstand)
      letzt = e.y
      aus.push(e)
    }
  }
  return aus
}

// ── Texte und Adresse (Schritt 5) ────────────────────────────────────────────

const GEGEN = { vorher: 'nachher', nachher: 'vorher', gleichzeitig: 'gleichzeitig', abgestimmt: 'abgestimmt' }

/** „2026/27“ → „2027/28“. */
export function naechstesSchuljahr(sj) {
  const start = Number(String(sj ?? '').slice(0, 4))
  if (!start) return null
  return `${start + 1}/${String((start + 2) % 100).padStart(2, '0')}`
}

/** „2016.V3“ → „V3“; ohne Zusatz die Jahreszahl. */
export function fassungKurz(f) {
  if (!f) return ''
  const [, zusatz] = String(f).split('.')
  return zusatz ?? String(f)
}

/** Woher die Lage einer Stufe kommt — für den Stufenkopf. */
export function lageQuelleText(stufe) {
  if (stufe.plan?.status === 'active') return 'Jahresverlaufsplan'
  if (stufe.plan) return 'Jahresverlaufsplan (Entwurf)'
  return 'ohne Jahresverlaufsplan: Lage geschätzt'
}

/** „KW 38–41“ mit Kalender, sonst „Woche 1–4“. */
export function wochenText(stufeInfo, von, bis) {
  const kv = kalenderwoche(stufeInfo, von)
  const kb = kalenderwoche(stufeInfo, bis)
  if (kv != null && kb != null) return kv === kb ? `KW ${kv}` : `KW ${kv}–${kb}`
  return von === bis ? `Woche ${von}` : `Woche ${von}–${bis}`
}

/** „Kl. 8, KW 38–41“ für die ganze Lage eines Kapitels; geschätzt gekennzeichnet. */
export function lageText(kapitel, stufenJe) {
  const teile = (kapitel?.lage ?? []).map((l) => `Kl. ${l.stufe}, ${wochenText(stufenJe[l.stufe], l.von_woche, l.bis_woche)}`)
  if (!teile.length) return 'nicht im Jahresverlaufsplan'
  const geschaetzt = kapitel.lage.some((l) => l.quelle === 'geschaetzt')
  const entwurf = kapitel.lage.some((l) => l.quelle === 'entwurf')
  return `${teile.join(' und ')}${geschaetzt ? ' (geschätzt)' : entwurf ? ' (Plan-Entwurf)' : ''}`
}

/** Die Art einer Absprache aus Sicht des Kapitels `id`: vorher heißt „das andere kommt zuerst“. */
export function artAusSicht(bezug, id) {
  return bezug.a === id ? bezug.art : GEGEN[bezug.art] ?? bezug.art
}

/**
 * Bezüge eines Kapitels für die Tafel, gruppiert. `frueher(a, b)` < 0 heißt a liegt vor b.
 * Rückgabe: absprachen, fremd (Querverweise), baut_auf, aufgegriffen, fach (an ein ganzes Fach).
 */
export function bezuegeDesKapitels(daten, id, { kapitelFach, vergleich, bereiche = false }) {
  const aus = { absprachen: [], fremd: [], baut_auf: [], aufgegriffen: [], fach: [] }
  for (const b of daten?.bezuege ?? []) {
    if (b.a !== id && b.b !== id) continue
    if (b.typ === 'bereich' && !bereiche) continue
    const ander = b.a === id ? b.b : b.a
    if (b.typ === 'absprache') aus.absprachen.push({ ...b, ander, art_hier: artAusSicht(b, id) })
    else if (kapitelFach.get(ander) !== kapitelFach.get(id)) aus.fremd.push({ ...b, ander })
    else (vergleich(ander, id) < 0 ? aus.baut_auf : aus.aufgegriffen).push({ ...b, ander })
  }
  aus.fach = (daten?.fach_absprachen ?? []).filter((f) => f.kapitel === id)
  return aus
}

/** Zustand aus der Adresse: fach, kapitel, schuljahr, weg, entwuerfe. */
export function ausAdresse(params) {
  const weg = params.get('weg')
  return {
    fach: params.get('fach') ?? '',
    kapitel: params.get('kapitel') ?? null,
    schuljahr: params.get('schuljahr') ?? null,
    weg: weg && /^\d+$/.test(weg) ? Number(weg) : null,
    stufe: params.get('stufe') && /^\d+$/.test(params.get('stufe')) ? Number(params.get('stufe')) : null,
    entwuerfe: params.get('entwuerfe') === '1',
  }
}

/** Und zurück — nur, was gesetzt ist. */
export function adresse({ fach, kapitel, schuljahr, weg, stufe, entwuerfe }) {
  const p = new URLSearchParams()
  if (fach) p.set('fach', fach)
  if (kapitel) p.set('kapitel', kapitel)
  if (schuljahr) p.set('schuljahr', schuljahr)
  if (weg != null) p.set('weg', String(weg))
  if (stufe != null) p.set('stufe', String(stufe))
  if (entwuerfe) p.set('entwuerfe', '1')
  return p.toString()
}

/** Einstellung, unter der je Fach die gewählten Spuren gemerkt werden. */
export const SPUREN_SCHLUESSEL = 'vernetzung_spuren'

export function gemerkteSpuren(einstellungen, fachId) {
  const roh = einstellungen?.[SPUREN_SCHLUESSEL]?.[String(fachId)]
  return Array.isArray(roh) ? roh.filter((x) => Number.isInteger(x)) : null
}

/**
 * Einstieg in die Vernetzung (Schritt 6, F7): aus dem Curriculum mit Kapitel, aus dem
 * Jahresverlaufsplan mit Stufe und Schuljahr, aus dem Planer mit Stufe. `aktuelles`: das
 * laufende Schuljahr — dann bleibt `schuljahr` weg.
 */
export function vernetzungPfad({ fach, kapitel = null, stufe = null, schuljahr = null, aktuelles = null, entwuerfe = false }) {
  const sj = schuljahr && schuljahr !== aktuelles ? schuljahr : null
  return `/knowledge/connections?${adresse({ fach: fach != null ? String(fach) : '', kapitel, schuljahr: sj, weg: null, stufe, entwuerfe })}`
}


// ── Liste (F9) — Bildschirm und PDF ─────────────────────────────────────────

/** Vergleich zweier Kapitel nach ihrer ersten Lage (Stufe, Woche); ohne Lage 0. */
export function nachLage(kapitelJe) {
  return (x, y) => {
    const lx = kapitelJe.get(x)?.lage?.[0]
    const ly = kapitelJe.get(y)?.lage?.[0]
    if (!lx || !ly) return 0
    return lx.stufe - ly.stufe || lx.von_woche - ly.von_woche
  }
}

/**
 * Die Vernetzung als Text: je Stufe die Kapitel des Fachs in der Mitte (nach Lage) mit ihren
 * Bezügen in Sätzen, dazu die Kapitel ohne Lage. `bezuege`: die aktiven (Schalter angewandt).
 */
export function liste(daten, bezuege) {
  const faecherJe = Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])])
  const faecherCode = Object.fromEntries(Object.values(faecherJe).map((f) => [f.code, f]))
  const kapitelJe = new Map(daten.kapitel.map((k) => [k.id, k]))
  const kapitelFach = new Map(daten.kapitel.map((k) => [k.id, k.fach_id]))
  const stufenJe = Object.fromEntries(daten.stufen.map((s) => [s.stufe, s]))
  const vergleich = nachLage(kapitelJe)
  const anderes = (id) => {
    const k = kapitelJe.get(id)
    return `${faecherJe[k?.fach_id]?.name ?? ''}: ${k?.titel ?? '?'} (${lageText(k, stufenJe)})`
  }
  const zeilen = (id) => {
    const g = bezuegeDesKapitels({ ...daten, bezuege }, id, { kapitelFach, vergleich, bereiche: true })
    return [
      ...g.absprachen.map((b) => {
        const texte = b.texte.filter(Boolean)
        const p = pruefungText(b.pruefung)
        return `Absprache — ${anderes(b.ander)} ${ART_SATZ[b.art_hier] ?? b.art_hier}${texte.length ? `: ${texte.join(' / ')}` : ''}${p ? ` ${p}` : ''}`
      }),
      ...g.fach.map((f) => `Absprache — ${faecherCode[f.fach_code]?.name ?? f.fach_code}: ${f.kapitel_titel ?? 'ganzes Fach'}${f.text ? `: ${f.text}` : ''}`),
      ...g.fremd.map((b) => `Bildungsplan — ${anderes(b.ander)}${b.typ === 'bereich' ? ', über einen Bereich' : ''} (${b.beispiele.join(', ')})`),
      ...g.baut_auf.map((b) => `Baut auf — ${anderes(b.ander)}`),
      ...g.aufgegriffen.map((b) => `Wird aufgegriffen in — ${anderes(b.ander)}`),
      ...(daten.leitlinien?.[id] ?? []).map((l) => `${l.art === 'll' ? 'Leitlinie' : 'Leitperspektive'} — ${l.titel}${l.aspekte.length ? ` (${l.aspekte.join(', ')})` : ''}`),
    ]
  }
  const eigene = daten.kapitel.filter((k) => k.fach_id === daten.fach.id)
  return {
    stufen: daten.stufen.map((s) => ({
      stufe: s,
      kapitel: eigene.filter((k) => (k.lage[0]?.stufe ?? null) === s.stufe)
        .sort((x, y) => (x.lage[0]?.von_woche ?? 0) - (y.lage[0]?.von_woche ?? 0))
        .map((k) => ({ id: k.id, titel: k.titel, lage: lageText(k, stufenJe), zeilen: zeilen(k.id) })),
    })),
    ohne_lage: eigene.filter((k) => !k.lage.length).map((k) => k.titel),
  }
}
