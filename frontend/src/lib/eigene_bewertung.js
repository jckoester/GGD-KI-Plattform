// Bewertungen eigener Assistenten (0.33, Päckchen AK): wie die Zahlen gelesen werden.
//
// Die Mindestzahl setzt der Server durch (`app/feedback/bewertung.py`, `MINDEST_EIGENE`):
// Unter ihr kommen weder Zahlen noch Anteil an — hier wird nur noch beschriftet.

/** Fallback, falls die Antwort die Schwelle nicht nennt (Liste „Meine Assistenten“). */
export const MINDESTZAHL = 10;

/**
 * Ein Rollenstand als Satz: „8 hilfreich, 3 nicht hilfreich — 73 % hilfreich“ oder
 * „noch weniger als 10 Bewertungen“.
 */
export function standText(stand, mindestzahl = MINDESTZAHL) {
    if (!stand || stand.zu_wenige) return `noch weniger als ${mindestzahl} Bewertungen`;
    return `${stand.plus} hilfreich, ${stand.minus} nicht hilfreich — ${stand.anteil} % hilfreich`;
}

/**
 * Was die Spalte in „Meine Assistenten“ zeigt: der Anteil der Schüler:innen, sonst der der
 * Lehrkräfte (Assistenten für Lehrkräfte), sonst ein Strich.
 *
 * @returns {{ text: string, titel: string }}
 */
export function anteilKurz(bewertung, mindestzahl = MINDESTZAHL) {
    const s = bewertung?.schueler;
    const l = bewertung?.lehrkraefte;
    if (s && !s.zu_wenige) return { text: `${s.anteil} %`, titel: `Schüler:innen: ${standText(s)}` };
    if (l && !l.zu_wenige) return { text: `${l.anteil} %`, titel: `Lehrkräfte: ${standText(l)}` };
    return { text: "—", titel: `Noch weniger als ${mindestzahl} Bewertungen` };
}
