/**
 * Anzeige des Audit-Logs (0.28, `/settings/audit`).
 *
 * Die Nutzdaten sind kleine flache Objekte (`{ grund: "anmeldedaten" }`, `{ teams: [...] }`);
 * sie stehen als eine Zeile „Schlüssel: Wert · …“ in der Tabelle. Gebilde darin werden knapp
 * als „Schlüssel Wert, …“ gezeigt, tiefere als JSON — sie sind selten und sollen die Zeile
 * nicht sprengen.
 */

function wert(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "ja" : "nein";
    if (Array.isArray(v)) return v.every((x) => typeof x !== "object" || x === null)
        ? v.join(", ") || "—"
        : JSON.stringify(v);
    if (typeof v === "object") {
        // Verschachtelt nur eine Ebene tief, etwa `geloescht: { auth: 0, … }`.
        const teile = Object.entries(v);
        return teile.every(([, x]) => typeof x !== "object" || x === null)
            ? teile.map(([k, x]) => `${k} ${wert(x)}`).join(", ") || "—"
            : JSON.stringify(v);
    }
    return String(v);
}

/** `{ von: "open", nach: "done" }` → `"von: open · nach: done"`; leer → `""`. */
export function datenText(payload) {
    return Object.entries(payload ?? {})
        .map(([k, v]) => `${k}: ${wert(v)}`)
        .join(" · ");
}

/** `("assistant", "12")` → `"assistant 12"`; ohne Ziel `""`. */
export function zielText(typ, id) {
    if (!typ) return "";
    return id ? `${typ} ${id}` : typ;
}
