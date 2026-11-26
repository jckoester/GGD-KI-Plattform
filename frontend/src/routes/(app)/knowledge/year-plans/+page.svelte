<script>
    /**
     * Jahresverlaufspläne der Fachschaften (BD, Schritt 5): je Fach die Pläne des laufenden und
     * kommenden Schuljahrs, darunter eingeklappt das Archiv (F10). Die Fachschaft legt hier neue
     * Pläne an. Fachfilter wie bei den Curricula (Schritt 7); `?fach=` wählt ein Fach gezielt
     * (Verweis aus Curricula und Curriculum).
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { createVerlaufsplan, getVerlaufsplaene, uebernehmeVerlaufsplan } from '$lib/api.js'
    import { PLANUNGSARTEN, ausgangspunkte, nachSchuljahr, schuljahreZumAnlegen, teilen, zeilenZusatz } from '$lib/verlaufsplan.js'
    import { pageTitle } from '$lib/stores/pageTitle.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { myGroups, myTeachingGroups } from '$lib/stores/myGroups.js'
    import { faecherFiltern } from '$lib/curriculum_baender.js'
    import FaecherFilter from '$lib/components/FaecherFilter.svelte'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import PageBody from '$lib/components/PageBody.svelte'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import ListenZeile from '$lib/components/ListenZeile.svelte'
    import StufenHinweis from '$lib/components/StufenHinweis.svelte'
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

    const istAdmin = $derived(!!$user?.roles?.includes('admin'))
    // Fachschaft (oder Admin) darf anlegen; der Server prüft es ohnehin.
    const fachschaften = $derived(new Set($myGroups.filter((g) => g.type === 'subject_department' && g.subject_id != null)
        .map((g) => g.subject_id)))

    // Eigene Fächer wie bei den Curricula: Unterrichtsgruppen und Fachschaften.
    const eigene = $derived([...new Set([
        ...$myTeachingGroups.filter((g) => g.subject_id).map((g) => g.subject_id),
        ...fachschaften,
    ])])
    const anzahl = $derived((antwort?.plaene ?? []).reduce((m, p) => ({ ...m, [p.subject_id]: (m[p.subject_id] ?? 0) + 1 }), {}))

    // Filter: „Meine Fächer“, „Alle Fächer“ (eigene und solche mit Plänen) oder ein Fach.
    let filter = $state(null)
    let fachWahl = $state($page.url.searchParams.get('fach') ?? '')
    const filterWert = $derived(filter ?? (eigene.length ? 'eigene' : 'alle'))
    const faecher = $derived(faecherFiltern($subjects, {
        eigene, filter: filterWert, fachId: fachWahl ? Number(fachWahl) : null, anzahl,
    }))
    const jahre = $derived(schuljahreZumAnlegen(antwort?.aktuelles_schuljahr))

    // Anlegen
    let neu = $state({})   // je Fach: { stufe, schuljahr, planungsart, quelle }
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

    // Auswahllisten: rechts Platz für den Pfeil (pr-8), sonst steht er im Text (Jan 26.11.2026)
    const feld = 'rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg pl-2 pr-8 py-1 text-sm text-light-tx dark:text-dark-tx'
</script>

<svelte:head><title>Jahresverlaufspläne</title></svelte:head>

<PageBody breit>
    <StufenHinweis eintrag="curricula" />
    <ZurueckLink href="/knowledge" label="Bibliothek" />
    <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">Jahresverlaufspläne</h1>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1 mb-5">
        Wann im Schuljahr was dran ist — je Fach, Klassenstufe und Schuljahr, auf dem Kalender der Schule.
    </p>

    {#if laedt}
        <LoadingBanner message="Pläne werden geladen…" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else}
        <FaecherFilter faecher={$subjects} {eigene} wert={filterWert} bind:fachWahl onwahl={(w) => (filter = w)} />
        {#if faecher.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                {filterWert === 'eigene' && !fachWahl ? 'Du bist in keinem Fach Mitglied der Fachschaft oder einer Unterrichtsgruppe.' : 'Noch keine Jahresverlaufspläne. Anlegen kann die Fachschaft eines Fachs.'}
            </p>
        {/if}
        <div class="space-y-3">
            {#each faecher as fach (fach.id)}
                {@const plaene = teilen((antwort?.plaene ?? []).filter((p) => p.subject_id === fach.id))}
                {@const darf = istAdmin || fachschaften.has(fach.id)}
                <details
                    class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4"
                    open={!!fachWahl || eigene.includes(fach.id)}
                >
                    <summary class="cursor-pointer flex items-baseline gap-2">
                        <span class="text-lg font-semibold text-light-tx dark:text-dark-tx">{fach.name}</span>
                        <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">({plaene.aktuell.length})</span>
                    </summary>

                    <!-- Je Schuljahr, darin je Stufe; Zeilen wie die Curricula (ListenZeile) -->
                    <div class="mt-3 space-y-4">
                        {#each nachSchuljahr(plaene.aktuell, antwort?.aktuelles_schuljahr) as g (g.schuljahr)}
                            <div>
                                <h4 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-1.5">
                                    {g.schuljahr}{#if g.text} <span class="font-normal text-light-tx-2 dark:text-dark-tx-2">· {g.text}</span>{/if}
                                </h4>
                                <div class="space-y-1.5">
                                    {#each g.plaene as p (p.id)}
                                        <ListenZeile href="/knowledge/year-plans/{p.id}" titel="Klasse {p.stufe}"
                                            zusatz={zeilenZusatz(p)} entwurf={p.status === 'draft'}
                                            entwurfHinweis="Noch nicht beschlossen — lesen können ihn alle Lehrkräfte, bearbeiten die Fachschaft"
                                            bearbeitbar={darf} />
                                    {/each}
                                </div>
                            </div>
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
                            <div class="mt-2 space-y-1.5">
                                {#each plaene.archiv as p (p.id)}
                                    <ListenZeile href="/knowledge/year-plans/{p.id}" titel="Klasse {p.stufe} · {p.schuljahr}"
                                        zusatz={zeilenZusatz(p)} entwurf={p.status === 'draft'} />
                                {/each}
                            </div>
                        </details>
                    {/if}
                </details>
            {/each}
        </div>
    {/if}
</PageBody>
