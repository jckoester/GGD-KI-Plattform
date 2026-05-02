<script>
    import { onMount } from "svelte";
    import { Bot, Loader2 } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import {
        getAdminAssistants,
        activateAssistant,
        deactivateAssistant,
    } from "$lib/api.js";

    let items = $state([])
    let loading = $state(true)
    let error = $state(null)
    let successMessage = $state(null)

    // Status-Badge-Farben
    const STATUS_CLASS = {
        active: "bg-light-gr/15 dark:bg-dark-gr/15 text-light-gr dark:text-dark-gr",
        draft: "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
        disabled: "bg-light-re/15 dark:bg-dark-re/15 text-light-re dark:text-dark-re",
    };
    const STATUS_LABEL = {
        active: "Aktiv",
        draft: "Entwurf",
        disabled: "Deaktiviert",
    };

    // Audience-Labels
    const AUDIENCE_LABELS = {
        all: "Alle",
        student: "Schüler:innen",
        teacher: "Lehrkräfte",
    };

    $effect(() => {
        if (successMessage) {
            const t = setTimeout(() => successMessage = null, 3000)
            return () => clearTimeout(t)
        }
    })

    async function loadAllAssistants() {
        loading = true;
        error = null;
        try {
            // Alle Assistenten laden (kein Statusfilter)
            const result = await getAdminAssistants({})
            items = result.items
        } catch (e) {
            error = e.message ?? 'Fehler beim Laden der Assistenten'
        } finally {
            loading = false
        }
    }

    async function handleActivate(item) {
        try {
            await activateAssistant(item.id)
            item.status = 'active'
            items = items  // Trigger Reaktivität
            successMessage = `„${item.name}" aktiviert.`
        } catch (e) {
            error = e.message ?? 'Fehler beim Aktivieren'
        }
    }

    async function handleDeactivate(item) {
        try {
            await deactivateAssistant(item.id)
            item.status = 'disabled'
            items = items  // Trigger Reaktivität
            successMessage = `„${item.name}" deaktiviert.`
        } catch (e) {
            error = e.message ?? 'Fehler beim Deaktivieren'
        }
    }

    function getActionLabel(item) {
        return item.status === 'active' ? 'Deaktivieren' : 'Aktivieren'
    }

    function getActionButtonClass(item) {
        if (item.status === 'active') {
            return 'text-xs px-2 py-1 rounded border border-light-re dark:border-dark-re text-light-re dark:text-dark-re hover:bg-light-re/10 dark:hover:bg-dark-re/10'
        }
        return 'text-xs px-2 py-1 rounded border border-light-gr dark:border-dark-gr text-light-gr dark:text-dark-gr hover:bg-light-gr/10 dark:hover:bg-dark-gr/10'
    }

    onMount(loadAllAssistants);
</script>

<div class="h-full overflow-y-auto p-6">
    <div class="max-w-4xl mx-auto">
        <div class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx">
            <Bot class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Assistenten-Freigabe</h1>
        </div>

        <div class="mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
            Wer welche Assistenten sehen und nutzen kann
        </div>

        {#if error}
            <div class="mb-4">
                <ErrorBanner message={error} />
            </div>
        {/if}

        {#if successMessage}
            <div class="mb-4">
                <SuccessBanner message={successMessage} />
            </div>
        {/if}

        {#if loading}
            <div class="flex items-center justify-center py-12">
                <Loader2 class="w-6 h-6 animate-spin" />
            </div>
        {:else}
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="text-left text-light-tx-2 dark:text-dark-tx-2">
                        <tr class="border-b border-light-ui-3 dark:border-dark-ui-3">
                            <th class="pb-3 pr-4 font-medium">Name</th>
                            <th class="pb-3 pr-4 font-medium">Beschreibung</th>
                            <th class="pb-3 pr-4 font-medium">Zielgruppe</th>
                            <th class="pb-3 pr-4 font-medium">Status</th>
                            <th class="pb-3 pr-4 font-medium">Aktion</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#if items.length === 0}
                            <tr>
                                <td colspan="5" class="py-4 text-center text-light-tx-2 dark:text-dark-tx-2">
                                    Keine Assistenten gefunden.
                                </td>
                            </tr>
                        {:else}
                            {#each items as item}
                                <tr class="border-b border-light-ui-3 dark:border-dark-ui-3">
                                    <td class="py-3 pr-4 font-medium text-light-tx dark:text-dark-tx">
                                        {item.name}
                                    </td>
                                    <td class="py-3 pr-4 max-w-[200px] truncate text-light-tx-2 dark:text-dark-tx-2">
                                        {item.description ?? ''}
                                    </td>
                                    <td class="py-3 pr-4 text-light-tx-2 dark:text-dark-tx-2">
                                        {AUDIENCE_LABELS[item.audience] ?? item.audience ?? ''}
                                    </td>
                                    <td class="py-3 pr-4">
                                        <span class="px-2 py-1 rounded-full text-xs {STATUS_CLASS[item.status] ?? STATUS_CLASS.draft}">
                                            {STATUS_LABEL[item.status] ?? item.status}
                                        </span>
                                    </td>
                                    <td class="py-3 pr-4">
                                        {#if item.status === 'active'}
                                            <button
                                                onclick={() => handleDeactivate(item)}
                                                class="text-xs px-2 py-1 rounded border border-light-re dark:border-dark-re text-light-re dark:text-dark-re hover:bg-light-re/10 dark:hover:bg-dark-re/10"
                                            >
                                                Deaktivieren
                                            </button>
                                        {:else if item.status === 'draft' || item.status === 'disabled'}
                                            <button
                                                onclick={() => handleActivate(item)}
                                                class="text-xs px-2 py-1 rounded border border-light-gr dark:border-dark-gr text-light-gr dark:text-dark-gr hover:bg-light-gr/10 dark:hover:bg-dark-gr/10"
                                            >
                                                Aktivieren
                                            </button>
                                        {/if}
                                    </td>
                                </tr>
                            {/each}
                        {/if}
                    </tbody>
                </table>
            </div>
        {/if}
    </div>
</div>
