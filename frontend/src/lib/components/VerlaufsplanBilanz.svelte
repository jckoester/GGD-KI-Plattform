<script>
    /**
     * Stundenbilanz eines Jahresverlaufsplans (BD Schritt 7, Unterschritt 6): je Kapitel Soll,
     * geplant, Wochen und Einstufung; bei sequenzgenauer Planung je Kapitel aufklappbar die
     * Sequenzen (Jan, 25.11.2026). Gerechnet hat der Server (`lage.kapitel`).
     *
     * Jede Zeile beginnt mit einem Symbol für ihre Abdeckung (zweiter Durchgang, Jan 25.11.2026):
     * eingetragen, teilweise (nur einige Sequenzen des Kapitels), fehlt — statt eines
     * Hinweisblocks darunter, der vom Plan ablenkte.
     *
     * Props: `lage`, `wochenstunden`, `band` (Curriculum über mehrere Stufen), `planungsart`.
     */
    import { ChevronDown, ChevronRight } from 'lucide-svelte'
    import { bilanzStand } from '$lib/verlaufsplan.js'
    import AbdeckungSymbol from '$lib/components/AbdeckungSymbol.svelte'

    let { lage, wochenstunden = null, band = false, planungsart = 'kapitel' } = $props()

    let offen = $state({})
    const sequenzgenau = $derived(planungsart === 'sequenz')
    const stand = {
        'passt': 'text-light-gr dark:text-dark-gr',
        'zu wenig': 'text-light-or dark:text-dark-or',
        'zu viel': 'text-light-or dark:text-dark-or',
    }
    const ohneKapitel = $derived(new Set(lage?.kapitel_ohne_abschnitt ?? []))
    const ohneSequenzen = $derived(new Set(sequenzgenau ? (lage?.sequenzen_ohne_abschnitt ?? []) : []))
    const fehlendeIn = (k) => (k.sequenzen ?? []).filter((x) => ohneSequenzen.has(x.sequenz_id)).length

    /** Abdeckung einer Kapitelzeile: eingetragen, teilweise (nur einige Sequenzen), fehlt. */
    function kapitelZustand(k) {
        if (ohneKapitel.has(k.kapitel_id)) return ['fehlt', 'Kein Abschnitt nennt dieses Kapitel']
        const n = sequenzgenau ? fehlendeIn(k) : 0
        if (n) return ['teil', `${n} ${n === 1 ? 'Sequenz' : 'Sequenzen'} ohne Abschnitt — aufklappen zeigt, welche`]
        return ['voll', 'Im Plan eingetragen']
    }
</script>

{#if lage?.kapitel?.length}
    <section data-abschnitt="bilanz">
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-2">Stunden je Kapitel</h2>
        {#if band}
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2">Das Curriculum gilt für mehrere Stufen; „Soll“ ist die Stundenzahl für das ganze Band.</p>
        {/if}
        {#if !wochenstunden}
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2">Ohne Wochenstunden im Curriculum zählt die Bilanz nur Wochen.</p>
        {/if}
        <table class="text-sm">
            <thead>
                <tr class="text-left text-light-tx-2 dark:text-dark-tx-2 border-b border-light-ui-3 dark:border-dark-ui-3">
                    <th class="py-1 pr-4">{sequenzgenau ? 'Kapitel und Sequenzen' : 'Kapitel'}</th>
                    <th class="py-1 pr-4">Soll</th><th class="py-1 pr-4">Geplant</th><th class="py-1 pr-4">Wochen</th><th class="py-1"></th>
                </tr>
            </thead>
            {#each lage.kapitel as k (k.kapitel_id)}
                {@const s = bilanzStand(k, wochenstunden)}
                {@const hatSeq = sequenzgenau && k.sequenzen?.length > 0}
                {@const [zustand, hinweis] = kapitelZustand(k)}
                <tbody>
                    <tr class="border-b border-light-ui-2 dark:border-dark-ui-2 text-light-tx dark:text-dark-tx">
                        <td class="py-1 pr-4">
                            <span class="inline-flex items-center gap-1.5">
                                <AbdeckungSymbol {zustand} text={hinweis} />
                                {#if hatSeq}
                                    <button type="button" class="inline-flex items-center gap-1 hover:underline"
                                        aria-expanded={!!offen[k.kapitel_id]}
                                        onclick={() => (offen[k.kapitel_id] = !offen[k.kapitel_id])}>
                                        {#if offen[k.kapitel_id]}<ChevronDown size={14} />{:else}<ChevronRight size={14} />{/if}
                                        {k.titel ?? 'nicht mehr im Curriculum'}
                                    </button>
                                {:else}
                                    <span class={sequenzgenau ? 'pl-5' : ''}>{k.titel ?? 'nicht mehr im Curriculum'}</span>
                                {/if}
                            </span>
                        </td>
                        <td class="py-1 pr-4">{k.soll ?? '–'}</td>
                        <td class="py-1 pr-4">{k.geplant ?? '–'}</td>
                        <td class="py-1 pr-4">{k.wochen}</td>
                        <td class="py-1 {s ? stand[s] : ''}">{s ?? ''}</td>
                    </tr>
                    {#if hatSeq && offen[k.kapitel_id]}
                        {#each k.sequenzen as sq (sq.sequenz_id)}
                            {@const ss = bilanzStand(sq, wochenstunden)}
                            <tr class="border-b border-light-ui-2 dark:border-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2">
                                <td class="py-0.5 pr-4 pl-6">
                                    <span class="inline-flex items-center gap-1.5">
                                        {#if ohneSequenzen.has(sq.sequenz_id)}
                                            <AbdeckungSymbol zustand="fehlt" text="Kein Abschnitt nennt diese Sequenz" />
                                        {:else}
                                            <AbdeckungSymbol zustand="voll" text="Im Plan eingetragen" />
                                        {/if}
                                        {sq.titel ?? 'nicht mehr im Curriculum'}
                                    </span>
                                </td>
                                <td class="py-0.5 pr-4">{sq.soll ?? '–'}</td>
                                <td class="py-0.5 pr-4">{sq.geplant ?? '–'}</td>
                                <td class="py-0.5 pr-4">{sq.wochen}</td>
                                <td class="py-0.5 {ss ? stand[ss] : ''}">{ss ?? ''}</td>
                            </tr>
                        {/each}
                    {/if}
                </tbody>
            {/each}
        </table>
    </section>
{/if}
