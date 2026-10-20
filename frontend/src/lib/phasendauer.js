/**
 * Phasen ohne Dauer (0.13, P1).
 *
 * Eine Phase darf im Stundenentwurf noch keine Minuten haben — eine Skizze aus dem Vault
 * („Einstieg: Video Zahnräder") wächst später in dieselben Felder hinein. `null` heißt
 * „noch nicht festgelegt"; `0` gibt es nicht, nur eine Phase ohne Angabe.
 *
 * ⚠️ `null` und Fehlen sind dasselbe — `dauer ?? …` statt eines Vorgabewerts im Zugriff.
 */

/** Was das Dauerfeld speichert: leer → `null`, sonst eine ganze Zahl von 1 bis 480. */
export function dauerAusEingabe(text) {
    const roh = String(text ?? "").trim()
    if (roh === "") return null
    const zahl = parseInt(roh, 10)
    if (Number.isNaN(zahl)) return null
    return Math.min(480, Math.max(1, zahl))
}

/**
 * Gestrichene Phasen (0.19, Jan 18.10.2026): Sie bleiben sichtbar, zählen aber nicht zur
 * Zeit — keine Zeitangabe, und die Uhr läuft ohne sie weiter. „Offen" zählt mit.
 *
 * `statusVon(phase)` liefert den Status, der gelten soll — gespeichert (`phase.status`)
 * oder, während der Nachbereitung, der gerade gewählte. Dieselbe Regel wie `zeitspalte`
 * und `zeitbudget` im Export (`backend/app/planning/lesson_export.py`).
 */
export const gespeicherterStatus = (phase) => phase?.status

export function istGestrichen(phase, statusVon = gespeicherterStatus) {
    return statusVon(phase) === "gestrichen"
}

/** Summe der gesetzten Dauern ohne gestrichene Phasen. */
export function geplanteMinuten(phasen, statusVon = gespeicherterStatus) {
    return (phasen ?? []).reduce(
        (summe, p) => summe + (istGestrichen(p, statusVon) ? 0 : p?.dauer_min || 0),
        0,
    )
}

/**
 * Der Beginn jeder Phase in Minuten — oder `null`, wo er sich nicht wissen lässt.
 *
 * ⚠️ **Nach einer Phase ohne Dauer steht die Uhr.** Ihr eigener Beginn ist bekannt, ihr
 * Ende nicht — und damit auch nicht der Beginn jeder folgenden Phase. Eine fehlende Dauer
 * als 0 weiterzuzählen hieße, `10–20′` anzuzeigen, wo niemand weiß, wann die Phase
 * beginnt (Jan, 03.10.2026, im Browser bemerkt).
 *
 * Eine gestrichene Phase bekommt `null` (Zeitspalte „–") und rückt die Uhr nicht vor.
 */
export function startzeiten(phasen, statusVon = gespeicherterStatus) {
    const starts = []
    let uhr = 0
    for (const phase of phasen ?? []) {
        if (istGestrichen(phase, statusVon)) {
            starts.push(null)
            continue
        }
        starts.push(uhr)
        uhr = uhr == null || phase?.dauer_min == null ? null : uhr + phase.dauer_min
    }
    return starts
}

/** Die Zeitspalte: „10–25′", ohne Dauer „ab 10′", mit unbekanntem Beginn „–". */
export function zeitspanne(beginn, dauer) {
    if (beginn == null) return "–"
    return dauer == null ? `ab ${beginn}′` : `${beginn}–${beginn + dauer}′`
}

/** Der Zusatz im Prompt der Material-Erzeugung: „ (15′)" oder nichts — nie „(null′)". */
export function dauerZusatz(dauer) {
    return dauer == null ? "" : ` (${dauer}′)`
}
