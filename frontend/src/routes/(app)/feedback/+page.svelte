<script>
    /**
     * „Meine Meldungen“ — der Rückweg des Feedback-Kanals (ADR-020).
     *
     * Die Schleife wird nicht über Kommunikation geschlossen, sondern über diese
     * Seite: Wer etwas gemeldet hat, sieht hier, was daraus geworden ist. Deshalb
     * schließen sich Anonymität und Rückmeldung nicht aus — der Weg läuft über das
     * Pseudonym, das die Sitzung ohnehin trägt.
     */
    import { onMount } from "svelte";
    import { Loader2 } from "lucide-svelte";
    import { getMyFeedback, withdrawFeedback } from "$lib/api.js";
    import {
        feedbackFehlertext,
        kategorieText,
        statusFarbe,
        statusText,
    } from "$lib/feedback.js";
    import { oeffneFeedback } from "$lib/stores/feedbackDialog.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    let meldungen = $state([]);
    let laedt = $state(true);
    let fehler = $state(null);
    let zieheZurueck = $state(null);

    async function laden() {
        laedt = true;
        try {
            meldungen = await getMyFeedback();
            fehler = null;
        } catch (err) {
            fehler = feedbackFehlertext(err);
        } finally {
            laedt = false;
        }
    }

    onMount(laden);

    async function zurueckziehen(eintrag) {
        zieheZurueck = eintrag.id;
        try {
            await withdrawFeedback(eintrag.id);
            meldungen = meldungen.filter((m) => m.id !== eintrag.id);
            fehler = null;
        } catch (err) {
            // Etwa 409: Die Sichtung hat die Meldung inzwischen angefasst. Dann ist
            // die Liste veraltet — neu laden ist hier die ehrlichere Antwort.
            fehler = feedbackFehlertext(err);
            await laden();
        } finally {
            zieheZurueck = null;
        }
    }

    const datum = (wert) =>
        new Date(wert).toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
</script>

<div class="h-full overflow-y-auto">
    <div class="max-w-3xl mx-auto px-4 py-6">
        {#if fehler}
            <ErrorBanner message={fehler} />
        {/if}

        {#if laedt}
            <div class="flex items-center gap-2 py-12 text-light-tx-2 dark:text-dark-tx-2">
                <Loader2 class="w-4 h-4 animate-spin" /> Lädt…
            </div>
        {:else if meldungen.length === 0}
            <div
                class="rounded-lg border border-dashed p-8 text-center
                       border-light-ui-3 dark:border-dark-ui-3"
            >
                <p class="text-light-tx dark:text-dark-tx">
                    Du hast noch nichts gemeldet.
                </p>
                <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Wenn etwas nicht funktioniert oder dir eine Verbesserung einfällt,
                    sag Bescheid.
                </p>
                <button
                    onclick={() => oeffneFeedback()}
                    class="mt-4 px-3 py-1.5 text-sm rounded-lg
                           bg-primary dark:bg-primary-dark text-white"
                >
                    Feedback geben
                </button>
            </div>
        {:else}
            <ul class="space-y-3">
                {#each meldungen as m (m.id)}
                    <li
                        class="rounded-lg border p-4
                               bg-light-bg dark:bg-dark-bg
                               border-light-ui-3 dark:border-dark-ui-3"
                    >
                        <div class="flex flex-wrap items-center gap-2">
                            <span
                                class="text-xs px-2 py-0.5 rounded-full border
                                       text-light-tx dark:text-dark-tx {statusFarbe(m.status)}"
                            >
                                {statusText(m)}
                            </span>
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                {kategorieText(m.category)} · {datum(m.created_at)}
                                {#if m.has_snapshot}· mit Chat{/if}
                            </span>
                        </div>

                        <p class="mt-2 whitespace-pre-wrap text-sm text-light-tx dark:text-dark-tx">
                            {m.content}
                        </p>

                        {#if m.admin_reply}
                            <div
                                class="mt-3 rounded border-l-2 pl-3 py-1
                                       border-light-bl dark:border-dark-bl"
                            >
                                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    Antwort der Administration
                                </p>
                                <p class="text-sm text-light-tx dark:text-dark-tx">
                                    {m.admin_reply}
                                </p>
                            </div>
                        {/if}

                        {#if m.status === "open"}
                            <div class="mt-3 flex justify-end">
                                <button
                                    onclick={() => zurueckziehen(m)}
                                    disabled={zieheZurueck === m.id}
                                    class="text-sm underline text-light-tx dark:text-dark-tx
                                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                           rounded px-2 py-1 disabled:opacity-50"
                                >
                                    Zurückziehen
                                </button>
                            </div>
                        {/if}
                    </li>
                {/each}
            </ul>
        {/if}
    </div>
</div>
