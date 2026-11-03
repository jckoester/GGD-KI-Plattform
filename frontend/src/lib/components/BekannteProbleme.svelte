<script>
    /**
     * Bekannte Probleme (0.31, Päckchen T, ADR-020) — was die Sichtung öffentlich gemacht hat.
     *
     * Zu sehen ist nur der Titel, den die Administration formuliert hat, nie der Text einer
     * Meldung. Welche Einträge erscheinen, entscheidet der Server nach der Rolle.
     *
     * `kompakt` im Feedback-Dialog: dort entsteht eine Doppelmeldung, dort hilft die Liste am
     * meisten. Bleibt sie leer oder scheitert das Laden, zeigt der Dialog nichts davon — das
     * Melden darf daran nicht hängen.
     */
    import { onMount } from "svelte";
    import { getKnownProblems } from "$lib/api.js";
    import { bekanntStatusText, statusFarbe } from "$lib/feedback.js";

    let { kompakt = false } = $props();

    let eintraege = $state([]);
    let geladen = $state(false);
    let fehlgeschlagen = $state(false);

    onMount(async () => {
        try {
            eintraege = await getKnownProblems();
        } catch {
            fehlgeschlagen = true;
        } finally {
            geladen = true;
        }
    });

    const datum = (wert) =>
        new Date(wert).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
</script>

{#if kompakt}
    {#if eintraege.length > 0}
        <details
            open
            class="mt-3 rounded-lg border p-3 border-light-ui-3 dark:border-dark-ui-3"
        >
            <summary class="cursor-pointer text-sm font-medium text-light-tx dark:text-dark-tx">
                Schon bekannt ({eintraege.length})
            </summary>
            <ul class="mt-2 max-h-40 overflow-y-auto space-y-1">
                {#each eintraege as e (e.id)}
                    <li class="text-sm text-light-tx dark:text-dark-tx">
                        {e.title}
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            · {bekanntStatusText(e)}
                        </span>
                    </li>
                {/each}
            </ul>
            <p class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">
                Steht dein Anliegen schon hier, musst du es nicht noch einmal melden.
            </p>
        </details>
    {/if}
{:else if geladen}
    {#if fehlgeschlagen}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Die bekannten Probleme konnten nicht geladen werden.
        </p>
    {:else if eintraege.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Derzeit sind keine Probleme bekannt.
        </p>
    {:else}
        <ul class="space-y-2">
            {#each eintraege as e (e.id)}
                <li
                    class="flex flex-wrap items-center gap-2 rounded-lg border p-3
                           bg-light-bg dark:bg-dark-bg border-light-ui-3 dark:border-dark-ui-3"
                >
                    <span
                        class="text-xs px-2 py-0.5 rounded-full border
                               text-light-tx dark:text-dark-tx {statusFarbe(e.status)}"
                    >
                        {bekanntStatusText(e)}
                    </span>
                    <span class="text-sm text-light-tx dark:text-dark-tx">{e.title}</span>
                    <span class="ml-auto text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {e.status === "done" ? "behoben am" : "seit"} {datum(e.seit)}
                    </span>
                </li>
            {/each}
        </ul>
    {/if}
{/if}
