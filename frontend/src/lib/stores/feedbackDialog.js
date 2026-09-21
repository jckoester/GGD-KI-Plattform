import { writable } from "svelte/store";

/**
 * Ob das Rückmelde-Formular offen ist — und ob der Chat vorausgewählt sein soll.
 *
 * **Warum ein Store und nicht ein `let` im Menü.** Geöffnet wird der Dialog aus dem
 * Nutzermenü und aus dem Chat-Kopf; beides sind Elemente, die beim Klick verschwinden.
 * Ein Dialog, der dort hinge, ginge mit ihnen. Er wird deshalb einmal im Layout
 * gerendert und von hier aus geschaltet.
 */
export const feedbackDialog = writable({ offen: false, chatAnhaengen: false });

export function oeffneFeedback({ chatAnhaengen = false } = {}) {
    feedbackDialog.set({ offen: true, chatAnhaengen });
}

export function schliesseFeedback() {
    feedbackDialog.set({ offen: false, chatAnhaengen: false });
}
