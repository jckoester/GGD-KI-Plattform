<script>
    import { onMount, onDestroy, tick } from "svelte";
    import { getSpend, getStatsTeams } from "$lib/api.js";
    import {
        ArrowLeft,
        ReceiptEuro,
        LoaderCircle,
        CircleX,
    } from "lucide-svelte";

    let data = $state(null);
    let loading = $state(true);
    let reloading = $state(false);
    let error = $state(null);
    let teams = $state([]);
    let selectedTeam = $state(null);

    let canvas = $state(null);
    let chart = null;
    let ChartConstructor = null;

    async function reload() {
        if (chart) {
            reloading = true;   // Canvas bleibt im DOM, Overlay erscheint
        } else {
            loading = true;     // Erster Ladevorgang: voller Spinner
        }
        error = null;
        try {
            data = await getSpend(selectedTeam);
        } catch (e) {
            error = e.message;
            loading = false;
            reloading = false;
            return;
        }
        loading = false;

        if (data.entries.length === 0) {
            chart?.destroy();
            chart = null;
            reloading = false;
            return;
        }

        await tick();
        reloading = false;

        if (!canvas) return;

        if (chart) {
            chart.data.labels = data.entries.map((e) => e.period);
            chart.data.datasets[0].data = data.entries.map((e) => e.eur);
            chart.update();
            return;
        }

        const ctx = canvas.getContext("2d");
        chart = new ChartConstructor(ctx, {
            type: "bar",
            data: {
                labels: data.entries.map((e) => e.period),
                datasets: [
                    {
                        label: "Verbrauch (€)",
                        data: data.entries.map((e) => e.eur),
                        backgroundColor: "rgba(139, 154, 72, 0.7)",
                        borderColor: "rgba(139, 154, 72, 1)",
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const idx = ctx.dataIndex;
                                const e = data.entries[idx];
                                return [
                                    `${e.eur.toFixed(4)} €`,
                                    `${e.usd.toFixed(4)} $`,
                                ];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: "#9ca3af" },
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: "#9ca3af",
                            callback: (v) => `${v} €`,
                        },
                    },
                },
            },
        });
    }

    onMount(async () => {
        const { Chart, registerables } = await import("chart.js");
        Chart.register(...registerables);
        ChartConstructor = Chart;

        const [teamsData] = await Promise.all([getStatsTeams(), reload()]);
        teams = teamsData;
    });

    onDestroy(() => {
        chart?.destroy();
    });
</script>

<svelte:head>
    <title>Kosten</title>
</svelte:head>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-4xl mx-auto py-8 space-y-6">
    <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
        <ReceiptEuro class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Kosten</h1>
    </div>

    {#if teams.length > 0}
      <div class="flex items-center gap-2 text-sm">
        <label for="team-select"
               class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">
          Team:
        </label>
        <select
          id="team-select"
          value={selectedTeam ?? ''}
          onchange={(e) => {
            selectedTeam = e.target.value || null
            reload()
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
        {#if data.entries.length === 0}
            <div
                class="p-6 text-center rounded border
                  border-light-tx-2 dark:border-dark-tx-2
                  text-light-tx-2 dark:text-dark-tx-2"
            >
                Keine Ausgaben im Zeitraum erfasst.
            </div>
        {:else}
            <div
                class="rounded border border-light-tx-2 dark:border-dark-tx-2
                  bg-light-bg dark:bg-dark-bg p-4"
            >
                <div class="relative h-72">
                    {#if reloading}
                      <div class="absolute inset-0 flex items-center justify-center
                          bg-light-bg/70 dark:bg-dark-bg/70 rounded z-10">
                        <LoaderCircle class="w-5 h-5 animate-spin text-light-tx-2 dark:text-dark-tx-2" />
                      </div>
                    {/if}
                    <canvas bind:this={canvas}></canvas>
                </div>
                <div
                    class="flex flex-wrap items-center justify-between gap-4 mt-4
                    pt-4 border-t border-light-tx-2 dark:border-dark-tx-2
                    text-sm text-light-tx dark:text-dark-tx"
                >
                    <span>
                        Gesamt:
                        <strong>{data.total_eur.toFixed(2)} €</strong>
                        /
                        <strong>{data.total_usd.toFixed(2)} $</strong>
                    </span>
                    <span class="text-light-tx-2 dark:text-dark-tx-2 text-xs">
                        Kurs: 1 EUR = {data.eur_usd_rate.toFixed(4)} USD
                    </span>
                </div>
            </div>
        {/if}
    {/if}
</div>
