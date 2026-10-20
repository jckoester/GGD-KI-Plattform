<script>
    import { onMount } from "svelte";
    import { getVorabStatistik } from "$lib/api.js";
    import { ArrowLeft, ScanSearch, Download } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import {
        anteil,
        kalenderwoche,
        summe,
        sortiere,
        knotenanteil,
        wochenCsv,
        knotenCsv,
    } from "$lib/vorabstatistik.js";

    function toDateString(d) {
        return d.toLocaleDateString("sv-SE");
    }

    const today = new Date();
    const defaultFrom = new Date(today);
    defaultFrom.setDate(today.getDate() - 7 * 12);

    let data = $state(null);
    let loading = $state(true);
    let error = $state(null);
    let fach = $state("");
    let fromDate = $state(toDateString(defaultFrom));
    let toDate = $state(toDateString(today));
    let sortierung = $state("angeboten");
    let absteigend = $state(true);

    let gesamt = $derived(data ? summe(data.wochen) : null);
    let knoten = $derived(data ? sortiere(data.knoten, sortierung, absteigend) : []);

    async function reload() {
        loading = true;
        error = null;
        try {
            data = await getVorabStatistik(fromDate, toDate, fach || null);
        } catch (e) {
            error = e.message;
        }
        loading = false;
    }

    function sortiereNach(schluessel) {
        if (sortierung === schluessel) absteigend = !absteigend;
        else {
            sortierung = schluessel;
            absteigend = true;
        }
    }

    function herunterladen(inhalt, name) {
        const url = URL.createObjectURL(new Blob([inhalt], { type: "text/csv;charset=utf-8" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
    }

    onMount(reload);

    const SPALTEN = [
        ["sicher", "sicher vorgelegt"],
        ["angeboten", "angeboten"],
        ["nachgeschlagen", "nachgeschlagen"],
        ["anteil", "Anteil"],
    ];
</script>

<svelte:head>
    <title>Vorab-Suche</title>
</svelte:head>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-5xl mx-auto py-8 space-y-6 text-light-tx dark:text-dark-tx">
    <div class="flex items-center gap-2">
        <ScanSearch class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Vorab-Suche</h1>
    </div>

    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Zu jeder Nachricht legt die Plattform passende Einträge des Wissensspeichers als Inhalt
        vor (<em>sicher</em>) und bietet weitere nur mit Titel an. <em>Nachgeschlagen</em> heißt:
        Der angebotene Eintrag stand im Suchergebnis derselben Antwort — nicht unbedingt, weil das
        Modell gezielt nach ihm gesucht hat. Titel, die oft angeboten und nie nachgeschlagen werden,
        sind Kandidaten für die Pflege der Suchbegriffe. <em>Davon Gruppe</em>: sicher nur, weil die
        Unterrichtsgruppe den Begriff schon hatte — sonst wäre er nur angeboten worden. Vorschau-Chats
        aus dem Editor zählen nicht.
    </p>

    <div class="flex flex-wrap items-center gap-4 text-sm">
        <div class="flex items-center gap-2">
            <label for="fach-select" class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">
                Fach des Chats:
            </label>
            <select
                id="fach-select"
                bind:value={fach}
                onchange={reload}
                class="rounded border border-light-tx-2 dark:border-dark-tx-2
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                       px-2 py-1 text-sm min-w-[10rem]"
            >
                <option value="">Alle</option>
                <option value="ohne">Ohne Fach</option>
                {#each data?.faecher ?? [] as f (f.id)}
                    <option value={String(f.id)}>{f.name}</option>
                {/each}
            </select>
        </div>
        <div class="flex items-center gap-2">
            <label for="from-date" class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Von:</label>
            <input
                id="from-date"
                type="date"
                bind:value={fromDate}
                max={toDate}
                onchange={() => {
                    if (fromDate <= toDate) reload();
                }}
                class="rounded border border-light-tx-2 dark:border-dark-tx-2
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx px-2 py-1 text-sm"
            />
        </div>
        <div class="flex items-center gap-2">
            <label for="to-date" class="text-light-tx-2 dark:text-dark-tx-2 shrink-0">Bis:</label>
            <input
                id="to-date"
                type="date"
                bind:value={toDate}
                min={fromDate}
                onchange={() => {
                    if (fromDate <= toDate) reload();
                }}
                class="rounded border border-light-tx-2 dark:border-dark-tx-2
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx px-2 py-1 text-sm"
            />
        </div>
    </div>

    {#if error}
        <ErrorBanner message={error} />
    {:else if loading && !data}
        <LoadingBanner />
    {:else if data}
        {#if data.wochen.length === 0}
            <div
                class="p-6 text-center rounded border border-light-tx-2 dark:border-dark-tx-2
                       text-light-tx-2 dark:text-dark-tx-2"
            >
                Keine Nachrichten im Zeitraum gezählt.
            </div>
        {:else}
            <section class="space-y-2">
                <div class="flex items-center justify-between gap-4">
                    <h2 class="text-lg font-semibold">Je Woche</h2>
                    <button
                        onclick={() => herunterladen(wochenCsv(data.wochen), "vorab-wochen.csv")}
                        class="flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                    >
                        <Download class="w-4 h-4" /> CSV
                    </button>
                </div>
                <div class="overflow-x-auto rounded border border-light-ui-3 dark:border-dark-ui-3">
                    <table class="w-full text-sm">
                        <thead class="bg-light-bg-2 dark:bg-dark-bg-2 text-left">
                            <tr>
                                <th class="px-3 py-2 font-medium">Woche</th>
                                <th class="px-3 py-2 font-medium text-right">Nachrichten</th>
                                <th class="px-3 py-2 font-medium text-right">mit sicherem Treffer</th>
                                <th class="px-3 py-2 font-medium text-right">mit Angebot</th>
                                <th class="px-3 py-2 font-medium text-right">nachgeschlagen</th>
                                <th class="px-3 py-2 font-medium text-right"
                                    title="Nur Nachrichten ohne sicheren Treffer — daneben wird ein Angebot fast nie nachgeschlagen"
                                >davon ohne sicheren Treffer</th>
                                <th class="px-3 py-2 font-medium text-right">Suchen ohne Angebot</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each data.wochen as w (w.woche)}
                                <tr class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                    <td class="px-3 py-1.5 whitespace-nowrap">{kalenderwoche(w.woche)}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{w.nachrichten}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{w.mit_sicher}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{w.mit_angebot}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">
                                        {anteil(w.angebot_nachgeschlagen, w.mit_angebot)}
                                    </td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">
                                        {anteil(w.angebot_ohne_sicher_nachgeschlagen, w.angebot_ohne_sicher)}
                                    </td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{w.suchen_ohne_angebot}</td>
                                </tr>
                            {/each}
                            <tr class="border-t-2 border-light-ui-3 dark:border-dark-ui-3 font-medium">
                                <td class="px-3 py-1.5">Zeitraum</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{gesamt.nachrichten}</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{gesamt.mit_sicher}</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{gesamt.mit_angebot}</td>
                                <td class="px-3 py-1.5 text-right tabular-nums">
                                    {anteil(gesamt.angebot_nachgeschlagen, gesamt.mit_angebot)}
                                </td>
                                <td class="px-3 py-1.5 text-right tabular-nums">
                                    {anteil(gesamt.angebot_ohne_sicher_nachgeschlagen, gesamt.angebot_ohne_sicher)}
                                </td>
                                <td class="px-3 py-1.5 text-right tabular-nums">{gesamt.suchen_ohne_angebot}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="space-y-2">
                <div class="flex items-center justify-between gap-4">
                    <h2 class="text-lg font-semibold">Je Eintrag</h2>
                    <button
                        onclick={() => herunterladen(knotenCsv(knoten), "vorab-eintraege.csv")}
                        class="flex items-center gap-1 text-sm text-light-bl dark:text-dark-bl hover:underline"
                    >
                        <Download class="w-4 h-4" /> CSV
                    </button>
                </div>
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Das Fach ist das des Eintrags; der Filter oben gilt dem Fach des Chats. Einträge,
                    die du nicht lesen darfst, stehen ohne Titel da.
                </p>
                <div class="overflow-x-auto rounded border border-light-ui-3 dark:border-dark-ui-3">
                    <table class="w-full text-sm">
                        <thead class="bg-light-bg-2 dark:bg-dark-bg-2 text-left">
                            <tr>
                                <th class="px-3 py-2 font-medium">Eintrag</th>
                                <th class="px-3 py-2 font-medium">Fach</th>
                                {#each SPALTEN as [schluessel, name] (schluessel)}
                                    <th
                                        class="px-3 py-2 font-medium text-right"
                                        aria-sort={sortierung === schluessel
                                            ? absteigend
                                                ? "descending"
                                                : "ascending"
                                            : "none"}
                                    >
                                        <button
                                            onclick={() => sortiereNach(schluessel)}
                                            class="hover:underline"
                                        >
                                            {name}{sortierung === schluessel
                                                ? absteigend
                                                    ? " ↓"
                                                    : " ↑"
                                                : ""}
                                        </button>
                                    </th>
                                {/each}
                            </tr>
                        </thead>
                        <tbody>
                            {#each knoten as k (k.node_id)}
                                <tr class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                    <td class="px-3 py-1.5">
                                        {#if k.titel}
                                            <a href={`/knowledge/${k.node_id}`}
                                               class="text-light-bl dark:text-dark-bl hover:underline">{k.titel}</a>
                                        {:else}
                                            <span class="italic text-light-tx-2 dark:text-dark-tx-2">nicht sichtbar</span>
                                        {/if}
                                    </td>
                                    <td class="px-3 py-1.5 text-light-tx-2 dark:text-dark-tx-2">{k.fach ?? "fachlos"}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">
                                        {k.sicher}{#if k.sicher_gruppe}
                                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2"
                                                  title="sicher, weil die Unterrichtsgruppe den Begriff schon hatte"
                                            >(davon Gruppe {k.sicher_gruppe})</span>{/if}
                                    </td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{k.angeboten}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">{k.nachgeschlagen}</td>
                                    <td class="px-3 py-1.5 text-right tabular-nums">
                                        {knotenanteil(k) === null ? "—" : `${Math.round(100 * knotenanteil(k))} %`}
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </section>
        {/if}
    {/if}
</div>
