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

/** Die Zeitspalte: „10–25′", ohne Dauer „ab 10′" — nie „10–10′". */
export function zeitspanne(beginn, dauer) {
    return dauer == null ? `ab ${beginn}′` : `${beginn}–${beginn + dauer}′`
}

/** Der Zusatz im Prompt der Material-Erzeugung: „ (15′)" oder nichts — nie „(null′)". */
export function dauerZusatz(dauer) {
    return dauer == null ? "" : ` (${dauer}′)`
}
