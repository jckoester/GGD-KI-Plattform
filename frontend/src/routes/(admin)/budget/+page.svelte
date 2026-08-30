<script>
    import { onMount } from 'svelte';
    import { getBudgetGrades, saveBudgetGrades } from '$lib/api.js';
    import { PiggyBank, ArrowLeft, LoaderCircle } from 'lucide-svelte';
    import ErrorBanner from '$lib/components/ErrorBanner.svelte';

    let data = $state(null);           // BudgetGradesResponse
    let loading = $state(true);
    let saving = $state(false);
    let error = $state(null);
    let saveError = $state(null);
    let showConfirm = $state(false);
    let saveResult = $state(null);     // { ok, updated_users }

    // Editierte EUR-Werte: key -> string (damit leere Eingabe moeglich)
    let editedBudgets = $state({});
    // Geschaetzte Nutzerzahl: key -> string (nur fuer Kostenschaetzung, nicht persistiert)
    let estimatedCounts = $state({});

    onMount(async () => {
        try {
            data = await getBudgetGrades();
            for (const g of data.grades) {
                editedBudgets[g.key] = String(g.max_budget_eur);
                estimatedCounts[g.key] = String(g.user_count);
            }
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    });

    // Abgeleitete Werte
    let changedGrades = $derived(
        data ? data.grades.filter(g =>
            parseFloat(editedBudgets[g.key] || '0') !== g.max_budget_eur
        ) : []
    );

    let isValid = $derived(
        data ? data.grades.every(g => {
            const v = parseFloat(editedBudgets[g.key] || '0');
            return v > 0 && isFinite(v);
        }) : false
    );

    // Kostenschaetzung (client-seitig, keine Server-Runde)
    function periodCost(key) {
        const budget = parseFloat(editedBudgets[key] || '0');
        const count = parseInt(estimatedCounts[key] || '0', 10);
        return isFinite(budget) && isFinite(count) ? budget * count : 0;
    }

    // Zahl der Unterrichtswochen aus school_year.yaml (2026/27: 40). Ohne lesbare
    // Datei liefert das Backend null — dann bleibt die Jahresspalte leer, statt eine
    // erfundene Zahl zu zeigen.
    let wochen = $derived(data?.unterrichtswochen);

    function annualCost(key) {
        return wochen ? periodCost(key) * wochen : null;
    }

    function totalPeriod() {
        return data?.grades.reduce((s, g) => s + periodCost(g.key), 0) ?? 0;
    }

    function totalAnnual() {
        return wochen ? totalPeriod() * wochen : null;
    }

    function eur(betrag) {
        return betrag == null ? '—' : `${betrag.toFixed(2)} €`;
    }

    // Hochrechnung: Der Sinn ist der Zeitpunkt. Im Juli weiß jeder, ob die Schule unter
    // ihrer Zusage geblieben ist; im März kann sie die Wochenbeträge noch anheben.
    let hr = $derived(data?.hochrechnung ?? null);
    let auslastung = $derived(
        hr?.erwartet_eur != null && hr?.zugeteilt_eur
            ? Math.round((hr.erwartet_eur / hr.zugeteilt_eur) * 100)
            : null,
    );

    // Speichern-Flow
    async function confirmSave() {
        saving = true;
        saveError = null;
        try {
            const updates = data.grades.map(g => ({
                key: g.key,
                max_budget_eur: parseFloat(editedBudgets[g.key]),
            }));
            saveResult = await saveBudgetGrades(updates);
            showConfirm = false;
            // Lokalen Stand neu laden
            data = await getBudgetGrades();
            for (const g of data.grades) {
                editedBudgets[g.key] = String(g.max_budget_eur);
                estimatedCounts[g.key] = String(g.user_count);
            }
        } catch (e) {
            saveError = e.message;
        } finally {
            saving = false;
        }
    }
</script>

<svelte:head>
    <title>Budget-Einstellungen</title>
</svelte:head>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-4xl mx-auto py-8">
    <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
        <PiggyBank class="w-6 h-6" />
        <h1 class="text-2xl font-semibold">Budget-Einstellungen</h1>
    </div>

    {#if error}
        <ErrorBanner message={error} />
    {:else if loading}
        <div class="flex justify-center items-center h-64">
            <LoaderCircle class="w-8 h-8 animate-spin" />
        </div>
    {:else if data}
        {#if saveResult}
            <div class="bg-green-100 dark:bg-green-900/30 border border-green-400 dark:border-green-600 text-green-700 dark:text-green-300 px-4 py-3 rounded mb-6">
                {saveResult.updated_users} LiteLLM-Budget(s) aktualisiert
            </div>
        {/if}

        <div class="bg-light-ui dark:bg-dark-ui rounded-lg border border-light-tx-2 dark:border-dark-tx-2 overflow-hidden shadow-sm">
            <table class="w-full">
                <thead class="bg-light-ma dark:bg-dark-ma text-left">
                    <tr>
                        <th class="p-3 text-light-tx dark:text-dark-tx font-semibold">Jahrgang/Rolle</th>
                        <th class="p-3 text-light-tx dark:text-dark-tx font-semibold">Budget je Unterrichtswoche (€)</th>
                        <th class="p-3 text-light-tx dark:text-dark-tx font-semibold text-center">Nutzer (DB)</th>
                        <th class="p-3 text-light-tx dark:text-dark-tx font-semibold">Geschätzte Nutzerzahl</th>
                        <th class="p-3 text-light-tx dark:text-dark-tx font-semibold text-right">Max-Kosten je Woche</th>
                        <th class="p-3 text-light-tx dark:text-dark-tx font-semibold text-right">Max-Kosten je Schuljahr</th>
                    </tr>
                </thead>
                <tbody>
                    {#each data.grades as grade, index}
                        <tr class="{index > 0 ? 'border-t border-light-tx-2 dark:border-dark-tx-2' : ''}">
                            <td class="p-3 text-light-tx dark:text-dark-tx">{grade.label}</td>
                            <td class="p-3">
                                <input
                                    type="number"
                                    min="0.01"
                                    step="0.01"
                                    bind:value={editedBudgets[grade.key]}
                                    class="w-24 rounded border border-light-tx-2 dark:border-dark-tx-2
                                           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                                           px-2 py-1 text-sm text-right"
                                />
                            </td>
                            <td class="p-3 text-center text-light-tx-2 dark:text-dark-tx-2">{grade.user_count}</td>
                            <td class="p-3">
                                <input
                                    type="number"
                                    min="0"
                                    step="1"
                                    bind:value={estimatedCounts[grade.key]}
                                    class="w-20 rounded border border-light-tx-2 dark:border-dark-tx-2
                                           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                                           px-2 py-1 text-sm text-right"
                                />
                            </td>
                            <td class="p-3 text-right text-light-tx dark:text-dark-tx">
                                {eur(periodCost(grade.key))}
                            </td>
                            <td class="p-3 text-right text-light-tx dark:text-dark-tx">
                                {eur(annualCost(grade.key))}
                            </td>
                        </tr>
                    {/each}

                    <!-- Summenzeile -->
                    <tr class="font-semibold border-t-2 border-light-tx-2 dark:border-dark-tx-2">
                        <td class="p-3 text-light-tx dark:text-dark-tx">Gesamt</td>
                        <td class="p-3"></td>
                        <td class="p-3"></td>
                        <td class="p-3"></td>
                        <td class="p-3 text-right text-light-tx dark:text-dark-tx">
                            {eur(totalPeriod())}
                        </td>
                        <td class="p-3 text-right text-light-tx dark:text-dark-tx">
                            {eur(totalAnnual())}
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        {#if hr}
            <div class="mt-6 rounded border border-light-ui-3 dark:border-dark-ui-3
                        bg-light-bg-2 dark:bg-dark-bg-2 px-4 py-3">
                <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2">
                    Hochrechnung aufs Schuljahr
                </h2>
                {#if hr.erwartet_eur == null}
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Noch keine Unterrichtswoche vergangen — es gibt nichts fortzuschreiben.
                    </p>
                {:else}
                    <p class="text-sm text-light-tx dark:text-dark-tx">
                        Bisher verbraucht: <strong>{eur(hr.verbraucht_eur)}</strong> in
                        {hr.wochen_vergangen} von {hr.wochen_gesamt} Unterrichtswochen.
                        Bei diesem Tempo endet das Schuljahr bei
                        <strong>{eur(hr.erwartet_eur)}</strong>{#if hr.zugeteilt_eur}
                            von {eur(hr.zugeteilt_eur)} zugeteilt<!--
                        -->{#if auslastung != null} ({auslastung} %){/if}{/if}.
                    </p>
                    {#if !hr.belastbar}
                        <p class="text-sm mt-2 text-light-tx-2 dark:text-dark-tx-2">
                            ⚠️ Erst {hr.wochen_vergangen} Woche(n) Grundlage — eine einzelne
                            Projektwoche verschiebt die Zahl noch erheblich. Ab etwa vier
                            Wochen wird sie belastbar.
                        </p>
                    {:else if auslastung != null && auslastung < 60}
                        <p class="text-sm mt-2 text-light-tx-2 dark:text-dark-tx-2">
                            Es zeichnet sich ab, dass ein erheblicher Teil nicht abfließt.
                            Jetzt lassen sich die Wochenbeträge noch anheben — am
                            Schuljahresende ist der Rest nur noch zu verwalten.
                        </p>
                    {:else if auslastung != null && auslastung > 100}
                        <p class="text-sm mt-2 text-light-re dark:text-dark-re">
                            Bei diesem Tempo wird die Zusage überschritten. Wochenbeträge
                            senken oder den Nutzerkreis prüfen.
                        </p>
                    {/if}
                    <p class="text-xs mt-2 text-light-tx-3 dark:text-dark-tx-3">
                        Lineare Fortschreibung des bisherigen Verbrauchs. Sie kennt keine
                        Saison — Klassenarbeitsphasen und Projekttage schlagen erst durch,
                        wenn sie stattgefunden haben.
                    </p>
                {/if}
            </div>
        {/if}

        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-4">
            Spalte "Nutzer (DB)" zeigt nur Nutzer, die sich mindestens einmal angemeldet haben.
            Für die Kostenschätzung tatsächliche Schülerzahl eintragen.
        </p>

        <div class="mt-4 rounded border border-light-tx-2 dark:border-dark-tx-2 bg-light-ui dark:bg-dark-ui px-4 py-3 text-sm text-light-tx-2 dark:text-dark-tx-2 space-y-1">
            <p><strong class="text-light-tx dark:text-dark-tx">Wirkung einer Budgetänderung:</strong></p>
            <ul class="list-disc list-inside space-y-0.5">
                <li>Das neue Limit gilt sofort für alle bereits angemeldeten Nutzer des Jahrgangs.</li>
                <li>Der bisher verbrauchte Betrag bleibt unverändert — nur die Obergrenze wird angepasst.</li>
                <li>Nutzer, die sich erstmals anmelden, erhalten automatisch das neue Budget.</li>
                <li>
                    Das Budget wird <strong>nicht zurückgesetzt.</strong> Die Obergrenze wächst
                    jede Unterrichtswoche um den eingetragenen Betrag — was in ruhigen Wochen
                    übrig bleibt, steht in dichten Wochen zusätzlich zur Verfügung.
                </li>
                <li>
                    Der Vorsprung ist begrenzt: Die Obergrenze eilt dem Verbrauch höchstens
                    wenige Wochen voraus (<code>vorsprung_wochen</code> in
                    <code>budget_tiers.yaml</code>). Wer ein halbes Jahr nichts nutzt, sammelt
                    kein halbes Jahr an.
                </li>
                {#if wochen}
                    <li>
                        Dieses Schuljahr hat <strong>{wochen} Unterrichtswochen</strong>
                        (aus <code>school_year.yaml</code>). Ferienwochen bekommen keine
                        Zuteilung — die Spalte „Max-Kosten je Schuljahr" ist der Betrag,
                        auf den sich die Schule festlegt.
                    </li>
                {:else}
                    <li class="text-light-re dark:text-dark-re">
                        Die Zahl der Unterrichtswochen ist nicht ermittelbar —
                        <code>school_year.yaml</code> prüfen. Ohne sie fehlt die Jahressumme.
                    </li>
                {/if}
                <li>
                    Zum Schuljahresbeginn startet die Zählung neu; Reste werden nicht
                    ins nächste Schuljahr übernommen.
                </li>
            </ul>
        </div>

        <div class="mt-6">
            <button
                disabled={!isValid || changedGrades.length === 0}
                onclick={() => showConfirm = true}
                class="px-6 py-2 rounded bg-light-ma dark:bg-dark-ma text-light-tx dark:text-dark-tx
                       hover:bg-light-ma/90 dark:hover:bg-dark-ma/90
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors font-medium"
            >
                Speichern
            </button>
        </div>

    {/if}
</div>

<!-- Bestaetigungs-Dialog -->
{#if showConfirm}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div class="bg-light-bg dark:bg-dark-bg rounded-lg border
                    border-light-tx-2 dark:border-dark-tx-2
                    p-6 max-w-md w-full mx-4 space-y-4 shadow-xl">
            <div class="flex items-center gap-2">
                <PiggyBank class="w-6 h-6 text-light-tx dark:text-dark-tx" />
                <h2 class="text-xl font-semibold text-light-tx dark:text-dark-tx">Budgets speichern?</h2>
            </div>

            <ul class="list-disc list-inside text-light-tx dark:text-dark-tx">
                {#each changedGrades as g}
                    <li>
                        {g.label}: {g.max_budget_eur.toFixed(2)} € → 
                        {parseFloat(editedBudgets[g.key]).toFixed(2)} €
                    </li>
                {/each}
            </ul>

            <p class="text-light-tx dark:text-dark-tx">
                Geschätzte Maximalkosten je Unterrichtswoche: <strong>{eur(totalPeriod())}</strong>
            </p>
            <p class="text-light-tx dark:text-dark-tx">
                Geschätzte Maximalkosten je Schuljahr: <strong>{eur(totalAnnual())}</strong>
                {#if wochen}
                    <span class="text-light-tx-2 dark:text-dark-tx-2">
                        ({wochen} Unterrichtswochen)
                    </span>
                {/if}
            </p>
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                Änderungen werden sofort auf alle bestehenden Nutzer angewendet.
            </p>

            {#if saveError}<ErrorBanner message={saveError} />{/if}

            <div class="flex gap-3 justify-end">
                <button
                    onclick={confirmSave}
                    disabled={saving}
                    class="px-4 py-2 rounded bg-light-ma dark:bg-dark-ma text-light-tx dark:text-dark-tx
                           hover:bg-light-ma/90 dark:hover:bg-dark-ma/90
                           disabled:opacity-50 disabled:cursor-not-allowed
                           transition-colors font-medium flex items-center gap-2"
                >
                    {#if saving}
                        <LoaderCircle class="w-4 h-4 animate-spin" />
                    {/if}
                    Bestätigen
                </button>
                <button
                    onclick={() => showConfirm = false}
                    disabled={saving}
                    class="px-4 py-2 rounded bg-light-ui dark:bg-dark-ui border border-light-tx-2 dark:border-dark-tx-2
                           text-light-tx dark:text-dark-tx
                           hover:bg-light-ui/80 dark:hover:bg-dark-ui/80
                           disabled:opacity-50 disabled:cursor-not-allowed
                           transition-colors"
                >
                    Abbrechen
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    table {
        border-collapse: collapse;
    }
</style>
