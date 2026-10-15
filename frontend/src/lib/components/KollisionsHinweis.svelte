<script>
    /**
     * Gleichnamiger Fachbegriff in einem anderen Fach (0.16, F7) — beim Speichern im Editor.
     *
     * Das Backend lehnt mit 409 ab, solange der neue Eintrag sich nicht abgrenzt. Hier steht,
     * welche Einträge es schon gibt, und die Wahl: mit Abgrenzung speichern (je Eintrag eine
     * Abgrenzungskante) oder abbrechen und auf den vorhandenen verweisen.
     */
    import { TriangleAlert } from "lucide-svelte";

    let { kollisionen, saving = false, onabgrenzen, onabbrechen } = $props();
</script>

<div
    class="mt-4 px-4 py-3 rounded-md border border-light-ye dark:border-dark-ye
           bg-light-ye-bg dark:bg-dark-ye-bg text-sm text-light-tx dark:text-dark-tx"
    role="alert"
>
    <div class="flex items-start gap-2">
        <TriangleAlert class="w-5 h-5 shrink-0 text-light-ye dark:text-dark-ye" />
        <div class="space-y-2">
            <p>Diesen Begriff führt schon ein anderes Fach:</p>
            <ul class="list-disc list-inside">
                {#each kollisionen as k (k.node_id)}
                    <li>
                        <a
                            href={`/knowledge/${k.node_id}`}
                            target="_blank"
                            rel="noopener"
                            class="text-light-bl dark:text-dark-bl hover:underline">{k.titel}</a
                        >
                        <span class="text-light-tx-2 dark:text-dark-tx-2">
                            ({k.fach ?? "fachlos"}, {k.art})
                        </span>
                    </li>
                {/each}
            </ul>
            <p class="text-light-tx-2 dark:text-dark-tx-2">
                Ein zweiter Eintrag braucht eine klare Abgrenzung. Gibt es keinen fachlichen
                Unterschied, verweise lieber auf den vorhandenen Eintrag. Speicherst du mit
                Abgrenzung, trägst du den Unterschied danach unter „Verknüpfen“ als Hinweis ein.
            </p>
            <div class="flex gap-2">
                <button
                    type="button"
                    onclick={onabgrenzen}
                    disabled={saving}
                    class="px-3 py-1.5 rounded-md bg-primary dark:bg-primary-dark text-white
                           disabled:opacity-50"
                >
                    Mit Abgrenzung speichern
                </button>
                <button
                    type="button"
                    onclick={onabbrechen}
                    class="px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                >
                    Abbrechen
                </button>
            </div>
        </div>
    </div>
</div>
