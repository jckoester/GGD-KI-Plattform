<script>
    import { User, Sun, Moon, Monitor, Save, ArrowLeft } from "lucide-svelte";
    import { themePref } from "$lib/stores/theme.js";
    import { user } from "$lib/stores/user.js";
    import { budget } from "$lib/stores/budget.js";
    import { goto } from "$app/navigation";
    import { patchPreferences, getPreferences } from "$lib/api.js";
    import { onMount } from "svelte";

    const themeOptions = [
        { value: "light", label: "Hell", Icon: Sun },
        { value: "dark", label: "Dunkel", Icon: Moon },
        { value: "system", label: "System", Icon: Monitor },
    ];

    const sidebarLimitOptions = [5, 10, 15, 20, 25];
    const costGranularityOptions = [
        { value: "none", label: "Gar nicht" },
        { value: "conversation", label: "Pro Konversation" },
        { value: "message", label: "Pro Nachricht" },
        { value: "both", label: "Beides" },
    ];

    // User-Präferenzen laden
    let preferences = $state({});
    let loading = $state(true);

    // Formatierung: 2 Dezimalstellen, Komma als Trennzeichen
    function fmt(v) {
        if (v == null) return "–";
        return v.toLocaleString("de-DE", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    onMount(async () => {
        try {
            preferences = await getPreferences();
        } catch (err) {
            console.error("Fehler beim Laden der Präferenzen:", err);
        } finally {
            loading = false;
        }
    });

    async function updatePreference(key, value) {
        await patchPreferences({ [key]: value });
        // User-Store aktualisieren
        user.update((u) => ({
            ...u,
            preferences: {
                ...u?.preferences,
                [key]: value,
            },
        }));
        // Lokale Präferenzen aktualisieren
        preferences = { ...preferences, [key]: value };
    }

    async function updateSidebarLimit(event) {
        const value = parseInt(event.target.value);
        await updatePreference("sidebar_recent_chats_limit", value);
    }

    function doSave() {
        goto("/");
    }

    let pct = $derived(
        $budget?.max_budget_eur && $budget?.spend_eur != null
            ? Math.min(
                  100,
                  Math.round(
                      ($budget.spend_eur / $budget.max_budget_eur) * 100,
                  ),
              )
            : null,
    );
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="h-full overflow-y-auto">
    <div class="max-w-2xl mx-auto p-6">
        <div
            class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx"
        >
            <User class="w-6 h-6 " />
            <h1 class="text-2xl font-semibold">Profil</h1>
        </div>

        <!-- Budget-Abschnitt -->
        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Budget
            </h2>
            {#if $budget && $budget.max_budget_eur != null}
                <div>
                    {#if pct != null}
                        <div
                            class="w-full h-1 rounded bg-light-ui-3 dark:bg-dark-ui-3 mb-3"
                        >
                            <div
                                class="h-1 rounded transition-all {pct >= 20
                                    ? 'bg-red-500'
                                    : 'bg-primary'}"
                                style="width: {100 - pct}%"
                            ></div>
                        </div>
                    {/if}
                </div>

                <div class="flex items-center text-sm mb-2">
                    <span class="text-light-tx-2 dark:text-dark-tx-2">
                        {#if $budget.budget_duration === "1mo"}
                            Diesen Monat sind noch
                        {:else}
                            Noch
                        {/if}
                        {fmt($budget?.remaining_eur)} € von {fmt(
                            $budget?.max_budget_eur,
                        )} € verfügbar.
                    </span>
                    {#if pct != null}
                        <span
                            class="ml-auto text-sm text-light-tx-2 dark:text-dark-tx-2"
                            >{100 - pct} %</span
                        >
                    {/if}
                </div>
                {#if $budget.budget_duration !== "1mo"}
                    <div
                        class="text-sm mb-2 text-light-tx-2 dark:text-dark-tx-2"
                    >
                        Gültig für {fmt($budget.budget_duration)}.
                    </div>
                {/if}
            {:else}
                <div class="text-sm mb-2 text-light-tx-2 dark:text-dark-tx-2">
                    Budgetdaten können derzeit nicht angezeigt werden.
                </div>
            {/if}
        </section>

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Darstellungsmodus
            </h2>
            <div class="flex gap-2">
                {#each themeOptions as { value, label, Icon }}
                    <button
                        class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors
                        {$themePref === value
                            ? 'bg-primary text-white'
                            : 'bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                        onclick={() => themePref.set(value)}
                    >
                        <Icon class="w-4 h-4" />
                        {label}
                    </button>
                {/each}
            </div>
        </section>

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Kostenanzeige
            </h2>
            <div>
                <label
                    class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                >
                    Kosten im Chat anzeigen
                </label>
                <select
                    onchange={(e) =>
                        updatePreference("cost_granularity", e.target.value)}
                    value={preferences?.cost_granularity ?? "none"}
                    class="w-full max-w-56 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary"
                    disabled={loading}
                >
                    {#each costGranularityOptions as { value, label }}
                        <option {value}>{label}</option>
                    {/each}
                </select>
            </div>
        </section>

        <section class="mb-8">
            <h2
                class="text-base font-semibold mb-3 text-light-tx-2 dark:text-dark-tx-2"
            >
                Chat-Sidebar
            </h2>
            <div class="space-y-4">
                <div>
                    <label
                        class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
                    >
                        Anzahl zuletzt angezeigter Chats
                    </label>
                    <select
                        value={preferences?.sidebar_recent_chats_limit ?? 10}
                        onchange={updateSidebarLimit}
                        class="w-full max-w-40 px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                           focus:outline-none focus:ring-2 focus:ring-primary"
                        disabled={loading}
                    >
                        {#each sidebarLimitOptions as opt}
                            <option value={opt}>{opt}</option>
                        {/each}
                    </select>
                </div>
            </div>
        </section>

        <section class="mb-8">
            <button
                class="px-4 py-2 rounded-md text-sm font-medium bg-light-gr-2 dark:bg-dark-gr-2 text-white hover:bg-light-gr dark:hover:bg-dark-gr transition-colors"
                onclick={doSave}
            >
                <Save class="w-4 h-4 inline-block mr-1 mb-1" /> Speichern
            </button>
        </section>
    </div>
</div>
