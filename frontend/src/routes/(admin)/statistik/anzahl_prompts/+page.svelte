<script>
    import { onMount } from "svelte";
    import { getHeatmap } from "$lib/api.js";
    import {
        ArrowLeft,
        ChartColumn,
        LoaderCircle,
        CircleX,
    } from "lucide-svelte";

    const DAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

    let data = $state(null);
    let loading = $state(true);
    let error = $state(null);

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

    onMount(async () => {
        try {
            data = await getHeatmap();
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
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
        {#if data}
            <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                {formatWeek(data.week_start, data.week_end)}
            </span>
        {/if}
    </div>

    {#if error}
        <div
            class="flex items-center gap-3 p-4 rounded border
                bg-light-re-2 dark:bg-dark-re-2
                border-light-re dark:border-dark-re
                text-dark-tx dark:text-light-tx"
        >
            <CircleX class="w-5 h-5 shrink-0" />
            <span class="text-sm">{error}</span>
        </div>
    {:else if loading}
        <div
            class="flex items-center gap-3 p-4 rounded border
                bg-light-bg dark:bg-dark-bg
                border-light-tx-2 dark:border-dark-tx-2
                text-light-tx-2 dark:text-dark-tx-2"
        >
            <LoaderCircle class="w-5 h-5 animate-spin shrink-0" />
            <span>Lädt…</span>
        </div>
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
