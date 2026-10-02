<script>
    import { onMount, onDestroy, tick } from "svelte";
    import { getSpend, getStatsTeams, getStatsModels } from "$lib/api.js";
    import { ArrowLeft, ReceiptEuro, LoaderCircle } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import { token, beobachteModus } from "$lib/diagrammfarben.js";
    import { betrag, tabellenZeilen } from "$lib/kostendiagramm.js";

    function toDateString(d) {
        return d.toLocaleDateString('sv-SE')
    }

    const today = new Date()
    const defaultFrom = new Date(today)
    defaultFrom.setDate(today.getDate() - 90)

    let data = $state(null);
    let loading = $state(true);
    let reloading = $state(false);
    let error = $state(null);
    let teams = $state([]);
    let selectedTeam = $state(null);
    let models = $state([]);
    let selectedModel = $state(null);
    let fromDate = $state(toDateString(defaultFrom))
    let toDate = $state(toDateString(today))
    let granularity = $state('month')

    let canvas = $state(null);
    let chart = null;
    let ChartConstructor = null;
    let abmelden = null;

    async function reload() {
        if (chart) {
            reloading = true;
        } else {
            loading = true;
        }
        error = null;
        try {
            data = await getSpend(selectedTeam, selectedModel, fromDate, toDate, granularity);
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

        zeichnen();
    }

    // Verbrauch ist **Blau** — dieselbe Größe wie die Ist-Linie auf `/budget`, dieselbe
    // Farbe. Bis 0.12 stand hier ein Olivgrün als fester Wert: Grün ist Statusfarbe
    // („gut") und für Datenreihen reserviert, und ein fester Wert folgt weder der
    // Palette noch dem Dunkelmodus. Flächig, ohne Rand: Eine halbtransparente Füllung
    // verfälscht die geprüfte Farbe.
    function konfiguration() {
        const f = {
            balken: token("verbrauch"),
            text2: token("text"),
            gitter: token("gitter"),
        };
        return {
            type: "bar",
            data: {
                labels: data.entries.map((e) => e.period),
                datasets: [
                    {
                        label: "Verbrauch",
                        data: data.entries.map((e) => e.eur),
                        backgroundColor: f.balken,
                        borderWidth: 0,
                        // Abgerundet am Datenende, eckig an der Grundlinie
                        // (`borderSkipped` ist dort die Vorgabe).
                        borderRadius: 4,
                        // Schmal halten: Bei drei Monaten wären es sonst breite Klötze.
                        maxBarThickness: 24,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    // Eine Reihe — keine Legende; die Überschrift benennt sie.
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            // Wert vorn.
                            label: (c) => {
                                const e = data.entries[c.dataIndex];
                                return [betrag(e.eur, "€"), betrag(e.usd, "$")];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: f.text2 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: f.gitter, lineWidth: 1 },
                        ticks: { color: f.text2, callback: (v) => betrag(v, "€") },
                    },
                },
            },
        };
    }

    function zeichnen() {
        if (!canvas || !ChartConstructor || !data?.entries?.length) return;
        chart?.destroy();
        chart = new ChartConstructor(canvas.getContext("2d"), konfiguration());
    }

    onMount(async () => {
        const { Chart, registerables } = await import("chart.js");
        Chart.register(...registerables);
        ChartConstructor = Chart;
        // Dunkelmodus eigens gewählt: beim Umschalten mit den dunklen Tokens neu zeichnen.
        abmelden = beobachteModus(zeichnen);

        const [teamsData, modelsData] = await Promise.all([
            getStatsTeams(),
            getStatsModels(),
            reload(),
        ]);
        teams = teamsData;
        models = modelsData;
    });

    onDestroy(() => {
        abmelden?.();
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

    {#if teams.length > 0 || models.length > 0}
      <div class="flex flex-wrap items-center gap-4 text-sm">
        {#if teams.length > 0}
          <div class="flex items-center gap-2">
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

        {#if models.length > 0}
          <div class="flex items-center gap-2">
            <label for="model-select"
                   class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">
              Modell:
            </label>
            <select
              id="model-select"
              value={selectedModel ?? ''}
              onchange={(e) => {
                selectedModel = e.target.value || null
                reload()
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

    <!-- Zeitraum-Filter -->
    <div class="flex flex-wrap items-center gap-4 text-sm">
      <div class="flex items-center gap-2">
        <label for="from-date"
               class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Von:</label>
        <input
          id="from-date"
          type="date"
          bind:value={fromDate}
          max={toDate}
          onchange={() => { if (fromDate <= toDate) reload() }}
          class="rounded border border-light-tx-2 dark:border-dark-tx-2
                 bg-light-ui dark:bg-dark-ui
                 text-light-tx dark:text-dark-tx
                 px-2 py-1 text-sm"
        />
      </div>

      <div class="flex items-center gap-2">
        <label for="to-date"
               class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Bis:</label>
        <input
          id="to-date"
          type="date"
          bind:value={toDate}
          min={fromDate}
          onchange={() => { if (fromDate <= toDate) reload() }}
          class="rounded border border-light-tx-2 dark:border-dark-tx-2
                 bg-light-ui dark:bg-dark-ui
                 text-light-tx dark:text-dark-tx
                 px-2 py-1 text-sm"
        />
      </div>

      <div class="flex items-center gap-2">
        <label for="granularity-select"
               class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Ansicht:</label>
        <select
          id="granularity-select"
          bind:value={granularity}
          onchange={reload}
          class="rounded border border-light-tx-2 dark:border-dark-tx-2
                 bg-light-ui dark:bg-dark-ui
                 text-light-tx dark:text-dark-tx
                 px-2 py-1 text-sm min-w-[7rem]"
        >
          <option value="month">Monat</option>
          <option value="week">Woche</option>
          <option value="day">Tag</option>
        </select>
      </div>
    </div>

    {#if error}
        <ErrorBanner message={error} />
    {:else if loading}
        <LoadingBanner />
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
                  bg-light-bg-2 dark:bg-dark-bg-2 p-4"
            >
                <div class="relative h-72">
                    {#if reloading}
                      <div class="absolute inset-0 flex items-center justify-center
                          bg-light-bg/70 dark:bg-dark-bg/70 rounded z-10">
                        <LoaderCircle class="w-5 h-5 animate-spin text-light-tx-2 dark:text-dark-tx-2" />
                      </div>
                    {/if}
                    <div
                        class="h-full"
                        role="img"
                        aria-label="Verbrauch je Zeitraum, insgesamt {betrag(
                            data.total_eur,
                        )}. Werte in der Tabelle darunter."
                    >
                        <canvas bind:this={canvas} aria-hidden="true"></canvas>
                    </div>
                </div>
                <!-- Tooltips ergänzen, sie dürfen nicht der einzige Weg zu einem Wert sein
                     (Tastatur, Bildschirmleser, Ausdruck). -->
                <details class="mt-3 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <summary class="cursor-pointer">Als Tabelle</summary>
                    <table class="mt-2 w-full">
                        <thead>
                            <tr class="text-left">
                                <th class="pr-4 font-medium">Zeitraum</th>
                                <th class="pr-4 font-medium text-right">Euro</th>
                                <th class="font-medium text-right">Dollar</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each tabellenZeilen(data.entries) as z (z.periode)}
                                <tr>
                                    <td class="pr-4">{z.periode}</td>
                                    <td class="pr-4 text-right tabular-nums">{z.eur}</td>
                                    <td class="text-right tabular-nums">{z.usd}</td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </details>
                <div
                    class="flex flex-wrap items-center justify-between gap-4 mt-4
                    pt-4 border-t border-light-tx-2 dark:border-dark-tx-2
                    text-sm text-light-tx dark:text-dark-tx"
                >
                    <span>
                        Gesamt:
                        <strong>{betrag(data.total_eur, "€")}</strong>
                        /
                        <strong>{betrag(data.total_usd, "$")}</strong>
                    </span>
                    <span class="text-light-tx-2 dark:text-dark-tx-2 text-xs">
                        Kurs: 1 EUR = {data.eur_usd_rate.toLocaleString("de-DE", {
                            minimumFractionDigits: 4,
                            maximumFractionDigits: 4,
                        })} USD
                    </span>
                </div>
            </div>
        {/if}
    {/if}
</div>
