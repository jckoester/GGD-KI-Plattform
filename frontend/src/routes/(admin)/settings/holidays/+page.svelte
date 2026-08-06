<script>
    import { ArrowLeft, CalendarDays, Copy, RefreshCw, Save } from "lucide-svelte";
    import { getHolidayProposal, applyHolidayProposal } from "$lib/api.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    let vorschlag = $state(null);
    // Ohne Auswahl entscheidet die bestehende school_year.yaml. Zum Jahreswechsel wäre
    // das ein Zirkelschluss — dann wählt der Admin das neue Jahr hier aus.
    let gewaehltesJahr = $state("");
    let laedt = $state(false);
    let fehler = $state("");
    let kopiert = $state(false);

    async function laden() {
        laedt = true;
        fehler = "";
        kopiert = false;
        try {
            vorschlag = await getHolidayProposal(gewaehltesJahr || null);
            const aktiv = (vorschlag.schuljahre ?? []).find((j) => j.gewaehlt);
            if (aktiv) gewaehltesJahr = aktiv.name;
        } catch (err) {
            fehler = err.message;
            vorschlag = null;
        } finally {
            laedt = false;
        }
    }

    let uebernehme = $state(false);
    let ergebnis = $state(null);

    async function uebernehmen() {
        uebernehme = true;
        fehler = "";
        ergebnis = null;
        try {
            ergebnis = await applyHolidayProposal(true, gewaehltesJahr || null);
            // Frisch nachladen: Danach steht dort, was tatsächlich in der Datei ist.
            vorschlag = await getHolidayProposal(gewaehltesJahr || null);
        } catch (err) {
            fehler = err.message;
        } finally {
            uebernehme = false;
        }
    }

    async function kopieren() {
        await navigator.clipboard.writeText(vorschlag.yaml);
        kopiert = true;
    }

    // `new Date("2025-09-15")` liest ISO-Datumsangaben als UTC — in Zeitzonen hinter UTC
    // zeigt das den Vortag. Deshalb die Bestandteile direkt in ein lokales Datum setzen.
    function alsDatum(iso) {
        const [j, m, t] = iso.split("-").map(Number);
        return new Date(j, m - 1, t);
    }

    function datum(iso) {
        return alsDatum(iso).toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }

    function tage(liste) {
        return liste
            .map((t) =>
                alsDatum(t).toLocaleDateString("de-DE", {
                    weekday: "short",
                    day: "2-digit",
                    month: "2-digit",
                    year: "numeric",
                }),
            )
            .join(" · ");
    }
</script>

<div class="max-w-4xl mx-auto p-6">
    <a
        href="/settings"
        class="inline-flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4"
    >
        <ArrowLeft class="w-4 h-4" /> Einstellungen
    </a>

    <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx mb-2 flex items-center gap-2">
        <CalendarDays class="w-5 h-5" /> Ferienkalender
    </h1>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-6 max-w-prose">
        Liest Ferien und Schuljahresgrenzen aus dem Stundenplan und schreibt daraus
        <code>config/school_year.yaml</code>. <strong>Halbjahreswechsel</strong> und die
        Schreibweise von <strong>Schuljahr</strong> bleiben unangetastet — die
        Stundenplanquelle kennt sie nicht. Geschrieben wird erst auf Knopfdruck; die
        bisherige Fassung wird gesichert.
    </p>

    <button
        onclick={laden}
        disabled={laedt}
        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary dark:bg-primary-dark
               text-white dark:text-dark-bl disabled:opacity-50"
    >
        <RefreshCw class="w-4 h-4" />
        {vorschlag ? "Erneut abrufen" : "Kalender abrufen"}
    </button>

    {#if laedt}
        <div class="mt-4"><LoadingBanner message="Ferienkalender wird abgerufen …" /></div>
    {/if}
    {#if fehler}
        <div class="mt-4"><ErrorBanner message={fehler} /></div>
    {/if}

    {#if vorschlag && vorschlag.configured === false}
        <div class="mt-4"><InfoBanner message={vorschlag.detail} /></div>
    {:else if vorschlag}
        <div class="mt-6 space-y-4">
            <InfoBanner
                message={`Schuljahr ${vorschlag.schuljahr}: ${vorschlag.abschnitte} Abschnitte, ` +
                    `zusammen ${vorschlag.freie_wochentage} unterrichtsfreie Wochentage.`}
            />

            {#if (vorschlag.schuljahre ?? []).length > 0}
                <section>
                    <label
                        for="schuljahr-wahl"
                        class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                    >
                        Schuljahr
                    </label>
                    <select
                        id="schuljahr-wahl"
                        bind:value={gewaehltesJahr}
                        onchange={laden}
                        class="px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx"
                    >
                        {#each vorschlag.schuljahre as j}
                            <option value={j.name}>
                                {j.name} ({datum(j.beginn)} – {datum(j.ende)})
                            </option>
                        {/each}
                    </select>
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-2 max-w-prose">
                        Vorausgewählt ist das Schuljahr der bestehenden Konfiguration. Für
                        den Jahreswechsel hier das neue wählen — dann muss auch der
                        Halbjahreswechsel in <code>school_year.yaml</code> passen.
                    </p>
                </section>
            {/if}

            {#each vorschlag.warnungen as w}
                <WarningBanner message={w} />
            {/each}

            {#if vorschlag.neu.length > 0}
                <section>
                    <h2 class="font-semibold text-light-tx dark:text-dark-tx mb-1">
                        Neu gegenüber der Konfiguration ({vorschlag.neu.length} Tage)
                    </h2>
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-2">
                        Diese Tage gelten bislang als Unterrichtstage, sind es aber nicht.
                    </p>
                    <p class="text-sm text-light-tx dark:text-dark-tx">{tage(vorschlag.neu)}</p>
                </section>
            {:else}
                <SuccessBanner message="Die Konfiguration ist bereits vollständig." />
            {/if}

            {#if vorschlag.nur_in_config.length > 0}
                <section>
                    <h2 class="font-semibold text-light-tx dark:text-dark-tx mb-1">
                        Nur in der Konfiguration ({vorschlag.nur_in_config.length} Tage)
                    </h2>
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-2 max-w-prose">
                        Diese Tage kennt der Ferienkalender nicht — vermutlich schulintern
                        gelegt (Wandertag, Projektwoche, letzter Schultag). Sie bleiben im
                        Vorschlag erhalten und sollten <strong>nicht</strong> gelöscht werden.
                    </p>
                    <p class="text-sm text-light-tx dark:text-dark-tx">
                        {tage(vorschlag.nur_in_config)}
                    </p>
                </section>
            {/if}

            <section>
                <div class="flex flex-wrap items-center gap-3 mb-3">
                    <button
                        onclick={uebernehmen}
                        disabled={uebernehme}
                        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg
                               bg-primary dark:bg-primary-dark text-white dark:text-dark-bl
                               disabled:opacity-50"
                    >
                        <Save class="w-4 h-4" /> In school_year.yaml übernehmen
                    </button>
                    <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Die bisherige Fassung wird als <code>.bak</code> daneben gesichert.
                    </span>
                </div>
                {#if ergebnis}
                    <div class="mb-3">
                        <SuccessBanner
                            message={`Geschrieben: ${ergebnis.pfad}` +
                                (ergebnis.sicherung ? ` · Sicherung: ${ergebnis.sicherung}` : "")}
                        />
                    </div>
                {/if}

                <div class="flex items-center justify-between mb-2">
                    <h2 class="font-semibold text-light-tx dark:text-dark-tx">
                        Inhalt von <code>school_year.yaml</code>
                    </h2>
                    <button
                        onclick={kopieren}
                        class="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg
                               border border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx"
                    >
                        <Copy class="w-4 h-4" /> Kopieren
                    </button>
                </div>
                {#if kopiert}
                    <div class="mb-2"><SuccessBanner message="In die Zwischenablage kopiert." /></div>
                {/if}
                <pre
                    class="p-4 rounded-lg overflow-x-auto text-xs
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           border border-light-ui-3 dark:border-dark-ui-3">{vorschlag.yaml}</pre>
            </section>
        </div>
    {/if}
</div>
