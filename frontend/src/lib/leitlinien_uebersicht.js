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

/** Alle Fundstellen der Übersicht, über Aspekte und „als Ganzes“. */
function alleFundstellen(u) {
    return [...(u?.aspekte ?? []).flatMap((a) => a.fundstellen), ...(u?.ganz ?? [])];
}

/**
 * Klassenstufen für den Filter (F6): jede Stufe, die eine Fundstelle abdeckt — ein Curriculum
 * für 7–8 bringt 7 und 8 mit. Aufsteigend; leer, wenn keine Fundstelle Stufen nennt.
 */
export function stufenAuswahl(u) {
    const stufen = new Set();
    for (const f of alleFundstellen(u)) {
        const von = f.min_grade ?? f.max_grade;
        const bis = f.max_grade ?? f.min_grade;
        if (von == null) continue;
        for (let s = von; s <= bis; s++) stufen.add(s);
    }
    return [...stufen].sort((a, b) => a - b);
}

/** Deckt die Fundstelle die Stufe ab? Ohne Angabe von Stufen: nein. */
export function deckt(f, stufe) {
    const von = f.min_grade ?? f.max_grade;
    const bis = f.max_grade ?? f.min_grade;
    return von != null && von <= stufe && stufe <= bis;
}

/**
 * Die Übersicht, eingegrenzt auf eine Klassenstufe (F6); ohne Stufe unverändert. Fächer mit
 * Eintragungen und Aspekte ohne Fundstelle gelten danach für diese Stufe.
 */
export function aufStufe(u, stufe) {
    if (!u || stufe == null) return u;
    const nur = (liste) => liste.filter((f) => deckt(f, stufe));
    const aspekte = u.aspekte.map((a) => ({ ...a, fundstellen: nur(a.fundstellen) }));
    const ganz = nur(u.ganz);
    const mitEintrag = new Set([...aspekte.flatMap((a) => a.fundstellen), ...ganz].map((f) => f.fach_id));
    return {
        ...u,
        aspekte,
        ganz,
        faecher: u.alle_faecher.filter((f) => mitEintrag.has(f.id)),
        ohne_fundstelle: aspekte.filter((a) => a.fundstellen.length === 0).map((a) => a.kuerzel),
    };
}
