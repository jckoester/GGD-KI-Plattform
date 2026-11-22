/**
 * Raster der Leitlinien-Übersicht (0.53, Päckchen AU): Fächer als Zeilen, Aspekte als Spalten.
 *
 * Die Daten kommen aus `GET /context/leitlinien/{id}/uebersicht`. Hier nur die Umformung für
 * die Seite, damit sie ohne Oberfläche prüfbar ist.
 */

/** Schlüssel der Spalte „Leitlinie als Ganzes“ (Verweise ohne Aspekt). */
export const GANZ = "__ganz";

/**
 * Spalten: je Aspekt eine, davor „als Ganzes“, wenn es solche Verweise gibt.
 * `[{ schluessel, kuerzel, titel, fundstellen, leer }]`
 */
export function spalten(u) {
    const aus = (u?.aspekte ?? []).map((a) => ({
        schluessel: a.node_id,
        kuerzel: a.kuerzel,
        titel: a.titel,
        fundstellen: a.fundstellen,
        leer: a.fundstellen.length === 0,
    }));
    if (u?.ganz?.length) {
        aus.unshift({ schluessel: GANZ, kuerzel: "Ganz", titel: `${u.leitlinie.titel} als Ganzes`,
                      fundstellen: u.ganz, leer: false });
    }
    return aus;
}

/**
 * Zeilen des Rasters: `[{ id, name, zellen: [n …], summe }]` in der Reihenfolge der Spalten.
 * `alle` — alle Fächer der Schule (F7), sonst nur die mit mindestens einer Fundstelle.
 */
export function zeilen(u, alle = false) {
    const sp = spalten(u);
    const faecher = (alle ? u?.alle_faecher : u?.faecher) ?? [];
    return faecher.map((f) => {
        const zellen = sp.map((s) => s.fundstellen.filter((x) => x.fach_id === f.id).length);
        return { id: f.id, name: f.name, zellen, summe: zellen.reduce((a, b) => a + b, 0) };
    });
}

/** Höchster Zellwert — Bezug der Farbstufen. */
export function hoechstwert(reihen) {
    return Math.max(0, ...reihen.flatMap((r) => r.zellen));
}

/** „Mathematik, SDG13: 2 Fundstellen“ — für Bildschirmleser und Tooltip. */
export function zellenText(fach, kuerzel, n) {
    return `${fach}, ${kuerzel}: ${n === 0 ? "keine" : n} Fundstelle${n === 1 ? "" : "n"}`;
}

/** Wohin eine Fundstelle führt: das Curriculum, an das Kapitel gesprungen. */
export function fundstelleHref(f, zurueck) {
    const back = zurueck ? `?back=${encodeURIComponent(zurueck)}` : "";
    return `/knowledge/curriculum/${f.curriculum_id}${back}#kapitel-${f.kapitel_id}`;
}
