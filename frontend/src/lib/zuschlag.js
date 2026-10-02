/**
 * Zuschläge von Hand — was die Oberfläche dazu rechnet und sagt (0.12, Paket 2, AP1).
 *
 * Die Kennung ist die Brücke über das Pseudonymisierungsprinzip: Der Server kennt keine
 * Namen. Wer einer Lehrkraft etwas aufbuchen will, braucht ihre Mitwirkung — sie liest
 * die Kennung im Profil ab und nennt sie. Den Namen erfährt nur der Mensch.
 */

/** So viele Zeichen des Pseudonyms sind die Kennung (wie `KENNUNG_LAENGE` im Backend). */
export const KENNUNG_LAENGE = 12;

/**
 * Pseudonym → Kennung in Vierergruppen, zum Vorlesen: „a3f9 c2b8 1e04".
 * @param {string|null|undefined} pseudonym
 */
export function kennung(pseudonym) {
    if (!pseudonym || pseudonym.length < KENNUNG_LAENGE) return null;
    return pseudonym.slice(0, KENNUNG_LAENGE).match(/.{1,4}/g).join(" ");
}

/**
 * Die eigene Kennung für das Profil — **nur für Lehrkräfte** (Jan, 02.10.2026).
 *
 * Einzelaufbuchung ist für Lehrkräfte gedacht; Schüler:innen bekommen Zuschläge über
 * ihre Gruppe und brauchen keine Kennung. `teacher` schließt Admins ein (Rollen sind
 * additiv, CLAUDE.md). „Vorerst" — wird das ausgeweitet, ändert sich nur diese Funktion.
 *
 * @param {{ pseudonym?: string, roles?: string[] }|null} user
 */
export function eigeneKennung(user) {
    if (!user?.roles?.includes("teacher")) return null;
    return kennung(user.pseudonym);
}

/**
 * Die Vorschau als Satz — **bevor** gebucht wird.
 *
 * ⚠️ Das ist der Schutz gegen den Tippfehler (5,00 → 500), nicht eine Obergrenze im
 * Code: „29 × 0,50 € = 14,50 €" ist eine andere Entscheidung als „0,50 €". Und er
 * nennt die Lehrkräfte getrennt, weil eine Unterrichtsgruppe sie mit enthält.
 *
 * @param {{anzahl:number, schueler:number, lehrkraefte:number, ohne_rolle:number,
 *          betrag_eur:number, summe_eur:number, einheiten_je_person:number,
 *          gruppenname?:string|null}} v
 */
export function vorschauText(v) {
    if (!v) return null;
    const euro = (x) => x.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
    const teile = [];
    if (v.schueler) teile.push(`${v.schueler} ${v.schueler === 1 ? "Schüler:in" : "Schüler:innen"}`);
    if (v.lehrkraefte) teile.push(`${v.lehrkraefte} ${v.lehrkraefte === 1 ? "Lehrkraft" : "Lehrkräfte"}`);
    if (v.ohne_rolle) teile.push(`${v.ohne_rolle} ohne Rolle in der Gruppe`);
    const wer = teile.length ? teile.join(", ") : `${v.anzahl} Person(en)`;
    const wo = v.gruppenname ? ` in „${v.gruppenname}"` : "";
    return (
        `${wer}${wo}: ${v.anzahl} × ${euro(v.betrag_eur)} = ${euro(v.summe_eur)} ` +
        `(je Person ${v.einheiten_je_person.toLocaleString("de-DE")} Einheiten)`
    );
}

/**
 * Das Ergebnis als Satz. Fehlgeschlagene werden **nicht** gebucht — ein zweiter Versuch
 * ist gefahrlos, und das soll dastehen, damit niemand zögert.
 * @param {{gebucht:number, fehlgeschlagen:string[], unbegrenzt:string[]}} e
 */
export function ergebnisText(e) {
    if (!e) return null;
    const saetze = [`${e.gebucht} gebucht.`];
    if (e.fehlgeschlagen?.length) {
        saetze.push(
            `${e.fehlgeschlagen.length} nicht erreichbar — dort wurde nichts gebucht, ` +
            `ein zweiter Versuch ist gefahrlos.`,
        );
    }
    if (e.unbegrenzt?.length) {
        saetze.push(`${e.unbegrenzt.length} ohne Budgetgrenze — dort ist kein Zuschlag nötig.`);
    }
    return saetze.join(" ");
}

/**
 * Der Anfragekörper aus den Eingaben — eine Stelle, damit Vorschau und Buchung **aus
 * denselben Daten** entstehen.
 *
 * ⚠️ **Gebucht wird nur, was die Vorschau gezeigt hat.** Die Oberfläche merkt sich den
 * Schlüssel (`schluessel()`) der geprüften Anfrage und gibt den Knopf „Jetzt aufbuchen"
 * nur frei, solange er zum aktuellen passt. Wer 0,50 € prüft und danach 500 eintippt,
 * muss neu prüfen — sonst wäre der Probelauf nur eine Geste.
 *
 * @returns {object|null} `null`, wenn die Eingaben noch keine Anfrage ergeben
 */
export function anfrage({ modus, gruppeId, mitglieder, kennungEingabe, betragEur, grund }) {
    const betrag = Number(String(betragEur ?? "").replace(",", "."));
    if (!(betrag > 0) || !grund?.trim()) return null;
    const basis = { betrag_eur: betrag, grund: grund.trim() };
    if (modus === "gruppe") {
        if (!gruppeId) return null;
        return { ...basis, gruppe_id: Number(gruppeId), mitglieder };
    }
    if (!kennungEingabe?.trim()) return null;
    return { ...basis, pseudonym: kennungEingabe.trim() };
}

/** Vergleichbarer Schlüssel einer Anfrage — ohne `probelauf`. */
export function schluessel(a) {
    return a ? JSON.stringify(a) : null;
}

/**
 * Vorgabe für den Mitgliederfilter je Gruppenart. Fachschaften bestehen aus
 * Lehrkräften; bei Klassen und Unterrichtsgruppen sind die Schüler:innen gemeint — die
 * Lehrkraft darin mitzutreffen war die Falle, derentwegen es den Filter gibt.
 */
export function mitgliederVorgabe(typ) {
    return typ === "subject_department" ? "lehrkraefte" : "schueler";
}
