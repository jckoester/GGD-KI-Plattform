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

export const PX_WOCHE = 13
export const STUFENKOPF = 34
export const STUFENABSTAND = 10
export const OBEN = 8

export const MITTE = 220
export const RINNE = 64
export const ACHSE = 58
export const RANDSPALTE = 112
export const LUECKE = 18
export const SPUR_STANDARD = 150
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

/** Je Stufe ihr Platz: `oben` (Kopf), `start` (erste Woche), `hoehe`. Dazu die Gesamthöhe. */
export function achse(stufen, { px = PX_WOCHE } = {}) {
  let y = OBEN
  const je = {}
  const liste = (stufen ?? []).map((s) => {
    const eintrag = { stufe: s.stufe, oben: y, start: y + STUFENKOPF, wochen: s.wochen, hoehe: STUFENKOPF + s.wochen * px }
    je[s.stufe] = eintrag
    y += eintrag.hoehe + STUFENABSTAND
    return eintrag
  })
  return { stufen: liste, je, hoehe: y, px }
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
export function spalten(breite, spurFaecher, { leitlinien = true } = {}) {
  const mobil = breite < MOBIL
  const rand = leitlinien && !mobil ? RANDSPALTE : 0
  const fest = ACHSE + 2 * rand + RINNE + MITTE + (rand ? 2 * LUECKE : 0)
  const frei = Math.max(0, breite - fest)
  const passen = mobil ? 0 : Math.floor(frei / (MIN_SPUR + LUECKE))
  const n = Math.min(spurFaecher.length, passen)
  const genutzt = spurFaecher.slice(0, n)
  const spurBreite = n ? Math.min(SPUR_STANDARD, Math.floor(frei / n) - LUECKE) : 0
  const { rechts, links } = seiten(genutzt)

  const sp = {}
  let x = ACHSE
  if (rand) { sp.leitlinien = { x, b: rand }; x += rand + LUECKE }
  for (const f of [...links].reverse()) { sp[f.id] = { x, b: spurBreite, seite: 'links' }; x += spurBreite + LUECKE }
  sp.rinne = { x, b: RINNE }
  x += RINNE
  sp.mitte = { x, b: MITTE, seite: 'mitte' }
  x += MITTE + LUECKE
  for (const f of rechts) { sp[f.id] = { x, b: spurBreite, seite: 'rechts' }; x += spurBreite + LUECKE }
  if (rand) { sp.leitperspektiven = { x, b: rand }; x += rand }
  return { spalten: sp, spurBreite, schmal: n > 0 && spurBreite < SCHMAL, mobil, passen, genutzt, breite: x }
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
