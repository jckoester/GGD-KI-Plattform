<script>
    import PageBody from "$lib/components/PageBody.svelte";
    import ZurueckLink from "$lib/components/ZurueckLink.svelte";
    import { onMount } from "svelte";
    import { getHeatmap, getStatsTeams, getStatsModels } from "$lib/api.js";
    import { ChartColumn, ChevronLeft, ChevronRight } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import { bereichText, stufe, stufenBereiche, zellenText } from "$lib/heatmap_stufen.js";

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
<PageBody breit>
<ZurueckLink href="/statistics" label="Statistiken" />

<div class="space-y-6">
    <div class="flex items-center">
        <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
            <ChartColumn class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Anzahl Prompts</h1>
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

    <!-- Zentriert, Wochennavigation direkt über der Heatmap (Jan, 19.11.2026): Breiter ziehen
         lässt sich die Heatmap nicht, ohne dass sie leidet. Die Navigation bleibt auch beim
         Laden und bei Fehlern stehen, damit man weiterblättern kann. -->
    <div class="flex flex-col items-center gap-3">
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

    {#if error}
        <div class="w-full"><ErrorBanner message={error} /></div>
    {:else if loading}
        <div class="w-full"><LoadingBanner /></div>
    {:else if data}
        <div
            class="rounded border border-light-ui-3 dark:border-dark-tx-2 inline-block
                   bg-light-bg-2 dark:bg-dark-bg-2"
        >
            <table class="border-collapse text-xs">
                <thead>
                    <tr>
                        <!-- leere Ecke über der Stunden-Spalte -->
                        <td
                            class="w-6 border-b border-r border-light-ui-3 dark:border-dark-tx-2"
                        ></td>
                        {#each DAY_NAMES as dayName}
                            <th
                                scope="col"
                                class="px-3 py-2 text-center font-medium
                         text-light-tx dark:text-dark-tx
                         border-b border-r border-light-ui-3 dark:border-dark-tx-2
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
                                <th
                                    scope="row"
                                    rowspan="3"
                                    class="align-bottom text-right pr-1 pb-0.5 w-6
                         text-light-tx-2 dark:text-dark-tx-2
                         border-r border-b-2 border-light-ui-3 dark:border-dark-tx-2
                         {hour < 21 ? 'border-b' : ''}"
                                >
                                    <span aria-hidden="true">{hour + 3}</span>
                                    <span class="sr-only">{hour}–{hour + 3} Uhr</span>
                                </th>
                            {/if}
                            <!-- Zellen pro Wochentag -->
                            {#each { length: 7 } as _, dow}
                                {@const cell = data.cells.find(
                                    (c) => c.dow === dow && c.hour === hour,
                                )}
                                {@const count = cell?.count ?? 0}
                                {@const s = stufe(count, maxCount)}
                                <td
                                    title={zellenText(DAY_NAMES[dow], hour, count)}
                                    class="h-3 border-r border-light-ui-3 dark:border-dark-tx-2
                         {hour % 3 === 2 ? 'border-b-2' : 'border-b'}
                         border-light-ui-3 dark:border-dark-tx-2"
                                    style={s > 0
                                        ? `background-color: var(--diagramm-stufe-${s})`
                                        : ""}
                                >
                                    <!-- Für Bildschirmleser der Wert in der Zelle (ein
                                         `aria-label` an `<td>` lesen nicht alle vor) -->
                                    <span class="sr-only">{zellenText(DAY_NAMES[dow], hour, count)}</span>
                                </td>
                            {/each}
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>

        <!-- Legende: feste Stufen mit ihren Grenzen (Nachrichten je Stunde) -->
        <div
            class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2"
        >
            <span>Nachrichten je Stunde:</span>
            {#each stufenBereiche(maxCount) as b (b.stufe)}
                <span class="flex items-center gap-1">
                    <span
                        class="inline-block w-4 h-4 rounded"
                        style="background-color: var(--diagramm-stufe-{b.stufe})"
                    ></span>
                    {bereichText(b)}
                </span>
            {/each}
        </div>
    {/if}
    </div>
</div>
</PageBody>
