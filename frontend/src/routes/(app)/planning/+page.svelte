<script>
    /**
     * Übersicht „Planung“ (0.42.2): je aktuelle Unterrichtsgruppe eine Kachel in ihren Planer,
     * abgesetzt darunter das Archiv. Dieselben Gruppen und Beschriftungen wie im Menü
     * (`menueGruppen`, `mitBeschriftung`); bis 0.42.1 leitete `/planning` ins Archiv.
     */
    import { getPlanungsArchiv, getPlanungsgruppen } from '$lib/api.js'
    import { anzahl, archivPfad, klassenKurz, menueGruppen, mitBeschriftung, plannerPfad } from '$lib/planung_archiv.js'
    import { subjectMap } from '$lib/stores/subjects.js'
    import { Archive } from 'lucide-svelte'
    import SubjectIcon from '$lib/components/SubjectIcon.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'

    let gruppen = $state([])
    let archiv = $state(null) // Zahl der Archiv-Gruppen; null = unbekannt
    let laedt = $state(true)
    let fehler = $state(null)

    $effect(() => {
        getPlanungsgruppen()
            .then((g) => (gruppen = mitBeschriftung(menueGruppen(g))))
            .catch((e) => (fehler = e.message))
            .finally(() => (laedt = false))
        // Nur für die Zahl auf der Archiv-Kachel — scheitert sie, bleibt die Kachel ohne Zahl.
        getPlanungsArchiv().then((a) => (archiv = a.length)).catch(() => (archiv = null))
    })

    function unterzeile(g) {
        const teile = [g.fach.name]
        const klassen = klassenKurz(g.klassen)
        if (klassen && !g.beschriftung.includes(klassen)) teile.push(klassen)
        if (g.termine) teile.push(anzahl(g.termine, 'Termin', 'Termine'))
        return teile.join(' · ')
    }

    const kachel = 'block rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4 bg-light-bg dark:bg-dark-bg ' +
        'hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors'
</script>

<svelte:head><title>Planung</title></svelte:head>

<div class="max-w-5xl mx-auto p-6 space-y-4">
    <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">Planung</h1>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Deine Unterrichtsgruppen in diesem Schuljahr. Eine Kachel öffnet die Jahresübersicht der Gruppe.
    </p>

    {#if laedt}
        <LoadingBanner message="Gruppen werden geladen …" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if gruppen.length === 0}
        <InfoBanner message="Du hast in diesem Schuljahr keine Unterrichtsgruppe mit Fach. Gruppen verwaltest du unter „Unterricht“." href="/teaching" linkLabel="Zu „Unterricht“" />
    {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each gruppen as g (g.id)}
                {@const fach = $subjectMap[g.fach.id]}
                <a href={plannerPfad(g)} class={kachel}
                   style={fach?.color ? `border-left: 4px solid ${fach.color}` : ''}
                   title={g.beschriftung === g.name ? undefined : g.name}>
                    <div class="flex items-center gap-2">
                        <SubjectIcon name={fach?.icon ?? null} size={18} color={fach?.color ?? null} />
                        <span class="font-medium text-light-tx dark:text-dark-tx truncate">{g.beschriftung}</span>
                    </div>
                    <p class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">{unterzeile(g)}</p>
                </a>
            {/each}
        </div>
    {/if}

    <!-- Abgesetzt: das Archiv ist kein Planer, sondern lesend (F12). -->
    <div class="pt-4 mt-2 border-t border-light-ui-2 dark:border-dark-ui-2">
        <a href={archivPfad()}
           class="flex items-center gap-3 rounded-lg border border-dashed border-light-ui-3 dark:border-dark-ui-3 p-4
                  bg-light-bg-2 dark:bg-dark-bg-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors sm:max-w-sm">
            <Archive class="w-5 h-5 text-light-tx-2 dark:text-dark-tx-2 flex-shrink-0" />
            <span class="min-w-0">
                <span class="block font-medium text-light-tx dark:text-dark-tx">Archiv</span>
                <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Einheiten und Stunden früherer Schuljahre{archiv != null ? ` · ${anzahl(archiv, 'Gruppe', 'Gruppen')}` : ''}
                </span>
            </span>
        </a>
    </div>
</div>
