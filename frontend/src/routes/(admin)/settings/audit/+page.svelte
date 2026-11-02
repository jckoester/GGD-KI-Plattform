<script>
    /**
     * Audit-Log lesen (0.28, Plan Schritt 6, F5 „einfach halten“).
     *
     * Nur lesend. Filter nach Kategorie, Ereignis, Akteur und Zeitraum; seitenweise, neueste
     * zuerst. Akteure stehen als Pseudonym da — wer dahintersteht, klärt diese Seite nicht;
     * dafür gibt es die 4-Augen-Wege. Ein Klick aufs Pseudonym filtert nach ihm.
     */
    import { onMount } from "svelte";
    import { ArrowLeft, ChevronLeft, ChevronRight, ScrollText } from "lucide-svelte";
    import { getAuditKatalog, getAuditLog } from "$lib/api.js";
    import { datenText, zielText } from "$lib/auditanzeige.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    const PRO_SEITE = 50;

    let kategorien = $state([]);
    let daten = $state(null);
    let laedt = $state(true);
    let fehler = $state(null);

    let kategorie = $state("");
    let ereignis = $state("");
    let akteur = $state("");
    let von = $state("");
    let bis = $state("");
    let seite = $state(1);

    const kategorieName = $derived(
        Object.fromEntries(kategorien.map((k) => [k.name, k.bezeichnung])),
    );
    const ereignisGruppen = $derived(
        kategorie ? kategorien.filter((k) => k.name === kategorie) : kategorien,
    );
    const seiten = $derived(daten ? Math.max(1, Math.ceil(daten.gesamt / PRO_SEITE)) : 1);

    function fristText(k) {
        if (k.aufbewahrung_tage === null) return `${k.bezeichnung}: unbefristet`;
        return `${k.bezeichnung}: ${k.aufbewahrung_tage} Tage`;
    }

    async function laden() {
        laedt = true;
        fehler = null;
        try {
            daten = await getAuditLog({
                kategorie, ereignis, akteur: akteur.trim(), von, bis, seite, pro_seite: PRO_SEITE,
            });
        } catch (e) {
            fehler = e.message;
        } finally {
            laedt = false;
        }
    }

    function filtern() {
        seite = 1;
        laden();
    }

    function kategorieWechseln() {
        // Ein Ereignis aus einer anderen Kategorie fände nichts mehr.
        if (ereignis && !ereignisGruppen.some((k) => k.ereignisse.some((e) => e.name === ereignis))) {
            ereignis = "";
        }
        filtern();
    }

    function nachAkteur(pseudonym) {
        akteur = pseudonym;
        filtern();
    }

    function zuruecksetzen() {
        kategorie = ereignis = akteur = von = bis = "";
        filtern();
    }

    function blaettern(n) {
        seite = n;
        laden();
    }

    function zeit(iso) {
        return new Date(iso).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "medium" });
    }

    onMount(async () => {
        try {
            kategorien = (await getAuditKatalog()).kategorien;
        } catch (e) {
            fehler = e.message;
        }
        await laden();
    });

    const feld =
        "bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded px-2 py-1 text-light-tx dark:text-dark-tx";
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-6xl mx-auto py-4 space-y-5">
    <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
        <ScrollText class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Audit-Log</h1>
    </div>

    <InfoBanner
        message={"Sicherheitsrelevante Ereignisse: gescheiterte Anmeldungen, Änderungen in der Verwaltung, Krisen-Flags, Löschläufe. Ohne Inhalte — kein Chat- oder Meldungstext. Personen erscheinen als Pseudonym; aufgelöst wird hier nichts. Die Einträge lassen sich nicht ändern oder löschen; sie verfallen nach Frist" +
            (kategorien.length ? ` (${kategorien.map(fristText).join(", ")}).` : ".")}
    />

    <form
        class="flex flex-wrap items-end gap-3 text-sm text-light-tx-2 dark:text-dark-tx-2"
        onsubmit={(e) => {
            e.preventDefault();
            filtern();
        }}
    >
        <label class="flex flex-col gap-1">
            Kategorie
            <select value={kategorie} onchange={(e) => { kategorie = e.currentTarget.value; kategorieWechseln(); }} class="{feld} min-w-[10rem]">
                <option value="">alle</option>
                {#each kategorien as k (k.name)}
                    <option value={k.name}>{k.bezeichnung}</option>
                {/each}
            </select>
        </label>
        <label class="flex flex-col gap-1">
            Ereignis
            <select value={ereignis} onchange={(e) => { ereignis = e.currentTarget.value; filtern(); }} class="{feld} min-w-[16rem]">
                <option value="">alle</option>
                {#each ereignisGruppen as k (k.name)}
                    <optgroup label={k.bezeichnung}>
                        {#each k.ereignisse as e (e.name)}
                            <option value={e.name}>{e.bezeichnung}</option>
                        {/each}
                    </optgroup>
                {/each}
            </select>
        </label>
        <label class="flex flex-col gap-1">
            Akteur (Pseudonym oder Anfang)
            <input bind:value={akteur} placeholder="z. B. 3f9a…" class="{feld} font-mono" />
        </label>
        <label class="flex flex-col gap-1">
            Von
            <input type="date" value={von} onchange={(e) => { von = e.currentTarget.value; filtern(); }} class={feld} />
        </label>
        <label class="flex flex-col gap-1">
            Bis
            <input type="date" value={bis} onchange={(e) => { bis = e.currentTarget.value; filtern(); }} class={feld} />
        </label>
        <button
            type="submit"
            class="px-3 py-1.5 rounded bg-primary dark:bg-primary-dark text-white"
        >
            Filtern
        </button>
        <button
            type="button"
            onclick={zuruecksetzen}
            class="px-3 py-1.5 rounded border border-light-ui-3 dark:border-dark-ui-3 hover:text-light-tx dark:hover:text-dark-tx"
        >
            Zurücksetzen
        </button>
    </form>

    {#if fehler}
        <ErrorBanner message={fehler} />
    {:else if laedt && !daten}
        <LoadingBanner message="Audit-Log wird geladen…" />
    {:else if daten}
        <div class="flex items-center justify-between text-sm text-light-tx-2 dark:text-dark-tx-2">
            <span>{daten.gesamt} {daten.gesamt === 1 ? "Eintrag" : "Einträge"}</span>
            {#if seiten > 1}
                <span class="flex items-center gap-2">
                    <button
                        onclick={() => blaettern(seite - 1)}
                        disabled={seite <= 1 || laedt}
                        aria-label="Vorige Seite"
                        class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40"
                    >
                        <ChevronLeft class="w-4 h-4" />
                    </button>
                    Seite {seite} von {seiten}
                    <button
                        onclick={() => blaettern(seite + 1)}
                        disabled={seite >= seiten || laedt}
                        aria-label="Nächste Seite"
                        class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40"
                    >
                        <ChevronRight class="w-4 h-4" />
                    </button>
                </span>
            {/if}
        </div>

        {#if daten.eintraege.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Keine Einträge für diese Auswahl.</p>
        {:else}
            <div
                class="overflow-x-auto border border-light-ui-3 dark:border-dark-ui-3 rounded-lg {laedt ? 'opacity-60' : ''}"
            >
                <table class="w-full text-sm">
                    <thead class="bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2">
                        <tr>
                            <th class="text-left font-medium px-3 py-2">Zeit</th>
                            <th class="text-left font-medium px-3 py-2">Ereignis</th>
                            <th class="text-left font-medium px-3 py-2">Akteur</th>
                            <th class="text-left font-medium px-3 py-2">Ziel</th>
                            <th class="text-left font-medium px-3 py-2">Angaben</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each daten.eintraege as e (e.id)}
                            <tr class="border-t border-light-ui-3 dark:border-dark-ui-3 align-top">
                                <td class="px-3 py-2 whitespace-nowrap text-light-tx-2 dark:text-dark-tx-2">
                                    {zeit(e.occurred_at)}
                                </td>
                                <td class="px-3 py-2 text-light-tx dark:text-dark-tx">
                                    {e.bezeichnung}
                                    <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                        {kategorieName[e.category] ?? e.category}
                                    </div>
                                </td>
                                <td class="px-3 py-2">
                                    {#if e.actor_pseudonym}
                                        <button
                                            onclick={() => nachAkteur(e.actor_pseudonym)}
                                            title={`${e.actor_pseudonym} — nach diesem Akteur filtern`}
                                            class="font-mono text-xs text-light-bl dark:text-dark-bl hover:underline"
                                        >
                                            {e.actor_pseudonym.slice(0, 12)}…
                                        </button>
                                    {:else}
                                        <span class="text-light-tx-2 dark:text-dark-tx-2">—</span>
                                    {/if}
                                    {#if e.actor_role}
                                        <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">{e.actor_role}</div>
                                    {/if}
                                </td>
                                <td class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2 font-mono text-xs">
                                    {zielText(e.target_type, e.target_id) || "—"}
                                </td>
                                <td class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2 text-xs break-words">
                                    {datenText(e.payload) || "—"}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    {/if}
</div>
