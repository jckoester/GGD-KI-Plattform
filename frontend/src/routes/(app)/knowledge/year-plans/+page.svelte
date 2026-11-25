<script>
    /**
     * Jahresverlaufspläne der Fachschaften (BD, Schritt 5): je Fach die Pläne des laufenden und
     * kommenden Schuljahrs, darunter eingeklappt das Archiv (F10). Die Fachschaft legt hier neue
     * Pläne an. `?fach=` öffnet ein Fach gezielt (Verweis aus Curricula und Curriculum).
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { createVerlaufsplan, getVerlaufsplaene, uebernehmeVerlaufsplan } from '$lib/api.js'
    import { PLANUNGSARTEN, ausgangspunkte, schuljahreZumAnlegen, teilen } from '$lib/verlaufsplan.js'
    import { pageTitle } from '$lib/stores/pageTitle.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { myGroups } from '$lib/stores/myGroups.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import PageBody from '$lib/components/PageBody.svelte'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'

    pageTitle.set('Jahresverlaufspläne')

    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) goto('/chat')
    })

    let antwort = $state(null)
    let fehler = $state(null)
    let laedt = $state(true)

    $effect(() => {
        getVerlaufsplaene()
            .then((a) => (antwort = a))
            .catch((e) => (fehler = e.message))
            .finally(() => (laedt = false))
    })

    const gewaehlt = $derived(Number($page.url.searchParams.get('fach')) || null)
    const istAdmin = $derived(!!$user?.roles?.includes('admin'))
    // Fachschaft (oder Admin) darf anlegen; der Server prüft es ohnehin.
    const fachschaften = $derived(new Set($myGroups.filter((g) => g.type === 'subject_department' && g.subject_id != null)
        .map((g) => g.subject_id)))

    const faecher = $derived.by(() => {
        const mitPlan = new Set((antwort?.plaene ?? []).map((p) => p.subject_id))
        return [...($subjects ?? [])]
            .filter((f) => mitPlan.has(f.id) || fachschaften.has(f.id) || f.id === gewaehlt)
            .sort((a, b) => (fachschaften.has(b.id) - fachschaften.has(a.id)) || a.name.localeCompare(b.name, 'de'))
    })
    const jahre = $derived(schuljahreZumAnlegen(antwort?.aktuelles_schuljahr))

    // Anlegen
    let neu = $state({})   // je Fach: { stufe, schuljahr, raster }
    let anlegeFehler = $state({})
    $effect(() => {
        for (const f of faecher) {
            if (!neu[f.id] && jahre.length) neu[f.id] = { stufe: '', schuljahr: jahre[0], planungsart: 'sequenz', quelle: '' }
        }
    })
    async function anlegen(fach) {
        const f = neu[fach.id]
        anlegeFehler[fach.id] = null
        try {
            if (f.quelle) {
                // Aus einem anderen Schuljahr übernehmen (Schritt 6): Stufe und Planungsart kommen von dort
                const p = await uebernehmeVerlaufsplan(f.quelle, f.schuljahr)
                goto(`/knowledge/year-plans/${p.id}${p.kapitel_entfallen ? `?entfallen=${p.kapitel_entfallen}` : ''}`)
                return
            }
            const p = await createVerlaufsplan({
                subject_id: fach.id, stufe: Number(f.stufe), schuljahr: f.schuljahr, planungsart: f.planungsart, abschnitte: [],
            })
            goto(`/knowledge/year-plans/${p.id}`)
        } catch (e) {
            anlegeFehler[fach.id] = e.message
        }
    }

    function statusText(p) {
        if (p.status === 'draft') return 'Entwurf'
        return p.beschlossen_am ? `beschlossen am ${p.beschlossen_am.split('-').reverse().join('.')}` : 'beschlossen'
    }

    const feld = 'rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm text-light-tx dark:text-dark-tx'
</script>

<svelte:head><title>Jahresverlaufspläne</title></svelte:head>

<PageBody breit>
    <ZurueckLink href="/knowledge/curricula" label="Curricula" />
    <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">Jahresverlaufspläne</h1>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1 mb-5">
        Wann im Schuljahr was dran ist — je Fach, Klassenstufe und Schuljahr, auf dem Kalender der Schule.
    </p>

    {#if laedt}
        <LoadingBanner message="Pläne werden geladen…" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if faecher.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Noch keine Jahresverlaufspläne. Anlegen kann die Fachschaft eines Fachs.</p>
    {:else}
        <div class="space-y-3">
            {#each faecher as fach (fach.id)}
                {@const plaene = teilen((antwort?.plaene ?? []).filter((p) => p.subject_id === fach.id))}
                {@const darf = istAdmin || fachschaften.has(fach.id)}
                <details
                    class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4"
                    open={gewaehlt ? gewaehlt === fach.id : fachschaften.has(fach.id)}
                >
                    <summary class="cursor-pointer flex items-baseline gap-2">
                        <span class="text-lg font-semibold text-light-tx dark:text-dark-tx">{fach.name}</span>
                        <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">({plaene.aktuell.length})</span>
                    </summary>

                    <div class="mt-3 space-y-1">
                        {#each plaene.aktuell as p (p.id)}
                            <a href="/knowledge/year-plans/{p.id}"
                               class="flex flex-wrap items-baseline gap-x-3 rounded px-2 py-1 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                                <span class="font-medium text-light-bl dark:text-dark-bl">Kl. {p.stufe} · {p.schuljahr}</span>
                                <span class="text-sm {p.status === 'draft' ? 'text-light-or dark:text-dark-or' : 'text-light-tx-2 dark:text-dark-tx-2'}">{statusText(p)}</span>
                                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">{p.wochen} Wochen geplant</span>
                            </a>
                        {:else}
                            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Kein Plan für das laufende oder kommende Schuljahr.</p>
                        {/each}
                    </div>

                    {#if darf && neu[fach.id]}
                        {@const f = neu[fach.id]}
                        {@const quellen = ausgangspunkte(antwort?.plaene, fach.id, Number(f.stufe), f.schuljahr)}
                        <form class="mt-3 flex flex-wrap items-end gap-2" onsubmit={(e) => { e.preventDefault(); anlegen(fach) }}>
                            <label class="text-xs text-light-tx-2 dark:text-dark-tx-2">Klassenstufe
                                <select class="{feld} block" bind:value={f.stufe} required>
                                    <option value="" disabled>wählen</option>
                                    {#each Array.from({ length: 9 }, (_, k) => k + 5) as s (s)}<option value={s}>{s}</option>{/each}
                                </select>
                            </label>
                            <label class="text-xs text-light-tx-2 dark:text-dark-tx-2">Schuljahr
                                <select class="{feld} block" bind:value={f.schuljahr}>
                                    {#each jahre as j (j)}<option value={j}>{j}</option>{/each}
                                </select>
                            </label>
                            {#if !f.quelle}
                                <label class="text-xs text-light-tx-2 dark:text-dark-tx-2">Planung
                                    <select class="{feld} block" bind:value={f.planungsart}>
                                        {#each PLANUNGSARTEN as p (p.wert)}<option value={p.wert}>{p.text}</option>{/each}
                                    </select>
                                </label>
                            {/if}
                            {#if quellen.length}
                                <label class="text-xs text-light-tx-2 dark:text-dark-tx-2">Ausgangspunkt
                                    <select class="{feld} block" bind:value={f.quelle}>
                                        <option value="">leer</option>
                                        {#each quellen as q (q.id)}<option value={q.id}>Plan {q.schuljahr} übernehmen</option>{/each}
                                    </select>
                                </label>
                            {/if}
                            <button type="submit"
                                class="px-3 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark text-on-fill hover:opacity-90">
                                Neuer Plan
                            </button>
                        </form>
                        {#if anlegeFehler[fach.id]}<div class="mt-2"><ErrorBanner message={anlegeFehler[fach.id]} /></div>{/if}
                    {/if}

                    {#if plaene.archiv.length}
                        <details class="mt-3">
                            <summary class="cursor-pointer text-sm text-light-tx-2 dark:text-dark-tx-2">Archiv ({plaene.archiv.length})</summary>
                            <div class="mt-1 space-y-1">
                                {#each plaene.archiv as p (p.id)}
                                    <a href="/knowledge/year-plans/{p.id}"
                                       class="flex flex-wrap items-baseline gap-x-3 rounded px-2 py-1 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                                        <span class="text-light-bl dark:text-dark-bl">Kl. {p.stufe} · {p.schuljahr}</span>
                                        <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">{statusText(p)}</span>
                                    </a>
                                {/each}
                            </div>
                        </details>
                    {/if}
                </details>
            {/each}
        </div>
    {/if}
</PageBody>
