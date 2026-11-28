/**
 * Die Zeitachse als SVG für das PDF (Päckchen BE, Teil A, Schritt 7, F14 a) — rein, ohne DOM.
 *
 * Je Stufe eine Seite A4 hoch. Dieselbe Anordnung wie die Ansicht (`zeitachse.js`), mit eigenen
 * Maßen für die feste Seitenbreite. Weil es auf Papier keine Tooltips gibt, tragen schmale Spuren
 * ein Kürzel („PH 3“) statt des Titels; welches Kapitel das ist, steht unter der Zeichnung.
 *
 * ⚠️ Nur Präsentationsattribute, kein CSS und keine Variablen: Das Backend prüft das SVG mit
 * `pruefe_svg` und setzt es mit weasyprint, das CSS in SVG nur teilweise kennt. Farben sind feste
 * Druckfarben, kein Dunkelmodus.
 */
import {
  fassungKurz, lageQuelleText, liste, stufenHinweise,
  achse, anker, bloecke, frueher, kalenderwoche, klammer, kurve, kurvenEnden, marken, mittelY, randmarken,
  rinnenTiefen, sichtbar, spalten, stil, STUFENKOPF,
} from './zeitachse.js'

export const SEITE = {
  breite: 700,
  px: 20,
  kopf: 22,
  masse: { ACHSE: 40, RANDSPALTE: 64, RINNE: 40, MITTE: 200, LUECKE: 10, SPUR_STANDARD: 10000, SCHMAL: 70, MIN_SPUR: 26, MOBIL: 0 },
}

const FARBE = { tx: '#1a1a1a', tx2: '#555555', ui: '#c8d4dc', kopf: '#eef2f6', rot: '#b3261e' }
const SCHRIFT = 'Liberation Sans, Arial, sans-serif'

/** „2026/27 · Bildungsplan V2 · Jahresverlaufsplan“ — die Anmerkungen stehen getrennt (`stufenHinweise`). */
export function stufenZeile(info) {
  return [info.schuljahr, info.fassung && `Bildungsplan ${fassungKurz(info.fassung)}`, lageQuelleText(info)]
    .filter(Boolean).join(' · ')
}

export function xml(t) {
  return String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Text in Zeilen für eine Breite (grob: Zeichenbreite ≈ 0,52 × Schriftgröße), höchstens `max`. */
export function umbrechen(text, breite, groesse, max) {
  const proZeile = Math.max(4, Math.floor(breite / (groesse * 0.52)))
  const woerter = String(text ?? '').split(/\s+/).filter(Boolean)
  const zeilen = []
  let z = ''
  for (const w of woerter) {
    if (!z) z = w
    else if ((z + ' ' + w).length <= proZeile) z += ' ' + w
    else { zeilen.push(z); z = w }
  }
  if (z) zeilen.push(z)
  const aus = zeilen.slice(0, max).map((x) => (x.length > proZeile ? x.slice(0, proZeile - 1) + '…' : x))
  if (zeilen.length > max && aus.length) {
    const letzte = aus[aus.length - 1]
    aus[aus.length - 1] = (letzte.length >= proZeile ? letzte.slice(0, proZeile - 1) : letzte) + '…'
  }
  return aus
}

/** Kürzel der Kapitel in den Spuren: Fachkürzel und laufende Nummer nach Lage. */
export function spurKuerzel(daten) {
  const aus = new Map()
  const zaehler = {}
  const je = Object.fromEntries(daten.faecher.map((f) => [f.id, f]))
  const sortiert = [...daten.kapitel].filter((k) => k.fach_id !== daten.fach.id && k.lage.length)
    .sort((a, b) => a.fach_id - b.fach_id || a.lage[0].stufe - b.lage[0].stufe || a.lage[0].von_woche - b.lage[0].von_woche)
  for (const k of sortiert) {
    zaehler[k.fach_id] = (zaehler[k.fach_id] ?? 0) + 1
    aus.set(k.id, `${je[k.fach_id]?.code ?? '?'} ${zaehler[k.fach_id]}`)
  }
  return aus
}

/**
 * Die Seiten des PDF. `kandidaten`: die Spurfächer in der Reihenfolge der Ansicht; `bezuege`: die
 * aktiven. Linien über eine Stufengrenze fehlen in der Zeichnung (sie stehen in der Liste).
 * Rückgabe: [{stufe, titel, svg, kuerzel: [{kuerzel, titel}]}].
 */
export function seiten(daten, { kandidaten, bezuege, leitlinien = true }) {
  const lay = spalten(SEITE.breite, kandidaten, { leitlinien, masse: SEITE.masse })
  const spurIds = new Set(lay.genutzt.map((f) => f.id))
  const faecherJe = Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])])
  const kapitelFach = new Map(daten.kapitel.map((k) => [k.id, k.fach_id]))
  const kuerzel = spurKuerzel(daten)
  const fachId = daten.fach.id

  return daten.stufen.map((info) => {
    const a = achse([{ stufe: info.stufe, wochen: info.wochen }], { px: SEITE.px })
    const W = SEITE.breite   // Zeichnung immer über die ganze Seitenbreite (Jan 28.11.2026)
    const kapitel = daten.kapitel.map((k) => ({ ...k, lage: k.lage.filter((l) => l.stufe === info.stufe) }))
      .filter((k) => k.lage.length)
    const je = bloecke(kapitel, a, lay.spalten, fachId)
    const hier = new Set(je.keys())
    const bz = bezuege.filter((b) => hier.has(b.a) && hier.has(b.b))
    const teile = []
    const y0 = SEITE.kopf

    // Spaltenköpfe
    const kopf = (text, s, fett = false) => s && teile.push(
      `<text x="${s.x + s.b / 2}" y="14" text-anchor="middle" font-size="9" font-weight="${fett ? 'bold' : 'normal'}" fill="${FARBE.tx2}">${xml(text)}</text>`)
    kopf('Leitlinien', lay.spalten.leitlinien)
    kopf('Leitperspektiven', lay.spalten.leitperspektiven)
    kopf(daten.fach.name, lay.spalten.mitte, true)
    for (const f of lay.genutzt) kopf(lay.schmal ? f.code : f.name, lay.spalten[f.id])

    const g = [`<g transform="translate(0,${y0})">`]
    // Stufenkopf, Wochen, Ferien
    const s = a.stufen[0]
    g.push(`<rect x="0" y="${s.oben}" width="${W}" height="${STUFENKOPF - 6}" fill="${FARBE.kopf}"/>`)
    g.push(`<text x="6" y="${s.oben + 23}" font-size="10" font-weight="bold" fill="${FARBE.tx}">Klasse ${info.stufe}</text>`
      + `<text x="62" y="${s.oben + 23}" font-size="8" fill="${FARBE.tx2}">${xml(stufenZeile(info))}</text>`)
    for (let w = 1; w <= s.wochen; w += 4) {
      const kw = kalenderwoche(info, w)
      g.push(`<text x="${SEITE.masse.ACHSE - 4}" y="${s.start + (w - 1) * a.px + 4}" text-anchor="end" font-size="7" fill="${FARBE.tx2}">${kw != null ? `KW ${kw}` : `Wo. ${w}`}</text>`)
    }
    for (const f of info.ferien ?? []) {
      const y = s.start + f.nach_woche * a.px - 1
      g.push(`<line x1="${SEITE.masse.ACHSE}" y1="${y}" x2="${W}" y2="${y}" stroke="${FARBE.ui}" stroke-width="0.8" stroke-dasharray="3 3"/>`)
      g.push(`<text x="${SEITE.masse.ACHSE + 2}" y="${y - 2}" font-size="6.5" font-style="italic" fill="${FARBE.tx2}">${xml(f.name)}</text>`)
    }

    // Kapitel
    for (const [id, liste] of je) {
      const k = kapitel.find((x) => x.id === id)
      const mitte = k.fach_id === fachId
      const farbe = faecherJe[k.fach_id]?.color ?? FARBE.tx2
      const m = marken(bz, id, kapitelFach, { bereiche: true })
      for (const blk of liste) {
        const geschaetzt = blk.quelle === 'geschaetzt'
        g.push(`<rect x="${blk.x}" y="${blk.y}" width="${blk.b}" height="${Math.max(blk.h, 6)}" rx="3" fill="${farbe}" fill-opacity="0.12" stroke="${farbe}" stroke-width="0.8"${geschaetzt ? ' stroke-dasharray="3 2"' : ''}/>`)
        if (geschaetzt) g.push(`<rect x="${blk.x}" y="${blk.y}" width="${blk.b}" height="${Math.max(blk.h, 6)}" rx="3" fill="url(#schraffur)"/>`)
        g.push(`<rect x="${blk.x}" y="${blk.y}" width="3" height="${Math.max(blk.h, 6)}" fill="${farbe}"/>`)
        const text = mitte || !lay.schmal ? k.titel : kuerzel.get(id) ?? ''
        const groesse = mitte ? 8.5 : 7
        const zeilen = umbrechen(text, blk.b - 8, groesse, Math.max(1, Math.floor((blk.h - 4) / (groesse + 2))))
        zeilen.forEach((z, i) => g.push(
          `<text x="${blk.x + 6}" y="${blk.y + groesse + 2 + i * (groesse + 2)}" font-size="${groesse}" font-weight="${mitte ? 'bold' : 'normal'}" fill="${FARBE.tx}">${xml(z)}</text>`))
        const mk = [m.fremd && `↔${m.fremd}`, mitte && m.eigen && `↕${m.eigen}`, m.verletzt && '!'].filter(Boolean).join(' ')
        if (mk && blk.h > 22 && (mitte || !lay.schmal)) {
          g.push(`<text x="${blk.x + blk.b - 3}" y="${blk.y + blk.h - 3}" text-anchor="end" font-size="7" fill="${m.verletzt ? FARBE.rot : FARBE.tx2}">${xml(mk)}</text>`)
        }
      }
    }

    // Linien: alle sichtbaren dieser Stufe
    const zeichnen = sichtbar(bz, { alle: true, bereiche: true, kapitelFach, fachId, spurIds })
    const eigen = []
    for (const b of zeichnen) {
      const xa = anker(je, b.a)
      const xb = anker(je, b.b)
      if (kapitelFach.get(b.a) === kapitelFach.get(b.b)) {
        const [f, sp] = frueher(je, b.a, b.b) <= 0 ? [xa, xb] : [xb, xa]
        eigen.push({ schluessel: `${b.a}|${b.b}`, y1: mittelY(f), y2: mittelY(sp), b })
      } else {
        const [m, o] = kapitelFach.get(b.a) === fachId ? [xa, xb] : [xb, xa]
        const e = kurvenEnden(m, o)
        const st = stil(b)
        g.push(`<path d="${kurve(e.x1, e.y1, e.x2, e.y2)}" fill="none" stroke="${st.verletzt ? FARBE.rot : st.strich ? FARBE.tx2 : FARBE.tx}" stroke-width="${st.breite * 0.8}"${st.strich ? ` stroke-dasharray="${st.strich}"` : ''}/>`)
      }
    }
    const tiefen = rinnenTiefen(eigen, { max: SEITE.masse.RINNE - 4, min: 6, schritt: 5 })
    for (const k of eigen) {
      g.push(`<path d="${klammer(lay.spalten.mitte.x, k.y1, k.y2, tiefen.get(k.schluessel), 4)}" fill="none" stroke="${daten.fach.color ?? FARBE.tx}" stroke-width="1.4" marker-end="url(#pfeil)"/>`)
    }

    // Leitlinien und Leitperspektiven
    for (const r of randmarken(daten.leitlinien, je, lay.spalten, { abstand: 11 })) {
      const form = r.art === 'll'
        ? `<rect x="${r.x}" y="${r.y - 3}" width="6" height="6" transform="rotate(45 ${r.x + 3} ${r.y})" fill="#ffffff" stroke="${daten.fach.color ?? FARBE.tx}" stroke-width="1.2"/>`
        : `<circle cx="${r.x + 3}" cy="${r.y}" r="3" fill="#ffffff" stroke="${daten.fach.color ?? FARBE.tx}" stroke-width="1.2"/>`
      g.push(form, `<text x="${r.x + 9}" y="${r.y + 2.5}" font-size="7" fill="${FARBE.tx}">${xml(r.kuerzel)}</text>`)
    }
    g.push('</g>')

    const hoehe = y0 + a.hoehe
    const defs = `<defs><pattern id="schraffur" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">`
      + `<line x1="0" y1="0" x2="0" y2="6" stroke="#000000" stroke-opacity="0.12" stroke-width="2"/></pattern>`
      + `<marker id="pfeil" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto">`
      + `<path d="M0,0 L8,4 L0,8 z" fill="${daten.fach.color ?? FARBE.tx}"/></marker></defs>`
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${hoehe}" viewBox="0 0 ${W} ${hoehe}" font-family="${SCHRIFT}">`
      + defs + teile.join('') + g.join('') + '</svg>'
    const spurKapitel = [...je.keys()].filter((id) => kapitelFach.get(id) !== fachId && lay.schmal)
      .map((id) => ({ kuerzel: kuerzel.get(id), titel: kapitel.find((k) => k.id === id)?.titel }))
      .sort((x, y) => x.kuerzel.localeCompare(y.kuerzel, 'de', { numeric: true }))
    // Vernetzte Fächer dieser Stufe ohne Spur — sonst fehlten sie stumm (Jan 28.11.2026)
    const hierIds = new Set(kapitel.map((k) => k.id))
    const ohneSpur = new Set()
    for (const b of bezuege) {
      if (!hierIds.has(b.a) && !hierIds.has(b.b)) continue
      const fa = kapitelFach.get(b.a)
      const fb = kapitelFach.get(b.b)
      if (fa === fb || (fa !== fachId && fb !== fachId)) continue
      const ander = fa === fachId ? fb : fa
      if (!spurIds.has(ander)) ohneSpur.add(ander)
    }
    const nichtGezeichnet = [...ohneSpur].map((id) => faecherJe[id]?.name).filter(Boolean).sort((x, y) => x.localeCompare(y, 'de'))
    return { stufe: info.stufe, svg, kuerzel: spurKapitel, nicht_gezeichnet: nichtGezeichnet }
  })
}

/**
 * Die Anfrage an `POST /context/vernetzung/pdf`: Titel, Zeitraum, je Stufe das SVG mit Kürzeln,
 * dazu die Liste (dieselben Sätze wie „als Liste“).
 */
export function pdfAnfrage(daten, { kandidaten, bezuege, leitlinien = true, zeitraum = '' }) {
  const s = seiten(daten, { kandidaten, bezuege, leitlinien })
  const l = liste(daten, bezuege)
  return {
    fach: daten.fach.name,
    titel: `Vernetzung der Fächer: ${daten.fach.name}`,
    untertitel: zeitraum,
    seiten: s.map((x) => {
      const i = daten.stufen.findIndex((st) => st.stufe === x.stufe)
      const info = daten.stufen[i]
      // Anmerkungen als Liste über der Zeichnung, nicht im Titel (Jan 28.11.2026)
      return { titel: `Klasse ${x.stufe} · ${stufenZeile(info)}`, svg: x.svg, kuerzel: x.kuerzel,
        nicht_gezeichnet: x.nicht_gezeichnet,
        hinweise: stufenHinweise(info, daten.stufen[i - 1], daten.fach.name) }
    }),
    liste: l.stufen.map(({ stufe, kapitel }) => ({
      titel: `Klasse ${stufe.stufe} · ${stufe.schuljahr}`,
      kapitel: kapitel.map((k) => ({ titel: k.titel, lage: k.lage, zeilen: k.zeilen })),
    })),
    ohne_lage: l.ohne_lage,
  }
}
