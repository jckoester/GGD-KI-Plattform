<script>
    /**
     * Absprachen mit anderen Fächern lesen (0.63, Päckchen AY Teil 2, Schritt 4).
     *
     * Eigene (am Kapitel gespeichert) und von außen (andere Fachschaften, die hierher zeigen),
     * je mit Fachmarke in Fachfarbe, Art aus Sicht dieses Kapitels und Link auf das andere
     * Kapitel. „beidseitig“, wenn beide Seiten die Absprache festhalten. Bei einseitigen von außen
     * bietet die Komponente die Gegenabsprache an — als Link (Lesesicht) oder Knopf (Editor).
     *
     * Props:
     * - eigene: Einträge aus `GET …/absprachen` (`kapitel[id].eigene`); im Editor leer lassen
     * - vonAussen: `kapitel[id].von_aussen` oder `fach`
     * - gegenHref(a): Link für „Gegenabsprache anlegen“ (oder null)
     * - ongegen(a): stattdessen ein Knopf (Editor)
     * - titel: Überschrift (wahlweise)
     */
    import { ArrowLeftRight } from "@lucide/svelte";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import { ART_SATZ, fachToenung, kapitelPfad, ortText } from "$lib/absprachen.js";

    let { eigene = [], vonAussen = [], gegenHref = null, ongegen = null, titel = "Absprachen mit anderen Fächern" } = $props();

    // Eine beidseitige Absprache steht nur einmal da — als eigene, mit „beidseitig“ und, wenn
    // drüben anders formuliert, dem Text der anderen Fachschaft.
    const nurVonAussen = $derived(vonAussen.filter((a) => !a.beidseitig));

    const link = "underline text-light-bl dark:text-dark-bl hover:text-primary dark:hover:text-primary-dark";
</script>

{#snippet marke(a)}
    <span class="shrink-0 inline-flex items-center gap-1 rounded border px-1 text-[11px] leading-4
                 text-light-tx-2 dark:text-dark-tx-2 border-light-ui-3 dark:border-dark-ui-3"
          style={fachToenung(a.color)}>
        <SubjectIcon name={a.icon} size={11} color={a.color} />
        {a.fach ?? a.fach_code}
    </span>
{/snippet}

{#snippet beidseitig()}
    <span class="inline-flex items-center gap-0.5 text-[11px] text-light-tx-2 dark:text-dark-tx-2"
          title="Beide Fachschaften haben die Absprache eingetragen">
        <ArrowLeftRight class="w-3 h-3" /> beidseitig
    </span>
{/snippet}

<div class="space-y-1 text-sm">
    {#if titel}<div class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2">{titel}</div>{/if}
    <ul class="space-y-1">
        {#each eigene as a (a.id)}
            <li class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-light-tx dark:text-dark-tx">
                {@render marke(a)}
                {#if kapitelPfad(a.ziel)}
                    <a href={kapitelPfad(a.ziel)} class={link}>{ortText(a.ziel)}</a>
                {:else}
                    <span class="font-medium">{ortText(null, a.kapitel_titel)}</span>
                {/if}
                <span class="text-light-tx-2 dark:text-dark-tx-2">— {ART_SATZ[a.art] ?? a.art}</span>
                {#if a.beidseitig}{@render beidseitig()}{/if}
                {#if a.text}<span class="basis-full text-light-tx-2 dark:text-dark-tx-2">{a.text}</span>{/if}
                {#if a.text_gegenseite}
                    <span class="basis-full text-light-tx-2 dark:text-dark-tx-2">{a.fach}: {a.text_gegenseite}</span>
                {/if}
            </li>
        {/each}
        {#each nurVonAussen as a (a.id)}
            <li class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-light-tx dark:text-dark-tx">
                {@render marke(a)}
                {#if kapitelPfad(a.quelle)}
                    <a href={kapitelPfad(a.quelle)} class={link}>{ortText(a.quelle)}</a>
                {:else}
                    <span class="font-medium">{a.quelle?.curriculum}</span>
                {/if}
                <span class="text-light-tx-2 dark:text-dark-tx-2">— {ART_SATZ[a.art_hier] ?? a.art_hier}</span>
                {#if a.beidseitig}
                    {@render beidseitig()}
                {:else}
                    <span class="text-[11px] text-light-tx-2 dark:text-dark-tx-2">eingetragen von der Fachschaft {a.fach}</span>
                    {#if ongegen}
                        <button type="button" class="text-xs {link}" onclick={() => ongegen(a)}>Gegenabsprache anlegen</button>
                    {:else if gegenHref?.(a)}
                        <a href={gegenHref(a)} class="text-xs {link}">Gegenabsprache anlegen</a>
                    {/if}
                {/if}
                {#if a.text}<span class="basis-full text-light-tx-2 dark:text-dark-tx-2">{a.text}</span>{/if}
            </li>
        {/each}
    </ul>
</div>
