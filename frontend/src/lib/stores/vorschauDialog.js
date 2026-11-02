import { writable } from "svelte/store";

/**
 * Der Dialog „Als Schüler:in ansehen" (0.29). Ein Store wie beim Feedback-Dialog: Geöffnet
 * wird er aus dem Nutzermenü und aus dem Assistenten-Editor; das Menü verschwindet beim
 * Klick, ein Dialog darin ginge mit ihm. Gerendert wird er einmal im Layout.
 */
export const vorschauDialog = writable({ offen: false });

/** @param {{ assistentId?: number, jahrgang?: number, gruppeId?: number }} [vorgabe] */
export function oeffneVorschau(vorgabe = {}) {
    vorschauDialog.set({ offen: true, ...vorgabe });
}

export function schliesseVorschau() {
    vorschauDialog.set({ offen: false });
}
