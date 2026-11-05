<script>
    /**
     * „So kommt er an“ (0.33, Päckchen AK): die Daumen zum eigenen Assistenten, gesamt und
     * getrennt nach Schüler:innen und Lehrkräften. Unter der Mindestzahl kommen keine Zahlen
     * an — das setzt der Server durch; hier steht dann nur „noch weniger als 10“.
     */
    import { getAssistantRatings } from "$lib/api.js";
    import { standText } from "$lib/eigene_bewertung.js";

    let { assistantId } = $props();

    let stand = $state(null);
    let fehler = $state(false);

    $effect(() => {
        const id = assistantId;
        stand = null;
        fehler = false;
        getAssistantRatings(id)
            .then((d) => (stand = d))
            .catch(() => (fehler = true));
    });
</script>

<div class="space-y-2 pt-2 border-t border-light-ui-3 dark:border-dark-ui-3">
    <span class="block text-sm font-medium text-light-tx dark:text-dark-tx">So kommt er an</span>
    {#if fehler}
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">Die Bewertungen ließen sich nicht laden.</p>
    {:else if stand}
        <dl class="text-sm text-light-tx dark:text-dark-tx space-y-1">
            <div>
                <dt class="inline text-light-tx-2 dark:text-dark-tx-2">Schüler:innen:</dt>
                <dd class="inline">{standText(stand.schueler, stand.mindestzahl)}</dd>
            </div>
            <div>
                <dt class="inline text-light-tx-2 dark:text-dark-tx-2">Lehrkräfte:</dt>
                <dd class="inline">{standText(stand.lehrkraefte, stand.mindestzahl)}</dd>
            </div>
        </dl>
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
            Daumen unter den Antworten, seit es den Assistenten gibt — ohne Namen und ohne Chat.
            Die meisten Antworten bewertet niemand; Test- und Vorschau-Chats zählen nicht. Was
            genau nicht stimmt, erfährst du aus Rückmeldungen mit angehängtem Chat.
        </p>
    {/if}
</div>
