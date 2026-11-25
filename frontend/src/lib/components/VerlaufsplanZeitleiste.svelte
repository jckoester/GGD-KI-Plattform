<script>
    /**
     * Zeitleiste eines Jahresverlaufsplans (BD, Schritt 5): die Unterrichtswochen des Schuljahrs
     * als Spalten, die Abschnitte als Balken darüber, die Ferien als Trenner dazwischen.
     *
     * Ferienwochen haben keine Spalte — der Plan zählt nur Unterrichtswochen (BD F1). Wochen nach
     * Schuljahresende (Überhang) sind schraffiert.
     *
     * Props: `abschnitte` (gespeichert), `lage` (vom Server), `kapitelReihenfolge` (für die Farben).
     */
    import { abschnittFarbe, hinweise, zeitraumText } from '$lib/verlaufsplan.js'

    let { abschnitte = [], lage, kapitelReihenfolge = [] } = $props()

    const spalten = $derived(Math.max(lage?.unterrichtswochen ?? 0, lage?.belegt ?? 0, 1))
    // Trenner nach dem letzten Abschnitt vor den Ferien — nicht nach dem Schuljahresende.
    const ferien = $derived((lage?.ferienabschnitte ?? []).filter((f) => f.endet_mit !== 'Schuljahresende'))

    function tooltip(a, l) {
        return [a.titel || 'ohne Thema', zeitraumText(l), ...hinweise(l)].filter(Boolean).join(' · ')
    }
</script>

{#if lage}
    <div class="overflow-x-auto" data-abschnitt="zeitleiste">
        <div
            class="relative grid gap-y-1 min-w-[40rem]"
            style="grid-template-columns: repeat({spalten}, minmax(0, 1fr));"
            role="list"
            aria-label="Zeitleiste des Schuljahrs"
        >
            <!-- Abschnitte -->
            {#each lage.abschnitte as l, i (l.id ?? i)}
                {@const a = abschnitte[i] ?? {}}
                {@const farbe = abschnittFarbe(a, kapitelReihenfolge)}
                <div
                    role="listitem"
                    class="h-9 rounded border border-light-ui-3 dark:border-dark-ui-3 px-1 overflow-hidden
                           text-xs leading-tight flex items-center
                           {farbe ? 'text-on-fill' : 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'}"
                    style="grid-row: 1; grid-column: {l.von_woche} / {l.bis_woche + 1};{farbe ? ` background-color: ${farbe};` : ''}"
                    title={tooltip(a, l)}
                >
                    <span class="truncate">{a.titel || '–'}</span>
                </div>
            {/each}

            <!-- Wochennummern, Überhang schraffiert -->
            {#each Array.from({ length: spalten }, (_, k) => k + 1) as w (w)}
                <div
                    class="text-[10px] text-center text-light-tx-2 dark:text-dark-tx-2
                           {w > (lage.unterrichtswochen ?? 0) ? 'bg-light-re-bg dark:bg-dark-ui-2 line-through' : ''}"
                    style="grid-row: 2; grid-column: {w};"
                    aria-hidden="true"
                >
                    {w === 1 || w % 5 === 0 ? w : ''}
                </div>
            {/each}

            <!-- Ferien: Trenner am Ende des Ferienabschnitts -->
            {#each ferien as f (f.bis_woche)}
                <div
                    class="pointer-events-none border-r-2 border-dashed border-light-tx-2 dark:border-dark-tx-2"
                    style="grid-row: 1 / 3; grid-column: {f.bis_woche};"
                    title={f.endet_mit}
                ></div>
                <div
                    class="text-[10px] text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap -ml-6"
                    style="grid-row: 3; grid-column: {f.bis_woche} / span 2;"
                >
                    {f.endet_mit.replace('ferien', '')}
                </div>
            {/each}
        </div>
    </div>
{/if}
