<script>
    import { onMount } from "svelte";
    import { Info, Save } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    let {
        title,
        modelLabel = "Modell",
        getMatrix,
        saveMatrix,
        emptyMessage = null,
        intro = null,
    } = $props();

    let matrix = $state(null); // { models, teams, allowlists }
    let dirty = $state({}); // { team_id: Set<model_id> } — lokale Änderungen
    let loading = $state(true);
    let saving = $state(false);
    let error = $state(null);
    let saveError = $state(null);

    function formatTeamLabel(teamId) {
        if (teamId === "lehrkraefte") return "Lehrkräfte";
        const grade = teamId.replace("jahrgang-", "");
        return `Klasse ${grade}`;
    }

    function syncDirty() {
        dirty = Object.fromEntries(
            matrix.teams.map((t) => [t, new Set(matrix.allowlists[t] ?? [])]),
        );
    }

    onMount(async () => {
        try {
            matrix = await getMatrix();
            syncDirty();
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    });

    async function save() {
        saving = true;
        saveError = null;
        try {
            const allowlists = Object.fromEntries(
                Object.entries(dirty).map(([t, s]) => [t, [...s]]),
            );
            matrix = await saveMatrix(allowlists);
            syncDirty();
        } catch (e) {
            saveError = e.message;
        } finally {
            saving = false;
        }
    }
</script>

<section class="space-y-4">
    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">{title}</h2>

    {#if intro}
        <div
            class="flex center-items gap-4 border-light-tx-2 dark:border-dark-tx-2 border-text-light-tx-2 dark:text-dark-tx-2 p-4 border rounded bg-light-bg dark:bg-dark-bg"
        >
            <Info class="w-12 h-6 mt-0" />
            <span class="text-sm">{@render intro()}</span>
        </div>
    {/if}

    {#if error}
        <ErrorBanner message={error} />
    {:else if loading}
        <LoadingBanner />
    {:else if emptyMessage && matrix.models.length === 0}
        <div
            class="flex center-items gap-4 p-4 border rounded border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2"
        >
            <span class="text-sm">{emptyMessage}</span>
        </div>
    {:else}
        {#if saveError}<ErrorBanner message={saveError} />{/if}

        <button
            onclick={save}
            disabled={saving || loading}
            class="px-4 py-2 text-light-tx dark:text-dark-tx rounded border border-light-tx-2 bg-light-ui-3 hover:bg-light-gr-2 dark:bg-dark-ui-3 dark:hover:bg-dark-gr-2 disabled:opacity-50"
        >
            <div class="flex items-center gap-2">
                <Save class="w-4 h-4" />
                {saving ? "Wird gespeichert…" : "Speichern"}
            </div>
        </button>

        <!-- Matrix-Tabelle -->
        <div class="overflow-x-auto">
            <table
                class="min-w-full border-collapse border border-light-tx-2 dark:border-dark-tx-2"
            >
                <thead
                    class="bg-light-ui-3 dark:bg-dark-ui-3 border-light-tx-2 dark:border-dark-tx-2 dark:text-dark-tx"
                >
                    <tr>
                        <th
                            class="p-3 border border-light-tx-2 dark:border-dark-tx-2 text-left"
                            >{modelLabel}</th
                        >
                        {#each matrix.teams as team}
                            <th
                                class="border border-light-tx-2 dark:border-dark-tx-2 w-8 h-24 p-0 relative"
                            >
                                <div
                                    class="absolute inset-0 flex items-center justify-center"
                                >
                                    <span
                                        class="rotate-270 whitespace-nowrap text-sm font-medium"
                                        >{formatTeamLabel(team)}</span
                                    >
                                </div>
                            </th>
                        {/each}
                    </tr>
                </thead>
                <tbody>
                    {#each matrix.models as model}
                        <tr
                            class="hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 dark:text-dark-tx"
                        >
                            <td
                                class="p-3 border border-light-tx-3 dark:border-dark-tx-3"
                            >
                                <code class="text-sm">{model}</code>
                            </td>
                            {#each matrix.teams as team}
                                <td
                                    class="p-3 border border-light-tx-3 dark:border-dark-tx-3 text-center"
                                >
                                    <input
                                        type="checkbox"
                                        checked={dirty[team]?.has(model)}
                                        onchange={(e) => {
                                            if (e.target.checked) {
                                                dirty[team].add(model);
                                            } else {
                                                dirty[team].delete(model);
                                            }
                                            dirty = dirty; // Reaktivität triggern
                                        }}
                                        class="w-5 h-5 text-light-gr dark:text-dark-gr border-light-tx-3 dark:border-dark-tx-3"
                                    />
                                </td>
                            {/each}
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>

        <button
            onclick={save}
            disabled={saving || loading}
            class="px-4 py-2 text-light-tx dark:text-dark-tx rounded border border-light-tx-2 bg-light-ui-3 hover:bg-light-gr-2 dark:bg-dark-ui-3 dark:hover:bg-dark-gr-2 disabled:opacity-50"
        >
            <div class="flex items-center gap-2">
                <Save class="w-4 h-4" />
                {saving ? "Wird gespeichert…" : "Speichern"}
            </div>
        </button>
    {/if}
</section>
