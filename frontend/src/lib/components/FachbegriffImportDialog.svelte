<script>
    /**
     * Fachbegriffe aus Dateien einspielen (Paket 10, AP4).
     *
     * Zwei Schritte, und der erste ist der wichtigere: **Probelauf, dann bestätigen.**
     * Derselbe Aufruf, einmal ohne und einmal mit Wirkung — was in der Vorschau steht,
     * ist deshalb genau das, was der echte Lauf tut, und nicht eine Vorhersage darüber.
     *
     * Die Regeln der Vorschau stehen in `$lib/fachbegriffe_import.js`; hier ist
     * Darstellung. Warum getrennt: Welche Zeile eine Frage stellt und wann „einspielen"
     * überhaupt lohnt, sind Entscheidungen — die prüft das Projekt im Modul.
     */
    import { Upload, Loader2, ExternalLink, FileDown } from "lucide-svelte";
    import { importiereFachbegriffe } from "$lib/api.js";
    import {
        brauchtEinbettung,
        eingespielt,
        entwuerfe,
        gruppiert,
        lohntSich,
        zusammenfassung,
    } from "$lib/fachbegriffe_import.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";

    let { fach, fachname, onclose, onfertig } = $props();

    let dateien = $state([]);
    let bericht = $state(null);
    let fertig = $state(null);
    let fehler = $state(null);
    let laeuft = $state(false);
    /** Dateinamen, deren handveränderte Knoten ersetzt werden sollen. */
    let ueberschreiben = $state([]);

    const entwurfszeilen = $derived(entwuerfe(bericht));
    const gruppen = $derived(gruppiert(bericht));
    const ergebniszeilen = $derived(eingespielt(fertig));

    function dateienGewaehlt(e) {
        dateien = [...(e.target.files ?? [])];
        // Ein neues Bündel macht jede vorige Vorschau ungültig — sie zu behalten hieße,
        // eine Bestätigung für Dateien anzubieten, die gar nicht mehr gewählt sind.
        bericht = null;
        fertig = null;
        ueberschreiben = [];
        fehler = null;
    }

    function umschalten(datei) {
        ueberschreiben = ueberschreiben.includes(datei)
            ? ueberschreiben.filter((d) => d !== datei)
            : [...ueberschreiben, datei];
    }

    async function lauf(probelauf) {
        laeuft = true;
        fehler = null;
        try {
            const antwort = await importiereFachbegriffe(fach, dateien, {
                probelauf,
                ueberschreiben,
            });
            if (probelauf) {
                bericht = antwort;
            } else {
                fertig = antwort;
                onfertig?.(antwort);
            }
        } catch (e) {
            fehler = e.message;
        } finally {
            laeuft = false;
        }
    }
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
    <div
        class="w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg p-6
               bg-light-bg dark:bg-dark-bg
               border border-light-ui-3 dark:border-dark-ui-3"
    >
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
            Fachbegriffe einspielen — {fachname}
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            Markdown-Dateien einzeln oder als Zip-Bündel mit Abbildungen unter
            <code>_Abb/</code>. Was eingespielt wird, ist sofort für alle sichtbar, die
            das Fach lesen dürfen — auch für Schüler:innen.
        </p>

        {#if !fertig}
            <label
                class="mt-4 flex flex-col gap-2 text-sm text-light-tx dark:text-dark-tx"
            >
                Dateien wählen
                <input
                    type="file"
                    multiple
                    accept=".md,.svg,.zip"
                    onchange={dateienGewaehlt}
                    class="text-sm text-light-tx-2 dark:text-dark-tx-2
                           file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0
                           file:text-sm file:bg-light-bg-2 dark:file:bg-dark-bg-2
                           file:text-light-tx dark:file:text-dark-tx"
                />
            </label>
            {#if dateien.length > 0}
                <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-1">
                    {dateien.length}
                    {dateien.length === 1 ? "Datei" : "Dateien"} gewählt
                </p>
            {/if}
            <!--
                Ein schlichter Link, kein `fetch`: Der Browser schickt das Sitzungscookie
                von selbst mit, und es gibt nichts zu parametrieren. Ein Umweg über
                `api.js` brächte hier nur eine Fehlerbehandlung für einen Fall, den es
                nicht gibt — wer den Dialog offen hat, ist Lehrkraft.
            -->
            <p class="mt-3 text-xs text-light-tx-2 dark:text-dark-tx-2">
                Noch keine Dateien?
                <a
                    href="/api/context/fachbegriffe/vorlage"
                    download
                    class="text-light-bl dark:text-dark-bl hover:underline
                           inline-flex items-center gap-1"
                >
                    <FileDown size="12" /> Vorlage herunterladen
                </a>
                — zwei Musterbegriffe, ein Stoffsteckbrief und eine Kurzfassung des
                Formats. Ausführlich in der
                <a
                    href="/help/fachbegriffe-pflegen"
                    class="text-light-bl dark:text-dark-bl hover:underline"
                >Hilfe</a>.
            </p>
        {/if}

        {#if fehler}
            <div class="mt-4"><ErrorBanner message={fehler} /></div>
        {/if}

        <!-- ── Vorschau ────────────────────────────────────────────────── -->
        {#if bericht && !fertig}
            <div class="mt-5">
                <h3 class="text-sm font-semibold text-light-tx dark:text-dark-tx">
                    Vorschau — {zusammenfassung(bericht)}
                </h3>
                <p class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                    Bis hierher wurde nichts geschrieben.
                </p>
            </div>

            {#if entwurfszeilen.length > 0}
                <div class="mt-3">
                    <WarningBanner
                        message={`${entwurfszeilen.length} ${
                            entwurfszeilen.length === 1 ? "Datei ist" : "Dateien sind"
                        } nicht als fachlich geprüft markiert (${entwurfszeilen
                            .map((z) => `${z.datei}: ${z.pruefstatus}`)
                            .join(", ")}). Einspielen heißt veröffentlichen.`}
                    />
                </div>
            {/if}

            {#each gruppen as gruppe (gruppe.zustand)}
                <div class="mt-4">
                    <h4
                        class="text-sm font-medium text-light-tx dark:text-dark-tx
                               flex items-baseline gap-2"
                    >
                        {gruppe.label}
                        <span class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                            {gruppe.zeilen.length}
                        </span>
                    </h4>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {gruppe.erklaerung}
                    </p>
                    <ul class="mt-1.5 space-y-1">
                        {#each gruppe.zeilen as zeile (zeile.datei)}
                            <li class="text-sm text-light-tx dark:text-dark-tx">
                                {#if zeile.zustand === "uebersprungen"}
                                    <label class="flex items-start gap-2">
                                        <input
                                            type="checkbox"
                                            checked={ueberschreiben.includes(zeile.datei)}
                                            onchange={() => umschalten(zeile.datei)}
                                            class="mt-1"
                                        />
                                        <span>
                                            {zeile.titel}
                                            <span
                                                class="text-xs text-light-tx-3
                                                       dark:text-dark-tx-3"
                                            >
                                                ({zeile.datei}) — mit der Datei
                                                überschreiben
                                            </span>
                                        </span>
                                    </label>
                                {:else}
                                    {zeile.titel}
                                    <span
                                        class="text-xs text-light-tx-3 dark:text-dark-tx-3"
                                    >
                                        ({zeile.datei})
                                    </span>
                                {/if}
                            </li>
                        {/each}
                    </ul>
                </div>
            {/each}

            {#if bericht.warnungen.length > 0}
                <div class="mt-4">
                    <h4 class="text-sm font-medium text-light-tx dark:text-dark-tx">
                        Hinweise
                    </h4>
                    <ul
                        class="mt-1 space-y-0.5 text-xs text-light-tx-2
                               dark:text-dark-tx-2 list-disc list-inside"
                    >
                        {#each bericht.warnungen as hinweis}
                            <li>{hinweis}</li>
                        {/each}
                    </ul>
                </div>
            {/if}

            {#if bericht.offene_ziele.length > 0}
                <div class="mt-4">
                    <h4 class="text-sm font-medium text-light-tx dark:text-dark-tx">
                        Verweise ins Leere ({bericht.offene_ziele.length})
                    </h4>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Diese Ziele gibt es noch nicht. Die Verbindung entsteht von
                        selbst, sobald sie eingespielt werden — die Liste ist die
                        Arbeitsliste dafür, kein Fehler.
                    </p>
                    <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-1">
                        {bericht.offene_ziele
                            .slice(0, 15)
                            .map((z) => `${z.ziel} (${z.anzahl}×)`)
                            .join(" · ")}{bericht.offene_ziele.length > 15 ? " …" : ""}
                    </p>
                </div>
            {/if}
        {/if}

        <!-- ── Ergebnis ────────────────────────────────────────────────── -->
        {#if fertig}
            <div class="mt-4">
                <SuccessBanner message={`Eingespielt: ${zusammenfassung(fertig)}.`} />
            </div>
            {#if brauchtEinbettung(fertig)}
                <div class="mt-3">
                    <InfoBanner
                        message="Über Namen und Aliase sind die Einträge sofort zu
                                 finden. Damit der Assistent sie auch inhaltlich findet,
                                 läuft nachts die Einbettung — bis dahin taucht Neues im
                                 Chat noch nicht von selbst auf."
                    />
                </div>
            {/if}
            {#if ergebniszeilen.length > 0}
                <ul class="mt-4 space-y-1">
                    {#each ergebniszeilen as zeile (zeile.datei)}
                        <li class="text-sm">
                            <a
                                href="/knowledge/{zeile.node_id}"
                                class="text-light-bl dark:text-dark-bl hover:underline
                                       inline-flex items-center gap-1"
                            >
                                {zeile.titel}
                                <ExternalLink size="12" />
                            </a>
                        </li>
                    {/each}
                </ul>
            {/if}
        {/if}

        <!-- ── Knöpfe ──────────────────────────────────────────────────── -->
        <div class="mt-6 flex justify-end gap-2">
            <button
                onclick={onclose}
                class="px-3 py-1.5 rounded-md text-sm border border-light-ui-3
                       dark:border-dark-ui-3 text-light-tx dark:text-dark-tx"
            >
                {fertig ? "Schließen" : "Abbrechen"}
            </button>
            {#if !fertig}
                <button
                    onclick={() => lauf(true)}
                    disabled={laeuft || dateien.length === 0}
                    class="px-3 py-1.5 rounded-md text-sm border border-light-ui-3
                           dark:border-dark-ui-3 text-light-tx dark:text-dark-tx
                           disabled:opacity-50"
                >
                    {#if laeuft}<Loader2 size="14" class="inline animate-spin" />{/if}
                    {bericht ? "Vorschau erneuern" : "Vorschau"}
                </button>
                <button
                    onclick={() => lauf(false)}
                    disabled={laeuft || !bericht || !lohntSich(bericht, ueberschreiben)}
                    class="px-3 py-1.5 rounded-md text-sm bg-primary dark:bg-primary-dark
                           text-white disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                    <Upload size="14" /> Einspielen
                </button>
            {/if}
        </div>
    </div>
</div>
