/**
 * Stabile Schlüssel für die Blasen im Chat (0.49, H3).
 *
 * `MessageBubble` hält eigenen Zustand (Herkunft und Kontext aufgeklappt, Zitat kopiert,
 * Bildstatus …). Ohne Schlüssel verwendet Svelte die Blasen **je Position** weiter: Beim
 * Wechsel in einen anderen Chat blieb so etwa „Kontext“ an der dritten Blase offen, und ein
 * Trenner, der beim Assistentenwechsel mitten in die Liste kommt, verschob den Zustand der
 * Antwort, die gerade entsteht, auf die Blase davor.
 *
 * Der Schlüssel entsteht **einmal**, wenn die Nachricht angelegt oder geladen wird, und wandert
 * mit jedem `{ ...m }` mit. Die Kennung vom Server taugt allein nicht: Eine neue Antwort bekommt
 * sie erst am Ende des Streams — ein Schlüsselwechsel dann baute die Blase neu auf.
 */

let zaehler = 0;

/** Nachricht mit Schlüssel: `m<id>` für gespeicherte, `n<laufend>` für im Browser angelegte. */
export function mitSchluessel(nachricht) {
    if (nachricht?.schluessel) return nachricht;
    const schluessel = nachricht?.id != null ? `m${nachricht.id}` : `n${++zaehler}`;
    return { ...nachricht, schluessel };
}

/**
 * Schlüssel für `{#each}`. Fehlt er (eine Stelle, die `mitSchluessel` vergessen hat), gilt die
 * Position — in eigenem Namensraum, damit er nie mit einem echten Schlüssel zusammenfällt:
 * Ein doppelter Schlüssel ist in Svelte ein Laufzeitfehler.
 */
export function blasenSchluessel(nachricht, index) {
    return nachricht?.schluessel ?? `i${index}`;
}
