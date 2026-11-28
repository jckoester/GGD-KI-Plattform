<script>
    /**
     * Vernetzung, Teil B (0.67, F10): Fach × Fach einer Klassenstufe als echte Tabelle. Je Zelle
     * die Zahl der verbundenen Kapitelpaare als Text („A 2 · Q 3“), dazu die Mengenstufe als
     * Farbfeld (`--diagramm-stufe-n`, wie die Leitlinien-Übersicht). Ein Klick öffnet die
     * Zeitachse mit dem Zeilenfach in der Mitte und dem Spaltenfach als einziger Spur.
     */
    import { ArrowDownUp, TriangleAlert } from '@lucide/svelte'
    import { kurz, satz } from '$lib/vernetzung_matrix.js'
    import SubjectIcon from '$lib/components/SubjectIcon.svelte'

    /** @type {{ t: any, schalter: any, hervor?: number|null, pfad: (z: any, s: any) => string, onzelle: (z: any, s: any) => void }} */
    let { t, schalter, hervor = null, pfad, onzelle } = $props()
    let ueber = $state(null)   // { r, s }: Zeile und Spalte unter dem Zeiger

    // Versuch (Jan, 28.11.2026): gefüllte Zellen statt Farbfeld neben der Zahl. Zurück: `false`.
    // Schrift je Stufe aus `--diagramm-stufe-n-tx` (layout.css, nach APCA gewählt).
    const GEFUELLT = true
    const gefuellt = (c) => GEFUELLT && c.farbe > 0
    // Die Marke „nicht eingehalten“ wie in der Zeitachse; ihr Grund folgt der Zelle, sonst steht
    // im dunklen Modus Schwarz auf Hellblau (Jan, 28.11.2026). Hell sind dort die Stufen 4–5.
    const markeStil = (farbe) => {
        const art = farbe >= 4 ? 'hell' : 'dunkel'
        return `background: var(--diagramm-marke-${art}-bg); color: var(--diagramm-marke-${art}-tx)`
    }

    function klick(e, zeile, spalte) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return   // neuer Tab bleibt möglich
        e.preventDefault()
        onzelle(zeile, spalte)
    }
</script>

<div class="overflow-x-auto">
    <table class="border-separate border-spacing-0.5 text-xs" onmouseleave={() => (ueber = null)}>
        <caption class="sr-only">Verbundene Kapitelpaare je Fächerpaar. Zeile: Fach in der Mitte, Spalte: Fach daneben.</caption>
        <thead>
            <tr>
                <td></td>
                {#each t.faecher as f, j (f.id)}
                    <th scope="col" class="px-1 pb-1 align-bottom font-semibold min-w-14
                               {ueber?.s === j ? 'text-light-tx dark:text-dark-tx' : 'text-light-tx-2 dark:text-dark-tx-2'}"
                        title={f.name}>
                        <span class="flex flex-col items-center gap-0.5">
                            <SubjectIcon name={f.icon} size={14} color={f.color} />
                            <span>{f.code}</span>
                        </span>
                        <span class="sr-only">{f.name}</span>
                    </th>
                {/each}
                <th scope="col" class="px-2 pb-1 align-bottom font-semibold text-light-tx-2 dark:text-dark-tx-2">Summe</th>
            </tr>
        </thead>
        <tbody>
            {#each t.zeilen as r, i (r.fach.id)}
                <tr class={r.fach.id === hervor ? 'outline outline-2 outline-primary dark:outline-primary-dark rounded' : ''}>
                    <!-- Hervorhebung ohne andere Schriftstärke: die Spalte darf nicht breiter werden -->
                    <th scope="row" class="pr-3 text-left font-normal whitespace-nowrap text-light-tx dark:text-dark-tx
                               {ueber?.r === i ? 'underline decoration-2 underline-offset-2' : ''}">
                        <span class="inline-flex items-center gap-1.5">
                            <SubjectIcon name={r.fach.icon} size={14} color={r.fach.color} />
                            {r.fach.name}
                            <span class="text-light-tx-2 dark:text-dark-tx-2">({r.fach.kapitel})</span>
                        </span>
                    </th>
                    {#each r.zellen as c, j (c.fach.id)}
                        {@const text = satz(r.fach, c.fach, c.z, schalter)}
                        <td class="p-0 text-center">
                            <a href={pfad(r.fach, c.fach)} title={text} aria-label={text}
                               onclick={(e) => klick(e, r.fach, c.fach)}
                               onmouseenter={() => (ueber = { r: i, s: j })} onfocus={() => (ueber = { r: i, s: j })}
                               style={gefuellt(c) ? `background-color: var(--diagramm-stufe-${c.farbe}); color: var(--diagramm-stufe-${c.farbe}-tx)` : undefined}
                               class="flex flex-col items-center justify-center h-11 min-w-14 px-1 rounded
                                      focus:outline-none focus:ring-2 focus:ring-primary
                                      {gefuellt(c) ? 'hover:ring-2 hover:ring-light-tx dark:hover:ring-dark-tx'
                                                   : `${c.diagonal ? 'bg-light-ui-2 dark:bg-dark-ui-2' : 'bg-light-bg-2 dark:bg-dark-bg-2'} hover:bg-light-ui-3 dark:hover:bg-dark-ui-3`}
                                      {ueber && (ueber.r === i || ueber.s === j) && !gefuellt(c) ? 'ring-1 ring-light-ui-3 dark:ring-dark-ui-3' : ''}">
                                {#if c.n}
                                    <span class="inline-flex items-center gap-1 font-semibold {gefuellt(c) ? '' : 'text-light-tx dark:text-dark-tx'}" aria-hidden="true">
                                        {#if c.farbe && !GEFUELLT}
                                            <span class="inline-block w-3 h-3 rounded-sm" style="background-color: var(--diagramm-stufe-{c.farbe})"></span>
                                        {/if}
                                        {#if c.diagonal}<ArrowDownUp class="w-3.5 h-3.5" />{/if}{c.n}
                                        {#if c.z.verletzt}
                                            <!-- Rot auf Blau ist schlecht zu lesen: das Warnzeichen auf eigenem Grund -->
                                            <span class="marke" style={gefuellt(c) ? markeStil(c.farbe) : undefined}>
                                                <TriangleAlert class="w-3 h-3" />
                                            </span>
                                        {/if}
                                    </span>
                                    {#if !c.diagonal}
                                        <span class="text-[10px] leading-tight {gefuellt(c) ? '' : 'text-light-tx-2 dark:text-dark-tx-2'}" aria-hidden="true">{kurz(c.z, schalter)}</span>
                                    {/if}
                                {:else}
                                    <span class="text-light-tx-2 dark:text-dark-tx-2" aria-hidden="true">·</span>
                                {/if}
                            </a>
                        </td>
                    {/each}
                    <td class="px-2 text-center text-light-tx-2 dark:text-dark-tx-2">{r.summe}</td>
                </tr>
            {/each}
        </tbody>
    </table>
</div>

<style>
    /* wie `.marke` in VernetzungZeitachse.svelte */
    .marke {
        display: inline-flex;
        align-items: center;
        padding: 1px 3px;
        border-radius: 4px;
        border: 1px solid var(--color-light-ui-3);
        background: var(--color-light-bg);
        color: var(--color-light-re);
    }
    :global(.dark) .marke {
        border-color: var(--color-dark-ui-3);
        background: var(--color-dark-bg);
        color: var(--color-dark-re);
    }
</style>
