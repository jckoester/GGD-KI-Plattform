<script>
    /**
     * Archiv der Planung, Ebene 1: Gruppen (0.42, Päckchen AO, F3/F12).
     *
     * Gruppen, die nicht mehr im Menü „Planung“ stehen — frühere, in denen ich noch Lehrkraft
     * bin, und solche, in denen ich eigene Planung habe, aber keine Mitgliedschaft mehr. Alles
     * hier ist lesend; was gezeigt wird, entscheidet `GET /planning/archive`.
     */
    import { getPlanungsArchiv } from '$lib/api.js'
    import { anzahl, archivPfad } from '$lib/planung_archiv.js'
    import ArchivAnsicht from '$lib/components/planner/ArchivAnsicht.svelte'
    import FachBadge from '$lib/components/FachBadge.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'

    let gruppen = $state([])
    let laedt = $state(true)
    let fehler = $state(null)
    let ansicht = $state('kacheln')

    $effect(() => {
        getPlanungsArchiv()
            .then((g) => (gruppen = g))
            .catch((e) => (fehler = e.message))
            .finally(() => (laedt = false))
    })

    function umfang(g) {
        return [anzahl(g.einheiten, 'Einheit', 'Einheiten'), anzahl(g.stunden, 'Stunde', 'Stunden')].join(' · ')
    }
</script>

<svelte:head><title>Archiv der Planung</title></svelte:head>

<div class="max-w-5xl mx-auto p-6 space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
        <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">Archiv der Planung</h1>
        <ArchivAnsicht bind:ansicht />
    </div>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Einheiten und Stunden früherer Gruppen. Du kannst sie lesen, aber nicht mehr ändern.
    </p>

    {#if laedt}
        <LoadingBanner message="Archiv wird geladen …" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if gruppen.length === 0}
        <InfoBanner message="Im Archiv liegt noch nichts. Hier erscheinen Gruppen früherer Schuljahre mit ihrer Planung." />
    {:else if ansicht === 'liste'}
        <ul class="divide-y divide-light-ui-2 dark:divide-dark-ui-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3">
            {#each gruppen as g (g.id)}
                <li>
                    <a href={archivPfad(g.id)}
                       class="flex items-center gap-3 px-4 py-3 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors">
                        <span class="flex-1 min-w-0 font-medium text-light-tx dark:text-dark-tx truncate">{g.name}</span>
                        <FachBadge fach={g.fach} />
                        <span class="w-20 text-xs text-light-tx-2 dark:text-dark-tx-2">{g.schuljahr ?? ''}</span>
                        <span class="w-40 text-right text-xs text-light-tx-2 dark:text-dark-tx-2">{umfang(g)}</span>
                    </a>
                </li>
            {/each}
        </ul>
    {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each gruppen as g (g.id)}
                <a href={archivPfad(g.id)}
                   class="block rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4
                          bg-light-bg dark:bg-dark-bg hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors">
                    <div class="flex items-start justify-between gap-2">
                        <span class="font-medium text-light-tx dark:text-dark-tx">{g.name}</span>
                        {#if g.schuljahr}
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{g.schuljahr}</span>
                        {/if}
                    </div>
                    <div class="mt-2"><FachBadge fach={g.fach} /></div>
                    <p class="mt-3 text-xs text-light-tx-2 dark:text-dark-tx-2">{umfang(g)}</p>
                    {#if g.zugang === 'eigentum'}
                        <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">Nur deine eigene Planung</p>
                    {/if}
                </a>
            {/each}
        </div>
    {/if}
</div>
