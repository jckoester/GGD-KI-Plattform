<script>
    import { onMount } from "svelte";
    import { getHeatmap, getStatsTeams, getStatsModels } from "$lib/api.js";
    import { ArrowLeft, ChartColumn, ChevronLeft, ChevronRight } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    const DAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

    let data = $state(null);
    let loading = $state(true);
    let error = $state(null);
    let teams = $state([]);
    let selectedTeam = $state(null);
    let models = $state([]);
    let selectedModel = $state(null);
    let weekOffset = $state(0);

    // Einmal berechnet, nicht per Zelle
    let maxCount = $derived(
        data ? Math.max(...data.cells.map((c) => c.count), 1) : 1,
    );

    function formatWeek(start, end) {
        const fmt = (s) => {
            const [, m, d] = s.split("-");
            return `${d}.${m}.`;
        };
        const [y] = end.split("-");
        return `${fmt(start)} – ${fmt(end)}${y}`;
    }

    async function reload() {
        loading = true;
        error = null;
        try {
            data = await getHeatmap(selectedTeam, selectedModel, weekOffset);
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    onMount(async () => {
        const [teamsData, modelsData] = await Promise.all([
            getStatsTeams(),
            getStatsModels(),
            reload(),
        ]);
        teams = teamsData;
        models = modelsData;
    });
</script>

<svelte:head>
    <title>Anzahl Prompts</title>
</svelte:head>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-2xl mx-auto py-8 space-y-6">
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
            <ChartColumn class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Anzahl Prompts</h1>
        </div>

        <!-- Wochennavigation -->
        <div class="flex items-center gap-1">
            <button
                onclick={() => { weekOffset -= 1; reload() }}
                class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                       text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                title="Vorherige Woche"
            >
                <ChevronLeft class="w-4 h-4" />
            </button>

            <span class="px-2 text-sm text-light-tx-2 dark:text-dark-tx-2 min-w-[11rem] text-center">
                {#if data}
                    {formatWeek(data.week_start, data.week_end)}
                {:else}
                    …
                {/if}
            </span>

            <button
                onclick={() => { weekOffset += 1; reload() }}
                disabled={weekOffset >= 0}
                class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                       text-light-tx-2 dark:text-dark-tx-2 transition-colors
                       disabled:opacity-30 disabled:cursor-not-allowed"
                title="Nächste Woche"
            >
                <ChevronRight class="w-4 h-4" />
            </button>

            {#if weekOffset < 0}
                <button
                    onclick={() => { weekOffset = 0; reload() }}
                    class="ml-1 px-2 py-0.5 rounded text-xs
                           border border-light-tx-2 dark:border-dark-tx-2
                           text-light-tx-2 dark:text-dark-tx-2
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    Heute
                </button>
            {/if}
        </div>
    </div>

    {#if teams.length > 0 || models.length > 0}
        <div class="flex flex-wrap items-center gap-4 text-sm">
            {#if teams.length > 0}
                <div class="flex items-center gap-2">
                    <label
                        for="team-select"
                        class="text-light-tx-2 dark:text-dark-tx-2 shrink-0"
                    >
                        Team:
                    </label>
                    <select
                        id="team-select"
                        value={selectedTeam ?? ''}
                        onchange={(e) => {
                            selectedTeam = e.target.value || null;
                            reload();
                        }}
                        class="rounded border border-light-tx-2 dark:border-dark-tx-2
                               bg-light-ui dark:bg-dark-ui
                               text-light-tx dark:text-dark-tx
                               px-2 py-1 text-sm min-w-[10rem]"
                    >
                        <option value="">Alle Teams</option>
                        {#each teams as t}
                            <option value={t.id}>{t.label}</option>
                        {/each}
                    </select>
                </div>
            {/if}

            {#if models.length > 0}
                <div class="flex items-center gap-2">
                    <label
                        for="model-select"
                        class="text-light-tx-2 dark:text-dark-tx-2 shrink-0"
                    >
                        Modell:
                    </label>
                    <select
                        id="model-select"
                        value={selectedModel ?? ''}
                        onchange={(e) => {
                            selectedModel = e.target.value || null;
                            reload();
                        }}
                        class="rounded border border-light-tx-2 dark:border-dark-tx-2
                               bg-light-ui dark:bg-dark-ui
                               text-light-tx dark:text-dark-tx
                               px-2 py-1 text-sm min-w-[10rem]"
                    >
                        <option value="">Alle Modelle</option>
                        {#each models as m}
                            <option value={m}>{m}</option>
                        {/each}
                    </select>
                </div>
            {/if}
        </div>
    {/if}

    {#if error}
        <ErrorBanner message={error} />
    {:else if loading}
        <LoadingBanner />
    {:else if data}
        <div
            class="rounded border border-light-tx-2 dark:border-dark-tx-2 inline-block"
        >
            <table class="border-collapse text-xs">
                <thead>
                    <tr class="bg-light-ui-3 dark:bg-dark-ui-3">
                        <!-- leere Ecke über der Stunden-Spalte -->
                        <th
                            class="w-6 border-b border-r border-light-tx-2 dark:border-dark-tx-2"
                        ></th>
                        {#each DAY_NAMES as dayName}
                            <th
                                class="px-3 py-2 text-center font-medium
                         text-light-tx dark:text-dark-tx
                         border-b border-r border-light-tx-2 dark:border-dark-tx-2
                         min-w-[2.75rem]"
                            >
                                {dayName}
                            </th>
                        {/each}
                    </tr>
                </thead>
                <tbody>
                    {#each { length: 24 } as _, hour}
                        <tr>
                            <!-- Stunden-Label: nur für die erste Stunde jeder 3er-Gruppe,
                   rowspan=3, Zahl am unteren Rand ausgerichtet -->
                            {#if hour % 3 === 0}
                                <td
                                    rowspan="3"
                                    class="align-bottom text-right pr-1 pb-0.5 w-6
                         text-light-tx-2 dark:text-dark-tx-2
                         border-r border-b-2 border-light-tx-2 dark:border-dark-tx-2
                         {hour < 21 ? 'border-b' : ''}"
                                >
                                    {hour + 3}
                                </td>
                            {/if}
                            <!-- Zellen pro Wochentag -->
                            {#each { length: 7 } as _, dow}
                                {@const cell = data.cells.find(
                                    (c) => c.dow === dow && c.hour === hour,
                                )}
                                {@const count = cell?.count ?? 0}
                                {@const opacity =
                                    count === 0
                                        ? 0
                                        : Math.max(0.15, count / maxCount)}
                                <td
                                    title="{count} Nachricht{count !== 1
                                        ? 'en'
                                        : ''}"
                                    class="h-3 border-r border-light-tx-2 dark:border-dark-tx-2
                         {hour % 3 === 2 ? 'border-b-2' : 'border-b'}
                         border-light-tx-2 dark:border-dark-tx-2
                         {count === 0
                                        ? 'bg-light-ui-3 dark:bg-dark-ui-3'
                                        : 'bg-light-gr-2 dark:bg-dark-gr-2'}"
                                    style={count > 0
                                        ? `opacity: ${opacity.toFixed(2)}`
                                        : ""}
                                >
                                </td>
                            {/each}
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>

        <div
            class="flex items-center gap-4 text-xs text-light-tx-2 dark:text-dark-tx-2"
        >
            <span class="flex items-center gap-1">
                <span
                    class="inline-block w-4 h-4 rounded bg-light-gr-2 dark:bg-dark-gr-2"
                    style="opacity: 0.2"
                ></span>
                wenige Nachrichten
            </span>
            <span class="flex items-center gap-1">
                <span
                    class="inline-block w-4 h-4 rounded bg-light-gr-2 dark:bg-dark-gr-2"
                    style="opacity: 1.0"
                ></span>
                viele Nachrichten
            </span>
        </div>
    {/if}
</div>
