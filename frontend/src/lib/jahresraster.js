// Welche Halbjahre eine Übernahme aus dem Stundenplan anlegt (AP2, 22.09.2026).
//
// **Das Problem, das das löst.** Zu Schuljahresbeginn planen Lehrkräfte das *Jahr*, der
// Stundenplan reicht aber nur bis zum Halbjahreswechsel. Ohne Termine im zweiten
// Halbjahr gibt es dort nichts zu planen. Erzeugt wird es deshalb **vorläufig** aus dem
// Raster des ersten — als Annahme gekennzeichnet, nicht als Auskunft.
//
// Die Regeln stehen hier und nicht in den Bauteilen: Das Projekt hat keine
// Svelte-Komponententests (siehe `picker_tastatur.test.js`), und zwei Bauteile
// (Sammelübernahme und Mustereditor) brauchen dieselbe Antwort.

/**
 * Kann von hier aus überhaupt der Rest des Jahres angelegt werden?
 *
 * Nur im ersten Halbjahr. Im zweiten gibt es kein „Restjahr" mehr — die Option dort
 * anzubieten wäre eine Schaltfläche ohne Wirkung.
 */
export function restjahrMoeglich(aktuellesHalbjahr) {
    return aktuellesHalbjahr === 1;
}

/**
 * Die Halbjahre, für die Stunden erzeugt werden — mit der Angabe, ob sie vorläufig sind.
 *
 * @returns {{halbjahr: number, vorlaeufig: boolean}[]} in Reihenfolge
 */
export function halbjahreFuerUebernahme(aktuellesHalbjahr, bisSchuljahresende = false) {
    const jetzt = { halbjahr: aktuellesHalbjahr, vorlaeufig: false };
    if (!bisSchuljahresende || !restjahrMoeglich(aktuellesHalbjahr)) return [jetzt];
    return [jetzt, { halbjahr: 2, vorlaeufig: true }];
}

/**
 * Für welches Halbjahr das Wochenmuster geschrieben wird — **nur für das laufende.**
 *
 * Für das zweite wird bewusst **keins** hinterlegt: Es *gibt* kein Muster für das
 * zweite Halbjahr, und ein kopiertes sähe wie eine Zusage aus. Der Slot-Generator fällt
 * von sich aus auf das Muster des ersten zurück und meldet das (`used_hj1_fallback`).
 */
export function halbjahrFuerMuster(aktuellesHalbjahr) {
    return aktuellesHalbjahr;
}

/** Ein Satz je erzeugtem Halbjahr. */
export function slotMeldung(stats) {
    const anzahl = stats?.created ?? 0;
    const was = anzahl === 1 ? "Stunde" : "Stunden";
    const hj = stats?.halbjahr;
    if (stats?.vorlaeufig) {
        return `${anzahl} ${was} im ${hj}. Halbjahr — vorläufig, aus dem jetzigen Raster.`;
    }
    return `${anzahl} ${was} im ${hj}. Halbjahr angelegt.`;
}

/**
 * Der Hinweis zu 14-tägigen Terminen über den Halbjahreswechsel hinweg — oder `null`.
 *
 * Als eigener Satz, nicht als Anhängsel: Die A-/B-Phase ist die einzige Angabe, die
 * dabei um eine ganze Woche danebenliegen kann. `ab_phasen` zählt ab der ersten
 * Unterrichtswoche des Schuljahres durch; zählt die Schule zum Halbjahr neu, stimmt die
 * Zuordnung nicht mehr. Die Unsicherheit ist vorübergehend — der echte Stundenplan
 * ersetzt das Raster.
 */
export function vierzehntaegigWarnung(stats) {
    if (!stats?.fallback_vierzehntaegig) return null;
    return (
        "Die Wochenmuster stammen aus dem 1. Halbjahr. 14-tägige Termine können dadurch " +
        "um eine Woche verschoben sein — sobald der Stundenplan für das 2. Halbjahr " +
        "steht, bitte einmal neu aus dem Stundenplan übernehmen."
    );
}
