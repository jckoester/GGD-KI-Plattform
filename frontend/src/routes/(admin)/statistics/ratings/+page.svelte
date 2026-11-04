<script>
    /**
     * Antwortbewertung (0.31, Päckchen T, ADR-020): Daumen je Assistent oder Modell.
     *
     * Die Zahlen sind Wochenzähler ohne Personen- und Chatbezug (`rating_counts`); sie
     * überdauern das Löschen der Chats. Einen Anteil zeigt die Seite erst ab
     * `MINDEST_FUER_ANTEIL` Bewertungen — darunter wäre er Zufall.
     */
    import { onMount } from "svelte";
    import { getBewertungStatistik } from "$lib/api.js";
    import { ArrowLeft, Download, ThumbsUp } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import { kalenderwoche } from "$lib/vorabstatistik.js";
    import {
        MINDEST_FUER_ANTEIL,
        anteilText,
        bewertungCsv,
        gesamt,
        zeilenName,
    } from "$lib/bewertungsstatistik.js";

    function toDateString(d) {
        return d.toLocaleDateString("sv-SE");
    }

    const today = new Date();
    const defaultFrom = new Date(today);
    defaultFrom.setDate(today.getDate() - 7 * 12);

    let data = $state(null);
    let loading = $state(true);
    let error = $state(null);
    let gruppierung = $state("assistent");
    let fromDate = $state(toDateString(defaultFrom));
    let toDate = $state(toDateString(today));

    const summeZeitraum = $derived(
        data
            ? data.wochen.reduce((s, w) => ({ plus: s.plus + w.plus, minus: s.minus + w.minus }),
                  { plus: 0, minus: 0 })
            : null,
    );

    async function reload() {
        loading = true;
        error = null;
        try {
            data = await getBewertungStatistik(fromDate, toDate, gruppierung);
        } catch (e) {
            error = e.message;
        }
        loading = false;
    }

    function herunterladen() {
        const inhalt = bewertungCsv(data.zeilen, data.gruppierung);
        const url = URL.createObjectURL(new Blob([inhalt], { type: "text/csv;charset=utf-8" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = `bewertungen-${data.gruppierung}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    onMount(reload);

    const feld = "rounded border border-light-tx-2 dark:border-dark-tx-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx px-2 py-1 text-sm";
</script>

<svelte:head>
    <title>Antwortbewertung</title>
</svelte:head>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-5xl mx-auto py-8 space-y-6 text-light-tx dark:text-dark-tx">
    <div class="flex items-center gap-2">
        <ThumbsUp class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Antwortbewertung</h1>
    </div>

    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Unter jeder Antwort im Chat lässt sich ein Daumen hoch („hilfreich“) oder runter („nicht
        hilfreich“) setzen. Gezählt wird je Woche, Assistent, Modell und Rolle — ohne Person und
        ohne Chat; die Zahlen bleiben, wenn Chats gelöscht werden. Eine Bewertung zählt in der Woche,
        in der sie zuerst gesetzt wurde. Test- und Vorschau-Chats zählen nicht. Den Anteil
        „hilfreich“ zeigt die Tabelle erst ab {MINDEST_FUER_ANTEIL} Bewertungen.
    </p>

    <div class="flex flex-wrap items-center gap-4 text-sm">
        <div class="flex items-center gap-2">
            <label for="gruppierung" class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Je:</label>
            <select id="gruppierung" bind:value={gruppierung} onchange={reload} class={feld}>
                <option value="assistent">Assistent</option>
                <option value="modell">Modell</option>
            </select>
        </div>
        <div class="flex items-center gap-2">
            <label for="from-date" class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Von:</label>
            <input id="from-date" type="date" bind:value={fromDate} max={toDate} class={feld}
                   onchange={() => { if (fromDate <= toDate) reload(); }} />
        </div>
        <div class="flex items-center gap-2">
            <label for="to-date" class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Bis:</label>
            <input id="to-date" type="date" bind:value={toDate} min={fromDate} class={feld}
                   onchange={() => { if (fromDate <= toDate) reload(); }} />
        </div>
    </div>

    {#if error}
        <ErrorBanner message={error} />
    {:else if loading && !data}
        <LoadingBanner />
    {:else if data}
        {#if data.zeilen.length === 0}
            <div class="p-6 text-center rounded border border-light-tx-2 dark:border-dark-tx-2
                        text-light-tx-2 dark:text-dark-tx-2">
                Keine Bewertungen im Zeitraum.
            </div>
        {:else}
            <section class="space-y-2">
                <div class="flex items-center justify-between gap-4">
                    <h2 class="text-lg font-semibold">
                        Je {data.gruppierung === "modell" ? "Modell" : "Assistent"}
                    </h2>
                    <button onclick={herunterladen}
                            class="flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline">
                        <Download class="w-4 h-4" /> CSV
                    </button>
                </div>
                <div class="overflow-x-auto rounded border border-light-ui-3 dark:border-dark-ui-3">
                    <table class="w-full text-sm">
                        <thead class="bg-light-bg-2 dark:bg-dark-bg-2 text-left">
                            <tr>
                                <th rowspan="2" class="px-3 py-2 font-medium align-bottom">
                                    {data.gruppierung === "modell" ? "Modell" : "Assistent"}
                                </th>
                                <th colspan="3" class="px-3 pt-2 font-medium text-center">Schüler:innen</th>
                                <th colspan="3" class="px-3 pt-2 font-medium text-center">Lehrkräfte</th>
                                <th rowspan="2" class="px-3 py-2 font-medium text-right align-bottom">Anteil gesamt</th>
                            </tr>
                            <tr>
                                {#each [0, 1] as k (k)}
                                    <th class="px-3 pb-2 font-medium text-right" title="hilfreich">👍</th>
                                    <th class="px-3 pb-2 font-medium text-right" title="nicht hilfreich">👎</th>
                                    <th class="px-3 pb-2 font-medium text-right">Anteil</th>
                                {/each}
                            </tr>
                        </thead>
                        <tbody>
                            {#each data.zeilen as z (z.schluessel ?? "ohne")}
                                {@const g = gesamt(z)}
                                <tr class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                    <td class="px-3 py-1.5">{zeilenName(z, data.gruppierung)}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{z.plus_schueler}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{z.minus_schueler}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{anteilText(z.plus_schueler, z.minus_schueler)}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{z.plus_lehrkraft}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{z.minus_lehrkraft}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{anteilText(z.plus_lehrkraft, z.minus_lehrkraft)}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums font-medium">{anteilText(g.plus, g.minus)}</td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="space-y-2">
                <h2 class="text-lg font-semibold">Je Woche</h2>
                <div class="overflow-x-auto rounded border border-light-ui-3 dark:border-dark-ui-3">
                    <table class="w-full text-sm">
                        <thead class="bg-light-bg-2 dark:bg-dark-bg-2 text-left">
                            <tr>
                                <th class="px-3 py-2 font-medium">Woche</th>
                                <th class="px-3 py-2 font-medium text-right" title="hilfreich">👍</th>
                                <th class="px-3 py-2 font-medium text-right" title="nicht hilfreich">👎</th>
                                <th class="px-3 py-2 font-medium text-right">Anteil</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each data.wochen as w (w.woche)}
                                <tr class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                    <td class="px-3 py-1.5 whitespace-nowrap">{kalenderwoche(w.woche)}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{w.plus}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{w.minus}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{anteilText(w.plus, w.minus)}</td>
                                </tr>
                            {/each}
                            <tr class="border-t-2 border-light-ui-3 dark:border-dark-ui-3 font-medium">
                                <td class="px-3 py-1.5">Zeitraum</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{summeZeitraum.plus}</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{summeZeitraum.minus}</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{anteilText(summeZeitraum.plus, summeZeitraum.minus)}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </section>
        {/if}
    {/if}
</div>
