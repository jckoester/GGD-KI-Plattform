<script>
    import { onMount } from "svelte";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { getSiteText, saveSiteText } from "$lib/api.js";
    import { renderMarkdown } from "$lib/markdown.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    const VALID_KEYS = ["impressum", "datenschutz", "hilfe", "regeln"];
    const LABELS = {
        impressum: "Impressum",
        datenschutz: "Datenschutzerklärung",
        hilfe: "Hilfe",
        regeln: "Nutzungsregeln",
    };

    // Initialer Tab aus URL-Parameter, Fallback auf 'impressum'
    let activeKey = $state(
        VALID_KEYS.includes($page.url.searchParams.get("tab"))
            ? $page.url.searchParams.get("tab")
            : "impressum",
    );

    let texts = $state({}); // key -> string (geladener DB-Stand)
    let edited = $state({}); // key -> string (Textarea-Wert)
    let loading = $state(false);
    let saving = $state(false);
    let error = $state(null);

    let saveSuccess = $state(null); // key des zuletzt gespeicherten Tabs
    let saveError = $state(null);

    onMount(() => loadTab(activeKey));

    async function loadTab(key) {
        if (key in texts) return; // Cache-Hit: kein erneuter Fetch
        loading = true;
        error = null;
        try {
            const data = await getSiteText(key);
            texts[key] = data.content;
            edited[key] = data.content;
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    function switchTab(key) {
        activeKey = key;
        goto(`/settings/texts?tab=${key}`, { replaceState: true, noScroll: true, keepFocus: true });
        loadTab(key);
    }

    let isChanged = $derived(edited[activeKey] !== texts[activeKey]);

    async function handleSave() {
        if (!activeKey || saving || !isChanged) return;

        saving = true;
        saveError = null;
        saveSuccess = null;

        try {
            await saveSiteText(activeKey, edited[activeKey]);
            // Update cached text after successful save
            texts[activeKey] = edited[activeKey];
            saveSuccess = activeKey;
            setTimeout(() => { saveSuccess = null; }, 3000);
        } catch (e) {
            saveError = e.message || "Fehler beim Speichern";
        } finally {
            saving = false;
        }
    }

    function hasUnsavedChanges(key) {
        return edited[key] !== undefined && edited[key] !== texts[key];
    }
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
           hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    ← Zurück
</button>

<div class="max-w-4xl mx-auto py-8">
    <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
        <h1 class="text-2xl font-semibold">Site-Texte bearbeiten</h1>
    </div>

    {#if error}<ErrorBanner message={error} />{/if}

    <!-- Tabs -->
    <div
        class="flex gap-1 mb-6 border-b border-light-ui-3 dark:border-dark-ui-3"
    >
        {#each VALID_KEYS as key}
            <button
                onclick={() => switchTab(key)}
                class="px-4 py-2 text-sm font-medium rounded-t transition-colors
                       {activeKey === key
                    ? 'bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx border border-b-0 border-light-ui-3 dark:border-dark-ui-3'
                    : 'text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
            >
                {LABELS[key]}
                {#if hasUnsavedChanges(key)}
                    <span class="ml-1 text-primary dark:text-primary-dark"
                        >●</span
                    >
                {/if}
            </button>
        {/each}
    </div>

    {#if loading && !texts[activeKey]}
        <div class="text-center py-8 text-light-tx-2 dark:text-dark-tx-2">
            Laden...
        </div>
    {:else}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Editor -->
            <div>
                <label
                    for="editor"
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-2"
                >
                    Markdown-Inhalt
                </label>
                <textarea
                    id="editor"
                    bind:value={edited[activeKey]}
                    rows="20"
                    class="w-full p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                           bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                           font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark"
                    placeholder="Geben Sie den Inhalt im Markdown-Format ein..."
                />
            </div>

            <!-- Preview -->
            <div>
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-2"
                >
                    Vorschau
                </label>
                <div
                    class="p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                            bg-light-ui dark:bg-dark-ui min-h-[400px]"
                >
                    {#if edited[activeKey]}
                        <div class="prose dark:prose-invert max-w-none">
                            {@html renderMarkdown(edited[activeKey])}
                        </div>
                    {:else}
                        <p class="text-light-tx-2 dark:text-dark-tx-2 text-sm">
                            Kein Inhalt — die Vorschau ist leer.
                        </p>
                    {/if}
                </div>
            </div>
        </div>

        <!-- Save Button -->
        <div class="mt-6 flex gap-3">
            <button
                onclick={handleSave}
                disabled={saving || !isChanged}
                class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                       hover:bg-primary-dark dark:hover:bg-primary transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed
                       {saving ? 'cursor-wait' : ''}"
            >
                {saving ? "Speichern..." : "Speichern"}
            </button>

            {#if saveSuccess === activeKey}
                <span
                    class="px-3 py-2 text-sm text-green-600 dark:text-green-400"
                >
                    Gespeichert
                </span>
            {/if}

            {#if saveError}
                <span class="px-3 py-2 text-sm text-red-600 dark:text-red-400">
                    {saveError}
                </span>
            {/if}
        </div>
    {/if}
</div>
