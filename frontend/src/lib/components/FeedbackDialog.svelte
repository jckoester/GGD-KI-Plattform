<script>
    /**
     * „Feedback geben“ — das Formular für Rückmeldungen (ADR-020).
     *
     * **Was automatisch mitgeht und warum.** Version, Seite, Browserkennung und
     * Fenstergröße legt der Client bei; von Hand liefert diese Angaben niemand
     * zuverlässig, und ohne sie ist eine Fehlerbeschreibung oft nicht
     * nachvollziehbar. Der Chat wandert **nur** auf ausdrücklichen Wunsch mit.
     *
     * **Der Hinweis oben ist Pflichtbestandteil** (ADR-020): Der Freitext ist die
     * einzige Stelle im System, an der jemand ungefiltert über Dritte schreiben
     * kann. Ebenso der Satz am Kontaktfeld — ohne ihn liest sich ein leeres
     * Eingabefeld wie eine Erwartung.
     *
     * Die Regeln liegen in `$lib/feedback.js`, damit sie prüfbar sind.
     */
    import { onMount } from "svelte";
    import { page } from "$app/stores";
    import { Loader2, X } from "lucide-svelte";
    import { createFeedback } from "$lib/api.js";
    import {
        KATEGORIEN,
        MAX_KONTAKT,
        MAX_LAENGE,
        MIN_LAENGE,
        baueNutzlast,
        fehlendeZeichen,
        feedbackFehlertext,
        istAbsendbar,
        sammleKontext,
    } from "$lib/feedback.js";
    import {
        activeConversationAssistantId,
        activeConversationId,
    } from "$lib/stores/pageTitle.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";

    let { vorauswahlChat = false, onclose = () => {} } = $props();

    let kategorie = $state("bug");
    let text = $state("");
    let kontakt = $state("");
    let chatAnhaengen = $state(false);

    // Einmal beim Öffnen vorbelegen — danach gehört die Auswahl der Nutzerin.
    // Bewusst nicht abgeleitet: Ein `$derived` zöge die Vorauswahl später wieder
    // nach und überschriebe ein bewusstes Abwählen. Der Dialog wird bei jedem
    // Öffnen neu erzeugt, ein einmaliges Setzen genügt also.
    onMount(() => {
        chatAnhaengen = vorauswahlChat && $activeConversationId != null;
    });
    let laeuft = $state(false);
    let fehler = $state(null);
    let gesendet = $state(false);

    const fehlend = $derived(fehlendeZeichen(text));
    const absendbar = $derived(istAbsendbar(text) && !laeuft);
    // Nur anbieten, wenn es etwas anzuhängen gibt: Eine Auswahl ohne Wirkung wäre
    // eine Zusage, die das Formular nicht halten kann.
    const chatVorhanden = $derived($activeConversationId != null);

    function schliessen() {
        onclose();
    }

    function beiTaste(ereignis) {
        if (ereignis.key === "Escape") schliessen();
    }

    async function absenden() {
        if (!absendbar) return;
        laeuft = true;
        fehler = null;
        try {
            const kontext = sammleKontext({
                pfad: $page.url.pathname,
                assistentId: $activeConversationAssistantId,
                version: __APP_VERSION__,
                kennung: navigator.userAgent,
                fenster: `${window.innerWidth}x${window.innerHeight}`,
            });
            await createFeedback(
                baueNutzlast({
                    kategorie,
                    text,
                    kontakt,
                    chatId: chatAnhaengen && chatVorhanden ? $activeConversationId : null,
                    kontext,
                }),
            );
            gesendet = true;
        } catch (err) {
            fehler = feedbackFehlertext(err);
        } finally {
            laeuft = false;
        }
    }
</script>

<svelte:window onkeydown={beiTaste} />

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
    <div
        class="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-lg p-6
               bg-light-bg dark:bg-dark-bg
               border border-light-ui-3 dark:border-dark-ui-3"
        role="dialog"
        aria-modal="true"
        aria-label="Feedback geben"
    >
        <div class="flex items-start justify-between gap-4">
            <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                Feedback geben
            </h2>
            <button
                onclick={schliessen}
                aria-label="Schließen"
                class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                       text-light-tx-2 dark:text-dark-tx-2"
            >
                <X class="w-4 h-4" />
            </button>
        </div>

        {#if gesendet}
            <div class="mt-4">
                <SuccessBanner
                    message="Danke! Deine Meldung ist angekommen."
                />
            </div>
            <p class="text-sm text-light-tx dark:text-dark-tx">
                Was daraus geworden ist, siehst du jederzeit unter „Meine Meldungen“.
            </p>
            <div class="mt-5 flex justify-end gap-2">
                <a
                    href="/feedback"
                    onclick={schliessen}
                    class="px-3 py-1.5 text-sm rounded-lg underline
                           text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    Meine Meldungen
                </a>
                <button
                    onclick={schliessen}
                    class="px-3 py-1.5 text-sm rounded-lg bg-primary dark:bg-primary-dark text-white"
                >
                    Schließen
                </button>
            </div>
        {:else}
            <div class="mt-4">
                <InfoBanner
                    message="Bitte keine Namen anderer Personen nennen. Deine Meldung sehen nur die Administrator:innen der Schule."
                />
            </div>

            {#if fehler}
                <ErrorBanner message={fehler} />
            {/if}

            <fieldset class="mt-2">
                <legend class="text-sm font-medium text-light-tx dark:text-dark-tx">
                    Worum geht es?
                </legend>
                <div class="mt-2 flex flex-col gap-1.5 sm:flex-row sm:gap-4">
                    {#each KATEGORIEN as k (k.wert)}
                        <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx">
                            <input
                                type="radio"
                                name="feedback-kategorie"
                                value={k.wert}
                                bind:group={kategorie}
                                class="accent-primary"
                            />
                            {k.label}
                        </label>
                    {/each}
                </div>
            </fieldset>

            <label class="mt-4 block">
                <span class="text-sm font-medium text-light-tx dark:text-dark-tx">
                    Was ist passiert?
                </span>
                <textarea
                    bind:value={text}
                    rows="5"
                    maxlength={MAX_LAENGE}
                    placeholder="Je genauer, desto besser: Was hast du getan, was ist passiert, was hattest du erwartet?"
                    class="mt-1 w-full rounded-lg p-2 text-sm
                           bg-light-bg dark:bg-dark-bg-2
                           text-light-tx dark:text-dark-tx
                           border border-light-ui-3 dark:border-dark-ui-3
                           focus:outline-none focus:ring-2 focus:ring-primary"
                ></textarea>
            </label>
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                {#if fehlend > 0}
                    Noch {fehlend} Zeichen bis zur Mindestlänge von {MIN_LAENGE}.
                {:else}
                    {text.trim().length} von {MAX_LAENGE} Zeichen.
                {/if}
            </p>

            {#if chatVorhanden}
                <label class="mt-4 flex items-start gap-2">
                    <input
                        type="checkbox"
                        bind:checked={chatAnhaengen}
                        class="mt-0.5 accent-primary"
                    />
                    <span class="text-sm text-light-tx dark:text-dark-tx">
                        Aktuellen Chat anhängen
                        <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Der Chat wird zusammen mit der Meldung gespeichert und mit ihr
                            gelöscht.
                        </span>
                    </span>
                </label>
            {/if}

            <label class="mt-4 block">
                <span class="text-sm font-medium text-light-tx dark:text-dark-tx">
                    Wie erreichen wir dich?
                </span>
                <input
                    bind:value={kontakt}
                    maxlength={MAX_KONTAKT}
                    class="mt-1 w-full rounded-lg p-2 text-sm
                           bg-light-bg dark:bg-dark-bg-2
                           text-light-tx dark:text-dark-tx
                           border border-light-ui-3 dark:border-dark-ui-3
                           focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <span class="mt-1 block text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Freiwillig. Für die Bearbeitung deiner Meldung ist das nicht nötig — du
                    kannst uns auch persönlich ansprechen.
                </span>
            </label>

            <div class="mt-5 flex justify-end gap-2">
                <button
                    onclick={schliessen}
                    class="px-3 py-1.5 text-sm rounded-lg
                           text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    Abbrechen
                </button>
                <button
                    onclick={absenden}
                    disabled={!absendbar}
                    class="px-3 py-1.5 text-sm rounded-lg inline-flex items-center gap-2
                           bg-primary dark:bg-primary-dark text-white
                           disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {#if laeuft}<Loader2 class="w-4 h-4 animate-spin" />{/if}
                    Absenden
                </button>
            </div>
        {/if}
    </div>
</div>
