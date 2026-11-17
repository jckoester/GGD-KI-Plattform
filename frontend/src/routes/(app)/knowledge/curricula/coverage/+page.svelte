<script>
    /**
     * Abdeckung über das Band (0.46, Päckchen AP Teil B, Schritt 8): die IK eines Bands über alle
     * Curricula, die ihm zugeordnet sind. Einstieg aus der Curricula-Liste (Bandkopf) und aus der
     * Abdeckung eines Curriculums. Parameter: `fach`, `fassung`, `band`, optional `entwuerfe=1`.
     */
    import { page } from '$app/stores'
    import { goto } from '$app/navigation'
    import { exportBandAbdeckung, getBandAbdeckung } from '$lib/api.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { abdeckungsPfad } from '$lib/curriculum_baender.js'
    import { gefilterteGruppen, ZUSTAND } from '$lib/curriculum_abdeckung.js'
    import PageBody from '$lib/components/PageBody.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import WarningBanner from '$lib/components/WarningBanner.svelte'
    import { ArrowLeft, FileDown } from 'lucide-svelte'

    // Wie die Curricula-Liste: nur Lehrkräfte und Admins.
    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) goto('/chat')
    })

    const fachId = $derived(Number($page.url.searchParams.get('fach')) || null)
    const fassung = $derived($page.url.searchParams.get('fassung') ?? '')
    const band = $derived($page.url.searchParams.get('band') ?? '')
    const entwuerfe = $derived($page.url.searchParams.get('entwuerfe') === '1')
    const fach = $derived(($subjects ?? []).find((s) => s.id === fachId) ?? null)

    let abdeckung = $state(null)
    let fehler = $state(null)
    let laedt = $state(true)
    let nurLuecken = $state(false)

    $effect(() => {
        if (!fachId || !fassung || !band) {
            fehler = 'Fach, Fassung und Band fehlen in der Adresse.'
            laedt = false
            return
        }
        let abgebrochen = false
        laedt = true
        fehler = null
        getBandAbdeckung(fachId, fassung, band, entwuerfe)
            .then((a) => { if (!abgebrochen) abdeckung = a })
            .catch((e) => { if (!abgebrochen) fehler = e.message })
            .finally(() => { if (!abgebrochen) laedt = false })
        return () => { abgebrochen = true }
    })

    function entwuerfeUmschalten(ein) {
        goto(abdeckungsPfad({ fachId, fassung, band, entwuerfe: ein }), { replaceState: true, noScroll: true })
    }

    const gruppen = $derived(gefilterteGruppen(abdeckung?.ik.gruppen, nurLuecken))

    let exportiert = $state(false)
    let exportFehler = $state(null)
    async function pdf() {
        exportiert = true
        exportFehler = null
        try {
            await exportBandAbdeckung(fachId, fassung, band, { entwuerfe, nurLuecken })
        } catch (e) {
            exportFehler = e.message
        } finally {
            exportiert = false
        }
    }
</script>

<PageBody breit>
    <div class="mb-6">
        <a
            href="/knowledge/curricula"
            class="flex items-center gap-1 mb-2 text-sm text-light-tx-2 dark:text-dark-tx-2
                 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
        >
            <ArrowLeft class="w-4 h-4" /> Zurück zu Curricula
        </a>
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">IK-Abdeckung im Band</h1>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            {fach?.name ?? 'Fach'} · BP {fassung} · {band}
        </p>
    </div>

    {#if laedt}
        <LoadingBanner message="Abdeckung wird berechnet…" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if abdeckung}
        <div class="space-y-5">
            <section>
                <div class="flex flex-wrap items-baseline justify-between gap-2 mb-2">
                    <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx">
                        Curricula des Bands
                    </h2>
                    <label class="inline-flex items-center gap-1.5 text-sm text-light-tx-2 dark:text-dark-tx-2"
                           title="Ein Entwurf, der ein veröffentlichtes Curriculum ersetzen soll, tritt an dessen Stelle.">
                        <input type="checkbox" checked={entwuerfe}
                               onchange={(e) => entwuerfeUmschalten(e.currentTarget.checked)} />
                        Entwürfe einbeziehen
                    </label>
                </div>
                {#if abdeckung.curricula.length}
                    <ul class="flex flex-wrap gap-2">
                        {#each abdeckung.curricula as c (c.id)}
                            <li>
                                <a href={`/knowledge/curriculum/${c.id}`}
                                   class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-sm border border-light-ui-3 dark:border-dark-ui-3
                                          text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                                    {c.title}
                                    {#if c.status === 'draft'}
                                        <span class="text-xs text-light-ye dark:text-dark-ye">Entwurf</span>
                                    {/if}
                                </a>
                            </li>
                        {/each}
                    </ul>
                {:else}
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Diesem Band ist noch kein {entwuerfe ? '' : 'veröffentlichtes '}Curriculum zugeordnet.
                    </p>
                {/if}
                {#if abdeckung.nicht_zugeordnet.length}
                    <div class="mt-3">
                        <WarningBanner
                            message={`Nicht mitgezählt, weil das Band nicht gewählt ist: ${abdeckung.nicht_zugeordnet.map((c) => c.title).join(', ')}. Im Editor lässt sich das Band wählen.`}
                        />
                    </div>
                {/if}
            </section>

            <section>
                <div class="flex flex-wrap items-baseline justify-between gap-2 mb-2">
                    <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx">
                        {abdeckung.ik.verknuepft} von {abdeckung.ik.gesamt} IK verknüpft{abdeckung.ik.partiell
                            ? ` · ${abdeckung.ik.partiell} partiell` : ''}{abdeckung.ik.fehlt
                            ? ` · ${abdeckung.ik.fehlt} fehlen` : ''}
                    </h2>
                    <div class="flex items-center gap-3">
                        <label class="inline-flex items-center gap-1.5 text-sm text-light-tx-2 dark:text-dark-tx-2">
                            <input type="checkbox" bind:checked={nurLuecken} /> nur Lücken
                        </label>
                        <button
                            onclick={pdf}
                            disabled={exportiert}
                            title="Die Liste wie angezeigt als PDF"
                            class="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3
                                   text-light-tx dark:text-dark-tx font-medium hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                   transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <FileDown class="w-3.5 h-3.5" /> PDF
                        </button>
                    </div>
                </div>
                {#if exportFehler}
                    <div class="mb-3"><ErrorBanner message={exportFehler} /></div>
                {/if}
                <div class="space-y-5">
                    {#each gruppen as g (g.titel)}
                        <div>
                            {#if g.titel}
                                <h3 class="text-base font-semibold text-light-tx dark:text-dark-tx border-b border-light-ui-3 dark:border-dark-ui-3 pb-1 mb-2">
                                    {g.titel}
                                </h3>
                            {/if}
                            <ul class="text-sm list-disc pl-5 space-y-1.5 marker:text-light-tx-2 dark:marker:text-dark-tx-2">
                                {#each g.kompetenzen as k (k.node_id)}
                                    <li class="text-light-tx dark:text-dark-tx" data-zustand={k.zustand}>
                                        <span class={ZUSTAND[k.zustand].klasse}>{ZUSTAND[k.zustand].text}</span>
                                        · <span class="font-medium">{k.nr}</span>
                                        {k.titel}
                                        {#if k.curricula.length}
                                            <span class="text-light-tx-2 dark:text-dark-tx-2">
                                                — {k.curricula.map((c) => c.title + (c.partiell ? ' (partiell)' : '')).join(', ')}
                                            </span>
                                        {/if}
                                    </li>
                                {/each}
                            </ul>
                        </div>
                    {:else}
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            {abdeckung.ik.gesamt ? 'Alle Kompetenzen des Bands sind verknüpft.' : 'Für dieses Band sind keine Kompetenzen hinterlegt.'}
                        </p>
                    {/each}
                </div>
            </section>
        </div>
    {/if}
</PageBody>
