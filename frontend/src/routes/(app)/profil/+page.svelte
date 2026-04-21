<script>
    import { Sun, Moon, Monitor, Save } from "lucide-svelte";
    import { themePref } from "$lib/stores/theme.js";
    import { user } from "$lib/stores/user.js";
    import { goto } from "$app/navigation";
    import { patchPreferences, getPreferences } from "$lib/api.js";
    import { onMount } from "svelte";

    const themeOptions = [
        { value: "light", label: "Hell", Icon: Sun },
        { value: "dark", label: "Dunkel", Icon: Moon },
        { value: "system", label: "System", Icon: Monitor },
    ];

    const sidebarLimitOptions = [5, 10, 15, 20, 25]

    // User-Präferenzen laden
    let preferences = $state({})
    let loading = $state(true)

    onMount(async () => {
        try {
            preferences = await getPreferences()
        } catch (err) {
            console.error('Fehler beim Laden der Präferenzen:', err)
        } finally {
            loading = false
        }
    })

    async function updateSidebarLimit(event) {
        const value = parseInt(event.target.value)
        await patchPreferences({ sidebar_recent_chats_limit: value })
        // User-Store aktualisieren
        user.update(u => ({
            ...u,
            preferences: {
                ...u?.preferences,
                sidebar_recent_chats_limit: value
            }
        }))
    }

    function doSave() {
        goto("/");
    }
</script>

<div class="h-full overflow-y-auto"><div class="max-w-2xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6 text-light-tx dark:text-dark-tx">
        Profil
    </h1>

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
            Chat-Sidebar
        </h2>
        <div class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2">
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
</div></div>
