<script>
    /**
     * Tafel der Vernetzung (BE, Teil A, Schritt 5): die Bezüge des gewählten Kapitels als Liste —
     * zugleich die Form ohne Maus und für den Screenreader (F9). Darunter bleibt die Legende der
     * Marken stehen (Befund 7).
     *
     * Props: daten, gewaehlt, bezuege (aktive), kapitelFach, vergleich(a, b), onwaehle(id),
     * onmitte(fachId)
     */
    import { ArrowDownUp, ArrowLeftRight, TriangleAlert } from '@lucide/svelte'
    import SubjectIcon from '$lib/components/SubjectIcon.svelte'
    import { ART_SATZ, fachToenung, pruefungText } from '$lib/absprachen.js'
    import { bezuegeDesKapitels, lageText } from '$lib/zeitachse.js'

    let { daten, gewaehlt = null, bezuege, kapitelFach, vergleich, onwaehle = () => {}, onmitte = () => {} } = $props()

    const faecherJe = $derived(Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])]))
    const faecherCode = $derived(Object.fromEntries(Object.values(faecherJe).map((f) => [f.code, f])))
    const kapitelJe = $derived(new Map(daten.kapitel.map((k) => [k.id, k])))
    const stufenJe = $derived(Object.fromEntries(daten.stufen.map((s) => [s.stufe, s])))
    const k = $derived(gewaehlt ? kapitelJe.get(gewaehlt) : null)
    const gruppen = $derived(k ? bezuegeDesKapitels({ ...daten, bezuege }, gewaehlt, { kapitelFach, vergleich, bereiche: true }) : null)
    const leitlinien = $derived(gewaehlt ? daten.leitlinien?.[gewaehlt] ?? [] : [])

    const link = 'underline text-light-bl dark:text-dark-bl hover:text-primary dark:hover:text-primary-dark'
</script>

{#snippet marke(fach)}
    <span class="inline-flex items-center gap-1 rounded border px-1 text-[11px] leading-4 text-light-tx-2 dark:text-dark-tx-2"
          style={fachToenung(fach?.color)}>
        <SubjectIcon name={fach?.icon} size={11} color={fach?.color} />{fach?.name ?? '?'}
    </span>
{/snippet}

{#snippet eintrag(id, zeilen)}
    {@const x = kapitelJe.get(id)}
    <li>
        <button type="button" onclick={() => onwaehle(id)}
                class="w-full text-left rounded border border-light-ui-3 dark:border-dark-ui-3 px-2 py-1
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 focus:outline-none focus:ring-2 focus:ring-primary">
            <span class="flex flex-wrap items-baseline gap-1.5">
                {@render marke(faecherJe[x?.fach_id])}
                <span class="font-medium text-light-tx dark:text-dark-tx">{x?.titel}</span>
            </span>
            <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">{lageText(x, stufenJe)}</span>
            {#each zeilen as z, i (i)}{#if z}<span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">{z}</span>{/if}{/each}
        </button>
    </li>
{/snippet}

<div class="space-y-3 text-sm">
    {#if !k}
        <h2 class="font-semibold text-light-tx dark:text-dark-tx">{daten.fach.name}</h2>
        <p class="text-light-tx-2 dark:text-dark-tx-2">
            Wähle ein Kapitel, dann siehst du seine Bezüge: Absprachen, Querverweise des Bildungsplans in andere
            Fächer und was im eigenen Fach darauf aufbaut. Die Klammern links der Mitte verbinden Kapitel des eigenen
            Fachs; der Pfeil zeigt auf das spätere.
        </p>
    {:else}
        <div>
            <h2 class="font-semibold text-light-tx dark:text-dark-tx">{k.titel}</h2>
            <div class="mt-0.5 flex flex-wrap items-baseline gap-1.5 text-xs text-light-tx-2 dark:text-dark-tx-2">
                {@render marke(faecherJe[k.fach_id])}<span>{lageText(k, stufenJe)}</span>
            </div>
            <div class="mt-1 flex flex-wrap gap-3 text-xs">
                <a class={link} href="/knowledge/curriculum/{k.curriculum_id}#kapitel-{k.id}">Im Curriculum öffnen</a>
                {#if k.fach_id !== daten.fach.id}
                    <button type="button" class={link} onclick={() => onmitte(k.fach_id)}>{faecherJe[k.fach_id]?.name} in die Mitte</button>
                {/if}
            </div>
        </div>

        <section>
            <h3 class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">Absprachen ({gruppen.absprachen.length + gruppen.fach.length})</h3>
            <ul class="space-y-1.5">
                {#each gruppen.absprachen as b (b.ander)}
                    {@render eintrag(b.ander, [
                        `${ART_SATZ[b.art_hier] ?? b.art_hier}${b.beidseitig ? ' · beidseitig' : ''}`,
                        ...b.texte.filter(Boolean),
                        pruefungText(b.pruefung),
                    ])}
                {/each}
                {#each gruppen.fach as f, i (i)}
                    <li class="rounded border border-light-ui-3 dark:border-dark-ui-3 px-2 py-1">
                        {@render marke(faecherCode[f.fach_code] ?? { name: f.fach_code })}
                        <span class="text-light-tx dark:text-dark-tx">{f.kapitel_titel ?? 'ganzes Fach'}</span>
                        {#if f.ausserhalb}<span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">nicht in dieser Ansicht</span>{/if}
                        {#if f.text}<span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">{f.text}</span>{/if}
                    </li>
                {/each}
                {#if !gruppen.absprachen.length && !gruppen.fach.length}<li class="text-xs text-light-tx-2 dark:text-dark-tx-2">keine</li>{/if}
            </ul>
        </section>

        <section>
            <h3 class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">Bildungsplan: andere Fächer ({gruppen.fremd.length})</h3>
            <ul class="space-y-1.5">
                {#each gruppen.fremd as b (b.ander)}
                    {@render eintrag(b.ander, [b.typ === 'bereich' ? 'über einen ganzen Bereich' : null, b.beispiele.join(', ')])}
                {:else}<li class="text-xs text-light-tx-2 dark:text-dark-tx-2">keine</li>{/each}
            </ul>
        </section>

        {#if k.fach_id === daten.fach.id}
            <section>
                <h3 class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">Im eigenen Fach — baut auf ({gruppen.baut_auf.length})</h3>
                <ul class="space-y-1.5">
                    {#each gruppen.baut_auf as b (b.ander)}{@render eintrag(b.ander, [b.beispiele.join(', ')])}
                    {:else}<li class="text-xs text-light-tx-2 dark:text-dark-tx-2">nichts</li>{/each}
                </ul>
            </section>
            <section>
                <h3 class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">Im eigenen Fach — wird aufgegriffen in ({gruppen.aufgegriffen.length})</h3>
                <ul class="space-y-1.5">
                    {#each gruppen.aufgegriffen as b (b.ander)}{@render eintrag(b.ander, [b.beispiele.join(', ')])}
                    {:else}<li class="text-xs text-light-tx-2 dark:text-dark-tx-2">nichts</li>{/each}
                </ul>
            </section>
            {#if leitlinien.length}
                <section>
                    <h3 class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">Leitperspektiven und Leitlinien</h3>
                    <ul class="space-y-1 text-xs text-light-tx dark:text-dark-tx">
                        {#each leitlinien as l (`${l.art}-${l.kuerzel}`)}
                            <li>{l.titel}{#if l.aspekte.length}<span class="text-light-tx-2 dark:text-dark-tx-2"> — {l.aspekte.join(', ')}</span>{/if}</li>
                        {/each}
                    </ul>
                </section>
            {/if}
        {/if}
    {/if}

    <section class="pt-2 border-t border-light-ui-3 dark:border-dark-ui-3 text-xs text-light-tx-2 dark:text-dark-tx-2 space-y-1"
             aria-label="Legende der Marken">
        <div class="flex items-center gap-1.5"><ArrowLeftRight class="w-3.5 h-3.5" /> Bezüge zu anderen Fächern</div>
        <div class="flex items-center gap-1.5"><ArrowDownUp class="w-3.5 h-3.5" /> Bezüge im eigenen Fach</div>
        <div class="flex items-center gap-1.5 text-light-re dark:text-dark-re"><TriangleAlert class="w-3.5 h-3.5" /> Absprache laut Jahresverlaufsplänen nicht eingehalten</div>
        <div class="flex items-center gap-1.5"><span class="inline-block w-3 h-3 rounded-full border-2 border-light-tx-2 dark:border-dark-tx-2"></span> Leitperspektive
            <span class="inline-block ml-2 w-2.5 h-2.5 rotate-45 rounded-[2px] border-2 border-light-tx-2 dark:border-dark-tx-2"></span> Leitlinie</div>
        <div>Gestrichelter Rand: Lage geschätzt, ohne Jahresverlaufsplan.</div>
    </section>
</div>
