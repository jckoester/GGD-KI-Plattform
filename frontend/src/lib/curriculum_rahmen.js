// Rahmenangaben eines Curriculums (0.46, E19/E20). Spiegel von
// backend/app/context/curriculum_rahmen.py — Prüfung und Bereinigung macht das Backend.

export const STUNDEN_JE_WOCHENSTUNDE = 30;

export const RAHMEN_TEXTFELDER = [
    { feld: "lehrwerk", label: "Lehrwerk", platzhalter: "z. B. Titel, Verlag, Band" },
    { feld: "beschluesse", label: "Beschlüsse der Fachschaft", platzhalter: "z. B. Lektüren, Pflichtversuche, Exkursionen" },
    { feld: "schwerpunkte", label: "Schwerpunkte", platzhalter: "Wofür die Fachschaft die freie Zeit nutzt" },
    { feld: "absprachen", label: "Absprachen", platzhalter: "z. B. Leistungsnachweise, Methoden- und Medienkonzept" },
];

/** Klassenstufen eines Bands: „7/8" → [7, 8], „8-10" → [8, 9, 10], „9" → [9]. */
export function stufen(jahrgangsstufe) {
    const zahlen = String(jahrgangsstufe ?? "").match(/\d+/g)?.map(Number) ?? [];
    if (!zahlen.length) return [];
    const lo = Math.min(...zahlen);
    const hi = Math.max(...zahlen);
    return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
}

/** Verplanbare Stunden (30 × Wochenstunden über alle Stufen) — null, solange eine Stufe fehlt. */
export function verplanbar(rahmen, jahrgangsstufe) {
    const ws = rahmen?.wochenstunden ?? {};
    const st = stufen(jahrgangsstufe);
    if (!st.length) return null;
    let summe = 0;
    for (const s of st) {
        const z = zahl(ws[String(s)]);
        if (z === null) return null;
        summe += z;
    }
    return summe * STUNDEN_JE_WOCHENSTUNDE;
}

function zahl(wert) {
    if (wert === null || wert === undefined || String(wert).trim() === "") return null;
    const z = Number(String(wert).replace(",", "."));
    return Number.isFinite(z) ? z : null;
}

/** Hat das Curriculum irgendeine Rahmenangabe? */
export function rahmenAngegeben(rahmen) {
    if (!rahmen) return false;
    if (Object.values(rahmen.wochenstunden ?? {}).some((w) => zahl(w) !== null)) return true;
    return RAHMEN_TEXTFELDER.some(({ feld }) => String(rahmen[feld] ?? "").trim());
}

/** „Kl. 7: 2 · Kl. 8: 2" für die Leseansicht; leer ohne Angaben. */
export function wochenstundenText(rahmen, jahrgangsstufe) {
    const ws = rahmen?.wochenstunden ?? {};
    const st = stufen(jahrgangsstufe).map(String);
    const reihe = [...st.filter((s) => s in ws), ...Object.keys(ws).filter((s) => !st.includes(s))];
    return reihe
        .filter((s) => zahl(ws[s]) !== null)
        .map((s) => `Kl. ${s}: ${String(ws[s]).replace(".", ",")}`)
        .join(" · ");
}

/** Rahmen mit geändertem Wert (Kopie); leere Wochenstunden fallen weg. */
export function rahmenMit(rahmen, feld, wert, stufe = null) {
    const neu = { ...(rahmen ?? {}) };
    if (feld === "wochenstunden") {
        const ws = { ...(neu.wochenstunden ?? {}) };
        if (String(wert ?? "").trim() === "") delete ws[String(stufe)];
        else ws[String(stufe)] = wert;
        neu.wochenstunden = ws;
    } else {
        neu[feld] = wert;
    }
    return neu;
}
