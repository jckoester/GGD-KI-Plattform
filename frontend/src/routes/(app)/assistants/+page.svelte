<script>
    import {
        ALLE_WERKZEUGE, abschnitteUebersicht, erstelltFilter, filterArten, nachErstellt, stufenText, zurAnzeige,
    } from "$lib/assistentenliste.js";
    import { ladeProduktarten } from "$lib/produktarten.js";
    import ProduktMarken from "$lib/components/ProduktMarken.svelte";
    import { page } from "$app/stores";
    import { BADGE } from "$lib/badges.js";
    import FachBadge from "$lib/components/FachBadge.svelte";
    import { assistentKosten } from "$lib/modellangaben.js";
    import { budget } from "$lib/stores/budget.js";

    const kostenText = (a) => assistentKosten(a, $budget?.eur_usd_rate, $budget?.einheiten_je_euro).marke;
    import PageBody from '$lib/components/PageBody.svelte'
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { getAssistants } from "$lib/api.js";
    import { subjectMap } from "$lib/stores/subjects.js"
    import Schlagwoerter from "$lib/components/Schlagwoerter.svelte"
    import { user } from "$lib/stores/user.js";
    import { Bot, Loader2, Copy, Pencil } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    let assistants = $state([])
    let arten = $state([]) // „stellt her“ (0.40)
    // Filter „Werkzeuge“ in der Adresse (`?erstellt=alle|image|…`) — Links und Zurück tragen ihn.
    const filter = $derived(erstelltFilter($page.url.searchParams.get("erstellt"), arten))
    const angeboteneArten = $derived(filterArten(assistants, arten))
    const gefiltert = $derived(nachErstellt(assistants, filter))
    // F37 c (0.26): spezifische, allgemeine, weitere — Überschriften nur ab zwei Abschnitten.
    const abschnitte = $derived(abschnitteUebersicht(gefiltert))

    const FILTER_KLASSE = "px-3 py-1 rounded-full text-sm border transition-colors"
    const filterKlasse = (aktiv) => aktiv
        ? `${FILTER_KLASSE} border-light-ui-3 dark:border-dark-ui-3 bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx font-medium`
        : `${FILTER_KLASSE} border-light-ui-2 dark:border-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2`
    let loading = $state(true)
    let error = $state(null)

    const AUDIENCE_LABELS = {
        all: "Alle",
        student: "Schüler:innen",
        teacher: "Lehrkräfte",
    }

    function getAudienceLabel(audience) {
        return AUDIENCE_LABELS[audience] || audience || ""
    }

    function isTeacher(u) {
        return !!u && (u.roles.includes("teacher") || u.roles.includes("admin"))
    }

    function isOwn(assistant, u) {
        return !!u && assistant.created_by === u.pseudonym
    }

    onMount(async () => {
        try {
            const [data, geladeneArten] = await Promise.all([getAssistants(), ladeProduktarten()])
            assistants = zurAnzeige(data.items)
            arten = geladeneArten
        } catch (err) {
            error = err.message ?? 'Fehler beim Laden der Assistenten'
        } finally {
            loading = false
        }
    })
</script>

<PageBody breit>
    <div class="max-w-4xl mx-auto">
        <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
            <Bot class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Assistenten</h1>
        </div>

        {#if !loading && angeboteneArten.length}
            <nav aria-label="Filter nach Werkzeug" class="flex flex-wrap gap-2 mb-6">
                <a href="/assistants" class={filterKlasse(!filter)} aria-current={!filter ? "page" : undefined}>Alle</a>
                <a href="/assistants?erstellt={ALLE_WERKZEUGE}" class={filterKlasse(filter === ALLE_WERKZEUGE)}
                   aria-current={filter === ALLE_WERKZEUGE ? "page" : undefined}>Werkzeuge</a>
                {#each angeboteneArten as art (art.id)}
                    <a href="/assistants?erstellt={art.id}" class={filterKlasse(filter === art.id)}
                       aria-current={filter === art.id ? "page" : undefined}>{art.filter}</a>
                {/each}
            </nav>
        {/if}

        {#if loading}
            <div class="flex items-center justify-center py-12">
                <div class="flex flex-col items-center gap-2 text-light-tx-2 dark:text-dark-tx-2">
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Assistenten werden geladen...</p>
                </div>
            </div>
        {:else if error}
            <ErrorBanner message={error} />
        {:else if assistants.length === 0}
            <div class="text-center py-12 text-light-tx-3 dark:text-dark-tx-3">
                <p class="text-lg">Derzeit sind keine Assistenten für dich verfügbar.</p>
            </div>
        {:else if gefiltert.length === 0}
            <div class="text-center py-12 text-light-tx-3 dark:text-dark-tx-3">
                <p class="text-lg">Kein Assistent für dich stellt das her.</p>
                <a href="/assistants" class="text-sm text-light-bl dark:text-dark-bl hover:underline">Alle Assistenten zeigen</a>
            </div>
        {:else}
          {#each abschnitte as abschnitt (abschnitt.titel)}
            {#if abschnitt.titel}
                <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-3 mt-6 first:mt-0">
                    {abschnitt.titel}
                </h2>
            {/if}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {#each abschnitt.liste as assistant (assistant.id)}
                    {@const fach = assistant.subject_id != null ? $subjectMap[assistant.subject_id] : null}
                    <!-- Kachel = Klickfläche = Hover-Fläche (0.27): Die Kachel ist Flex-Spalte, der
                         Knopf füllt sie — sonst färbte sich bei kurzer Beschreibung nur ein Teil. -->
                    <div class="relative group flex flex-col bg-light-bg-2 dark:bg-dark-bg-2
                               border border-light-ui-3 dark:border-dark-ui-3
                               rounded-lg overflow-hidden">
                        <!-- Farbiger Streifen oben (nur bei Fach mit Farbe) — zusammen mit dem
                             Fach-Etikett; allein war er nicht eindeutig (Jan, 01.11.2026). -->
                        {#if fach?.color}
                            <span class="block h-[3px] w-full shrink-0" style="background-color: {fach.color}"></span>
                        {/if}
                        <!-- Hauptklickbereich → Chat -->
                        <button
                            onclick={() => goto(`/chat?assistant_id=${assistant.id}`)}
                            class="flex-1 w-full text-left p-4 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <div class="flex items-start gap-3">
                                <Bot class="w-5 h-5 text-light-bl dark:text-dark-bl shrink-0 mt-0.5" />
                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span class="font-medium text-light-tx dark:text-dark-tx">
                                            {assistant.name}
                                        </span>
                                        <FachBadge {fach} />
                                        {#if assistant.audience}
                                            <span class={BADGE}>{getAudienceLabel(assistant.audience)}</span>
                                        {/if}
                                        {#if stufenText(assistant)}
                                            <span class={BADGE}>{stufenText(assistant)}</span>
                                        {/if}
                                        <ProduktMarken {assistant} />
                                        {#if kostenText(assistant)}
                                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2"
                                                  title="Geschätzte Kosten je Nachricht, samt Prompt und Dokumenten">{kostenText(assistant)}</span>
                                        {/if}
                                    </div>
                                    {#if assistant.description}
                                        <p class="text-sm mt-1 text-light-tx-2 dark:text-dark-tx-2 line-clamp-2">
                                            {assistant.description}
                                        </p>
                                    {/if}
                                    <!-- Das Fach steht schon als Badge — nicht noch einmal als Schlagwort. -->
                                    <Schlagwoerter tags={(assistant.tags ?? []).filter((t) => t !== fach?.slug)} />
                                </div>
                            </div>
                        </button>

                        <!-- Aktions-Icons (Lehrkräfte) — erscheinen beim Hover -->
                        {#if isTeacher($user)}
                            <div class="absolute top-2 right-2 flex gap-1
                                        opacity-0 group-hover:opacity-100 focus-within:opacity-100
                                        transition-opacity">
                                {#if isOwn(assistant, $user)}
                                    <button
                                        onclick={() => goto(`/assistants/my/${assistant.id}`)}
                                        title="Bearbeiten"
                                        class="p-1.5 rounded-md
                                               bg-light-bg-2/90 dark:bg-dark-bg-2/90
                                               border border-light-ui-3 dark:border-dark-ui-3
                                               text-light-tx-2 dark:text-dark-tx-2
                                               hover:text-light-tx dark:hover:text-dark-tx
                                               transition-colors"
                                    >
                                        <Pencil size={13} />
                                    </button>
                                {/if}
                                <button
                                    onclick={() => goto(`/assistants/my/neu?from=${assistant.id}`)}
                                    title="Als Vorlage duplizieren"
                                    class="p-1.5 rounded-md
                                           bg-light-bg-2/90 dark:bg-dark-bg-2/90
                                           border border-light-ui-3 dark:border-dark-ui-3
                                           text-light-tx-2 dark:text-dark-tx-2
                                           hover:text-light-tx dark:hover:text-dark-tx
                                           transition-colors"
                                >
                                    <Copy size={13} />
                                </button>
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
          {/each}
        {/if}
    </div>
</PageBody>
