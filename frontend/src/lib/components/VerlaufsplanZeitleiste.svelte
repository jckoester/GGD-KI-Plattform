<script>
    /**
     * Ablaufleiste eines Jahresverlaufsplans (BD Schritt 5; zweiter Durchgang, Jan 25.11.2026):
     * die Unterrichtswochen als Raster, die Abschnitte als Blöcke darüber.
     *
     * - Ferien sind eine schraffierte Lücke mit Kurznamen (Schraffur wie im Planer der Gruppe,
     *   `planner-ferien-band`); ein Abschnitt über Ferien zerfällt in Stücke links und rechts.
     * - Darüber Monatsachse, Linie „2. HJ“ und „heute“; darunter die Wochennummern.
     * - Ab drei Wochen trägt ein Block seinen Titel, darunter nur die Nummer.
     * - Freie Wochen gestrichelt „frei“, Wochen nach Schuljahresende rot, Puffer schraffiert
     *   (gegenläufig zu den Ferien, `verlaufsplan-puffer`).
     * - Mindestbreite je Woche; ist die Leiste breiter als der Platz, scrollt sie waagerecht und
     *   springt im laufenden Schuljahr einmal zu „heute“.
     * - Maus über einem Block hebt ihn hier und in Tabelle/Editor hervor (`hervor`, bindable);
     *   Klick ruft `onwahl(i)`.
     *
     * Gerechnet wird das Raster in `$lib/ablaufleiste.js`.
     *
     * Props: `abschnitte`, `lage`, `kapitelReihenfolge`, `kapitelVon`, `planungsart`, `aktuell`
     * (laufendes Schuljahr), `hervor`, `onwahl`.
     */
    import { abschnittFarbe, hinweise, zeitraumText } from '$lib/verlaufsplan.js'
    import { bloecke, freiStuecke, heuteSpalte, monate, raster } from '$lib/ablaufleiste.js'

    let {
        abschnitte = [], lage, kapitelReihenfolge = [], kapitelVon = {}, planungsart = 'kapitel',
        aktuell = false, hervor = $bindable(null), onwahl = () => {},
    } = $props()

    const r = $derived(raster(lage))
    const vorlage = $derived(r.spalten.map((s) => (s.art === 'woche' ? 'minmax(1.5rem, 1fr)' : '1.25rem')).join(' '))
    const mindestbreite = $derived.by(() => {
        const w = r.spalten.filter((s) => s.art === 'woche').length
        const f = r.spalten.length - w
        return `calc(${w * 1.5 + f * 1.25}rem + ${(r.spalten.length - 1) * 2}px)`
    })
    const bl = $derived(bloecke(lage, r))
    const frei = $derived(freiStuecke(lage, r))
    const mon = $derived(monate(lage, r.spalteVon))
    const hj = $derived(lage?.halbjahr_ab_woche ? r.spalteVon[lage.halbjahr_ab_woche] : null)
    const heute = $derived(aktuell ? heuteSpalte(lage, r) : null)
    const n = $derived(lage?.unterrichtswochen ?? 0)
    const ueberhang = $derived(lage?.ueberhang ? { von: r.spalteVon[n + 1], bis: r.spalten.length + 1 } : null)

    function tooltip(a, l) {
        return [`${l.nr}. ${a.titel || 'ohne Thema'}`, zeitraumText(l), ...hinweise(l)].filter(Boolean).join(' · ')
    }

    // Einmal zu „heute“ springen, wenn die Leiste breiter ist als der Platz
    let scroller = $state(null)
    let heuteEl = $state(null)
    let gesprungen = false
    $effect(() => {
        if (gesprungen || !scroller || !heuteEl) return
        if (scroller.scrollWidth > scroller.clientWidth) {
            scroller.scrollLeft = Math.max(0, heuteEl.offsetLeft - scroller.clientWidth / 3)
        }
        gesprungen = true
    })

    // Lesbarer Grund für die Beschriftung auf der kräftigen Puffer-Schraffur
    const grundPuffer = 'rounded px-1 bg-light-ui-2 dark:bg-dark-ui-2'
    const klein = 'text-[10px] leading-none text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap'
</script>

<!-- Wochenlinien in einem Block oder freien Stück (Jan 26.11.2026): Ein Stück liegt nie über
     Ferien, seine Spalten sind also alle Wochen gleicher Breite — ein inneres Raster mit derselben
     Fuge trifft die Wochengrenzen der Leiste. In Schriftfarbe, schwach. -->
{#snippet wochenlinien(wochen)}
    {#if wochen > 1}
        <span class="pointer-events-none absolute inset-0 grid gap-x-0.5" aria-hidden="true"
            style="grid-template-columns: repeat({wochen}, minmax(0, 1fr));">
            {#each Array.from({ length: wochen }, (_, w) => w) as w (w)}
                <span class={w ? 'border-l border-current opacity-25' : ''}></span>
            {/each}
        </span>
    {/if}
{/snippet}

{#if lage}
    <div class="rounded-md border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg p-3" data-abschnitt="zeitleiste">
        <div class="overflow-x-auto pb-1" bind:this={scroller}>
            <div
                class="relative grid gap-x-0.5 gap-y-1"
                style="grid-template-columns: {vorlage}; grid-template-rows: auto auto 2.5rem auto auto; min-width: {mindestbreite};"
                role="group"
                aria-label="Ablauf des Schuljahrs"
            >
                <!-- Zeile 1: Marken -->
                {#if hj}
                    <div class="{klein} font-medium" style="grid-row: 1; grid-column: {hj};" aria-hidden="true">2. HJ</div>
                {/if}
                {#if heute}
                    <div class="{klein} font-semibold text-light-bl dark:text-dark-bl flex justify-center" style="grid-row: 1; grid-column: {heute.spalte};" aria-hidden="true">heute</div>
                {/if}

                <!-- Zeile 2: Monate -->
                {#each mon as m (m.spalte)}
                    <div class="{klein} border-l border-light-ui-3 dark:border-dark-ui-3 pl-0.5" style="grid-row: 2; grid-column: {m.spalte};" aria-hidden="true">{m.text}</div>
                {/each}

                <!-- Zeile 3: Wochenraster, Ferien, Blöcke -->
                {#each r.spalten as s, k (k)}
                    {#if s.art === 'woche'}
                        <div class="rounded-sm {s.ueberhang ? 'bg-light-re-bg dark:bg-dark-re-bg' : 'bg-light-ui-2 dark:bg-dark-ui-2'}"
                            style="grid-row: 3; grid-column: {k + 1};" aria-hidden="true"></div>
                    {:else}
                        <div class="planner-ferien-band rounded-sm" style="grid-row: 3; grid-column: {k + 1};"
                            title="{s.name}" aria-hidden="true"></div>
                    {/if}
                {/each}

                {#each frei as f (f.von)}
                    <div class="relative rounded border border-dashed border-light-tx-2 dark:border-dark-tx-2 flex items-center justify-center {klein}"
                        style="grid-row: 3; grid-column: {f.von} / {f.bis};" aria-hidden="true">
                        {@render wochenlinien(f.wochen)}
                        {#if f.beschriftet}<span class="relative">frei</span>{/if}
                    </div>
                {/each}

                {#each bl as b (b.i)}
                    {@const a = abschnitte[b.i] ?? {}}
                    {@const l = lage.abschnitte[b.i]}
                    {@const farbe = abschnittFarbe(a, kapitelReihenfolge, { planungsart, kapitelVon })}
                    {@const text = tooltip(a, l)}
                    {#each b.stuecke as st, k (k)}
                        <button
                            type="button"
                            class="relative h-10 rounded overflow-hidden px-1 text-xs leading-tight flex items-center
                                   justify-center text-center cursor-pointer transition-shadow
                                   {a.puffer ? 'verlaufsplan-puffer text-light-tx dark:text-dark-tx' : farbe ? 'text-on-fill' : 'bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx dark:text-dark-tx'}
                                   {hervor === b.i ? 'ring-2 ring-offset-1 ring-light-tx dark:ring-dark-tx ring-offset-light-bg dark:ring-offset-dark-bg z-10' : ''}"
                            style="grid-row: 3; grid-column: {st.von} / {st.bis};{farbe && !a.puffer ? ` background-color: ${farbe};` : ''}"
                            title={text}
                            aria-label={st.beschriftung ? text : undefined}
                            aria-hidden={st.beschriftung ? undefined : 'true'}
                            tabindex={st.beschriftung ? 0 : -1}
                            onmouseenter={() => (hervor = b.i)}
                            onmouseleave={() => (hervor = null)}
                            onfocus={() => (hervor = b.i)}
                            onblur={() => (hervor = null)}
                            onclick={() => onwahl(b.i)}
                        >
                            {@render wochenlinien(st.wochen)}
                            {#if st.beschriftung === 'titel'}
                                <span class="relative truncate {a.puffer ? grundPuffer : ''}">{a.titel || b.nr}</span>
                            {:else if st.beschriftung === 'nummer'}
                                <span class="relative font-medium {a.puffer ? grundPuffer : ''}">{b.nr}</span>
                            {/if}
                        </button>
                    {/each}
                {/each}

                {#if ueberhang}
                    <div class="pointer-events-none rounded border-2 border-light-re dark:border-dark-re z-20"
                        style="grid-row: 3; grid-column: {ueberhang.von} / {ueberhang.bis};"
                        title="nach Schuljahresende"></div>
                {/if}

                <!-- Zeile 4: Wochennummern -->
                {#each r.spalten as s, k (k)}
                    {#if s.art === 'woche' && (s.nr === 1 || s.nr % 5 === 0 || s.ueberhang)}
                        <div class="{klein} text-center {s.ueberhang ? 'text-light-re dark:text-dark-re' : ''}"
                            style="grid-row: 4; grid-column: {k + 1};" aria-hidden="true">{s.nr}</div>
                    {/if}
                {/each}

                <!-- Zeile 5: Ferien -->
                {#each r.spalten as s, k (k)}
                    {#if s.art === 'ferien'}
                        <div class="{klein} flex justify-center" style="grid-row: 5; grid-column: {k + 1};" title={s.name}>{s.kurz}</div>
                    {/if}
                {/each}

                <!-- Linien über alle Zeilen -->
                {#if hj}
                    <div class="pointer-events-none border-l border-dashed border-light-tx-2 dark:border-dark-tx-2 -ml-px z-20"
                        style="grid-row: 1 / 5; grid-column: {hj};" aria-hidden="true"></div>
                {/if}
                {#if heute}
                    <div bind:this={heuteEl} class="pointer-events-none flex justify-center z-30"
                        style="grid-row: 2 / 5; grid-column: {heute.spalte};" aria-hidden="true">
                        <div class="w-0.5 h-full bg-light-bl dark:bg-dark-bl rounded-full"></div>
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}
