/**
 * Was der Browser über Bildschirm und Zeigegerät verrät (0.15.1) — für die Eingabezeile
 * des Chats (`$lib/chat_eingabe.js`).
 */
import { readable } from "svelte/store";

/**
 * Die tatsächlich sichtbare Höhe in CSS-Pixeln, `null` ohne Browser.
 *
 * Gemessen über `visualViewport`: Safari auf iPhone und iPad verkleinert bei offener
 * Bildschirmtastatur nicht das Layout (`100dvh` bleibt die volle Höhe — das
 * `interactive-widget` in `app.html` wertet er nach heutigem Stand nicht aus), sondern nur
 * den sichtbaren Ausschnitt. Ohne `visualViewport` gilt `innerHeight`.
 *
 * Solange jemand den Store liest, steht der Wert zusätzlich als CSS-Variable
 * `--sichtbare-hoehe` am Wurzelelement. Höhendeckel, die sonst `dvh` nähmen, rechnen
 * damit: `max-h-[calc(var(--sichtbare-hoehe,100dvh)*0.35)]` — mit offener Tastatur sind
 * 35 % der vollen Höhe fast der ganze sichtbare Rest.
 */
export const sichtbareHoehe = readable(null, (set) => {
    if (typeof window === "undefined") return;
    const vv = window.visualViewport;
    const quelle = vv ?? window;
    const lies = () => {
        const hoehe = vv ? vv.height : window.innerHeight;
        document.documentElement.style.setProperty("--sichtbare-hoehe", `${Math.round(hoehe)}px`);
        set(hoehe);
    };
    lies();
    quelle.addEventListener("resize", lies);
    return () => {
        quelle.removeEventListener("resize", lies);
        document.documentElement.style.removeProperty("--sichtbare-hoehe");
    };
});

/**
 * Ist das Hauptzeigegerät grob — ein Finger statt Maus oder Trackpad?
 *
 * Folgt Änderungen: Ein iPad, an das ein Trackpad kommt, meldet sich um.
 */
export const grobZeiger = readable(false, (set) => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const abfrage = window.matchMedia("(pointer: coarse)");
    set(abfrage.matches);
    const neu = (e) => set(e.matches);
    abfrage.addEventListener?.("change", neu);
    return () => abfrage.removeEventListener?.("change", neu);
});
