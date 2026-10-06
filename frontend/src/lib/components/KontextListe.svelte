<script>
    // Die aufgeklappte Zeile „Kontext (n)" unter einer Antwort (0.14). Was je Stufe
    // dasteht, entscheidet `kontextEintraege` in `$lib/kontext_anzeige.js`. Titel mit
    // Formeln wie in `ContextNodeLabel` — `renderInlineMath` maskiert den Rest.
    import { renderInlineMath } from "$lib/markdown.js";

    let { eintraege } = $props();
</script>

<ul class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2 space-y-0.5">
    {#each eintraege as e (e.node_id)}
        <li>
            <a href={e.href} class="text-light-bl dark:text-dark-bl hover:underline">{@html renderInlineMath(e.titel)}</a>
            {#if e.fach}<span> · {e.fach}</span>{/if}
            {#if e.details.length}
                <span class="block pl-3">{e.details.join(' · ')}</span>
            {/if}
        </li>
    {/each}
</ul>
