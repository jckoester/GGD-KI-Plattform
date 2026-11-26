/**
 * Raster der Ablaufleiste eines Jahresverlaufsplans (BD, zweiter Durchgang, Jan 25.11.2026) —
 * reine Rechnung, gezeichnet wird in `VerlaufsplanZeitleiste.svelte`.
 *
 * Spalten sind die Unterrichtswochen; zwischen ihnen liegen die Ferien als eigene, schmale
 * Spalte (schraffierte Lücke). Ein Abschnitt, der über Ferien reicht, zerfällt deshalb in
 * Stücke links und rechts der Lücke. Wochen nach Schuljahresende (Überhang) hängen ohne Lücke
 * hinten an. Spaltennummern sind die der CSS-Grid-Spalten (ab 1).
 *
 * Eingabe ist die `lage` vom Server (`wochen`, `ferien`, `halbjahr_ab_woche`,
 * `unterrichtswochen`, `belegt`, `abschnitte`).
 */

/** Ab so vielen Wochen trägt ein Block seinen Titel, darunter nur die Nummer. */
export const TITEL_AB_WOCHEN = 3

const MONATE = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** „2025-09-15“ als Datum um Mitternacht Ortszeit. */
function tag(iso) {
    const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
    return new Date(y, m - 1, d)
}

function plusTage(d, n) {
    const x = new Date(d)
    x.setDate(x.getDate() + n)
    return x
}

/** „Herbst“ aus „Herbstferien“ — Kurzname für die schmale Lücke. */
export function ferienKurz(name) {
    return String(name ?? '').replace(/ferien$/i, '') || String(name ?? '')
}

/**
 * Das Raster: `spalten` (je `{art: 'woche', nr, ueberhang}` oder `{art: 'ferien', name, kurz}`),
 * `spalteVon` (Woche → Spalte) und `stuecke(von, bis)` — die Spaltenbereiche `[von, bis)`
 * eines Wochenbereichs, an den Ferien getrennt.
 */
export function raster(lage) {
    const n = lage?.unterrichtswochen ?? 0
    const anzahl = Math.max(n, lage?.belegt ?? 0, 1)
    const nachWoche = new Map((lage?.ferien ?? []).filter((f) => f.nach_woche < n).map((f) => [f.nach_woche, f]))
    const spalten = []
    const spalteVon = {}
    for (let w = 1; w <= anzahl; w++) {
        spalten.push({ art: 'woche', nr: w, ueberhang: w > n })
        spalteVon[w] = spalten.length
        const f = nachWoche.get(w)
        if (f && w < anzahl) spalten.push({ art: 'ferien', name: f.name, kurz: ferienKurz(f.name), von: f.von, bis: f.bis })
    }

    /** Spaltenbereiche der Wochen `von`–`bis`, an jeder Ferienlücke getrennt. */
    function stuecke(von, bis) {
        const aus = []
        let start = von
        for (let w = von; w <= bis; w++) {
            if (w === bis || nachWoche.has(w)) {
                aus.push({ von: spalteVon[start], bis: spalteVon[w] + 1, wochen: w - start + 1 })
                start = w + 1
            }
        }
        return aus
    }

    return { spalten, spalteVon, stuecke }
}

/** Monatsachse: Spalte und Kurzname, wo ein neuer Monat beginnt (gezählt am Donnerstag der Woche). */
export function monate(lage, spalteVon) {
    const aus = []
    let vorher = null
    for (const w of lage?.wochen ?? []) {
        const m = plusTage(tag(w.montag), 3).getMonth()
        if (m !== vorher) aus.push({ spalte: spalteVon[w.nr], text: MONATE[m] })
        vorher = m
    }
    return aus
}

/**
 * Wo „heute“ liegt: `{ spalte }` der Unterrichtswoche oder der Ferienlücke; `null` vor dem
 * ersten Montag, nach der letzten Unterrichtswoche oder ohne Wochen.
 */
export function heuteSpalte(lage, r, heute = new Date()) {
    const wochen = lage?.wochen ?? []
    if (!wochen.length) return null
    const h = new Date(heute.getFullYear(), heute.getMonth(), heute.getDate())
    for (const w of wochen) {
        const montag = tag(w.montag)
        if (h >= montag && h < plusTage(montag, 7)) return { spalte: r.spalteVon[w.nr] }
    }
    if (h < tag(wochen[0].montag) || h >= plusTage(tag(wochen.at(-1).montag), 7)) return null
    // Zwischen zwei Unterrichtswochen: in den Ferien danach
    const davor = wochen.filter((w) => tag(w.montag) < h).at(-1)
    const luecke = r.spalten[r.spalteVon[davor.nr]]  // Spalte direkt nach der Woche (0-basiert = +1)
    return luecke?.art === 'ferien' ? { spalte: r.spalteVon[davor.nr] + 1 } : { spalte: r.spalteVon[davor.nr] }
}

/**
 * Die Blöcke der Abschnitte: je Abschnitt seine Stücke und welches den Titel trägt (das breiteste;
 * unter `TITEL_AB_WOCHEN` Wochen nur die Nummer).
 */
export function bloecke(lage, r) {
    return (lage?.abschnitte ?? []).map((l, i) => {
        const st = r.stuecke(l.von_woche, l.bis_woche)
        const breitestes = st.reduce((b, s, k) => (s.wochen > st[b].wochen ? k : b), 0)
        return {
            i,
            nr: l.nr ?? i + 1,
            stuecke: st.map((s, k) => ({
                ...s,
                beschriftung: k === breitestes ? (s.wochen >= TITEL_AB_WOCHEN ? 'titel' : 'nummer') : null,
            })),
        }
    })
}

/** Freie Wochen am Ende des Schuljahrs als Stücke (gestrichelt „frei“); leer ohne freie Wochen. */
export function freiStuecke(lage, r) {
    const n = lage?.unterrichtswochen ?? 0
    const belegt = lage?.belegt ?? 0
    if (belegt >= n) return []
    const st = r.stuecke(belegt + 1, n)
    const breitestes = st.reduce((b, s, k) => (s.wochen > st[b].wochen ? k : b), 0)
    return st.map((s, k) => ({ ...s, beschriftet: k === breitestes }))
}
