<script>
    // Bestätigungsdialog für das PII-Eingabe-Gate (Phase 14, Datensparsamkeit,
    // Schritt 5). Wird vor dem Senden angezeigt, wenn die lokale Prüfung
    // (Client-Regex + Server-NER) personenbezogene Daten in der Eingabe findet.
    //
    // Charakter: freiwilliger Schutz-Nudge — kein Zwang. Die empfohlene Aktion
    // ist „Bearbeiten"; „Trotzdem senden" bleibt jederzeit möglich. Es wird nichts
    // persistiert; der Scan lief lokal auf dem Schulserver, der Provider hat den
    // Text noch nicht gesehen.
    import { TriangleAlert } from "lucide-svelte";
    import {
        PII_CATEGORY_LABELS,
        segmentText,
        uniqueCategories,
    } from "$lib/pii_gate.js";

    let { text, spans, onedit, onsend } = $props();

    let suppress = $state(false);

    const segments = $derived(segmentText(text, spans));
    const categories = $derived(uniqueCategories(spans));

    const labelFor = (cat) => PII_CATEGORY_LABELS[cat] ?? cat;
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <button
        class="absolute inset-0 bg-black/50"
        onclick={() => onedit?.()}
        aria-label="Schließen und Eingabe bearbeiten"
    ></button>
    <div
        class="relative bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
               rounded-lg shadow-lg w-full max-w-lg p-6"
    >
        <div
            class="flex items-center gap-2 mb-1 text-light-tx dark:text-dark-tx"
        >
            <TriangleAlert class="w-5 h-5 text-light-ye dark:text-dark-ye" />
            <h2 class="text-lg font-semibold">
                Persönliche Daten in deiner Nachricht
            </h2>
        </div>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-3">
            Deine Nachricht enthält offenbar personenbezogene Daten. Sende
            möglichst keine echten Namen, Adressen oder Kontaktdaten an die KI —
            weder von dir noch von anderen. Geprüft wurde lokal auf dem
            Schulserver; gesendet wurde noch nichts.
        </p>

        <!-- Gefundene Kategorien -->
        {#if categories.length > 0}
            <div class="flex flex-wrap gap-1.5 mb-3">
                {#each categories as cat}
                    <span
                        class="px-2 py-0.5 rounded-full text-xs font-medium
                               bg-light-ye-2 dark:bg-dark-ye-2
                               text-dark-tx dark:text-light-tx
                               border border-light-ye dark:border-dark-ye"
                    >
                        {labelFor(cat)}
                    </span>
                {/each}
            </div>
        {/if}

        <!-- Vorschau mit markierten Fundstellen -->
        <div
            class="text-sm text-light-tx dark:text-dark-tx whitespace-pre-wrap
                   max-h-48 overflow-y-auto rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg px-3 py-2 mb-4"
        >
            {#each segments as seg}
                {#if seg.category}
                    <mark
                        class="rounded px-0.5 font-medium
                               bg-light-ye dark:bg-dark-ye
                               text-dark-tx dark:text-light-tx"
                        title={labelFor(seg.category)}>{seg.text}</mark
                    >
                {:else}{seg.text}{/if}
            {/each}
        </div>

        <!-- Nicht-erneut-warnen -->
        <label
            class="flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4 cursor-pointer"
        >
            <input
                type="checkbox"
                bind:checked={suppress}
                class="rounded border-light-ui-3 dark:border-dark-ui-3 text-primary
                       focus:ring-primary"
            />
            In dieser Konversation nicht erneut warnen
        </label>

        <div class="flex justify-end gap-3">
            <button
                type="button"
                onclick={() => onsend?.(suppress)}
                class="px-4 py-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui dark:hover:bg-dark-ui transition-colors"
            >
                Trotzdem senden
            </button>
            <button
                type="button"
                onclick={() => onedit?.()}
                class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                       hover:bg-primary-dark dark:hover:bg-primary transition-colors"
            >
                Bearbeiten
            </button>
        </div>
    </div>
</div>
